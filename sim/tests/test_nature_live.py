"""S4: 生态/动物信号进真实 tick，动物仅进入观察投影。"""

from pathlib import Path

from sim.api.ws import delta_payload, snapshot_payload
from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.core.clock import GameClock
from sim.core.events import EventKind
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder


def loop_at(tick: int) -> TickLoop:
    return TickLoop(GameClock(speed=1), build_default_bus(), WorldState(tick=tick, world_seed=42))


def test_ecology_crossing_emits_one_validated_signal():
    loop = loop_at(2 * TICKS_PER_GAME_DAY - 1)
    loop.advance_frame(2 / 60)
    events = [e for e in loop.drain_events() if e.event_type is EventKind.ECOLOGY_SHIFT]
    assert len(events) == 1
    assert events[0].payload == {"phase": "平稳", "prey_trend": "平稳", "predator_trend": "稀少"}
    loop.advance_frame(10 / 60)
    assert not any(e.event_type is EventKind.ECOLOGY_SHIFT for e in loop.drain_events())


def test_fauna_crossing_emits_changed_species_only():
    loop = loop_at(5 * 3600 - 1)
    loop.advance_frame(2 / 60)
    events = [e for e in loop.drain_events() if e.event_type is EventKind.FAUNA_TICK]
    assert {e.payload["species"]: e.payload["state"] for e in events} == {
        "狼": "蛰伏",
        "鹿": "出没",
        "鸟": "出没",
    }
    loop.advance_frame(10 / 60)
    assert not any(e.event_type is EventKind.FAUNA_TICK for e in loop.drain_events())
    assert loop.state.entities == {}


def test_fauna_uses_existing_actor_projection_without_world_entities():
    town = TileMap.from_json_file(Path(__file__).resolve().parents[1] / "content/linhe-town.json")
    loop = loop_at(0)
    loop.pathfinder = Pathfinder(town)
    loop.fauna_enabled = True
    actors = snapshot_payload(loop, town)["actors"]
    assert {a["name"]: a["anim"] for a in actors} == {"狼": "idle", "鹿": "rest", "鸟": "rest"}
    assert all(town.is_walkable(a["x"], a["y"]) for a in actors)
    assert all("entity_id" not in a and "tick" not in a for a in actors)
    loop.state = loop.state.model_copy(update={"tick": 5 * 3600})
    delta = delta_payload(loop, set())["actors"]
    assert {a["name"]: a["anim"] for a in delta} == {"狼": "rest", "鹿": "idle", "鸟": "idle"}
    assert loop.state.entities == {}


def test_fauna_sighting_reaches_local_perception_only():
    from sim.core.world import EntityState
    from sim.perception.senses import rtoken_of, run_perception_step
    from sim.world.nature import fauna_projection_at

    town = TileMap.from_json_file(Path(__file__).resolve().parents[1] / "content/linhe-town.json")
    deer = next(f for f in fauna_projection_at(5 * 3600, 42, town) if f.species == "鹿")
    state = WorldState(
        tick=5 * 3600,
        world_seed=42,
        entities={"observer": EntityState(entity_id="observer", pos=deer.pos)},
    )
    frames = run_perception_step(state, town, [], include_fauna=True)
    assert set(frames) == {rtoken_of("observer")}
    assert "鹿" in frames[rtoken_of("observer")].narrated()
    assert set(state.entities) == {"observer"}


def test_snapshot_and_delta_share_dynamic_fauna_map():
    town = TileMap.from_json_file(Path(__file__).resolve().parents[1] / "content/linhe-town.json")
    loop = loop_at(0)
    loop.pathfinder = Pathfinder(town)
    loop.fauna_enabled = True
    first = snapshot_payload(loop, town)["actors"][0]
    changed = town.with_collision(first["x"], first["y"], walkable=False)
    loop.pathfinder.observe_map(changed)
    snapshot = snapshot_payload(loop, town)["actors"]
    delta = delta_payload(loop, set())["actors"]
    assert {a["rtoken"]: (a["x"], a["y"]) for a in snapshot} == {
        a["rtoken"]: (a["x"], a["y"]) for a in delta
    }
