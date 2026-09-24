"""sim.npc.norms — 不成文规矩 v0（M3 批次 D1，m3-plan §3 批次 D）。
规矩 = 知识表（他人属性知识）→ **世界内语言行为约束**的最小通路：
- 输入：KnowledgeStore.iter_valid(holder) 的有效知识行（B3 治理列已过滤失效）；
- 筛选：只取**他人**属性知识（subject_npc_id 非 NULL 且 != holder——自身事实
  知识是自我认知不是规矩），按 confidence 降序取 top-N（N=MAX_NORMS）；
- 措辞：`norms_text_of` 只消费知识行的 `fact` 原文——写入门（X7）保证 fact
  已过 banned/hidden 扫描，本模块**不改写、不加数值、不加戏外词**（confidence
  是戏外数值，绝不进文本，§7 铁律）；
- 挂载：调用方（LLM 装配层）把产物交给 assembler 的 [规矩] 段（messages[1]
  内，不破 messages[0] 前缀缓存分界）。
纯函数、无 IO（store 查询归调用方）；C5：同输入同输出（同分按行 id 稳定序）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sim.core.persistence.models import Knowledge

#: 规矩条数上限（成本红线：prompt 预算内的最小集，M4 按实测调）。
MAX_NORMS = 5


def _is_third_party_knowledge(row: Knowledge, holder_id: str) -> bool:
    """他人属性知识判定：subject 两列成对且主体不是持有者自己。"""
    return row.subject_npc_id is not None and row.subject_npc_id != holder_id


def select_norms(
    rows: Iterable[Knowledge], *, holder_id: str, limit: int = MAX_NORMS
) -> tuple[Knowledge, ...]:
    """有效知识行 → 规矩知识行（他人属性、confidence 降序、top-limit）。

    同分按行 id 升序稳定（C5，不依赖 store 迭代序）。
    """
    candidates = [r for r in rows if _is_third_party_knowledge(r, holder_id)]
    candidates.sort(key=lambda r: (-r.confidence, r.id))
    return tuple(candidates[: max(0, limit)])


def norms_text_of(rows: Iterable[Knowledge], *, holder_id: str) -> str:
    """规矩知识行 → [规矩] 段文本（逐行 fact，一行一条）。

    空集 → 空串（assembler 空段省略语义）；fact 直用不改写——写入门是
    措辞的唯一关口，本模块不做第二套词面处理（不造第二判梯）。
    """
    selected = select_norms(rows, holder_id=holder_id)
    if not selected:
        return ""
    return "\n".join(r.fact for r in selected)
