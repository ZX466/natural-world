"""批次 D2（NPC 开口——村民意愿独白接线）钉子。

三个面：
1. sim_exec.npc_events_for_tick 增 willingness 注入：意愿冲突（band≥1）时
   每 NPC 一条 NPC_MONOLOGUE 事件（form=bubble——外在可观察面，广播全连接；
   thought 私密面归 chenmo L2）。
2. 节流：按 NPC 记上次发表 tick，冷却 _MONOLOGUE_COOLDOWN_TICKS=300（5 游戏
   分）内不再发——batch B 实测每 10 tick 一决策，50 人不节流每分钟可产 3000 条。
3. 静默路径：willingness=None → 行为零变化（零回归）。

前端零改动：monologue(bubble) 帧已被批次 A 的 ws dispatch + uiStore.pushMonologue
消费（「自语」标签渲染在心之声面板）；头顶气泡渲染不在 D2（面板先行）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.t1


def _willingness_runtime():
    """带意愿冲突的 runtime（band=2：内在挣扎族，band≥1 必产独白）。"""
    from sim.agent.will import WillingnessVerdict
    from sim.npc.model import Need, NpcProfileData
    from sim.npc.runtime import NpcRuntime
    from sim.npc.utility import UtilityModel

    def _profile(nid: str) -> NpcProfileData:
        return NpcProfileData(
            npc_id=nid, name=nid, lod=1, needs=(Need(name="hunger", value=0.9, weight=1.0),)
        )

    return NpcRuntime(
        profiles={"npc_01": _profile("npc_01"), "npc_02": _profile("npc_02")},
        utility=UtilityModel(n_npc=2),
        willingness=WillingnessVerdict(score=0.6, band=2),
    )


def _bare_runtime():
    """无意愿面 runtime（现默认形态）。"""
    from sim.npc.model import Need, NpcProfileData
    from sim.npc.runtime import NpcRuntime
    from sim.npc.utility import UtilityModel

    def _profile(nid: str) -> NpcProfileData:
        return NpcProfileData(
            npc_id=nid, name=nid, lod=1, needs=(Need(name="hunger", value=0.9, weight=1.0),)
        )

    return NpcRuntime(
        profiles={"npc_01": _profile("npc_01"), "npc_02": _profile("npc_02")},
        utility=UtilityModel(n_npc=2),
    )


def _state():
    from sim.core.world import EntityState, WorldState

    return WorldState(
        world_seed=42,
        entities={
            "npc_01": EntityState(entity_id="npc_01", pos=(5, 5)),
            "npc_02": EntityState(entity_id="npc_02", pos=(9, 9)),
        },
    )


def _bubbles(batch):
    from sim.core.events import EventKind

    return [
        e
        for e in batch
        if e.event_type is EventKind.NPC_MONOLOGUE and e.payload.get("form") == "bubble"
    ]


class TestWillingnessWiring:
    def test_willingness_produces_bubble_monologue(self) -> None:
        from sim.api.main import _fallback_map
        from sim.npc.sim_exec import npc_events_for_tick
        from sim.world.pathfinding import Pathfinder

        batch = npc_events_for_tick(
            runtime=_willingness_runtime(),
            state=_state(),
            tick=1000,
            pathfinder=Pathfinder(_fallback_map()),
            seed=42,
        )
        bubbles = _bubbles(batch)
        assert bubbles, "band=2 必须产 bubble 独白（NPC 开口）"
        assert all(str(e.payload["content"]) for e in bubbles)
        # 独白主体进 actor_id（路由面）；npc_id 进 payload
        assert all(e.actor_id == e.payload["npc_id"] for e in bubbles)

    def test_cooldown_throttles(self) -> None:
        from sim.api.main import _fallback_map
        from sim.npc.sim_exec import npc_events_for_tick
        from sim.world.pathfinding import Pathfinder

        pf = Pathfinder(_fallback_map())
        runtime = _willingness_runtime()
        state = _state()
        last: dict[str, int] = {}

        def bubbles_of(events, npc_id):
            return [
                e for e in _bubbles(events) if str(e.payload.get("npc_id", "")) == npc_id
            ]

        batch1 = npc_events_for_tick(
            runtime=runtime, state=state, tick=1000, pathfinder=pf, seed=42, monologue_last=last
        )
        assert bubbles_of(batch1, "npc_01"), "首拍 npc_01 开口"
        batch2 = npc_events_for_tick(
            runtime=runtime, state=state, tick=1100, pathfinder=pf, seed=42, monologue_last=last
        )
        assert not bubbles_of(batch2, "npc_01"), "冷却（300 tick）内同一 NPC 不再开口"

    def test_after_cooldown_speaks_again(self) -> None:
        from sim.api.main import _fallback_map
        from sim.npc.sim_exec import npc_events_for_tick
        from sim.world.pathfinding import Pathfinder

        pf = Pathfinder(_fallback_map())
        runtime = _willingness_runtime()
        state = _state()
        last: dict[str, int] = {}
        npc_events_for_tick(
            runtime=runtime, state=state, tick=1000, pathfinder=pf, seed=42, monologue_last=last
        )
        npc_events_for_tick(
            runtime=runtime, state=state, tick=1100, pathfinder=pf, seed=42, monologue_last=last
        )
        batch3 = npc_events_for_tick(
            runtime=runtime, state=state, tick=1350, pathfinder=pf, seed=42, monologue_last=last
        )
        assert _bubbles(batch3), "冷却过后再开口"

    def test_none_willingness_zero_regression(self) -> None:
        from sim.api.main import _fallback_map
        from sim.npc.sim_exec import npc_events_for_tick
        from sim.world.pathfinding import Pathfinder

        batch = npc_events_for_tick(
            runtime=_bare_runtime(),
            state=_state(),
            tick=1000,
            pathfinder=Pathfinder(_fallback_map()),
            seed=42,
        )
        assert batch, "决策照常产出"
        assert not _bubbles(batch), "无意愿面 → 零 bubble"
