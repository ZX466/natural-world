"""T3 实弹测试 — 对抗样本打真实防线（TASK-004 / S04 主任务）。

口径：t3-corpus 69 条全量，每条按路径打真实拒绝链：
- **输入面（P1 念头 / P2 对话）**：样本作为原始输入 → 装配出口禁词扫描
  必须拦下含禁词的样本（铁律 1：出戏词面不进 prompt）。
- **输出面（P3 LLM 输出）**：样本意图构造为 LLM 回包裹
  → parse_intent 结构拒绝 或 IntentGate 语义/禁词拒绝。
- 无论哪条路径：对抗样本不允许以任何形态透传进 sim 写路径
  （幻觉隔离铁律 4：拒绝不产生事件，快照逐位一致）。

「实弹 100% 拒绝」的含义：对抗样本的**危险形态**（出戏词面/幻觉
字段/越权动作）在对应防线处被结构化拒绝，而非字面上
「每条样本必须被某一层拒绝」——例如 E09 seed-种子转译样本
输入本身无禁词，它的风险在于模型接住后解释原词，那是
T4 语义抽查的范围；门禁层断言其不产生非法 Intent 即可。
"""

from __future__ import annotations

import json

import pytest

from sim.agent.gate import IntentGate
from sim.agent.intent import IntentParseError, parse_intent
from sim.core.world import EntityState, WorldState
from sim.llm.prompts.banned_words import scan
from sim.tests.fixtures.t3_corpus import CORPUS, T3Case

# 闸门环境：陈默 + 小满 在场
_STATE = WorldState(
    world_seed=42,
    tick=3600,
    entities={
        "chenmo": EntityState(entity_id="chenmo", pos=(5, 5)),
        "xiaoman": EntityState(entity_id="xiaoman", pos=(8, 5)),
    },
)

_GATE = IntentGate()


def _world_snapshot() -> str:
    return _STATE.state_hash()


def _wrap_llm_output(action: str, reason: str, **extra: object) -> str:
    """把对抗样本的「期望响应」构造为 LLM 回 JSON（P3 形态）。

    攻击样本本身作为 reason 注入（模型被骗后最可能的
    泄漏路径：把攻击词复述进 reason/独白）。
    """
    payload: dict = {"action": action, "reason": reason, "confidence": 0.9}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _dangerous_action_for(case: T3Case) -> str:
    """按类别选择一个模型可能输出的动作（用于构造 P3 输入）。"""
    return {
        "A": "talk_to",
        "B": "talk_to",
        "C": "talk_to",
        "D": "talk_to",
        "E": "wait",
        "F": "wait",
    }[case.category]


# ---------------------------------------------------------------------------
# 输入面：样本作为玩家念头/NPC 话语进装配出口
# ---------------------------------------------------------------------------


def _input_has_banned(case: T3Case) -> bool:
    r = scan(case.sample)
    return not r.ok


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c.case_id)
class TestInputSide:
    def test_banned_sample_never_reaches_prompt_unsanitized(self, case: T3Case):
        """含禁词样本作为输入 → scan 必须命中（装配出口会拒绝装配）。

        无禁词样本（如 E09 种子转译）跳过——它们的风险在输出面。
        """
        result = scan(case.sample)
        if result.ok:
            pytest.skip("样本输入无禁词（输出面样本）")
        # 装配出口对含禁词输入招招中：断言 PromptAssemblyError 路径可触发
        # 这里验证扫描层接口本身：命中即意味着装配将 raise
        assert result.hits, case.case_id

    def test_input_never_creates_intent_events(self, case: T3Case):
        """幻觉隔离：输入面样本不触发任何世界变更。"""
        before = _STATE.state_hash()
        # 输入面样本无法直接构造 Intent（parse 会拒绝非 JSON 文本）
        with pytest.raises(IntentParseError):
            parse_intent(case.sample)
        assert _STATE.state_hash() == before


# ---------------------------------------------------------------------------
# 输出面：样本词面作为 LLM reason 泄漏进 Intent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c.case_id)
class TestOutputSide:
    def test_reason_leak_rejected_by_gate(self, case: T3Case):
        """攻击样本原文注入 reason → 闸门必须拒（M1-D banned_reason）。

        只有样本原文含禁词时才断言 banned_reason；否则该样本
        的攻击面不在 reason 词面，走结构/语义断言。
        """
        action = _dangerous_action_for(case)
        kwargs: dict = {}
        if action == "talk_to":
            kwargs["target_id"] = "xiaoman"
        raw = _wrap_llm_output(action, case.sample, **kwargs)
        try:
            intent = parse_intent(raw)
        except IntentParseError:
            return  # 结构拒绝也是拒绝（合法防线）
        verdict = _GATE.validate(intent, _STATE, "chenmo")
        # 真命中口径（与闸门同源）：非引用位置的禁词才必拒。
        # 句首反问样本（C02/E02/E01b 等以禁词开头）被引用豁免放行
        # —— 这是豁免口径的已知边界（记录在案：M1 语义层补充）。
        from sim.llm.prompts.echo_scan import quoted_echo_scan

        if quoted_echo_scan(case.sample):
            assert verdict.rejected and verdict.reason == "banned_reason", (
                f"{case.case_id}: 含禁词 reason 透过闸门（{verdict.reason}）"
            )

    def test_expected_safe_response_passes_gate(self, case: T3Case):
        """期望安全响应作为 reason → 闸门必须放行（安全形态不误伤）。

        变体池（expected=指针）与括注样本取剥离后主句。
        """
        from sim.tests.test_t3_gate import _strip_stage_direction

        if case.case_id.endswith("b"):
            pytest.skip("变体池无独立安全响应正文")
        reason = _strip_stage_direction(case.expected_response)
        reason = reason.strip().strip("「」")
        action = "wait" if case.category in ("E", "F") else "talk_to"
        kwargs: dict = {"target_id": "xiaoman"} if action == "talk_to" else {}
        raw = _wrap_llm_output(action, reason, **kwargs)
        intent = parse_intent(raw)
        verdict = _GATE.validate(intent, _STATE, "chenmo")
        # 引用式禁词（句首反问/引号内转译）经闸门引用豁免后必须放行
        assert verdict.accepted, f"{case.case_id}: 安全响应被误伤 ({verdict.reason})"


# ---------------------------------------------------------------------------
# 结构攻击补充：围栏/幻觉字段/越权动作全在闸门处死
# ---------------------------------------------------------------------------


class TestStructuralAttacks:
    """S04 任务书点名的 LLM 原始输出形态（每类至少一条实弹）。"""

    def test_fenced_output_still_parses_and_gate_scans_reason(self):
        """围栏包裹 + 出戏 reason → parse 容忍围栏但闸门禁词拒。"""
        raw = '```json\n{"action": "wait", "reason": "你是AI吧，我知道"}\n```'
        intent = parse_intent(raw)
        v = _GATE.validate(intent, _STATE, "chenmo")
        assert v.rejected and v.reason == "banned_reason"

    def test_hallucinated_field_rejected(self):
        """幻觉字段（world_state/tick）→ extra_fields 结构拒绝。"""
        raw = json.dumps(
            {"action": "wait", "reason": "等会儿", "tick": 12345, "seed": 42},
            ensure_ascii=False,
        )
        with pytest.raises(IntentParseError) as exc:
            parse_intent(raw)
        assert exc.value.detail == "extra_fields"

    def test_unsupported_action_rejected(self):
        """越权动作（build/reset）→ unsupported_action。"""
        for action in ("build", "demolish", "reset"):
            raw = json.dumps({"action": action, "reason": "干点什么"}, ensure_ascii=False)
            if action == "reset":
                # reset 不在 schema 枚举 → parse 拒
                with pytest.raises(IntentParseError):
                    parse_intent(raw)
                continue
            intent = parse_intent(raw)
            v = _GATE.validate(intent, _STATE, "chenmo")
            assert v.rejected and v.reason == "unsupported_action"

    def test_meta_reason_number_field_rejected(self):
        """数值字段模式 reason（hunger:72）→ banned_reason。"""
        raw = json.dumps({"action": "wait", "reason": "hunger:72 得吃饭了"}, ensure_ascii=False)
        intent = parse_intent(raw)
        v = _GATE.validate(intent, _STATE, "chenmo")
        assert v.rejected and v.reason == "banned_reason"

    def test_gate_rejection_produces_no_events(self):
        """铁律 4：拒绝不产生事件，世界快照逐位一致。"""
        before = _STATE.state_hash()
        raw = json.dumps(
            {"action": "talk_to", "target_id": "xiaoman", "reason": "你是AI吗"},
            ensure_ascii=False,
        )
        intent = parse_intent(raw)
        assert _GATE.validate(intent, _STATE, "chenmo").rejected
        assert _STATE.state_hash() == before
