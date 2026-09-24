"""D1 不成文规矩 v0 — T5 之前的钉子（m3-plan 批次 D1，RED 先行）。

规矩 = 知识表（KnowledgeStore.iter_valid）→ 世界内语言行为约束的最小通路：
- 筛选：他人属性知识（subject_npc_id 非 NULL 且 != holder）按 confidence 取 top-N；
- 措辞：世界内语言、第一人称、零数值（规则文本「不出现具体数值」对齐 §7）；
- 挂载：assembler [规矩] 段在 messages[1] 内（[记忆] 之后 [处境] 之前），
  不动 messages[0] 身份锚（前缀缓存分界不变，C06-④ 契约）。
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.knowledge_store import KnowledgeStore
from sim.llm.memory_scan import MemoryWritePipeline
from sim.llm.prompts.assembler import (
    InputSlice,
    MemorySlice,
    NormSlice,
    PlanSlice,
    SituationSlice,
    assemble_prompt,
)
from sim.llm.prompts.identity import IdentityAnchor
from sim.npc.norms import MAX_NORMS, norms_text_of


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessions(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture()
def pipeline() -> MemoryWritePipeline:
    return MemoryWritePipeline()


class TestNormsSelection:
    """知识行 → 规矩条目的筛选语义。"""

    @pytest.mark.t1
    async def test_subject_knowledge_becomes_norm(self, sessions, pipeline) -> None:
        store = KnowledgeStore(sessions)
        await store.write_fact(
            pipeline,
            holder_id="npc-a",
            fact="别人家的事不能随便说破",
            confidence=0.9,
            source="witnessed",
            learned_at=0,
            subject_npc_id="npc-b",
            subject_attr_id="h1",
            evidence_seq=1,
        )
        rows = await store.iter_valid("npc-a")
        text = norms_text_of(rows, holder_id="npc-a")
        assert text != ""
        assert "说破" in text

    @pytest.mark.t1
    async def test_self_knowledge_excluded(self, sessions, pipeline) -> None:
        store = KnowledgeStore(sessions)
        await store.write_fact(
            pipeline,
            holder_id="npc-a",
            fact="自己心里的事不必逢人便讲",
            confidence=0.9,
            source="witnessed",
            learned_at=0,
            subject_npc_id="npc-a",
            subject_attr_id="h1",
            evidence_seq=1,
        )
        rows = await store.iter_valid("npc-a")
        assert norms_text_of(rows, holder_id="npc-a") == ""

    @pytest.mark.t1
    async def test_top_n_cap(self, sessions, pipeline) -> None:
        store = KnowledgeStore(sessions)
        for i in range(MAX_NORMS + 3):
            await store.write_fact(
                pipeline,
                holder_id="npc-a",
                fact=f"第{i}条：别在人前揭人短处",
                confidence=0.5 + i * 0.01,
                source="witnessed",
                learned_at=0,
                subject_npc_id="npc-b",
                subject_attr_id=f"h{i}",
                evidence_seq=i + 1,
            )
        rows = await store.iter_valid("npc-a")
        text = norms_text_of(rows, holder_id="npc-a")
        assert text.count("\n") <= MAX_NORMS - 1  # 行数 ≤ MAX_NORMS

    @pytest.mark.t1
    async def test_invalidated_excluded(self, sessions, pipeline) -> None:
        store = KnowledgeStore(sessions)
        await store.write_fact(
            pipeline,
            holder_id="npc-a",
            fact="别提他家那桩旧事",
            confidence=0.9,
            source="witnessed",
            learned_at=0,
            subject_npc_id="npc-b",
            subject_attr_id="h1",
            evidence_seq=1,
        )
        await store.invalidate_by_row(1)
        rows = await store.iter_valid("npc-a")
        assert norms_text_of(rows, holder_id="npc-a") == ""


class TestNormsWording:
    """世界内语言铁律：零数值、第一人称、无戏外词。"""

    @pytest.mark.t1
    async def test_confidence_number_never_in_text(self, sessions, pipeline) -> None:
        store = KnowledgeStore(sessions)
        await store.write_fact(
            pipeline,
            holder_id="npc-a",
            fact="他的家底别对外人提",
            confidence=0.87,
            source="witnessed",
            learned_at=0,
            subject_npc_id="npc-b",
            subject_attr_id="h1",
            evidence_seq=1,
        )
        rows = await store.iter_valid("npc-a")
        text = norms_text_of(rows, holder_id="npc-a")
        assert "0.87" not in text
        assert "0.9" not in text

    @pytest.mark.t1
    async def test_no_meta_words(self, sessions, pipeline) -> None:
        store = KnowledgeStore(sessions)
        await store.write_fact(
            pipeline,
            holder_id="npc-a",
            fact="他的伤疤来历别追问",
            confidence=0.9,
            source="witnessed",
            learned_at=0,
            subject_npc_id="npc-b",
            subject_attr_id="h1",
            evidence_seq=1,
        )
        rows = await store.iter_valid("npc-a")
        text = norms_text_of(rows, holder_id="npc-a")
        from sim.llm.prompts.banned_words import BANNED_WORDS

        low = text.lower()
        for w in BANNED_WORDS:
            assert w.lower() not in low


class TestAssemblerNormSection:
    """[规矩] 段挂载：messages[1] 内、[记忆] 后；messages[0] 恒定。"""

    def _anchor(self) -> IdentityAnchor:
        return IdentityAnchor(
            entity_id="chenmo",
            self_narrative="我叫陈默，在临河镇讨生活，跑腿送信换几个铜板。",
            persona_summary="性子沉，不爱说话，但认死理。对陌生人多留个心眼。",
            long_term_goal="攒够钱，把西街那间铺子盘下来，往后有个落脚的营生。",
        )

    @pytest.mark.t1
    def test_norms_section_rendered(self) -> None:
        norm = NormSlice(entries=("他的家底别对外人提",))
        prompt = assemble_prompt(
            anchor=self._anchor(),
            memory=MemorySlice(),
            situation=SituationSlice(),
            plan=PlanSlice(),
            user_input=InputSlice(thought="去集市看看"),
            norms=norm,
            chain_id="t",
        )
        body = prompt.messages[1]["content"]
        assert "规矩" in body
        assert "他的家底别对外人提" in body
        # 段序：[规矩] 在 [处境] 之前、[记忆] 之后
        if "你还记得的事" in body:
            assert body.index("你还记得的事") < body.index("规矩")
        assert body.index("规矩") < body.index("四周") if "四周" in body else True

    @pytest.mark.t1
    def test_empty_norms_no_section(self) -> None:
        prompt = assemble_prompt(
            anchor=self._anchor(),
            memory=MemorySlice(),
            situation=SituationSlice(),
            plan=PlanSlice(),
            user_input=InputSlice(thought="去集市看看"),
            norms=NormSlice(),
            chain_id="t",
        )
        assert "规矩" not in prompt.messages[1]["content"]

    @pytest.mark.t1
    def test_anchor_fingerprint_unchanged_by_norms(self) -> None:
        p1 = assemble_prompt(
            anchor=self._anchor(),
            memory=MemorySlice(),
            situation=SituationSlice(),
            plan=PlanSlice(),
            user_input=InputSlice(thought="去集市"),
            norms=NormSlice(),
            chain_id="t",
        )
        p2 = assemble_prompt(
            anchor=self._anchor(),
            memory=MemorySlice(),
            situation=SituationSlice(),
            plan=PlanSlice(),
            user_input=InputSlice(thought="去集市"),
            norms=NormSlice(entries=("别揭人短",)),
            chain_id="t",
        )
        assert p1.first_message_fingerprint() == p2.first_message_fingerprint()
