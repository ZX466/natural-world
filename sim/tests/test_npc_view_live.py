"""Real lifespan/commit/load seams: stationary actions and narrative caches."""

from pathlib import Path

import pytest

from sim.api import main, ws
from sim.api.anchors import AnchorStore
from sim.api.settings import ProfileStore
from sim.core.events import npc_act_event, npc_chat_event, npc_health_changed_event
from sim.tests.test_health_live_wiring import stop_background


@pytest.fixture
async def live_world(monkeypatch, tmp_path):
    from sim.api import anchors, settings
    from sim.npc import sim_exec

    database = Path(tmp_path) / "world.db"
    monkeypatch.setattr(anchors, "_anchor_store", AnchorStore(f"sqlite:///{database.as_posix()}"))
    monkeypatch.setattr(
        settings, "_profile_store", ProfileStore(f"sqlite:///{database.as_posix()}")
    )
    decision = ["rest"]
    monkeypatch.setattr(
        sim_exec,
        "npc_events_for_tick",
        lambda runtime, state, tick, *a, **kw: [
            npc_act_event(tick, "villager_01", decision[0]),
        ],
    )
    async with main.lifespan(main.app):
        await stop_background(main.app)
        await main.app.state.flush_for_anchor()
        yield main.app, decision, anchors._anchor_store


def drive_action(app):
    loop = app.state.loop
    loop.state = loop.state.model_copy(update={"tick": 10})
    loop.clock.restore_tick(10)
    hook = next(h for h in loop._npc_hooks if h.__name__ == "_npc_tick_hook")
    for event in hook(loop.state, 10) or []:
        loop.enqueue(event)


async def test_stationary_changed_action_marks_delta_once_and_does_not_require_movement(live_world):
    app, decision, _ = live_world
    loop = app.state.loop
    loop.drain_delta()
    before = loop.state.entities["villager_01"].pos
    drive_action(app)
    assert loop.state.entities["villager_01"].pos == before
    delta = ws.delta_payload(loop, loop.drain_delta())
    row = next(a for a in delta["actors"] if a["rtoken"] == ws._rtoken("villager_01"))
    assert row["anim"] == "rest"
    drive_action(app)
    assert "villager_01" not in loop.drain_delta()
    decision[0] = "work"
    drive_action(app)
    assert "villager_01" in loop.drain_delta()


async def test_committed_health_and_relationships_update_narratives_without_actor_movement(
    live_world,
):
    app, _, _ = live_world
    loop = app.state.loop
    old = ws.snapshot_payload(loop, app.state.tile_map)["npc_views"]
    assert all(v["rtoken"] != ws._rtoken("villager_01") for v in old)
    ws.delta_payload(loop, set())  # Establish the connected observer's baseline.
    loop.enqueue(npc_chat_event(loop.state.tick, "villager_01", "chenmo", "坐下歇会儿。"))
    loop.enqueue(
        npc_health_changed_event(
            loop.state.tick,
            npc_id="chenmo",
            category="old_injury",
            code="wrist_strain",
            severity=0.9,
        )
    )
    await app.state.flush_for_anchor()
    delta = ws.delta_payload(loop, set())
    # Existing fauna silhouettes are included even with an empty moved set.
    assert all(row.get("sprite", "").startswith("fauna_") for row in delta["actors"])
    assert {row["rtoken"] for row in delta["npc_views"]} == {
        ws._rtoken("chenmo"),
        ws._rtoken("villager_01"),
    }
    assert any("发作得厉害" in text for row in delta["npc_views"] for text in row["health"])
    assert "npc_views" not in ws.delta_payload(loop, set())


async def test_player_load_clears_action_and_narrative_future_in_the_real_success_block(live_world):
    app, _, anchors = live_world
    loop = app.state.loop
    history = await app.state.store.read_branch_history("main")
    target = anchors.create_item(
        "尚未相识",
        branch_id="main",
        tick=loop.state.tick,
        seq=history[-1]["seq"],
        rng_state=app.state.rng_capture(),
    )
    drive_action(app)
    loop.enqueue(npc_chat_event(loop.state.tick, "villager_01", "chenmo", "坐下歇会儿。"))
    await app.state.flush_for_anchor()
    assert ws._anim_of("villager_01") == "rest"
    assert any(
        v["rtoken"] == ws._rtoken("villager_01")
        for v in ws.snapshot_payload(loop, app.state.tile_map)["npc_views"]
    )
    ws.register_anchor_id(target.id, target.name, "河风轻拂")
    try:
        ws.handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": target.id},
            loop,
            app.state.pathfinder,
            ws.ControlState(),
        )
        await app.state.drain_pending_loads()
        assert app.state.load_outcomes[-1] == (target.id, True)
        assert ws._anim_of("villager_01") == "idle"
        assert not any(
            v["rtoken"] == ws._rtoken("villager_01")
            for v in ws.snapshot_payload(loop, app.state.tile_map)["npc_views"]
        )
    finally:
        ws.reset_anchor_registry()


async def test_ending_self_trigger_window_retracts_health_without_a_new_emergence_event(
    live_world, monkeypatch
):
    from sim.core.events import EventKind
    from sim.npc.contract import HiddenState

    app, _, _ = live_world
    state = app.state.hidden_states["chenmo"]
    attribute = state.profile.attributes[0]
    desired = [frozenset({attribute.id})]

    def evaluate(current, context):
        ids = (
            frozenset(a.id for a in current.profile.attributes) if current.profile else frozenset()
        )
        return HiddenState(current.profile, desired[0] & ids)

    monkeypatch.setattr(HiddenState, "evaluate", evaluate)
    drive_action(app)
    visible = ws.snapshot_payload(app.state.loop, app.state.tile_map)["npc_views"]
    assert any(attribute.label in text for row in visible for text in row["health"])
    await app.state.flush_for_anchor()
    ws.delta_payload(app.state.loop, set())
    desired[0] = frozenset()
    drive_action(app)
    assert not any(
        e.event_type is EventKind.NPC_HIDDEN_EMERGE for e in app.state.loop.pending_events
    )
    delta = ws.delta_payload(app.state.loop, set())["npc_views"]
    assert any(row["rtoken"] == ws._rtoken("chenmo") for row in delta)
    assert all(attribute.label not in text for row in delta for text in row.get("health", []))


async def test_restart_hydrates_committed_known_people_without_live_decisions(
    monkeypatch, tmp_path
):
    from sim.api import anchors, settings

    database = tmp_path / "world.db"
    monkeypatch.setattr(anchors, "_anchor_store", AnchorStore(f"sqlite:///{database.as_posix()}"))
    monkeypatch.setattr(
        settings, "_profile_store", ProfileStore(f"sqlite:///{database.as_posix()}")
    )
    for restarting in (False, True):
        async with main.lifespan(main.app):
            await stop_background(main.app)
            loop = main.app.state.loop
            await main.app.state.flush_for_anchor()
            if not restarting:
                loop.enqueue(
                    npc_chat_event(loop.state.tick, "villager_01", "chenmo", "坐下歇会儿。")
                )
                await main.app.state.flush_for_anchor()
            full = ws.snapshot_payload(loop, main.app.state.tile_map)["npc_views"]
            assert any(row["rtoken"] == ws._rtoken("villager_01") for row in full)
