"""M4-B3 B 批接线钉子——runtime 消费意愿 verdict（DESIGN §10「但最终都执行」）。

B2 管线（sim/agent/will.py）已定 w₁-w₄ 合成与四档表现；本文件钉死 runtime 消费面：
- 带冲突动作执行时产 NPC_MONOLOGUE 事件（K8 通路，band≥1 必有独白微词）；
- **决策结果不被意愿改写**——NPC_ACT 的 action 与无意愿管线时逐位一致
  （类型层保证「最终都执行」的运行时面）；
- defers（band 3）不拦截、不延迟 NPC_ACT——「先做别的再绕回来」是 M4-B 后续
  计划层语义，本批只钉「不拦截」；
- 独白内容零元信息（冲突度数值/权重名不出现在 event payload）。
"""
from __future__ import annotations

import pytest

from sim.agent.will import willingness_conflict
from sim.core.events import EventKind
from sim.npc.runtime import NpcRuntime
from sim.npc.utility import UtilityModel


def _make_runtime(**kwargs) -> NpcRuntime:
    from sim.npc.model import Need, NpcProfileData

    profiles = {
        p.npc_id: p
        for p in [
            NpcProfileData(
                npc_id="chenmo",
                name="陈默",
                ocean=(50.0, 50.0, 50.0, 50.0, 50.0),
                needs=(Need(name="hunger", value=0.9, weight=1.0),),
            ),
            NpcProfileData(
                npc_id="wangpo",
                name="王婆",
                ocean=(50.0, 50.0, 50.0, 50.0, 50.0),
                needs=(Need(name="hunger", value=0.3, weight=1.0),),
            ),
        ]
    }
    return NpcRuntime(
        profiles=profiles, utility=UtilityModel(n_npc=len(profiles)), **kwargs
    )


@pytest.mark.t1
class TestRuntimeWillingnessWiring:
    def test_high_conflict_action_yields_monologue_event(self) -> None:
        # 构造高冲突场景：注入愿意管线钩子后，NPC_MONOLOGUE 出现在事件流
        rt = _make_runtime(willingness=willingness_conflict(0.9, 0.9, 0.9, 0.9))
        events = rt.tick(tick=100)
        mono = [e for e in events if e.event_type is EventKind.NPC_MONOLOGUE]
        assert mono, "高冲突动作应产独白事件"
        assert mono[0].payload["form"] in ("bubble", "thought", "plan")

    def test_zero_conflict_yields_no_monologue(self) -> None:
        # band 0 自然接受：无独白事件
        rt = _make_runtime(willingness=willingness_conflict(0.05, 0.05, 0.05, 0.05))
        events = rt.tick(tick=100)
        mono = [e for e in events if e.event_type is EventKind.NPC_MONOLOGUE]
        assert mono == []

    def test_decision_unaffected_by_willingness(self) -> None:
        # 「最终都执行」：同一世界态下，意愿管线开关不改变 NPC_ACT 的 action 序列
        rt_plain = _make_runtime()
        acts_plain = [
            (e.payload["npc_id"], e.payload["action"])
            for e in rt_plain.tick(tick=100)
            if e.event_type is EventKind.NPC_ACT
        ]
        rt_willed = _make_runtime(willingness=willingness_conflict(0.95, 0.95, 0.95, 0.95))
        acts_willed = [
            (e.payload["npc_id"], e.payload["action"])
            for e in rt_willed.tick(tick=100)
            if e.event_type is EventKind.NPC_ACT
        ]
        assert acts_plain == acts_willed

    def test_monologue_payload_has_no_meta_numbers(self) -> None:
        # X 系同款：payload 只有 npc_id/form/content（extra=forbid schema 层挡）
        rt = _make_runtime(willingness=willingness_conflict(0.9, 0.9, 0.9, 0.9))
        events = rt.tick(tick=100)
        mono = [e for e in events if e.event_type is EventKind.NPC_MONOLOGUE]
        assert mono
        assert set(mono[0].payload.keys()) == {"npc_id", "form", "content"}
