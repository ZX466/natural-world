"""T1 钉子 — M4 词表补落（裁 16-4 / 裁 19 F-1，2026-09-27 codex S4b）。

**背景**：`docs/security/m4-closure-preaudit.md` §3 F-1 实测发现——裁 16-4 已裁
「`BANNED_WORDS_META` 新增 `概率`/`注定`」但一直没落（`概率 in BANNED_WORDS=False`），
P4 运气探针「这概率多少」在 T4 输出侧与 assembler 出站终扫都无词面防线。
裁 19 放行本域（codex，词面 CR owner）补落，本文件是补落后的词面守卫。

**裁决口径（裁 16-4，CR 未变）**：
- 加：`概率`、`注定`（因果未知面 S1 §5 C-1 + 运气面 S1 §4 L-2）；
- **不加** `命中`/`骰`：战斗语境「命中」是自然词，误报面大，走白名单兜。

**为什么「八成能成」不在词表**：§14 未知四轴要的是「不给概率」而非禁一切程度副词；
「八成/十有八九」是自然口语的程度表达，落词表会误伤大量合规叙事
（`test_percentage_idiom_not_banned` 钉住这一边界，防后续扩面走偏）。
"""

from __future__ import annotations

import pytest

from sim.llm.prompts.banned_words import BANNED_WORDS, BANNED_WORDS_META, scan


@pytest.mark.t1
class TestM4ProbabilityWordsBanned:
    """裁 16-4 补落守卫：概率/注定进词表且 scan() 命中。"""

    @pytest.mark.parametrize("word", ["概率", "注定"])
    def test_word_in_meta_table(self, word: str) -> None:
        assert word in BANNED_WORDS_META
        assert word in BANNED_WORDS  # 合并集合也含（消费方只引 BANNED_WORDS）

    @pytest.mark.parametrize(
        "text",
        [
            "这概率多少",  # P4 运气探针原句
            "成功概率是多少",
            "你是不是命中注定",
            "这事注定要发生",
        ],
    )
    def test_scan_hits(self, text: str) -> None:
        result = scan(text)
        assert not result.ok, text
        assert any(h.word in {"概率", "注定"} for h in result.hits), text

    def test_hit_kind_is_meta(self) -> None:
        result = scan("这概率多少")
        assert result.hits[0].kind == "meta"


@pytest.mark.t1
class TestM4ProbabilityWordsNoFalsePositive:
    """不加词口径的守卫：命中/骰/程度副词不误伤（裁 16-4 + §14 未知四轴）。"""

    @pytest.mark.parametrize(
        "text",
        [
            "一箭命中靶心",  # 战斗语境「命中」= 自然词（裁 16-4 明确不加）
            "掷骰子决定去哪",  # 「骰」不加
            "骰子滚出六点",  # 「骰」不加
        ],
    )
    def test_not_banned_natural_combat_words(self, text: str) -> None:
        assert scan(text).ok, text

    @pytest.mark.parametrize("text", ["八成能成", "十有八九会下雨", "多半赶得上"])
    def test_percentage_idiom_not_banned(self, text: str) -> None:
        """程度副词不落词表——§14 禁的是「概率/数值」，不是一切程度表达。

        钉住这条边界防后续扩面走偏（「八成」进词表会误伤大量合规叙事）。
        """
        assert scan(text).ok, text

    def test_existing_whitelist_unaffected(self) -> None:
        """既有白名单项照旧豁免（棋子运气/手气好/模特儿）。"""
        assert scan("今天棋子运气不错").ok
        assert scan("今天手气好").ok
        assert scan("她是个好模特儿").ok

    def test_new_word_does_not_break_whitelist_spans(self) -> None:
        """加词后既有例外区间语义不变：区间外禁词仍命中。"""
        result = scan("棋子运气之外，游戏还是要玩的")
        assert not result.ok
        assert any(h.word == "游戏" for h in result.hits)


@pytest.mark.t1
class TestM4ProbabilityWordsPipelineWiring:
    """补落的消费面：assembler 出站终扫 / memory_scan 判梯同词表生效。"""

    def test_write_pipeline_rejects_probability_text(self) -> None:
        from sim.llm.memory_scan import MemoryWritePipeline

        result = MemoryWritePipeline().decide("这事概率不大")
        assert result.admitted is False

    def test_impulse_gate_rejects_probability_text(self) -> None:
        """I-1 banned 扫复用同一词表 → 玩家 impulse 也被拦。"""
        from sim.agent.impulse_gate import impulse_gate

        verdict = impulse_gate("你说这概率多大", None)
        assert verdict.admitted is False
        assert verdict.reason in {"unrewritable", "too_many_hits", "rewrite_residual"}
