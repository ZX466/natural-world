"""harness 断言门单测（性能域，pi）— M2-P6 advisory 门。
契约：
- 缺省（env 未置）：`assert_threshold` / `assert_median_threshold` 越线即 AssertionError
  （定标机硬断言，P5 前行为不变）；
- `PI_BENCH_ADVISORY=1`（nightly / 共享 runner）：越线不失败，只记录（返回是否越线 +
  记日志）；采集逻辑完全不变——门只决定「断不断言」。
- env 读在**调用时**（非 import 时），monkeypatch 可切；非法值（非 "1"）视作未置。
"""

from __future__ import annotations

import pytest

from sim.tests.bench.harness import (
    advisory_mode,
    assert_median_threshold,
    assert_threshold,
)


class _FakeMedian:
    """冒牌 median 统计量（harness 只读 .stats.median / .stats.mean，单位秒）。"""

    def __init__(self, median_s: float, mean_s: float | None = None) -> None:
        self.median = median_s
        self.mean = mean_s if mean_s is not None else median_s


class _FakeStats:
    def __init__(self, median_s: float, mean_s: float | None = None) -> None:
        self.stats = _FakeMedian(median_s, mean_s)


class TestAdvisoryModeFlag:
    def test_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PI_BENCH_ADVISORY", raising=False)
        assert advisory_mode() is False

    def test_one_turns_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PI_BENCH_ADVISORY", "1")
        assert advisory_mode() is True

    def test_non_one_stays_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PI_BENCH_ADVISORY", "0")
        assert advisory_mode() is False
        monkeypatch.setenv("PI_BENCH_ADVISORY", "true")
        assert advisory_mode() is False
        monkeypatch.setenv("PI_BENCH_ADVISORY", "")
        assert advisory_mode() is False


class TestAssertThresholdGate:
    def test_over_line_fails_without_advisory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PI_BENCH_ADVISORY", raising=False)
        with pytest.raises(AssertionError, match="超阈值"):
            assert_threshold(9.0, 3.0, "测试项")

    def test_over_line_passes_with_advisory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PI_BENCH_ADVISORY", "1")
        assert assert_threshold(9.0, 3.0, "测试项") is True  # 返回值 = 越线且仅记录

    def test_under_line_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PI_BENCH_ADVISORY", raising=False)
        assert assert_threshold(1.0, 3.0, "测试项") is False
        monkeypatch.setenv("PI_BENCH_ADVISORY", "1")
        assert assert_threshold(1.0, 3.0, "测试项") is False


class TestAssertMedianThresholdGate:
    def test_over_line_fails_without_advisory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PI_BENCH_ADVISORY", raising=False)
        with pytest.raises(AssertionError, match="中位超阈值"):
            assert_median_threshold(_FakeStats(0.009), 3.0, "测试项")

    def test_over_line_passes_with_advisory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PI_BENCH_ADVISORY", "1")
        assert assert_median_threshold(_FakeStats(0.009), 3.0, "测试项") is True

    def test_under_line_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PI_BENCH_ADVISORY", raising=False)
        assert assert_median_threshold(_FakeStats(0.001), 3.0, "测试项") is False
