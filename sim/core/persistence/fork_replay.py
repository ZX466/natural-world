"""分叉重放的「可比字段集」口径（预研稿 §6.4，M5-D3-c）。

T2 要求「回放逐位一致」，但有些字段**物理上不可能**逐位一致——比它们就等于把真不一致
埋进噪声里：

- 自增 id（克隆必换 id）、落库时钟（``created_at`` unixepoch）、向量（LLM 嵌入非逐位
  稳定；克隆走字节拷贝另立断言）、归档标记（``is_cold``/``updated_at``）、读侧副作用
  （``last_accessed_tick``）。

纪律：**排除项必须有名字**（`EXCLUDED_FIELDS` 记 ORM 列名 + 理由），且
``COMPARABLE_*`` 与它零交集——新增列若想进比较，必须先在排除表里说明自己为什么不可比
（或反向：想被比较就得从排除表挪进来）。钉子见
``sim/tests/test_m5_fork_replay.py::TestComparableFieldSet``。

跨分支比较语料时还必须忽略**分支身份与行身份**（``branch_id`` / ``id`` / ``entry_id``）：
分叉克隆已重映射（裁 10 (i)），比它们必然不等——那是**预期**的差异，不是缺陷。
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from sim.core.persistence.models import Knowledge, NpcMemory

#: 排除项：ORM 列名 → 排除理由（钉子守卫「有名字、有理由、是真实列名」）。
EXCLUDED_FIELDS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "id": "自增主键：克隆必换 id（裁 10 (i) 显式分配）",
        "branch_id": "分支身份：跨分支比较语料时本就不同（这正是分叉的定义）",
        "entry_id": "记忆业务句柄：裁 10 (i) 已重映射（uuid5 派生），比它必假红",
        "created_at": "落库墙钟（unixepoch）：分叉两次落库时间不同",
        "embedding": "向量：LLM 嵌入非逐位稳定；克隆字节相等由 R-1 另立断言",
        "last_accessed_tick": "读侧副作用：回放/读档不得改它（改了就回放不纯）",
    }
)

#: `npc_memories` 可比字段（内容面 + 治理面 + 证据面）。
COMPARABLE_MEMORY_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "npc_id",
        "content",
        "source",
        "importance",
        "emotion_tag",
        "distortion",
        "event_seq",
        "created_at_tick",
        "superseded_by",
        "invalid_reason",
    }
)

#: `knowledge` 可比字段。
COMPARABLE_KNOWLEDGE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "holder_id",
        "fact",
        "confidence",
        "source",
        "learned_at",
        "subject_npc_id",
        "subject_attr_id",
        "evidence_ref",
        "invalidated",
        "invalid_reason",
    }
)

#: `knowledge.source_knowledge_id` 是**自增 int 链指针**，克隆后必变 → 不可比；
#: 但它「非空/为空」的形态要靠 R-2 的悬空断言保证，故不进可比集（名字在此登记）。
_SOURCE_CHAIN_NOTE: Final[str] = "knowledge.source_knowledge_id（自增链指针，克隆后必变）"


def comparable_memory(row: NpcMemory) -> dict[str, object]:
    """`npc_memories` 行 → 可比字段字典（只含 :data:`COMPARABLE_MEMORY_FIELDS`）。"""
    return {name: getattr(row, name) for name in sorted(COMPARABLE_MEMORY_FIELDS)}


def comparable_knowledge(row: Knowledge) -> dict[str, object]:
    """`knowledge` 行 → 可比字段字典（只含 :data:`COMPARABLE_KNOWLEDGE_FIELDS`）。

    ``evidence_ref`` 是**归一后的证据引用**二元组 ``(分支, seq)``：``evidence_branch_id``
    为 NULL 的语义是「证据就在本分支」，故归一成本行的 ``branch_id`` 再比——否则跨分支
    克隆（事件不克隆 ⇒ NULL 被改写为父分支 id，0008-d）会假红。
    """
    values: dict[str, object] = {
        name: getattr(row, name) for name in COMPARABLE_KNOWLEDGE_FIELDS if name != "evidence_ref"
    }
    values["evidence_ref"] = (row.evidence_branch_id or row.branch_id, row.evidence_seq)
    return values
