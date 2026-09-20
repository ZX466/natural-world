"""prompt 装配器测试 — §8 六段结构 + 铁律防线（T1 级，无 LLM 调用）。

- 段序固定：messages[0]=身份锚（前缀缓存分界），messages[1]=其余五段
- 零元信息：装配产物过禁词表（出站终扫），命中即抛 PromptAssemblyError
- 视角锁定：身份锚渲染为第一人称叙事文本
- cache_hit 探针：同锚连发 → True，换锚 → False
"""

from __future__ import annotations

import pytest

from sim.llm.client import _LAST_ANCHOR_FP, _prefix_cache_probe
from sim.llm.prompts.assembler import (
    AssembledPrompt,
    InputSlice,
    MemorySlice,
    PlanSlice,
    PromptAssemblyError,
    SituationSlice,
    assemble_prompt,
)
from sim.llm.prompts.identity import IdentityAnchor


@pytest.fixture()
def anchor() -> IdentityAnchor:
    return IdentityAnchor(
        entity_id="chenmo",
        self_narrative="我叫陈默，在临河镇讨生活，跑腿送信换几个铜板。",
        persona_summary="性子沉，不爱说话，但认死理。对陌生人多留个心眼。",
        long_term_goal="攒够钱，把西街那间铺子盘下来，往后有个落脚的营生。",
    )


class TestSixSectionOrder:
    def test_messages_shape(self, anchor: IdentityAnchor):
        prompt = assemble_prompt(
            anchor,
            MemorySlice(entries=("上礼拜帮王婆送过一封信。",)),
            SituationSlice(
                perception_text="你看到：有人在不远处。", interoception_text="肚子有点饿。"
            ),
            PlanSlice(current_plan="去集市看看行情", last_intent_result=""),
            InputSlice(thought="该去赚钱了"),
            chain_id="chain001",
        )
        assert len(prompt.messages) == 2
        assert prompt.messages[0]["role"] == "system"
        assert prompt.messages[1]["role"] == "user"
        # 段序：内感受在感知前；记忆在最前；念头在计划后、要求前
        body = prompt.messages[1]["content"]
        pos_memory = body.index("上礼拜帮王婆")
        pos_hunger = body.index("肚子有点饿")
        pos_percept = body.index("有人在不远处")
        pos_plan = body.index("去集市看看行情")
        pos_thought = body.index("该去赚钱了")
        pos_req = body.index("只输出一个 JSON")
        assert pos_memory < pos_hunger < pos_percept < pos_plan < pos_thought < pos_req

    def test_empty_slices_minimal_body(self, anchor: IdentityAnchor):
        """全空切片 → 只有 [要求] 段（结构完整，不留空段）。"""
        prompt = assemble_prompt(
            anchor, MemorySlice(), SituationSlice(), PlanSlice(), InputSlice(), "c2"
        )
        assert "只输出一个 JSON" in prompt.messages[1]["content"]
        assert "还记得的事" not in prompt.messages[1]["content"]

    def test_fingerprint_stable(self, anchor: IdentityAnchor):
        p1 = assemble_prompt(
            anchor, MemorySlice(), SituationSlice(), PlanSlice(), InputSlice(), "c3"
        )
        p2 = assemble_prompt(
            anchor, MemorySlice(), SituationSlice(), PlanSlice(), InputSlice(), "c4"
        )
        assert p1.first_message_fingerprint() == p2.first_message_fingerprint()
        assert len(p1.first_message_fingerprint()) == 64


class TestIdentityAnchor:
    def test_render_first_person(self, anchor: IdentityAnchor):
        text = anchor.render()
        assert "我叫陈默" in text
        assert "陈默" in text  # 自述里有名字（第一人称叙述允许自称）

    def test_frozen(self, anchor: IdentityAnchor):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            anchor.self_narrative = "改"

    def test_entity_id_never_rendered_alone(self, anchor: IdentityAnchor):
        """entity_id 只作寻址主键；render() 输出不含「entity_id」字样。"""
        assert "entity_id" not in anchor.render()


class TestBannedWordGate:
    def test_meta_word_in_memory_rejected(self, anchor: IdentityAnchor):
        """记忆文本带出戏词 → 装配失败（出站终扫兜底，S2 同一词表）。"""
        with pytest.raises(PromptAssemblyError) as exc:
            assemble_prompt(
                anchor,
                MemorySlice(entries=("我总觉得这个世界像个游戏。",)),
                SituationSlice(),
                PlanSlice(),
                InputSlice(),
                "c5",
            )
        assert any(h in ("游戏",) for h in exc.value.hits)

    def test_meta_word_in_thought_rejected(self, anchor: IdentityAnchor):
        with pytest.raises(PromptAssemblyError):
            assemble_prompt(
                anchor,
                MemorySlice(),
                SituationSlice(),
                PlanSlice(),
                InputSlice(thought="干脆读档重来一次吧"),
                "c6",
            )

    def test_clean_assembly_passes(self, anchor: IdentityAnchor):
        prompt = assemble_prompt(
            anchor,
            MemorySlice(entries=("王婆给的铜板还剩三个。",)),
            SituationSlice(perception_text="四周很安静。"),
            PlanSlice(),
            InputSlice(),
            "c7",
        )
        assert isinstance(prompt, AssembledPrompt)


class TestCacheProbe:
    def test_same_anchor_two_calls(self):
        """同锚连发：第一次 False（无历史），第二次 True（前缀命中判定）。"""
        _LAST_ANCHOR_FP.clear()
        messages = [{"role": "system", "content": "锚A"}, {"role": "user", "content": "x"}]
        assert _prefix_cache_probe("p1", messages) is False
        assert _prefix_cache_probe("p1", messages) is True

    def test_anchor_change_resets(self):
        _LAST_ANCHOR_FP.clear()
        anchor_a = [{"role": "system", "content": "锚A"}]
        anchor_b = [{"role": "system", "content": "锚B"}]
        _prefix_cache_probe("p1", anchor_a)
        assert _prefix_cache_probe("p1", anchor_b) is False


class TestLogSetup:
    def test_setup_logging_idempotent(self):
        from sim.core.logsetup import setup_logging

        setup_logging()
        setup_logging()  # 幂等：不抛异常

    def test_redact_sensitive_in_chain(self):
        """敏感键日志值被 *** 替换（K8 全局链生效）。"""
        import structlog
        from structlog.testing import CapturingLogger

        from sim.core.logsetup import setup_logging

        setup_logging()
        cap = CapturingLogger()
        # 保留全局 processor 链（含 redact_sensitive），logger 工厂换 CapturingLogger
        processors = list(structlog.get_config()["processors"])
        structlog.configure(
            processors=processors,
            logger_factory=lambda *args: cap,
            cache_logger_on_first_use=False,
        )
        logger = structlog.get_logger("test.redact")
        logger.info("llm.request", api_key="sk-secret-123", profile_name="p")
        rendered = str(cap.calls[-1].args[0])
        assert "sk-secret-123" not in rendered  # 明文不落日志（K4/K8）
        assert "***" in rendered and "api_key" in rendered
        assert "profile_name" in rendered and "p" in rendered  # 非敏感键不受影响
        setup_logging()  # 恢复全局配置（供后续用例）
