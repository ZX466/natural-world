"""差事完成率断言（裁 17-1：完成率线 = **10 日重定标**）。

**2026-11-01 用户裁定启用硬阈值 1.0。** 依据是实测基线，不是拍的：

- 来源 `.orca/audits/t5-baseline-2026-11-01/baseline.json`（第十五轮取证）
- 10 seed × 4 条跨日链 = **40/40 通过**，中位与最差都是 **1.0**
- 口径是**确定性脚本链**（`chain_runner` 固定 fixture + `parse_intent` + `IntentGate`，
  零 LLM、零网络、零随机）⇒ **没有抖动来源** ⇒ 任何一条链失败都是真实回退

**为什么不沿用 M1 的 80%**：M1 是**单决策**口径（`sim/tests/fixtures/errands.py` 20 条脚本
差事，单场景单决策），T5 是 10 日长跑口径。两者口径不同，数值不可搬运。

**为什么不留缓冲**（0.95 之类）：确定性夹具无随机源，缓冲只会让真实回退静默通过，
不会吸收任何抖动。

**口径的诚实边界**：这里的 rate 是**脚本完成率**，不是生产 NPC 自主行为的完成率。
生产自主完成率没有基线数据，本模块不对它做任何断言。

若将来要改这条线，须经用户裁定并引用新的实测基线、显式标注来源。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: 差事完成率硬阈值（用户 2026-11-01 裁定）。
#: 来源：`.orca/audits/t5-baseline-2026-11-01/baseline.json` 实测 40/40 = 1.0。
ERRAND_COMPLETION_RATE_MIN = 1.0


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
    """把本轮 outcomes 折成基线记录（供归档/重定标）。"""
    rate = completion_rate(outcomes)
    return ErrandBaseline(
        cases=len(outcomes),
        passed=sum(1 for o in outcomes if o.passed),
        rate=rate,
    )


def assert_baseline_recorded(baseline: ErrandBaseline) -> ErrandBaseline:
    """校验结构自洽 + 完成率不越线（`ERRAND_COMPLETION_RATE_MIN`）。

    先判结构（自相矛盾的记录连阈值都谈不上），再判阈值。
    返回基线本身，供调用方归档时免去二次取用。
    """
    assert baseline.cases > 0, "基线无效：cases 必须 > 0"
    assert 0 <= baseline.passed <= baseline.cases, (
        f"基线无效：passed={baseline.passed} 越界 cases={baseline.cases}"
    )
    expected = baseline.passed / baseline.cases
    assert baseline.rate == expected, (
        f"基线自相矛盾：rate={baseline.rate!r} != passed/cases={expected!r}"
    )
    assert baseline.rate >= ERRAND_COMPLETION_RATE_MIN, (
        f"差事完成率 {baseline.rate:.3f}（{baseline.passed}/{baseline.cases}）"
        f"低于阈值 {ERRAND_COMPLETION_RATE_MIN}。口径为确定性脚本链（零 LLM 零随机），"
        f"失败即真实回退，不是抖动。基线见 .orca/audits/t5-baseline-2026-11-01/baseline.json"
    )
    return baseline
