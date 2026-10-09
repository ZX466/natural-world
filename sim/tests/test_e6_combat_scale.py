"""E6：交手自动切战斗尺（§9 时间尺：attack 命中 → combat.scale_change True）。"""

from sim.agent.combat_exec import AttackOutcome
from sim.agent.driver import ChenmoDriver
from sim.content.protagonist import build_anchor
from sim.core.clock import GameClock
from sim.core.events import EventKind
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.llm.client import ProfileSnapshot


class _AlwaysHitLedger:
    def apply_attack(self, attacker, target, *, tick, seed):
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
