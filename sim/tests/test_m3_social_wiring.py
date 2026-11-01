from sim.npc.evidence import witnesses_of_entity_emerge
from sim.perception.frame import Channel, Observation, PerceptionFrame
from sim.perception.senses import rtoken_of


def test_entity_witnesses_map_tokens_and_record_previous_frame_tick():
    frames = {
        rtoken_of("listener"): PerceptionFrame(
            observer=rtoken_of("listener"),
            tick=9,
            observations=(
                Observation(
                    channel=Channel.VISION,
                    subject=rtoken_of("subject"),
                    description="走来",
                    strength=1,
                ),
            ),
        )
    }
    assert witnesses_of_entity_emerge(
        frames, subject="subject", entity_ids=["listener", "subject"], tick=10
    ) == (["listener"], 9)


def test_entity_witnesses_reject_current_or_future_frames():
    frames = {
        rtoken_of("listener"): PerceptionFrame(
            observer=rtoken_of("listener"),
            tick=10,
            observations=(
                Observation(
                    channel=Channel.VISION,
                    subject=rtoken_of("subject"),
                    description="走来",
                    strength=1,
                ),
            ),
        )
    }
    assert witnesses_of_entity_emerge(
        frames, subject="subject", entity_ids=["listener", "subject"], tick=10
    ) == ([], None)


def test_witnessed_verdict_uses_explicit_observation_tick():
    from sim.npc.evidence import judge_third_party_hidden

    verdict = judge_third_party_hidden(
        source="witnessed",
        holder_id="listener",
        subject_id="subject",
        attr_id="attr",
        observed_tick=9,
        events=[
            {
                "event_type": "npc.hidden_emerge",
                "tick": 10,
                "payload": {"npc_id": "subject", "attr_ids": ["attr"], "observed_tick": 9},
                "witnesses": ["listener"],
            }
        ],
    )
    assert verdict.admitted


async def test_relationship_projection_uses_callers_transaction(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import npc_chat_event
    from sim.core.persistence.models import Relationship
    from sim.core.persistence.social_projection import project_relationships

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await project_relationships(
            session, "main", [npc_chat_event(tick=10, npc_id="a", to_id="b", line="你好")]
        )
    async with sessions() as session:
        row = await session.get(Relationship, ("main", "a", "b"))
        assert row is not None
        from sim.npc.society import CHAT_AFFECTION_DELTA

        assert row.affection == CHAT_AFFECTION_DELTA
        assert row.last_interaction == 10


async def test_relationship_projection_rolls_back_with_event_transaction(engine):
    import pytest
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import npc_chat_event
    from sim.core.persistence.models import Relationship
    from sim.core.persistence.social_projection import project_relationships

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    with pytest.raises(RuntimeError):
        async with sessions.begin() as session:
            await project_relationships(
                session, "main", [npc_chat_event(tick=10, npc_id="a", to_id="b", line="你好")]
            )
            await session.flush()
            raise RuntimeError("rollback")
    async with sessions() as session:
        assert await session.get(Relationship, ("main", "a", "b")) is None


async def test_relationship_projection_is_branch_scoped(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import npc_chat_event
    from sim.core.persistence.models import Relationship
    from sim.core.persistence.social_projection import project_relationships

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await project_relationships(
            session, "child", [npc_chat_event(tick=10, npc_id="a", to_id="b", line="你好")]
        )
    async with sessions() as session:
        assert await session.get(Relationship, ("main", "a", "b")) is None
        assert await session.get(Relationship, ("child", "a", "b")) is not None


def test_knowledge_event_rejects_unsourced_hidden_fact():
    import pytest

    from sim.core.events import KnowledgeLearnedPayload

    with pytest.raises(ValueError):
        KnowledgeLearnedPayload(
            holder_id="b", subject_id="a", attr_id="h", fact="咳嗽", source="witnessed"
        )


async def test_witness_knowledge_projection_points_to_real_emerge(engine):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import EventKind, WorldEvent, hidden_emerge_event
    from sim.core.persistence.models import Knowledge
    from sim.core.persistence.social_projection import project_knowledge

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    emerged = hidden_emerge_event(10, "a", ("h",), ["b"]).model_copy(
        update={"payload": {"npc_id": "a", "attr_ids": ["h"], "observed_tick": 9}}
    )
    learned = WorldEvent(
        tick=10,
        event_type=EventKind.NPC_KNOWLEDGE_LEARNED,
        payload={
            "holder_id": "b",
            "subject_id": "a",
            "attr_id": "h",
            "fact": "他在雨夜咳嗽",
            "source": "witnessed",
            "observed_tick": 9,
            "evidence_tick": 10,
        },
    )
    async with sessions.begin() as session:
        await project_knowledge(session, sessions, "main", [emerged, learned], {0: 101, 1: 102})
    async with sessions() as session:
        row = (await session.execute(select(Knowledge))).scalar_one()
        assert row.holder_id == "b"
        assert row.evidence_seq == 101
        assert row.confidence == 0.9


async def test_told_knowledge_requires_matching_teller_and_preserves_parent(engine):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import EventKind, WorldEvent
    from sim.core.persistence.knowledge_store import KnowledgeStore
    from sim.core.persistence.models import Knowledge
    from sim.core.persistence.social_projection import project_knowledge
    from sim.llm.memory_scan import MemoryWritePipeline

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = KnowledgeStore(sessions)
    root = await store.write_fact(
        MemoryWritePipeline(),
        holder_id="a",
        fact="雨夜咳嗽",
        confidence=0.9,
        source="witnessed",
        learned_at=1,
        subject_npc_id="s",
        subject_attr_id="h",
        evidence_seq=1,
    )
    event = WorldEvent(
        tick=2,
        actor_id="a",
        event_type=EventKind.NPC_KNOWLEDGE_LEARNED,
        payload={
            "holder_id": "b",
            "subject_id": "s",
            "attr_id": "h",
            "fact": "雨夜咳嗽",
            "source": "told",
            "source_knowledge_id": root.row_id,
        },
    )
    async with sessions.begin() as session:
        await project_knowledge(session, sessions, "main", [event], {0: 2})
    async with sessions() as session:
        rows = (await session.execute(select(Knowledge).order_by(Knowledge.id))).scalars().all()
        assert len(rows) == 2
        assert rows[1].source_knowledge_id == root.row_id
        assert rows[1].confidence == 0.54


async def test_chat_prepares_told_event_from_speakers_valid_knowledge(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import npc_chat_event
    from sim.core.persistence.knowledge_store import KnowledgeStore
    from sim.core.persistence.social_projection import prepare_retell_events
    from sim.llm.memory_scan import MemoryWritePipeline

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await KnowledgeStore(sessions).write_fact(
        MemoryWritePipeline(),
        holder_id="a",
        fact="雨夜咳嗽",
        confidence=0.9,
        source="witnessed",
        learned_at=1,
        subject_npc_id="s",
        subject_attr_id="h",
        evidence_seq=1,
    )
    events = await prepare_retell_events(sessions, "main", [npc_chat_event(2, "a", "b", "你好")])
    assert len(events) == 1
    assert events[0].payload["holder_id"] == "b"
    assert events[0].payload["source_knowledge_id"] is not None


async def test_witness_anchor_matches_the_admitted_event(engine):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import EventKind, WorldEvent, hidden_emerge_event
    from sim.core.persistence.models import Knowledge
    from sim.core.persistence.social_projection import project_knowledge

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    first = hidden_emerge_event(10, "a", ("h",), [])
    second = hidden_emerge_event(10, "a", ("h",), ["b"])
    learned = WorldEvent(
        tick=10,
        event_type=EventKind.NPC_KNOWLEDGE_LEARNED,
        payload={
            "holder_id": "b",
            "subject_id": "a",
            "attr_id": "h",
            "fact": "雨夜咳嗽",
            "source": "witnessed",
            "observed_tick": 10,
            "evidence_tick": 10,
        },
    )
    async with sessions.begin() as session:
        await project_knowledge(
            session, sessions, "main", [first, second, learned], {0: 101, 1: 102, 2: 103}
        )
    async with sessions() as session:
        row = (await session.execute(select(Knowledge))).scalar_one()
        assert row.evidence_seq == 102


async def test_same_batch_chat_does_not_repeat_one_fact(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import npc_chat_event
    from sim.core.persistence.knowledge_store import KnowledgeStore
    from sim.core.persistence.social_projection import prepare_retell_events
    from sim.llm.memory_scan import MemoryWritePipeline

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await KnowledgeStore(sessions).write_fact(
        MemoryWritePipeline(),
        holder_id="a",
        fact="雨夜咳嗽",
        confidence=0.9,
        source="witnessed",
        learned_at=1,
        subject_npc_id="s",
        subject_attr_id="h",
        evidence_seq=1,
    )
    events = await prepare_retell_events(
        sessions, "main", [npc_chat_event(2, "a", "b", "你好"), npc_chat_event(3, "a", "b", "你好")]
    )
    assert len(events) == 1


async def test_relationship_retell_projection_matches_ledger(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import relationship_retell_event
    from sim.core.persistence.models import Relationship
    from sim.core.persistence.social_projection import project_relationships
    from sim.npc.chat_ledger import ChatLedger

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    ledger = ChatLedger()
    ledger.adjust("a", "b", kind="retell")
    async with sessions.begin() as session:
        await project_relationships(session, "main", [relationship_retell_event(10, "a", "b")])
    async with sessions() as session:
        row = await session.get(Relationship, ("main", "a", "b"))
        assert row is not None
        assert row.trust == ledger.relations_of("a")["b"]["trust"]


async def test_norms_reach_driver_prompt():
    import json

    from sim.tests.test_m4c_llm_driver import TestChenmoDriver as DriverFixture
    from sim.tests.test_m4c_llm_driver import _FakeLlm, _FakeProfile

    llm = _FakeLlm(json.dumps({"action": "wait", "reason": "等等"}))
    driver = DriverFixture._driver(llm, profile=_FakeProfile())
    assert await driver.decide_once(
        DriverFixture._loop_with_chenmo().state, 10, norms_entries=("雨夜别约他出诊",)
    )
    assert "雨夜别约他出诊" in str(llm.last_messages)


async def test_relationship_hydration_restores_runtime_values(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import npc_chat_event, relationship_retell_event
    from sim.core.persistence.social_projection import hydrate_relationships, project_relationships
    from sim.npc.chat_ledger import ChatLedger

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await project_relationships(
            session,
            "main",
            [npc_chat_event(1, "a", "b", "你好"), relationship_retell_event(2, "a", "b")],
        )
    ledger = ChatLedger()
    async with sessions() as session:
        await hydrate_relationships(session, "main", ledger)
    assert ledger.relations_of("a")["b"]["affection"] > 0
    assert ledger.relations_of("a")["b"]["trust"] > 0


async def test_told_cannot_reference_knowledge_from_another_branch(engine):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import EventKind, WorldEvent
    from sim.core.persistence.knowledge_store import KnowledgeStore
    from sim.core.persistence.models import Knowledge
    from sim.core.persistence.social_projection import project_knowledge
    from sim.llm.memory_scan import MemoryWritePipeline

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    root = await KnowledgeStore(sessions).write_fact(
        MemoryWritePipeline(),
        holder_id="a",
        fact="雨夜咳嗽",
        confidence=0.9,
        source="witnessed",
        learned_at=1,
        subject_npc_id="s",
        subject_attr_id="h",
        evidence_seq=1,
    )
    event = WorldEvent(
        branch_id="child",
        tick=2,
        actor_id="a",
        event_type=EventKind.NPC_KNOWLEDGE_LEARNED,
        payload={
            "holder_id": "b",
            "subject_id": "s",
            "attr_id": "h",
            "fact": "雨夜咳嗽",
            "source": "told",
            "source_knowledge_id": root.row_id,
        },
    )
    async with sessions.begin() as session:
        await project_knowledge(session, sessions, "child", [event], {0: 2})
    async with sessions() as session:
        assert (
            not (await session.execute(select(Knowledge).where(Knowledge.branch_id == "child")))
            .scalars()
            .all()
        )


async def test_fork_cloned_knowledge_can_be_retold_in_child(engine, store):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import hidden_emerge_event, npc_chat_event
    from sim.core.persistence.fork import fork_from_anchor
    from sim.core.persistence.knowledge_store import KnowledgeStore
    from sim.core.persistence.social_projection import prepare_retell_events, project_knowledge
    from sim.llm.memory_scan import MemoryWritePipeline

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await store.append("main", [hidden_emerge_event(1, "s", ("h",), ["a"]).to_store_dict()])
    parent = await KnowledgeStore(sessions).write_fact(
        MemoryWritePipeline(),
        holder_id="a",
        fact="雨夜咳嗽",
        confidence=0.9,
        source="witnessed",
        learned_at=1,
        subject_npc_id="s",
        subject_attr_id="h",
        evidence_seq=1,
    )

    async def preflush():
        pass

    await fork_from_anchor(
        sessions,
        parent_branch_id="main",
        fork_seq=1,
        fork_tick=1,
        new_branch_id="child",
        preflush=preflush,
    )
    child_store = KnowledgeStore(sessions, branch_id="child")
    source = (await child_store.iter_valid("a"))[0]
    assert source.id != parent.row_id
    events = await prepare_retell_events(sessions, "child", [npc_chat_event(2, "a", "b", "你好")])
    assert events[0].payload["source_knowledge_id"] == source.id
    async with sessions.begin() as session:
        await project_knowledge(session, sessions, "child", events, {0: 1})
    rows = await child_store.iter_valid("b")
    assert len(rows) == 1
    assert rows[0].source_knowledge_id == source.id
    assert not await KnowledgeStore(sessions).iter_valid("b")


async def test_retell_rejects_receivers_untriggered_hidden_words(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from sim.core.events import npc_chat_event
    from sim.core.persistence.knowledge_store import KnowledgeStore
    from sim.core.persistence.social_projection import prepare_retell_events
    from sim.llm.memory_scan import MemoryWritePipeline
    from sim.npc.contract import HiddenState
    from sim.npc.hidden import HiddenAttribute, HiddenProfile

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await KnowledgeStore(sessions).write_fact(
        MemoryWritePipeline(),
        holder_id="a",
        fact="night cough",
        confidence=0.9,
        source="witnessed",
        learned_at=1,
        subject_npc_id="s",
        subject_attr_id="h",
        evidence_seq=1,
    )
    attr = HiddenAttribute(
        id="b.h",
        category="trauma",
        label="night cough",
        descriptors=("night cough",),
        triggers=("rain",),
    )
    hidden = {"b": HiddenState(HiddenProfile(npc_id="b", attributes=(attr,)), frozenset())}
    events = await prepare_retell_events(
        sessions, "main", [npc_chat_event(2, "a", "b", "hello")], hidden_states=hidden
    )
    assert events == []
