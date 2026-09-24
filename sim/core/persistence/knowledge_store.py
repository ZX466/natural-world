"""knowledge 表数据访问层 — KnowledgeStore（M3-D4 / B3 实施，裁 10 全采）。

数据域职责（opencode）：把 M3 知识表的**写入门**与**治理级联**收在一处，调用方
（`sim/npc/runtime.py` 架构域、`sim/npc/propagation.py` 传播域）不直接碰 SQL。

两条纪律（codex m3-evidence-chain §6 + m3-preplan §1 R1/R4/X7）：

1. **写入门唯一（X7）**：知识文本 `fact` 必过 `MemoryWritePipeline.scan_fact()`
   ——与记忆写入**同一条判梯**（同一 banned 词表 + hidden 直陈扫描 + 改写/拒写
   阶梯，见 `memory_scan.decide`）。本模块**不提供裸 INSERT 路径**：绕开
   `write_fact()` 直插 ORM 行只能用于低层存储测试，生产写入必经此门。
2. **继承失效、不继承替代（R1/S5）**：源记忆被 supersede → 其派生的 knowledge 行
   置 `invalidated=1`，并沿 `source_knowledge_id`（told 链）向下递归传播。
   **无「替代行」**——knowledge 不存在「B 替代 A」的概念，故用独立失效位而非
   `superseded_by` 链（`evidence.py` 读 `teller_knowledge["invalidated"]` 即此键）。

其余纪律：分支隔离（全 SQL 带 `branch_id`，R4）、幂等（已失效行不改
`invalid_reason`、不重复计数）、同事务（`session=` 入参让调用方把级联与源侧
supersede 串进同一事务，异常整批回滚，无半失效）。

证据锚定：`evidence_seq` 不在本模块自行分配 seq——**复用 M2-D3 `seq_by_index`
投影缝**（`store.append` 在同一事务内分配 seq 后把 event_index→seq 映射交给
投影回调），见 :func:`fill_evidence_seq`，不造第二套 seq 分配器。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sim.core.persistence.models import Knowledge
from sim.llm.memory_scan import MemoryWritePipeline
from sim.npc.hidden import HiddenProfile

#: 单世界线 M1 默认分支；多分支由调用方覆盖（与 SqlMemoryStore 同口径）。
DEFAULT_BRANCH_ID = "main"

#: `knowledge.source` 取值域（与 0005 CHECK `ck_knowledge_source` 同源）。
KNOWLEDGE_SOURCES = frozenset({"witnessed", "told", "inferred"})

#: 级联失效原因（R1/S5 语义常量——**结构化串，不含 LLM 原文/词面**，同 npc_memories）。
REASON_SOURCE_SUPERSEDED = "source_memory_superseded"
REASON_CASCADE = "told_chain_cascade"


class KnowledgeStoreError(RuntimeError):
    """知识表非法访问（不存在 / 形态越界 / 写入门拒收）。"""


@dataclass(frozen=True)
class KnowledgeWriteResult:
    """`write_fact()` 产出（对镜 `WriteResult`，但落 knowledge 表）。

    `fact` 是**实际落库文本**——命中可映射 banned 词时为改写后文本（改写语义
    属写入门，调用方不得绕过它写原文）。
    """

    accepted: bool
    row_id: int | None
    fact: str | None
    reason: str | None = None
    hits: tuple[str, ...] = ()


@dataclass(frozen=True)
class PendingKnowledge:
    """投影缝内待回填 `evidence_seq` 的知识行（witnessed 专用）。

    `row` 由 :func:`staged_witnessed_row` 构造并已挂在调用方的 session 上
    （未 flush）；`event_index` 指向本次 append 事件列表里锚定的
    `npc.hidden_emerge` 行下标。叙事文本（`fact`）由调用方给——数据域只管形状。
    """

    row: Knowledge
    event_index: int


# ---------------------------------------------------------------------------
# 形态校验（应用层 = 提案 §2.2「软约束」；DB CHECK 只覆盖可表达的三条）
# ---------------------------------------------------------------------------


def _check_shape(
    *,
    confidence: float,
    source: str,
    subject_npc_id: str | None,
    subject_attr_id: str | None,
) -> None:
    """写入门前的形态校验：source 取值域 / confidence 值域 / subject 成对。

    另有两条**证据链形态**（proposal §2.2）同样在应用层把关：
    witnessed ⇒ 有 `evidence_seq` 与 `subject_npc_id`；told ⇒ 有
    `source_knowledge_id`（自我披露链根除外，evidence-chain §5）。
    """
    if source not in KNOWLEDGE_SOURCES:
        raise KnowledgeStoreError(f"knowledge.source 越界: {source!r}")
    if not 0.0 <= confidence <= 1.0:
        raise KnowledgeStoreError(f"knowledge.confidence 越界 [0,1]: {confidence!r}")
    if (subject_npc_id is None) != (subject_attr_id is None):
        raise KnowledgeStoreError(
            "subject_npc_id 与 subject_attr_id 必须成对（自身事实两列同 NULL）"
        )
    if source == "witnessed" and subject_npc_id is None:
        raise KnowledgeStoreError("witnessed 知识必须有 subject_npc_id/subject_attr_id")


def _check_evidence_shape(
    *,
    source: str,
    holder_id: str,
    subject_npc_id: str | None,
    evidence_seq: int | None,
    source_knowledge_id: int | None,
) -> None:
    """证据链形态校验（witnessed 锚定事件 / told 锚定上行，链根自我披露除外）。"""
    if source == "witnessed" and evidence_seq is None:
        raise KnowledgeStoreError("witnessed 知识必须有 evidence_seq（emerge 事件 seq）")
    if source == "told" and source_knowledge_id is None and subject_npc_id != holder_id:
        raise KnowledgeStoreError(
            "told 知识必须有 source_knowledge_id（自我披露链根 subject==holder 除外）"
        )


# ---------------------------------------------------------------------------
# 投影缝：evidence_seq 回填（复用 M2-D3 seq_by_index，不造第二套）
# ---------------------------------------------------------------------------


def staged_witnessed_row(
    *,
    holder_id: str,
    fact: str,
    learned_at: int,
    subject_npc_id: str,
    subject_attr_id: str,
    branch_id: str = DEFAULT_BRANCH_ID,
    confidence: float,
    event_index: int,
) -> PendingKnowledge:
    """构造一条**已挂 session、未 flush** 的 witnessed 知识行（`evidence_seq` 待回填）。

    供 `flush_tick(..., extra_projection=...)` 的投影回调内使用：行先入 session，
    再由 :func:`fill_evidence_seq` 用 `seq_by_index` 回填 `evidence_seq`，
    随本次 commit 原子落库（同 `npc_profiles.lod` / `matter_state` 投影纪律）。
    `confidence` 通常取 `evidence.WITNESSED_CONFIDENCE`（0.9）。
    """
    _check_shape(
        confidence=confidence,
        source="witnessed",
        subject_npc_id=subject_npc_id,
        subject_attr_id=subject_attr_id,
    )
    row = Knowledge(
        holder_id=holder_id,
        fact=fact,
        confidence=confidence,
        source="witnessed",
        learned_at=learned_at,
        branch_id=branch_id,
        subject_npc_id=subject_npc_id,
        subject_attr_id=subject_attr_id,
        evidence_seq=None,
        source_knowledge_id=None,
        source_memory=None,
        invalidated=False,
        invalid_reason=None,
    )
    return PendingKnowledge(row=row, event_index=event_index)


def fill_evidence_seq(
    session: AsyncSession,
    seq_by_index: dict[int, int],
    pending: Sequence[PendingKnowledge],
) -> int:
    """用 M2-D3 `seq_by_index` 映射回填 `evidence_seq`（**唯一真相源**）。

    `seq_by_index` 由 `store.append` 在同一事务内分配 seq 后交给投影回调——
    本函数**不读 max(seq)、不自行分配**，故不会与 events.seq 分叉（那会让
    witnessed 知识锚到不存在的 seq）。返回回填行数（未在本次批次的下标跳过）。
    """
    filled = 0
    for item in pending:
        seq = seq_by_index.get(item.event_index)
        if seq is None:
            continue
        item.row.evidence_seq = seq
        filled += 1
    return filled


# ---------------------------------------------------------------------------
# KnowledgeStore
# ---------------------------------------------------------------------------


class KnowledgeStore:
    """knowledge 表读写 + 治理级联（分支隔离 / 幂等 / 可同事务）。

    构造用 `async_sessionmaker`（与 `SqlEventStore` / `NpcStore` 同缝）；``session=``
    入参让调用方把级联并进自己的事务（裁 10「supersede 事务内级联」）。
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        branch_id: str = DEFAULT_BRANCH_ID,
    ) -> None:
        self._session_factory = session_factory
        self._branch_id = branch_id

    @property
    def branch_id(self) -> str:
        return self._branch_id

    # ------------------------------------------------------------------
    # 写入门（X7：fact 必过写入门）
    # ------------------------------------------------------------------

    async def write_fact(
        self,
        pipeline: MemoryWritePipeline,
        *,
        holder_id: str,
        fact: str,
        confidence: float,
        source: str,
        learned_at: int,
        subject_npc_id: str | None = None,
        subject_attr_id: str | None = None,
        evidence_seq: int | None = None,
        source_knowledge_id: int | None = None,
        source_memory: str | None = None,
        hidden: HiddenProfile | None = None,
        triggered: frozenset[str] = frozenset(),
        session: AsyncSession | None = None,
    ) -> KnowledgeWriteResult:
        """知识落库**唯一入口**：先过写入门（`pipeline.scan_fact`），再 INSERT。

        写入门拒收（banned 词面不可机械替换 / 未触发隐藏属性直陈）→ 返回
        `accepted=False` 且**不落库**（同记忆 S4「拒写不落库」纪律）。改写放行时
        落 `decision.content`（清洗后文本），不是原文。

        `source_memory` 记派生源记忆 entry_id——R1 级联起点。`evidence_seq` 由
        witnessed 路径给（投影缝经 `fill_evidence_seq` 回填，或调用方直给）。
        """
        # 形态先校验（信任边界，廉价无副作用），再过写入门——免为必被拒的行做扫描。
        _check_shape(
            confidence=confidence,
            source=source,
            subject_npc_id=subject_npc_id,
            subject_attr_id=subject_attr_id,
        )
        _check_evidence_shape(
            source=source,
            holder_id=holder_id,
            subject_npc_id=subject_npc_id,
            evidence_seq=evidence_seq,
            source_knowledge_id=source_knowledge_id,
        )
        decision = pipeline.scan_fact(fact, hidden=hidden, triggered=triggered)
        if not decision.admitted:
            return KnowledgeWriteResult(
                accepted=False,
                row_id=None,
                fact=None,
                reason=decision.reason,
                hits=decision.hits,
            )
        row = Knowledge(
            holder_id=holder_id,
            fact=decision.content,
            confidence=confidence,
            source=source,
            learned_at=learned_at,
            branch_id=self._branch_id,
            subject_npc_id=subject_npc_id,
            subject_attr_id=subject_attr_id,
            evidence_seq=evidence_seq,
            source_knowledge_id=source_knowledge_id,
            source_memory=source_memory,
            invalidated=False,
            invalid_reason=None,
        )

        if session is not None:
            # 调用方拥有事务：只 stage，不 commit（与 supersede 同一事务）。
            return await self._stage(session, row, decision.content, decision.hits)
        async with self._session_factory() as own:
            result = await self._stage(own, row, decision.content, decision.hits)
            await own.commit()
            return result

    async def _stage(
        self,
        session: AsyncSession,
        row: Knowledge,
        fact: str,
        hits: tuple[str, ...],
    ) -> KnowledgeWriteResult:
        session.add(row)
        await session.flush()
        return KnowledgeWriteResult(accepted=True, row_id=row.id, fact=fact, hits=hits)

    # ------------------------------------------------------------------
    # 读（分支隔离 + 可见视图过滤治理位）
    # ------------------------------------------------------------------

    async def get(self, row_id: int, *, session: AsyncSession | None = None) -> Knowledge | None:
        """按 id 取一行（同分支内；跨分支 id 视作不存在，R4）。"""
        if session is not None:
            return await self._get(session, row_id)
        async with self._session_factory() as own:
            return await self._get(own, row_id)

    async def _get(self, session: AsyncSession, row_id: int) -> Knowledge | None:
        result = await session.execute(
            select(Knowledge).where(
                Knowledge.id == row_id,
                Knowledge.branch_id == self._branch_id,
            )
        )
        return result.scalar_one_or_none()

    async def iter_valid(
        self, holder_id: str, *, session: AsyncSession | None = None
    ) -> list[Knowledge]:
        """持有者的**有效**知识（`invalidated=0`，B1 双列口径同语义）。"""
        stmt = (
            select(Knowledge)
            .where(
                Knowledge.branch_id == self._branch_id,
                Knowledge.holder_id == holder_id,
                Knowledge.invalidated.is_(False),
            )
            .order_by(Knowledge.id)
        )
        if session is not None:
            return list((await session.execute(stmt)).scalars().all())
        async with self._session_factory() as own:
            return list((await own.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------
    # 治理级联（R1/S5：继承失效、不继承替代）
    # ------------------------------------------------------------------

    async def invalidate_by_source(
        self,
        entry_id: str,
        reason: str = REASON_SOURCE_SUPERSEDED,
        *,
        session: AsyncSession | None = None,
    ) -> int:
        """按派生源记忆 `entry_id` 失效其全部派生知识行，并沿 told 链向下传播。

        R1 级联起点（`knowledge.source_memory` = 源记忆 entry_id）。返回本次
        **新置失效**的行数（0 = 无派生 / 已失效过，幂等）。与源记忆 supersede
        同事务——传 `session=` 即并入调用方事务。
        """
        return await self._invalidate(
            lambda s: self._seeds_by_source(s, entry_id), reason, session=session
        )

    async def supersede_source_memory(
        self,
        entry_id: str,
        reason: str = REASON_SOURCE_SUPERSEDED,
        *,
        session: AsyncSession | None = None,
    ) -> int:
        """`invalidate_by_source` 的语义别名（源记忆被 supersede 的显式名）。"""
        return await self.invalidate_by_source(entry_id, reason, session=session)

    async def invalidate_by_row(
        self,
        row_id: int,
        reason: str = REASON_CASCADE,
        *,
        session: AsyncSession | None = None,
    ) -> int:
        """直接失效一条知识行 + 沿 told 链向下递归（级联内层/单点皆用此口）。"""
        return await self._invalidate(
            lambda s: self._seed_single(s, row_id), reason, session=session
        )

    async def _seeds_by_source(self, session: AsyncSession, entry_id: str) -> list[int]:
        result = await session.execute(
            select(Knowledge.id).where(
                Knowledge.branch_id == self._branch_id,
                Knowledge.source_memory == entry_id,
            )
        )
        return list(result.scalars().all())

    async def _seed_single(self, session: AsyncSession, row_id: int) -> list[int]:
        """单行种子（跨分支 id 视作不存在——级联从空种子起步，返回 0）。"""
        result = await session.execute(
            select(Knowledge.id).where(
                Knowledge.id == row_id,
                Knowledge.branch_id == self._branch_id,
            )
        )
        return list(result.scalars().all())

    async def _invalidate(
        self,
        seeds_fn,
        reason: str,
        *,
        session: AsyncSession | None = None,
    ) -> int:
        if session is not None:
            return await self._cascade(session, seeds_fn, reason)
        async with self._session_factory() as own:
            count = await self._cascade(own, seeds_fn, reason)
            await own.commit()
            return count

    async def _cascade(self, session: AsyncSession, seeds_fn, reason: str) -> int:
        """沿 told 链（`source_knowledge_id`）广度递归置失效，幂等 + 分支隔离。

        - 幂等：已失效行不重写 `invalid_reason`、不重复计数；但仍**向下遍历**
          （其下游可能尚未失效——上一轮级联只覆盖了当时存在的子行）。
        - 分支隔离：种子、子行与逐行状态查询都带 `branch_id`（R4）；跨分支 id
          视作不存在。
        - 无替代行：只置 `invalidated=1` + `invalid_reason`，不写任何替代指针。
        """
        frontier = list(dict.fromkeys(await seeds_fn(session)))
        visited: set[int] = set()
        count = 0
        while frontier:
            node = frontier.pop()
            if node in visited:
                continue
            visited.add(node)
            state = await session.execute(
                select(Knowledge.invalidated).where(
                    Knowledge.id == node,
                    Knowledge.branch_id == self._branch_id,
                )
            )
            was_valid = state.scalar_one_or_none()
            if was_valid is None:
                continue
            if not was_valid:
                await session.execute(
                    update(Knowledge)
                    .where(
                        Knowledge.id == node,
                        Knowledge.branch_id == self._branch_id,
                        Knowledge.invalidated.is_(False),
                    )
                    .values(invalidated=True, invalid_reason=reason)
                )
                count += 1
            # 已失效则幂等跳过（不覆写 invalid_reason、不计数），但继续向下走。
            children = await session.execute(
                select(Knowledge.id).where(
                    Knowledge.branch_id == self._branch_id,
                    Knowledge.source_knowledge_id == node,
                )
            )
            frontier.extend(children.scalars().all())
        return count
