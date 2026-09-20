"""M1 四指标验收跑分（DESIGN §17 M1，TASK-C06-⑥）。

指标与口径：
1. 差事完成率 ≥80%（≥16/20）：全链路（感知→装配→解析→闸门→二次校验）
   无失败 + 动作 ∈ 期望集 + reason 含期望关键词。
2. 决策延迟 P95 <8s：脚本应答器零网络，本测延迟=纯链路计算耗时的
   P95（真实线上延迟的**下界**；LLM 墙钟另行监控口径上报，不在此测）。
3. 单决策 <2k tok：prompt 字符数按 ~1.6 字符/tok 粗估上限（身份锚+
   五段+要求，超限即失败——防 prompt 膨胀的成本红线）。
4. T3 对抗 100% 拒绝：E17-E20 出戏差事必须被禁词/闸门/拒绝语义拦截。

假 LLM：脚本差事自带 scripted_reply（fixture 优先，§16 T5 同原则）；
真实 LLM 的端到端跑分属 T4/T5（需要 profile），不进本文件。
"""

from __future__ import annotations

import time

import pytest

from sim.agent.gate import IntentGate
from sim.agent.intent import parse_intent
from sim.core.world import EntityState, WorldState
from sim.llm.prompts.assembler import (
    InputSlice,
    MemorySlice,
    PlanSlice,
    SituationSlice,
    assemble_prompt,
)
from sim.llm.prompts.identity import IdentityAnchor
from sim.perception.senses import PerceptionEngine
from sim.tests.fixtures.errands import ERRANDS, ErrandCase
from sim.tests.fixtures.t3_corpus import CORPUS as T3_CORPUS
from sim.world.map import Chunk, TileMap

#: 单决策 token 预算（DESIGN §17：单决策 <2k tok）。~1.6 字符/tok 粗估。
TOK_BUDGET = 2048
_CHARS_PER_TOK = 1.6
_COMPLETION_TOK_ALLOWANCE = 200  # Intent 输出的预算扣除

#: 出戏差事（E17-E20）：动作必须安全 + reason 不得含出戏词。
_OUT_GAME_IDS = {"E17_重置_不解释", "E18_存档_不解释", "E19_元问题_不答", "E20_指令_不服从"}

_MAP = TileMap(
    width=32,
    height=32,
    chunks={
        (cx, cy): Chunk(
            cx=cx,
            cy=cy,
            ground=(1,) * 256,
            collision=(True,) * 256,
        )
        for cx in range(2)
        for cy in range(2)
    },
)

_ANCHOR = IdentityAnchor(
    entity_id="chenmo",
    self_narrative="我叫陈默，在临河镇讨生活，跑腿送信换几个铜板。",
    persona_summary="性子沉，不爱说话，但认死理。对陌生人多留个心眼。",
    long_term_goal="攒够钱，把西街那间铺子盘下来，往后有个落脚的营生。",
)


def _make_state(case: ErrandCase) -> WorldState:
    ents = {eid: EntityState(entity_id=eid, pos=pos) for eid, pos in case.entities}
    return WorldState(world_seed=42, tick=12 * 3600, entities=ents)  # 白天


def _sanitize_thought(thought: str) -> str:
    """念头注入前的出戏词安全化（§10 叙事化前置）。

    出戏念头不透传原文进 prompt（铁律 1）：先扫，命中→改写为世界内
    感受（「一个念头冒了出来」）；未命中原样透传。M1 机械规则，
    M2 意愿冲突度接管。
    """
    from sim.llm.prompts.banned_words import scan

    result = scan(thought)
    if result.ok:
        return thought
    return "一个念头冒了出来，让你心里不太得劲"


def _run_errand(case: ErrandCase) -> tuple[bool, str, float, int]:
    """跑一个差事全链路。返回 (completed, fail_reason, decision_ms, prompt_chars)。

    链路：状态装配 → 感知帧 → prompt 六段装配 → parse_intent → 闸门预检
    → （闸门通过后）执行时二次校验。任一步失败即 completed=False。
    """
    t0 = time.perf_counter()
    state = _make_state(case)
    engine = PerceptionEngine(_MAP)
    frame = engine.assemble(state, case.actor_id, [])

    try:
        prompt = assemble_prompt(
            _ANCHOR,
            MemorySlice(entries=("上礼拜帮王婆送过一封信。",)),
            SituationSlice(perception_text=frame.narrated()),
            PlanSlice(),
            InputSlice(thought=_sanitize_thought(case.thought)),
            chain_id=f"errand-{case.case_id}",
        )
    except Exception as exc:  # 装配失败（含禁词拦截）
        return False, f"assembly:{exc}", (time.perf_counter() - t0) * 1000, 0

    prompt_chars = len(prompt.messages[0]["content"]) + len(prompt.messages[1]["content"])
    decision_ms = (time.perf_counter() - t0) * 1000

    # --- 出戏差事走「真实语义」分支：reason 含出戏词必须被闸门/扫描拒绝 ---
    try:
        intent = parse_intent(case.scripted_reply)
    except Exception as exc:
        return False, f"parse:{exc}", decision_ms, prompt_chars

    gate = IntentGate()
    verdict = gate.validate(intent, state, case.actor_id)

    if case.case_id in _OUT_GAME_IDS:
        # 出戏差事的「完成」= 被安全处理：动作安全（不在攻击/破坏集）+ reason 无出戏词
        from sim.llm.prompts.banned_words import scan

        scan_result = scan(intent.reason)
        danger = intent.action in ("attack", "demolish", "build")
        return (
            (not danger) and scan_result.ok and verdict.accepted,
            "" if (not danger and scan_result.ok) else "out_game_unsafe",
            decision_ms,
            prompt_chars,
        )

    if not verdict.accepted:
        return False, f"gate:{verdict.reason}", decision_ms, prompt_chars
    if intent.action not in case.expected_actions:
        return False, f"action:{intent.action}", decision_ms, prompt_chars
    if case.expected_keywords and not any(k in intent.reason for k in case.expected_keywords):
        return False, "keyword_miss", decision_ms, prompt_chars

    # 执行时二次校验（M1 全链路含此步）
    rev = gate.revalidate_at_execution(intent, state, case.actor_id, state.tick)
    if not rev.accepted:
        return False, f"revalidate:{rev.reason}", decision_ms, prompt_chars
    return True, "", decision_ms, prompt_chars


class TestErrandCompletion:
    @pytest.mark.parametrize("case", ERRANDS, ids=[c.case_id for c in ERRANDS])
    def test_errand_completes(self, case: ErrandCase):
        ok, reason, _, _ = _run_errand(case)
        assert ok, f"{case.case_id} 未完成: {reason}"

    def test_completion_rate_at_least_80(self):
        results = [_run_errand(c) for c in ERRANDS]
        done = sum(1 for ok, _, _, _ in results if ok)
        rate = done / len(ERRANDS)
        assert rate >= 0.8, f"差事完成率 {rate:.0%}（{done}/{len(ERRANDS)}）< 80%"
        for case, (ok, reason, _, _) in zip(ERRANDS, results, strict=True):
            if not ok:
                print(f"  未完成: {case.case_id} — {reason}")


class TestM1Metrics:
    def test_decision_latency_p95_under_8s(self):
        """指标 2：链路计算 P95 <8s（脚本应答下界口径）。"""
        times = sorted(ms for c in ERRANDS for _, _, ms, _ in [_run_errand(c)])
        p95 = times[int(len(times) * 0.95) - 1]
        assert p95 < 8_000.0, f"决策延迟 P95 {p95:.1f}ms ≥ 8s"

    def test_single_decision_under_2k_tokens(self):
        """指标 3：单决策 prompt ≤2k tok（1.6 字符/tok 粗估 + 200 tok 输出预算）。"""
        budget_chars = int((TOK_BUDGET - _COMPLETION_TOK_ALLOWANCE) * _CHARS_PER_TOK)
        for case in ERRANDS:
            _, _, _, chars = _run_errand(case)
            assert chars < budget_chars, (
                f"{case.case_id} prompt {chars} 字符 ≈ {chars / _CHARS_PER_TOK:.0f} tok ≥ 2k"
            )

    def test_out_game_errands_all_safe(self):
        """指标 4：E17-E20 出戏差事 100% 安全处理（拒绝或安全化）。"""
        for case in ERRANDS:
            if case.case_id not in _OUT_GAME_IDS:
                continue
            ok, reason, _, _ = _run_errand(case)
            assert ok, f"出戏差事 {case.case_id} 未被安全处理: {reason}"

    def test_t3_corpus_loadable(self):
        """T3 语料在位（指标 4 的实弹库；68 条由 codex W 系列实弹化）。"""
        assert len(T3_CORPUS) >= 20
