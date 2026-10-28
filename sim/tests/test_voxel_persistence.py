"""Real lifespan/flush/restart/historical-fork tests for V4a, with isolated DBs."""

import asyncio

import pytest

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


def target(app):
    hero = app.state.loop.state.entities["chenmo"]
    runtime = app.state.voxel_runtime
    choices = [
        (x, y)
        for y in range(app.state.tile_map.height)
        for x in range(app.state.tile_map.width)
        if abs(hero.pos[0] - x) + abs(hero.pos[1] - y) <= 4
        and not app.state.tile_map.is_walkable(x, y)
        and runtime._height(x, y) > 0
        and not runtime._occupied(x, y)
    ]
    assert choices
    return choices[0]


def material_at(app, pos):
    # Literal spec oracle: persistence must preserve the material of the selected
    # real-map cell instead of assuming every reachable obstruction is earth.
    return {1: "earth", 2: "stone", 3: "wood"}[app.state.voxel_runtime._height(*pos)]


async def dig(app, pos):
    loop = app.state.loop
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
    assert app.state.voxel_runtime.snapshot()["inventory"][material_at(app, pos)] == 1


async def place(app, pos):
    loop = app.state.loop
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


async def test_real_flush_updates_collision_and_conserves_materials():
    async with main.lifespan(main.app):
        app = main.app
        await app.state.flush_for_anchor()
        pos = target(app)
        material = material_at(app, pos)
        await dig(app, pos)
        assert app.state.tile_map.is_walkable(*pos)
        assert app.state.pathfinder.tile_map is app.state.tile_map
        balances = await NpcStore(app.state.store).materialize_material_balances([material])
        assert balances[("npc:chenmo", material)] == 1
        assert balances[("world:tile", material)] == -1
        await place(app, pos)
        assert not app.state.tile_map.is_walkable(*pos)
        assert app.state.voxel_runtime.snapshot()["inventory"] == {
            "earth": 0,
            "stone": 0,
            "wood": 0,
        }
        balances = await NpcStore(app.state.store).materialize_material_balances([material])
        assert balances[("npc:chenmo", material)] == 0
        assert balances[("world:tile", material)] == 0
        rows = await app.state.store.read_branch_history("main")
        edits = [row for row in rows if row["event_type"] == "voxel.edited"]
        assert [row["payload"]["action"] for row in edits] == ["dig", "place"]
        assert [row["payload"]["material_id"] for row in edits] == [material, material]
        assert all("inventory" not in row["payload"] for row in rows)
        assert [
            row["action"]
            for row in ws.snapshot_payload(app.state.loop, app.state.tile_map)["voxel_edits"]
        ] == ["place"]


async def test_cold_start_restores_edits_stock_and_collision_without_duplicate_genesis():
    async with main.lifespan(main.app):
        app = main.app
        pos = target(app)
        material = material_at(app, pos)
        await dig(app, pos)
    async with main.lifespan(main.app):
        app = main.app
        assert app.state.voxel_runtime.snapshot() == {
            "dig": None,
            "inventory": {"earth": 0, "stone": 0, "wood": 0, material: 1},
        }
        assert app.state.tile_map.is_walkable(*pos)
        assert ws.snapshot_payload(app.state.loop, app.state.tile_map)["voxel_edits"] == [
            {
                "x": pos[0],
                "y": pos[1],
                "action": "dig",
                "gid": main._ground_tile_id(app.state.tile_map, *pos),
            }
        ]
        rows = await app.state.store.read_branch_history("main")
        assert sum(row["event_type"] == "world.create" for row in rows) == 1


async def test_historical_fork_uses_cursor_material_balance_and_drops_future_edit():
    async with main.lifespan(main.app):
        app = main.app
        anchors = AnchorStore()
        pos = target(app)
        material = material_at(app, pos)
        await dig(app, pos)
        old = await save(app, anchors, "材料已挖出")
        app.state.loop.advance_frame(1 / 60)
        await place(app, pos)
        await save(app, anchors, "材料已放下")
        parent = await app.state.store.current_branch_id()
        await load(app, old)
        child = await app.state.store.current_branch_id()
        assert child != parent
        assert app.state.voxel_runtime.snapshot() == {
            "dig": None,
            "inventory": {"earth": 0, "stone": 0, "wood": 0, material: 1},
        }
        assert app.state.tile_map.is_walkable(*pos)
        rows = ws.snapshot_payload(app.state.loop, app.state.tile_map)["voxel_edits"]
        assert len(rows) == 1 and rows[0]["action"] == "dig"
        balances = await NpcStore(app.state.store, branch_id=child).materialize_material_balances(
            [material]
        )
        assert balances[("npc:chenmo", material)] == 1, (
            "A historical fork must not clone future parent stock"
        )
        await place(app, pos)
        assert app.state.voxel_runtime.snapshot()["inventory"] == {
            "earth": 0,
            "stone": 0,
            "wood": 0,
        }
        assert not app.state.tile_map.is_walkable(*pos)
        parent_balances = await NpcStore(
            app.state.store, branch_id=parent
        ).materialize_material_balances([material])
        assert parent_balances[("npc:chenmo", material)] == 0


async def test_nested_fork_material_prefix_does_not_mix_branch_sequence_numbers():
    async with main.lifespan(main.app):
        app = main.app
        anchors = AnchorStore()
        pos = target(app)
        material = material_at(app, pos)
        await dig(app, pos)
        parent_dig = await save(app, anchors, "父线挖出")
        await place(app, pos)
        await save(app, anchors, "父线放下")
        await load(app, parent_dig)
        await place(app, pos)
        child_place = await save(app, anchors, "子线放下")
        await dig(app, pos)
        await save(app, anchors, "子线后来挖出")
        await load(app, child_place)
        branch = await app.state.store.current_branch_id()
        balances = await NpcStore(app.state.store, branch_id=branch).materialize_material_balances(
            [material]
        )
        assert balances[("npc:chenmo", material)] == 0
        assert balances[("world:tile", material)] == 0
        assert app.state.voxel_runtime.snapshot()["inventory"] == {
            "earth": 0,
            "stone": 0,
            "wood": 0,
        }
        assert not app.state.tile_map.is_walkable(*pos)
        assert (
            ws.snapshot_payload(app.state.loop, app.state.tile_map)["voxel_edits"][0]["action"]
            == "place"
        )
