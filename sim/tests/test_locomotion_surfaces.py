"""Canonical terrain authority and legal elevated player locomotion."""

from __future__ import annotations

import importlib
import importlib.util
from typing import Any

import pytest

from sim.core.clock import GameClock
from sim.core.events import tile_changed_event, voxel_edited_event
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.world.map import CHUNK_SIZE, Chunk, TileMap
from sim.world.pathfinding import Pathfinder


def surface(heights: dict[tuple[int, int], int], banks: set[tuple[int, int]] | None = None) -> Any:
    banks = banks or set()
    collision = tuple(
        heights.get((x, y), 1) == 1 and (x, y) not in banks
        for y in range(CHUNK_SIZE)
        for x in range(CHUNK_SIZE)
    )
    tile_map = TileMap(
        width=4,
        height=4,
        chunks={
            (0, 0): Chunk(cx=0, cy=0, ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE), collision=collision)
        },
    )
    assert importlib.util.find_spec("sim.world.surface") is not None, (
        "canonical surface projection required"
    )
    module = importlib.import_module("sim.world.surface")
    return module.SurfaceMap(tile_map, lambda x, y: heights.get((x, y), 1))


def planning(state: WorldState, pf: Pathfinder, goal: tuple[int, int], gait: str = "walk") -> Any:
    module = importlib.import_module("sim.world.locomotion")
    plan = getattr(module, "plan_jump", None)
    assert callable(plan), "server-side jump validation required"
    return plan(state, "chenmo", goal, gait, pf)


def configured(heights: dict[tuple[int, int], int]) -> tuple[Any, Pathfinder, TickLoop]:
    view = surface(heights)
    pf = Pathfinder(view.tile_map, height_of=view.height_at)
    loop = TickLoop(
        clock=GameClock(),
        bus=build_default_bus(),
        state=WorldState(entities={"chenmo": EntityState(entity_id="chenmo", pos=(0, 0))}),
        pathfinder=pf,
    )

    def observe(event: Any) -> None:
        view.observe(event)
        pf.observe_map(view.tile_map)

    attach = getattr(loop, "attach_event_observer", None)
    assert callable(attach), "unflushed terrain changes must be visible before the next tick"
    attach(observe)
    return view, pf, loop


def test_high_surface_paths_do_not_make_npc_collision_walkable() -> None:
    view = surface({(1, 0): 2, (2, 0): 2, (3, 0): 3})
    pf = Pathfinder(view.tile_map, height_of=view.height_at)
    with pytest.raises(ValueError):
        pf.find((0, 0), (1, 0))
    assert pf.find((1, 0), (2, 0), elevation=2) == ((1, 0), (2, 0))
    with pytest.raises(ValueError):
        pf.find((1, 0), (3, 0), elevation=2)
    assert not view.tile_map.is_walkable(1, 0)
    assert not view.tile_map.is_walkable(3, 0)


def test_blocked_earth_bank_stays_blocked_in_ground_and_surface_mode() -> None:
    view = surface({}, {(1, 0)})
    pf = Pathfinder(view.tile_map, height_of=view.height_at)
    assert view.height_at(1, 0) == 1 and not view.tile_map.is_walkable(1, 0)
    for elevation in [None, 1]:
        with pytest.raises(ValueError):
            pf.find((0, 0), (1, 0), elevation=elevation)
    state = WorldState(entities={"chenmo": EntityState(entity_id="chenmo", pos=(0, 0))})
    assert planning(state, pf, (1, 0)).payload["target_height"] == 1
    assert not view.tile_map.is_walkable(1, 0)


def test_new_build_completion_carries_its_explicit_support_height() -> None:
    from sim.agent.build_exec import BUILD_DURATION_TICKS, BuildRuntime
    from sim.core.events import EventKind

    view = surface({})
    build = BuildRuntime(view.tile_map, seed=42)
    assert build.start("builder", (1, 1), tick=0) is not None
    events = build.on_tick(BUILD_DURATION_TICKS)
    tiles = [event for event in events if event.event_type is EventKind.TILE_CHANGED]
    assert len(tiles) == 4
    assert all(event.payload.get("height") == 2 for event in tiles)
    for event in events:
        view.apply(event)
    assert view.height_at(1, 1) == 2
    assert not view.tile_map.is_walkable(1, 1)


@pytest.mark.parametrize("height", [2, 3])
def test_real_surface_validated_jump_lands_high_and_back_down(height: int) -> None:
    view, pf, loop = configured({(1, 0): height})
    loop.enqueue(planning(loop.state, pf, (1, 0)))
    loop.advance_frame(0.6)
    actor = loop.state.entities["chenmo"]
    assert actor.pos == (1, 0) and view.height_at(*actor.pos) == height
    assert actor.jump is not None and not actor.jump.airborne
    assert not view.tile_map.is_walkable(1, 0)
    loop.enqueue(planning(loop.state, pf, (0, 0)))
    loop.advance_frame(0.6)
    assert loop.state.entities["chenmo"].pos == (0, 0)
    assert view.height_at(0, 0) == 1


@pytest.mark.parametrize("goal", [(-1, 0), (4, 0), (3, 0), (True, 0), (1.5, 0)])
def test_invalid_jump_coordinates_or_reach_have_no_world_mutation(goal: Any) -> None:
    _, pf, loop = configured({})
    before = loop.state.state_hash()
    with pytest.raises(ValueError):
        planning(loop.state, pf, goal)
    assert loop.state.state_hash() == before


def test_cannot_land_in_water_or_jump_through_tall_diagonal_corner() -> None:
    _, pf, loop = configured({(1, 0): 0})
    with pytest.raises(ValueError):
        planning(loop.state, pf, (1, 0))
    _, pf, loop = configured({(1, 0): 3})
    with pytest.raises(ValueError):
        planning(loop.state, pf, (1, 1))
    # Landing on that adjacent high top is legal; passing below its side is not.
    assert planning(loop.state, pf, (1, 0)).payload["target_height"] == 3


def test_running_jump_can_clear_one_height_two_obstacle_but_not_height_three() -> None:
    _, pf, loop = configured({(1, 0): 2})
    assert planning(loop.state, pf, (2, 0), "run").payload["goal"] == [2, 0]
    _, pf, loop = configured({(1, 0): 3})
    with pytest.raises(ValueError):
        planning(loop.state, pf, (2, 0), "run")


def test_landing_sees_unflushed_support_change_within_one_frame() -> None:
    view, pf, loop = configured({(1, 0): 2})
    loop.enqueue(planning(loop.state, pf, (1, 0)))
    loop.advance_frame(10 / 60)
    change = voxel_edited_event(loop.state.tick, x=1, y=0, action="dig")
    loop.enqueue(change.model_copy(update={"payload": {**change.payload, "height": 1}}))
    loop.enqueue(tile_changed_event(loop.state.tick, 1, 0, 1, height=1))
    assert view.height_at(1, 0) == 1  # no flush callback was run
    loop.advance_frame(0.6)
    assert loop.state.entities["chenmo"].pos == (0, 0)
    landed = [e for e in loop.pending_events if e.event_type.value == "actor.jump_landed"]
    assert len(landed) == 1 and landed[0].payload["reason"] == "obstructed"


def test_height_one_placement_does_not_turn_into_walkable_ground() -> None:
    view, _, loop = configured({})
    edit = voxel_edited_event(0, x=1, y=0, action="place")
    loop.enqueue(edit.model_copy(update={"payload": {**edit.payload, "height": 1}}))
    loop.enqueue(tile_changed_event(0, 1, 0, 0, height=1))
    assert view.height_at(1, 0) == 1
    assert not view.tile_map.is_walkable(1, 0)
    loop.enqueue(
        voxel_edited_event(0, x=1, y=0, action="dig").model_copy(
            update={
                "payload": {"x": 1, "y": 0, "action": "dig", "material_id": "earth", "height": 1}
            }
        )
    )
    loop.enqueue(tile_changed_event(0, 1, 0, 1, height=1))
    assert view.tile_map.is_walkable(1, 0)


def test_tile_height_extension_preserves_legacy_event_shape() -> None:
    assert "height" not in tile_changed_event(0, 1, 0, 0).payload
    assert tile_changed_event(0, 1, 0, 0, height=2).payload["height"] == 2
