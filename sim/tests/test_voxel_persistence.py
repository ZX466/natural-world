"""Real-map flush, cold-start and nested-fork depth/inventory contracts (1.14)."""

import asyncio

import pytest

from sim.agent.voxel_exec import VoxelRuntime
from sim.api import main, ws
from sim.api.anchors import AnchorStore
from sim.core.persistence.npc_store import NpcStore
from sim.tests.test_structure_presentation_restore import load, save


@pytest.fixture(autouse=True)
def idle_world(monkeypatch, tmp_path):
    async def idle(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "run_world_driver", idle)


def target(app, height=3):
    runtime = app.state.voxel_runtime
    hero = app.state.loop.state.entities["chenmo"]
    return next(
        (x, y)
        for y in range(app.state.tile_map.height)
        for x in range(app.state.tile_map.width)
        if abs(hero.pos[0] - x) + abs(hero.pos[1] - y) <= 4
        and not app.state.tile_map.is_walkable(x, y)
        and runtime.height_at(x, y) == height
        and not runtime._occupied(x, y)
    )


async def dig(app, pos):
    runtime, loop = app.state.voxel_runtime, app.state.loop
    height = runtime.height_at(*pos)
    material = {1: "earth", 2: "stone", 3: "wood"}[height]
    before = runtime.snapshot()["inventory"][material]
    assert (
        ws.handle_client_message(
            {
                "type": "voxel_request",
                "channel": "render",
                "action": "dig_start",
                "x": pos[0],
                "y": pos[1],
            },
            loop,
            app.state.pathfinder,
        )
        is None
    )
    loop.advance_frame(0.5)
    await app.state.flush_for_anchor()
    assert runtime.height_at(*pos) == height - 1
    assert runtime.snapshot()["inventory"][material] == before + 1
    assert app.state.tile_map.is_walkable(*pos) == (height - 1 == 1)


async def place(app, pos):
    runtime, loop = app.state.voxel_runtime, app.state.loop
    assert runtime.height_at(*pos) == 1
    before = runtime.snapshot()["inventory"]["earth"]
    assert (
        ws.handle_client_message(
            {
                "type": "voxel_request",
                "channel": "render",
                "action": "place",
                "x": pos[0],
                "y": pos[1],
            },
            loop,
            app.state.pathfinder,
        )
        is None
    )
    await app.state.flush_for_anchor()
    assert runtime.height_at(*pos) == 2
    assert runtime.snapshot()["inventory"]["earth"] == before - 1
    assert not app.state.tile_map.is_walkable(*pos)


def heights(app):
    return [
        app.state.voxel_runtime.height_at(x, y)
        for y in range(app.state.tile_map.height)
        for x in range(app.state.tile_map.width)
    ]


async def assert_full_replay(app):
    branch = await app.state.store.current_branch_id()
    ns = NpcStore(app.state.store, branch_id=branch)
    events = await ns.read_branch_history()
    restored = VoxelRuntime(
        tile_map=lambda: app.state.tile_map,
        height_of=app.state.voxel_runtime._height,
        ground_gid=lambda x, y: main._ground_tile_id(app.state.tile_map, x, y),
        occupied=lambda x, y: False,
    )
    restored.restore_from_events(events)
    assert restored.snapshot() == app.state.voxel_runtime.snapshot()
    assert [
        restored.height_at(x, y)
        for y in range(app.state.tile_map.height)
        for x in range(app.state.tile_map.width)
    ] == heights(app)
    expected_rows = ws.voxel_snapshot_rows()
    ws.restore_voxel_edits(
        events,
        ground_gid=lambda x, y: main._ground_tile_id(app.state.tile_map, x, y),
        height_of=restored._height,
    )
    assert ws.voxel_snapshot_rows() == expected_rows
    rebuilt = await main.rebuild_tile_map(ns)
    for y in range(rebuilt.height):
        for x in range(rebuilt.width):
            assert rebuilt.is_walkable(x, y) == app.state.tile_map.is_walkable(x, y)
            if rebuilt.is_walkable(x, y):
                assert restored.height_at(x, y) == 1
    # This oracle needs bounded ancestor prefixes; the older replay helper reads
    # only branch-local rows and deliberately cannot verify a fork's baseline.
    balances = {}
    for event in events:
        if event["event_type"] != "material.moved":
            continue
        payload = event["payload"]
        for field, sign in (("from_ref", -1), ("to_ref", 1)):
            key = (payload[field], payload["material_id"])
            balances[key] = balances.get(key, 0) + sign * payload["quantity"]
    assert await ns.materialize_material_balances() == balances
    return events


async def test_real_flush_updates_layer_collision_and_conserves_each_material():
    async with main.lifespan(main.app):
        app = main.app
        pos, bank = target(app), target(app, 1)
        await dig(app, pos)
        assert not app.state.tile_map.is_walkable(*pos)
        await dig(app, pos)
        await dig(app, bank)
        assert not app.state.tile_map.is_walkable(*bank)
        await place(app, pos)
        assert app.state.pathfinder.tile_map is app.state.tile_map
        ns = NpcStore(app.state.store)
        balances = await ns.materialize_material_balances()
        for material, count in {"earth": 0, "stone": 1, "wood": 1}.items():
            assert balances[("npc:chenmo", material)] == count
            assert balances[("world:tile", material)] == -count
        rows = await assert_full_replay(app)
        edits = [r for r in rows if r["event_type"] == "voxel.edited"]
        assert [r["payload"]["height"] for r in edits] == [2, 1, 0, 2]
        assert all("inventory" not in row["payload"] for row in rows)


async def test_cold_start_restores_exact_depth_stock_and_collision_without_duplicate_genesis():
    async with main.lifespan(main.app):
        app = main.app
        pos = target(app)
        await dig(app, pos)
        expected_heights = heights(app)
        expected_stock = app.state.voxel_runtime.snapshot()
        expected_rows = ws.voxel_snapshot_rows()
    async with main.lifespan(main.app):
        app = main.app
        assert heights(app) == expected_heights
        assert app.state.voxel_runtime.snapshot() == expected_stock
        assert ws.voxel_snapshot_rows() == expected_rows
        assert not app.state.tile_map.is_walkable(*pos)
        rows = await assert_full_replay(app)
        assert sum(row["event_type"] == "world.create" for row in rows) == 1
        await dig(app, pos)
        assert app.state.tile_map.is_walkable(*pos)


async def test_historical_fork_restores_cursor_depth_and_drops_future_layers():
    async with main.lifespan(main.app):
        app = main.app
        anchors = AnchorStore()
        pos, bank = target(app), target(app, 1)
        await dig(app, bank)
        await dig(app, pos)
        expected_heights, expected_stock = heights(app), app.state.voxel_runtime.snapshot()
        old = await save(app, anchors, "保留两层")
        await dig(app, pos)
        await place(app, pos)
        parent = await app.state.store.current_branch_id()
        await save(app, anchors, "未来放置")
        await load(app, old)
        assert await app.state.store.current_branch_id() != parent
        assert heights(app) == expected_heights
        assert app.state.voxel_runtime.snapshot() == expected_stock
        assert not app.state.tile_map.is_walkable(*pos)
        await assert_full_replay(app)
        await dig(app, pos)
        assert app.state.tile_map.is_walkable(*pos)
        parent_balances = await NpcStore(
            app.state.store, branch_id=parent
        ).materialize_material_balances()
        assert parent_balances[("npc:chenmo", "earth")] == 0
        assert app.state.voxel_runtime.snapshot()["inventory"]["earth"] == 1


async def test_nested_fork_replay_matches_all_14000_cells_without_sorting_local_sequences():
    async with main.lifespan(main.app):
        app = main.app
        anchors = AnchorStore()
        pos, bank = target(app), target(app, 1)
        await dig(app, bank)
        await dig(app, pos)
        parent_target = await save(app, anchors, "父线两层")
        await dig(app, pos)
        await place(app, pos)
        await save(app, anchors, "父线未来")
        await load(app, parent_target)
        await dig(app, pos)
        expected_heights, expected_stock = heights(app), app.state.voxel_runtime.snapshot()
        child_target = await save(app, anchors, "子线一层")
        await place(app, pos)
        await save(app, anchors, "子线未来")
        await load(app, child_target)
        assert heights(app) == expected_heights
        assert app.state.voxel_runtime.snapshot() == expected_stock
        events = await assert_full_replay(app)
        column = [
            row["payload"]["height"]
            for row in events
            if row["event_type"] == "voxel.edited"
            and (row["payload"]["x"], row["payload"]["y"]) == pos
        ]
        assert column == [2, 1]
        await place(app, pos)
        await assert_full_replay(app)
