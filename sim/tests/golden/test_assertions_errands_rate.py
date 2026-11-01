"""差事完成率断言（M4-C4 + 裁 17-1 定线）。

**2026-11-01 用户裁定启用硬阈值 1.0**（来源：`.orca/audits/t5-baseline-2026-11-01/baseline.json`，
10 seed × 4 链 = 40/40，中位与最差都是 1.0）。口径是**确定性脚本链**
（`chain_runner` 固定 fixture + `parse_intent` + `IntentGate`，零 LLM、零网络、零随机）⇒
无抖动来源 ⇒ 任何一条链失败都是真实回退，必须红。**不沿用 M1 的 80%**（那是单决策口径）。

阈值低于 1.0 只会掩盖真实回退，不会吸收抖动——这是本文件写死 1.0 的理由。
"""

from __future__ import annotations

import pytest

from sim.tests.golden.assertions import (
    ERRAND_COMPLETION_RATE_MIN,
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
    """`measure_baseline` 只折算，不判定——0.7 也能记录（判定归 `assert_baseline_recorded`）。"""
    baseline = measure_baseline(_outcomes(14))
    assert (baseline.cases, baseline.passed) == (20, 14)
    assert baseline.rate == 0.7


def test_assert_returns_baseline_for_archiving() -> None:
    """定线后断言返回基线本身，调用方归档免二次取用。"""
    baseline = measure_baseline(_outcomes(20))
    assert assert_baseline_recorded(baseline) is baseline


def test_threshold_is_one_from_measured_baseline() -> None:
    """阈值 = 实测基线 1.0（不是拍脑袋、不是 M1 的 80%）。"""
    assert ERRAND_COMPLETION_RATE_MIN == 1.0


def test_full_completion_passes() -> None:
    assert_baseline_recorded(measure_baseline(_outcomes(20)))


def test_any_single_failure_is_red() -> None:
    """**定线的关键行为**：少一条就红（确定性夹具无抖动，失败即真实回退）。"""
    with pytest.raises(AssertionError, match="完成率"):
        assert_baseline_recorded(measure_baseline(_outcomes(19)))
    with pytest.raises(AssertionError, match="完成率"):
        assert_baseline_recorded(measure_baseline(_outcomes(1)))
    with pytest.raises(AssertionError, match="完成率"):
        assert_baseline_recorded(measure_baseline(_outcomes(0)))


def test_shell_only_checks_structure() -> None:
    with pytest.raises(AssertionError, match="cases 必须 > 0"):
        assert_baseline_recorded(ErrandBaseline(cases=0, passed=0, rate=0.0))
    with pytest.raises(AssertionError, match="越界"):
        assert_baseline_recorded(ErrandBaseline(cases=20, passed=21, rate=1.05))
    with pytest.raises(AssertionError, match="自相矛盾"):
        assert_baseline_recorded(ErrandBaseline(cases=20, passed=10, rate=0.9))
