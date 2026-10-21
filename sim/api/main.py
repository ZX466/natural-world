"""FastAPI 应用装配 — M0（sim/api/main.py）。

路由：/api/health（戏外探针）/ /api/world/map（碰撞层静态资产，HTTP 不走 WS）/
/ws（WS 网关）。启动即建世界（创世事件走 apply），驱动任务随 lifespan 起。
"""

from __future__ import annotations

import contextlib
import ipaddress
import uuid
from collections import deque
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from sim.api.anchors import router as anchors_router
from sim.api.errors import install_error_handlers
from sim.api.settings import router as settings_router
from sim.api.ws import (
    ConnectionManager,
    _error_frame,
    check_origin,
    frames_of,
    handle_client_message,
    map_static_payload,
    run_world_driver,
    session_state_payload,
    snapshot_payload,
    ws_auth_token,
)
from sim.core.events import EventKind, tile_changed_event, world_create_event
from sim.core.persistence.database import create_session_factory, init_database
from sim.core.persistence.store import SqlEventStore
from sim.core.rng import RngRegistry
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.world.map import TileMap

logger = structlog.get_logger()

manager = ConnectionManager()

# M7（R7）：创世名册——陈默 + 3 名占位村民（静止实体，AI 归 M2 装配线）。
# 批次 B：占位村民退役，正式名册 50 村民（sim/content/villagers.py）入列——
# 世界 = chenmo + 50 villager（51 实体）。
GENESIS_ENTITIES: tuple[str, ...] = (
    "chenmo",
    *(f"villager_{i + 1:02d}" for i in range(50)),
    "cat_grey",
    "dog_black",
    "raven",
)
#: 出生点（2026-10-12 D6-D8 换图：村广场 anchor 侧可走格；桃花源
#: Spawning Blocks 候选 90 格内取村广场带（行 51-54）确定性选点）
SPAWN_TILE: tuple[int, int] = (100, 53)
TOWN_MAP_PATH = Path(__file__).resolve().parents[1] / "content" / "linhe-town.json"
WORLD_DB_PATH = Path("world.db")


def _fallback_map() -> TileMap:
    """M0 占位 32×32 全平图（真实图缺失/损坏时的 fail-safe 底座）。"""
    from sim.world.map import CHUNK_SIZE, Chunk

    chunks = {}
    for cy in range(2):
        for cx in range(2):
            chunks[(cx, cy)] = Chunk(
                cx=cx,
                cy=cy,
                ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
    return TileMap(width=32, height=32, chunks=chunks)


def _default_map() -> TileMap:
    """优先 sim/content 真实小镇图；缺失/损坏回退占位（fail-safe，启动不炸）。"""
    if TOWN_MAP_PATH.exists():
        try:
            return TileMap.from_json_file(TOWN_MAP_PATH)
        except Exception as exc:
            logger.warning("map.town_load_failed", reason=str(exc))
    return _fallback_map()


async def rebuild_tile_map(branch_store: Any) -> TileMap:
    """从静态底图与本分支的瓦片事件重建碰撞，不继承旧分支内存图。"""
    from sim.core.events import TileChangedPayload

    tile_map = _default_map()
    if branch_store is not None:
        for event in await branch_store.read_branch_history():
            if event["event_type"] == "tile_changed":
                payload = TileChangedPayload.model_validate(event["payload"])
                tile_map = tile_map.with_collision(
                    payload.x, payload.y, walkable=payload.tile_id != 0
                )
    return tile_map


#: 需要补发 tile 还原事件的结构终态（起点 STARTED/CHECKPOINT 不改占格）。
_TILE_RESTORING_KINDS = {
    EventKind.STRUCTURE_COLLAPSED,
    EventKind.STRUCTURE_REMOVED,
}


def _ground_tile_id(tile_map: TileMap, x: int, y: int) -> int:
    """静态底图在 (x,y) 的原 tile_id。

    ground/collision 挂在 **Chunk** 上（`sim/world/map.py`），不是 TileMap
    顶层数组：全局坐标要先 chunk_of 再折成本地下标。
    """
    from sim.world.map import CHUNK_SIZE

    chunk = tile_map.chunks[tile_map.chunk_of(x, y)]
    lx, ly = x % CHUNK_SIZE, y % CHUNK_SIZE
    return int(chunk.ground[ly * CHUNK_SIZE + lx])


def _with_structure_tile_restore(
    events: list[Any],
    structures: Any,
    tile_map: TileMap,
) -> list[Any]:
    """P-6：坍塌/拆除后补发逐格 `tile_changed(tile_id=静态原值)`。

    没有这一步，建筑倒了格子却**永久为墙**（`derive_tile_events` 此前零生产
    调用点），玩家会看到看不见的障碍。还原目标取静态底图原值，因此拆掉建筑
    后地面恢复成它本来的样子（草地仍可行走、水面仍不可走）。

    `structures` 必须是**事件应用前**的快照（调用方在 observe 之前调用）。
    """
    out: list[Any] = []
    for event in events:
        out.append(event)
        if event.event_type not in _TILE_RESTORING_KINDS:
            continue
        sid = str(event.payload.get("structure_id", ""))
        snapshot = getattr(structures, "get", lambda _k: None)(sid)
        if snapshot is None:
            continue
        # 逐格还原到**该格**的静态原值（不能共用首格值）。
        for x, y in snapshot.tiles:
            out.append(
                tile_changed_event(
                    event.tick,
                    x,
                    y,
                    _ground_tile_id(tile_map, x, y),
                    branch_id=event.branch_id,
                )
            )
    return out


async def build_loop() -> tuple[TickLoop, Any]:
    """组装世界：store（建表）+ bus + TickLoop + 创世 + 出生点搬运。返回 (loop, store)。"""
    from sqlalchemy.ext.asyncio import create_async_engine

    # D20：SQLite 写并发止血（用户实测 POST /api/anchors 500 database is locked
    # ——同步 anchors 写面与 aiosqlite 驱动事务撞锁即硬炸）。WAL 允许读写并行、
    # busy_timeout 让写者等锁而不是立刻炸；不改变单写者语义（flush 串行契约不动）。
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{WORLD_DB_PATH.as_posix()}",
        connect_args={"timeout": 10.0},  # sqlite3 busy_timeout（秒）
    )
    await init_database(engine)  # 开发库快速起步；生产走 alembic upgrade head
    # D20：WAL 日志模式（库级持久设置，一次即可）——读写并行、写锁等待
    # 而非硬炸；S2 已让同步存档写在线程池内闭环，避免阻塞 driver 的异步提交。
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
    session_factory = create_session_factory(engine)
    store = SqlEventStore(session_factory)
    from sim.core.persistence.world_restore import has_world, restore_world

    try:
        if await has_world(store):
            branch_id = await store.current_branch_id_or_none()
            if branch_id is None:
                # 留下只读诊断面；lifespan 的 source_ready 闸门禁止驱动/保存。
                return TickLoop(_make_clock(), build_default_bus(), WorldState()), store
            return await restore_world(store, branch_id), store
    except Exception:
        await engine.dispose()
        raise
    loop = TickLoop(clock=_make_clock(), bus=build_default_bus(), state=WorldState(world_seed=42))
    loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=GENESIS_ENTITIES))
    # 批次 B（D19 换调）：创世村民出生=**定籍点邻域**（territory_spawn_positions
    # ——人一落地就在自己村里，无开局大迁徙挤巷；D18 写的函数本批接线）。
    from sim.content.villagers import territory_spawn_positions

    tile_map_for_spawn = _default_map()
    roster = [eid for eid in GENESIS_ENTITIES if eid.startswith("villager_")]
    # 主角先占 SPAWN（村民散布避开同格——2026-10-12 换图后药铺=村广场带，
    # 定籍锚点 (100,52) 邻域恰含 SPAWN，无 occupied 参数时首个村民撞主角格）
    spawn_of: dict[str, tuple[int, int]] = {"chenmo": SPAWN_TILE}
    positions = territory_spawn_positions(
        tile_map_for_spawn, roster, occupied={"chenmo": SPAWN_TILE}
    )
    for eid, pos in positions.items():
        spawn_of[eid] = pos
    # 动物落点：村广场带可走格（2026-10-12 换图；旧 (9..11,16) 随旧图退役）
    spawn_of.update({"cat_grey": (99, 52), "dog_black": (101, 52), "raven": (101, 53)})
    for eid in GENESIS_ENTITIES:
        loop.issue_move(eid, [(0, 0), spawn_of[eid]])
    loop.advance_frame(1.0)
    return loop, store


def _make_clock():
    from sim.core.clock import GameClock

    return GameClock(speed=1.0)


def _active_profile_snapshot_provider():
    """批次 C：active LLM profile → ProfileSnapshot 提供器（driver 每轮取）。

    无 active profile 返回 None（driver 零调用降级）。api_key 解密只发生在
    load_profile_snapshot 调用瞬间（K3：用完即丢，明文只活在快照生命周期内）。
    读档/fork 后 profile 表换分支不在本批范围（profile 是戏外配置面）。
    """
    from sim.api.settings import get_profile_store
    from sim.llm.client import load_profile_snapshot as _load_snapshot

    def _provider():
        try:
            row = get_profile_store().get_active()
        except Exception as exc:  # 设置库故障不拖垮世界（降级无 LLM）
            logger.warning("chenmo.profile_provider_failed", reason=str(exc))
            return None
        if row is None:
            return None
        return _load_snapshot(
            profile_name=row.name,
            base_url=row.base_url,
            model=row.model,
            temperature=row.temperature,
            max_tokens=row.max_tokens,
            api_key_enc=row.api_key_enc,
        )

    return _provider


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    import asyncio

    from sim.core.logsetup import setup_logging
    from sim.perception.senses import run_perception_step

    setup_logging()  # K8：redact_sensitive 进全局日志链（第二道防线）
    loop, store = await build_loop()
    world_write_lock = asyncio.Lock()
    app.state.world_write_lock = world_write_lock
    from sim.core.persistence.npc_store import NpcStore

    current_branch = await store.current_branch_id_or_none()
    tile_map = await rebuild_tile_map(
        NpcStore(store, branch_id=current_branch) if current_branch is not None else None
    )
    # C06-③：感知挂载进 tick 固定执行序第 3 步（帧键=rtoken，WS 不广播）
    # 批次 D8：感知叙事接真名（rtoken→戏内名映射；名册 villagers + 陈默）。
    # 名字是戏内事实可出站；映射后 prompt 说「赵铁柱正朝这边走」而非「rt-…」。
    from sim.content.protagonist import CHENMO_ID, build_anchor
    from sim.content.villagers import VILLAGER_IDS, VILLAGER_NAMES

    _display_names: dict[str, str] = dict(zip(VILLAGER_IDS, VILLAGER_NAMES, strict=True))
    _display_names[CHENMO_ID] = "陈默"
    from sim.content.animals import ANIMALS, animal_events, seed_animals

    _display_names.update({eid: name for eid, (name, _) in ANIMALS.items()})
    from sim.npc.roles import ROLES, role_events

    _display_names.update({eid: role[0] for eid, role in ROLES.items()})

    # 批次 D10：头顶名字供数——快照 actor.name 出站（同源映射，感知真名一致）。
    from sim.api.ws import set_display_names

    set_display_names(_display_names)

    loop.attach_perception(
        lambda state, tick_events: run_perception_step(
            state,
            build_runtime.tile_map,
            tick_events,
            display_name_of=_display_names,
            species_of={eid: species for eid, (_, species) in ANIMALS.items()},
            include_fauna=True,
        )
    )

    async def on_flush(events: list[Any]) -> None:
        from sim.core.persistence.world_restore import flush_world

        branch_id = await store.current_branch_id_or_none() or "main"
        # P-6：结构终态（坍塌/拆除）必须补发逐格 tile_changed 恢复可走。
        # 派生必须在 maintenance.observe **之前**——observe 会把 REMOVED 从
        # structures pop 掉，之后拿不到 tiles；且此时快照仍是事件前的旧态，
        # 正好是派生需要的「该结构占着哪些格」。
        # 收编 codex DA-01/DA-02：落库改走 flush_world（事件 + 完整世界检查点
        # 同事务），但**派生必须先做**，派生后的完整列表才是本批真相。
        events = _with_structure_tile_restore(events, maintenance.structures, tile_map)
        await flush_world(store, branch_id, loop, events)
        maintenance.observe(events)
        for event in events:
            if event.event_type.value == "structure.completed":
                from sim.api.ws import set_structure_phase

                sid = str(event.payload["structure_id"])
                structure = maintenance.structures.get(sid)
                if structure is not None:
                    set_structure_phase(sid, list(structure.tiles), "built")
        cognition.observe(events)
        branch_id = await store.current_branch_id_or_none()
        if branch_id is not None:
            if memory_store.branch_id != branch_id:
                memory_store.attach_branch(branch_id)
            async with store.session_factory.begin() as session:
                await memory_store.hydrate_if_empty(session)
                await memory_store.flush(session)

    async def on_flush_async() -> None:
        await on_flush(loop.drain_events())

    async def flush_for_anchor() -> None:
        events = list(loop.pending_events)
        await on_flush(events)
        del loop.pending_events[: len(events)]
        loop.pending_broadcast_events.extend(events)

    app.state.flush_for_anchor = flush_for_anchor

    app.state.loop = loop
    app.state.store = store
    app.state.tile_map = tile_map

    from sim.core.persistence.async_memory_store import AsyncMemoryStore

    branch_id = await store.current_branch_id_or_none()
    memory_store = AsyncMemoryStore(branch_id=branch_id or "unbound")
    if branch_id is not None:
        async with store.session_factory() as session:
            await memory_store.hydrate(session)
    app.state.memory_store = memory_store
    from sim.agent.cognition import CognitionState

    cognition = CognitionState()
    app.state.cognition = cognition

    # ── 批次 B：NPC 装配进实况世界 ──────────────────────────────────
    # 1) 播种 50 村民 profile（幂等；库已有则零行）；
    # 2) 装配 NpcRuntime（物化 profiles → 效用决策器）；
    # 3) 挂决策钩子（每 10 tick 一轮 → NPC_ACT 批次 + wander/move 拆解 MOVE）。
    from sim.content.villagers import seed_villagers
    from sim.core.persistence.npc_store import NpcStore
    from sim.npc.assemble import assemble_runtime
    from sim.npc.sim_exec import npc_events_for_tick
    from sim.world.pathfinding import Pathfinder

    seeded = await seed_villagers(store.session_factory)
    if seeded:
        logger.info("npc.seeded", count=seeded)
    await seed_animals(store.session_factory)
    npc_store = NpcStore(store)
    npc_runtime, _hidden_states = await assemble_runtime(npc_store)
    # 批次 D14：真实意愿面——逐人合成（性格/需求/处境 → band 全谱），
    # 替换 D2 的全队 band=1 占位（「四句循环」根因收口）。最终都执行
    # （§10）：verdict 只产独白/defers，不改效用决策。
    from sim.agent.will import synthesize_verdict

    npc_runtime.willingness_of = synthesize_verdict
    # 批次 D15 补线①：权力供数——core.persistence.power_store.PowerStore 物化 →
    # runtime.power（效用面权力列偏置开闸；空表 = 不赋 = 逐位同旧，
    # 见 assemble.attach_power 契约）。
    from sim.core.persistence.power_store import PowerStore
    from sim.npc.assemble import attach_power

    attach_power(
        npc_runtime,
        await PowerStore(store).materialize(None),
    )
    pathfinder = Pathfinder(tile_map)
    app.state.pathfinder = pathfinder
    loop.pathfinder = pathfinder
    loop.fauna_enabled = True
    app.state.npc_runtime = npc_runtime
    monologue_last: dict[str, int] = {}
    monologue_quota: dict[int, int] = {}  # D10：每节拍出镇配额账本（撞拍保险丝）
    # 批次 E2/E1：聊天账本（关系漂移+记忆环形缓冲）+ 聊天冷却账本——
    # 调用方持有（跨拍记忆态，同 monologue_last 口径；不进重放面）。
    from sim.npc.chat_ledger import ChatLedger

    chat_ledger = ChatLedger()
    app.state.chat_ledger = chat_ledger
    chat_last: dict[str, int] = {}
    retell_last: dict[str, int] = {}  # 批次 E2：学舌冷却账本（调用方持有）
    # 批次 E3：全镇余额账本（村民工钱 + 陈默买卖共享一份账）。
    from sim.world.economy import CoinLedger

    coin_ledger = CoinLedger()
    app.state.coin_ledger = coin_ledger
    from sim.npc.errand_runtime import ErrandRuntime

    errands = ErrandRuntime(seed=loop.state.world_seed, coin_ledger=coin_ledger)
    app.state.errands = errands
    from sim.npc.demography import Demography

    demography = Demography(seed=loop.state.world_seed)
    app.state.demography = demography
    loop.attach_npc_runtime(lambda state, tick: demography.tick(tick))
    wage_last: dict[str, int] = {}
    # 批次 E4：施工 runtime（事件为真相；每 tick 推进 checkpoint/完工）。
    from sim.agent.build_exec import BuildRuntime

    build_runtime = BuildRuntime(tile_map, seed=loop.state.world_seed)
    # P-2：重启后在建工地不丢——从当前分支事件流恢复（`_site` 是纯内存态）。
    _start_branch = await store.current_branch_id_or_none()
    if _start_branch is not None:
        build_runtime.restore_from_events(
            await NpcStore(store, branch_id=_start_branch).read_branch_history()
        )
    app.state.build_runtime = build_runtime

    # 结构瓦片以 maintenance 的事件折叠为准，on_flush 完工后投影 built。
    from sim.world.maintenance import WorldMaintenance

    matter_ledger = await npc_store.materialize_matter()
    structure_snapshots = await npc_store.materialize_structures()
    maintenance = WorldMaintenance(ledger=matter_ledger, structures=structure_snapshots)

    def _build_tick_hook(state: Any, tick: int) -> list[Any] | None:
        nonlocal tile_map
        events = build_runtime.on_tick(tick)
        if events:
            # TILE_CHANGED → 寻路缓存失效（§14 chunk 失效；图换新实例后
            # pathfinder 需感知——observe_map 对齐新几何）。
            tile_map = build_runtime.tile_map
            app.state.tile_map = tile_map
            pathfinder.observe_map(tile_map)
        return events or None

    loop.attach_npc_runtime(_build_tick_hook)

    def _maintenance_tick_hook(state: Any, tick: int) -> list[Any] | None:
        return maintenance.tick(tick=tick, seed=state.world_seed) or None

    loop.attach_maintenance(_maintenance_tick_hook)

    def _npc_tick_hook(state: Any, tick: int) -> list[Any] | None:
        chenmo = state.entities.get(CHENMO_ID)
        if chenmo is not None:
            for npc_id, _profile in npc_runtime.profiles.items():
                if _profile.species != "human":
                    continue
                entity = state.entities.get(npc_id)
                nearby = (
                    entity is not None
                    and abs(entity.pos[0] - chenmo.pos[0]) + abs(entity.pos[1] - chenmo.pos[1]) <= 3
                )
                npc_runtime.update_lod(npc_id, in_interaction=nearby, tick=tick)
        batch = npc_events_for_tick(
            npc_runtime,
            state,
            tick,
            pathfinder,
            seed=loop.state.world_seed,
            monologue_last=monologue_last,
            monologue_quota=monologue_quota,
            chat_last=chat_last,
            display_name_of=_display_names,
            chat_ledger=chat_ledger,
            retell_last=retell_last,  # 批次 E2：学舌通路（review C3 修复）
            wage_last=wage_last,
            coin_ledger=coin_ledger,
            build_runtime=build_runtime,
        )
        # 批次 D14：npc.act → 动作姿势账本（快照/delta 的 anim 字段供数）。
        from sim.api.ws import set_action_anim
        from sim.npc.sim_exec import anim_of_action

        for event in batch or []:
            if (
                getattr(event, "event_type", None) is not None
                and getattr(event.event_type, "value", "") == "npc.act"
            ):
                npc_id = str(event.payload.get("npc_id", ""))
                if npc_id:
                    set_action_anim(npc_id, anim_of_action(str(event.payload.get("action", ""))))
        return batch or None

    role_last: dict[str, int] = {}

    def _role_tick(state: Any, tick: int) -> list[Any]:
        events: list[Any] = []
        for npc_id in ROLES:
            if npc_id not in state.entities or tick - role_last.get(npc_id, -600) < 600:
                continue
            frame = loop.perception_frames.get(rtoken_of(npc_id))
            if isinstance(frame, PerceptionFrame):
                batch = role_events(npc_id, frame, tick)
                if batch:
                    role_last[npc_id] = tick
                    for event in batch:
                        memory_pipeline.write(
                            npc_id,
                            str(event.payload["content"]),
                            source="reason",
                            event_seq=None,
                            importance=0.7,
                            emotion_tag=None,
                        )
                    events.extend(batch)
        return events

    loop.attach_npc_runtime(_role_tick)
    loop.attach_npc_runtime(_npc_tick_hook)
    loop.attach_npc_runtime(lambda state, tick: animal_events(state, build_runtime.tile_map, tick))
    loop.attach_npc_runtime(lambda state, tick: errands.tick(state, tick) or None)

    # ── 批次 D5：火灾实况（凌晨确定性起火 → 蔓延 → 死亡代价）──────────
    from sim.npc.fire_runtime import FireRuntime, ignite_due

    fire_runtime = FireRuntime()
    app.state.fire_runtime = fire_runtime

    # DA-03 补：两本账都是纯内存态，构造点在此（不在 build_loop）——冷启动必须
    # 按**当前分支谱系**重放，否则进程重启后余额归零、`fire_seq` 归零会让下一场
    # 火重发 `fire-1` 撞库里既有主键（`FireWriteError` 打死驱动）。
    if current_branch is not None:
        _cold_events = await NpcStore(store, branch_id=current_branch).read_branch_history()
        coin_ledger.restore_from_events(_cold_events)
        fire_runtime.restore_from_events(_cold_events)

    def _fire_tick_hook(state: Any, tick: int) -> list[Any] | None:
        events: list[Any] = []
        if ignite_due(loop.state.world_seed, tick):
            # 确定性落点：药铺前空地东南的草地（seed+tick 哈希散布可走格）
            import zlib

            h = zlib.crc32(f"fire-spot:{loop.state.world_seed}:{tick}".encode())
            gx, gy = h % tile_map.width, (h // tile_map.width) % tile_map.height
            if tile_map.is_walkable(gx, gy):
                events.extend(fire_runtime.ignite_at(tick=tick, x=gx, y=gy))
        if fire_runtime.cells:
            walkable = {
                (x, y)
                for x in range(tile_map.width)
                for y in range(tile_map.height)
                if tile_map.is_walkable(x, y)
            }
            events.extend(fire_runtime.step(tick=tick, walkable=walkable))
            burning = {(c.x, c.y) for c in fire_runtime.cells}
            events.extend(fire_runtime.collect_deaths(state, burning=burning))
        return events or None

    loop.attach_npc_runtime(_fire_tick_hook)

    # ── 批次 C：陈默 L2 决策驱动（LLM 接进决策循环）─────────────────
    # 播种主角档案 → 组 ChenmoDriver → impulse 钩子 + 节拍任务随 lifespan。
    # LLM 调用全异步、失败降级（driver 内）；世界照常运转不因 LLM 阻塞。
    from sim.agent.driver import ChenmoDriver
    from sim.api.ws import set_impulse_trigger
    from sim.content.protagonist import seed_protagonist
    from sim.llm.client import LlmClient

    chenmo_seeded = await seed_protagonist(store.session_factory)
    if chenmo_seeded:
        logger.info("protagonist.seeded", npc_id="chenmo")
    llm_client = LlmClient()

    # 批次 D6：感知帧 → 叙事文本投影（chenmo 的 prompt [处境] 段供数）。
    # run_perception_step 每 tick 为全员装帧（键=rtoken）；取不到/空感知 →
    # 空文本（[处境] 段省略）。感知帧是 tick 内瞬时快照——直接读最新帧即可。
    from sim.agent.language import LanguageProfile
    from sim.content.protagonist import _profile_row as _chenmo_profile_row
    from sim.perception.frame import PerceptionFrame
    from sim.perception.senses import rtoken_of

    language = LanguageProfile.from_json(str(_chenmo_profile_row()["knowledge_boundary"]))
    chenmo_rtoken = rtoken_of("chenmo")

    def _chenmo_perception() -> str:
        frame = loop.perception_frames.get(chenmo_rtoken)
        if frame is None:
            return ""
        assert isinstance(frame, PerceptionFrame)
        return frame.narrated(language=language)

    # 批次 D15 补线②：陈默记忆切片——感知叙述经 write() 闸门入记忆
    # （observe），决策前检索 top-k 进 prompt（recall → memory_entries）；
    # 补线③日切反思共用本 pipeline。进程内记忆（M4 口径，见 agent.chenmo_memory）。
    from sim.agent.chenmo_memory import observe as _mem_observe
    from sim.agent.chenmo_memory import recall as _mem_recall
    from sim.content.protagonist import CHENMO_ID
    from sim.llm.memory_scan import MemoryWritePipeline

    memory_pipeline = MemoryWritePipeline(store=memory_store)

    def _writeback_downgrade(npc_id: str) -> None:
        memories = chat_ledger.memories_of(npc_id)
        if not memories:
            return
        memory_pipeline.write(
            npc_id=npc_id,
            content=memories[-1][1],
            source="reason",
            event_seq=None,
            importance=0.5,
            emotion_tag=None,
        )

    npc_runtime.on_downgrade = _writeback_downgrade
    _ = CHENMO_ID  # 反思 npc_ids 用（见补线③）
    # 批次 E6：战斗账本（hp 进程内；死亡走 npc.death 事件——C4 零新增 kind）。
    from sim.agent.combat_exec import CombatLedger
    from sim.core.entropy import EntropyMixer

    combat_ledger = CombatLedger()
    app.state.combat_ledger = combat_ledger
    entropy_mixer = EntropyMixer(rng=RngRegistry(world_seed=loop.state.world_seed))

    def _combat_entropy(stream: str, tick: int):
        nonlocal entropy_mixer
        entropy_mixer, event = entropy_mixer.mix(stream, tick=tick)
        return event

    loop.attach_entropy(_combat_entropy)
    from sim.npc.speech_register import SpeechContext

    driver = ChenmoDriver(
        anchor=build_anchor(),
        llm=llm_client,
        profile_provider=_active_profile_snapshot_provider(),
        perception_provider=_chenmo_perception,
        display_name_of=_display_names.get,  # 批次 E1：talk_to 台词用戏内名
        economy_provider=lambda: (coin_ledger, loop.state.world_seed),  # 批次 E3
        build_runtime_provider=lambda: build_runtime,  # 批次 E4
        combat_provider=lambda: (combat_ledger, loop.state.world_seed),  # 批次 E6
        entropy_provider=_combat_entropy,
        speech_context_provider=lambda target: SpeechContext(
            language.class_register,
            in_circle=target is None or target in chat_ledger.relations_of(CHENMO_ID),
        ),
    )
    app.state.chenmo_driver = driver
    loop.attach_maintenance(lambda state, tick: driver.combat_tick(loop, pathfinder=pathfinder))
    set_impulse_trigger(driver.request_decision)

    world_revision = 0

    async def _chenmo_loop() -> None:
        """决策循环：impulse 置位或节拍到期 → 决策 + 同拍执行（与世界 driver 平行）。

        执行在决策之后（pending 刚入队即执行，revalidate 用当前世界态）；
        事件随世界帧落库/广播。
        """
        import os
        import time as _time

        try:
            interval = float(os.environ.get("CHENMO_DECIDE_SECONDS", "60"))
        except ValueError:
            interval = 60.0
        interval = max(5.0, interval)  # 下限护栏：防误配 0 烧钱
        last = _time.monotonic()
        while True:
            await asyncio.sleep(0.5)
            if not getattr(app.state, "world_source_ready", True):
                continue
            now = _time.monotonic()
            due = (now - last) >= interval
            if not driver.take_requested() and not due:
                continue
            last = now
            # D15：先记后忆——感知叙述过闸门入记忆，检索 top-k 进决策 prompt
            # （感知文本同轮复用，不二次投影）。
            _perception_text = _chenmo_perception()
            if _perception_text:
                _mem_observe(memory_pipeline, _perception_text, tick=loop.state.tick)
            # 批次 E2：[记忆] 段双源——检索 top-k 为主，当日对话记忆（ledger
            # 最新 3 条）排前（最新鲜的社交事实优先）。
            from sim.agent.chenmo_memory import merge_ledger_entries

            _ledger_texts = tuple(text for _, text in chat_ledger.memories_of(CHENMO_ID)[-3:])
            # 2026-10-12「只心声不动」修复：[处境] 附可去地标表——模型此前
            # 不知道任何坐标（[计划] 恒空、target_pos 无从填起），输出收敛
            # wait/短移=行动面空转。地标=戏内地点名+坐标（戏内事实可出站）。
            _landmarks = (
                "你知道这些去处：药铺（100,53，你的铺子）、染坊市集（72,52）、"
                "桃门（15,18）、溪桥（66,19）、梯田（122,19）、客栈院（44,53）。"
                "想去哪就 move_to 它的坐标。"
            )
            decision_revision = world_revision
            await driver.decide_once(
                loop.state,
                loop.state.tick,
                memory_entries=merge_ledger_entries(
                    _mem_recall(
                        memory_pipeline,
                        now_tick=loop.state.tick,
                        params=cognition.params_at(loop.state.tick),
                    ),
                    _ledger_texts,
                    top_k=3,
                ),
                perception_text=_perception_text,
                landmarks_text=_landmarks,
            )
            async with world_write_lock:
                if decision_revision != world_revision:
                    driver.reset_combat()
                    continue
                driver.execute_pending(loop, pathfinder=pathfinder)

    app.state.chenmo_task = asyncio.create_task(_chenmo_loop())

    # 批次 A 接线（M6 补施工）：rng 状态捕获缝——锚点存档时 capture_rng_state 的
    # 真实实现（registry 由 world_seed 纯函数重建 + 抽签 cache 在 TickContext）。
    # anchors.py 的 `_rng_state_or_none` 经 `app.state.rng_capture` 零改动接上。
    from sim.core.rng_state import capture_rng_state

    def _capture_rng() -> str:
        from sim.world.weather import WEATHER_STREAM

        registry = RngRegistry(world_seed=loop.state.world_seed)
        return capture_rng_state(registry, loop.context.rng_cache, (WEATHER_STREAM,))

    app.state.rng_capture = _capture_rng

    from sim.core.persistence.fork_orchestration import set_materialization_hooks
    from sim.core.persistence.world_restore import materialization_hooks

    set_materialization_hooks(materialization_hooks())

    # 生产读档 hook（裁 28-G driver 生产挂载；R-1 修复后形态，M5-K7 R-1 CRITICAL）：
    # load_anchor 分发块是**同步契约**，而 fork 事务必须跑在事件循环里——
    # 同 loop 内忙等会让 task 永不推进（kilo 实证：挂死且 except 救不了）。
    # 修法 = kilo 建议②「批处理范式」（与 fast_forward 同构，零新增消息类型）：
    # handler 侧 hook 只做**请求登记**并立即受理；真正分叉由 driver 循环在
    # flush 后的 await 窗口执行；完成/失败由后续单接完成通道定向回帧。
    pending_loads: deque[tuple[str, str]] = deque()  # (request_id, anchor_id)

    def _production_load_hook(anchor_id: str) -> None:
        """登记读档请求（同步、不阻塞）；真执行在 driver 的 _drain_loads。"""
        request_id = uuid.uuid4().hex[:12]
        pending_loads.append((request_id, anchor_id))
        # None = 已登记、尚未完成；同步 True 路径只用于已完成的兼容 hook。

    async def _drain_loads() -> bool:
        nonlocal demography, tile_map, world_revision
        """driver 每帧调用：执行 pending fork（事件循环内，可 await）。

        失败帧（案 B 最小形，K16 审计稿 §3.2）：失败走既有 `_error_frame` +
        `_ERROR_LOAD_FAILED`（不扩 11 项词表）；**玩家可见文本是字面量**（戏内
        口语零工程词——K16 白盒钉锁死）；`reason` 只进日志字段。
        """
        from sim.api import ws as _ws_mod
        from sim.core.persistence.fork_orchestration import (
            locate_anchor,
            orchestrate_materialized_load_anchor,
        )

        changed = False
        while pending_loads:
            _request_id, anchor_id = pending_loads.popleft()
            activated = False
            try:
                location = await locate_anchor(store.session_factory, anchor_id)
                _, materialized = await orchestrate_materialized_load_anchor(
                    store.session_factory,
                    anchor_id=anchor_id,
                    flush_in_flight=on_flush_async,
                    register_child=register_new_branch,
                    hooks=materialization_hooks(target_tick=location.tick),
                    make_current=True,
                )
                restored: TickLoop = materialized.world
                loop.state = restored.state
                loop.context = restored.context
                loop.chaos = restored.chaos
                loop.clock.restore_tick(restored.state.tick)
                if restored.context.combat_active:
                    loop.enter_combat()
                else:
                    loop.exit_combat()
                loop.pending_events.clear()
                loop.pending_delta_entity_ids.clear()
                loop.pending_broadcast_events.clear()
                loop.pending_combat_visuals.clear()
                loop.perception_frames = {}
                world_revision += 1
                for control in manager.controls():
                    control.cancel_fast_forward()
                changed = True
                activated = True
                # 批次 E（review I2 修复）：读档=分叉 → 进程内 runtime 账本全部
                # 清零——旧分支的 hp/余额/关系/冷却跨分支残留会造成「一刀秒杀」
                # /「凭空余财」（账本是**本分支**的世界状态投影，分叉即失效）。
                # P-4 更正：火场账本**并不**由 fork 编排层处理（fork_orchestration
                # 不引用 fire）——此前注释所述有误，旧火确实会跨分支继续烧。
                demography = Demography(seed=loop.state.world_seed)
                app.state.demography = demography
                errands.reset()
                cognition.reset()
                role_last.clear()
                driver.reset_combat()
                combat_ledger.reset()
                coin_ledger.reset()
                chat_ledger.reset()
                fire_runtime.reset()  # P-4
                build_runtime.reset()  # P-2
                monologue_last.clear()
                monologue_quota.clear()
                chat_last.clear()
                retell_last.clear()
                wage_last.clear()
                from sim.core.persistence.npc_store import NpcStore

                branch_id = await store.current_branch_id_or_none()
                if branch_id is None:
                    raise RuntimeError("fork completed without an active branch")
                branch_store = NpcStore(store, branch_id=branch_id)
                branch_events = await branch_store.read_branch_history()
                coin_ledger.restore_from_events(branch_events)
                fire_runtime.restore_from_events(branch_events)
                maintenance.ledger = await branch_store.materialize_matter()
                maintenance.structures = await branch_store.materialize_structures()
                tile_map = await rebuild_tile_map(branch_store)
                app.state.tile_map = tile_map
                build_runtime.tile_map = tile_map
                # P-2：工地账本纯内存，清零后须从**本分支**事件流恢复在建工地
                # （不清零则旧工地跨分支推进并发出旧 structure_id 的事件）。
                build_runtime.restore_from_events(branch_events)
                pathfinder.observe_map(tile_map)
                pathfinder.cache.entries.clear()
                maintenance._cascades.clear()
                maintenance._collapsed.clear()
                memory_store.attach_branch(await store.current_branch_id_or_none())
                logger.info("fork.runtime_ledgers_reset", anchor_id=anchor_id)
                logger.info("fork.load_completed", anchor_id=anchor_id)
                app.state.world_source_ready = True
                load_outcomes.append((anchor_id, True))
                pointer = _ws_mod.anchor_pointer(anchor_id)
                await manager.broadcast_json(
                    session_state_payload(
                        speed=int(loop.clock.speed) or 1,
                        paused=loop.clock.speed == 0,
                        anchor=pointer,
                        notice=_ws_mod.fork_notice(pointer.get("name", "") if pointer else ""),
                        tick=loop.state.tick,
                    )
                )
                await manager.broadcast_json(_ws_mod.timescale_payload(loop.context.combat_active))
                await manager.broadcast_json(snapshot_payload(loop, tile_map))
            except Exception as exc:
                if activated:
                    app.state.world_source_ready = False
                    loop.clock.set_speed(0)
                logger.warning(
                    "fork.load_failed",
                    anchor_id=anchor_id,
                    reason=str(exc),
                )
                load_outcomes.append((anchor_id, False))
                # 案 B 失败帧：给**当前所有连接**发既有 error 帧（玩家可见）。
                # 文本字面量（K16 白盒钉：非字面量/工程词都红）。无连接时广播是
                # no-op（不因「没人在线」而失败——账本已落，帧是尽力投递）。
                await manager.broadcast_json(
                    _ws_mod._error_frame("load_anchor", "load_failed", "这个档读不出来了。")
                )
        return changed

    def register_new_branch(_new_branch_id: str) -> None:
        """子分支可载性登记（观察日志；两套注册表勿混，K4 §3.4）。"""
        logger.debug("fork.child_branch_registered", branch_id=_new_branch_id)

    # drain 结果账本（R-1 修复的可观测面；test_m5_anchors_crud 消费断言）。
    load_outcomes: list[tuple[str, bool]] = []

    # 同步 hook 出口（ws.py 分发块契约）+ driver 每帧 drain 注册
    from sim.api import ws as _ws_mod

    _ws_mod.set_anchor_load_hook(_production_load_hook)
    app.state.drain_pending_loads = _drain_loads
    app.state.load_outcomes = load_outcomes
    # driver 在 _drain_loads 定义之后创建（case B 接线：drain_loads 生产调用点）
    # 批次 D15 补线③：日切反思挂载——世界循环日切钩子把当日 event 素材
    # 压成 reason 摘要（write() 闸门照扫；无素材零产物是常态路径）。
    from sim.npc.reflection import make_day_switch_reflector

    _day_reflector = make_day_switch_reflector(
        memory_pipeline,
        npc_ids=(CHENMO_ID, *VILLAGER_IDS),
    )
    # 只允许空库开线；已有分支但无当前行时保持故障态，禁止后台猜 main 修复真源。
    from sqlalchemy import select

    from sim.core.persistence.models import Branch

    source_ready = await store.current_branch_id_or_none() is not None
    if not source_ready:
        async with store.session_factory() as session:
            source_ready = await session.scalar(select(Branch.id).limit(1)) is None
    app.state.world_source_ready = source_ready
    app.state.driver = asyncio.create_task(
        run_world_driver(
            loop,
            manager,
            tile_map,
            on_flush,
            on_day_switch=_day_reflector,
            drain_loads=_drain_loads,
            write_lock=world_write_lock,
        )
        if source_ready
        else asyncio.Event().wait()
    )
    try:
        yield
    finally:
        app.state.flush_for_anchor = None
        app.state.pathfinder = None
        delattr(app.state, "world_source_ready")
        tasks = (app.state.chenmo_task, app.state.driver)
        for task in tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        await store.session_factory.kw["bind"].dispose()
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                raise result


app = FastAPI(title="临河镇 sim", version="1.11", lifespan=lifespan)
app.include_router(settings_router)
app.include_router(anchors_router)  # M5-K7：玩家档读路径（落库 → WS 查表集供数）

from sim.api.openapi_ext import install as _install_openapi_ext  # noqa: E402

_install_openapi_ext()  # WS components 进 OpenAPI（kilo K03 差异回写）
install_error_handlers(app)  # ProblemDetail 全局错误形（anchors-api §3.2，S-1）


class HealthStatus(BaseModel):
    """戏外探针响应（K3 §2.1 #15）。

    status 单值枚举用 Field(json_schema_extra)（pydantic Literal 会产 const 形，
    与快照 enum 形不符）。装饰 title 由 custom_openapi 后处理统一剥除。
    注意：勿加 model 级 json_schema_extra 的 properties——会整体替换字段 extras
    （吞 enum）。docstring 不进 schema：json_schema_extra={"description": ""}
    占位 + 后处理剥空串（快照 HealthStatus 无 description 键）。
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"description": ""})

    status: str = Field(json_schema_extra={"enum": ["ok"]})
    world_running: bool
    in_combat: bool = Field(description="戏外只读，不回流戏内")


class MapChunk(BaseModel):
    """碰撞+地面层 chunk（只读静态资产）。

    M7（1.3）增 `ground_b64` = base64(u16 小端、chunk 内行主序)——与
    `map_static_payload` / 前端 `decodeGroundB64` 三方同一定义。
    """

    model_config = ConfigDict(extra="forbid")

    cx: int = Field(ge=0)
    cy: int = Field(ge=0)
    collision_b64: str = Field(
        description="base64 编码的可通行位（1=可通行），不含 seed/tick/entity_id"
    )
    ground_b64: str = Field(
        description="base64 编码的地面 tile id（u16 小端、行主序；"
        "调色板值域见前端 sprout-palette.json）"
    )


class WorldMapResponse(BaseModel):
    """/api/world/map 响应：碰撞层静态资产（戏外 meta shell，对齐 sim map_static_payload）"""

    model_config = ConfigDict(extra="forbid")

    w: int = Field(ge=0)
    h: int = Field(ge=0)
    tileset: str
    chunks: list[MapChunk]


@app.get("/api/health", response_model=HealthStatus)
async def health() -> HealthStatus:
    loop: TickLoop = app.state.loop
    return HealthStatus(
        status="ok",
        world_running=getattr(app.state, "world_source_ready", True),
        in_combat=loop.context.combat_active,
    )


@app.get("/api/world/map", response_model=WorldMapResponse)
async def world_map() -> WorldMapResponse:
    """碰撞层静态资产（codex 意见 5：走 HTTP 不走 WS；kilo chunk 提案已批）。"""
    raw = map_static_payload(app.state.tile_map)
    return WorldMapResponse(
        w=raw["w"],
        h=raw["h"],
        tileset=raw["tileset"],
        chunks=[MapChunk(**c) for c in raw["chunks"]],
    )


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    # W6 握手层：Origin 白名单（防恶意网页 localhost CSRF / DNS rebinding）。
    # token 校验在 hello 消息层（见 handle_client_message）。
    if not check_origin(ws.headers.get("origin")):
        await ws.close(code=4003)  # 4003 = origin rejected（自定义码段 4000+）
        return
    await ws.accept()
    # K8：玩家连接=主角本人视角（thought 面板定向投递给它；其余连接=旁观者，
    # 只收 bubble/plan）。身份由服务端定（不采客户端自报，防越权读他人面板）。
    from sim.api.ws import subscriber_for_protagonist

    manager.register(ws, subscriber_id=subscriber_for_protagonist(app.state.loop))
    pf = _pathfinder()
    # M5-K3 / 裁 21-A D-3：会话态**连接级**——由 ConnectionManager 每连接一份
    control = manager.control_of(ws)
    authed = False
    try:
        # 接入即发全量快照（kilo ws-protocol：sync 的答案）。
        # M6-K5 裁 41-4：出站**一律走咽喉**（`manager.send_json_to`）——直发
        # `ws.send_json` 会绕过 K11/K15 两层禁键剥除+留痕（旁路=闸门失效）。
        await manager.send_json_to(ws, snapshot_payload(app.state.loop, app.state.tile_map))
        # M5-K3 / D-5+D-6：连接期初值一帧（刻度/暂停态/游标指针 + notice=null）。
        # 重连后前端据此恢复「世界此刻的样子」，不必靠推断。
        await manager.send_json_to(
            ws,
            session_state_payload(
                speed=control.effective_speed(),
                paused=control.paused,
                anchor=_current_anchor_pointer(),
                tick=app.state.loop.state.tick,  # M7-R3：连接即同步时钟
            ),
        )
        while True:
            raw = await ws.receive_json()
            if not isinstance(raw, dict):
                raw = {}
            msg_type = raw.get("type")
            if not isinstance(msg_type, str):
                msg_type = "unknown"
                raw = {**raw, "type": msg_type}
            if not authed and msg_type not in {"hello", "sync_request"}:
                reply = _error_frame(
                    msg_type if isinstance(msg_type, str) else "unknown",
                    "auth_error",
                    "authentication required",
                )
            elif msg_type in {"move_request", "set_control", "player_impulse"}:
                async with app.state.world_write_lock:
                    if not getattr(app.state, "world_source_ready", True):
                        reply = _error_frame(msg_type, "bad_action", "此刻动不了。")
                    else:
                        reply = handle_client_message(raw, app.state.loop, pf, control)
            else:
                reply = handle_client_message(raw, app.state.loop, pf, control)
            if msg_type == "hello":
                authed = any(frame.get("type") == "hello_ack" for frame in frames_of(reply))
            # M5-K3：读档成功回两帧（分叉告知 + 全量），其余仍单帧/无帧
            for frame in frames_of(reply):
                await manager.send_json_to(ws, frame)
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(ws)


class WsTokenResponse(BaseModel):
    """本机 WS 握手凭据；只经 HTTP 返回，不写入世界或持久化。"""

    model_config = ConfigDict(extra="forbid")
    token: str


@app.get("/api/ws-token", response_model=WsTokenResponse)
async def websocket_token(request: Request, response: Response) -> WsTokenResponse:
    origin = request.headers.get("origin")
    try:
        local_peer = (
            request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
        )
    except ValueError:
        local_peer = False
    if (
        not local_peer
        or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}
        or not origin
        or origin == "null"
        or not check_origin(origin)
    ):
        raise HTTPException(status_code=403, detail="Forbidden")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Origin"] = origin
    return WsTokenResponse(token=ws_auth_token())


def _current_anchor_pointer() -> dict[str, str] | None:
    """当前游标指针（D-9 同源数据面：HTTP 只读面 `/api/anchors/current` 的同一行）。

    只取 `name` + `story_label`（零原始数值）。取不到（空库/落库未就绪）回 None
    ——首帧不能因读档数据面故障而失败，故 fail-soft。
    """
    from sim.api.anchors import get_anchor_store

    try:
        item = get_anchor_store().current_item()
    except Exception:
        # 读档数据面故障不得拖垮 WS 连接（首帧是「尽力而为」的初值）
        return None
    if item is None:
        return None
    return {"name": item.name, "story_label": item.story_label}


def _pathfinder():
    from sim.world.pathfinding import Pathfinder

    active = getattr(app.state, "pathfinder", None)
    if active is not None:
        return active
    return Pathfinder(app.state.tile_map)
