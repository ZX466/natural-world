"""Species capability is checked before knowledge events, with real perception wiring."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from sim.core.events import EventKind, npc_chat_event
from sim.core.persistence.knowledge_store import KnowledgeStore
from sim.core.persistence.models import Event, Knowledge
from sim.core.persistence.social_projection import prepare_retell_events
from sim.llm.memory_scan import MemoryWritePipeline


@pytest.mark.parametrize(
    ("species", "expected"),
    [("human", True), ("cat", False), ("dog", False), ("raven", False), ("unknown", False)],
)
def test_species_knowledge_capability(species, expected):
    from sim.npc.evidence import can_hold_knowledge

    assert can_hold_knowledge(species) is expected


async def test_lifespan_animal_witnesses_do_not_acquire_human_knowledge():
    """Seeded night trigger and actual perception; no synthetic frames or hidden profiles."""
    from sim.api.main import app, lifespan
    from sim.tests.test_health_live_wiring import stop_background

    animals = {"cat_grey", "dog_black", "raven"}
    humans = {"villager_04", "villager_05"}
    async with lifespan(app):
        await stop_background(app)
        await app.state.flush_for_anchor()
        loop = app.state.loop
        entities = dict(loop.state.entities)
        # Put the fixture's witnesses together in a real walkable cell. Perception and
        # seeded Chenmo health stay untouched; the tick hooks decide who saw what.
        for observer in animals | humans:
            entities[observer] = entities[observer].model_copy(
                update={"pos": entities["chenmo"].pos, "path": ()}
            )
        for tick in (23 * 3600 - 2, 23 * 3600):
            loop.state = loop.state.model_copy(update={"entities": entities, "tick": tick})
            loop.clock.restore_tick(tick)
            # Same order as _tick_once: runtime sees the previously completed frame.
            loop._run_npc_runtime()
            loop._run_perception()
            entities = dict(loop.state.entities)
        emerges = [
            event
            for event in loop.pending_events
            if event.event_type is EventKind.NPC_HIDDEN_EMERGE
            and event.payload["npc_id"] == "chenmo"
        ]
        assert emerges, "The seeded night condition must produce a real emergence"
        assert set(emerges[-1].witnesses) >= animals | humans
        learned = [
            event
            for event in loop.pending_events
            if event.event_type is EventKind.NPC_KNOWLEDGE_LEARNED
        ]
        holders = {event.payload["holder_id"] for event in learned}
        assert holders >= humans
        assert holders.isdisjoint(animals), "Animals may witness but cannot hold human facts"
        await app.state.flush_for_anchor()
        async with app.state.store.session_factory() as session:
            rows = list(await session.scalars(select(Knowledge)))
            persisted = list(
                await session.scalars(
                    select(Event).where(Event.event_type == EventKind.NPC_KNOWLEDGE_LEARNED.value)
                )
            )
        assert {row.holder_id for row in rows} >= humans
        assert {row.holder_id for row in rows}.isdisjoint(animals)
        assert {json.loads(row.payload)["holder_id"] for row in persisted}.isdisjoint(animals)
        assert all(row.evidence_seq is not None for row in rows if row.source == "witnessed")


@pytest.mark.parametrize(
    ("speaker_species", "listener_species"), [("human", "cat"), ("dog", "human")]
)
async def test_retell_species_gate_prevents_animal_receivers_and_legacy_sources(
    engine, speaker_species, listener_species
):
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await KnowledgeStore(sessions).write_fact(
        MemoryWritePipeline(),
        holder_id="speaker",
        fact="雨夜咳嗽",
        confidence=0.9,
        source="witnessed",
        learned_at=1,
        subject_npc_id="subject",
        subject_attr_id="hidden",
        evidence_seq=1,
    )
    events = await prepare_retell_events(
        sessions,
        "main",
        [npc_chat_event(2, "speaker", "listener", "你好")],
        species_of={"speaker": speaker_species, "listener": listener_species},
    )
    assert events == []
    assert not await KnowledgeStore(sessions).iter_valid("listener")
