"""P：分支地图与施工账本必须随启动/读档重建。"""

import asyncio

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine

from sim.agent.build_exec import BuildRuntime
from sim.api import main, ws
from sim.core.clock import GameClock
from sim.core.events import world_create_event
from sim.core.persistence.database import create_session_factory, init_database
from sim.core.persistence.models import Branch
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.tests.test_e4_build_loop import _find_open_2x2


@pytest.fixture
async def branch_world(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_database(engine)
    store = SqlEventStore(create_session_factory(engine))
    base = main._default_map()
    pos = _find_open_2x2(base)
    old = BuildRuntime(base, seed=42)
    started = old.start("chenmo", pos, tick=100)
    assert started is not None
    end_tick = 100 + old.active_duration()
    events = [world_create_event(0, 42, ("chenmo",)), started, *old.on_tick(end_tick)]
    await NpcStore(store, branch_id="main").flush_tick(events)
    async with store.session_factory.begin() as session:
        session.add(
            Branch(
                id="earlier",
                forked_from_branch="main",
                forked_from_seq=1,
                status="active",
                is_current=False,
            )
        )
    loop = TickLoop(
        clock=GameClock(speed=1),
        bus=build_default_bus(),
        state=WorldState(
            world_seed=42,
            tick=end_tick,
            entities={
                "chenmo": EntityState(entity_id="chenmo", pos=(100, 53)),
            },
        ),
    )

    async def build_loop():
        return loop, store

    async def idle_driver(*args, **kwargs):
        await asyncio.Event().wait()

    async def load_earlier(*args, **kwargs):
        async with store.session_factory.begin() as session:
            await session.execute(update(Branch).values(is_current=False))
            await session.execute(
                update(Branch).where(Branch.id == "earlier").values(is_current=True)
            )

    monkeypatch.setattr(main, "build_loop", build_loop)
    monkeypatch.setattr(main, "_default_map", lambda: base)
    monkeypatch.setattr(main, "run_world_driver", idle_driver)
    monkeypatch.setattr(main, "_active_profile_snapshot_provider", lambda: lambda: None)
    monkeypatch.setattr(
        "sim.core.persistence.fork_orchestration.orchestrate_load_anchor",
        load_earlier,
    )
    yield store, pos, old.tile_map
    await engine.dispose()


async def test_startup_replays_completed_wall(branch_world):
    _, pos, _ = branch_world
    async with main.lifespan(main.app):
        assert not main.app.state.tile_map.is_walkable(*pos)
        assert main.app.state.build_runtime.tile_map is main.app.state.tile_map


async def test_loading_earlier_branch_drops_old_wall(branch_world):
    _, pos, old_map = branch_world
    async with main.lifespan(main.app):
        main.app.state.tile_map = old_map
        main.app.state.build_runtime.tile_map = old_map
        main.app.state.pathfinder.observe_map(old_map)
        assert ws._ANCHOR_LOAD_HOOK is not None
        ws._ANCHOR_LOAD_HOOK("earlier")
        await main.app.state.drain_pending_loads()
        assert main.app.state.load_outcomes[-1] == ("earlier", True)
        assert main.app.state.build_runtime.tile_map.is_walkable(*pos)
        assert main.app.state.tile_map.is_walkable(*pos)
