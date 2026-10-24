"""V4a gateway, sealed event contracts, presentation fold and private inventory."""

import pytest
from fastapi import WebSocket
from pydantic import ValidationError

from sim.api import ws
from sim.core.clock import GameClock
from sim.core.events import VoxelEditedPayload
from sim.core.tick import TickLoop
from sim.core.world import build_default_bus
from sim.tests.test_voxel_runtime import setup_runtime
from sim.world.pathfinding import Pathfinder


@pytest.fixture
def scene():
    runtime, state, maps, _water, _occupied, commit = setup_runtime()
    loop = TickLoop(clock=GameClock(), bus=build_default_bus(), state=state)
    pf = Pathfinder(tile_map=maps[0])
    ws.set_voxel_runtime(runtime)
    ws.reset_voxel_edits()
    yield runtime, loop, pf, maps, commit
    ws.set_voxel_runtime(None)
    ws.reset_voxel_edits()


def test_voxel_dispatch_and_snapshot_delta_use_protocol_112(scene):
    runtime, loop, pf, maps, commit = scene
    assert ws._PROTOCOL_VERSION == "1.12"
    assert (
        ws.handle_client_message(
            {"type": "voxel_request", "channel": "render", "action": "dig_start", "x": 2, "y": 1},
            loop,
            pf,
        )
        is None
    )
    assert loop.pending_events == []
    assert runtime.snapshot()["dig"]["progress"] == 0
    events = runtime.tick(loop.state, 130)
    commit(events)
    ws.apply_voxel_events(events, ground_gid=lambda x, y: 7)
    expected = [{"x": 2, "y": 1, "action": "dig", "gid": 7}]
    assert ws.snapshot_payload(loop, maps[0])["voxel_edits"] == expected
    assert ws.delta_payload(loop, set())["voxel_edits"] == expected
    assert "voxel_edits" not in ws.delta_payload(loop, set())


@pytest.mark.parametrize(
    "fields",
    [
        {"x": True},
        {"x": "2"},
        {"x": -1},
        {"x": 99},
        {"action": "mine_all"},
        {"by": "villager_01"},
        {"quantity": 100},
        {"y": None},
    ],
)
def test_invalid_voxel_input_is_sealed_and_has_no_events(scene, fields):
    runtime, loop, pf, _, _ = scene
    reply = ws.handle_client_message(
        {
            "type": "voxel_request",
            "channel": "render",
            "action": "dig_start",
            "x": 2,
            "y": 1,
            **fields,
        },
        loop,
        pf,
    )
    frames = ws.frames_of(reply)
    assert [frame["type"] for frame in frames] == ["error", "voxel_state"]
    assert frames[0]["ref"] == "voxel_request" and frames[0]["code"] == "bad_target"
    assert frames[1]["inventory"] == {"earth": 0}
    assert runtime.snapshot()["dig"] is None
    assert loop.pending_events == []


@pytest.mark.parametrize(
    "fields",
    [
        {"by": "villager_01"},
        {"quantity": 2},
        {"quantity": True},
        {"material_id": "stone"},
        {"inventory": {"earth": 99}},
        {"x": True},
    ],
)
def test_voxel_event_payload_has_only_authorized_semantics(fields):
    with pytest.raises(ValidationError):
        VoxelEditedPayload.model_validate({"x": 2, "y": 1, "action": "dig", **fields})


def test_restore_edits_folds_tile_truth_and_clears_future_cells(scene):
    runtime, loop, _, _, commit = scene
    runtime.request("dig_start", 2, 1, loop.state)
    dug = runtime.tick(loop.state, 130)
    commit(dug)
    placed = runtime.request("place", 3, 1, loop.state)
    commit(placed)
    rows = [event.to_store_dict() for event in [*dug, *placed]]
    ws.restore_voxel_edits(rows, ground_gid=lambda x, y: 7)
    assert ws.snapshot_payload(loop, scene[3][0])["voxel_edits"] == [
        {"x": 2, "y": 1, "action": "dig", "gid": 7},
        {"x": 3, "y": 1, "action": "place", "gid": 0},
    ]
    ws.restore_voxel_edits(rows[:3], ground_gid=lambda x, y: 7)
    assert ws.snapshot_payload(loop, scene[3][0])["voxel_edits"] == [
        {"x": 2, "y": 1, "action": "dig", "gid": 7},
    ]
    ws.restore_voxel_edits([], ground_gid=lambda x, y: 7)
    assert ws.snapshot_payload(loop, scene[3][0]).get("voxel_edits", []) == []


class Socket(WebSocket):
    def __init__(self):
        self.frames = []

    async def send_json(self, data, mode="text"):
        self.frames.append(data)


async def test_inventory_updates_require_authentication_and_disconnect_cancels_owner(scene):
    runtime, loop, _, _, _ = scene
    manager = ws.ConnectionManager()
    private, unauthenticated = Socket(), Socket()
    control = ws.ControlState()
    manager.register(private, control=control)
    manager.register(unauthenticated)
    manager.mark_authenticated(private)
    runtime.request("dig_start", 2, 1, loop.state, owner=control)
    await ws.flush_voxel_updates(manager)
    assert private.frames[-1]["type"] == "voxel_state"
    assert unauthenticated.frames == []
    manager.unregister(private)
    assert runtime.snapshot()["dig"] is None
    assert runtime.tick(loop.state, 130) == []


async def test_completion_error_is_only_sent_to_its_owner(scene):
    runtime, loop, _, _, _ = scene
    manager = ws.ConnectionManager()
    first, second = Socket(), Socket()
    control = ws.ControlState()
    manager.register(first, control=control)
    manager.register(second)
    manager.mark_authenticated(first)
    manager.mark_authenticated(second)
    runtime.request("dig_start", 2, 1, loop.state, owner=control)
    loop.state = loop.state.model_copy(update={"entities": {}})
    runtime.tick(loop.state, 130)
    await ws.flush_voxel_updates(manager)
    assert any(frame["type"] == "error" for frame in first.frames)
    assert not any(frame["type"] == "error" for frame in second.frames)


def test_rejection_text_is_a_closed_literal_set_not_an_exception_channel():
    assert ws._voxel_bad_target("DB busy: internal path") == ws._error_frame(
        "voxel_request", "bad_target", "这处地方动不了土。"
    )
    assert ws._voxel_bad_target("行囊里没有土了。")["message"] == "行囊里没有土了。"
