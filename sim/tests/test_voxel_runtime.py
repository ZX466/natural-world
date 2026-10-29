"""V4a: only Chenmo, deterministic mining, material conservation and replay."""

import pytest

from sim.agent.voxel_exec import DIG_TICKS, VoxelRejected, VoxelRuntime
from sim.core.clock import GameClock
from sim.core.events import EventKind, material_moved_event, voxel_edited_event
from sim.core.persistence.event_validation import validate_store_row
from sim.core.persistence.npc_store import NpcStore
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.tests.test_p_rebuild_tile_map_contract import make_open_map


def setup_runtime(*, heights=None):
    maps = [make_open_map().with_collision(2, 1, walkable=False)]
    water, occupied = set(), set()
    heights = heights or {}
    runtime = VoxelRuntime(
        tile_map=lambda: maps[0],
        height_of=lambda x, y: 0 if (x, y) in water else heights.get((x, y), 1),
        ground_gid=lambda x, y: 7,
        occupied=lambda x, y: (x, y) in occupied,
    )
    state = WorldState(
        world_seed=42, tick=100, entities={"chenmo": EntityState(entity_id="chenmo", pos=(1, 1))}
    )

    def commit(events):
        for event in events:
            validate_store_row(event.to_store_dict())
            if event.event_type is EventKind.TILE_CHANGED:
                maps[0] = maps[0].with_collision(
                    event.payload["x"], event.payload["y"], walkable=event.payload["tile_id"] != 0
                )
        runtime.observe(events)

    return runtime, state, maps, water, occupied, commit


def dig_once(runtime, state, owner=None):
    assert runtime.request("dig_start", 2, 1, state, owner=owner) == []
    assert runtime.tick(state, state.tick + DIG_TICKS - 1) == []
    return runtime.tick(state, state.tick + DIG_TICKS)


def test_dig_finishes_after_exactly_thirty_ticks_and_commits_one_unit():
    runtime, state, maps, _, _, commit = setup_runtime()
    events = dig_once(runtime, state)
    assert [event.event_type for event in events] == [
        EventKind.VOXEL_EDITED,
        EventKind.MATERIAL_MOVED,
        EventKind.TILE_CHANGED,
    ]
    assert events[0].payload == {
        "x": 2,
        "y": 1,
        "action": "dig",
        "height": 0,
        "material_id": "earth",
        "quantity": 1,
        "by": "chenmo",
    }
    assert events[1].payload["from_ref"] == "world:tile"
    assert events[1].payload["to_ref"] == "npc:chenmo"
    assert events[1].payload["reason"] == "dig_yield"
    assert events[1].payload["quantity"] == 1
    assert events[2].payload["tile_id"] == 0
    assert runtime.snapshot()["inventory"] == {"earth": 0, "stone": 0, "wood": 0}
    commit(events)
    assert not maps[0].is_walkable(2, 1)
    assert runtime.snapshot() == {"dig": None, "inventory": {"earth": 1, "stone": 0, "wood": 0}}
    assert runtime.tick(state, 1000) == []


def test_place_checks_stock_and_reserves_pending_consumption():
    runtime, state, maps, _, _, commit = setup_runtime()
    with pytest.raises(VoxelRejected):
        runtime.request("place", 3, 1, state)
    commit(dig_once(runtime, state))
    events = runtime.request("place", 3, 1, state)
    assert events[0].payload["action"] == "place"
    assert events[1].payload["reason"] == "place_consumed"
    assert events[1].payload["from_ref"] == "npc:chenmo"
    assert events[1].payload["to_ref"] == "world:tile"
    assert events[2].payload["tile_id"] == 0
    with pytest.raises(VoxelRejected):
        runtime.request("place", 4, 1, state)
    commit(events)
    assert not maps[0].is_walkable(3, 1)
    assert runtime.snapshot()["inventory"] == {"earth": 0, "stone": 0, "wood": 0}
    with pytest.raises(VoxelRejected):
        runtime.request("place", 4, 1, state)


def test_progress_is_throttled_to_six_ticks_and_cancel_has_no_world_event():
    runtime, state, _, _, _, _ = setup_runtime()
    owner = object()
    runtime.request("dig_start", 2, 1, state, owner=owner)
    for tick in range(101, 125):
        assert runtime.tick(state, tick) == []
    updates = [payload for _, payload in runtime.drain_updates() if "dig" in payload]
    assert [payload["dig"]["progress"] for payload in updates] == [0, 0.2, 0.4, 0.6, 0.8]
    runtime.request("dig_cancel", 2, 1, state, owner=owner)
    assert runtime.snapshot()["dig"] is None
    assert runtime.tick(state, 1000) == []
    assert runtime.snapshot()["inventory"]["earth"] == 0


def test_cancel_from_another_connection_does_not_cancel_the_owner():
    runtime, state, _, _, _, commit = setup_runtime()
    owner = object()
    runtime.request("dig_start", 2, 1, state, owner=owner)
    runtime.request("dig_cancel", 2, 1, state, owner=object())
    assert runtime.snapshot()["dig"] is not None
    commit(runtime.tick(state, 130))
    assert runtime.snapshot()["inventory"]["earth"] == 1


def test_repeated_start_keeps_the_original_deadline_and_pending_targets_are_idempotent():
    runtime, state, _, _, _, commit = setup_runtime()
    owner = object()
    runtime.request("dig_start", 2, 1, state, owner=owner)
    runtime.request("dig_start", 2, 1, state.model_copy(update={"tick": 110}), owner=owner)
    events = runtime.tick(state, 130)
    assert len(events) == 3
    with pytest.raises(VoxelRejected):
        runtime.request("dig_start", 2, 1, state, owner=owner)
    commit(events)
    with pytest.raises(VoxelRejected):
        runtime.request("dig_start", 2, 1, state, owner=owner)


@pytest.mark.parametrize("position", [(-1, 1), (32, 1), (2, 40), (8, 1), (True, 1), (2.5, 1)])
def test_bad_coordinates_and_distance_do_not_start_digging(position):
    runtime, state, _, _, _, _ = setup_runtime()
    with pytest.raises(VoxelRejected):
        x, y = position
        runtime.request("dig_start", x, y, state)
    assert runtime.snapshot() == {"dig": None, "inventory": {"earth": 0, "stone": 0, "wood": 0}}


@pytest.mark.parametrize("obstruction", ["water", "structure", "already_open"])
def test_water_structure_and_identical_state_are_rejected(obstruction):
    runtime, state, maps, water, occupied, _ = setup_runtime()
    if obstruction == "water":
        water.add((2, 1))
    elif obstruction == "structure":
        occupied.add((2, 1))
    else:
        maps[0] = maps[0].with_collision(2, 1, walkable=True)
    with pytest.raises(VoxelRejected):
        runtime.request("dig_start", 2, 1, state)
    assert runtime.tick(state, 200) == []


@pytest.mark.parametrize("change", ["range", "water", "structure", "incapacitated", "dead"])
def test_completion_revalidates_and_rejects_without_producing_events(change):
    runtime, state, _, water, occupied, _ = setup_runtime()
    runtime.request("dig_start", 2, 1, state)
    if change == "range":
        state = state.model_copy(
            update={
                "entities": {
                    "chenmo": state.entities["chenmo"].model_copy(update={"pos": (20, 20)})
                }
            }
        )
    elif change == "water":
        water.add((2, 1))
    elif change == "structure":
        occupied.add((2, 1))
    elif change == "incapacitated":
        state = state.model_copy(
            update={
                "entities": {
                    "chenmo": state.entities["chenmo"].model_copy(
                        update={"incapacitated_until": 200}
                    )
                }
            }
        )
    else:
        state = state.model_copy(update={"entities": {}})
    assert runtime.tick(state, 130) == []
    assert runtime.snapshot() == {"dig": None, "inventory": {"earth": 0, "stone": 0, "wood": 0}}
    assert any("error" in payload for _, payload in runtime.drain_updates())


def test_replay_restores_inventory_and_drops_unfinished_control_state():
    runtime, state, maps, _, _, commit = setup_runtime()
    events = dig_once(runtime, state)
    commit(events)
    placed = runtime.request("place", 3, 1, state)
    commit(placed)
    restored = VoxelRuntime(
        tile_map=lambda: maps[0],
        height_of=lambda x, y: 3,
        ground_gid=lambda x, y: 7,
        occupied=lambda x, y: False,
    )
    restored.restore_from_events([event.to_store_dict() for event in [*events, *placed]])
    assert restored.snapshot() == {"dig": None, "inventory": {"earth": 0, "stone": 0, "wood": 0}}
    assert restored.tick(state, 500) == []


def test_placing_a_wall_cancels_crossing_paths_using_existing_move_events():
    runtime, state, _, _, _, commit = setup_runtime()
    commit(dig_once(runtime, state))
    state = state.model_copy(
        update={
            "entities": {
                **state.entities,
                "villager_01": EntityState(
                    entity_id="villager_01", pos=(1, 1), path=((3, 1), (4, 1))
                ),
            }
        }
    )
    events = runtime.request("place", 3, 1, state)
    assert any(event.event_type is EventKind.MOVE for event in events)
    loop = TickLoop(clock=GameClock(), bus=build_default_bus(), state=state)
    for event in events:
        loop.enqueue(event)
    # Existing MOVE contracts keep their current-position first point; it is
    # consumed by the normal walker, and contains no route through the wall.
    assert loop.state.entities["villager_01"].path == ((1, 1),)
    assert (3, 1) not in loop.state.entities["villager_01"].path
    assert all(event.payload.get("by", "chenmo") == "chenmo" for event in events)


def test_same_inputs_generate_byte_identical_event_rows():
    first, state, _, _, _, _ = setup_runtime()
    second, _, _, _, _, _ = setup_runtime()
    left = dig_once(first, state)
    right = dig_once(second, state)
    assert [event.model_dump_json() for event in left] == [
        event.model_dump_json() for event in right
    ]
    replay_state = state.model_copy(update={"tick": 130})
    loop = TickLoop(clock=GameClock(), bus=build_default_bus(), state=replay_state)
    before = replay_state.state_hash()
    for event in left:
        loop.enqueue(event)
    assert loop.state.state_hash() == before


def test_foreign_fractional_earth_transfers_do_not_touch_player_stock():
    from sim.core.events import material_moved_event

    runtime, _, _, _, _, _ = setup_runtime()
    runtime.observe(
        [
            material_moved_event(
                100,
                transfer_id="foreign-earth",
                material_id="earth",
                quantity=0.25,
                from_ref="world:tile",
                to_ref="world:burned",
                reason="burned",
            )
        ]
    )
    assert runtime.snapshot()["inventory"] == {"earth": 0, "stone": 0, "wood": 0}


def test_dig_yields_each_cells_static_height_material_and_credits_separate_stock():
    runtime, state, maps, _, _, commit = setup_runtime(heights={(2, 1): 1, (3, 1): 2, (1, 2): 3})
    for x, y, material in [(2, 1, "earth"), (3, 1, "stone"), (1, 2, "wood")]:
        maps[0] = maps[0].with_collision(x, y, walkable=False)
        runtime.request("dig_start", x, y, state)
        events = runtime.tick(state, state.tick + DIG_TICKS)
        assert events[0].payload["material_id"] == material
        assert events[1].payload["material_id"] == material
        assert events[0].payload["quantity"] == events[1].payload["quantity"] == 1
        commit(events)
        state = state.model_copy(update={"tick": state.tick + DIG_TICKS})
    assert runtime.snapshot()["inventory"] == {"earth": 1, "stone": 1, "wood": 1}


@pytest.mark.parametrize(("height", "material"), [(1, "earth"), (2, "stone"), (3, "wood")])
def test_place_on_a_walkable_surface_requires_earth_after_each_yield(height, material):
    runtime, state, maps, _, _, commit = setup_runtime(heights={(2, 1): height})
    dug = dig_once(runtime, state)
    commit(dug)
    assert runtime.snapshot()["inventory"][material] == 1
    if material != "earth":
        with pytest.raises(VoxelRejected, match="没有土"):
            runtime.request("place", 3, 1, state.model_copy(update={"tick": 130}))
        assert runtime.snapshot()["inventory"][material] == 1
        return
    placed = runtime.request("place", 3, 1, state.model_copy(update={"tick": 130}))
    assert placed[0].payload["material_id"] == "earth"
    assert placed[0].payload["height"] == 2
    assert placed[1].payload["material_id"] == "earth"
    assert placed[1].payload["reason"] == "place_consumed"
    commit(placed)
    assert runtime.snapshot()["inventory"] == {"earth": 0, "stone": 0, "wood": 0}
    assert not maps[0].is_walkable(3, 1)


def stock_events():
    return [
        material_moved_event(
            1,
            transfer_id=f"seed-{material}",
            material_id=material,
            quantity=1,
            from_ref="world:tile",
            to_ref="npc:chenmo",
            reason="dig_yield",
        )
        for material in ("earth", "stone", "wood")
    ]


def test_pending_placements_reserve_target_materials_independently_until_flush():
    runtime, state, _, _, _, commit = setup_runtime(heights={(3, 1): 2, (4, 1): 2})
    runtime.observe(stock_events())
    stone = runtime.request("place", 3, 1, state)
    earth = runtime.request("place", 1, 2, state)
    assert stone[0].payload["material_id"] == "stone"
    assert earth[0].payload["material_id"] == "earth"
    assert runtime.snapshot()["inventory"] == {"earth": 1, "stone": 1, "wood": 1}
    with pytest.raises(VoxelRejected):
        runtime.request("place", 4, 1, state)
    commit(stone)
    with pytest.raises(VoxelRejected):
        runtime.request("place", 4, 1, state)
    commit(earth)
    with pytest.raises(VoxelRejected):
        runtime.request("place", 1, 3, state)
    assert runtime.snapshot()["inventory"] == {"earth": 0, "stone": 0, "wood": 1}


def test_restore_discards_pending_reservations_for_every_material():
    runtime, state, _, _, _, _ = setup_runtime(heights={(3, 1): 2})
    grants = stock_events()
    runtime.observe(grants)
    runtime.request("place", 3, 1, state)
    runtime.request("place", 1, 2, state)
    runtime.restore_from_events([event.to_store_dict() for event in grants])
    assert runtime.request("place", 3, 1, state)[0].payload["material_id"] == "stone"
    assert runtime.request("place", 1, 2, state)[0].payload["material_id"] == "earth"


async def test_three_material_persistence_snapshot_and_replay_are_bit_equal(store):
    runtime, state, maps, _, _, commit = setup_runtime(heights={(2, 1): 1, (3, 1): 2, (1, 2): 3})
    ns = NpcStore(store)
    for x, y in [(2, 1), (3, 1), (1, 2)]:
        maps[0] = maps[0].with_collision(x, y, walkable=False)
        runtime.request("dig_start", x, y, state)
        events = runtime.tick(state, state.tick + DIG_TICKS)
        await ns.flush_tick(events)
        commit(events)
        state = state.model_copy(update={"tick": state.tick + DIG_TICKS})
    placed = runtime.request("place", 3, 1, state)
    await ns.flush_tick(placed)
    commit(placed)
    balances = await ns.materialize_material_balances()
    assert balances == await ns.materialize_material_balances_replay()
    assert runtime.snapshot()["inventory"] == {"earth": 0, "stone": 1, "wood": 1}
    assert {
        material: balances[("npc:chenmo", material)] for material in ("earth", "stone", "wood")
    } == {
        "earth": 0.0,
        "stone": 1.0,
        "wood": 1.0,
    }
    restored, _, _, _, _, _ = setup_runtime()
    restored.restore_from_events(await ns.read_branch_history())
    assert restored.snapshot() == runtime.snapshot()
    restored.restore_from_events([])
    assert restored.snapshot()["inventory"] == {"earth": 0, "stone": 0, "wood": 0}


def test_old_earth_events_replay_verbatim_even_on_a_static_wood_cell():
    runtime, _, _, _, _, _ = setup_runtime(heights={(2, 1): 3})
    old_edit = voxel_edited_event(1, x=2, y=1, action="dig")
    old_material = stock_events()[0]
    runtime.restore_from_events([old_edit.to_store_dict(), old_material.to_store_dict()])
    assert runtime.snapshot()["inventory"] == {"earth": 1, "stone": 0, "wood": 0}


@pytest.mark.parametrize("material", ["earth", "stone", "wood"])
def test_fractional_or_negative_player_stock_is_rejected_without_mutating_counts(material):
    runtime, _, _, _, _, _ = setup_runtime()
    before = runtime.snapshot()
    for quantity, from_ref, to_ref in [
        (0.25, "world:tile", "npc:chenmo"),
        (1, "npc:chenmo", "world:tile"),
    ]:
        event = material_moved_event(
            1,
            transfer_id="invalid-stock",
            material_id=material,
            quantity=quantity,
            from_ref=from_ref,
            to_ref=to_ref,
            reason="dig_yield",
        )
        with pytest.raises(ValueError):
            runtime.observe([event])
        assert runtime.snapshot() == before


def test_foreign_and_unknown_material_transfers_do_not_credit_player_stock():
    runtime, _, _, _, _, _ = setup_runtime()
    before = runtime.snapshot()
    for material, to_ref in [("iron", "npc:chenmo"), ("stone", "npc:other"), ("wood", "npc:other")]:
        runtime.observe(
            [
                material_moved_event(
                    1,
                    transfer_id=f"foreign-{material}",
                    material_id=material,
                    quantity=0.25,
                    from_ref="world:tile",
                    to_ref=to_ref,
                    reason="dig_yield",
                )
            ]
        )
    assert runtime.snapshot() == before
