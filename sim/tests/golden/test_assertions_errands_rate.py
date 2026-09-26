"""差事完成率壳的最小单元测试（M4-C4）——**验证它不设阈值**（裁 17-1：10 日重定标）。"""

from __future__ import annotations

import pytest

from sim.tests.golden.assertions import (
    ErrandBaseline,
    ErrandOutcome,
    assert_baseline_recorded,
    completion_rate,
    measure_baseline,
)


def _outcomes(passed: int, total: int = 20) -> list[ErrandOutcome]:
    """固定序列（C5：无 random）：前 passed 条通过、其余失败。"""
    return [
        ErrandOutcome(
            case_id=f"E{i:02d}",
            passed=i < passed,
            reason="ok" if i < passed else "未完成",
        )
        for i in range(total)
    ]


def test_completion_rate_math() -> None:
    assert completion_rate(_outcomes(16)) == 0.8  # M1 口径 16/20 的回声
    assert completion_rate(_outcomes(20)) == 1.0
    assert completion_rate(_outcomes(0)) == 0.0


def test_empty_sample_is_error_not_zero() -> None:
    with pytest.raises(ValueError, match="无样本"):
        completion_rate([])


def test_measure_baseline_records() -> None:
    baseline = measure_baseline(_outcomes(14))
    assert (baseline.cases, baseline.passed) == (20, 14)
    assert baseline.rate == 0.7
    assert_baseline_recorded(baseline)


def test_shell_does_not_threshold_low_rate() -> None:
    """**裁 17-1 的关键行为**：完成率再低也不红（阈值待 10 日重定标）。"""
    assert_baseline_recorded(measure_baseline(_outcomes(1)))  # 5% 也放过
    assert_baseline_recorded(measure_baseline(_outcomes(0)))  # 0% 也放过


def test_shell_only_checks_structure() -> None:
    with pytest.raises(AssertionError, match="cases 必须 > 0"):
        assert_baseline_recorded(ErrandBaseline(cases=0, passed=0, rate=0.0))
    with pytest.raises(AssertionError, match="越界"):
        assert_baseline_recorded(ErrandBaseline(cases=20, passed=21, rate=1.05))
    with pytest.raises(AssertionError, match="自相矛盾"):
        assert_baseline_recorded(ErrandBaseline(cases=20, passed=10, rate=0.9))
