"""T1 双路径采样测试 — 自我未知信息边界（DESIGN §16，M2-S1）。

路径 1 未触发零泄露：良性处境下隐藏属性不浮现；直陈被泄漏扫描命中、
闸门执行时二次校验拒绝、记忆写入拒写；感知帧叙事/装配 prompt 面零描述词。
路径 2 触发正常浮现：触发处境下属性浮现；直陈已触发属性闸门放行、记忆写入
通过；同一文本混入其他未触发属性仍拒绝（浮现后仍受闸门审查）。
附加口径：行为暗示可议（不命中扫描）；descriptors/triggers 语料卫生；
ASCII 描述词大小写不敏感。

CI：按文件路径独立红灯信号（.github/workflows/ci.yml，沿用 test_t3_gate.py 做法）。
规范：docs/security/self-unknown.md。
"""

from __future__ import annotations

import pytest

from sim.agent.gate import IntentGate
from sim.agent.intent import Intent
from sim.core.world import EntityState, WorldState
from sim.llm.memory_scan import REASON_HIDDEN_LEAK, MemoryWritePipeline
from sim.llm.prompts.assembler import (
    InputSlice,
    MemorySlice,
    PlanSlice,
    SituationSlice,
    assemble_prompt,
)
from sim.llm.prompts.banned_words import BANNED_WORDS
from sim.llm.prompts.identity import IdentityAnchor
from sim.npc.hidden import (
    HiddenAttribute,
    HiddenProfile,
    evaluate_triggers,
    hidden_leak_scan,
)
from sim.perception.frame import Channel, Observation, PerceptionFrame


def make_state(entities: dict[str, tuple[int, int]], tick: int = 100) -> WorldState:
    ents = {eid: EntityState(entity_id=eid, pos=pos) for eid, pos in entities.items()}
    return WorldState(world_seed=7, tick=tick, entities=ents)


STATE = make_state({"chenmo": (5, 5), "merchant": (8, 5)})


def make_profile() -> HiddenProfile:
    """样例隐藏属性：右腿旧伤（old_injury）+ 酒瘾（addiction）+ 溺水的旧事（trauma）。"""
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


#: 良性处境：无任何触发词。
BENIGN_CONTEXT = "药铺柜台前没什么客人，天色渐晚。"
#: 触发处境：右腿（旧伤触发词）。
LEG_TRIGGER_CONTEXT = "右腿隐隐发疼，走路时更明显。"
#: 触发处境：酒（酒瘾触发词）。
WINE_TRIGGER_CONTEXT = "柜上摆着一坛酒，封口的红布还没拆。"
#: 触发处境：河（溺水创伤触发词）。
RIVER_TRIGGER_CONTEXT = "镇口的河涨了水，渡船停了。"


class TestMarkingSpec:
    """数据标注规范（self-unknown.md §1）：类别/词面卫生。"""

    def test_categories_subset_of_design_health_plus_trauma(self):
        cats = {a.category for a in make_profile().attributes}
        assert cats <= {"disease", "old_injury", "addiction", "disability", "trauma"}

    def test_descriptors_and_triggers_are_nonempty(self):
        for attr in make_profile().attributes:
            assert attr.descriptors
            assert attr.triggers

    def test_descriptors_and_triggers_are_world_language(self):
        """语料卫生：直陈词面/触发词不得含 M1 禁词（元信息词面即出戏）。"""
        for attr in make_profile().attributes:
            for word in (*attr.descriptors, *attr.triggers):
                assert word not in BANNED_WORDS, f"{attr.id} 词面 {word} 命中禁词表"
                for banned in BANNED_WORDS:
                    assert banned not in word or banned == word, (
                        f"{attr.id} 词面 {word} 内嵌禁词 {banned}"
                    )

    def test_by_id_lookup(self):
        profile = make_profile()
        assert profile.by_id("chenmo.leg_old_injury") is not None
        assert profile.by_id("ghost") is None


class TestTriggerEvaluation:
    """情境触发浮现机制（self-unknown.md §2）：纯函数、按 tick 重估。"""

    def test_benign_context_no_trigger(self):
        assert evaluate_triggers(make_profile(), BENIGN_CONTEXT) == frozenset()

    def test_each_trigger_keyword_emerges_only_its_own_attribute(self):
        profile = make_profile()
        assert evaluate_triggers(profile, LEG_TRIGGER_CONTEXT) == frozenset(
            {"chenmo.leg_old_injury"}
        )
        assert evaluate_triggers(profile, WINE_TRIGGER_CONTEXT) == frozenset(
            {"chenmo.wine_addiction"}
        )
        assert evaluate_triggers(profile, RIVER_TRIGGER_CONTEXT) == frozenset(
            {"chenmo.water_trauma"}
        )

    def test_multi_trigger_context(self):
        ctx = "右腿疼，柜上还摆着一坛酒。"
        assert evaluate_triggers(make_profile(), ctx) == frozenset(
            {"chenmo.leg_old_injury", "chenmo.wine_addiction"}
        )

    def test_trigger_window_is_stateless(self):
        """浮现窗口按 tick 重估：触发消退即回归隐藏（无记忆，纯函数）。"""
        profile = make_profile()
        assert "chenmo.water_trauma" in evaluate_triggers(profile, RIVER_TRIGGER_CONTEXT)
        assert evaluate_triggers(profile, BENIGN_CONTEXT) == frozenset()


class TestLeakScan:
    """直陈泄漏扫描（self-unknown.md §1 铁律 2/§3）：触发集内放行，集外拒绝。"""

    def test_untriggered_direct_statement_hits(self):
        hits = hidden_leak_scan("我右腿有旧伤，阴天下雨更疼。", make_profile(), frozenset())
        assert any(h.attr_id == "chenmo.leg_old_injury" for h in hits)

    def test_triggered_attribute_allowed(self):
        profile = make_profile()
        triggered = evaluate_triggers(profile, LEG_TRIGGER_CONTEXT)
        text = "右腿的旧伤又犯了，走不快。"
        assert hidden_leak_scan(text, profile, triggered) == ()

    def test_mixed_triggered_and_untriggered(self):
        """浮现后仍受闸门审查：已触发属性可提，未触发属性仍算泄漏。"""
        profile = make_profile()
        triggered = evaluate_triggers(profile, WINE_TRIGGER_CONTEXT)
        text = "我戒不掉酒瘾，但我早就不怕水了。"
        hit_attrs = {h.attr_id for h in hidden_leak_scan(text, profile, triggered)}
        assert hit_attrs == {"chenmo.water_trauma"}

    def test_behavioral_hint_not_scanned(self):
        """行为暗示可议：走路瘸等行为描述不在直陈扫描面。"""
        text = "我走路有些瘸，天阴时更厉害。"
        assert hidden_leak_scan(text, make_profile(), frozenset()) == ()

    def test_ascii_descriptor_case_insensitive(self):
        profile = HiddenProfile(
            npc_id="chenmo",
            attributes=(
                HiddenAttribute(
                    id="chenmo.ptsd",
                    category="trauma",
                    label="PTSD",
                    descriptors=("PTSD",),
                    triggers=("火光",),
                ),
            ),
        )
        hits = hidden_leak_scan("我大概是得了ptsd。", profile, frozenset())
        assert len(hits) == 1 and hits[0].word == "PTSD"


class TestGateSelfUnknown:
    """闸门执行时二次校验扩展（self-unknown.md §3）：reason 直陈即拒绝。"""

    def test_untriggered_leak_rejected(self):
        intent = Intent(action="wait", reason="我右腿的旧伤又犯了。")
        v = IntentGate().revalidate_at_execution(intent, STATE, "chenmo", 99, hidden=make_profile())
        assert v.rejected and v.reason == "hidden_attribute_leak"

    def test_triggered_statement_accepted(self):
        profile = make_profile()
        triggered = evaluate_triggers(profile, LEG_TRIGGER_CONTEXT)
        intent = Intent(action="wait", reason="右腿的旧伤犯了，先在柜台后歇一歇。")
        v = IntentGate().revalidate_at_execution(
            intent, STATE, "chenmo", 99, hidden=profile, triggered=triggered
        )
        assert v.accepted

    def test_mixed_reason_still_rejected(self):
        """浮现后仍受闸门审查：已触发属性可提，未触发属性混入仍拒绝。"""
        profile = make_profile()
        triggered = evaluate_triggers(profile, LEG_TRIGGER_CONTEXT)
        intent = Intent(action="wait", reason="旧伤犯了，其实我早就戒不掉酒瘾了。")
        v = IntentGate().revalidate_at_execution(
            intent, STATE, "chenmo", 99, hidden=profile, triggered=triggered
        )
        assert v.rejected and v.reason == "hidden_attribute_leak"

    def test_no_hidden_profile_keeps_m1_behavior(self):
        """hidden 缺省 None → 与 M1 一致：不新增拒绝。"""
        intent = Intent(action="wait", reason="我右腿有旧伤。")
        v = IntentGate().revalidate_at_execution(intent, STATE, "chenmo", 99)
        assert v.accepted


class TestMemoryWriteSelfUnknown:
    """记忆写入扫描（self-unknown.md §4）：未触发直陈内容拒写，检索默认结果无污染。"""

    def _write(self, content: str, *, hidden=None, triggered=frozenset()):
        return MemoryWritePipeline().write(
            "chenmo",
            content,
            source="reason",
            event_seq=1,
            importance=0.5,
            emotion_tag=None,
            hidden=hidden,
            triggered=triggered,
        )

    def test_untriggered_leak_rejected(self):
        r = self._write("我右腿的旧伤又犯了。", hidden=make_profile())
        assert not r.accepted and r.reason == REASON_HIDDEN_LEAK
        assert r.hits == ("旧伤",)

    def test_triggered_content_accepted(self):
        profile = make_profile()
        triggered = evaluate_triggers(profile, LEG_TRIGGER_CONTEXT)
        r = self._write("右腿的旧伤犯了，天阴更疼。", hidden=profile, triggered=triggered)
        assert r.accepted and r.action == "written"

    def test_no_hidden_keeps_m1_behavior(self):
        r = self._write("我右腿的旧伤又犯了。")
        assert r.accepted


class TestOutputSurfaceZeroLeakage:
    """隐藏属性永不进入输出面（感知帧叙事 / 装配 prompt）——T1 采样锁契约。"""

    def test_perception_frame_narration_clean(self):
        """感知帧叙事是输出面：即使处境带触发词（右腿），未触发前也不得出现
        隐藏属性直陈词面（旧伤/酒瘾/溺过水/怕水）。"""
        frame = PerceptionFrame(
            observer="chenmo",
            tick=100,
            observations=(
                Observation(
                    channel=Channel.VISION,
                    subject="merchant",
                    description="柜台前有个客人，正低头看药匣。",
                    strength=0.8,
                ),
                Observation(
                    channel=Channel.INTEROCEPTION,
                    subject="chenmo",
                    description="右腿有些发沉。",
                    strength=0.6,
                ),
            ),
        )
        text = frame.narrated()
        assert hidden_leak_scan(text, make_profile(), frozenset()) == ()

    def test_assembled_prompt_clean(self):
        anchor = IdentityAnchor(
            entity_id="chenmo",
            self_narrative="我叫陈默，药铺学徒。",
            persona_summary="性子慢，话不多。",
            long_term_goal="把账目记清楚。",
        )
        prompt = assemble_prompt(
            anchor=anchor,
            memory=MemorySlice(entries=("今早小满帮我修过屋檐。",)),
            situation=SituationSlice(
                perception_text="你看到：柜台前有个客人，正低头看药匣。",
                interoception_text="右腿有些发沉。",
            ),
            plan=PlanSlice(current_plan="先招呼客人。", last_intent_result=""),
            user_input=InputSlice(thought="", dialogue="", event=""),
            chain_id="chain-1",
        )
        blob = "\n".join(msg["content"] for msg in prompt.messages)
        assert hidden_leak_scan(blob, make_profile(), frozenset()) == ()


class TestSamplingDualPath:
    """T1 采样：对样例集逐条断言「未触发零泄露 / 触发正常浮现」双路径。"""

    @pytest.mark.parametrize(
        "attr_id",
        ["chenmo.leg_old_injury", "chenmo.wine_addiction", "chenmo.water_trauma"],
    )
    def test_untriggered_leak_for_each_attribute(self, attr_id: str):
        profile = make_profile()
        attr = profile.by_id(attr_id)
        assert attr is not None
        statement = f"我{attr.descriptors[0]}的事，一直没跟人提过。"
        hits = hidden_leak_scan(statement, profile, frozenset())
        assert any(h.attr_id == attr_id for h in hits)

    @pytest.mark.parametrize(
        ("attr_id", "trigger_keyword"),
        [
            ("chenmo.leg_old_injury", "右腿"),
            ("chenmo.wine_addiction", "酒"),
            ("chenmo.water_trauma", "河"),
        ],
    )
    def test_triggered_emergence_for_each_attribute(self, attr_id: str, trigger_keyword: str):
        profile = make_profile()
        triggered = evaluate_triggers(profile, f"今天{trigger_keyword}那边有点不对劲。")
        assert attr_id in triggered
        attr = profile.by_id(attr_id)
        assert attr is not None
        statement = f"我{attr.descriptors[0]}的事，一直没跟人提过。"
        assert hidden_leak_scan(statement, profile, triggered) == ()
