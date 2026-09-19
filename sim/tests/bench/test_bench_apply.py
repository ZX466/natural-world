"""事件 apply 基准（性能域，pi）— sim.core.world.EventBus.apply（唯一写路径，C4）

回归阈值：APPLY_P99_LIMIT_MS = 0.04ms/事件（bench-plan.md §3；budget.md §2.3）。
口径：50 个 MOVE 事件 × 多次，测单事件 apply 均耗。
M0 事件种类最小集：world.create / move / combat.scale_change / entropy_inject。
"""

from __future__ import annotations

import pytest

from sim.core.events import WorldEvent, move_event
from sim.core.world import EventBus, TickContext, WorldState, build_default_bus

from .harness import assert_threshold, make_state
from .thresholds import APPLY_P99_LIMIT_MS

N_ENTITIES = 50
EVENTS_PER_ROUND = 50


def _apply_50_moves(bus: EventBus, state: WorldState, ctx: TickContext) -> float:
    """应用 50 个 MOVE 事件（L1 稳态：50 NPC 每 tick 决策事件），返回每事件毫秒。"""
    events: list[WorldEvent] = []
    for i in range(N_ENTITIES):
        events.append(
            move_event(
                tick=state.tick + 1,
                actor_id=f"e{i:03d}",
                start=(i, 0),
                goal=(i, 3),
                path=((i, 0), (i, 1), (i, 2), (i, 3)),
            )
        )
    t0 = _perf_counter()
    for ev in events:
        bus.apply(state, ev, ctx)
    return (_perf_counter() - t0) * 1000.0 / len(events)


def _perf_counter() -> float:
    import time

    return time.perf_counter()


@pytest.mark.bench
def test_apply_move_per_event(benchmark) -> None:
    """MOVE 事件单事件 apply 耗时 ≤0.04ms（budget §2.3）。"""
    bus = build_default_bus()
    state = make_state(N_ENTITIES)
    ctx = TickContext()

    def _run() -> float:
        return _apply_50_moves(bus, state, ctx)

    measured = benchmark.pedantic(_run, rounds=5, iterations=1)
    assert_threshold(measured, APPLY_P99_LIMIT_MS, "apply(move) 单事件")


@pytest.mark.bench
def test_apply_50_events_batch(benchmark) -> None:
    """50 事件批量耗时（budget §1 名义列：apply 批 1ms / tick）。"""
    bus = build_default_bus()
    state = make_state(N_ENTITIES)
    ctx = TickContext()

    def _run() -> float:
        return _apply_50_moves(bus, state, ctx) * EVENTS_PER_ROUND

    measured = benchmark.pedantic(_run, rounds=5, iterations=1)
    assert_threshold(measured, 2.0, "apply 50 事件批量")  # budget §2.3 上限 2ms


def test_apply_unknown_kind_rejected() -> None:
    """契约守卫：未注册 kind 必须拒绝（唯一写路径防线 1）。"""
    from sim.core.events import EventKind, WorldEvent

    bus = build_default_bus()
    state = make_state(1)
    bad = WorldEvent(
        tick=state.tick + 1,
        event_type=EventKind.TILE_CHANGED,  # M0 未启用 handler（M3 预留）
        actor_id="",
        payload={},
    )
    try:
        bus.apply(state, bad, TickContext())
    except NotImplementedError:
        pass
    else:
        raise AssertionError("未启用事件种类未拒绝（TILE_CHANGED 在 M0 应拒绝）")


def test_apply_future_event_rejected() -> None:
    """契约守卫：来自未来的事件必须拒绝（tick 合法性防线 2）。"""
    from sim.core.events import EventKind, WorldEvent

    bus = build_default_bus()
    state = make_state(1)
    future = WorldEvent(
        tick=state.tick + 99,
        event_type=EventKind.WORLD_CREATE,
        actor_id="",
        payload={"seed": 1, "entities": []},
    )
    try:
        bus.apply(state, future, TickContext())
    except ValueError:
        pass
    else:
        raise AssertionError("未来 tick 事件未被拒绝")
