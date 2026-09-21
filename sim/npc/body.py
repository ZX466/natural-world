"""sim.npc.body — 身体状态（M2-A1 §1.1；DESIGN 铁律 7「必须有身体」）。

hp/hunger 等数值 → 内感受叙事化数据源（narrate 消费）。
零 LLM 成本；纯数据 + 叙事映射表。
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class BodyState:
    """NPC 身体数值（M2 范围：hp/饥饿对齐；伤病在 npc_health 档）。"""

    npc_id: str
    hp: float = 100.0  # 0..100
    hunger: float = 0.0  # 0..1（与 needs.hunger 同步，单真相源在 needs，本字段为投影）

    def interoception_text(self) -> str:
        """内感受叙事（assembler SituationSlice.interoception_text 的来源）。

        映射规则对齐 DESIGN §7 感官流转换表。
        """
        parts: list[str] = []
        if self.hp < 30:
            parts.append("伤处疼得厉害，喘气都得收着点")
        elif self.hp < 60:
            parts.append("身上有些发虚")
        if self.hunger >= 0.8:
            parts.append("肚子空得有点发慌")
        elif self.hunger >= 0.5:
            parts.append("有点饿了")
        return "；".join(parts) if parts else "身体还算利索"

    def damaged(self, amount: float) -> BodyState:
        return replace(self, hp=max(0.0, self.hp - amount))

    def healed(self, amount: float) -> BodyState:
        return replace(self, hp=min(100.0, self.hp + amount))
