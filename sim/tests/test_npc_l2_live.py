"""Real lifespan: completed nearby-NPC model output is queued, persisted and replayed."""

import asyncio
import json
from dataclasses import dataclass, field

import pytest

from sim.core.events import EventKind
from sim.llm.client import LlmClient, ProfileSnapshot
from sim.tests.test_health_live_wiring import stop_background
from sim.tests.test_m4c_llm_driver import _fake_result


@dataclass
class ModelControl:
    fail: bool = False
    block: asyncio.Event | None = None
    entered: asyncio.Event = field(default_factory=asyncio.Event)


@pytest.fixture
async def live_l2(monkeypatch):
    from sim.api import main

    calls = []
    control = ModelControl()

    async def complete(self, profile, messages, decision=None, *, max_tokens_override=None):
        calls.append(messages)
        control.entered.set()
        if control.block is not None:
            await control.block.wait()
        if control.fail:
            raise TimeoutError("fixture")
        return _fake_result(
            json.dumps(
                {
                    "action": "request_chat",
                    "thought": "该把旧事说清楚。",
                    "line": "陈默，今儿可还顺当？",
                }
            )
        )

    profile = ProfileSnapshot("fake", "http://invalid.local", "fake", 0, 192, "fixture")
    monkeypatch.setattr(main, "_active_profile_snapshot_provider", lambda: lambda: profile)
    monkeypatch.setattr(LlmClient, "complete", complete)
    async with main.lifespan(main.app):
        app = main.app
        await stop_background(app)
        await app.state.flush_for_anchor()
        coordinator = app.state.npc_l2
        loop = app.state.loop
        loop.clock.set_speed(1)
        entities = dict(loop.state.entities)
        protagonist = entities["chenmo"].pos
        # Isolate one conversation partner using genuine entities/profiles/map; the
        # production perception, eligibility, model service and event hooks remain real.
        far = next(
            (x, y)
            for x in range(app.state.tile_map.width)
            for y in range(app.state.tile_map.height)
            if app.state.tile_map.is_walkable(x, y)
            and abs(x - protagonist[0]) + abs(y - protagonist[1]) > 20
        )
        for npc_id, entity in entities.items():
            if npc_id != "chenmo":
                entities[npc_id] = entity.model_copy(
                    update={"pos": protagonist if npc_id == "villager_24" else far, "path": ()}
                )
        loop.state = loop.state.model_copy(update={"entities": entities, "tick": 36000})
        loop.clock.restore_tick(36000)
        await coordinator.step()  # Availability refresh; nobody is promoted yet.
        assert calls == []
        loop._run_perception()
        loop._run_npc_runtime()
        assert app.state.npc_runtime.profiles["villager_24"].lod == 2
        assert not any(
            event.event_type is EventKind.NPC_CHAT and event.payload.get("npc_id") == "villager_24"
            for event in loop.pending_events
        ), "A template must not consume the opening before the L2 decision"
        yield app, calls, control


async def _consume(app):
    await app.state.npc_l2.step()
    loop = app.state.loop
    loop.state = loop.state.model_copy(update={"tick": 36010})
    loop.clock.restore_tick(36010)
    loop._run_npc_runtime()
    return [
        event
        for event in loop.pending_events
        if event.payload.get("npc_id") == "villager_24" and event.tick == 36010
    ]


async def test_promoted_npc_model_dialogue_is_persisted_and_replays_without_model(live_l2):
    from sim.core.persistence.world_restore import expand_world

    app, calls, _ = live_l2
    events = await _consume(app)
    assert len(calls) == 1
    assert "villager_24" not in str(calls[0])
    assert calls[0][0]["content"].startswith(
        app.state.npc_runtime.profiles["villager_24"].identity_anchor
    )
    chats = [event for event in events if event.event_type is EventKind.NPC_CHAT]
    assert len(chats) == 1
    assert chats[0].payload["to_id"] == "chenmo"
    assert chats[0].payload["line"] == "陈默，今儿可还顺当？"
    thoughts = [event for event in events if event.event_type is EventKind.NPC_MONOLOGUE]
    assert any(event.payload.get("content") == "该把旧事说清楚。" for event in thoughts)
    assert all("raw" not in event.payload for event in events)
    await app.state.flush_for_anchor()
    history = await app.state.store.read_branch_history("main")
    assert any(row["payload"].get("line") == "陈默，今儿可还顺当？" for row in history)
    calls.clear()
    first = expand_world({}, history)
    second = expand_world({}, history)
    assert first.state.state_hash() == second.state.state_hash()
    assert calls == []


async def test_model_timeout_uses_template_while_world_keeps_advancing(live_l2):
    app, calls, failure = live_l2
    failure.fail = True
    events = await _consume(app)
    assert len(calls) == 1
    chats = [event for event in events if event.event_type is EventKind.NPC_CHAT]
    assert len(chats) == 1
    assert chats[0].payload["line"] != "陈默，今儿可还顺当？"
    tick = app.state.loop.state.tick
    app.state.loop.advance_frame(0.1)
    assert app.state.loop.state.tick > tick


async def test_downgrade_compacts_model_conclusions_into_durable_memory(live_l2):
    from sqlalchemy import select

    from sim.core.persistence.models import NpcMemory

    app, calls, _ = live_l2
    await _consume(app)
    loop = app.state.loop
    entities = dict(loop.state.entities)
    entities["villager_24"] = entities["villager_24"].model_copy(update={"pos": (0, 0), "path": ()})
    loop.state = loop.state.model_copy(update={"entities": entities})
    for tick in (36020, 36040):
        loop.state = loop.state.model_copy(update={"tick": tick})
        loop._run_npc_runtime()
        assert app.state.npc_runtime.profiles["villager_24"].lod == 2
    loop.state = loop.state.model_copy(update={"tick": 36050})
    loop._run_npc_runtime()
    assert app.state.npc_runtime.profiles["villager_24"].lod == 1
    await app.state.npc_l2.step()
    assert len(calls) == 1
    await app.state.flush_for_anchor()
    async with app.state.store.session_factory() as session:
        rows = list(
            await session.scalars(
                select(NpcMemory).where(
                    NpcMemory.npc_id == "villager_24", NpcMemory.source == "reason"
                )
            )
        )
    assert any("该把旧事说清楚" in row.content for row in rows)


async def test_live_world_advances_while_the_model_is_waiting(live_l2):
    app, calls, control = live_l2
    control.block = asyncio.Event()
    task = asyncio.create_task(app.state.npc_l2.step())
    await asyncio.wait_for(control.entered.wait(), timeout=1)
    try:
        async with asyncio.timeout(1), app.state.world_write_lock:
            tick = app.state.loop.state.tick
            app.state.loop.advance_frame(0.1)
            assert app.state.loop.state.tick > tick
        assert len(calls) == 1
    finally:
        control.block.set()
        await task


async def test_committed_direct_speech_is_present_in_the_npc_model_context(live_l2):
    from sim.core.events import npc_chat_event

    app, calls, _ = live_l2
    app.state.loop.enqueue(npc_chat_event(36000, "chenmo", "villager_24", "我在桥边等你。"))
    await app.state.flush_for_anchor()
    await app.state.npc_l2.step()
    assert len(calls) == 1
    assert "陈默说：我在桥边等你。" in calls[0][1]["content"]


async def test_paused_world_does_not_start_a_model_request(live_l2):
    app, calls, _ = live_l2
    app.state.loop.clock.set_speed(0)
    await app.state.npc_l2.step()
    assert calls == []


async def test_offline_startup_with_an_active_profile_never_calls_the_model(monkeypatch):
    from sim.api import main
    from sim.core.persistence.offline_store import last_recorded_at

    calls = []

    async def complete(self, *args, **kwargs):
        calls.append(args)
        return _fake_result('{"action":"rest","thought":"歇歇脚。","line":""}')

    profile = ProfileSnapshot("fake", "http://invalid.local", "fake", 0, 192, "fixture")
    monkeypatch.setattr(main, "_active_profile_snapshot_provider", lambda: lambda: profile)
    monkeypatch.setattr(LlmClient, "complete", complete)
    async with main.lifespan(main.app):
        await stop_background(main.app)
        await main.app.state.flush_for_anchor()
        recorded = await last_recorded_at(main.app.state.store, "main")
        assert recorded is not None
    monkeypatch.setattr(main, "_offline_wall_time", lambda: recorded + 1)
    async with main.lifespan(main.app):
        await stop_background(main.app)
        assert main.app.state.offline_result is not None
        assert calls == []


@pytest.mark.parametrize("mode", ["no-profile", "disabled-budget"])
async def test_missing_or_disabled_model_keeps_nearby_npcs_on_l1(monkeypatch, mode):
    from sim.api import main

    calls = []

    async def complete(self, *args, **kwargs):
        calls.append(args)
        return _fake_result('{"action":"rest","thought":"歇歇脚。","line":""}')

    profile = ProfileSnapshot("fake", "http://invalid.local", "fake", 0, 192, "fixture")
    monkeypatch.setattr(
        main,
        "_active_profile_snapshot_provider",
        lambda: lambda: profile if mode == "disabled-budget" else None,
    )
    if mode == "disabled-budget":
        monkeypatch.setenv("NPC_L2_CALLS_PER_MINUTE", "0")
    monkeypatch.setattr(LlmClient, "complete", complete)
    async with main.lifespan(main.app):
        app = main.app
        await stop_background(app)
        app.state.loop.clock.set_speed(1)
        entities = dict(app.state.loop.state.entities)
        entities["villager_24"] = entities["villager_24"].model_copy(
            update={"pos": entities["chenmo"].pos, "path": ()}
        )
        app.state.loop.state = app.state.loop.state.model_copy(
            update={"entities": entities, "tick": 36000}
        )
        await app.state.npc_l2.step()
        app.state.loop._run_npc_runtime()
        assert app.state.npc_runtime.profiles["villager_24"].lod == 1
        assert calls == []


async def test_real_player_load_restores_recorded_events_without_calling_the_model(
    live_l2, tmp_path
):
    from sim.api import ws
    from sim.api.anchors import AnchorStore

    app, calls, _ = live_l2
    await _consume(app)
    await app.state.flush_for_anchor()
    loop = app.state.loop
    history = await app.state.store.read_branch_history("main")
    saved_hash = loop.state.state_hash()
    anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
    anchor = anchors.create_item(
        "河畔旧事",
        branch_id="main",
        tick=loop.state.tick,
        seq=history[-1]["seq"],
        rng_state=app.state.rng_capture(),
        state_hash=saved_hash,
    )
    anchors.create_item(
        "新近河风",
        branch_id="main",
        tick=loop.state.tick,
        seq=history[-1]["seq"],
        rng_state=app.state.rng_capture(),
        state_hash=saved_hash,
    )
    ws.register_anchor_id(anchor.id, "河畔旧事", "河风轻拂")
    try:
        calls.clear()
        ws.handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": anchor.id},
            loop,
            app.state.pathfinder,
            ws.ControlState(),
        )
        await app.state.drain_pending_loads()
        assert app.state.load_outcomes[-1] == (anchor.id, True)
        assert loop.state.state_hash() == saved_hash
        assert await app.state.store.current_branch_id() != "main"
        assert app.state.npc_l2.take_ready() == {}
        assert calls == []
        # Loading cannot buy a fresh per-NPC budget by replacing the runtime.
        await app.state.npc_l2.step()
        assert calls == []
    finally:
        ws.reset_anchor_registry()


async def test_recovered_world_can_enable_l2_after_fault_startup(monkeypatch, tmp_path):
    from sqlalchemy import text

    from sim.api import main, ws
    from sim.api.anchors import AnchorStore

    calls = []

    async def complete(self, *args, **kwargs):
        calls.append(args)
        return _fake_result('{"action":"rest","thought":"歇歇脚。","line":""}')

    profile = ProfileSnapshot("fake", "http://invalid.local", "fake", 0, 192, "fixture")
    monkeypatch.setattr(main, "_active_profile_snapshot_provider", lambda: lambda: profile)
    monkeypatch.setattr(LlmClient, "complete", complete)
    anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
    async with main.lifespan(main.app):
        app = main.app
        await stop_background(app)
        await app.state.flush_for_anchor()
        rows = await app.state.store.read_branch_history("main")

        def save(name):
            return anchors.create_item(
                name,
                branch_id="main",
                tick=app.state.loop.state.tick,
                seq=rows[-1]["seq"],
                rng_state=app.state.rng_capture(),
            )

        anchor = save("修复前的河风")
        save("后来的河风")
        async with app.state.store.session_factory.begin() as session:
            await session.execute(text("UPDATE branches SET is_current=0"))
    async with main.lifespan(main.app):
        app = main.app
        await stop_background(app)
        assert not app.state.world_source_ready
        app.state.loop.clock.set_speed(1)
        await app.state.npc_l2.step()
        assert calls == []
        # Repair only this pytest database's pointer; then use the real queued
        # player load. The lifecycle barrier must not retain startup failure.
        async with app.state.store.session_factory.begin() as session:
            await session.execute(text("UPDATE branches SET is_current=1 WHERE id='main'"))
        ws.register_anchor_id(anchor.id, "修复前的河风", "河风轻拂")
        try:
            ws.handle_client_message(
                {"type": "load_anchor", "channel": "session", "anchor_id": anchor.id},
                app.state.loop,
                app.state.pathfinder,
                ws.ControlState(),
            )
            await app.state.drain_pending_loads()
            assert app.state.load_outcomes[-1] == (anchor.id, True)
            assert app.state.world_source_ready
            await app.state.npc_l2.step()
            assert app.state.npc_l2.available
            app.state.loop._run_perception()
            app.state.loop._run_npc_runtime()
            await app.state.npc_l2.step()
            assert len(calls) == 1
        finally:
            ws.reset_anchor_registry()
