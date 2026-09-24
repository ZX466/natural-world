"""sim.npc.society — 关系演化规则（M3 批次 B-B3 最小集；m3-plan §3）。

M3 最小集（防过度设计）：
1. retell 转述成功 → to_npc 对 from_npc 的 trust +δ（有向：只动 b→a 方向）；
2. witnessed 目击他人隐藏属性 → fear +δ（trauma 关联）；
3. chat 日常对话 → affection 小幅漂移 + last_interaction 刷新。

边界（m2 架构稿 §3 延续）：不做关系推理；关系面不出感知帧（社会未知轴）；
不碰 L1 效用链（批次 D 才接）。δ 为常量起步，M4 按实测调。
"""

from __future__ import annotations

from typing import Literal

from sim.core.persistence.relationship_store import RelationshipStore

#: 转述成功对转述者的信任增益（b→a 方向）。
RETELL_TRUST_DELTA = 0.05
#: 目击他人隐藏属性浮现的恐惧增益（b→subject 方向）。
WITNESS_FEAR_DELTA = 0.10
#: 日常对话的好感漂移。
CHAT_AFFECTION_DELTA = 0.02

InteractionKind = Literal["retell", "witness_hidden", "chat"]

#: kind → (from 侧字段, to 侧字段, delta)：from_npc 主动、to_npc 承受印象——
#: 演化落在 to_npc 对 from_npc 的关系行（b→a，有向不对称）。
_RULES: dict[str, tuple[str, float]] = {
    "retell": ("trust", RETELL_TRUST_DELTA),
    "witness_hidden": ("fear", WITNESS_FEAR_DELTA),
    "chat": ("affection", CHAT_AFFECTION_DELTA),
}


def apply_interaction(
    store: RelationshipStore, *, kind: InteractionKind, from_npc: str, to_npc: str
) -> None:
    """一次互动的关系演化（幂等单次；调用方决定频次——频控归行为层）。

    演化方向：to_npc 对 from_npc 的关系行（印象在承受方）。
    """
    try:
        field, delta = _RULES[kind]
    except KeyError as exc:
        raise ValueError(f"未知互动类型: {kind!r}") from exc
    store.adjust(to_npc, from_npc, **{field: delta})
