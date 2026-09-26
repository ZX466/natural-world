"""M4-D2b — 施工推进纯函数：每日 checkpoint、规则版本与尾部确定性重算。"""

from __future__ import annotations

from typing import Any

import pytest

from sim.core.events import EventKind
from sim.world.structure import (
    BUILD_RULE_VERSION,
    CHECKPOINT_INTERVAL_TICKS,
    BuildProgress,
    UnknownBuildRuleError,
    advance_build,
    build_checkpoint_event,
    checkpoint_due,
    mark_checkpoint,
    next_checkpoint_tick,
    recompute_tail,
)


def _state(**overrides: Any) -> BuildProgress:
    values: dict[str, Any] = {
        "structure_id": "hut-1",
        "progress": 0.0,
        "quality": 0.5,
        "integrity": 1.0,
        "build_rule_version": BUILD_RULE_VERSION,
        "started_tick": 10,
        "planned_duration_ticks": CHECKPOINT_INTERVAL_TICKS,
    }
    return BuildProgress(**{**values, **overrides})


class TestCadence:
    def test_relative_to_started_tick_mid_day(self) -> None:
        assert next_checkpoint_tick(_state(started_tick=10)) == CHECKPOINT_INTERVAL_TICKS

    def test_started_on_boundary_waits_full_day(self) -> None:
        assert next_checkpoint_tick(_state(started_tick=CHECKPOINT_INTERVAL_TICKS)) == (
            2 * CHECKPOINT_INTERVAL_TICKS
        )

    def test_checkpoint_not_due_before_boundary(self) -> None:
        assert not checkpoint_due(_state(), tick=CHECKPOINT_INTERVAL_TICKS - 1)

    def test_checkpoint_due_on_boundary(self) -> None:
        assert checkpoint_due(_state(), tick=CHECKPOINT_INTERVAL_TICKS)

    def test_event_emitted_only_when_due(self) -> None:
        state = advance_build(_state(started_tick=0), target_tick=CHECKPOINT_INTERVAL_TICKS)
        assert build_checkpoint_event(state, tick=1) is None
        event = build_checkpoint_event(state, tick=CHECKPOINT_INTERVAL_TICKS)
        assert event is not None
        assert event.event_type is EventKind.STRUCTURE_CHECKPOINT
        assert event.payload["progress"] == pytest.approx(1.0)

    def test_mark_checkpoint_suppresses_repeat_until_next_day(self) -> None:
        state = advance_build(_state(started_tick=0), target_tick=CHECKPOINT_INTERVAL_TICKS)
        marked = mark_checkpoint(state, tick=CHECKPOINT_INTERVAL_TICKS)
        assert not checkpoint_due(marked, tick=CHECKPOINT_INTERVAL_TICKS + 1)
        assert next_checkpoint_tick(marked) == 2 * CHECKPOINT_INTERVAL_TICKS


class TestAdvance:
    def test_progress_is_linear_and_clamped(self) -> None:
        state = _state(started_tick=0)
        half = advance_build(state, target_tick=CHECKPOINT_INTERVAL_TICKS // 2)
        done = advance_build(state, target_tick=CHECKPOINT_INTERVAL_TICKS * 2)
        assert half.progress == pytest.approx(0.5)
        assert done.progress == 1.0

    def test_advance_is_pure_and_idempotent(self) -> None:
        state = _state()
        first = advance_build(state, target_tick=123)
        second = advance_build(state, target_tick=123)
        assert first == second
        assert state.progress == 0.0

    def test_quality_and_integrity_carry_verbatim(self) -> None:
        state = _state(quality=0.37, integrity=0.82)
        assert advance_build(state, target_tick=500).quality == 0.37
        assert advance_build(state, target_tick=500).integrity == 0.82

    def test_unknown_rule_never_falls_back(self) -> None:
        with pytest.raises(UnknownBuildRuleError):
            advance_build(_state(build_rule_version="retired"), target_tick=100)


class TestTailRecompute:
    def test_tail_recompute_bit_equal_next_checkpoint(self) -> None:
        started = _state()
        first = advance_build(started, target_tick=CHECKPOINT_INTERVAL_TICKS)
        recomputed_first = recompute_tail(first, target_tick=CHECKPOINT_INTERVAL_TICKS)
        assert recomputed_first == first

        second = advance_build(started, target_tick=2 * CHECKPOINT_INTERVAL_TICKS)
        recomputed_second = recompute_tail(second, target_tick=2 * CHECKPOINT_INTERVAL_TICKS)
        assert recomputed_second == second

    def test_tail_uses_checkpoint_rule_version(self) -> None:
        checkpoint = BuildProgress(
            structure_id="hut-1",
            progress=0.5,
            quality=0.5,
            integrity=1.0,
            build_rule_version="legacy-v0",
            started_tick=_state().started_tick,
            planned_duration_ticks=_state().planned_duration_ticks,
        )
        with pytest.raises(UnknownBuildRuleError):
            recompute_tail(checkpoint, target_tick=CHECKPOINT_INTERVAL_TICKS)

    def test_whole_lifecycle_tail_is_exact(self) -> None:
        state = _state()
        checkpoints = []
        for day in range(1, 4):
            state = advance_build(state, target_tick=day * CHECKPOINT_INTERVAL_TICKS)
            checkpoints.append(state)
        assert (
            recompute_tail(checkpoints[-1], target_tick=3 * CHECKPOINT_INTERVAL_TICKS)
            == checkpoints[-1]
        )
