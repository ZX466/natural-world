"""Wave B: production light provider follows private lifecycle history and forks."""

import asyncio

import pytest

from sim.api import anchors, main, settings, ws
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


def ignite(app):
    occupied = {actor.pos for actor in app.state.loop.state.entities.values()}
    x, y = next(
        (x, y)
        for y in range(app.state.tile_map.height)
        for x in range(app.state.tile_map.width)
        if app.state.tile_map.is_walkable(x, y) and (x, y) not in occupied
    )
    for event in app.state.fire_runtime.ignite_at(tick=app.state.loop.state.tick, x=x, y=y):
        app.state.loop.enqueue(event)


def lights(app):
    return ws.snapshot_payload(app.state.loop, app.state.tile_map)["lights"]


async def test_real_provider_cold_restore_extinction_and_shutdown_do_not_leave_ghosts():
    async with main.lifespan(main.app):
        app = main.app
        assert lights(app) == []
        ignite(app)
        await app.state.flush_for_anchor()
        expected = lights(app)
        assert len(expected) == 1 and expected[0]["kind"] == "fire"
        loop, tile_map = app.state.loop, app.state.tile_map
    assert ws.snapshot_payload(loop, tile_map)["lights"] == []
    async with main.lifespan(main.app):
        app = main.app
        assert lights(app) == expected
        for _ in range(12):
            app.state.loop.replay_until(app.state.loop.state.tick + 1)
            for event in app.state.fire_runtime.step(
                tick=app.state.loop.state.tick, walkable=set()
            ):
                app.state.loop.enqueue(event)
        await app.state.flush_for_anchor()
        assert lights(app) == []


async def test_load_before_ignition_clears_lights_and_delta_history(tmp_path):
    async with main.lifespan(main.app):
        app = main.app
        anchor_store = anchors.AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
        before = await save_anchor(app, anchor_store, "起火之前")
        ignite(app)
        await app.state.flush_for_anchor()
        assert ws.delta_payload(app.state.loop, set()).get("lights")
        await load_anchor(app, before.id)
        assert lights(app) == []
        assert "lights" not in ws.delta_payload(app.state.loop, set())
