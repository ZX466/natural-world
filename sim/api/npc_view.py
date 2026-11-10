"""Branch-local inputs for the protagonist's narrative view of known people.

SQL is read only at hydration / committed relevant event batches. Raw rows stay
here; the WS ledger receives only the explicitly constructed narrative shape.
"""

import json
from collections.abc import Callable, Container, Mapping
from dataclasses import dataclass
from typing import NotRequired, TypedDict, cast

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sim.core.persistence.models import Knowledge, NpcHealth, Relationship
from sim.npc.hidden import HiddenAttribute, HiddenCategory, HiddenProfile, hidden_leak_scan
from sim.perception.narrate import narrate_bond, narrate_health

PROTAGONIST = "chenmo"


class NpcViewRow(TypedDict):
    rtoken: str
    name: NotRequired[str]
    health: list[str]
    bond: str
    knows: list[str]


@dataclass(frozen=True)
class NpcViewInputs:
    health: tuple[NpcHealth, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    knowledge: tuple[Knowledge, ...] = ()

    def rows(
        self,
        *,
        triggered: frozenset[str],
        live_ids: Container[str],
        display_names: Mapping[str, str],
        rtoken_of: Callable[[str], str],
    ) -> list[NpcViewRow]:
        incoming = {
            r.owner_id: r
            for r in self.relationships
            if r.other_id == PROTAGONIST and r.owner_id != PROTAGONIST
        }
        known = set(incoming) | {
            r.other_id for r in self.relationships if r.owner_id == PROTAGONIST
        }
        known.add(PROTAGONIST)
        attributes = {(h.npc_id, f"{h.npc_id}.health_{h.code}"): h for h in self.health}
        valid = [
            fact
            for fact in self.knowledge
            if fact.holder_id == PROTAGONIST
            and not fact.invalidated
            and fact.subject_npc_id in known
            and fact.subject_npc_id in live_ids
            and (fact.subject_npc_id, fact.subject_attr_id) in attributes
        ]
        known_pairs = {(f.subject_npc_id, f.subject_attr_id) for f in valid}
        permitted = frozenset(
            attr_id
            for (subject, attr_id) in attributes
            if (
                attr_id in triggered
                if subject == PROTAGONIST
                else subject in known and subject in live_ids and (subject, attr_id) in known_pairs
            )
        )
        hidden = HiddenProfile(
            npc_id=PROTAGONIST,
            attributes=tuple(
                HiddenAttribute(
                    id=attr_id,
                    category=cast(HiddenCategory, attribute.category),
                    label=attribute.label,
                    descriptors=tuple(
                        {attribute.label, *json.loads(attribute.descriptors or "[]")}
                    ),
                    triggers=(),
                )
                for (_, attr_id), attribute in attributes.items()
                if attribute.hidden
            ),
        )
        facts: dict[tuple[str, str], set[str]] = {}
        for fact in valid:
            assert fact.subject_npc_id is not None and fact.subject_attr_id is not None
            attribute = attributes[(fact.subject_npc_id, fact.subject_attr_id)]
            if attribute.hidden and fact.subject_attr_id not in permitted:
                continue
            # A previously admitted sentence can mention another hidden item
            # or an expired self window. Exclude that whole sentence here,
            # while constructing the row, with no hint or rewritten fragment.
            if hidden_leak_scan(fact.fact, hidden, permitted):
                continue
            # Use the admitted text itself. No labels, sources, confidence,
            # evidence pointers, or other holders' knowledge cross this edge.
            facts.setdefault((attribute.npc_id, fact.subject_attr_id), set()).add(fact.fact)

        result: list[NpcViewRow] = []
        for npc_id in sorted(known):
            if npc_id not in live_ids:
                continue
            visible_health = []
            for pair, attribute in sorted(attributes.items()):
                if attribute.npc_id != npc_id or not attribute.active:
                    continue
                if attribute.hidden and pair[1] not in permitted:
                    continue
                text = narrate_health(attribute.label, attribute.severity)
                if not hidden_leak_scan(text, hidden, permitted):
                    visible_health.append(text)
            knows = sorted(
                {
                    text
                    for (subject, _), texts in facts.items()
                    if subject == npc_id
                    for text in texts
                }
            )
            if npc_id == PROTAGONIST:
                if not visible_health and not knows:
                    continue
                bond = ""
            else:
                impression = incoming.get(npc_id)
                bond = (
                    narrate_bond(impression.trust, impression.affection, impression.fear)
                    if impression is not None
                    else "你们曾打过照面。"
                )
            row: NpcViewRow = {
                "rtoken": rtoken_of(npc_id),
                "health": visible_health,
                "bond": bond,
                "knows": knows,
            }
            name = display_names.get(npc_id)
            if name and name != npc_id:
                row["name"] = name
            result.append(row)
        return result


async def load_npc_view_inputs(session: AsyncSession, branch_id: str) -> NpcViewInputs:
    """One consistent branch read, outside all synchronous WS payload paths."""
    relationships = tuple(
        (
            await session.scalars(
                select(Relationship).where(
                    Relationship.branch_id == branch_id,
                    or_(Relationship.owner_id == PROTAGONIST, Relationship.other_id == PROTAGONIST),
                )
            )
        ).all()
    )
    known = {PROTAGONIST}
    for row in relationships:
        known.update((row.owner_id, row.other_id))
    health = tuple(
        (
            await session.scalars(
                select(NpcHealth).where(
                    NpcHealth.branch_id == branch_id,
                    # Hidden metadata closes cross-person fact leaks without
                    # making unknown people eligible for an outbound entry.
                    or_(NpcHealth.npc_id.in_(known), NpcHealth.hidden.is_(True)),
                )
            )
        ).all()
    )
    knowledge = tuple(
        (
            await session.scalars(
                select(Knowledge).where(
                    Knowledge.branch_id == branch_id,
                    Knowledge.holder_id == PROTAGONIST,
                    Knowledge.invalidated.is_(False),
                    Knowledge.subject_npc_id.in_(known),
                )
            )
        ).all()
    )
    return NpcViewInputs(health, relationships, knowledge)
