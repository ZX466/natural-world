"""Material identity survives placement, excavation, projection and replay."""

import pytest

from sim.agent.voxel_exec import DIG_TICKS, VoxelRejected
from sim.api import voxel_view, ws
from sim.core.events import EventKind, tile_changed_event
from sim.tests.test_voxel_runtime import setup_runtime, stock_events


@pytest.mark.parametrize(("material", "height"), [("earth", 1), ("stone", 2), ("wood", 3)])
def test_place_dig_cycle_returns_exactly_the_requested_material(material, height):
    runtime, state, maps, _, _, commit = setup_runtime()
    grants = stock_events()
    runtime.observe(grants)
    placed = runtime.request("place", 3, 1, state, material=material)
    assert placed[0].payload["material_id"] == material
    assert placed[0].payload["height"] == height
    assert placed[2].payload["tile_id"] == 0
    commit(placed)
    assert runtime.height_at(3, 1) == height
    assert not maps[0].is_walkable(3, 1)
    assert runtime.snapshot()["inventory"][material] == 0
    with pytest.raises(VoxelRejected):
        runtime.request("place", 3, 1, state, material=material)
    runtime.request("dig_start", 3, 1, state)
    dug = runtime.tick(state, state.tick + DIG_TICKS)
    assert dug[0].payload["material_id"] == material
    assert dug[0].payload["height"] == 1
    assert dug[2].payload["tile_id"] == 7
    commit(dug)
    assert maps[0].is_walkable(3, 1)
    assert runtime.snapshot()["inventory"] == {"earth": 1, "stone": 1, "wood": 1}
    with pytest.raises(VoxelRejected):
        runtime.request("dig_start", 3, 1, state)


@pytest.mark.parametrize("material", ["earth", "stone", "wood"])
def test_restored_placement_keeps_material_and_single_unit_refund(material):
    runtime, state, maps, _, _, commit = setup_runtime()
    grants = stock_events()
    runtime.observe(grants)
    placed = runtime.request("place", 3, 1, state, material=material)
    commit(placed)
    runtime.restore_from_events([event.to_store_dict() for event in [*grants, *placed]])
    runtime.request("dig_start", 3, 1, state)
    dug = runtime.tick(state, state.tick + DIG_TICKS)
    assert dug[1].payload["material_id"] == material
    commit(dug)
    assert maps[0].is_walkable(3, 1)
    assert runtime.snapshot()["inventory"] == {"earth": 1, "stone": 1, "wood": 1}


@pytest.mark.parametrize("material", ["iron", "", None, 1, True, []])
def test_unknown_material_is_rejected_without_edit_or_reservation(material):
    runtime, state, _, _, _, _ = setup_runtime()
    runtime.observe(stock_events())
    before = runtime.snapshot()
    with pytest.raises(VoxelRejected):
        runtime.request("place", 3, 1, state, material=material)
    assert runtime.snapshot() == before
    assert runtime.request("place", 3, 1, state)[0].payload["material_id"] == "earth"


def test_default_earth_does_not_consume_material_implied_by_target_height():
    runtime, state, _, _, _, _ = setup_runtime()
    runtime.observe(stock_events())
    earth = runtime.request("place", 3, 1, state)
    stone = runtime.request("place", 1, 2, state, material="stone")
    assert earth[0].payload["material_id"] == "earth"
    assert stone[0].payload["material_id"] == "stone"
    with pytest.raises(VoxelRejected, match="没有石料"):
        runtime.request("place", 4, 1, state, material="stone")


def test_tile_change_preserves_projected_material_and_restoring_drops_future_rows():
    runtime, state, _, _, _, commit = setup_runtime()
    runtime.observe(stock_events())
    placed = runtime.request("place", 3, 1, state, material="wood")
    commit(placed)
    voxel_view.reset_voxel_edits()
    try:
        voxel_view.apply_voxel_events(placed, ground_gid=lambda x, y: 7, height_of=runtime._height)
        # Structure changes may alter collision, but must not replace voxel material.
        changed = tile_changed_event(101, 3, 1, 7)
        voxel_view.apply_voxel_events(
            [changed], ground_gid=lambda x, y: 7, height_of=runtime._height
        )
        assert voxel_view.voxel_snapshot_rows() == [
            {"x": 3, "y": 1, "action": "place", "gid": 0, "height": 3, "material": "wood"}
        ]
        voxel_view.restore_voxel_edits(
            [event.to_store_dict() for event in [*placed, changed]],
            ground_gid=lambda x, y: 7,
            height_of=runtime._height,
        )
        assert voxel_view.voxel_snapshot_rows()[0]["material"] == "wood"
        voxel_view.restore_voxel_edits([], ground_gid=lambda x, y: 7, height_of=runtime._height)
        assert voxel_view.voxel_snapshot_rows() == []
    finally:
        voxel_view.reset_voxel_edits()


def test_gateway_forwards_material_to_the_runtime_and_seals_unknown_values():
    from sim.core.clock import GameClock
    from sim.core.tick import TickLoop
    from sim.core.world import build_default_bus
    from sim.world.pathfinding import Pathfinder

    runtime, state, maps, _, _, _ = setup_runtime()
    runtime.observe(stock_events())
    loop = TickLoop(GameClock(), build_default_bus(), state)
    ws.set_voxel_runtime(runtime)
    try:
        fields = {"type": "voxel_request", "channel": "render", "action": "place", "x": 3, "y": 1}
        reply = ws.handle_client_message({**fields, "material": "stone"}, loop, Pathfinder(maps[0]))
        assert reply is None
        edit = next(
            event for event in loop.pending_events if event.event_type is EventKind.VOXEL_EDITED
        )
        assert edit.payload["height"] == 2 and edit.payload["material_id"] == "stone"
        before = list(loop.pending_events)
        reply = ws.handle_client_message({**fields, "material": "iron"}, loop, Pathfinder(maps[0]))
        assert ws.frames_of(reply)[0]["code"] == "bad_target"
        assert loop.pending_events == before
    finally:
        ws.set_voxel_runtime(None)
