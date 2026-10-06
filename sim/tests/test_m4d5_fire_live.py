"""批次 D5（火灾+死亡接实况）钉子。

面：
1. bus 注册 FIRE_IGNITED / FIRE_EXTINGUISHED no-op handler（重放安全）；
2. 火灾世界自转面 FireRuntime：凌晨确定性起火（混沌流判定）→ step_fires
   蔓延 → 火到 NPC 脚下 → npc.death（对称删除）；
3. 死亡广播：npc.death 事件随帧落库+快照过滤（实体消失——代价真实可见）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.t1


class TestFireBusHandlers:
    def test_fire_ignited_registered_noop(self) -> None:
        from sim.core.events import EventKind, fire_ignited_event
        from sim.core.world import TickContext, WorldState, build_default_bus

        bus = build_default_bus()
        assert EventKind.FIRE_IGNITED in bus._handlers
        state = WorldState(world_seed=42)
        ev = fire_ignited_event(tick=1, fire_id="f1", x=5, y=5)
        result = bus.apply(state, ev, TickContext())
        assert result.state == state

    def test_fire_extinguished_registered_noop(self) -> None:
        from sim.core.events import EventKind, fire_extinguished_event
        from sim.core.world import TickContext, WorldState, build_default_bus

        bus = build_default_bus()
        assert EventKind.FIRE_EXTINGUISHED in bus._handlers
        state = WorldState(world_seed=42)
        ev = fire_extinguished_event(tick=1, fire_id="f1", x=5, y=5, end="fuel_out")
        result = bus.apply(state, ev, TickContext())
        assert result.state == state


class TestFireRuntime:
    @staticmethod
    def _runtime():
        from sim.npc.fire_runtime import FireRuntime
        from sim.world.fire import FireCell

        cell = FireCell(x=10, y=16, fire_id="f0", fuel_ticks=5, ignited_tick=99)
        return FireRuntime(cells=(cell,), fire_seq=1)

    def test_ignite_window_deterministic(self) -> None:
        """起火窗口判定是 (seed, tick) 纯函数。"""
        from sim.npc.fire_runtime import ignite_due

        assert ignite_due(42, 86400) == ignite_due(42, 86400)

    def test_spread_emits_ignite_events(self) -> None:
        """活跃火源 → step_fires 蔓延 → fire.ignited 事件批次。"""
        from sim.core.events import EventKind

        rt = self._runtime()
        events = rt.step(tick=100, walkable={(11, 16), (9, 16), (10, 17)})
        ignited = [e for e in events if e.event_type is EventKind.FIRE_IGNITED]
        assert ignited, "蔓延必须产 fire.ignited"

    def test_death_when_fire_at_npc(self) -> None:
        """火格 == NPC 位置 → npc.death 事件（实体对称删除）。"""
        from sim.core.events import EventKind
        from sim.core.world import EntityState, WorldState
        from sim.npc.fire_runtime import FireRuntime

        rt = FireRuntime(cells=(), fire_seq=0)
        state = WorldState(
            world_seed=42,
            entities={"villager_01": EntityState(entity_id="villager_01", pos=(3, 3))},
        )
        events = rt.collect_deaths(state, burning={(3, 3)})
        deaths = [e for e in events if e.event_type is EventKind.NPC_DEATH]
        assert len(deaths) == 1
        assert deaths[0].payload["entity_id"] == "villager_01"
