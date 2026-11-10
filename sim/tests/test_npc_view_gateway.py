"""NPC narrative snapshots never consume another observer's pending changes."""

import asyncio
from contextlib import suppress
from typing import Any, cast

import pytest

from sim.api import ws
from sim.api.npc_view import NpcViewRow
from sim.core.clock import GameClock
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.tests.test_p_rebuild_tile_map_contract import make_open_map


@pytest.fixture(autouse=True)
def clean_views():
    ws.clear_npc_views()
    yield
    ws.clear_npc_views()


def scene():
    return TickLoop(
        GameClock(speed=0),
        build_default_bus(),
        WorldState(
            world_seed=42,
            entities={"chenmo": EntityState(entity_id="chenmo", pos=(1, 1))},
        ),
    ), make_open_map()


def item(bond="见面会同你搭句话。") -> NpcViewRow:
    return {"rtoken": ws._rtoken("friend"), "name": "小满", "health": [], "bond": bond, "knows": []}


def test_snapshot_is_full_and_does_not_consume_unbroadcast_changes():
    loop, tile_map = scene()
    ws.set_npc_views([item()])
    full = ws.snapshot_payload(loop, tile_map)["npc_views"]
    assert full == [item()]
    assert ws._npc_views_changed()
    assert ws.delta_payload(loop, set())["npc_views"] == full
    assert "npc_views" not in ws.delta_payload(loop, set())
    ws.set_npc_views([item("愿意和你多说几句。")])
    assert ws.snapshot_payload(loop, tile_map)["npc_views"] == [item("愿意和你多说几句。")]
    assert ws.delta_payload(loop, set())["npc_views"] == [item("愿意和你多说几句。")]


def test_snapshot_only_entries_still_send_removal_and_reset_clears_both_baselines():
    loop, tile_map = scene()
    ws.set_npc_views([item()])
    assert ws.snapshot_payload(loop, tile_map)["npc_views"] == [item()]
    ws.set_npc_views([])
    assert ws.snapshot_payload(loop, tile_map)["npc_views"] == []
    assert ws._npc_views_changed()
    assert ws.delta_payload(loop, set())["npc_views"] == [
        {"op": "remove", "rtoken": item()["rtoken"]}
    ]
    assert not ws._npc_views_changed()
    ws.set_npc_views([item()])
    ws.clear_npc_views()
    assert ws.snapshot_payload(loop, tile_map)["npc_views"] == []
    assert not ws._npc_views_changed()


def test_payload_arrays_cannot_mutate_current_or_broadcast_narrative_state():
    loop, tile_map = scene()
    original = item()
    ws.set_npc_views([original])
    original["health"].append("bad")
    first = ws.snapshot_payload(loop, tile_map)["npc_views"]
    assert first[0]["health"] == []
    first[0]["health"].append("bad snapshot")
    assert ws.delta_payload(loop, set())["npc_views"][0]["health"] == []
    assert not ws._npc_views_changed()


def test_reverted_state_is_resent_after_a_snapshot_exposed_a_temporary_version():
    loop, tile_map = scene()
    ws.set_npc_views([item()])
    ws.delta_payload(loop, set())
    temporary = item("愿意和你多说几句。")
    temporary["health"] = ["腕上旧伤发作得厉害。"]
    ws.set_npc_views([temporary])
    assert ws.snapshot_payload(loop, tile_map)["npc_views"] == [temporary]
    ws.set_npc_views([item()])
    # A later third observer sees the old baseline; that must not erase the
    # second observer's exposure to the temporary hidden/narrative version.
    assert ws.snapshot_payload(loop, tile_map)["npc_views"] == [item()]
    assert ws._npc_views_changed()
    assert ws.delta_payload(loop, set())["npc_views"] == [item()]
    assert not ws._npc_views_changed()


async def test_stationary_world_driver_sends_narrative_change_without_any_events():
    loop, tile_map = scene()
    ws.set_npc_views([item()])

    class Socket:
        def __init__(self):
            self.frames = []
            self.ready = asyncio.Event()

        async def send_json(self, payload):
            self.frames.append(payload)
            if payload.get("npc_views"):
                self.ready.set()

    socket = Socket()
    manager = ws.ConnectionManager()
    manager.register(cast(Any, socket))
    task = asyncio.create_task(ws.run_world_driver(loop, manager, tile_map))
    try:
        await asyncio.wait_for(socket.ready.wait(), 1)
        frame = next(f for f in socket.frames if f.get("npc_views"))
        assert frame["type"] == "state_delta"
        assert frame["actors"] == [] and frame["npc_views"] == [item()]
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def test_reappeared_baseline_row_is_resent_after_an_empty_snapshot():
    loop, tile_map = scene()
    ws.set_npc_views([item()])
    ws.delta_payload(loop, set())
    ws.set_npc_views([])
    assert ws.snapshot_payload(loop, tile_map)["npc_views"] == []
    ws.set_npc_views([item()])
    assert ws._npc_views_changed()
    assert ws.delta_payload(loop, set())["npc_views"] == [item()]
    assert not ws._npc_views_changed()
