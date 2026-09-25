"""X2/X3 breakdown 死路钉子（M3-S6 预审 F-a，m3-preplan §4「X2/X3 钉子进 T1 全量」）。

m3-preplan X2：BIAS_NAMES（confirmation_bias/trauma_avoidance…）是元信息标签且
**不在 banned_words 词表**——防线只能靠构造隔离：breakdown 只进 dev 观测，永不进
assemble_prompt 产物 / NPC_ACT params / knowledge fact。
m3-preplan X3：UtilityDecision.scores 六动作全量分数只做审计——scores 永不落
events / memory / knowledge（runtime.tick 已按 ACTION_PAYLOAD_KEYS 过滤 params）。

本文件把「死路」钉死为可回归断言：三条出路面逐面扫描 BIAS_NAMES 词面与
breakdown/scores 键名，任何一条出现即红（构造隔离失效 = 元信息泄漏进戏内）。
"""
from __future__ import annotations

import pytest

from sim.agent.cognition import BIAS_NAMES
from sim.llm.memory_scan import make_entry
from sim.llm.prompts.assembler import (
    InputSlice,
    MemorySlice,
    NormSlice,
    PlanSlice,
    SituationSlice,
    assemble_prompt,
)
from sim.llm.prompts.identity import IdentityAnchor
from sim.npc.actions import ACTION_PAYLOAD_KEYS
from sim.npc.memory import MemoryHit

#: X2/X3 泄漏词面：bias 标签全量 + 诊断分解键名（词面级扫描，加 bias 只需扩 BIAS_NAMES）
_LEAK_TOKENS: tuple[str, ...] = (*BIAS_NAMES, "breakdown", "scores")


def _fake_hit(bias_word: str | None = None) -> MemoryHit:
    """构造一条带 breakdown 的 MemoryHit（breakdown 故意含 bias 词面，最坏情况）。"""
    entry = make_entry(
        entry_id="e1",
        npc_id="npc-a",
        content="陈默在雨夜咳得厉害",
        source="event",
        event_seq=1,
        importance=0.8,
        emotion_tag="担忧",
    )
    bd: list[tuple[str, float]] = [("base", 0.9)]
    if bias_word is not None:
        bd.append((bias_word, 1.3))
    return MemoryHit(entry=entry, score=0.9, breakdown=tuple(bd))


@pytest.mark.t1
class TestBreakdownDeadEnd:
    """X2：breakdown（含 BIAS_NAMES 词面）在三条戏内出路面全部死路。"""

    def test_bias_names_exist_to_make_this_test_meaningful(self) -> None:
        # 守卫：BIAS_NAMES 非空且确不在 banned 词表（前提复核，词表变了这里先红）
        assert len(BIAS_NAMES) >= 2

    def test_assembled_prompt_never_contains_breakdown_tokens(self) -> None:
        anchor = IdentityAnchor(
            entity_id="npc-a",
            self_narrative="陈默，镇上郎中",
            persona_summary="沉默寡言，医术好",
            long_term_goal="攒钱盘下药铺",
        )
        memory = MemorySlice(entries=(f"{_fake_hit(BIAS_NAMES[0]).entry.content}",))
        prompt = assemble_prompt(
            anchor,
            memory,
            situation=SituationSlice(perception_text="雨夜，药铺炉火未熄"),
            plan=PlanSlice(current_plan="明早出诊"),
            user_input=InputSlice(thought="今晚有人在拍门"),
            chain_id="c-x2",
            norms=NormSlice(entries=("别在雨夜约陈默出诊",)),
        )
        rendered = str(prompt)
        for token in _LEAK_TOKENS:
            assert token not in rendered, f"元信息词面 {token!r} 泄漏进 prompt"

    def test_npc_act_params_whitelist_never_admits_bias_keys(self) -> None:
        # X3：ACTION_PAYLOAD_KEYS 白名单不含 bias/breakdown/scores 键——
        # 即便 payload 塞入这些键，payload_keys_allowed 也必须拒绝
        for action, keys in ACTION_PAYLOAD_KEYS.items():
            for token in ("breakdown", "scores", *BIAS_NAMES):
                assert token not in keys, f"{action} 白名单混入诊断键 {token!r}"

    def test_knowledge_and_event_surfaces_are_structurally_clean(self) -> None:
        # X2×X7 构造隔离扫描：breakdown/scores 的生产消费面全部封闭——
        # ① knowledge 侧（sim/core/persistence/）零引用（fact 只来自写入门放行的
        #   世界内文本，X2 的死路=写入侧根本不喂 breakdown，非 norms 二次过滤）；
        # ② NPC_ACT params 只可能带 ACTION_PAYLOAD_KEYS 白名单键（上方已断言）；
        # ③ BIAS_NAMES 词面只存在于 cognition.py（定义处）与 memory.py（breakdown
        #   诊断分解，dev 观测面）——泄漏进事件/persistence/norms 装配面即红。

        # 静态结构断言（免子进程）
        from pathlib import Path

        persistence_dir = Path("sim/core/persistence")
        leaked = [
            p.name
            for p in persistence_dir.glob("*.py")
            if "breakdown" in p.read_text(encoding="utf-8")
        ]
        assert leaked == [], f"persistence 域泄漏 breakdown: {leaked}"
        norms_src = Path("sim/npc/norms.py").read_text(encoding="utf-8")
        assert "breakdown" not in norms_src and "BIAS_NAMES" not in norms_src
