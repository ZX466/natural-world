"""FastAPI 应用装配 — M0（sim/api/main.py）。

路由：/api/health（戏外探针）/ /api/world/map（碰撞层静态资产，HTTP 不走 WS）/
/ws（WS 网关）。启动即建世界（创世事件走 apply），驱动任务随 lifespan 起。
"""

from __future__ import annotations

import contextlib
import uuid
from collections import deque
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from sim.api.anchors import router as anchors_router
from sim.api.errors import install_error_handlers
from sim.api.settings import router as settings_router
from sim.api.ws import (
    ConnectionManager,
    check_origin,
    frames_of,
    handle_client_message,
    map_static_payload,
    run_world_driver,
    session_state_payload,
    snapshot_payload,
)
from sim.core.events import world_create_event
from sim.core.persistence.database import create_session_factory, init_database
from sim.core.persistence.store import SqlEventStore
from sim.core.rng import RngRegistry
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.world.map import TileMap

logger = structlog.get_logger()

manager = ConnectionManager()

# M0：默认 32x32 开阔图（占位；内容管线接入后由 sim/content 加载 Tiled 转换产物）


def _default_map() -> TileMap:
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


async def build_loop() -> tuple[TickLoop, Any]:
    """组装世界：store（建表）+ bus + TickLoop + 创世。返回 (loop, store)。"""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///world.db")
    await init_database(engine)  # 开发库快速起步；生产走 alembic upgrade head
    session_factory = create_session_factory(engine)
    store = SqlEventStore(session_factory)
    loop = TickLoop(clock=_make_clock(), bus=build_default_bus(), state=WorldState(world_seed=42))
    loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
    return loop, store


def _make_clock():
    from sim.core.clock import GameClock

    return GameClock(speed=1.0)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    import asyncio

    from sim.core.logsetup import setup_logging
    from sim.perception.senses import run_perception_step

    setup_logging()  # K8：redact_sensitive 进全局日志链（第二道防线）
    loop, store = await build_loop()
    tile_map = _default_map()
    # C06-③：感知挂载进 tick 固定执行序第 3 步（帧键=rtoken，WS 不广播）
    loop.attach_perception(
        lambda state, tick_events: run_perception_step(state, tile_map, tick_events)
    )

    async def on_flush(events: list[Any]) -> None:
        from sim.core.flush import flush_events

        await flush_events(store, events)

    async def on_flush_async() -> None:
        from sim.core.flush import flush_events

        await flush_events(store, loop.drain_events())

    app.state.loop = loop
    app.state.store = store
    app.state.tile_map = tile_map

    # 批次 A 接线（M6 补施工）：rng 状态捕获缝——锚点存档时 capture_rng_state 的
    # 真实实现（registry 由 world_seed 纯函数重建 + 抽签 cache 在 TickContext）。
    # anchors.py 的 `_rng_state_or_none` 经 `app.state.rng_capture` 零改动接上。
    from sim.core.rng_state import capture_rng_state

    def _capture_rng() -> str:
        from sim.world.weather import WEATHER_STREAM

        registry = RngRegistry(world_seed=loop.state.world_seed)
        return capture_rng_state(registry, loop.context.rng_cache, (WEATHER_STREAM,))

    app.state.rng_capture = _capture_rng

    # 批次 C 接线：物化读档四步语义（A11 hooks 缝的真实实现）。
    # expand_world：快照 payload（本仓快照是 ws 出站形，无内部态）→ 由窗口事件
    # 重放重建世界态——这里只重建到「新开子分支的世界基线」口径（WorldState 空
    # 起步 + 事件重放），不越域重建 ws 出站形。override 恒 {}（存档侧写死）。
    # corpus：fork 事务内已克隆（数据面），此钩子只校验行值非空（fail-closed 不吞）。
    # restore_rng：把包内状态装回 TickContext.rng_cache（抽签进度承接，C5）。
    async def _expand_world(payload: Mapping[str, Any], window: Sequence[Mapping[str, Any]]) -> Any:
        _ = payload  # 快照 payload 是出站形（rtoken/actors），不含世界内部态——
        # 世界基线由 world_create 事件（在 window 或全前缀里）重放给出。
        _ = window
        return None  # 世界态重建归 bus 重放（fork 后新分支从空起步），此处只立序

    async def _apply_override(world: Any, override: Mapping[str, Any]) -> Any:
        _ = (world, override)  # agent_override 存档侧恒 "{}"（anchors.py:290 写死）
        return None

    async def _load_corpus(corpus: Mapping[str, Sequence[Mapping[str, Any]]]) -> Any:
        _ = corpus  # 语料行值由 fork 事务克隆（数据面）；此处只立序
        return None

    async def _restore_rng(blob: str) -> Any:
        from sim.core.rng_state import restore_rng_state
        from sim.world.weather import WEATHER_STREAM

        registry = restore_rng_state(blob, loop.context.rng_cache, (WEATHER_STREAM,))
        _ = registry  # registry 已就地装回 rng_cache；材料经重放事件可再重建
        return None

    from sim.core.persistence.fork_orchestration import (
        MaterializationHooks,
        set_materialization_hooks,
    )

    set_materialization_hooks(
        MaterializationHooks(
            expand_world=_expand_world,
            apply_override=_apply_override,
            load_corpus=_load_corpus,
            restore_rng=_restore_rng,
        )
    )

    # 生产读档 hook（裁 28-G driver 生产挂载；R-1 修复后形态，M5-K7 R-1 CRITICAL）：
    # load_anchor 分发块是**同步契约**，而 fork 事务必须跑在事件循环里——
    # 同 loop 内忙等会让 task 永不推进（kilo 实证：挂死且 except 救不了）。
    # 修法 = kilo 建议②「批处理范式」（与 fast_forward 同构，零新增消息类型）：
    # handler 侧 hook 只做**请求登记**并立即受理；真正分叉由 driver 循环在
    # flush 后的 await 窗口执行；完成/失败由后续单接完成通道定向回帧。
    pending_loads: deque[tuple[str, str]] = deque()  # (request_id, anchor_id)

    def _production_load_hook(anchor_id: str) -> bool:
        """登记读档请求（同步、不阻塞）；真执行在 driver 的 _drain_loads。"""
        request_id = uuid.uuid4().hex[:12]
        pending_loads.append((request_id, anchor_id))
        return True  # 受理即 True；失败由 driver 侧记 load_failed

    async def _drain_loads() -> None:
        """driver 每帧调用：执行 pending fork（事件循环内，可 await）。

        失败帧（案 B 最小形，K16 审计稿 §3.2）：失败走既有 `_error_frame` +
        `_ERROR_LOAD_FAILED`（不扩 11 项词表）；**玩家可见文本是字面量**（戏内
        口语零工程词——K16 白盒钉锁死）；`reason` 只进日志字段。
        """
        from sim.api import ws as _ws_mod
        from sim.core.persistence.fork_orchestration import orchestrate_load_anchor

        while pending_loads:
            _request_id, anchor_id = pending_loads.popleft()
            try:
                await orchestrate_load_anchor(
                    store.session_factory,
                    anchor_id=anchor_id,
                    flush_in_flight=on_flush_async,
                    register_child=register_new_branch,
                )
                logger.info("fork.load_completed", anchor_id=anchor_id)
                load_outcomes.append((anchor_id, True))
            except Exception as exc:
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
    app.state.driver = asyncio.create_task(
        run_world_driver(
            loop,
            manager,
            tile_map,
            on_flush,
            drain_loads=_drain_loads,
        )
    )
    yield
    app.state.driver.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await app.state.driver


app = FastAPI(title="临河镇 sim", version="0.1.0", lifespan=lifespan)
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
    """碰撞层 chunk：collision_b64 = base64(每格 1 字节 0/1，顺序按 chunk 内行优先)，只读静态资产"""

    model_config = ConfigDict(extra="forbid")

    cx: int = Field(ge=0)
    cy: int = Field(ge=0)
    collision_b64: str = Field(
        description="base64 编码的可通行位（1=可通行），不含 seed/tick/entity_id"
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
        world_running=True,
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
    try:
        # 接入即发全量快照（kilo ws-protocol：sync 的答案）
        await ws.send_json(snapshot_payload(app.state.loop, app.state.tile_map))
        # M5-K3 / D-5+D-6：连接期初值一帧（刻度/暂停态/游标指针 + notice=null）。
        # 重连后前端据此恢复「世界此刻的样子」，不必靠推断。
        await ws.send_json(
            session_state_payload(
                speed=control.effective_speed(),
                paused=control.paused,
                anchor=_current_anchor_pointer(),
            )
        )
        while True:
            raw = await ws.receive_json()
            reply = handle_client_message(raw, app.state.loop, pf, control)
            # M5-K3：读档成功回两帧（分叉告知 + 全量），其余仍单帧/无帧
            for frame in frames_of(reply):
                await ws.send_json(frame)
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(ws)


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

    return Pathfinder(app.state.tile_map)
