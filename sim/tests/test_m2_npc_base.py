"""M2-A2 第一批：NPC 底座骨架 + 事件扩展（m2-npc-cognition §1/§4）。

T1 断言：秒级，无 LLM，随 `-m "not bench"` 全量跑。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sim.core.events import (
    EventKind,
    MatterPayload,
    NpcActPayload,
    NpcLodChangePayload,
    matter_event,
    npc_lod_change_event,
)
from sim.npc.actions import ACTION_PAYLOAD_KEYS, ACTION_WHITELIST, payload_keys_allowed
from sim.npc.body import BodyState
from sim.npc.model import Need, NeedsError, NpcProfileData, needs_from_json
from sim.npc.needs import advance_needs, threshold_hits

# ---------------------------------------------------------------------------
# sim/npc/model.py — Need / NpcProfileData
# ---------------------------------------------------------------------------


class TestNeed:
    def test_need_frozen_replace_returns_new(self) -> None:
        # Arrange
        n = Need(name="hunger", value=0.2, weight=2.0)

        # Act
        n2 = n.advanced(0.1)

        # Assert
        assert n2.value == pytest.approx(0.3)
        assert n.value == pytest.approx(0.2)  # 原实例不变

    def test_need_value_bounds_enforced(self) -> None:
        with pytest.raises(NeedsError, match="越界"):
            Need(name="hunger", value=1.5, weight=1.0)

    def test_need_weight_positive(self) -> None:
        with pytest.raises(NeedsError, match="weight"):
            Need(name="hunger", value=0.5, weight=0.0)

    def test_advance_clips_at_one(self) -> None:
        n = Need(name="hunger", value=0.99, weight=1.0)
        assert n.advanced(0.5).value == 1.0


class TestNpcProfileData:
    def test_utility_scores_weighted(self) -> None:
        # Arrange
        p = NpcProfileData(
            npc_id="npc_1",
            name="张三",
            needs=(Need("hunger", 0.8, 2.0), Need("social", 0.4, 1.0)),
        )

        # Act / Assert
        assert p.utility_scores() == {"hunger": pytest.approx(1.6), "social": pytest.approx(0.4)}

    def test_with_lod_validates(self) -> None:
        p = NpcProfileData(npc_id="npc_1", name="张三")
        assert p.with_lod(2).lod == 2
        with pytest.raises(NeedsError, match="lod"):
            p.with_lod(3)

    def test_with_needs_immutable(self) -> None:
        p = NpcProfileData(npc_id="npc_1", name="张三")
        p2 = p.with_needs((Need("hunger", 0.1, 1.0),))
        assert p.needs == ()
        assert len(p2.needs) == 1

    def test_needs_from_json_roundtrip(self) -> None:
        raw = '[{"name":"hunger","value":0.3,"weight":1.5}]'
        needs = needs_from_json(raw)
        assert needs[0].name == "hunger"
        assert needs[0].weight == pytest.approx(1.5)

    def test_needs_from_json_rejects_garbage(self) -> None:
        with pytest.raises(NeedsError):
            needs_from_json("{not json")
        with pytest.raises(NeedsError):
            needs_from_json('{"name":"hunger"}')  # 对象而非数组


# ---------------------------------------------------------------------------
# sim/npc/needs.py — 推进与阈值
# ---------------------------------------------------------------------------


class TestNeedsAdvance:
    def test_advance_needs_progresses_and_immutable(self) -> None:
        needs = (Need("hunger", 0.0, 1.0), Need("energy", 0.0, 1.0))
        out = advance_needs(needs, ticks=100)
        assert out[0].value > 0.0
        assert needs[0].value == 0.0

    def test_unknown_need_untouched(self) -> None:
        needs = (Need("mystery", 0.5, 1.0),)
        assert advance_needs(needs)[0].value == pytest.approx(0.5)

    def test_threshold_hits_maps_remedy(self) -> None:
        # Arrange
        needs = (Need("hunger", 0.8, 1.0), Need("energy", 0.2, 1.0))

        # Act
        hits = threshold_hits(needs)

        # Assert
        assert hits == ("eat",)

    def test_threshold_below_no_hit(self) -> None:
        needs = (Need("hunger", 0.5, 1.0),)
        assert threshold_hits(needs) == ()


# ---------------------------------------------------------------------------
# sim/npc/body.py — 内感受叙事
# ---------------------------------------------------------------------------


class TestBody:
    def test_interoception_empty_is_healthy(self) -> None:
        b = BodyState(npc_id="npc_1")
        assert b.interoception_text() == "身体还算利索"

    def test_interoception_hungry(self) -> None:
        b = BodyState(npc_id="npc_1", hunger=0.9)
        assert "肚子空" in b.interoception_text()

    def test_interoception_injured(self) -> None:
        b = BodyState(npc_id="npc_1", hp=20.0)
        assert "疼" in b.interoception_text()

    def test_damage_clamps_at_zero(self) -> None:
        b = BodyState(npc_id="npc_1", hp=5.0).damaged(50.0)
        assert b.hp == 0.0


# ---------------------------------------------------------------------------
# sim/core/events.py — M2 事件扩展
# ---------------------------------------------------------------------------


class TestM2Events:
    def test_npc_lod_change_event_payload(self) -> None:
        e = npc_lod_change_event(10, "npc_1", 1, 2, "enter_range")
        assert e.event_type == EventKind.NPC_LOD_CHANGE
        assert e.payload["to_lod"] == 2

    def test_npc_lod_change_rejects_bad_lod(self) -> None:
        with pytest.raises(ValidationError):
            NpcLodChangePayload(npc_id="npc_1", from_lod=1, to_lod=5, reason="x")

    def test_npc_act_event_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            NpcActPayload(npc_id="npc_1", action="move", smuggled="x")  # type: ignore[call-arg]

    def test_matter_event_factory_rejects_non_matter_kind(self) -> None:
        with pytest.raises(ValueError, match="MATTER_"):
            matter_event(1, EventKind.MOVE, "m_1")

    def test_matter_decay_event(self) -> None:
        e = matter_event(1, EventKind.MATTER_DECAY, "m_food_1", amount=-0.2, durability=0.5)
        assert e.payload["amount"] == pytest.approx(-0.2)


# ---------------------------------------------------------------------------
# sim/npc/actions.py — 白名单
# ---------------------------------------------------------------------------


class TestActionWhitelist:
    def test_six_actions_fixed(self) -> None:
        assert (
            frozenset({"move", "work", "eat", "rest", "wander", "request_chat"}) == ACTION_WHITELIST
        )

    def test_payload_keys_allowed(self) -> None:
        assert payload_keys_allowed("move", {"path"})
        assert not payload_keys_allowed("move", {"smuggled"})
        assert not payload_keys_allowed("fly", {"wings"})

    def test_every_action_has_payload_schema(self) -> None:
        assert set(ACTION_PAYLOAD_KEYS.keys()) == set(ACTION_WHITELIST)

    def test_matter_payload_model_frozen(self) -> None:
        with pytest.raises(ValidationError):
            MatterPayload(matter_id="m", x=0, y=0, bogus=1)  # type: ignore[call-arg]
