"""M2-A2 第三批第 5 项：language.py 叙事降质（m2-npc-cognition §5.2）。

契约（arch §5.2 + kilo M2-K1 复核意见全采信）：
- LanguageProfile(literacy, jargon, class_register)：按角色构造（0004 夹具命名）；
- 判定纯函数零 LLM：
  - 识字类观察 literacy 不足 → 「有音无义」变体；
  - 行话/阶层用语词表命中 → 按听者 class_register 降质；
- 出戏三红线：降质文案零数值零系统词（banned_words.scan() 0 命中）；
  literacy 只做阈值绝不进文本；降质只动叙事层文本（Observation/Frame 原始数据完整）；
- 挂载点：PerceptionFrame.narrated() 装配内、通道分组输出前（K1 意见④）；
  接口面不变（perception content string），判据字段不出 WS。
"""

from __future__ import annotations

import pytest

from sim.agent.language import LanguageProfile, degrade_observation_text
from sim.llm.prompts.banned_words import scan
from sim.perception.frame import Channel, Observation, PerceptionFrame


def _profile(**kw) -> LanguageProfile:
    base = {"literacy": 0.9, "jargon": (), "class_register": "平民"}
    base.update(kw)
    return LanguageProfile(**base)


class TestLanguageProfile:
    def test_from_json_roundtrip(self) -> None:
        """0004 夹具 JSON 形 → LanguageProfile（数据层命名对齐）。"""
        import json

        raw = json.dumps({"literacy": 0.5, "jargon": ["漕运"], "class_register": "平民"})
        p = LanguageProfile.from_json(raw)
        assert p.literacy == 0.5
        assert p.jargon == ("漕运",)
        assert p.class_register == "平民"

    def test_from_json_defaults(self) -> None:
        p = LanguageProfile.from_json("{}")
        assert p.literacy == 1.0  # 缺省全识字
        assert p.jargon == ()
        assert p.class_register == "平民"


class TestIlliteracy:
    def test_low_literacy_text_degrades(self) -> None:
        """识字不足读布告 → 有音无义变体（零数值）。"""
        out = degrade_observation_text(
            "布告上写着：悬赏缉拿盗匪张三。", "written", _profile(literacy=0.2)
        )
        assert "悬赏" not in out
        assert "看不懂" in out

    def test_high_literacy_keeps_text(self) -> None:
        out = degrade_observation_text(
            "布告上写着：悬赏缉拿盗匪张三。", "written", _profile(literacy=0.9)
        )
        assert out == "布告上写着：悬赏缉拿盗匪张三。"

    def test_literacy_value_never_in_text(self) -> None:
        """literacy 数值绝不进文本（红线 2）。"""
        out = degrade_observation_text("布告内容若干。", "written", _profile(literacy=0.2))
        assert "0.2" not in out and "0" not in out


class TestJargonRegister:
    def test_jargon_hit_low_register_degrades(self) -> None:
        """行话命中 + 平民听者 → 「没听明白」降质。"""
        out = degrade_observation_text(
            "他说这批货要走漕运。", "speech", _profile(literacy=0.9, jargon=("漕运",))
        )
        assert "漕运" not in out
        assert "没听明白" in out or "没明白" in out

    def test_jargon_high_register_keeps(self) -> None:
        """行话命中 + 士绅听者（阶层听得懂）→ 不降质。"""
        out = degrade_observation_text(
            "他说这批货要走漕运。", "speech",
            _profile(literacy=0.9, jargon=("漕运",), class_register="士绅"),
        )
        assert out == "他说这批货要走漕运。"

    def test_no_jargon_hit_keeps(self) -> None:
        out = degrade_observation_text(
            "今天天气不错。", "speech", _profile(literacy=0.9, jargon=("漕运",))
        )
        assert out == "今天天气不错。"


class TestBannedWordsRedLine:
    @pytest.mark.parametrize("text", [
        "布告上写着：悬赏缉拿盗匪张三。",
        "他说这批货要走漕运。",
        "有块布告，画着些看不懂的符号。",
        "他说的几个词你没听明白。",
    ])
    def test_degraded_text_zero_banned_hits(self, text) -> None:
        """降质文案过 banned_words.scan() 0 命中（红线 1，K1 口径延续）。"""
        out = degrade_observation_text(
            text, "speech", _profile(literacy=0.2, jargon=("漕运",))
        )
        assert scan(out).hits == ()


class TestNarratedMount:
    """挂载点：narrated() 通道分组输出前；原始数据完整（红线 3）。"""

    def _frame(self) -> PerceptionFrame:
        return PerceptionFrame(
            observer="rt-x",
            tick=0,
            observations=(
                Observation(
                    channel=Channel.HEARING, subject="rt-y",
                    description="rt-y说：这批货要走漕运。", strength=0.8,
                ),
            ),
        )

    def test_narrated_with_profile_degrades(self) -> None:
        frame = self._frame()
        text = frame.narrated(
            language=_profile(literacy=0.9, jargon=("漕运",)),
            channel_kinds={"rt-y": "speech"},
        )
        assert "漕运" not in text
        assert "你听到：" in text

    def test_narrated_without_profile_unchanged(self) -> None:
        """缺省无语言档 → 叙事与 M1 完全一致（零回归）。"""
        frame = self._frame()
        assert frame.narrated() == frame.narrated()

    def test_observations_immutable_after_degrade(self) -> None:
        """降质只动叙事层：Observation.description 原文保持完整（红线 3）。"""
        frame = self._frame()
        frame.narrated(
            language=_profile(literacy=0.9, jargon=("漕运",)),
            channel_kinds={"rt-y": "speech"},
        )
        assert frame.observations[0].description == "rt-y说：这批货要走漕运。"
