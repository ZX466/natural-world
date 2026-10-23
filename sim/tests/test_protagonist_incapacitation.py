"""DA-07：主角失能后继续世界；普通 NPC 仍真实死亡。"""

import asyncio
import hashlib
import json

import pytest

from sim.agent.combat_exec import CombatLedger, settle_attack
from sim.agent.driver import ChenmoDriver
from sim.agent.intent import Intent
from sim.api import main, ws
from sim.api.anchors import AnchorStore
from sim.content.protagonist import build_anchor
from sim.core.clock import GameClock
from sim.core.events import EventKind, agent_incapacitated_event, agent_recovered_event
from sim.core.persistence.event_validation import EventValidationError, validate_store_row
from sim.core.persistence.world_restore import WorldCheckpoint, expand_world
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.llm.client import LlmClient
from sim.npc.fire_runtime import FireRuntime
from sim.tests.test_structure_presentation_restore import load, save


def world(tick=0):
    state = WorldState(
        world_seed=42,
        tick=tick,
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(10, 10), path=((11, 10),)),
            "villager_01": EntityState(entity_id="villager_01", pos=(10, 10)),
        },
    )
    loop = TickLoop(clock=GameClock(), bus=build_default_bus(), state=state)
    loop.clock.restore_tick(tick)
    return loop


def test_fire_incapacitates_protagonist_and_kills_ordinary_npc():
    loop = world()
    fire = FireRuntime()
    events = fire.collect_deaths(loop.state, burning={(10, 10)})
    assert not any(
        e.event_type is EventKind.NPC_DEATH and e.payload["entity_id"] == "chenmo" for e in events
    )
    for event in events:
        loop.enqueue(event)
    assert "chenmo" in loop.state.entities
    assert "villager_01" not in loop.state.entities
    assert loop.state.entities["chenmo"].path == ()
    assert fire.collect_deaths(loop.state, burning={(10, 10)}) == []


@pytest.mark.parametrize("target", ["chenmo", "villager_01"])
def test_combat_terminal_policy_preserves_only_protagonist(target):
    attacker = "villager_01" if target == "chenmo" else "chenmo"
    tick = next(
        t for t in range(100) if settle_attack(attacker, target, tick=t, seed=42).outcome != "miss"
    )
    loop = world(tick)
    ledger = CombatLedger()
    ledger.apply_damage(target, ledger.hp_of(target) - 1)
    driver = ChenmoDriver(
        anchor=build_anchor(),
        llm=LlmClient(),
        profile_provider=lambda: None,
        combat_provider=lambda: (ledger, 42),
    )
    driver._issue_attack(
        loop, attacker, Intent(action="attack", target_id=target, reason="护住自己。")
    )
    if target == "chenmo":
        assert target in loop.state.entities, (
            "a lethal combat exchange must not delete the protagonist"
        )
        assert any(e.event_type.value == "agent.incapacitated" for e in loop.pending_events)
        assert not loop.context.combat_active
        assert not any(e.event_type is EventKind.NPC_DEATH for e in loop.pending_events)
    else:
        assert target not in loop.state.entities
        assert any(e.event_type is EventKind.NPC_DEATH for e in loop.pending_events)


async def test_production_recovers_with_time_jump_and_accepts_impulse(monkeypatch):
    release = asyncio.Event()
    recovered = asyncio.Event()
    frames = []
    original_driver = ws.run_world_driver

    async def held_driver(loop, manager, tile_map, on_flush, **kwargs):
        async def observe_flush(events):
            await on_flush(events)
            if any(e.event_type.value == "agent.recovered" for e in events):
                recovered.set()

        await release.wait()
        await original_driver(loop, manager, tile_map, observe_flush, **kwargs)

    async def capture(frame):
        frames.append(frame)

    monkeypatch.setattr(main, "run_world_driver", held_driver)
    monkeypatch.setattr(main.manager, "broadcast_json", capture)
    async with main.lifespan(main.app):
        app = main.app
        loop = app.state.loop
        fire = app.state.fire_runtime
        pos = loop.state.entities["chenmo"].pos
        start = loop.state.tick
        for event in fire.ignite_at(tick=start, x=pos[0], y=pos[1]):
            loop.enqueue(event)
        for event in fire.collect_deaths(loop.state, burning={pos}):
            loop.enqueue(event)
        assert "chenmo" in loop.state.entities, "fire must leave a recoverable protagonist"
        until = loop.state.entities["chenmo"].incapacitated_until
        assert until is not None and until > start
        driver = app.state.chenmo_driver
        reply = ws.handle_client_message(
            {"type": "player_impulse", "channel": "control", "text": "先歇一会"},
            loop,
            app.state.pathfinder,
        )
        assert ws.frames_of(reply)[0]["injected"] is True
        assert not await driver.decide_once(loop.state, loop.state.tick)
        assert driver._last_impulse == "先歇一会"
        driver._pending.append(Intent(action="move_to", target_pos=(1, 1), reason="旧计划"))
        assert driver.execute_pending(loop, pathfinder=app.state.pathfinder) == 0
        assert not driver._pending
        app.state.combat_ledger.apply_damage("chenmo", 100)
        app.state.combat_ledger.apply_damage("villager_02", 3)
        other_hp = app.state.combat_ledger.hp_of("villager_02")
        release.set()
        await asyncio.wait_for(recovered.wait(), timeout=30)
        loop.clock.set_speed(0)
        actor = loop.state.entities["chenmo"]
        assert actor.incapacitated_until is None
        assert loop.state.tick >= until
        assert app.state.tile_map.is_walkable(*actor.pos)
        assert actor.pos not in {(c.x, c.y) for c in fire.cells}
        assert app.state.combat_ledger.hp_of("chenmo") > 0
        assert app.state.combat_ledger.hp_of("villager_02") == other_hp
        history = await app.state.store.read_branch_history("main")
        kinds = [row["event_type"] for row in history]
        assert kinds.count("agent.incapacitated") == kinds.count("agent.recovered") == 1
        # 自动跳时结束需发送既有全量帧，让时钟和角色位置立即追平。
        await asyncio.sleep(0)
        assert any(frame["type"] == "full_snapshot" for frame in frames)
        assert "incapacitated_until" not in json.dumps(frames)
        assert "recover_at" not in json.dumps(frames)


def test_incapacitation_checkpoint_and_event_tail_preserve_deadline():
    loop = world()
    old_shape = loop.state.model_dump(mode="json")
    for actor in old_shape["entities"].values():
        actor.pop("incapacitated_until", None)
    legacy_hash = hashlib.sha256(
        json.dumps(old_shape, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert loop.state.state_hash() == legacy_hash
    loop.enqueue(agent_incapacitated_event(0, entity_id="chenmo"))
    deadline = loop.state.entities["chenmo"].incapacitated_until
    assert deadline is not None
    payload = WorldCheckpoint.capture(loop).model_dump(mode="json")
    restored = WorldCheckpoint.model_validate(payload).make_loop()
    assert restored.state.state_hash() == loop.state.state_hash()
    restored.issue_move("chenmo", [(10, 10), (11, 10)])
    restored.advance_frame(1)
    assert restored.state.entities["chenmo"].pos == (10, 10)
    with pytest.raises(ValueError, match="recovery"):
        restored.enqueue(
            agent_recovered_event(restored.state.tick, entity_id="chenmo", pos=(11, 10))
        )
    restored.replay_until(deadline)
    event = agent_recovered_event(deadline, entity_id="chenmo", pos=(11, 10))
    restored.enqueue(event)
    folded = expand_world(payload, [event.to_store_dict()])
    assert folded.state.state_hash() == restored.state.state_hash()
    assert folded.state.entities["chenmo"].incapacitated_until is None


@pytest.mark.parametrize("recovery", [False, True])
def test_lifecycle_event_store_rejects_unregistered_payload_fields(recovery):
    event = (
        agent_recovered_event(3600, entity_id="chenmo", pos=(1, 1))
        if recovery
        else agent_incapacitated_event(0, entity_id="chenmo")
    )
    row = event.to_store_dict()
    validate_store_row(row)
    row["payload"] = {**event.payload, "cause": "fire"}
    with pytest.raises(EventValidationError):
        validate_store_row(row)


@pytest.mark.parametrize("historical_load", [False, True])
async def test_incapacitation_survives_restart_and_historical_load(
    tmp_path, monkeypatch, historical_load
):
    async def idle(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "run_world_driver", idle)
    async with main.lifespan(main.app):
        app = main.app
        loop = app.state.loop
        loop.enqueue(agent_incapacitated_event(loop.state.tick, entity_id="chenmo"))
        deadline = loop.state.entities["chenmo"].incapacitated_until
        assert deadline is not None
        await app.state.flush_for_anchor()
        if historical_load:
            anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
            target = await save(app, anchors, "失能时")
            loop.replay_until(deadline)
            loop.enqueue(agent_recovered_event(deadline, entity_id="chenmo", pos=(100, 53)))
            await save(app, anchors, "醒来后")
            await load(app, target)
            assert loop.state.entities["chenmo"].incapacitated_until == deadline
    async with main.lifespan(main.app):
        assert main.app.state.loop.state.entities["chenmo"].incapacitated_until == deadline


async def test_decision_started_before_incapacitation_is_discarded_after_recovery(monkeypatch):
    entered, release, executed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def idle(*args, **kwargs):
        await asyncio.Event().wait()

    async def held_decision(self, *args, **kwargs):
        entered.set()
        await release.wait()
        return True

    def record_execution(self, *args, **kwargs):
        executed.set()
        return 0

    monkeypatch.setattr(main, "run_world_driver", idle)
    monkeypatch.setattr(ChenmoDriver, "decide_once", held_decision)
    monkeypatch.setattr(ChenmoDriver, "execute_pending", record_execution)
    async with main.lifespan(main.app):
        app = main.app
        loop = app.state.loop
        app.state.chenmo_driver.request_decision()
        await asyncio.wait_for(entered.wait(), timeout=5)
        loop.enqueue(agent_incapacitated_event(loop.state.tick, entity_id="chenmo"))
        await app.state.flush_for_anchor()
        deadline = loop.state.entities["chenmo"].incapacitated_until
        assert deadline is not None
        loop.replay_until(deadline)
        loop.enqueue(agent_recovered_event(deadline, entity_id="chenmo", pos=(100, 53)))
        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not executed.is_set()


def test_recovery_and_player_fast_forward_share_budget_when_combat_ends():
    loop = world()
    loop.issue_combat_scale(True)

    def end_combat(state, tick):
        if loop.context.combat_active:
            loop.issue_combat_scale(False)

    loop.attach_maintenance(end_combat)
    recovery, player = ws.ControlState(), ws.ControlState()
    recovery.request_fast_forward(1)
    player.request_fast_forward(1000)
    assert ws.step_fast_forward(loop, [recovery, player], budget=240) <= 240
