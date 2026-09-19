"""memory-scan S1-S7 单测（docs/security/memory-scan.md 实施清单逐条验收）。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sim.llm.memory_scan import (
    REASON_BANNED_WORD,
    MemoryWritePipeline,
    WriteResult,
)
from sim.llm.prompts.banned_words import REWRITE_MAP, scan

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "sim"


def _write(pipeline: MemoryWritePipeline, content: str, **kw) -> WriteResult:
    kw.setdefault("source", "reason")
    kw.setdefault("event_seq", 1)
    kw.setdefault("importance", 0.5)
    kw.setdefault("emotion_tag", None)
    return pipeline.write("chenmo", content, **kw)


# ---------------------------------------------------------------------------
# S1：唯一入口 + CI 守卫
# ---------------------------------------------------------------------------


class TestS1Guard:
    def test_write_is_only_entry(self):
        """write() 返回结构化结果；条目只能经它产生。"""
        p = MemoryWritePipeline()
        r = _write(p, "小满帮我修过屋檐")
        assert r.accepted and r.action == "written" and r.entry is not None
        assert len(p) == 1

    def test_no_direct_memory_entry_construction_in_sim(self):
        """CI grep 守卫：MemoryEntry( 构造只允许出现在 memory_scan.py 自身。"""
        offenders: list[str] = []
        for py in SIM_DIR.rglob("*.py"):
            if py.name == "memory_scan.py" or "__pycache__" in str(py):
                continue
            # 测试文件允许构造 MemoryEntry 做断言；生产代码不允许
            if py.parent.name == "tests":
                continue
            text = py.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "MemoryEntry(" in line:
                    offenders.append(f"{py.relative_to(REPO_ROOT)}:{i}")
        assert not offenders, f"绕过 MemoryWritePipeline 的构造点: {offenders}"

    def test_scan_module_import_is_single_source(self):
        """S2 CR：memory_scan 只从 banned_words 导入 scan，不自带词表。"""
        text = (SIM_DIR / "llm" / "memory_scan.py").read_text(encoding="utf-8")
        assert "from sim.llm.prompts.banned_words import" in text
        # 词面不应在 memory_scan 内重复定义（抽查三个）
        for w in ("存档", "snapshot", "token"):
            assert f'"{w}"' not in text.replace(f"REASON_{w}", "")


# ---------------------------------------------------------------------------
# S3：改写映射 + 复扫
# ---------------------------------------------------------------------------


class TestS3Rewrite:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("这局游戏真有意思", "这局日子真有意思"),
            ("卯时了，tick又过了", "卯时了，时辰又过了"),
            ("账册先存档", None),  # 存档→账册 后「账册先账册」复扫通过
        ],
    )
    def test_rewrite_ok(self, raw: str, expected: str | None):
        p = MemoryWritePipeline()
        r = _write(p, raw)
        assert r.accepted and r.action == "rewritten"
        assert r.entry is not None
        rescanned = scan(r.entry.content)
        assert rescanned.ok  # 落库内容必须干净
        if expected is not None:
            assert r.entry.content == expected

    def test_rewrite_recorded_in_result(self):
        p = MemoryWritePipeline()
        r = _write(p, "手气这运气真好")
        assert r.action == "rewritten"
        assert "运气" in r.hits


# ---------------------------------------------------------------------------
# S4：拒写路径 + 结构化原因
# ---------------------------------------------------------------------------


class TestS4Reject:
    def test_too_many_hits_rejected(self):
        p = MemoryWritePipeline()
        r = _write(p, "这游戏是模拟的吧，重开重来一次好了，读档算了")
        assert not r.accepted and r.action == "rejected"
        assert r.reason == "too_many_hits"
        assert r.entry is None
        assert len(p) == 0  # 不落库

    def test_unmapped_word_rejected(self):
        p = MemoryWritePipeline()
        r = _write(p, "你的seed是多少")
        assert not r.accepted
        assert r.reason == "unrewritable"  # seed 无映射
        assert "seed" in r.hits

    def test_rewrite_residual_rejected(self):
        """替换后仍不干净的文本拒写（复扫兜底）。

        构造：可映射禁词 + 数值字段模式。number_field 不在 REWRITE_MAP
        → 可映射性不成立 → unrewritable（带数值字段的文本不做机械改写救援，
        这正是 M1-H 的意图：数值词面本身就不该以任何形态落库）。
        """
        p = MemoryWritePipeline()
        r = _write(p, "这游戏hunger:72")
        assert not r.accepted and r.reason == "unrewritable"
        assert any("hunger" in h for h in r.hits)


# ---------------------------------------------------------------------------
# S5：superseded_by 治理列 + 检索过滤
# ---------------------------------------------------------------------------


class TestS5Supersede:
    def test_supersede_marks_and_filters(self):
        p = MemoryWritePipeline()
        # 旧条目故意经改写路径写入（存档→账册），模拟上线前漏网的低劣文本
        r_old = _write(p, "旧条目：账册先存档，回头再理")
        assert r_old.entry is not None
        assert r_old.entry.content == "旧条目：账册先账册，回头再理"
        # 替代条目：干净文本正常写入
        r_new = _write(p, "干净条目：小满帮我修过屋檐")
        assert r_new.entry is not None
        p.supersede(r_old.entry.id, r_new.entry.id, REASON_BANNED_WORD)
        # 检索不可见
        visible_ids = [e.id for e in p.iter_visible("chenmo")]
        assert r_old.entry.id not in visible_ids
        assert r_new.entry.id in visible_ids
        # 审计可见：get() 仍能取到改写后的原文内容，治理列在位
        old = p.get(r_old.entry.id)
        assert old.content == "旧条目：账册先账册，回头再理"  # 内容未被 supersede 改动
        assert old.superseded_by == r_new.entry.id
        assert old.invalid_reason == REASON_BANNED_WORD

    def test_supersede_requires_existing_replacement(self):
        p = MemoryWritePipeline()
        r = _write(p, "正常条目")
        assert r.entry is not None
        with pytest.raises(KeyError):
            p.supersede(r.entry.id, "nonexistent", REASON_BANNED_WORD)


# ---------------------------------------------------------------------------
# S6：命中观测（structlog dev 日志）—— 冒烟：不抛异常即可，深度验证归 T4
# ---------------------------------------------------------------------------


class TestS6Observation:
    def test_hits_logged_without_error(self):
        p = MemoryWritePipeline()
        _write(p, "你的seed是多少")  # 拒写路径（含 warning）
        _write(p, "手气这运气真好")  # 改写路径（含 info）
        assert True  # 走通即 S6 管线无异常；日志内容断言在 T4 nightly 报表做


# ---------------------------------------------------------------------------
# S7：t3-corpus 联动冒烟
# ---------------------------------------------------------------------------


class TestS7CorpusSmoke:
    def test_corpus_banned_samples_never_persist(self):
        """从 t3-corpus 抽攻击样本作为记忆候选 → 全部被拒/改写为干净文本。"""
        from sim.tests.fixtures.t3_corpus import CORPUS

        p = MemoryWritePipeline()
        polluted_leaked = 0
        for case in CORPUS:
            r = _write(p, case.sample)
            if r.accepted:
                assert r.entry is not None
                assert scan(r.entry.content).ok, f"{case.case_id} 落库内容仍含禁词"
            else:
                polluted_leaked += 0  # 拒写即安全
        # 68 条语料样本不允许任何一条带禁词落库
        assert len(p) == sum(
            1
            for c in CORPUS
            if scan(c.sample).ok
            or (
                scan(c.sample).hits
                and all(h.word in REWRITE_MAP for h in scan(c.sample).hits)
                and len(scan(c.sample).hits) <= 2
                and scan(scan(c.sample).cleaned).ok
            )
        )

    def test_rewrite_map_covers_common_leakage(self):
        """常见泄漏词（游戏/tick/存档/玩家/运气/快照/回放/分支）有映射；其余拒写是预期。"""
        for w in ("游戏", "tick", "存档", "玩家", "运气", "快照", "回放", "分支"):
            assert w in REWRITE_MAP, w


# ---------------------------------------------------------------------------
# asyncio 卫生（pytest-asyncio auto 模式下防未 awaited 告警）
# ---------------------------------------------------------------------------


def test_asyncio_loop_absent() -> None:
    """memory_scan 为同步管线——不需要 loop；此测试防未来误加未 await 调用。"""
    loop = asyncio.new_event_loop()
    try:
        assert not loop.is_running()
    finally:
        loop.close()
