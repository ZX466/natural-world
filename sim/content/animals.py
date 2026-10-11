"""灰、黑子、鸦：创世固定三实体，物种档案和确定性游荡。"""

from __future__ import annotations

import hashlib

from sim.core.events import WorldEvent, move_event
from sim.core.world import WorldState

ANIMALS = {"cat_grey": ("灰", "cat"), "dog_black": ("黑子", "dog"), "raven": ("鸦", "raven")}


async def seed_animals(session_factory) -> int:
    from sqlalchemy import select

    from sim.content.villagers import _profile_row
    from sim.core.persistence.models import NpcProfile
    from sim.npc.model import NpcProfileData

    async with session_factory() as session:
        existing = set((await session.execute(select(NpcProfile.id))).scalars().all())
        missing = set(ANIMALS) - existing
        for eid in sorted(missing):
            name, species = ANIMALS[eid]
            row = _profile_row(NpcProfileData(npc_id=eid, name=name, species=species, lod=0))
            row["species"] = species
            row["identity_anchor"] = f"我叫{name}。"
            session.add(NpcProfile(**row))
        await session.commit()
        return len(missing)


def animal_events(state: WorldState, tile_map, tick: int) -> list[WorldEvent]:
    if tick % 60:
        return []
    events = []
    for eid in ANIMALS:
        entity = state.entities.get(eid)
        if entity is None or entity.path:
            continue
        x, y = entity.pos
        candidates = sorted(
            (x + dx, y + dy)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
            if tile_map.is_walkable(x + dx, y + dy)
        )
        if not candidates:
            continue
        digest = hashlib.sha256(f"fauna:{state.world_seed}:{tick}:{eid}".encode()).digest()
        goal = candidates[int.from_bytes(digest[:4], "big") % len(candidates)]
        events.append(move_event(tick, eid, entity.pos, goal, (entity.pos, goal)))
    return events
