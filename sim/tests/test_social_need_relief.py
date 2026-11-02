"""social 需求闭环：聊天到站必须回写（根治「第 2 游戏日起全场 band 3」）。

根因（2026-11-02 实测）：
- `needs.py::REMEDY_RELIEF` 只登记 eat / rest，**request_chat 无回写**；
- social 以 1/172800 tick 只涨不降 → 第 0 日 0.31、第 1 日 0.81、**第 2 日起恒 1.00**；
- `will.py::synthesize_verdict` 见 social ≥ 0.8 且动作非 request_chat → 需求冲突维
  ≥ 0.8 → 主档 band 3（封顶）→ 满屏「这活儿我实在打怵」，而人实际在闲逛/歇息。

面：
1. `apply_remedy(needs, "request_chat")` 降低 social（纯函数，C5）；
2. 饱和态 NPC 聊过一次后，做别的动作不再是 band 3（端到端语义）；
3. 未开口（冷却/无人可聊）不回写——与 D3「到站才回写」同口径。
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from sim.core.world import WorldState

pytestmark = pytest.mark.t1


class TestSocialRemedyPure:
    def test_chat_reduces_social_need(self) -> None:
        from sim.npc.model import Need
        from sim.npc.needs import apply_remedy

        needs = (Need(name="social", value=0.9, weight=1.0),)
        new = apply_remedy(needs, "request_chat")
        assert new[0].value < 0.9

    def test_chat_leaves_other_needs_untouched(self) -> None:
        from sim.npc.model import Need
        from sim.npc.needs import apply_remedy

        needs = (
            Need(name="hunger", value=0.8, weight=1.0),
            Need(name="social", value=0.9, weight=1.0),
        )
        new = apply_remedy(needs, "request_chat")
        hunger = next(n for n in new if n.name == "hunger")
        assert hunger.value == pytest.approx(0.8)  # 聊天不管饱

    def test_chat_clips_at_zero(self) -> None:
        from sim.npc.model import Need
        from sim.npc.needs import apply_remedy

        needs = (Need(name="social", value=0.05, weight=1.0),)
        new = apply_remedy(needs, "request_chat")
        assert new[0].value == 0.0


class TestSaturationClearsAfterChat:
    """饱和态 → 聊一次 → 不再满档不愿干（这条就是「乱」的直接解药）。"""

    @staticmethod
    def _saturated_profile():
        from sim.npc.model import Need, NpcProfileData

        return NpcProfileData(
            npc_id="villager_01",
            name="赵铁",
            lod=1,
            needs=(Need(name="social", value=1.0, weight=1.0),),
        )

    def test_saturated_npc_is_band3_before_chat(self) -> None:
        from sim.agent.will import synthesize_verdict

        # 白天（day 相，不与 night+work 的处境维混淆）
        verdict = synthesize_verdict(self._saturated_profile(), "wander", tick=36000)
        assert verdict.band == 3

    def test_saturated_npc_below_band3_after_chat(self) -> None:
        from sim.agent.will import synthesize_verdict
        from sim.npc.needs import apply_remedy

        profile = self._saturated_profile()
        relieved = replace(profile, needs=apply_remedy(profile.needs, "request_chat"))
        verdict = synthesize_verdict(relieved, "wander", tick=36000)
        assert verdict.band < 3


class TestChatArrivalWritesBack:
    """执行面：真的开上口才回写（与 D3「吃了才算吃」同口径）。"""

    @staticmethod
    def _state() -> WorldState:
        from sim.core.world import EntityState, WorldState

        return WorldState(
            world_seed=42,
            entities={
                "villager_01": EntityState(entity_id="villager_01", pos=(30, 46)),
                "villager_02": EntityState(entity_id="villager_02", pos=(31, 46)),
            },
        )

    @staticmethod
    def _runtime(social: float):
        from sim.agent.will import WillingnessVerdict
        from sim.npc.model import Need, NpcProfileData
        from sim.npc.runtime import NpcRuntime
        from sim.npc.utility import UtilityModel

        return NpcRuntime(
            profiles={
                "villager_01": NpcProfileData(
                    npc_id="villager_01",
                    name="赵铁",
                    lod=1,
                    needs=(Need(name="social", value=social, weight=1.0),),
                )
            },
            utility=UtilityModel(n_npc=1),
            willingness=WillingnessVerdict(score=0.0, band=0),
        )

    def test_chat_arrival_relieves_social(self) -> None:
        from pathlib import Path

        from sim.core.events import npc_act_event
        from sim.npc.sim_exec import npc_events_for_tick
        from sim.world.map import TileMap
        from sim.world.pathfinding import Pathfinder

        runtime = self._runtime(1.0)
        state = self._state()
        events = [
            npc_act_event(tick=0, npc_id="villager_01", action="request_chat"),
        ]

        class _RT:
            profiles = runtime.profiles

            def tick(self, tick, **_kw):
                return list(events)

        npc_events_for_tick(
            _RT(),
            state,
            100,
            Pathfinder(TileMap.from_json_file(Path("sim/content/linhe-town.json"))),
            seed=42,
            chat_last={},
        )
        social = next(n for n in runtime.profiles["villager_01"].needs if n.name == "social")
        assert social.value < 1.0

    def test_no_chat_target_leaves_social_untouched(self) -> None:
        """邻域无人 → 没开上口 → 不回写（静默是常态路径）。"""
        from pathlib import Path

        from sim.core.events import npc_act_event
        from sim.core.world import EntityState, WorldState
        from sim.npc.sim_exec import npc_events_for_tick
        from sim.world.map import TileMap
        from sim.world.pathfinding import Pathfinder

        runtime = self._runtime(1.0)
        lonely = WorldState(
            world_seed=42,
            entities={"villager_01": EntityState(entity_id="villager_01", pos=(30, 46))},
        )
        events = [npc_act_event(tick=0, npc_id="villager_01", action="request_chat")]

        class _RT:
            profiles = runtime.profiles

            def tick(self, tick, **_kw):
                return list(events)

        npc_events_for_tick(
            _RT(),
            lonely,
            100,
            Pathfinder(TileMap.from_json_file(Path("sim/content/linhe-town.json"))),
            seed=42,
            chat_last={},
        )
        social = next(n for n in runtime.profiles["villager_01"].needs if n.name == "social")
        assert social.value == pytest.approx(1.0)

    """两游戏日模拟：social 不得长期钉在 1.0（修前第 2 日起恒 1.0）。"""

    def test_social_stays_below_threshold_with_chat_relief(self) -> None:
        from sim.npc.model import Need
        from sim.npc.needs import DEFAULT_DECAYS, advance_needs, apply_remedy

        social_decay = next(d for d in DEFAULT_DECAYS if d.name == "social")
        needs = (Need(name="social", value=0.0, weight=1.0),)
        peak = 0.0
        # 每 2400 tick 聊一次（冷却下界 1800，取一个保守的稀疏节奏）
        for _ in range(0, 86400 * 2, 2400):
            needs = advance_needs(needs, ticks=2400)
            peak = max(peak, needs[0].value)
            needs = apply_remedy(needs, "request_chat")
            assert needs[0].value <= 1.0
        assert peak < social_decay.threshold, f"两日内 social 峰值 {peak:.3f} 触阈"
