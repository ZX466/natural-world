"""Wave B: real runtime cells use the generic light snapshot/delta channel."""

import asyncio
import json
from contextlib import suppress
from dataclasses import replace
from typing import Any, cast

import pytest

from sim.api import ws
from sim.core.clock import GameClock
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.npc.fire_runtime import FireRuntime
from sim.tests.test_p_rebuild_tile_map_contract import make_open_map


def bind(runtime):
    from sim.npc import light_view

    setter = getattr(ws, "set_light_provider", None)
    assert setter is not None, "the real light provider is not wired"
    setter(lambda: light_view.fire_lights(runtime.cells))


@pytest.fixture(autouse=True)
def reset_provider():
    setter = getattr(ws, "set_light_provider", None)
    if setter is not None:
        setter(None)
    yield
    setter = getattr(ws, "set_light_provider", None)
    if setter is not None:
        setter(None)


def scene():
    return TickLoop(
        GameClock(speed=1),
        build_default_bus(),
        WorldState(world_seed=42, entities={"chenmo": EntityState(entity_id="chenmo", pos=(1, 1))}),
    ), make_open_map()


def test_real_cells_project_only_existing_observable_fields_without_mutation():
    runtime = FireRuntime()
    events = runtime.ignite_at(tick=0, x=3, y=4)
    original = runtime.cells
    bind(runtime)
    loop, tile_map = scene()
    first = ws.snapshot_payload(loop, tile_map)["lights"]
    assert len(first) == 1
    assert set(first[0]) == {"rtoken", "x", "y", "kind", "radius", "flicker"}
    assert {key: first[0][key] for key in ("x", "y", "kind", "radius", "flicker")} == {
        "x": 3,
        "y": 4,
        "kind": "fire",
        "radius": 5,
        "flicker": 0.4,
    }
    internal_id = events[0].payload["fire_id"]
    assert isinstance(internal_id, str)
    assert internal_id not in json.dumps(first)
    assert ws.snapshot_payload(loop, tile_map)["lights"] == first
    assert runtime.cells is original


def test_birth_no_change_extinction_and_snapshot_cannot_consume_pending_removal():
    runtime = FireRuntime()
    bind(runtime)
    loop, tile_map = scene()
    assert "lights" not in ws.delta_payload(loop, set())
    runtime.ignite_at(tick=0, x=3, y=4)
    full = ws.snapshot_payload(loop, tile_map)["lights"]
    added = ws.delta_payload(loop, set())["lights"]
    assert added == [{"op": "add", **full[0]}]
    assert "lights" not in ws.delta_payload(loop, set())
    ended = []
    for tick in range(1, 13):
        ended.extend(runtime.step(tick=tick, walkable=set()))
    assert ended and not runtime.cells
    assert ws.snapshot_payload(loop, tile_map)["lights"] == []  # Another client joins.
    assert ws.delta_payload(loop, set())["lights"] == [
        {"op": "remove", "rtoken": full[0]["rtoken"]}
    ]
    assert "lights" not in ws.delta_payload(loop, set())


def test_tokens_remain_stable_across_replay_and_distinguish_cells():
    runtime = FireRuntime()
    history = [*runtime.ignite_at(tick=0, x=3, y=4), *runtime.ignite_at(tick=0, x=4, y=4)]
    bind(runtime)
    loop, tile_map = scene()
    before = ws.snapshot_payload(loop, tile_map)["lights"]
    assert len({row["rtoken"] for row in before}) == 2
    runtime.restore_from_events(event.to_store_dict() for event in history)
    assert ws.snapshot_payload(loop, tile_map)["lights"] == before
    runtime.cells = tuple(reversed(runtime.cells))
    assert ws.snapshot_payload(loop, tile_map)["lights"] == before
    first, second = runtime.cells
    runtime.cells = (first, replace(second, fire_id=first.fire_id))
    assert len({row["rtoken"] for row in ws.snapshot_payload(loop, tile_map)["lights"]}) == 2


def test_snapshot_only_birth_is_removed_after_extinction_before_any_add_delta():
    runtime = FireRuntime()
    runtime.ignite_at(tick=0, x=3, y=4)
    bind(runtime)
    loop, tile_map = scene()
    shown = ws.snapshot_payload(loop, tile_map)["lights"]
    assert len(shown) == 1
    for tick in range(1, 13):
        runtime.step(tick=tick, walkable=set())
    assert ws._lights_changed() is True
    assert ws.delta_payload(loop, set())["lights"] == [
        {"op": "remove", "rtoken": shown[0]["rtoken"]}
    ]
    assert ws._lights_changed() is False
    assert "lights" not in ws.delta_payload(loop, set())


async def test_stationary_world_driver_broadcasts_light_changes_without_actor_movement():
    runtime = FireRuntime()
    bind(runtime)
    loop, tile_map = scene()
    for event in runtime.ignite_at(tick=0, x=3, y=4):
        loop.enqueue(event)

    class Socket:
        def __init__(self):
            self.frames = []
            self.ready = asyncio.Event()

        async def send_json(self, payload):
            self.frames.append(payload)
            if payload.get("type") == "state_delta" and payload.get("lights"):
                self.ready.set()

    socket = Socket()
    manager = ws.ConnectionManager()
    manager.register(cast("Any", socket))
    task = asyncio.create_task(ws.run_world_driver(loop, manager, tile_map))
    try:
        await asyncio.wait_for(socket.ready.wait(), 1)
        frame = next(frame for frame in socket.frames if frame.get("lights"))
        assert frame["actors"] == []
        assert frame["lights"][0]["op"] == "add"
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
