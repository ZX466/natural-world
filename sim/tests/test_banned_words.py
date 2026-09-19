"""禁词表单源单测（M1-A/M1-G + memory-scan.md §2）。

三类覆盖（TASK-003 任务书要求）：
1. 禁词命中（meta/persist/大小写/词边界/数值字段模式）
2. 白名单豁免（模特儿/棋子运气不误伤）
3. 范围隔离（代码与技术字段词面不受本模块管——scan 只处理传入的叙事文本，
   这里验证 scan 是纯函数、不越权改写映射表外词汇、cleaned 复扫收敛）
"""

from __future__ import annotations

import pytest

from sim.llm.prompts.banned_words import (
    BANNED_WORDS,
    BANNED_WORDS_META,
    BANNED_WORDS_PERSIST,
    REWRITE_MAP,
    scan,
)

# ---------------------------------------------------------------------------
# 1. 禁词命中
# ---------------------------------------------------------------------------


class TestBannedHit:
    @pytest.mark.parametrize(
        "text",
        [
            "你是AI吗",
            "你是ai吗",  # 大小写不敏感
            "你是Ai吗",
            "大语言模型",
            "这个世界是模拟的",
            "我们来玩个游戏",
            "现在tick多少",
            "你的seed是什么",
            "token 数量",
        ],
    )
    def test_meta_words_hit(self, text: str):
        result = scan(text)
        assert not result.ok
        assert result.hits[0].kind == "meta"
        assert result.hits[0].word.lower() in {w.lower() for w in BANNED_WORDS_META}

    @pytest.mark.parametrize(
        "text",
        ["分支", "branch 语句", "abandoned 记录", "重放", "快照", "回放", "snapshot 文件"],
    )
    def test_persist_words_hit(self, text: str):
        result = scan(text)
        assert not result.ok
        assert result.hits[0].kind == "persist"

    def test_ascii_word_boundary(self):
        """词边界：maintain 不中 AI、unlucky 不中 luck。"""
        assert scan("I will maintain this shop").ok
        assert scan("he felt unlucky today").ok
        # 但独立词命中
        assert not scan("bad luck today").ok
        assert not scan("the AI agent").ok

    def test_number_field_pattern(self):
        """M1-H：hunger:72 类数值+字段名模式拦截。"""
        for text in ("hunger:72", "energy = 30", "mood：85", "HP:10"):
            result = scan(text)
            assert not result.ok, text
            assert result.hits[0].kind == "number_field"

    def test_hit_coordinates(self):
        result = scan("前缀tick后缀")
        assert len(result.hits) == 1
        assert result.hits[0].start == 2
        assert result.hits[0].end == 6


# ---------------------------------------------------------------------------
# 2. 白名单豁免（S2 验收：模特儿/棋子运不误伤）
# ---------------------------------------------------------------------------


class TestWhitelist:
    def test_modelte_no_false_positive(self):
        assert scan("她是个好模特儿").ok

    def test_chess_luck_no_false_positive(self):
        assert scan("今天棋子运气不错").ok
        assert scan("棋子运气好").ok

    def test_whitelist_only_covers_spans(self):
        """例外只豁免例外区间——区间外的禁词仍命中。"""
        result = scan("棋子运气之外，游戏还是要玩的")
        assert not result.ok
        assert any(h.word == "游戏" for h in result.hits)


# ---------------------------------------------------------------------------
# 3. 范围隔离与纯函数性
# ---------------------------------------------------------------------------


class TestScopeAndPurity:
    def test_cleaned_rewrite_map_only(self):
        """cleaned 只按 REWRITE_MAP 机械替换；映射外词汇原样保留。"""
        result = scan("这局游戏重开吧")
        assert result.cleaned == "这局日子重开吧"  # 重开无映射 → 保留

    def test_cleaned_rescan_progress(self):
        """可映射词替换后复扫命中减少（S3 复扫收敛的前置）。"""
        result = scan("手气这运气真好")
        rescanned = scan(result.cleaned)
        assert rescanned.ok  # 运气→手气 后无残留

    def test_scan_is_pure(self):
        text = "游戏"
        first = scan(text)
        second = scan(text)
        assert first.hits == second.hits
        assert first.cleaned == second.cleaned

    def test_wordlist_complete(self):
        """M1-A + M1-G 全集在位（m1-checklist.md 对照）。"""
        for w in (
            "AI",
            "模型",
            "模拟",
            "游戏",
            "角色扮演",
            "tick",
            "entity_id",
            "玩家",
            "运气",
            "luck",
            "seed",
            "随机数",
            "重开",
            "重来一次",
            "存档",
            "读档",
            "profile",
            "prompt",
            "token",
        ):
            assert w in BANNED_WORDS_META, w
        for w in ("分支", "branch", "abandoned", "重放", "快照", "回放", "snapshot"):
            assert w in BANNED_WORDS_PERSIST, w

    def test_rewrite_map_keys_in_banned(self):
        """映射表键必须是禁词子集（同模块维护，防漂移）。"""
        assert set(REWRITE_MAP) <= BANNED_WORDS
