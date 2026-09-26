"""差事完成率断言**壳**（裁 17-1：完成率线 = **10 日重定标**）。

**本轮不设阈值**——按纪律「不写断言组本体里没有依据的数」：M1 的 80% 是**单决策**口径
（`sim/tests/fixtures/errands.py` 20 条脚本差事，单场景单决策），而 T5 是 10 日长跑口径；
跨日多决策续接 fixture 属 D 批（裁 17-③）任务。故本模块只做两件事：

1. `measure_baseline()`：**基线实测**——把本轮 outcomes 折成 `{cases, passed, rate}` 记录，
   供 `golden-nightly` 归档（每种子一份），作为 10 日重定标的输入；
2. `assert_baseline_recorded()`：**只校验结构**（样本数 > 0、rate ∈ [0,1]、rate 与
   passed/cases 自洽），**不对 rate 本身设阈值**——定线由 D 批交付时附实测基线后再裁。

若将来要启用硬阈值，唯一正确的做法是把 D 批交付的实测基线写成常量并显式标注来源，
不得沿用 M1 的 80%（口径不同）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrandOutcome:
    """一条差事的结果（`reason` 仅诊断用，不参与判定）。"""

    case_id: str
    passed: bool
    reason: str = ""


@dataclass(frozen=True)
class ErrandBaseline:
    """10 日重定标用的**基线实测**（cases / passed / rate；rate = passed / cases）。"""

    cases: int
    passed: int
    rate: float


def completion_rate(outcomes: Sequence[ErrandOutcome]) -> float:
    """完成率数值（空样本抛错——率无定义，不静默返 0）。"""
    if not outcomes:
        raise ValueError("完成率无样本：outcomes 为空")
    done = sum(1 for o in outcomes if o.passed)
    return done / len(outcomes)


def measure_baseline(outcomes: Sequence[ErrandOutcome]) -> ErrandBaseline:
    """把本轮 outcomes 折成基线记录（供归档/重定标，不设阈值）。"""
    rate = completion_rate(outcomes)
    return ErrandBaseline(
        cases=len(outcomes),
        passed=sum(1 for o in outcomes if o.passed),
        rate=rate,
    )


def assert_baseline_recorded(baseline: ErrandBaseline) -> None:
    """裁 17-1 壳：**只校验结构自洽，不判 rate 好坏**（阈值待 10 日重定标）。"""
    assert baseline.cases > 0, "基线无效：cases 必须 > 0"
    assert 0 <= baseline.passed <= baseline.cases, (
        f"基线无效：passed={baseline.passed} 越界 cases={baseline.cases}"
    )
    expected = baseline.passed / baseline.cases
    assert baseline.rate == expected, (
        f"基线自相矛盾：rate={baseline.rate!r} != passed/cases={expected!r}"
    )
    # 裁 17-1：此处**刻意不设完成率阈值**——M1 80% 是单决策口径；10 日线待 D 批实测基线后重定标。
