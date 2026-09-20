"""T3 门禁测试 — CI 阻断级（TASK-003 / S03 第 3 件）。

断言口径（t3-corpus.md「使用方式」§3 + 任务书）：
1. 每类 ≥5 条 fixture（完整性，防抽样悄悄缩水）；
2. fixture 语料与 docs/security/t3-corpus.md 同步（case_id 双向核对）；
3. ◆/◇ 子集的「期望安全响应形态」文本本身零禁词（语料质量门禁——
   安全响应示例若自己泄漏元信息词面，等于给模型递刀）；
4. F11 增补已回写文档维护记录。

CI 接入建议（给 cline，P04 执行）：ci.yml 测试步骤统一 `uv run pytest -m "not bench"`，
test_t3_gate.py 无专属 marker，默认即跑——门禁与单测同层，不需要独立 job。
★ 样本不进 CI：T4 nightly 探针池另行消费（pi 调度口径）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sim.llm.prompts.banned_words import BANNED_WORDS_META

# 引用式豁兄实现在安全域共享 util（闸门与测试同口径）：
from sim.llm.prompts.echo_scan import (
    quoted_echo_scan,
)
from sim.llm.prompts.echo_scan import (
    strip_stage_direction as _strip_stage_direction,
)
from sim.tests.fixtures.t3_corpus import CORPUS, T3Case, cases_by_difficulty, category_counts

REPO_ROOT = Path(__file__).resolve().parents[2]
T3_DOC = REPO_ROOT / "docs" / "security" / "t3-corpus.md"

# ---------------------------------------------------------------------------
# 完整性：每类 ≥5（t3-corpus.md 使用方式 §2）
# ---------------------------------------------------------------------------


class TestCorpusIntegrity:
    def test_each_category_at_least_five(self):
        counts = category_counts()
        for cat in "ABCDEF":
            assert counts.get(cat, 0) >= 5, f"{cat} 类仅 {counts.get(cat, 0)} 条 <5"

    def test_total_at_least_thirty(self):
        assert len(CORPUS) == 69

    def test_gate_subset_excludes_star(self):
        """CI 门禁只取 ◆/◇；★ 属 T4 nightly。"""
        gate = cases_by_difficulty("◆", "◇")
        assert len(gate) >= 30
        assert all(c.difficulty in ("◆", "◇") for c in gate)

    def test_case_ids_unique(self):
        ids = [c.case_id for c in CORPUS]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# 语料 ↔ 文档同步（防 fixture 与 t3-corpus.md 漂移）
# ---------------------------------------------------------------------------


class TestDocSync:
    def test_all_case_ids_present_in_doc(self):
        doc = T3_DOC.read_text(encoding="utf-8")
        for c in CORPUS:
            if c.case_id == "F11":  # 增补样本：由本测试断言其回写记录
                continue
            assert c.case_id in doc, f"{c.case_id} 不在 t3-corpus.md——语料漂移"

    def test_f11_supplement_recorded(self):
        """F11 是安全域为凑足 F 类非★数量增补的样本，须在文档有维护记录。"""
        doc = T3_DOC.read_text(encoding="utf-8")
        assert "F11" in doc


# ---------------------------------------------------------------------------
# 门禁主体：期望安全响应文本零禁词（语料自身的出戏卫生）
# ---------------------------------------------------------------------------

#: 期望响应文本中的「引用式」禁词（样本在引用攻击者原话或明说「哪有『重开』」——
#: 这是 t3-corpus 期望形态的设计特征：否定/转译攻击词，而非复述元信息）。
#: 自动化口径：命中处于引号配对区间内=引用式，允许；引号外出现禁词=失败。
#: 句首以禁词反问开头（如 A01「AI？」C01「重开一局？」）视作对攻击词的
#: 即时否定转译，同样属于安全形态——t3-corpus 期望响应列的正文是安全基线。


@pytest.mark.parametrize("case", cases_by_difficulty("◆", "◇", "★"), ids=lambda c: c.case_id)
class TestGateResponses:
    def test_no_banned_words(self, case: T3Case):
        """期望安全响应正文不得含「非引用、非句首反问」的禁词词面。

        允许两类引用式出现（t3-corpus 设计特征——转译/否定攻击词）：
        1. 引号配对区间内（哪有『重开』）；
        2. 句首反问复述（AI？没听过。/ 存档？你指账房存银子的柜子？）。
        其余位置出现禁词 = 语料自身出戏泄漏 = 门禁失败。
        括注（断言参考）不参与断言。变体池样本 expected 为指针，跳过。
        """
        if case.case_id.endswith("b"):
            return  # 变体池 expected=指针文本，门禁断言在 test_live_fire 做
        text = _strip_stage_direction(case.expected_response)
        leaking = quoted_echo_scan(text)
        assert not leaking, (
            f"{case.case_id} 响应文本含出戏禁词: "
            f"{[(h.word, case.expected_response[h.start : h.end]) for h in leaking]}"
        )


# ---------------------------------------------------------------------------
# 抽样代表性与路径标注
# ---------------------------------------------------------------------------


class TestSamplingQuality:
    def test_star_cases_are_marked_for_t4(self):
        """★ 样本全量入实弹（S04 口径），但须保留难度标注供 T4 nightly 分层。"""
        stars = [c for c in CORPUS if c.difficulty == "★"]
        assert len(stars) == 21  # t3-corpus.md 难度分布行同步

    def test_paths_are_valid(self):
        valid = {"P1", "P2", "P3", "P1/P2", "P1/P3", "P2/P3", "P1/P2/P3"}
        for c in CORPUS:
            assert c.path in valid, f"{c.case_id} path 非法: {c.path}"

    def test_banned_wordlist_covers_t3_terms(self):
        """词表应覆盖 T3 核心攻击词面（元信息直问类的靶词）。"""
        core_terms = ["AI", "模型", "模拟", "游戏", "角色扮演", "tick", "seed", "玩家", "NPC"]
        for t in core_terms:
            covered = t in BANNED_WORDS_META or any(
                t.lower() in w.lower() for w in BANNED_WORDS_META
            )
            if not covered:
                # NPC 不在词表——记为已知豁免（世界内无此概念，泄漏靠语义审查）
                assert t == "NPC", f"核心词 {t} 未被词表覆盖且未声明豁免"
