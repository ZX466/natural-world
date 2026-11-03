"""Daily health must use the real synchronous driver seam and persist next-frame events.

The task/wait/cancel harness mirrors TestDaySwitchHook._drive_frames; it runs
run_world_driver itself on pytest's loop, rather than emulating its day loop.
"""

import asyncio
import contextlib
import inspect

import pytest
from sqlalchemy import select

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.core.events import EventKind, npc_health_changed_event
from sim.core.persistence.models import NpcHealth
from sim.tests.test_health_live_wiring import stop_background


@pytest.fixture
async def daily_world(monkeypatch):
    from sim.api import main
    from sim.npc import reflection

    captured = asyncio.Event()
    callbacks = {}
    order = []
    current_day = [None]

    def reflector_factory(*args, **kwargs):
        def reflect(day):
            current_day[0] = day
            order.append(("reflection", day))
            return ["return-value-is-not-an-input"]

        return reflect

    async def held_driver(loop, manager, tile_map, on_flush, **kwargs):
        callbacks.update(loop=loop, manager=manager, tile_map=tile_map, flush=on_flush, **kwargs)
        captured.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(reflection, "make_day_switch_reflector", reflector_factory)
    monkeypatch.setattr(main, "run_world_driver", held_driver)
    async with main.lifespan(main.app):
        await asyncio.wait_for(captured.wait(), timeout=5)
        app = main.app
        await stop_background(app)
        await app.state.flush_for_anchor()
        original = app.state.loop.enqueue

        def observe_enqueue(event):
            if (
                event.event_type is EventKind.NPC_HEALTH_CHANGED
                and event.payload.get("npc_id") == "chenmo"
                and event.payload.get("code") == "wrist_strain"
            ):
                order.append(("health", current_day[0]))
            return original(event)

        monkeypatch.setattr(app.state.loop, "enqueue", observe_enqueue)
        yield app, callbacks, order


async def _row(app, code="wrist_strain"):
    async with app.state.store.session_factory() as session:
        return await session.scalar(
            select(NpcHealth).where(
                NpcHealth.branch_id == "main", NpcHealth.npc_id == "chenmo", NpcHealth.code == code
            )
        )


async def _drive(app, callbacks, *, jump_days=0):
    from sim.api.ws import run_world_driver

    loop = app.state.loop
    loop.state = loop.state.model_copy(update={"tick": TICKS_PER_GAME_DAY - 1})
    loop.clock.restore_tick(loop.state.tick)
    loop.clock.set_speed(1)
    # Like TestDaySwitchHook.test_day_switch_after_flush, guarantee a preexisting
    # event in the first frame: empty frames legitimately skip on_flush entirely.
    loop.issue_move("chenmo", [loop.state.entities["chenmo"].pos])
    flushed = []
    health_flushed = asyncio.Event()
    day_after_flushes = []

    def on_day(day):
        day_after_flushes.append(len(flushed))
        callbacks["on_day_switch"](day)

    async def flush(events):
        await callbacks["flush"](events)
        flushed.append(list(events))
        if len(flushed) == 1 and jump_days:
            # The first frame can advance zero ticks; make the intended three-day
            # catch-up explicit instead of depending on real sleep rounding.
            loop.state = loop.state.model_copy(
                update={"tick": TICKS_PER_GAME_DAY * (1 + jump_days)}
            )
            loop.clock.restore_tick(loop.state.tick)
        if any(event.event_type is EventKind.NPC_HEALTH_CHANGED for event in events):
            health_flushed.set()

    task = asyncio.create_task(
        run_world_driver(
            loop,
            callbacks["manager"],
            callbacks["tile_map"],
            on_flush=flush,
            on_day_switch=on_day,
            write_lock=app.state.world_write_lock,
        )
    )
    try:
        await asyncio.wait_for(health_flushed.wait(), timeout=10)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    return flushed, day_after_flushes


async def test_real_day_switch_enqueues_then_next_frame_persists_health(daily_world):
    app, callbacks, order = daily_world
    assert (await _row(app)).severity == 0.2
    flushed, day_after_flushes = await _drive(app, callbacks)
    assert (await _row(app)).severity == 0.15
    assert not any(event.event_type is EventKind.NPC_HEALTH_CHANGED for event in flushed[0])
    changed = [e for e in flushed[-1] if e.event_type is EventKind.NPC_HEALTH_CHANGED]
    assert changed
    assert day_after_flushes == [len(flushed) - 1]
    assert order[:2] == [("reflection", 2), ("health", 2)]
    assert not inspect.iscoroutinefunction(callbacks["on_day_switch"])
    assert callbacks["on_day_switch"](2) is None
    assert not any(
        event.event_type is EventKind.NPC_HEALTH_CHANGED for event in app.state.loop.pending_events
    )


async def test_real_multi_day_frame_sequentially_evolves_each_day(daily_world):
    app, callbacks, order = daily_world
    flushed, day_after_flushes = await _drive(app, callbacks, jump_days=2)
    changed = [
        event
        for batch in flushed
        for event in batch
        if event.event_type is EventKind.NPC_HEALTH_CHANGED
        and event.payload["npc_id"] == "chenmo"
        and event.payload["code"] == "wrist_strain"
    ]
    assert [event.payload["severity"] for event in changed] == [0.15, 0.1, 0.05]
    assert len({event.tick for event in changed}) == 1
    assert (await _row(app)).severity == 0.05
    assert day_after_flushes == [len(flushed) - 1] * 3
    assert order[:6] == [
        ("reflection", 2),
        ("health", 2),
        ("reflection", 3),
        ("health", 3),
        ("reflection", 4),
        ("health", 4),
    ]


async def test_committed_same_day_health_change_is_refreshed_before_evolution(daily_world):
    app, callbacks, _ = daily_world
    loop = app.state.loop
    loop.enqueue(
        npc_health_changed_event(
            loop.state.tick,
            npc_id="chenmo",
            category="old_injury",
            code="wrist_strain",
            severity=0.8,
        )
    )
    await app.state.flush_for_anchor()
    assert (await _row(app)).severity == 0.8
    await _drive(app, callbacks)
    assert (await _row(app)).severity == 0.75


async def test_head_branch_switch_refreshes_snapshot_without_changing_parent(daily_world):
    from sqlalchemy import func

    from sim.core.persistence.fork import fork_from_anchor
    from sim.core.persistence.models import Event

    app, callbacks, _ = daily_world
    loop = app.state.loop
    async with app.state.store.session_factory() as session:
        seq = await session.scalar(select(func.max(Event.seq)).where(Event.branch_id == "main"))
    await fork_from_anchor(
        app.state.store.session_factory,
        parent_branch_id="main",
        fork_seq=seq,
        fork_tick=loop.state.tick,
        new_branch_id="health-child",
        preflush=app.state.flush_for_anchor,
    )
    loop.enqueue(
        npc_health_changed_event(
            loop.state.tick,
            npc_id="chenmo",
            category="old_injury",
            code="wrist_strain",
            severity=0.8,
            branch_id="health-child",
        )
    )
    await app.state.flush_for_anchor()
    assert app.state.health_evolution.branch_id == "health-child"
    await _drive(app, callbacks)
    async with app.state.store.session_factory() as session:
        child = await session.scalar(
            select(NpcHealth.severity).where(
                NpcHealth.branch_id == "health-child",
                NpcHealth.npc_id == "chenmo",
                NpcHealth.code == "wrist_strain",
            )
        )
    assert child == 0.75
    assert (await _row(app)).severity == 0.2


async def test_offline_crossing_skips_health_and_live_baseline_does_not_backfill(monkeypatch):
    from sim.api import main
    from sim.core.persistence.offline_store import last_recorded_at

    ready = asyncio.Event()
    callbacks = {}

    async def held_driver(loop, manager, tile_map, on_flush, **kwargs):
        callbacks.update(kwargs)
        ready.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "run_world_driver", held_driver)
    async with main.lifespan(main.app):
        await asyncio.wait_for(ready.wait(), timeout=5)
        app = main.app
        await stop_background(app)
        loop = app.state.loop
        loop.state = loop.state.model_copy(update={"tick": TICKS_PER_GAME_DAY - 30})
        loop.clock.restore_tick(loop.state.tick)
        loop.issue_move("chenmo", [loop.state.entities["chenmo"].pos])
        await app.state.flush_for_anchor()
        recorded = await last_recorded_at(app.state.store, "main")
        assert recorded is not None
    ready.clear()
    monkeypatch.setattr(main, "_offline_wall_time", lambda: recorded + 1)
    async with main.lifespan(main.app):
        await asyncio.wait_for(ready.wait(), timeout=5)
        app = main.app
        await stop_background(app)
        assert app.state.offline_result.advanced_ticks == 60
        assert app.state.health_evolution.last_day == 2
        assert (await _row(app)).severity == 0.2
        history = await app.state.store.read_branch_history("main")
        assert not any(row["event_type"] == EventKind.NPC_HEALTH_CHANGED.value for row in history)
        callbacks["on_day_switch"](2)
        assert not any(
            e.event_type is EventKind.NPC_HEALTH_CHANGED for e in app.state.loop.pending_events
        )
        app.state.loop.state = app.state.loop.state.model_copy(
            update={"tick": 2 * TICKS_PER_GAME_DAY}
        )
        callbacks["on_day_switch"](3)
        await app.state.flush_for_anchor()
        assert (await _row(app)).severity == 0.15


async def test_player_load_resets_health_day_baseline_without_claiming_health_cursor_fold(
    daily_world, tmp_path
):
    """Control reset only: the main-only historical health fold is outside this tree."""
    from sim.api import ws
    from sim.api.anchors import AnchorStore

    app, callbacks, _ = daily_world
    loop = app.state.loop
    rows = await app.state.store.read_branch_history("main")
    anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
    target = anchors.create_item(
        "伤未变时",
        branch_id="main",
        tick=loop.state.tick,
        seq=rows[-1]["seq"],
        rng_state=app.state.rng_capture(),
    )
    loop.state = loop.state.model_copy(update={"tick": 3 * TICKS_PER_GAME_DAY})
    loop.clock.restore_tick(loop.state.tick)
    callbacks["on_day_switch"](4)
    await app.state.flush_for_anchor()
    assert app.state.health_evolution.last_day == 4
    rows = await app.state.store.read_branch_history("main")
    anchors.create_item(
        "伤已变时",
        branch_id="main",
        tick=loop.state.tick,
        seq=rows[-1]["seq"],
        rng_state=app.state.rng_capture(),
    )
    ws.register_anchor_id(target.id, "伤未变时", "河风轻拂")
    try:
        ws.handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": target.id},
            loop,
            app.state.pathfinder,
            ws.ControlState(),
        )
        await app.state.drain_pending_loads()
        assert app.state.load_outcomes[-1] == (target.id, True)
        assert app.state.health_evolution.branch_id == await app.state.store.current_branch_id()
        assert app.state.health_evolution.last_day == 1
        assert not any(e.event_type is EventKind.NPC_HEALTH_CHANGED for e in loop.pending_events)
    finally:
        ws.reset_anchor_registry()
