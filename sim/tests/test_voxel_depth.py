"""Committed layer depth, collision and legacy replay contracts for protocol 1.14."""

import pytest
from pydantic import ValidationError

from sim.api import voxel_view
from sim.core.events import VoxelEditedPayload, tile_changed_event, voxel_edited_event
from sim.tests.test_voxel_runtime import dig_once, setup_runtime


def test_high_column_digs_one_layer_at_a_time_and_only_opens_at_one():
    runtime, state, maps, _, _, commit = setup_runtime(heights={(2, 1): 3})
    first = dig_once(runtime, state)
    assert first[0].payload["height"] == 2
    assert first[0].payload["material_id"] == "wood"
    assert first[2].payload["tile_id"] == 0
    commit(first)
    assert not maps[0].is_walkable(2, 1)
    state = state.model_copy(update={"tick": 130})
    second = dig_once(runtime, state)
    assert second[0].payload["height"] == 1
    assert second[0].payload["material_id"] == "stone"
    assert second[2].payload["tile_id"] == 7
    commit(second)
    assert maps[0].is_walkable(2, 1)
    assert runtime.snapshot()["inventory"] == {"earth": 0, "stone": 1, "wood": 1}


def test_earth_bank_yields_one_earth_but_zero_height_never_becomes_walkable_or_diggable():
    runtime, state, maps, _, _, commit = setup_runtime()
    events = dig_once(runtime, state)
    assert events[0].payload["height"] == 0
    assert events[2].payload["tile_id"] == 0
    commit(events)
    assert not maps[0].is_walkable(2, 1)
    assert runtime.snapshot()["inventory"]["earth"] == 1
    with pytest.raises(ValueError, match="水面上动不了土"):
        runtime.request("dig_start", 2, 1, state)
    placed = runtime.request("place", 3, 1, state)
    assert placed[0].payload["height"] == 2
    assert placed[0].payload["material_id"] == "earth"
    commit(placed)
    assert runtime.snapshot()["inventory"]["earth"] == 0
    assert not maps[0].is_walkable(3, 1)


def test_pending_edit_does_not_publish_depth_and_replay_restores_the_next_layer():
    runtime, state, maps, _, _, commit = setup_runtime(heights={(2, 1): 3})
    first = dig_once(runtime, state)
    assert runtime.height_at(2, 1) == 3
    commit(first)
    assert runtime.height_at(2, 1) == 2
    runtime.restore_from_events([event.to_store_dict() for event in first])
    assert runtime.height_at(2, 1) == 2
    assert not maps[0].is_walkable(2, 1)
    second = dig_once(runtime, state.model_copy(update={"tick": 130}))
    assert second[0].payload["height"] == 1
    assert second[0].payload["material_id"] == "stone"
    runtime.restore_from_events([])
    assert runtime.height_at(2, 1) == 3


@pytest.mark.parametrize("height", [-1, 4, True, 1.5, "1"])
def test_event_rejects_invalid_result_heights(height):
    with pytest.raises(ValidationError):
        VoxelEditedPayload.model_validate({"x": 2, "y": 1, "action": "dig", "height": height})


def test_event_accepts_an_explicit_result_height_and_retains_legacy_rows():
    payload = VoxelEditedPayload.model_validate(
        {"x": 2, "y": 1, "action": "dig", "height": 1}
    )
    assert payload.height == 1
    assert "height" not in voxel_edited_event(1, x=2, y=1, action="dig").payload


def test_legacy_replay_folds_depth_but_preserves_original_material_stock():
    runtime, _, _, _, _, _ = setup_runtime(heights={(2, 1): 3})
    edits = [voxel_edited_event(tick, x=2, y=1, action="dig") for tick in (1, 2)]
    runtime.restore_from_events([edit.to_store_dict() for edit in edits])
    assert runtime.height_at(2, 1) == 1
    voxel_view.reset_voxel_edits()
    try:
        voxel_view.apply_voxel_events(
            [edits[0], tile_changed_event(1, 2, 1, 7)],
            ground_gid=lambda x, y: 7,
            height_of=lambda x, y: 3,
        )
        assert voxel_view.voxel_snapshot_rows() == [
            {"x": 2, "y": 1, "action": "dig", "gid": 0, "height": 2}
        ]
        voxel_view.restore_voxel_edits(
            [event.to_store_dict() for event in edits],
            ground_gid=lambda x, y: 7,
            height_of=lambda x, y: 3,
        )
        assert voxel_view.voxel_snapshot_rows() == [
            {"x": 2, "y": 1, "action": "dig", "gid": 7, "height": 1}
        ]
    finally:
        voxel_view.reset_voxel_edits()


async def test_server_map_rebuild_normalizes_heightless_voxel_history():
    from sim.api.main import VOXEL_HEIGHT_PATH, _default_map, _ground_tile_id, rebuild_tile_map

    import json

    heights = json.loads(VOXEL_HEIGHT_PATH.read_text(encoding="utf-8"))
    tile_map = _default_map()
    x, y = next(
        (i % heights["w"], i // heights["w"])
        for i, height in enumerate(heights["h_values"])
        if height == 3
    )
    rows = [
        voxel_edited_event(1, x=x, y=y, action="dig").to_store_dict(),
        tile_changed_event(1, x, y, _ground_tile_id(tile_map, x, y)).to_store_dict(),
    ]

    class History:
        async def read_branch_history(self):
            return rows

    restored = await rebuild_tile_map(History())
    assert not restored.is_walkable(x, y)
