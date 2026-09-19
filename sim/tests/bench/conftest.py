"""基准 harness fixtures（性能域，pi）。

bench_loop_empty / bench_loop_50：由 harness 装配的真实内核 loop。
"""

from __future__ import annotations

import pytest

from sim.core.tick import TickLoop

from .harness import make_loop, make_state

# expose harness helpers for `from sim.tests.bench import assert_threshold` style imports
__all__ = ["make_loop", "make_state"]


@pytest.fixture
def bench_loop_empty() -> TickLoop:
    """空世界（0 实体）loop — 纯内核开销（clock/tick 固定序）。"""
    return make_loop(0)


@pytest.fixture
def bench_loop_50() -> TickLoop:
    """50 NPC 世界 loop — 对应 DESIGN §13 L1 规模。"""
    return make_loop(50)
