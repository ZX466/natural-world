"""世界检查点与恢复；内部状态不得经过 WS 表现快照反向推断。"""

from __future__ import annotations

import gzip
from collections.abc import Mapping, Sequence
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sim.core.clock import GameClock
from sim.core.events import CombatScaleChangePayload, EventKind, WorldEvent
from sim.core.persistence.anchor_package import MaterializationHooks
from sim.core.persistence.models import Branch, Snapshot
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.snapshot_policy import prune_hot_snapshots
from sim.core.persistence.store import SqlEventStore, decompress_snapshot
from sim.core.tick import TickLoop
from sim.core.world import TickContext, WorldState, build_default_bus
from sim.world.chaos import ChaosState


class WorldCheckpoint(BaseModel):
    """独立于协议的内部快照形状；格式错误必须拒绝，不能退化为空世界。"""

    model_config = ConfigDict(extra="forbid")
    format: Literal["world.v1"] = "world.v1"
    state: WorldState
    combat_active: bool = False
    chaos_chain: float = Field(default=0.0, ge=0.0, le=1.0)
    rng_states: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @classmethod
    def capture(cls, loop: TickLoop) -> WorldCheckpoint:
        return cls(
            state=loop.state,
            combat_active=loop.context.combat_active,
            chaos_chain=loop.chaos.chain,
            rng_states={
                key: gen.bit_generator.state for key, gen in loop.context.rng_cache.items()
            },
        )

    def make_loop(self) -> TickLoop:
        cache: dict[str, Any] = {}
        for key, state in self.rng_states.items():
            # 当前引擎只注册 PCG64；不按磁盘字符串动态导入/实例化任意类。
            generator = np.random.Generator(np.random.PCG64(0))
            generator.bit_generator.state = state
            cache[key] = generator
        loop = TickLoop(
            clock=GameClock(),
            bus=build_default_bus(),
            state=self.state,
            context=TickContext(rng_cache=cache),
            chaos=ChaosState(self.chaos_chain),
        )
        loop.clock.restore_tick(self.state.tick)
        if self.combat_active:
            loop.enter_combat()
        return loop


async def flush_world(
    store: SqlEventStore, branch_id: str, loop: TickLoop, events: Sequence[WorldEvent]
) -> None:
    """事件和完整世界检查点同事务提交；保存的是本批结束状态。"""
    if not events:
        return
    checkpoint = WorldCheckpoint.capture(loop)
    blob = gzip.compress(checkpoint.model_dump_json().encode(), compresslevel=6)

    async def checkpoint_projection(
        session: AsyncSession, seq_by_index: dict[int, int], _events: Sequence[WorldEvent]
    ) -> None:
        session.add(
            Snapshot(
                branch_id=branch_id,
                seq=max(seq_by_index.values()),
                tick=checkpoint.state.tick,
                snapshot_data=blob,
                schema_version=1,
                is_cold=False,
            )
        )
        await prune_hot_snapshots(session, branch_id)

    await NpcStore(store, branch_id=branch_id).flush_tick(
        events, extra_projection=checkpoint_projection
    )


def expand_world(payload: dict[str, Any], window: Sequence[Mapping[str, Any]]) -> TickLoop:
    """展开内部快照并折叠事件尾部；表现帧缺少世界真相，拒绝直接展开。"""
    if "format" in payload:
        loop = WorldCheckpoint.model_validate(payload).make_loop()
    elif {"world_seed", "tick", "entities"} <= payload.keys():
        # 兼容已有完整 WorldState 快照；绝不把 actors/rtoken 帧当世界态。
        loop = WorldCheckpoint(state=WorldState.model_validate(payload)).make_loop()
    else:
        if payload:
            raise ValueError("snapshot has no restorable world state")
        loop = WorldCheckpoint(state=WorldState()).make_loop()
    for row in window:
        event = WorldEvent.model_validate(row)
        loop.replay_until(max(loop.state.tick, event.tick - 1))
        loop.enqueue(event)
        if event.event_type is EventKind.COMBAT_SCALE_CHANGE:
            active = CombatScaleChangePayload.model_validate(event.payload).entering
            loop.enter_combat() if active else loop.exit_combat()
    loop.replay_until(max([loop.state.tick, *(int(row["tick"]) for row in window)]))
    loop.pending_events.clear()
    loop.pending_delta_entity_ids.clear()
    return loop


async def restore_world(store: SqlEventStore, branch_id: str) -> TickLoop:
    """恢复当前分支；沿祖先查检查点时严格遵守每个分叉游标。"""
    history = await store.read_branch_history(branch_id)
    if sum(row["event_type"] == EventKind.WORLD_CREATE for row in history) != 1:
        raise ValueError("world history must contain exactly one genesis")
    current = branch_id
    upper = 2**62 - 1
    descendants: set[str] = set()
    while True:
        snapshot = await store.latest_snapshot(current, 2**62 - 1, max_seq=upper)
        if snapshot is not None:
            if snapshot.schema_version != 1:
                raise ValueError("unsupported world snapshot schema")
            payload = decompress_snapshot(snapshot)
            if {"world_seed", "tick", "entities"} <= payload.keys() or "format" in payload:
                start = next(
                    (
                        i + 1
                        for i, row in enumerate(history)
                        if row["branch_id"] == current and row["seq"] == snapshot.seq
                    ),
                    None,
                )
                if snapshot.seq == 0:
                    # 子线 seq=0 已含祖先基线，后缀只从子线/其后代开始。
                    start = next(
                        (
                            i
                            for i, row in enumerate(history)
                            if row["branch_id"] in descendants | {current}
                        ),
                        len(history),
                    )
                if start is None:
                    raise ValueError("snapshot cursor is outside branch history")
                restored = expand_world(payload, [])
                if restored.state.tick != snapshot.tick:
                    raise ValueError("snapshot tick does not match world state")
                # 旧 WorldState 快照没有时间尺；从已记录的切换恢复。
                if "format" not in payload:
                    for row in history[:start]:
                        if row["event_type"] == EventKind.COMBAT_SCALE_CHANGE:
                            active = CombatScaleChangePayload.model_validate(
                                row["payload"]
                            ).entering
                            restored.enter_combat() if active else restored.exit_combat()
                return expand_world(WorldCheckpoint.capture(restored).model_dump(), history[start:])
        async with store.session_factory() as session:
            branch = await session.get(Branch, current)
            if branch is None:
                raise ValueError("missing branch history")
            if branch.forked_from_branch is None:
                break
            descendants.add(current)
            current = branch.forked_from_branch
            if branch.forked_from_seq is None:
                raise ValueError("missing branch cutoff")
            upper = branch.forked_from_seq
    return expand_world({}, history)


async def has_world(store: SqlEventStore) -> bool:
    """只有真正空库才允许创世；当前指针损坏不能被新世界掩盖。"""
    async with store.session_factory() as session:
        return await session.scalar(select(Branch.id).limit(1)) is not None


def materialization_hooks(*, target_tick: int | None = None) -> MaterializationHooks:
    """每次读档独立展开，验证失败不触碰正在运行的世界或随机流。"""
    restored: TickLoop | None = None

    async def expand(payload: Mapping[str, Any], window: Sequence[Mapping[str, Any]]) -> TickLoop:
        nonlocal restored
        restored = expand_world(dict(payload), window)
        if target_tick is not None:
            restored.replay_until(target_tick)
        return restored

    async def override(world: Any, values: Mapping[str, Any]) -> TickLoop:
        if values:
            raise ValueError("unsupported agent override")
        if not isinstance(world, TickLoop):
            raise ValueError("materialization did not produce a world")
        return world

    async def corpus(_rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        # 包内行已由物化器校验，写入子线由 fork 的事务承担。
        return None

    async def rng(blob: str) -> None:
        from sim.core.rng_state import restore_rng_state
        from sim.world.weather import WEATHER_STREAM

        if restored is None:
            raise ValueError("world must be expanded before rng restoration")
        restore_rng_state(blob, restored.context.rng_cache, (WEATHER_STREAM,))

    return MaterializationHooks(
        expand_world=expand, apply_override=override, load_corpus=corpus, restore_rng=rng
    )
