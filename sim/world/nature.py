"""生态/动物实况：稀疏事件信号与可重算的观察投影，零世界实体增殖。"""

from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256

from sim.core.calendar import TICKS_PER_GAME_DAY, TICKS_PER_GAME_HOUR, phase_of_day
from sim.core.events import EventKind, WorldEvent
from sim.world.ecology import ecology_phase_at, ecology_shift_due
from sim.world.fauna import active_species_at, fauna_sightings_at
from sim.world.map import TileMap


def nature_events_at(tick: int) -> list[WorldEvent]:
    events = []
    if tick > 0 and tick % TICKS_PER_GAME_DAY == 0 and ecology_shift_due(tick - 1, tick):
        phase = ecology_phase_at(tick)
        events.append(
            WorldEvent(
                tick=tick,
                event_type=EventKind.ECOLOGY_SHIFT,
                actor_id="",
                payload={
                    "phase": phase.phase,
                    "prey_trend": phase.prey_trend,
                    "predator_trend": phase.predator_trend,
                },
            )
        )
    if tick % TICKS_PER_GAME_HOUR:
        return events
    if tick and phase_of_day(tick - 1) is phase_of_day(tick):
        return events
    previous = {s.species: s.state for s in fauna_sightings_at(tick - 1)} if tick else {}
    for sighting in fauna_sightings_at(tick):
        if previous.get(sighting.species) != sighting.state:
            events.append(
                WorldEvent(
                    tick=tick,
                    event_type=EventKind.FAUNA_TICK,
                    actor_id="",
                    payload={"species": sighting.species, "state": sighting.state},
                )
            )
    return events


@dataclass(frozen=True)
class FaunaProjection:
    entity_id: str
    species: str
    pos: tuple[int, int]
    sprite: str
    anim: str


@lru_cache(maxsize=256)
def _spots(seed: int, species: str, width: int, height: int) -> tuple[tuple[int, int], ...]:
    points = []
    for index in range(128):
        digest = sha256(f"fauna-spot:{seed}:{species}:{index}".encode()).digest()
        points.append(
            (int.from_bytes(digest[:4], "big") % width, int.from_bytes(digest[4:8], "big") % height)
        )
    return tuple(points)


def fauna_projection_at(tick: int, seed: int, tile_map: TileMap) -> tuple[FaunaProjection, ...]:
    active = set(active_species_at(tick))
    result = []
    for species, slug in (("狼", "wolf"), ("鹿", "deer"), ("鸟", "bird")):
        pos = next(
            (
                p
                for p in _spots(seed, species, tile_map.width, tile_map.height)
                if tile_map.is_walkable(*p)
            ),
            None,
        )
        if pos is not None:
            result.append(
                FaunaProjection(
                    f"wildlife_{slug}",
                    species,
                    pos,
                    f"fauna_{slug}",
                    "idle" if species in active else "rest",
                )
            )
    return tuple(result)
