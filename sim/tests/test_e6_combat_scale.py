"""E6：交手自动切战斗尺（§9 时间尺：attack 命中 → combat.scale_change True）。"""

from sim.agent.combat_exec import AttackOutcome
from sim.agent.driver import ChenmoDriver
from sim.content.protagonist import build_anchor
from sim.core.clock import GameClock
from sim.core.events import EventKind
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus


class _AlwaysHitLedger:
    def apply_attack(self, attacker, target, *, tick, seed, entropy_roll=None):
        return AttackOutcome(outcome="hit", damage=2, target_hp=8)


def _driver(**kwargs) -> ChenmoDriver:
    defaults: dict = {
        "anchor": build_anchor(),
        "llm": _NullLlm(),
        "profile_provider": lambda: None,
    }
    defaults.update(kwargs)
    return ChenmoDriver(**defaults)


class _NullLlm:
    pass


def test_attack_enters_combat_scale():
    state = WorldState(
        world_seed=42,
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(10, 10)),
            "villager_01": EntityState(entity_id="villager_01", pos=(11, 10)),
        },
    )
    loop = TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)
    driver = _driver(combat_provider=lambda: (_AlwaysHitLedger(), 42))
    from sim.agent.intent import Intent

    driver._pending.append(
        Intent(action="attack", target_id="villager_01", reason="他欺人太甚", confidence=0.9)
    )
    driver.execute_pending(loop, pathfinder=None)
    kinds = [e.event_type for e in loop.drain_events()]
    assert EventKind.COMBAT_SCALE_CHANGE in kinds


def test_scale_expires_after_window():
    state = WorldState(
        world_seed=42,
        entities={"chenmo": EntityState(entity_id="chenmo", pos=(10, 10))},
    )
    loop = TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)
    driver = _driver()
    driver._combat_until_tick = 0  # 已过期（state.tick=0 >= 0）
    driver.execute_pending(loop, pathfinder=None)
    kinds = [e.event_type for e in loop.drain_events()]
    assert EventKind.COMBAT_SCALE_CHANGE in kinds


def test_no_combat_scale_without_attack():
    state = WorldState(
        world_seed=42,
        entities={"chenmo": EntityState(entity_id="chenmo", pos=(10, 10))},
    )
    loop = TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)
    driver = _driver()
    from sim.agent.intent import Intent

    driver._pending.append(
        Intent(action="move_to", target_pos=(12, 10), reason="去铺子", confidence=0.9)
    )
    driver.execute_pending(loop, pathfinder=None)
    kinds = [e.event_type.value for e in loop.drain_events()]
    assert "combat.scale_change" not in kinds


def test_critical_attack_records_entropy_event():
    from sim.agent.combat_exec import needs_critical_entropy
    from sim.agent.intent import Intent
    from sim.core.entropy import EntropyMixer
    from sim.core.rng import RngRegistry

    state = WorldState(
        world_seed=42,
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(10, 10)),
            "villager_01": EntityState(entity_id="villager_01", pos=(11, 10)),
        },
    )
    loop = TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)
    mixer = EntropyMixer(rng=RngRegistry(world_seed=42))
    events = []

    def entropy_provider(stream: str, tick: int):
        nonlocal mixer
        mixer, event = mixer.mix(stream, tick=tick)
        events.append(event)
        return event

    driver = _driver(
        combat_provider=lambda: (_AlwaysHitLedger(), 42),
        entropy_provider=entropy_provider,
    )
    tick = next(
        t for t in range(1000) if needs_critical_entropy("chenmo", "villager_01", tick=t, seed=42)
    )
    loop.state = loop.state.model_copy(update={"tick": tick})
    driver._pending.append(
        Intent(action="attack", target_id="villager_01", reason="防身", confidence=0.9)
    )
    driver.execute_pending(loop, pathfinder=None)

    assert len(events) == 1
    assert events[0].event_type is EventKind.ENTROPY_INJECT


def test_attack_requires_melee_distance_and_records_no_entropy():
    from sim.agent.intent import Intent

    state = WorldState(
        world_seed=42,
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(10, 10)),
            "villager_01": EntityState(entity_id="villager_01", pos=(22, 10)),
        },
    )
    loop = TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)
    calls = []
    driver = _driver(
        combat_provider=lambda: (_AlwaysHitLedger(), 42),
        entropy_provider=lambda stream, tick: calls.append((stream, tick)),
    )
    driver._pending.append(Intent(action="attack", target_id="villager_01", reason="他欺人太甚"))
    driver.execute_pending(loop, pathfinder=None)
    assert not calls
    assert EventKind.COMBAT_SCALE_CHANGE not in [e.event_type for e in loop.drain_events()]


def test_live_combat_prefetch_applies_only_at_next_ten_tick_unit():
    from sim.agent.intent import Intent

    state = WorldState(
        world_seed=42,
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(10, 10)),
            "villager_01": EntityState(entity_id="villager_01", pos=(11, 10)),
        },
    )
    loop = TickLoop(clock=GameClock(speed=1), bus=build_default_bus(), state=state)
    driver = _driver(combat_provider=lambda: (_AlwaysHitLedger(), 42))
    driver._pending.append(Intent(action="attack", target_id="villager_01", reason="防身"))
    driver.execute_pending(loop, pathfinder=None)
    loop.drain_events()
    driver._pending.append(
        Intent(
            action="attack",
            target_id="villager_01",
            params={"posture": "shout"},
            reason="先喊乡亲来",
        )
    )
    driver.execute_pending(loop, pathfinder=None)
    assert not loop.drain_events()
    loop.state = state.model_copy(update={"tick": 9})
    driver.combat_tick(loop, pathfinder=None)
    assert not loop.drain_events()
    loop.state = state.model_copy(update={"tick": 10})
    driver.combat_tick(loop, pathfinder=None)
    events = loop.drain_events()
    assert any(
        e.event_type is EventKind.NPC_MONOLOGUE and e.payload["form"] == "bubble" for e in events
    )
    assert driver.take_requested()  # unit start prefetches next LLM decision


def test_bad_posture_rejected_by_shared_intent_gate():
    from sim.agent.gate import IntentGate
    from sim.agent.intent import Intent

    state = WorldState(entities={"chenmo": EntityState(entity_id="chenmo", pos=(0, 0))})
    verdict = IntentGate().validate(
        Intent(action="attack", target_id="chenmo", params={"posture": "teleport"}, reason="防身"),
        state,
        "chenmo",
    )
    assert verdict.rejected
