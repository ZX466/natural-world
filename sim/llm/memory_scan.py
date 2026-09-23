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
- M2-S1 自我未知扩展：hidden 提供时，未触发隐藏属性直陈内容 → 拒写
  （reason=REASON_HIDDEN_LEAK；docs/security/self-unknown.md §4）。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

import structlog

from sim.llm.prompts.banned_words import REWRITE_MAP, scan
from sim.npc.hidden import HiddenProfile, hidden_leak_scan

logger = structlog.get_logger(__name__)

MemorySource = Literal["reason", "dialogue", "event", "interoception"]

#: 命中数 ≤ 该值且全部可映射 → 走改写；否则拒写（memory-scan.md §3）。
REWRITE_MAX_HITS = 2

#: superseded_by / invalid_reason 取值（S5 治理列）。
REASON_BANNED_WORD = "banned_word"
REASON_MANUAL_REVIEW = "manual_review"
#: M2-S1 自我未知：未触发隐藏属性直陈（docs/security/self-unknown.md §3/§4）。
REASON_HIDDEN_LEAK = "hidden_attribute_leak"


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


def make_entry(
    *,
    entry_id: str,
    npc_id: str,
    content: str,
    source: MemorySource,
    event_seq: int | None,
    importance: float,
    emotion_tag: str | None,
    superseded_by: str | None = None,
    invalid_reason: str | None = None,
) -> MemoryEntry:
    """MemoryEntry 唯一构造工厂（S1 守卫：构造点只允许在 memory_scan.py）。

    store 实现（内存/SQLite）一律经此构造，避免绕开 Pipeline 的审计面。
    """
    return MemoryEntry(
        id=entry_id,
        npc_id=npc_id,
        content=content,
        source=source,
        event_seq=event_seq,
        importance=importance,
        emotion_tag=emotion_tag,
        superseded_by=superseded_by,
        invalid_reason=invalid_reason,
    )


@runtime_checkable
class MemoryStore(Protocol):
    """记忆持久化接口（memory-scan.md §4/§5）。

    Pipeline 负责扫描/处置决策；store 负责落库与治理列。实现须保持语义一致：
    - ``persist``：插入一条已通过扫描的记忆，返回含稳定 id 的 MemoryEntry。
    - ``supersede``：只更新治理列（superseded_by/invalid_reason），永不改 content。
    - ``iter_visible``：过滤 ``superseded_by IS NOT NULL``（检索视图）。
    - ``get``：含被取代条目（审计视图）。
    """

    def persist(
        self,
        *,
        npc_id: str,
        content: str,
        source: MemorySource,
        event_seq: int | None,
        importance: float,
        emotion_tag: str | None,
    ) -> MemoryEntry: ...

    def get(self, entry_id: str) -> MemoryEntry: ...

    def supersede(self, old_id: str, new_id: str, reason: str) -> MemoryEntry: ...

    def iter_visible(self, npc_id: str) -> Iterator[MemoryEntry]: ...

    def __len__(self) -> int: ...


class InMemoryStore:
    """内存实现（M0 默认；与 SQLite 实现行为一致，供对照）。"""

    def __init__(self) -> None:
        self._entries: dict[str, MemoryEntry] = {}

    def persist(
        self,
        *,
        npc_id: str,
        content: str,
        source: MemorySource,
        event_seq: int | None,
        importance: float,
        emotion_tag: str | None,
    ) -> MemoryEntry:
        entry = make_entry(
            entry_id=uuid.uuid4().hex,
            npc_id=npc_id,
            content=content,
            source=source,
            event_seq=event_seq,
            importance=importance,
            emotion_tag=emotion_tag,
        )
        self._entries[entry.id] = entry
        return entry

    def get(self, entry_id: str) -> MemoryEntry:
        return self._entries[entry_id]

    def supersede(self, old_id: str, new_id: str, reason: str) -> MemoryEntry:
        old = self._entries[old_id]
        if new_id not in self._entries:
            raise KeyError(f"replacement entry {new_id} does not exist")
        updated = make_entry(
            entry_id=old.id,
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
        return updated

    def iter_visible(self, npc_id: str) -> Iterator[MemoryEntry]:
        for e in self._entries.values():
            # M3-B1 双列口径：任一治理列非空即不可见（R3 修复，与 SqlMemoryStore 同语义）
            if e.npc_id == npc_id and e.superseded_by is None and e.invalid_reason is None:
                yield e

    def __len__(self) -> int:
        return len(self._entries)


class MemoryWritePipeline:
    """记忆写入唯一入口（S1）。扫描/处置后委托 store 持久化（D04 接口化）。

    store 未传时用 InMemoryStore（M0 兼容）；SQLite 实现见
    ``sim.core.persistence.memory_store.SqlMemoryStore``。扫描逻辑与 store 无关。
    """

    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store: MemoryStore = store if store is not None else InMemoryStore()

    @property
    def store(self) -> MemoryStore:
        return self._store

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
        hidden: HiddenProfile | None = None,
        triggered: frozenset[str] = frozenset(),
    ) -> WriteResult:
        """唯一写入入口。上游只允许传叙事化产物（不得传 LLM 原始输出）。

        M2-S1：hidden 提供时，未触发隐藏属性的直陈内容 → 拒写
        （reason=REASON_HIDDEN_LEAK；不改写——直陈面不是机械词，S4 拒写保底）。
        """
        if hidden is not None:
            leaks = hidden_leak_scan(content, hidden, triggered)
            if leaks:
                words = tuple(dict.fromkeys(leak.word for leak in leaks))
                return self._reject(npc_id, source, words, REASON_HIDDEN_LEAK)
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
        return self._store.persist(
            npc_id=npc_id,
            content=content,
            source=source,
            event_seq=event_seq,
            importance=importance,
            emotion_tag=emotion_tag,
        )

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
        updated = self._store.supersede(old_id, new_id, reason)
        logger.info("memory_scan.superseded", old=old_id, new=new_id, reason=reason)
        return updated

    def iter_visible(self, npc_id: str) -> Iterator[MemoryEntry]:
        """检索视图：跳过被取代条目（superseded_by IS NOT NULL 语义）。"""
        return self._store.iter_visible(npc_id)

    def get(self, entry_id: str) -> MemoryEntry:
        """审计视图：含被取代条目（S5 验收：审计可见）。"""
        return self._store.get(entry_id)

    def __len__(self) -> int:
        return len(self._store)
