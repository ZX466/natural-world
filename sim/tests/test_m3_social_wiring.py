from sim.core.events import EventKind
from sim.npc.evidence import witnesses_of_entity_emerge
from sim.perception.frame import Channel, Observation, PerceptionFrame
from sim.perception.senses import rtoken_of, run_perception_step
from sim.tests.test_health_live_wiring import stop_background
from sim.world.map import CHUNK_SIZE, Chunk, TileMap


def _open_map() -> TileMap:
    chunks = {
        (cx, cy): Chunk(
            cx=cx,
            cy=cy,
            ground=(0,) * (CHUNK_SIZE * CHUNK_SIZE),
            collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
        )
        for cx in range(2)
        for cy in range(2)
    }
    return TileMap(width=32, height=32, chunks=chunks)


def test_entity_witnesses_use_production_display_name_labels():
    frames = {
        rtoken_of("villager_01"): PerceptionFrame(
            observer=rtoken_of("villager_01"),
            tick=9,
            observations=(
                Observation(
                    channel=Channel.VISION,
                    subject="小满",
                    description="小满就在不远处。",
                    strength=0.4,
                ),
            ),
        )
    }
    assert witnesses_of_entity_emerge(
        frames,
        subject="villager_02",
        entity_ids=["villager_01", "villager_02"],
        tick=10,
        display_name_of={"villager_01": "赵铁", "villager_02": "小满"},
    ) == (["villager_01"], 9)


def test_entity_witnesses_resolve_real_perception_labels():
    from sim.core.world import EntityState, WorldState

    state = WorldState(
        entities={
            "villager_01": EntityState(entity_id="villager_01", pos=(1, 1)),
            "villager_02": EntityState(entity_id="villager_02", pos=(2, 1)),
        }
    )
    frames = run_perception_step(
        state,
        _open_map(),
        [],
        display_name_of={"villager_01": "赵铁", "villager_02": "小满"},
    )
    assert witnesses_of_entity_emerge(
        frames,
        subject="villager_02",
        entity_ids=["villager_01", "villager_02"],
        tick=2,
        display_name_of={"villager_01": "赵铁", "villager_02": "小满"},
    ) == (["villager_01"], 0)


def test_entity_witnesses_fail_closed_on_ambiguous_display_name():
    """同名两人：显示名不可唯一反查 ⇒ 宁可不装配，也不误判目击（fail-closed）。"""
    frames = {
        rtoken_of("villager_01"): PerceptionFrame(
            observer=rtoken_of("villager_01"),
            tick=9,
            observations=(
                Observation(
                    channel=Channel.VISION,
                    subject="小满",
                    description="小满就在不远处。",
                    strength=0.4,
                ),
            ),
        )
    }
    # 词面无法唯一反查主体 ⇒ 既无目击人，也无可报告的目击 tick（fail-closed）。
    assert witnesses_of_entity_emerge(
        frames,
        subject="villager_02",
        entity_ids=["villager_01", "villager_02", "villager_03"],
        tick=10,
        display_name_of={
            "villager_01": "赵铁",
            "villager_02": "小满",
            "villager_03": "小满",
        },
    ) == ([], None)


def test_entity_witnesses_resolve_subject_without_display_name():
    """无显示名的实体：senses 用 rtoken 作词面，装配须按同一口径反查（不得误 fail-closed）。"""
    frames = {
        rtoken_of("listener"): PerceptionFrame(
            observer=rtoken_of("listener"),
            tick=9,
            observations=(
                Observation(
                    channel=Channel.VISION,
                    subject=rtoken_of("subject"),  # senses 对无名实体的词面
                    description="走来",
                    strength=1,
                ),
            ),
        )
    }
    assert witnesses_of_entity_emerge(
        frames,
        subject="subject",  # 不在 display_name_of 里
        entity_ids=["listener", "subject"],
        tick=10,
        display_name_of={"listener": "赵铁"},
    ) == (["listener"], 9)


def _neighbour_villagers(state) -> tuple[str, str]:
    entities = sorted(
        (e for e in state.entities.values() if e.entity_id.startswith("villager_")),
        key=lambda e: e.entity_id,
    )
    for subject in entities:
        observer = min(
            (e for e in entities if e.entity_id != subject.entity_id),
            key=lambda e: abs(e.pos[0] - subject.pos[0]) + abs(e.pos[1] - subject.pos[1]),
            default=None,
        )
        if observer is not None:
            return subject.entity_id, observer.entity_id
    raise AssertionError("测试需要两个村民实体")


async def test_lifespan_witnesses_knowledge_from_real_perception():
    """真跑 lifespan：感知帧 → 目击装配 → knowledge 落库（本轮漏检的结构缺口）。

    执行序照抄 `TickLoop._tick_once`（`tick.py:94-96`）：**先 npc_runtime 后 perception**。
    故 emerge 只能拿**上一帧**：先在 tick-2 装配真实感知帧，再在 tick 触发浮现。
    """
    from sqlalchemy import select

    from sim.api.main import app, lifespan
    from sim.core.persistence.models import Knowledge
    from sim.npc.contract import HiddenState
    from sim.npc.hidden import HiddenAttribute, HiddenProfile

    async with lifespan(app):
        await stop_background(app)
        loop = app.state.loop
        await app.state.flush_for_anchor()
        subject, observer = _neighbour_villagers(loop.state)
        loop.state = loop.state.model_copy(
            update={
                "entities": {
                    **loop.state.entities,
                    observer: loop.state.entities[observer].model_copy(
                        update={
                            "pos": (
                                loop.state.entities[subject].pos[0] + 1,
                                loop.state.entities[subject].pos[1],
                            )
                        }
                    ),
                }
            }
        )
        attr = HiddenAttribute(
            id=f"{subject}.health_live_witness",
            category="trauma",
            label="肩头旧伤",
            descriptors=("肩头旧伤",),
            triggers=("夜深了",),
        )
        app.state.hidden_states[subject] = HiddenState(
            HiddenProfile(npc_id=subject, attributes=(attr,)), frozenset()
        )
        observe_tick = 23 * 3600 - 2  # 偶数 tick 才装配视觉；早于浮现一拍
        emerge_tick = 23 * 3600  # 决策节拍（10 的倍数）
        loop.state = loop.state.model_copy(update={"tick": observe_tick})
        loop.clock.restore_tick(loop.state.tick)
        loop._run_perception()
        loop.state = loop.state.model_copy(update={"tick": emerge_tick})
        loop.clock.restore_tick(loop.state.tick)
        loop._run_npc_runtime()
        emerges = [
            e
            for e in loop.pending_events
            if e.event_type is EventKind.NPC_HIDDEN_EMERGE and e.payload["npc_id"] == subject
        ]
        assert emerges and observer in emerges[-1].witnesses
        learned = [
            e for e in loop.pending_events if e.event_type is EventKind.NPC_KNOWLEDGE_LEARNED
        ]
        assert learned
        await app.state.flush_for_anchor()
        async with app.state.store.session_factory() as session:
            rows = (
                (await session.execute(select(Knowledge).where(Knowledge.holder_id == observer)))
                .scalars()
                .all()
            )
        assert any(row.subject_npc_id == subject and row.evidence_seq is not None for row in rows)


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
