"""Untrusted movement/flight requests and observable, nontechnical actor facts."""

from __future__ import annotations

from typing import Any

import pytest

from sim.api import ws
from sim.core.clock import GameClock
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.world.map import CHUNK_SIZE, Chunk, TileMap
from sim.world.pathfinding import Pathfinder
from sim.world.surface import SurfaceMap


def context() -> tuple[TickLoop, Pathfinder, SurfaceMap]:
    heights = {(1, 0): 2, (1, 1): 2, (2, 0): 3}
    collision = tuple((x, y) not in heights for y in range(CHUNK_SIZE) for x in range(CHUNK_SIZE))
    tile_map = TileMap(
        width=4,
        height=4,
        chunks={
            (0, 0): Chunk(cx=0, cy=0, ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE), collision=collision)
        },
    )
    view = SurfaceMap(tile_map, lambda x, y: heights.get((x, y), 1))
    pf = Pathfinder(view.tile_map, height_of=view.height_at)
    loop = TickLoop(
        clock=GameClock(),
        bus=build_default_bus(),
        pathfinder=pf,
        state=WorldState(entities={"chenmo": EntityState(entity_id="chenmo", pos=(0, 0))}),
    )
    return loop, pf, view


def send(loop: TickLoop, pf: Pathfinder, kind: str = "jump_request", **fields: Any) -> Any:
    return ws.handle_client_message(
        {"type": kind, "channel": "render", "target_x": 1, "target_y": 0, **fields}, loop, pf
    )


def test_explicit_gait_reaches_event_and_legacy_request_retains_old_semantics() -> None:
    loop, pf, _ = context()
    assert send(loop, pf, "move_request", target_x=0, target_y=1, gait="walk") is None
    assert loop.state.entities["chenmo"].gait == "walk"
    assert loop.state.entities["chenmo"].path == ((0, 1),)
    loop, pf, _ = context()
    assert send(loop, pf, "move_request", target_x=0, target_y=1) is None
    assert loop.state.entities["chenmo"].gait is None
    assert loop.state.entities["chenmo"].path == ((0, 0), (0, 1))


def test_jump_request_changes_server_state_and_retains_completed_render_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ws, "_VOXEL_RUNTIME", None)
    loop, pf, _ = context()
    reply = send(loop, pf)
    assert loop.state.entities["chenmo"].jump is not None
    assert loop.state.entities["chenmo"].jump.airborne
    assert reply is not None and reply["type"] == "state_delta"
    assert reply["actors"][0]["jump"]["active"]
    loop.advance_frame(0.6)
    actor = ws.snapshot_payload(loop, pf.tile_map)["actors"][0]
    assert actor["x"] == 1 and actor["y"] == 0
    assert actor["elevation"] == 2 and actor["gait"] == "walk"
    assert not actor["jump"]["active"] and actor["jump"]["progress"] == 1
    token = actor["jump"]["rtoken"]
    assert send(loop, pf, "move_request", target_x=1, target_y=1, gait="run") is None
    loop.advance_frame(1)
    actor = ws.snapshot_payload(loop, pf.tile_map)["actors"][0]
    assert (actor["x"], actor["y"]) == (1, 1)
    assert actor["jump"]["rtoken"] == token
    assert actor["elevation"] == 2


@pytest.mark.parametrize(
    "fields",
    [
        {"target_x": True},
        {"target_x": 1.5},
        {"target_x": -1},
        {"target_x": 4},
        {"gait": "fly"},
        {"gait": None},
        {"entity_id": "villager_01"},
        {"elevation": 3},
        {"duration": 1},
        {"start_height": 3},
    ],
)
def test_invalid_jump_never_mutates_world(fields: dict[str, Any]) -> None:
    loop, pf, _ = context()
    before = loop.state.state_hash()
    response = send(loop, pf, **fields)
    assert response is not None and response["type"] == "error"
    assert response["ref"] == "jump_request" and response["code"] == "bad_target"
    assert loop.state.state_hash() == before


def test_jump_snapshot_never_exposes_internal_tick_or_entity_identifiers() -> None:
    loop, pf, _ = context()
    send(loop, pf)
    frame = ws.snapshot_payload(loop, pf.tile_map)
    actor = frame["actors"][0]
    assert actor.get("jump") is not None
    banned = {"tick", "seed", "world_seed", "entity_id", "started_at", "landed_at", "seq"}

    def check(value: Any) -> None:
        if isinstance(value, dict):
            assert not (set(value) & banned)
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    check(actor)


def test_second_jump_is_rejected_and_ground_move_does_not_interrupt_flight() -> None:
    loop, pf, _ = context()
    send(loop, pf)
    before = loop.state
    reply = send(loop, pf)
    assert reply["code"] == "bad_target"
    assert send(loop, pf, "move_request", target_x=0, target_y=1, gait="run") is None
    assert loop.state == before


@pytest.mark.asyncio
async def test_rebuilt_ground_and_player_surface_share_height_one_bank_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sim.api import main
    from sim.core.events import tile_changed_event, voxel_edited_event

    _loop, _, view = context()
    edit = voxel_edited_event(0, x=0, y=1, action="place")
    rows = [
        edit.model_copy(update={"payload": {**edit.payload, "height": 1}}).to_store_dict(),
        tile_changed_event(0, 0, 1, 0, height=1).to_store_dict(),
    ]

    class History:
        async def read_branch_history(self) -> Any:
            return rows

    monkeypatch.setattr(main, "_default_map", lambda: view.tile_map)
    monkeypatch.setattr(main, "_voxel_height_lookup", lambda: view.height_at)
    result = await main.rebuild_surface(History())
    ground = await main.rebuild_tile_map(History())
    assert result.height_at(0, 1) == 1 and not result.tile_map.is_walkable(0, 1)
    assert not ground.is_walkable(0, 1)


def test_flush_observer_does_not_apply_legacy_height_twice() -> None:
    from sim.core.events import voxel_edited_event

    _, _, view = context()
    event = voxel_edited_event(0, x=2, y=0, action="dig")
    view.observe(event)
    assert view.height_at(2, 0) == 2
    view.observe_unseen([event])
    assert view.height_at(2, 0) == 2
    view.mark_flushed([event])
    # Reusing a legacy event as another logged fact is not global event dedup.
    view.observe(event)
    assert view.height_at(2, 0) == 1
