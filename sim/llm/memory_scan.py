"""记忆写入前禁词扫描管线（memory-scan.md S1-S6 落地）。

设计（docs/security/memory-scan.md，Claude 架构域已批原则方向）：
- S1 唯一入口：所有 MemoryEntry 写入必须经 MemoryWritePipeline.write()；
  CI 守卫测试断言仓内无绕过构造点（test_memory_scan.py::TestS1Guard）。
- S2 单一词表：与 prompt 出口共用 sim.llm.prompts.banned_words。
- S3 改写优先：命中 ≤2 且全部命中词在 REWRITE_MAP → 机械替换后复扫，通过才写。
- S4 拒写次之：>2 处 / 有词无映射 → 不落库，返回结构化原因。
  底线判断：记忆缺失比记忆污染安全。
- S5 补救：永不改内容字段；supersede(old, new) 只更新治理列
  （superseded_by / invalid_reason）；检索用 iter_visible 过滤。
- S6 观测：每次命中走 structlog dev 通道（npc_id/source/命中词/处置）。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

import structlog

from sim.llm.prompts.banned_words import REWRITE_MAP, scan

logger = structlog.get_logger(__name__)

MemorySource = Literal["reason", "dialogue", "event", "interoception"]

#: 命中数 ≤ 该值且全部可映射 → 走改写；否则拒写（memory-scan.md §3）。
REWRITE_MAX_HITS = 2

#: superseded_by / invalid_reason 取值（S5 治理列）。
REASON_BANNED_WORD = "banned_word"
REASON_MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class MemoryEntry:
    """记忆条目（存储形态与 opencode D03 建表对齐；M0 阶段内存态验证）。

    content 是唯一被扫描保护的叙事文本；治理列见 memory-scan.md §4。
    """

    id: str
    npc_id: str
    content: str
    source: MemorySource
    event_seq: int | None
    importance: float
    emotion_tag: str | None
    superseded_by: str | None = None
    invalid_reason: str | None = None


@dataclass(frozen=True)
class WriteResult:
    """write() 结构化产出：accepted 决定是否落库；其余字段供观测与上游反馈。"""

    accepted: bool
    entry: MemoryEntry | None
    action: str  # "written" | "rewritten" | "rejected"
    hits: tuple[str, ...] = ()
    reason: str | None = None


class MemoryWritePipeline:
    """记忆写入唯一入口（S1）。持有条目表并暴露治理/检索 API（S5）。

    M0 阶段 entries 为内存 list；opencode D03 落 npc_memories 表后，
    store 侧实现同一接口即可，扫描/处置逻辑不变。
    """

    def __init__(self) -> None:
        self._entries: dict[str, MemoryEntry] = {}

    # ------------------------------------------------------------------
    # S1-S4：写入路径
    # ------------------------------------------------------------------

    def write(
        self,
        npc_id: str,
        content: str,
        *,
        source: MemorySource,
        event_seq: int | None,
        importance: float,
        emotion_tag: str | None,
    ) -> WriteResult:
        """唯一写入入口。上游只允许传叙事化产物（不得传 LLM 原始输出）。"""
        result = scan(content)
        if result.ok:
            entry = self._persist(npc_id, content, source, event_seq, importance, emotion_tag)
            return WriteResult(accepted=True, entry=entry, action="written")

        hit_words = tuple(dict.fromkeys(h.word for h in result.hits))

        if len(result.hits) <= REWRITE_MAX_HITS and all(h.word in REWRITE_MAP for h in result.hits):
            rescanned = scan(result.cleaned)
            if rescanned.ok:
                entry = self._persist(
                    npc_id, result.cleaned, source, event_seq, importance, emotion_tag
                )
                logger.info(
                    "memory_scan.rewritten",
                    npc_id=npc_id,
                    source=source,
                    hits=list(hit_words),
                )
                return WriteResult(accepted=True, entry=entry, action="rewritten", hits=hit_words)
            # 复扫仍有残留 → 按拒写处理（词面级机械替换救不回的文本）
            residual = tuple(dict.fromkeys(h.word for h in rescanned.hits))
            return self._reject(npc_id, source, hit_words + residual, "rewrite_residual")

        reason_code = "unrewritable" if len(result.hits) <= REWRITE_MAX_HITS else "too_many_hits"
        return self._reject(npc_id, source, hit_words, reason_code)

    def _persist(
        self,
        npc_id: str,
        content: str,
        source: MemorySource,
        event_seq: int | None,
        importance: float,
        emotion_tag: str | None,
    ) -> MemoryEntry:
        entry = MemoryEntry(
            id=uuid.uuid4().hex,
            npc_id=npc_id,
            content=content,
            source=source,
            event_seq=event_seq,
            importance=importance,
            emotion_tag=emotion_tag,
        )
        self._entries[entry.id] = entry
        return entry

    def _reject(
        self, npc_id: str, source: MemorySource, hit_words: tuple[str, ...], reason: str
    ) -> WriteResult:
        logger.warning(
            "memory_scan.rejected",
            npc_id=npc_id,
            source=source,
            hits=list(hit_words),
            reason=reason,
        )
        return WriteResult(
            accepted=False, entry=None, action="rejected", hits=hit_words, reason=reason
        )

    # ------------------------------------------------------------------
    # S5：append-only 补救与检索过滤
    # ------------------------------------------------------------------

    def supersede(self, old_id: str, new_id: str, reason: str) -> MemoryEntry:
        """标记旧条目无效并指向替代条目。只动两列治理列，不碰内容。"""
        old = self._entries[old_id]
        if new_id not in self._entries:
            raise KeyError(f"replacement entry {new_id} does not exist")
        updated = MemoryEntry(
            id=old.id,
            npc_id=old.npc_id,
            content=old.content,
            source=old.source,
            event_seq=old.event_seq,
            importance=old.importance,
            emotion_tag=old.emotion_tag,
            superseded_by=new_id,
            invalid_reason=reason,
        )
        self._entries[old_id] = updated
        logger.info("memory_scan.superseded", old=old_id, new=new_id, reason=reason)
        return updated

    def iter_visible(self, npc_id: str) -> Iterator[MemoryEntry]:
        """检索视图：跳过被取代条目（superseded_by IS NOT NULL 语义）。"""
        for e in self._entries.values():
            if e.npc_id == npc_id and e.superseded_by is None:
                yield e

    def get(self, entry_id: str) -> MemoryEntry:
        """审计视图：含被取代条目（S5 验收：审计可见）。"""
        return self._entries[entry_id]

    def __len__(self) -> int:
        return len(self._entries)
