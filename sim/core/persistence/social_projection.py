"""Event-derived social projections; transaction ownership stays with flush_world."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from sim.core.events import EventKind, WorldEvent
from sim.core.persistence.models import Relationship
from sim.npc.society import CHAT_AFFECTION_DELTA, RETELL_TRUST_DELTA


async def project_relationships(
    session: AsyncSession, branch_id: str, events: Sequence[WorldEvent]
) -> None:
    for event in events:
        if event.event_type not in {EventKind.NPC_CHAT, EventKind.NPC_RELATIONSHIP_RETELL}:
            continue
        owner = str(event.payload["npc_id"])
        other = str(event.payload["to_id"])
        row = await session.get(Relationship, (branch_id, owner, other))
        if row is None:
            row = Relationship(
                branch_id=branch_id,
                owner_id=owner,
                other_id=other,
                trust=0.0,
                affection=0.0,
                fear=0.0,
                debt=0.0,
                face=0.0,
                last_interaction=event.tick,
            )
            session.add(row)
        if event.event_type is EventKind.NPC_CHAT:
            row.affection = min(1.0, row.affection + CHAT_AFFECTION_DELTA)
        else:
            row.trust = min(1.0, row.trust + RETELL_TRUST_DELTA)
        row.last_interaction = event.tick


async def project_knowledge(session, sessions, branch_id, events, seq_by_index):
    """Validate evidence against immutable events before projecting any fact."""
    from sim.core.events import KnowledgeLearnedPayload
    from sim.core.persistence.knowledge_store import KnowledgeStore
    from sim.llm.memory_scan import MemoryWritePipeline
    from sim.npc.evidence import judge_third_party_hidden

    knowledge = KnowledgeStore(sessions, branch_id=branch_id)
    pipeline = MemoryWritePipeline()
    rows = [event.to_store_dict() for event in events]
    for event in events:
        if event.event_type is not EventKind.NPC_KNOWLEDGE_LEARNED:
            continue
        payload = KnowledgeLearnedPayload.model_validate(event.payload)
        source_row = None
        evidence_seq = None
        if payload.source == "witnessed":
            for index, candidate in enumerate(events):
                if (
                    candidate.event_type is EventKind.NPC_HIDDEN_EMERGE
                    and candidate.tick == payload.evidence_tick
                    and candidate.payload.get("npc_id") == payload.subject_id
                    and payload.attr_id in candidate.payload.get("attr_ids", [])
                ):
                    admitted = judge_third_party_hidden(
                        source="witnessed",
                        holder_id=payload.holder_id,
                        subject_id=payload.subject_id,
                        attr_id=payload.attr_id,
                        events=[candidate.to_store_dict()],
                        observed_tick=payload.observed_tick,
                    )
                    if admitted.admitted:
                        evidence_seq = seq_by_index.get(index)
                        break
            if evidence_seq is None:
                continue
        else:
            if payload.source_knowledge_id is None:
                continue
            source_row = await knowledge.get(payload.source_knowledge_id, session=session)
            if source_row is None or source_row.holder_id != event.actor_id:
                continue
        teller = (
            None
            if source_row is None
            else {
                "invalidated": source_row.invalidated,
                "subject_npc_id": source_row.subject_npc_id,
                "subject_attr_id": source_row.subject_attr_id,
                "confidence": source_row.confidence,
            }
        )
        if source_row is not None and payload.fact != source_row.fact:
            continue
        verdict = judge_third_party_hidden(
            source=payload.source,
            holder_id=payload.holder_id,
            subject_id=payload.subject_id,
            attr_id=payload.attr_id,
            events=rows,
            observed_tick=payload.observed_tick,
            teller_knowledge=teller,
        )
        if not verdict.admitted:
            continue
        await knowledge.write_fact(
            pipeline,
            holder_id=payload.holder_id,
            fact=payload.fact,
            confidence=verdict.confidence,
            source=payload.source,
            learned_at=event.tick,
            subject_npc_id=payload.subject_id,
            subject_attr_id=payload.attr_id,
            evidence_seq=evidence_seq,
            source_knowledge_id=payload.source_knowledge_id,
            session=session,
        )


async def prepare_retell_events(
    sessions, branch_id, events, *, hidden_states=None, species_of=None
):
    """Assemble retellings only for knowledge-capable speakers and listeners.

    Species come from runtime profiles; implicit humans follow perception's default.
    Legacy animal knowledge is retained as history but cannot seed new retellings.
    """
    from sim.core.events import KnowledgeLearnedPayload
    from sim.core.persistence.knowledge_store import KnowledgeStore
    from sim.npc.evidence import TOLD_CONFIDENCE_FLOOR, TOLD_DECAY, can_hold_knowledge

    store = KnowledgeStore(sessions, branch_id=branch_id)
    prepared = []
    reserved: set[tuple[str, str, str]] = set()
    for event in events:
        if event.event_type is not EventKind.NPC_CHAT:
            continue
        speaker = str(event.payload["npc_id"])
        listener = str(event.payload["to_id"])
        if not all(
            can_hold_knowledge((species_of or {}).get(npc_id, "human"))
            for npc_id in (speaker, listener)
        ):
            continue
        existing = await store.iter_valid(listener)
        known = {(row.subject_npc_id, row.subject_attr_id) for row in existing}
        for row in await store.iter_valid(speaker):
            if (
                row.subject_npc_id is None
                or row.subject_attr_id is None
                or row.subject_npc_id == listener
            ):
                continue
            if (listener, row.subject_npc_id, row.subject_attr_id) in reserved:
                continue
            if (row.subject_npc_id, row.subject_attr_id) in known:
                continue
            if row.confidence * TOLD_DECAY < TOLD_CONFIDENCE_FLOOR:
                continue
            from sim.llm.memory_scan import MemoryWritePipeline
            from sim.npc.contract import HiddenState

            receiver = (hidden_states or {}).get(listener, HiddenState.empty())
            decision = MemoryWritePipeline().scan_fact(row.fact, **receiver.memory_kwargs())
            if not decision.admitted or decision.content != row.fact:
                continue
            payload = KnowledgeLearnedPayload(
                holder_id=listener,
                subject_id=row.subject_npc_id,
                attr_id=row.subject_attr_id,
                fact=row.fact,
                source="told",
                source_knowledge_id=row.id,
            )
            reserved.add((listener, row.subject_npc_id, row.subject_attr_id))
            prepared.append(
                WorldEvent(
                    branch_id=branch_id,
                    tick=event.tick,
                    actor_id=speaker,
                    target_id=listener,
                    event_type=EventKind.NPC_KNOWLEDGE_LEARNED,
                    payload=payload.model_dump(mode="json"),
                )
            )
            break
    return prepared


async def hydrate_relationships(session: AsyncSession, branch_id: str, ledger) -> None:
    """Restore the runtime mirror when starting or changing branches."""
    from sqlalchemy import select

    rows = (
        await session.execute(select(Relationship).where(Relationship.branch_id == branch_id))
    ).scalars()
    ledger.restore_relations(
        {
            owner: {
                row.other_id: {
                    field: getattr(row, field)
                    for field in ("affection", "trust", "fear", "debt", "face")
                }
                for row in group
            }
            for owner, group in _group_relations(rows).items()
        }
    )


def _group_relations(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row.owner_id, []).append(row)
    return grouped
