"""M4-B2 意愿冲突度管线（DESIGN §10；m4-plan 批次 B 行为链 Claude 域）。

**意愿冲突度** = w₁性格违背 + w₂风险 + w₃需求冲突 + w₄处境不合（§10 公式）。
四档表现（0.0-0.3 自然接受 / 0.3-0.6 轻微迟疑 / 0.6-0.8 明显抱怨拖延 / 0.8-1.0
强烈抵触先做别的）；**但最终都执行**——意愿系统只产「表现强度」不改决策结果。

纪律（§10/§19）：
- 抱怨必须是**自我怀疑**（「我干嘛要干这个」），绝不能是被操纵感
  （「谁在指使我」）——后者即出戏，模板词面逐条钉死；
- 冲突度数值/w1-w4 权重是元信息，**永不进任何戏内文本**（X 系构造隔离同款）；
- 纯函数管线：同输入同输出（C5）；不改 UtilityDecision 的动作选择——
  「最终都执行」由类型层保证（管线只产 WillingnessVerdict，不回写 scores）。
"""
from __future__ import annotations

import pytest

from sim.agent.will import (
    WILLINGNESS_BANDS,
    WillingnessVerdict,
    willingness_conflict,
    willingness_expression,
)


@pytest.mark.t1
class TestWillingnessConflict:
    """w₁-w₄ 合成与四档切分。"""

    def test_zero_conflict_all_neutral(self) -> None:
        # 全中性输入 → 冲突度 0 → 自然接受档
        v = willingness_conflict(0.0, 0.0, 0.0, 0.0)
        assert v.score == pytest.approx(0.0)
        assert v.band == 0

    def test_weights_compose_linearly(self) -> None:
        # 每维满值 → 合成 = w1+w2+w3+w4（权重和=1.0，§10 公式线性合成）
        v = willingness_conflict(1.0, 1.0, 1.0, 1.0)
        assert v.score == pytest.approx(1.0)
        assert v.band == 3

    def test_bands_cut_at_documented_thresholds(self) -> None:
        # 四档边界按 §10 表：0.3/0.6/0.8（输入×4 使单维 1.0×w=0.25 时总分恰好落界：
        # 权重 0.25/维，单维满值=0.25；要构造总分 s 用 四维=s/0.25 均摊）
        assert WILLINGNESS_BANDS == (0.3, 0.6, 0.8)
        def at(total: float) -> WillingnessVerdict:
            x = total  # 四维均摊 x*0.25*4 = x
            return willingness_conflict(x, x, x, x)
        assert at(0.29).band == 0
        assert at(0.30).band == 1
        assert at(0.59).band == 1
        assert at(0.60).band == 2
        assert at(0.80).band == 3
        _ = WillingnessVerdict  # re-export 消费确认（frozen 语义在下方单独钉）

    def test_inputs_clamped_to_unit_range(self) -> None:
        # 越界输入夹到 [0,1]（防御性：上游信号病态时不爆表）
        v = willingness_conflict(5.0, -2.0, 0.5, 0.0)
        assert 0.0 <= v.score <= 1.0

    def test_verdict_is_frozen(self) -> None:
        import dataclasses

        v = willingness_conflict(0.9, 0.0, 0.0, 0.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            v.score = 0.1  # type: ignore[misc]


@pytest.mark.t1
class TestWillingnessExpression:
    """四档表现 + 抱怨词面纪律（自我怀疑，绝不被操纵感）。"""

    def test_band0_natural_acceptance_no_text(self) -> None:
        v = willingness_conflict(0.1, 0.1, 0.1, 0.1)  # 均摊 → 总分 0.1 → band 0
        expr = willingness_expression(v, npc_name="陈默")
        assert expr is None  # 0.0-0.3 自然接受，无表现

    def test_band1_mild_hesitation_self_doubt(self) -> None:
        v = willingness_conflict(0.4, 0.4, 0.4, 0.4)  # 均摊 → 总分 0.4 → band 1
        expr = willingness_expression(v, npc_name="陈默")
        assert expr is not None and expr.band == 1
        assert expr.monologue  # 独白里有微词

    def test_band3_strong_resistance_defers_action(self) -> None:
        # 多维叠加到 band 3（权重和=1.0，各维都高 → 总分高）
        v = willingness_conflict(0.95, 0.9, 0.9, 0.9)
        assert v.band == 3
        expr = willingness_expression(v, npc_name="陈默")
        assert expr is not None and expr.band == 3
        assert expr.defers  # 先做别的事再绕回来

    def test_single_dimension_scales_linearly(self) -> None:
        # 单维输入按权重线性缩放（w=0.25）：性格违背 0.95 → 总分 0.2375（band 0）
        # ——意愿系统不夸大单维信号；强表现需要多维叠加（§10 加权和语义）
        v = willingness_conflict(0.95, 0.0, 0.0, 0.0)
        assert v.score == pytest.approx(0.95 * 0.25)
        assert v.band == 0

    def test_all_templates_are_self_doubt_never_manipulated(self) -> None:
        # §10/§19 铁律：全部档位词面=自我怀疑；禁词面=被操纵感/外部命令源
        # 扫描各档实际可达组合（单维到不了高档 → 用多维叠加扫满四档）
        FORBIDDEN = ("谁在指使", "谁指使", "被指使", "有人让我", "命令我", "被控制", "被操纵")
        combos = [
            (0.35, 0.35, 0.35, 0.35),
            (0.5, 0.5, 0.5, 0.5),
            (0.65, 0.65, 0.65, 0.65),
            (0.75, 0.7, 0.8, 0.75),
            (0.9, 0.9, 0.9, 0.9),
        ]
        for c in combos:
            v = willingness_conflict(*c)
            expr = willingness_expression(v, npc_name="陈默")
            if expr is None:
                continue
            for word in FORBIDDEN:
                assert word not in expr.monologue, f"档 {v.band} 词面越界: {word!r}"

    def test_scores_never_leak_into_text(self) -> None:
        # X 系同款：冲突度数值/权重名永不进独白文本
        v = willingness_conflict(0.7, 0.7, 0.7, 0.7)  # 均摊 → 总分 0.7 → band 2
        expr = willingness_expression(v, npc_name="陈默")
        assert expr is not None and expr.monologue  # band≥2 必有词
        assert f"{v.score}" not in expr.monologue
        for token in ("w1", "w2", "w3", "w4", "conflict", "band"):
            assert token not in expr.monologue

    def test_expression_is_deterministic(self) -> None:
        # C5：同输入同输出（模板选取确定性，不依赖随机）
        v = willingness_conflict(0.7, 0.7, 0.7, 0.7)
        a = willingness_expression(v, npc_name="陈默")
        b = willingness_expression(v, npc_name="陈默")
        assert a == b
