"""The production terrain cursor must lead landing and preserve flush order."""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

from sim.api import anchors, main, settings, ws
from sim.core.clock import GameClock
from sim.core.events import (
    EventKind,
    WorldEvent,
    structure_collapsed_event,
    structure_completed_event,
    structure_removed_event,
    structure_started_event,
    tile_changed_event,
    voxel_edited_event,
    world_create_event,
)
from sim.core.persistence.database import create_session_factory, init_database
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore
from sim.core.persistence.world_restore import flush_world
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.world.locomotion import plan_jump


@pytest.fixture
async def live_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_world_database: Any
) -> AsyncIterator[FastAPI]:
    database = tmp_path / "world.db"
    anchor_store = anchors.AnchorStore(f"sqlite:///{database}")
    profile_store = settings.ProfileStore(f"sqlite:///{database}")
    monkeypatch.setattr(anchors, "_anchor_store", anchor_store)
    monkeypatch.setattr(settings, "_profile_store", profile_store)
    monkeypatch.setattr(main, "manager", ws.ConnectionManager())
    base = main._fallback_map()
    monkeypatch.setattr(main, "_default_map", lambda: base)
    monkeypatch.setattr(main, "_voxel_height_lookup", lambda: lambda x, y: 1)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    try:
        await init_database(engine)
        store = SqlEventStore(create_session_factory(engine))
        loop = TickLoop(GameClock(), build_default_bus(), WorldState(world_seed=42))
        for event in (
            world_create_event(0, 42, ("chenmo",)),
            structure_started_event(
                0,
                structure_id="landing",
                tiles=((1, 0),),
                kind="hut",
                material="wood",
                planned_duration_ticks=1,
                recipe_id="hut_v1",
                recipe_version="1",
                build_rule_version="1",
            ),
            structure_completed_event(0, structure_id="landing", quality=0.8, integrity=1.0),
            tile_changed_event(0, 1, 0, 0, height=2),
        ):
            loop.enqueue(event)
        await flush_world(store, "main", loop, loop.drain_events())

        async def loaded_loop() -> tuple[TickLoop, SqlEventStore, None]:
            return loop, store, None

        async def idle_driver(*args: Any, **kwargs: Any) -> None:
            await asyncio.Event().wait()

        monkeypatch.setattr(main, "build_loop", loaded_loop)
        monkeypatch.setattr(main, "run_world_driver", idle_driver)
        async with main.lifespan(main.app):
            await main.app.state.flush_for_anchor()
            assert main.app.state.pathfinder.height_at(1, 0) == 2
            yield main.app
    finally:
        await engine.dispose()
        anchor_store._engine.dispose()
        profile_store._engine.dispose()


def terminal_event(kind: str, tick: int) -> WorldEvent:
    if kind == "collapsed":
        return structure_collapsed_event(tick, structure_id="landing", cause="decay")
    return structure_removed_event(tick, structure_id="landing", reason="demolished")


@pytest.mark.parametrize("terminal", ["collapsed", "removed"])
async def test_same_frame_structure_terminal_invalidates_landing_before_flush(
    live_structure: FastAPI, terminal: str
) -> None:
    app = live_structure
    loop: TickLoop = app.state.loop
    loop.enqueue(plan_jump(loop.state, "chenmo", (1, 0), "walk", app.state.pathfinder))

    def finish_structure(state: WorldState, tick: int) -> list[WorldEvent]:
        return [terminal_event(terminal, tick)] if tick == 35 else []

    loop.attach_maintenance(finish_structure)
    loop.advance_frame(0.6)
    landed = [event for event in loop.pending_events if event.event_type is EventKind.JUMP_LANDED]
    assert len(landed) == 1
    assert landed[0].tick == 36
    assert landed[0].payload["reason"] == "obstructed"
    assert landed[0].payload["goal"] == [0, 0]
    assert landed[0].payload["target_height"] == 1
    assert loop.state.entities["chenmo"].pos == (0, 0)
    assert app.state.pathfinder.height_at(1, 0) == 1

    await app.state.flush_for_anchor()
    rows = await NpcStore(app.state.store, branch_id="main").read_branch_history()
    restores = [
        row
        for row in rows
        if row["event_type"] == EventKind.TILE_CHANGED.value and row["tick"] == 35
    ]
    assert len(restores) == 1
    assert restores[0]["payload"]["height"] == 1
    rebuilt = await main.rebuild_surface(NpcStore(app.state.store, branch_id="main"))
    assert rebuilt.height_at(1, 0) == app.state.pathfinder.height_at(1, 0) == 1


@pytest.mark.parametrize("terminal", ["collapsed", "removed"])
@pytest.mark.parametrize("fail_first_flush", [False, True])
async def test_terminal_then_voxel_keeps_event_order_and_releases_derived_events(
    live_structure: FastAPI,
    terminal: str,
    fail_first_flush: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sim.core.persistence import world_restore

    app = live_structure
    loop: TickLoop = app.state.loop
    store = NpcStore(app.state.store, branch_id="main")
    before = await store.read_branch_history()
    loop.enqueue(terminal_event(terminal, 0))
    assert app.state.pathfinder.height_at(1, 0) == 1
    # Once committed, neither the observer nor the terminal cache may retain these.
    restored_refs = [weakref.ref(event) for event in app.state.surface._observed]
    assert len(restored_refs) == 1
    edit = voxel_edited_event(0, x=1, y=0, action="place", height=3)
    loop.enqueue(edit.model_copy(update={"payload": {**edit.payload, "material_id": "wood"}}))
    loop.enqueue(tile_changed_event(0, 1, 0, 0, height=3))
    assert app.state.pathfinder.height_at(1, 0) == 3

    if fail_first_flush:

        async def failed_commit(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("synthetic transaction failure")

        with monkeypatch.context() as transaction:
            transaction.setattr(world_restore, "flush_world", failed_commit)
            with pytest.raises(RuntimeError, match="synthetic transaction failure"):
                await app.state.flush_for_anchor()
        assert await store.read_branch_history() == before
        assert app.state.pathfinder.height_at(1, 0) == 3

    await app.state.flush_for_anchor()
    assert app.state.pathfinder.height_at(1, 0) == 3
    assert not app.state.tile_map.is_walkable(1, 0)
    assert all(reference() is None for reference in restored_refs)
    rows = await store.read_branch_history()
    tail = rows[len(before) :]
    expected_terminal = (
        EventKind.STRUCTURE_COLLAPSED if terminal == "collapsed" else EventKind.STRUCTURE_REMOVED
    )
    assert [row["event_type"] for row in tail] == [
        expected_terminal.value,
        EventKind.TILE_CHANGED.value,
        EventKind.VOXEL_EDITED.value,
        EventKind.TILE_CHANGED.value,
    ]
    assert [row["payload"]["height"] for row in tail if row["event_type"] == "tile_changed"] == [
        1,
        3,
    ]
    rebuilt = await main.rebuild_surface(store)
    assert rebuilt.height_at(1, 0) == app.state.pathfinder.height_at(1, 0) == 3
    assert not rebuilt.tile_map.is_walkable(1, 0)
    await app.state.flush_for_anchor()
    assert await store.read_branch_history() == rows
