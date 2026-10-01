"""M5-S6 负钉 — 戏外词表钩子判层（m5-s5-meta-lexicon-and-budget-cr.md §2 / 裁 30 §B）。

CR-1 结构落地（空表 + scan_meta_shell 分派）的唯一安规风险：**未来有人把
META_SHELL 误接成 Agent 面的豁免源**——那等于让戏外合法词反灌叙事面
（S5 CR-1 自己警告的洞，本文件钉死它）。

三条判层纪律（全部锁现状=绿；任何违反显式红）：
1. **Agent 面分派永不读 META_SHELL**：`scan()` 对含 META_SHELL 词的文本判定
   与「META_SHELL 为空时」完全一致（源码白盒 + 行为双验）；
2. **空表 = scan_meta_shell ≡ scan**（结构自证：分派正确性在空表下不劣化）；
3. **本表不做豁免源**：`scan()` 源码不出现 META_SHELL 引用（词面表与钩子
   判层物理隔离，白盒扫描）。
"""

from __future__ import annotations

import inspect

from sim.llm.prompts.banned_words import (
    BANNED_WORDS,
    BANNED_WORDS_META_SHELL,
    scan,
    scan_meta_shell,
)


class TestMetaShellLexicon:
    def test_table_is_empty_structure_only(self) -> None:
        """结构先行：空表（裁 30 §B）——8 词候选以批注留存，填值随首个戏外 CR。"""
        assert frozenset() == BANNED_WORDS_META_SHELL

    def test_scan_meta_shell_equals_scan_when_table_empty(self) -> None:
        """空表自证：分派在空表下与 scan() 逐词一致（不劣化）。"""
        for text in (
            "重开模拟器，我的游戏日记。",
            "AI助手 v2 prompt=1 tick:5",
            "初到临河 第二日清晨",
            "",
        ):
            assert scan_meta_shell(text).hits == scan(text).hits, text

    def test_agent_dispatch_never_reads_meta_shell(self) -> None:
        """判层核心：`scan()` 源码零 META_SHELL 引用——Agent 面不读戏外表。

        行为双验：含候选 8 词的文本，`scan()` 判定与「假想 META_SHELL 已填」
        无关——只要 scan 源码不引用它，填值就影响不到 Agent 面。
        """
        src = inspect.getsource(scan)
        assert "META_SHELL" not in src, (
            "scan() 源码引用了 BANNED_WORDS_META_SHELL——戏外表被接成 Agent 面"
            "豁免源（CR-1 明令禁止的洞）"
        )

    def test_meta_shell_words_still_blocked_on_agent_surface(self) -> None:
        """行为面：候选 8 词在 `scan()`（Agent 面）下全部照拦——不受空表影响。"""
        for word in ("重开", "读档", "存档", "快照", "回放", "游戏", "模拟", "玩家"):
            assert word in BANNED_WORDS, word
            assert scan(f"记事本里写着{word}。").hits, f"Agent 面 {word} 未拦"

    def test_meta_shell_covers_candidate_words_when_filled(self) -> None:
        """分派语义演示（结构正确性）：临时填值后 scan_meta_shell 放行该词。

        用猴子补丁改模块 frozenset（只影响本测试进程）——证明分派真的读表、
        且只放行表内词。生产空表语义由 test_scan_meta_shell_equals_scan_when_table_empty 锁。
        """
        import sim.llm.prompts.banned_words as bw

        original = bw.BANNED_WORDS_META_SHELL
        try:
            bw.BANNED_WORDS_META_SHELL = frozenset({"重开"})
            # 「重开」进表 → 放行；「游戏」不在表 → 仍拦
            result = scan_meta_shell("重开模拟器，游戏日记。")
            words = {h.word for h in result.hits}
            assert "重开" not in words
            assert "游戏" in words
        finally:
            bw.BANNED_WORDS_META_SHELL = original
        # 复原后恢复等价（fixture 无残留）
        assert original == bw.BANNED_WORDS_META_SHELL
        assert scan_meta_shell("重开模拟器。").hits == scan("重开模拟器。").hits

    def test_number_field_and_persist_kinds_preserved(self) -> None:
        """分派语义完整性：number_field 与 persist kind 判层与 scan() 同口径。

        （number_field 属 M1-H 数值词面——戏外面无豁免理由，分派照拦；
        实测 scan_meta_shell 现不含 number_field 遍历，本钉锁的是「persist/meta
        kind 分层一致 + number_field 不因分派被意外引入」两个边界。）
        """
        a = scan_meta_shell("存档吧。 分支。")
        kinds = {(h.word, h.kind) for h in a.hits}
        b = {(h.word, h.kind) for h in scan("存档吧。 分支。").hits}
        assert kinds == b
        assert any(k == "persist" for _, k in kinds)
        assert any(k == "meta" for _, k in kinds)
