"""升格隐藏属性契约（M2-S2，docs/security/l1-whitelist.md §2）。

NPC 升降格（L1↔L2）时隐藏创伤属性（自我未知）的 hidden/triggered 状态
随 runtime 内存态传递——L1 期间触发的属性升格后仍可提，触发窗口外直陈
仍被 hidden_leak_scan 拒绝（闸门 + 记忆写入双防线，同 M2-S1 口径）。

HiddenState 是一个 NPC 在某 tick 的隐藏属性快照，携带三个消费侧方法
（全部纯函数，可重放）：evaluate / check_reason / gate_kwargs / memory_kwargs。
empty() 是无隐藏属性 NPC 的恒等值（各消费点零分支透传）。

runtime 调用点契约见 l1-whitelist.md §3（runtime 归 Claude 架构域）。
"""

from __future__ import annotations

from dataclasses import dataclass

from sim.npc.hidden import HiddenProfile, evaluate_triggers, hidden_leak_scan


@dataclass(frozen=True)
class HiddenState:
    """一个 NPC 在某 tick 的隐藏属性状态（profile + 触发窗口）。"""

    profile: HiddenProfile | None
    triggered: frozenset[str]

    @staticmethod
    def empty() -> HiddenState:
        """无隐藏属性 NPC 的恒等值：闸门/记忆写入行为与 M1 一致。"""
        return HiddenState(profile=None, triggered=frozenset())

    def evaluate(self, context_text: str) -> HiddenState:
        """tick 重估触发窗口（self-unknown.md §2：浮现窗口按 tick 重估）。"""
        if self.profile is None:
            return self
        return HiddenState(
            profile=self.profile,
            triggered=evaluate_triggers(self.profile, context_text),
        )

    def check_reason(self, reason: str) -> bool:
        """reason 是否含未触发属性直陈（True = 有泄漏）。

        降格写回前的降级检查与闸门拒绝同口径（hidden_leak_scan 同工具）；
        行为暗示（走路瘸等）不在扫描面——直陈禁止，行为暗示可议。
        """
        if self.profile is None:
            return False
        return bool(hidden_leak_scan(reason, self.profile, self.triggered))

    def gate_kwargs(self) -> dict:
        """传给 IntentGate.revalidate_at_execution 的参数形。"""
        return {"hidden": self.profile, "triggered": self.triggered}

    def memory_kwargs(self) -> dict:
        """传给 MemoryWritePipeline.write 的参数形。"""
        return {"hidden": self.profile, "triggered": self.triggered}
