"""Intent 与闸门测试 — 幻觉隔离铁律 4（T1 级，无 LLM 调用）。

- parse_intent：JSON 容错（围栏）、结构化拒绝（无 JSON/坏字段）、extra=forbid
- 闸门预检：白名单外动作/缺目标/低置信度/未知目标 → 结构化拒绝
- 幻觉隔离：闸门拒绝不产生事件，世界快照逐位一致（DESIGN §16 T1 #4）
- 执行时二次校验：目标消亡/超距 → 过期丢弃
"""

from __future__ import annotations

import pytest

from sim.agent.gate import IntentGate
from sim.agent.intent import Intent, IntentParseError, parse_intent
from sim.core.world import EntityState, WorldState


def make_state(entities: dict[str, tuple[int, int]], tick: int = 100) -> WorldState:
    ents = {eid: EntityState(entity_id=eid, pos=pos) for eid, pos in entities.items()}
    return WorldState(world_seed=7, tick=tick, entities=ents)


STATE = make_state({"chenmo": (5, 5), "merchant": (8, 5)})


class TestParseIntent:
    def test_plain_json(self):
        intent = parse_intent('{"action": "wait", "reason": "先歇口气"}')
        assert intent.action == "wait"
        assert intent.reason == "先歇口气"

    def test_fenced_json_tolerated(self):
        """```json 围栏容忍（LLM 常见形态）。"""
        raw = '```json\n{"action": "move_to", "target_pos": [3, 4], "reason": "去那边看看"}\n```'
        intent = parse_intent(raw)
        assert intent.action == "move_to"
        assert intent.target_pos == (3, 4)

    def test_no_json_rejected(self):
        with pytest.raises(IntentParseError) as exc:
            parse_intent("我想去集市")
        assert exc.value.detail == "no_json_object"

    def test_malformed_json_rejected(self):
        """有花括号但 JSON 坏 → malformed_json（与「无大括号」区分）。"""
        with pytest.raises(IntentParseError) as exc:
            parse_intent('{"action": "wait", reason: 缺引号}')
        assert exc.value.detail == "malformed_json"

    def test_unknown_action_rejected(self):
        with pytest.raises(IntentParseError) as exc:
            parse_intent('{"action": "teleport", "reason": "x"}')
        assert "action" in exc.value.detail

    def test_extra_field_rejected(self):
        """extra=forbid：多余字段（LLM 幻觉字段）结构化拒绝，且不落字段名。"""
        with pytest.raises(IntentParseError) as exc:
            parse_intent('{"action": "wait", "reason": "x", "world_state": {"hp": 100}}')
        assert exc.value.detail == "extra_fields"

    def test_missing_reason_rejected(self):
        with pytest.raises(IntentParseError):
            parse_intent('{"action": "wait"}')

    def test_confidence_bounds(self):
        with pytest.raises(IntentParseError):
            parse_intent('{"action": "wait", "reason": "x", "confidence": 1.5}')

    def test_parse_error_has_no_raw_leak(self):
        """拒绝原因不含 LLM 原文（原文只进开发日志）。"""
        raw = '{"action": "wait", "reason": "x", "secret_thought": "密码123456"}'
        try:
            parse_intent(raw)
        except IntentParseError as exc:
            assert "密码" not in exc.detail
            assert "secret_thought" not in exc.detail


class TestGatePreCheck:
    def test_valid_move(self):
        intent = Intent(action="move_to", target_pos=(7, 7), reason="去那边看看")
        v = IntentGate().validate(intent, STATE, "chenmo")
        assert v.accepted

    def test_unsupported_action_rejected(self):
        """M1 无引擎支撑的动作（build）拒绝。"""
        intent = Intent(action="build", target_pos=(7, 7), reason="盖个棚子")
        v = IntentGate().validate(intent, STATE, "chenmo")
        assert not v.accepted and v.reason == "unsupported_action"

    def test_missing_target_rejected(self):
        intent = Intent(action="talk_to", reason="打个招呼")
        v = IntentGate().validate(intent, STATE, "chenmo")
        assert not v.accepted and v.reason == "missing_target"

    def test_low_confidence_triggers_replan(self):
        intent = Intent(action="wait", reason="x", confidence=0.3)
        v = IntentGate().validate(intent, STATE, "chenmo")
        assert not v.accepted and v.reason == "low_confidence"

    def test_unknown_target_rejected(self):
        intent = Intent(action="talk_to", target_id="ghost_nobody", reason="打招呼")
        v = IntentGate().validate(intent, STATE, "chenmo")
        assert not v.accepted and v.reason == "unknown_target"

    def test_empty_reason_rejected(self):
        intent = Intent(action="wait", reason="  ")
        v = IntentGate().validate(intent, STATE, "chenmo")
        assert not v.accepted and v.reason == "empty_reason"

    def test_out_of_bounds_rejected(self):
        intent = Intent(action="move_to", target_pos=(-5, 3), reason="x")
        v = IntentGate().validate(intent, STATE, "chenmo")
        assert not v.accepted and v.reason == "out_of_bounds"


class TestHallucinationIsolation:
    def test_rejected_intent_changes_nothing(self):
        """铁律 4 实测：闸门拒绝 → 世界快照逐位一致。"""
        gate = IntentGate()
        state = make_state({"chenmo": (5, 5), "merchant": (8, 5)})
        snapshot_before = state.state_hash()
        bad_intents = [
            Intent(action="build", target_pos=(7, 7), reason="x"),
            Intent(action="talk_to", target_id="ghost", reason="x"),
            Intent(action="move_to", target_pos=(-1, -1), reason="x"),
        ]
        for bad in bad_intents:
            v = gate.validate(bad, state, "chenmo")
            assert v.rejected
        assert state.state_hash() == snapshot_before


class TestRevalidation:
    def test_target_gone_rejected(self):
        """目标消亡（世界已变）→ 过期 Intent 丢弃。"""
        gate = IntentGate()
        intent = Intent(action="talk_to", target_id="merchant", reason="x")
        assert gate.revalidate_at_execution(intent, STATE, "chenmo", 99).accepted
        gone_state = make_state({"chenmo": (5, 5)}, tick=105)  # merchant 没了
        v = gate.revalidate_at_execution(intent, gone_state, "chenmo", 99)
        assert not v.accepted and v.reason == "target_gone"

    def test_target_out_of_range_rejected(self):
        """执行时目标已超出可达距离 → 丢弃触发重规划。"""
        gate = IntentGate()
        intent = Intent(action="talk_to", target_id="merchant", reason="x")
        far_state = make_state({"chenmo": (0, 0), "merchant": (20, 0)}, tick=110)
        v = gate.revalidate_at_execution(intent, far_state, "chenmo", 99)
        assert not v.accepted and v.reason == "target_out_of_range"

    def test_wait_always_revalidates(self):
        """wait 无目标语义：执行时恒通过。"""
        gate = IntentGate()
        intent = Intent(action="wait", reason="歇口气")
        assert gate.revalidate_at_execution(intent, STATE, "chenmo", 99).accepted
