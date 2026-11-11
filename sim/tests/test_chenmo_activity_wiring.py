"""The protagonist uses the existing action/delta seam, outside NPC utility."""

import asyncio
import json

from sqlalchemy import select

from sim.agent.intent import Intent
from sim.api import main, ws
from sim.content.protagonist import build_needs
from sim.core.events import npc_act_event
from sim.core.persistence.models import NpcProfile
from sim.npc.needs import advance_needs
from sim.perception.narrate import narrate_hunger
from sim.tests.test_npc_view_live import live_world as live_world


async def test_protagonist_action_fact_marks_stationary_delta_without_npc_utility(live_world):
    app, _, _ = live_world
    loop = app.state.loop
    loop.drain_delta()
    loop.enqueue(npc_act_event(loop.state.tick, "chenmo", "work"))
    assert "chenmo" in loop.drain_delta()
    assert ws._anim_of("chenmo") == "work"
    payload = ws.delta_payload(loop, {"chenmo"})
    assert (
        next(a for a in payload["actors"] if a["rtoken"] == ws._rtoken("chenmo"))["anim"] == "work"
    )
    loop.enqueue(npc_act_event(loop.state.tick, "chenmo", "work"))
    assert "chenmo" not in loop.drain_delta()
    assert "chenmo" not in app.state.npc_runtime.profiles


async def test_decision_loop_advances_only_protagonist_needs_and_passes_hunger(monkeypatch):
    from sim.agent.driver import ChenmoDriver

    received = []
    ready = asyncio.Event()

    async def held_driver(*args, **kwargs):
        await asyncio.Event().wait()

    async def capture(driver, state, tick, **kwargs):
        received.append(kwargs)
        ready.set()
        return False

    monkeypatch.setattr(main, "run_world_driver", held_driver)
    monkeypatch.setattr(ChenmoDriver, "decide_once", capture)
    async with main.lifespan(main.app):
        app = main.app
        assert "chenmo" not in app.state.npc_runtime.profiles
        old_villager = app.state.npc_runtime.profiles["villager_01"].needs
        loop = app.state.loop
        loop.state = loop.state.model_copy(update={"tick": loop.state.tick + 26000})
        loop.clock.restore_tick(loop.state.tick)
        app.state.chenmo_driver.request_decision()
        await asyncio.wait_for(ready.wait(), 3)
        expected = advance_needs(build_needs(), ticks=26000)
        assert app.state.chenmo_needs.needs == expected
        hunger = next(n.value for n in expected if n.name == "hunger")
        assert received[0]["interoception_text"] == narrate_hunger(hunger)
        assert not any(c.isdigit() for c in received[0]["interoception_text"])
        assert app.state.npc_runtime.profiles["villager_01"].needs == old_villager
        async with app.state.store.session_factory() as session:
            stored = await session.scalar(select(NpcProfile.needs).where(NpcProfile.id == "chenmo"))
        assert [n["value"] for n in json.loads(stored)] == [0.3, 0.2, 0.4]


async def test_load_rebuilds_projection_and_clears_past_result_without_needs_writes(live_world):
    app, _, anchors = live_world
    loop = app.state.loop
    history = await app.state.store.read_branch_history("main")
    target = anchors.create_item(
        "干活以前",
        branch_id="main",
        tick=loop.state.tick,
        seq=history[-1]["seq"],
        rng_state=app.state.rng_capture(),
    )
    driver = app.state.chenmo_driver
    previous = app.state.chenmo_needs
    previous.advance_to(loop.state.tick + 34560)
    driver._pending.append(Intent(action="work", reason="守着药铺，把手边的活做好。"))
    driver.execute_pending(loop, pathfinder=app.state.pathfinder)
    await app.state.flush_for_anchor()
    assert driver.last_intent_result
    assert app.state.coin_ledger.balance_of("chenmo") == 5
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
        assert app.state.chenmo_needs is not previous
        assert app.state.chenmo_needs.needs == build_needs()
        assert not driver.last_intent_result
        assert app.state.coin_ledger.balance_of("chenmo") == 0
    finally:
        ws.reset_anchor_registry()
