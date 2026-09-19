"""时钟基准（性能域，pi）— sim.core.clock.GameClock。

回归阈值：TICK_P99_LIMIT_MS = 8.3ms（budget.md §1，1x 每 tick 预算 16.6ms 的 50%）。
口径：跑 600 帧（600 tick = 10 真实秒 @1x）测每 tick 均耗。
"""

from __future__ import annotations

import pytest

from sim.core.clock import GameClock

from .harness import assert_threshold, ms_per_tick
from .thresholds import TICK_P99_LIMIT_MS


@pytest.mark.bench
def test_clock_advance_1x_per_tick_latency_empty_world(bench_loop_empty, benchmark) -> None:
    """空世界纯内核：clock.advance + tick 固定序，每 tick 均耗应远低于预算。"""

    def _run() -> float:
        return ms_per_tick(bench_loop_empty, frames=600)

    measured = benchmark.pedantic(_run, rounds=5, iterations=1)
    assert_threshold(measured, TICK_P99_LIMIT_MS, "clock/tick 空世界每 tick")


@pytest.mark.bench
def test_clock_advance_1x_per_tick_latency_50npc(bench_loop_50, benchmark) -> None:
    """50 NPC（L1 规模）世界：每 tick 均耗须 ≤ 8.3ms 回归线。"""

    def _run() -> float:
        return ms_per_tick(bench_loop_50, frames=600)

    measured = benchmark.pedantic(_run, rounds=5, iterations=1)
    assert_threshold(measured, TICK_P99_LIMIT_MS, "clock/tick 50 NPC 每 tick")


def test_clock_ticks_per_real_second_contract() -> None:
    """契约守卫（T1 级，不跑循环只查换算）：1x=60、战斗尺=1（DESIGN §9/§10 v2.1）。"""
    clock = GameClock(speed=1.0)
    assert clock.ticks_per_real_second() == 60.0
    clock.enter_combat()
    assert clock.ticks_per_real_second() == 1.0
    clock.exit_combat()
    assert clock.ticks_per_real_second() == 60.0


def test_clock_speed_switch_contract() -> None:
    """倍速：合法 0/1/4/16，非法值拒绝。"""
    for speed in (0.0, 1.0, 4.0, 16.0):
        GameClock(speed=speed)
    try:
        GameClock(speed=2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("非法倍速 2.0 未被拒绝（应只允许 0/1/4/16）")
