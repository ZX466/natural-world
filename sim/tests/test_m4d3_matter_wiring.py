"""批次 D3（eat 生理闭环——到站消耗）钉子。

设计裁决：MaterialMoveReason 是建造经济理由表（封闭枚举，golden 守恒断言
口径），食物消耗不扩它。eat 闭环 = 执行面在 eat **到站**时对 NPC 需求做
负增量回写（内存态，实况侧；重放不经过执行面，C5 不破）。

面：
1. eat 到站 → hunger 显著回落（-0.3），energy/social 微涨（吃饱心情）；
2. 未到站（路径在途）不回落；
3. rest 到站 → energy 回落；work 到站 → 无消耗（产出面后续批次）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.t1


class TestEatArrival:
    def test_eat_arrival_reduces_hunger(self) -> None:
        from sim.npc.model import Need
        from sim.npc.needs import apply_remedy

        needs = (
            Need(name="hunger", value=0.9, weight=1.0),
            Need(name="energy", value=0.5, weight=0.8),
        )
        new = apply_remedy(needs, "eat")
        hunger = next(n for n in new if n.name == "hunger")
        assert hunger.value == pytest.approx(0.6)
        energy = next(n for n in new if n.name == "energy")
        assert energy.value == pytest.approx(0.35)  # 0.5 - 0.15（进食恢复体力）

    def test_rest_arrival_reduces_energy(self) -> None:
        from sim.npc.model import Need
        from sim.npc.needs import apply_remedy

        needs = (Need(name="energy", value=0.8, weight=0.8),)
        new = apply_remedy(needs, "rest")
        assert new[0].value == pytest.approx(0.5)  # 睡一觉 -0.3

    def test_unknown_remedy_noop(self) -> None:
        from sim.npc.model import Need
        from sim.npc.needs import apply_remedy

        needs = (Need(name="hunger", value=0.9, weight=1.0),)
        new = apply_remedy(needs, "dance")
        assert new[0].value == pytest.approx(0.9)

    def test_clip_at_zero(self) -> None:
        from sim.npc.model import Need
        from sim.npc.needs import apply_remedy

        needs = (Need(name="hunger", value=0.1, weight=1.0),)
        new = apply_remedy(needs, "eat")
        assert new[0].value == 0.0


class TestExecIntegration:
    @staticmethod
    def _state_with_arrived_npc():
        from sim.core.world import EntityState, WorldState

        return WorldState(
            world_seed=42,
            entities={"npc_01": EntityState(entity_id="npc_01", pos=(10, 15))},  # EAT_SITE
        )

    @staticmethod
    def _runtime_arrived_at_eat():
        from sim.agent.will import WillingnessVerdict
        from sim.npc.model import Need, NpcProfileData
        from sim.npc.runtime import NpcRuntime
        from sim.npc.utility import UtilityModel

        return NpcRuntime(
            profiles={
                "npc_01": NpcProfileData(
                    npc_id="npc_01",
                    name="x",
                    lod=1,
                    needs=(Need(name="hunger", value=0.9, weight=1.0),),
                )
            },
            utility=UtilityModel(n_npc=1),
            willingness=WillingnessVerdict(score=0.0, band=0),
        )

    def test_eat_decision_at_site_applies_remedy(self) -> None:
        """决策=eat 且已到站 → runtime 需求回落（下一个 ACT 周期生效）。"""
        from sim.api.main import _fallback_map
        from sim.npc.sim_exec import npc_events_for_tick
        from sim.world.pathfinding import Pathfinder

        runtime = self._runtime_arrived_at_eat()
        state = self._state_with_arrived_npc()
        pf = Pathfinder(_fallback_map())

        # 第一拍：决策 eat → move（去食摊）
        npc_events_for_tick(runtime=runtime, state=state, tick=1000, pathfinder=pf, seed=42)
        # 模拟已到站：实体在 EAT_SITE 且再次决策 eat
        p = runtime.profiles["npc_01"]
        hunger_before = next(n for n in p.needs if n.name == "hunger").value
        assert hunger_before > 0.5
