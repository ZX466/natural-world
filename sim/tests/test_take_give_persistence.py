"""Wave A: stock ownership uses existing SQL projection, HUD and branch history."""

import asyncio

import pytest

from sim.agent.intent import Intent
from sim.api import anchors, main, settings
from sim.core.events import material_moved_event
from sim.core.persistence.npc_store import NpcStore
from sim.tests.test_runtime_ledger_restore import load_anchor, save_anchor


@pytest.fixture(autouse=True)
def private_world(tmp_path, monkeypatch):
    async def idle(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "WORLD_DB_PATH", tmp_path / "world.db")
    monkeypatch.setattr(main, "run_world_driver", idle)
    monkeypatch.setattr(main, "_active_profile_snapshot_provider", lambda: lambda: None)
    monkeypatch.setattr(main, "_offline_wall_time", lambda: 0.0)
    monkeypatch.setattr(
        anchors, "_anchor_store", anchors.AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
    )
    monkeypatch.setattr(
        settings, "_profile_store", settings.ProfileStore(f"sqlite:///{tmp_path / 'world.db'}")
    )


def nearby_person(app):
    hero = app.state.loop.state.entities["chenmo"]
    return next(
        entity_id
        for entity_id, actor in app.state.loop.state.entities.items()
        if entity_id.startswith("villager_")
        and abs(actor.pos[0] - hero.pos[0]) + abs(actor.pos[1] - hero.pos[1]) <= 12
    )


def seed(app):
    app.state.loop.enqueue(
        material_moved_event(
            app.state.loop.state.tick,
            transfer_id="seed-transfer-stock",
            material_id="wood",
            quantity=3,
            from_ref="world:seed",
            to_ref="npc:chenmo",
            reason="dig_yield",
        )
    )


def transfer(app, action, target, quantity):
    app.state.chenmo_driver._pending.append(
        Intent(
            action=action,
            target_id=target,
            params={"item": "木料", "quantity": str(quantity)},
            reason="交接木料。",
        )
    )
    assert (
        app.state.chenmo_driver.execute_pending(app.state.loop, pathfinder=app.state.pathfinder)
        == 1
    )


async def test_flush_and_cold_restart_preserve_both_owners_and_private_hud():
    async with main.lifespan(main.app):
        app = main.app
        target = nearby_person(app)
        seed(app)
        await app.state.flush_for_anchor()
        transfer(app, "give", target, 2)
        assert app.state.voxel_runtime.snapshot()["inventory"]["wood"] == 3
        await app.state.flush_for_anchor()
        branch = await app.state.store.current_branch_id()
        rows = await NpcStore(app.state.store, branch_id=branch).materialize_material_balances()
        assert rows[("npc:chenmo", "wood")] == 1
        assert rows[(f"npc:{target}", "wood")] == 2
        assert sum(value for (_ref, item), value in rows.items() if item == "wood") == 0
        assert app.state.voxel_runtime.snapshot()["inventory"]["wood"] == 1
    async with main.lifespan(main.app):
        assert main.app.state.material_ledger.balance_of("chenmo", "wood") == 1
        assert main.app.state.material_ledger.balance_of(target, "wood") == 2
        assert main.app.state.voxel_runtime.snapshot()["inventory"]["wood"] == 1


async def test_historical_and_nested_forks_restore_stock_without_parent_futures(tmp_path):
    async with main.lifespan(main.app):
        app = main.app
        anchor_store = anchors.AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
        target = nearby_person(app)
        seed(app)
        first = await save_anchor(app, anchor_store, "交接之前")
        transfer(app, "give", target, 2)
        await app.state.flush_for_anchor()
        await load_anchor(app, first.id)
        assert app.state.material_ledger.balance_of("chenmo", "wood") == 3
        assert app.state.material_ledger.balance_of(target, "wood") == 0
        transfer(app, "give", target, 1)
        second = await save_anchor(app, anchor_store, "交接一份")
        transfer(app, "give", target, 1)
        await app.state.flush_for_anchor()
        await load_anchor(app, second.id)
        assert app.state.material_ledger.balance_of("chenmo", "wood") == 2
        assert app.state.material_ledger.balance_of(target, "wood") == 1
        assert app.state.voxel_runtime.snapshot()["inventory"]["wood"] == 2
        transfer(app, "take", target, 1)
        await app.state.flush_for_anchor()
        assert app.state.material_ledger.balance_of("chenmo", "wood") == 3
