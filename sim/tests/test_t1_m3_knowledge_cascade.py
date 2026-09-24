"""T1 钉子 — R1 知识级联失效闭环（M3-D4 / B3 实施验收，codex M3-S5 待验收）。

钉的是 **codex docs/security/m3-evidence-chain.md §8-7** 那一条端到端契约：

    源记忆 supersede → 派生 knowledge 行失效 → 下游 told 行级联失效 → told 链断拒收

配套红线（同预审 7 要点）：

1. **继承失效、不继承替代**（§6 终裁）：只置 `invalidated=1` + `invalid_reason`，
   knowledge 表内**不存在任何替代指针**（无 `superseded_by` 列）——codex 预审①
   「无替代行语义，别造 replacement 列」；
2. **链断拒收闭环**（§8-3）：teller 行失效后 `judge_third_party_hidden` 必须
   `admitted=False` / reason=`told_teller_knowledge_invalidated`——级联不是只改库，
   是真把 told 传播链闭上；
3. **幂等**：重复失效不重复计数、不覆写首次 `invalid_reason`（审计留首次原因）；
4. **分支隔离**（R4）：级联不跨 `branch_id`（他分支同 `id` 空间不受影响）；
5. **写入门不被新列绕过**（X7）：`fact` 命中 banned 词面 / 未触发隐藏属性直陈
   → 拒收不落库（知识表不是扫描面的旁路）；
6. **`evidence_seq` 复用 `seq_by_index`**：witnessed 行的 `evidence_seq` 必等于
   锚定 `npc.hidden_emerge` 事件被持久层实际分配的 seq（不造第二套 seq 分配器）。

CI：`test_t1_*` 前缀随 `-m "not bench"` 全量跑；本文件由 opencode M3-D4 实施转绿。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.knowledge_store import (
    REASON_CASCADE,
    REASON_SOURCE_SUPERSEDED,
    KnowledgeStore,
    KnowledgeStoreError,
    fill_evidence_seq,
    staged_witnessed_row,
)
from sim.core.persistence.models import Knowledge
from sim.llm.memory_scan import MemoryWritePipeline
from sim.npc.evidence import WITNESSED_CONFIDENCE, judge_third_party_hidden
from sim.npc.hidden import HiddenAttribute, HiddenProfile

# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessions(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def pipeline():
    return MemoryWritePipeline()


def _hidden_profile() -> HiddenProfile:
    """一个未触发即直陈即拒的隐藏属性（descriptors = 直陈词面）。"""
    return HiddenProfile(
        npc_id="npc-1",
        attributes=(
            HiddenAttribute(
                id="h1",
                category="disease",
                label="咳疾",
                descriptors=("痨病",),
                triggers=("雨夜",),
            ),
        ),
    )


async def _write_single(
    store: KnowledgeStore, pipeline: MemoryWritePipeline, *, source_memory: str
) -> int:
    """单条 witnessed 行挂源记忆（无下游）——隔离 level-1 失效语义。"""
    written = await store.write_fact(
        pipeline,
        holder_id="npc-a",
        fact="npc-c 咳疾缠身",
        confidence=WITNESSED_CONFIDENCE,
        source="witnessed",
        learned_at=10,
        subject_npc_id="npc-c",
        subject_attr_id="h1",
        evidence_seq=7,
        source_memory=source_memory,
    )
    assert written.accepted
    assert written.row_id is not None
    return written.row_id


async def _seed_chain(
    store: KnowledgeStore, pipeline: MemoryWritePipeline, *, source_memory: str
) -> dict[str, int]:
    """A（witnessed，source_memory 挂源记忆）→ B（told 自 A）→ C（told 自 B）。

    三行构成 told 传播链；B/C 的 `source_knowledge_id` 逐跳指回上一行。
    """
    a = await store.write_fact(
        pipeline,
        holder_id="npc-a",
        fact="npc-c 咳疾缠身",
        confidence=WITNESSED_CONFIDENCE,
        source="witnessed",
        learned_at=10,
        subject_npc_id="npc-c",
        subject_attr_id="h1",
        evidence_seq=7,
        source_memory=source_memory,
    )
    b = await store.write_fact(
        pipeline,
        holder_id="npc-b",
        fact="npc-c 咳疾缠身",
        confidence=0.54,
        source="told",
        learned_at=11,
        subject_npc_id="npc-c",
        subject_attr_id="h1",
        source_knowledge_id=a.row_id,
    )
    c = await store.write_fact(
        pipeline,
        holder_id="npc-d",
        fact="npc-c 咳疾缠身",
        confidence=0.32,
        source="told",
        learned_at=12,
        subject_npc_id="npc-c",
        subject_attr_id="h1",
        source_knowledge_id=b.row_id,
    )
    assert a.accepted and b.accepted and c.accepted
    assert a.row_id is not None and b.row_id is not None and c.row_id is not None
    return {"a": a.row_id, "b": b.row_id, "c": c.row_id}


# ---------------------------------------------------------------------------
# 0. schema 形状（0005 迁移）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestKnowledgeGovernanceSchema:
    async def test_seven_governance_columns_exist(self, sessions) -> None:
        """0005：证据链四列 + 治理三列齐备。"""
        async with sessions() as session:
            result = await session.execute(text("PRAGMA table_info(knowledge)"))
            cols = {row[1] for row in result.all()}
        assert {
            "subject_npc_id",
            "subject_attr_id",
            "evidence_seq",
            "source_knowledge_id",
            "source_memory",
            "invalidated",
            "invalid_reason",
        } <= cols

    async def test_three_indexes_exist(self, sessions) -> None:
        """0005：级联起点 / told 链递归 / 主体+属性 三索引。"""
        async with sessions() as session:
            result = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='knowledge'")
            )
            names = {row[0] for row in result.all()}
        assert {
            "idx_knowledge_source_memory",
            "idx_knowledge_source_kid",
            "idx_knowledge_subject",
        } <= names

    async def test_invalidated_defaults_false(self, sessions, pipeline) -> None:
        """新行 `invalidated=0`（0005 server_default，add_column 无需回填）。"""
        store = KnowledgeStore(sessions)
        written = await store.write_fact(
            pipeline,
            holder_id="npc-1",
            fact="村东有口枯井",
            confidence=0.5,
            source="told",
            learned_at=10,
            source_knowledge_id=None,
            subject_npc_id="npc-1",
            subject_attr_id="a1",
        )
        assert written.accepted
        row = await store.get(written.row_id)  # type: ignore[arg-type]
        assert row is not None
        assert row.invalidated is False
        assert row.invalid_reason is None


# ---------------------------------------------------------------------------
# 1. R1 级联端到端 + 链断拒收闭环（钉子主条，evidence-chain §8-7）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestR1CascadeEndToEnd:
    async def test_source_supersede_invalidates_derived_row(self, sessions, pipeline) -> None:
        """源记忆 supersede → 其派生行失效（无下游时 count=1，隔离 level-1）。"""
        store = KnowledgeStore(sessions)
        row_id = await _write_single(store, pipeline, source_memory="mem-1")

        count = await store.supersede_source_memory("mem-1", REASON_SOURCE_SUPERSEDED)
        assert count == 1

        row = await store.get(row_id)
        assert row is not None
        assert row.invalidated is True
        assert row.invalid_reason == REASON_SOURCE_SUPERSEDED

    async def test_cascade_propagates_down_told_chain(self, sessions, pipeline) -> None:
        """R1 全链：A 失效沿 `source_knowledge_id` 递归 → B、C 一起失效。"""
        store = KnowledgeStore(sessions)
        ids = await _seed_chain(store, pipeline, source_memory="mem-1")

        count = await store.invalidate_by_source("mem-1", REASON_SOURCE_SUPERSEDED)
        assert count == 3  # A + B + C

        for key in ("a", "b", "c"):
            row = await store.get(ids[key])
            assert row is not None
            assert row.invalidated is True, f"row {key} 未随级联失效"

    async def test_cascade_is_inherit_only_no_replacement(self, sessions, pipeline) -> None:
        """预审①：只失效、不替代——表内无替代指针列，fact 内容零改动。"""
        store = KnowledgeStore(sessions)
        ids = await _seed_chain(store, pipeline, source_memory="mem-1")
        before = await store.get(ids["a"])
        assert before is not None

        await store.invalidate_by_source("mem-1", REASON_SOURCE_SUPERSEDED)

        after = await store.get(ids["a"])
        assert after is not None
        assert after.fact == before.fact  # 只动治理列，永不改 fact
        assert after.source_knowledge_id == before.source_knowledge_id
        async with sessions() as session:
            cols = {
                row[1]
                for row in (await session.execute(text("PRAGMA table_info(knowledge)"))).all()
            }
        assert "superseded_by" not in cols  # 禁止造 replacement 列

    async def test_told_chain_broken_rejected_after_cascade(self, sessions, pipeline) -> None:
        """§8-3 链断拒收闭环：teller 行失效 → 判定拒收（级联真闭上传播链）。"""
        store = KnowledgeStore(sessions)
        ids = await _seed_chain(store, pipeline, source_memory="mem-1")
        await store.invalidate_by_source("mem-1", REASON_SOURCE_SUPERSEDED)

        row_a = await store.get(ids["a"])
        assert row_a is not None
        verdict = judge_third_party_hidden(
            source="told",
            holder_id="npc-b",
            subject_id="npc-c",
            attr_id="h1",
            events=[],
            teller_knowledge={
                "invalidated": row_a.invalidated,
                "subject_npc_id": row_a.subject_npc_id,
                "subject_attr_id": row_a.subject_attr_id,
                "confidence": row_a.confidence,
            },
        )
        assert verdict.admitted is False
        assert verdict.reason == "told_teller_knowledge_invalidated"

    async def test_iter_valid_hides_cascaded_rows(self, sessions, pipeline) -> None:
        """可见视图：级联后派生行不再出现在 `iter_valid`（B1 双列口径同语义）。"""
        store = KnowledgeStore(sessions)
        await _seed_chain(store, pipeline, source_memory="mem-1")
        assert len(await store.iter_valid("npc-b")) == 1

        await store.invalidate_by_source("mem-1", REASON_SOURCE_SUPERSEDED)
        assert await store.iter_valid("npc-b") == []


# ---------------------------------------------------------------------------
# 2. 幂等 / 分支隔离 / 同事务
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestCascadeSafety:
    async def test_repeated_invalidate_is_idempotent(self, sessions, pipeline) -> None:
        """幂等：重复失效返回 0，且不覆写首次 `invalid_reason`。"""
        store = KnowledgeStore(sessions)
        ids = await _seed_chain(store, pipeline, source_memory="mem-1")

        first = await store.invalidate_by_source("mem-1", REASON_SOURCE_SUPERSEDED)
        second = await store.invalidate_by_source("mem-1", "some_other_reason")
        third = await store.invalidate_by_row(ids["a"], "yet_another")

        assert first == 3
        assert second == 0
        assert third == 0
        row = await store.get(ids["a"])
        assert row is not None
        assert row.invalid_reason == REASON_SOURCE_SUPERSEDED  # 首次原因留存

    async def test_invalidate_row_propagates_downward(self, sessions, pipeline) -> None:
        """单点失效 `invalidate_by_row` 也向下递归（级联内层同一口径）。"""
        store = KnowledgeStore(sessions)
        ids = await _seed_chain(store, pipeline, source_memory="mem-1")

        count = await store.invalidate_by_row(ids["b"], REASON_CASCADE)
        assert count == 2  # B + C（A 不受影响——失效向下传播，不向上）

        row_a = await store.get(ids["a"])
        assert row_a is not None
        assert row_a.invalidated is False

    async def test_cascade_branch_isolated(self, sessions, pipeline) -> None:
        """R4：main 的级联不碰 branch-b 的同 id 空间。"""
        main = KnowledgeStore(sessions, branch_id="main")
        other = KnowledgeStore(sessions, branch_id="branch-b")

        w_main = await main.write_fact(
            pipeline,
            holder_id="npc-a",
            fact="村东有口枯井",
            confidence=0.9,
            source="witnessed",
            learned_at=10,
            subject_npc_id="npc-c",
            subject_attr_id="h1",
            evidence_seq=1,
            source_memory="mem-1",
        )
        w_other = await other.write_fact(
            pipeline,
            holder_id="npc-a",
            fact="村东有口枯井",
            confidence=0.9,
            source="witnessed",
            learned_at=10,
            subject_npc_id="npc-c",
            subject_attr_id="h1",
            evidence_seq=1,
            source_memory="mem-1",
        )
        assert w_main.accepted and w_other.accepted

        assert await main.invalidate_by_source("mem-1", REASON_SOURCE_SUPERSEDED) == 1
        assert await other.invalidate_by_source("mem-1", REASON_SOURCE_SUPERSEDED) == 1

        # main 的级联没有把 branch-b 的行带走（各自独立失效）
        row_other = await other.get(w_other.row_id)  # type: ignore[arg-type]
        assert row_other is not None
        assert row_other.branch_id == "branch-b"

    async def test_invalidate_by_row_unknown_id_returns_zero(self, sessions) -> None:
        """未知 / 跨分支 id 视作不存在，返回 0（不抛、不误伤）。"""
        store = KnowledgeStore(sessions)
        assert await store.invalidate_by_row(99999, REASON_CASCADE) == 0

    async def test_invalidate_rolls_back_with_caller_transaction(self, sessions, pipeline) -> None:
        """同事务：级联并入调用方事务 → 调用方回滚则失效一并回滚（无半失效）。"""
        store = KnowledgeStore(sessions)
        written = await store.write_fact(
            pipeline,
            holder_id="npc-a",
            fact="村东有口枯井",
            confidence=0.9,
            source="witnessed",
            learned_at=10,
            subject_npc_id="npc-c",
            subject_attr_id="h1",
            evidence_seq=3,
            source_memory="mem-1",
        )
        assert written.accepted

        async with sessions() as session:
            count = await store.invalidate_by_source(
                "mem-1", REASON_SOURCE_SUPERSEDED, session=session
            )
            assert count == 1
            await session.rollback()

        row = await store.get(written.row_id)  # type: ignore[arg-type]
        assert row is not None
        assert row.invalidated is False  # 回滚后未失效——无半写


# ---------------------------------------------------------------------------
# 3. X7：知识写入过写入门（新列不是扫描面的旁路）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestKnowledgeWriteGate:
    async def test_banned_fact_rejected_not_persisted(self, sessions, pipeline) -> None:
        """X7：banned 词面命中（无映射，机械替换救不回）→ 拒收且**不落库**。"""
        store = KnowledgeStore(sessions)
        result = await store.write_fact(
            pipeline,
            holder_id="npc-1",
            fact="他在用 prompt 记事",
            confidence=0.9,
            source="witnessed",
            learned_at=10,
            subject_npc_id="npc-2",
            subject_attr_id="h1",
            evidence_seq=1,
        )
        assert result.accepted is False
        assert result.reason == "unrewritable"
        assert await store.iter_valid("npc-1") == []

    async def test_rewritable_banned_fact_stores_cleaned_text(self, sessions, pipeline) -> None:
        """可机械映射的 banned 词 → 放行，但落**清洗后**文本（改写语义不被绕过）。"""
        store = KnowledgeStore(sessions)
        result = await store.write_fact(
            pipeline,
            holder_id="npc-1",
            fact="村口那场游戏很热闹",
            confidence=0.9,
            source="witnessed",
            learned_at=10,
            subject_npc_id="npc-2",
            subject_attr_id="h1",
            evidence_seq=1,
        )
        assert result.accepted is True
        assert result.fact is not None
        assert "游戏" not in result.fact
        row = await store.get(result.row_id)  # type: ignore[arg-type]
        assert row is not None
        assert row.fact == result.fact

    async def test_hidden_direct_statement_rejected(self, sessions, pipeline) -> None:
        """X7：未触发隐藏属性直陈 → 拒收不落库（同记忆 M2-S1 口径）。"""
        store = KnowledgeStore(sessions)
        result = await store.write_fact(
            pipeline,
            holder_id="npc-1",
            fact="npc-2 身患痨病",
            confidence=0.9,
            source="witnessed",
            learned_at=10,
            subject_npc_id="npc-2",
            subject_attr_id="h1",
            evidence_seq=1,
            hidden=_hidden_profile(),
        )
        assert result.accepted is False
        assert result.reason == "hidden_attribute_leak"
        assert await store.iter_valid("npc-1") == []

    async def test_triggered_hidden_fact_admitted(self, sessions, pipeline) -> None:
        """已触发的隐藏属性可直陈（触发面恢复 → 放行，门不误伤）。"""
        store = KnowledgeStore(sessions)
        result = await store.write_fact(
            pipeline,
            holder_id="npc-1",
            fact="npc-2 身患痨病",
            confidence=0.9,
            source="witnessed",
            learned_at=10,
            subject_npc_id="npc-2",
            subject_attr_id="h1",
            evidence_seq=1,
            hidden=_hidden_profile(),
            triggered=frozenset({"h1"}),
        )
        assert result.accepted is True

    async def test_shape_violation_rejected(self, sessions, pipeline) -> None:
        """形态越界（confidence / source / subject 成对）→ 拒，不落半行。"""
        store = KnowledgeStore(sessions)
        with pytest.raises(KnowledgeStoreError):
            await store.write_fact(
                pipeline,
                holder_id="npc-1",
                fact="村东有口枯井",
                confidence=1.5,
                source="told",
                learned_at=10,
                subject_npc_id="npc-1",
                subject_attr_id="a1",
            )
        with pytest.raises(KnowledgeStoreError):
            await store.write_fact(
                pipeline,
                holder_id="npc-1",
                fact="村东有口枯井",
                confidence=0.5,
                source="gossip",
                learned_at=10,
                subject_npc_id="npc-1",
                subject_attr_id="a1",
            )
        with pytest.raises(KnowledgeStoreError):
            # subject 两列不成对（自身事实须两列同 NULL）
            await store.write_fact(
                pipeline,
                holder_id="npc-1",
                fact="村东有口枯井",
                confidence=0.5,
                source="told",
                learned_at=10,
                subject_npc_id="npc-2",
            )


# ---------------------------------------------------------------------------
# 4. evidence_seq 复用 seq_by_index（不造第二套 seq 分配器）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestEvidenceSeqBackfill:
    async def test_evidence_seq_equals_persisted_event_seq(self, sessions) -> None:
        """witnessed 行 `evidence_seq` = emerge 事件**持久层实际分配**的 seq。

        走真实 `NpcStore.flush_tick(extra_projection=...)` 投影缝：seq 由
        `store.append` 分配，本模块只按 `seq_by_index` 回填——不造第二套分配器。
        """
        from sim.core.events import hidden_emerge_event
        from sim.core.persistence.npc_store import NpcStore
        from sim.core.persistence.store import SqlEventStore

        npcs = NpcStore(SqlEventStore(sessions))
        staged: list = []

        async def projection(session, seq_by_index, batch) -> None:
            pending = [
                staged_witnessed_row(
                    holder_id=holder_id,
                    fact="npc-c 咳疾缠身",
                    learned_at=ev.tick,
                    subject_npc_id="npc-c",
                    subject_attr_id=attr_id,
                    confidence=WITNESSED_CONFIDENCE,
                    event_index=idx,
                )
                for idx, ev in enumerate(batch)
                if ev.event_type.value == "npc.hidden_emerge"
                for holder_id in ev.witnesses
                for attr_id in ev.payload["attr_ids"]
            ]
            for item in pending:
                session.add(item.row)
                staged.append(item)
            assert fill_evidence_seq(session, seq_by_index, pending) == len(pending)

        await npcs.flush_tick(
            [hidden_emerge_event(10, "npc-c", ("h1",), witnesses=["npc-a"])],
            extra_projection=projection,
        )

        rows = (await sessions().execute(select(Knowledge))).scalars().all()
        assert len(rows) == 1
        assert rows[0].evidence_seq == 1  # 首事件的实际 seq
        assert rows[0].source == "witnessed"
        assert rows[0].subject_npc_id == "npc-c"
        assert rows[0].subject_attr_id == "h1"

    async def test_fill_skips_event_index_outside_batch(self, sessions) -> None:
        """下标不在本批次（seq_by_index 无此键）→ 跳过而非编造 seq。"""
        async with sessions() as session:
            pending = [
                staged_witnessed_row(
                    holder_id="npc-a",
                    fact="npc-c 咳疾缠身",
                    learned_at=10,
                    subject_npc_id="npc-c",
                    subject_attr_id="h1",
                    confidence=WITNESSED_CONFIDENCE,
                    event_index=99,
                )
            ]
            assert fill_evidence_seq(session, {1: 1}, pending) == 0
            assert pending[0].row.evidence_seq is None
