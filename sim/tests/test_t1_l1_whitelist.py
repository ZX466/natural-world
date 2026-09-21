"""T1 门禁测试 — L1 动作白名单 + 升格隐藏属性契约（M2-S2）。

两块断言（docs/security/l1-whitelist.md §1/§2/§4）：
1. L1 白名单（sim/npc/actions.py）：六动作全集锁定、payload 键逐动作白名单、
   未知动作/未知键拒绝、request_chat 在白名单内（升格触发器语义）。
2. 升格隐藏属性契约（sim/npc/contract.py）：HiddenState.evaluate 触发窗口重估、
   gate_kwargs/memory_kwargs 形状、触发中放行/未触发拒绝、降格写回不降防线、
   check_reason 与闸门拒绝一致、empty() 恒等值零回归。

CI：按文件路径独立红灯信号（.github/workflows/ci.yml）。
"""

from __future__ import annotations

import pytest

from sim.agent.gate import IntentGate
from sim.agent.intent import Intent
from sim.core.world import EntityState, WorldState
from sim.llm.memory_scan import REASON_HIDDEN_LEAK, MemoryWritePipeline
from sim.npc.actions import ACTION_PAYLOAD_KEYS, ACTION_WHITELIST, payload_keys_allowed
from sim.npc.contract import HiddenState
from sim.npc.hidden import HiddenAttribute, HiddenProfile, hidden_leak_scan


def make_state(entities: dict[str, tuple[int, int]], tick: int = 100) -> WorldState:
    ents = {eid: EntityState(entity_id=eid, pos=pos) for eid, pos in entities.items()}
    return WorldState(world_seed=7, tick=tick, entities=ents)


STATE = make_state({"chenmo": (5, 5), "merchant": (8, 5)})


def make_hidden_profile() -> HiddenProfile:
    """样例隐藏属性（同 test_t1_self_unknown）：右腿旧伤 + 酒瘾 + 溺水的旧事。"""
    return HiddenProfile(
        npc_id="chenmo",
        attributes=(
            HiddenAttribute(
                id="chenmo.leg_old_injury",
                category="old_injury",
                label="右腿旧伤",
                descriptors=("旧伤", "右腿旧伤"),
                triggers=("阴雨天", "右腿"),
            ),
            HiddenAttribute(
                id="chenmo.wine_addiction",
                category="addiction",
                label="酒瘾",
                descriptors=("酒瘾",),
                triggers=("酒",),
            ),
            HiddenAttribute(
                id="chenmo.water_trauma",
                category="trauma",
                label="溺水的旧事",
                descriptors=("溺过水", "怕水"),
                triggers=("河",),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# 1. L1 动作白名单（sim/npc/actions.py）
# ---------------------------------------------------------------------------


class TestL1ActionWhitelist:
    def test_six_actions_locked(self) -> None:
        """动作全集锁定：与 m2-npc-cognition §2.1 六项一致。"""
        assert (
            frozenset({"move", "work", "eat", "rest", "wander", "request_chat"}) == ACTION_WHITELIST
        )

    @pytest.mark.parametrize(
        ("action", "keys"),
        [
            ("move", {"path"}),
            ("work", {"site"}),
            ("eat", {"food_id"}),
            ("rest", {"hours"}),
            ("wander", {"radius"}),
            ("request_chat", {"to_npc"}),
        ],
    )
    def test_payload_keys_whitelisted(self, action: str, keys: set[str]) -> None:
        assert payload_keys_allowed(action, keys)

    def test_unknown_action_rejected(self) -> None:
        assert not payload_keys_allowed("fly", {"wings"})
        assert not payload_keys_allowed("attack", {"target"})

    def test_smuggled_payload_key_rejected(self) -> None:
        """防扩展夹带：白名单键之外一律拒绝。"""
        assert not payload_keys_allowed("move", {"path", "smuggled"})
        assert not payload_keys_allowed("rest", {"hours", "secret"})
        assert payload_keys_allowed("eat", set())  # eat 的 payload 键可省略（params 可空）

    def test_request_chat_is_promotion_trigger_semantics(self) -> None:
        """request_chat 在白名单内：L1 对话请求是 L1→L2 升格触发器之一。"""
        assert "request_chat" in ACTION_WHITELIST
        assert payload_keys_allowed("request_chat", {"to_npc"})

    def test_every_action_has_payload_schema(self) -> None:
        """每个白名单动作都有 payload schema（防漏配）。"""
        assert set(ACTION_PAYLOAD_KEYS) == set(ACTION_WHITELIST)

    def test_whitelist_is_frozenset(self) -> None:
        """不可变集合：运行期不可扩（防夹带的类型层保障）。"""
        assert isinstance(ACTION_WHITELIST, frozenset)
        assert all(isinstance(v, frozenset) for v in ACTION_PAYLOAD_KEYS.values())


# ---------------------------------------------------------------------------
# 2. 升格隐藏属性契约（sim/npc/contract.py）
# ---------------------------------------------------------------------------


class TestHiddenStateEvaluate:
    def test_benign_context_no_trigger(self) -> None:
        s = HiddenState(make_hidden_profile(), frozenset())
        s2 = s.evaluate("药铺柜台前没什么客人，天色渐晚。")
        assert s2.triggered == frozenset()

    def test_trigger_context_emerges(self) -> None:
        s = HiddenState(make_hidden_profile(), frozenset())
        s2 = s.evaluate("右腿隐隐发疼，走路时更明显。")
        assert s2.triggered == frozenset({"chenmo.leg_old_injury"})

    def test_trigger_window_reestimated_each_tick(self) -> None:
        """浮现窗口按 tick 重估：触发消退即回归隐藏。"""
        s = HiddenState(make_hidden_profile(), frozenset()).evaluate("镇口的河涨了水。")
        assert "chenmo.water_trauma" in s.triggered
        s3 = s.evaluate("药铺柜台前没什么客人。")
        assert s3.triggered == frozenset()

    def test_empty_state_evaluate_noop(self) -> None:
        s = HiddenState.empty().evaluate("随便什么处境。")
        assert s == HiddenState.empty()


class TestHiddenStateConsumers:
    def test_gate_kwargs_shape(self) -> None:
        s = HiddenState(make_hidden_profile(), frozenset({"chenmo.leg_old_injury"}))
        kw = s.gate_kwargs()
        assert set(kw) == {"hidden", "triggered"}
        assert kw["hidden"] is s.profile
        assert kw["triggered"] == s.triggered

    def test_memory_kwargs_shape(self) -> None:
        s = HiddenState(make_hidden_profile(), frozenset())
        kw = s.memory_kwargs()
        assert set(kw) == {"hidden", "triggered"}
        assert kw["hidden"] is s.profile

    def test_triggered_statement_passes_gate(self) -> None:
        """升格后：触发中的属性直陈放行。"""
        s = HiddenState(make_hidden_profile(), frozenset()).evaluate("右腿隐隐发疼。")
        intent = Intent(action="wait", reason="右腿的旧伤犯了，先歇一歇。")
        v = IntentGate().revalidate_at_execution(intent, STATE, "chenmo", 99, **s.gate_kwargs())
        assert v.accepted

    def test_untriggered_leak_rejected_by_gate(self) -> None:
        """升格后：未触发属性直陈仍拒绝（浮现后仍受闸门审查）。"""
        s = HiddenState(make_hidden_profile(), frozenset()).evaluate("右腿隐隐发疼。")
        intent = Intent(action="wait", reason="其实我一直戒不掉酒瘾。")
        v = IntentGate().revalidate_at_execution(intent, STATE, "chenmo", 99, **s.gate_kwargs())
        assert v.rejected and v.reason == "hidden_attribute_leak"

    def test_demotion_writeback_uses_memory_kwargs(self) -> None:
        """降格 L1：LLM 结论压缩写回记忆走 memory_kwargs——未触发直陈拒写。"""
        s = HiddenState(make_hidden_profile(), frozenset()).evaluate("药铺里没什么事。")
        result = MemoryWritePipeline().write(
            "chenmo",
            "今天柜台前没什么客人，其实我一直戒不掉酒瘾。",
            source="reason",
            event_seq=1,
            importance=0.5,
            emotion_tag=None,
            **s.memory_kwargs(),
        )
        assert not result.accepted
        assert result.reason == REASON_HIDDEN_LEAK
        assert result.hits == ("酒瘾",)

    def test_demotion_writeback_triggered_allowed(self) -> None:
        """降格 L1：触发窗口内的属性可写入（浮现时的正常记忆）。"""
        s = HiddenState(make_hidden_profile(), frozenset()).evaluate("右腿隐隐发疼。")
        result = MemoryWritePipeline().write(
            "chenmo",
            "右腿的旧伤犯了，天阴更疼。",
            source="reason",
            event_seq=1,
            importance=0.5,
            emotion_tag=None,
            **s.memory_kwargs(),
        )
        assert result.accepted


class TestDegradedCheck:
    def test_check_reason_leak_true(self) -> None:
        """check_reason 与闸门拒绝一致：未触发直陈 → True（有泄漏）。"""
        s = HiddenState(make_hidden_profile(), frozenset())
        assert s.check_reason("我右腿有旧伤。")

    def test_check_reason_triggered_false(self) -> None:
        s = HiddenState(make_hidden_profile(), frozenset()).evaluate("右腿隐隐发疼。")
        assert not s.check_reason("右腿的旧伤犯了。")

    def test_check_reason_behavioral_hint_false(self) -> None:
        """行为暗示可议：走路瘸等行为描述不在直陈扫描面。"""
        s = HiddenState(make_hidden_profile(), frozenset())
        assert not s.check_reason("我走路有些瘸，天阴时更厉害。")

    def test_check_reason_consistent_with_leak_scan(self) -> None:
        """check_reason 与 hidden_leak_scan 同口径（同一工具，禁两处维护）。"""
        profile = make_hidden_profile()
        s = HiddenState(profile, frozenset())
        text = "我戒不掉酒瘾，但早就不怕水了。"
        assert s.check_reason(text) == bool(hidden_leak_scan(text, profile, s.triggered))

    def test_check_reason_empty_state_false(self) -> None:
        assert not HiddenState.empty().check_reason("我右腿有旧伤。")


class TestEmptyStateZeroRegression:
    """empty() 恒等值：无隐藏属性 NPC 的闸门/记忆写入行为与 M1 一致。"""

    def test_gate_accepts_same_reason(self) -> None:
        intent = Intent(action="wait", reason="我右腿有旧伤。")
        v = IntentGate().revalidate_at_execution(
            intent, STATE, "chenmo", 99, **HiddenState.empty().gate_kwargs()
        )
        assert v.accepted

    def test_memory_write_accepts_same_content(self) -> None:
        result = MemoryWritePipeline().write(
            "chenmo",
            "我右腿有旧伤。",
            source="reason",
            event_seq=1,
            importance=0.5,
            emotion_tag=None,
            **HiddenState.empty().memory_kwargs(),
        )
        assert result.accepted
