"""M3 批次 B-B1：传播 = 复制写（m3-plan 批次 B 架构细化；R5/R6 落地）。

TDD RED 先行。契约（m3-plan §3 B-B1）：
- retell = 读 A 可见 → 证据链判定（evidence.judge_third_party_hidden）→
  **在 B 侧走一次 write()**（B 的写入门 banned+hidden 扫描自动生效，R6：
  不开放跨人读，传播只经「写入门」复制）；
- told 衰减在 retell 内计算（evidence.TOLD_DECAY），**不改 MemoryWritePipeline 本体**
  （扫描面零扩——R7/S1 纪律）；
- 判定拒绝（EvidenceVerdict.admitted=False）→ 不写、返回 None（结构化拒绝，
  不抛异常——传播失败是常态路径非错误）；
- 写入来源 source="dialogue"（转述是对话行为）。
"""

from __future__ import annotations

import pytest

from sim.llm.memory_scan import InMemoryStore, MemoryWritePipeline


def _ok_entry(result) -> object:
    assert result.accepted and result.entry is not None
    return result.entry


CLEAN = "小满帮我把屋檐的瓦片一片片归回了原位"


class TestRetellCopiesThroughGate:
    def test_retell_writes_to_holder_via_pipeline(self) -> None:
        """判定通过 → B 侧 write()（banned+hidden 扫描走 B 的管线）。"""
        from sim.npc.propagation import retell

        store = InMemoryStore()
        pipeline_b = MemoryWritePipeline(store=store)

        entry = retell(
            pipeline=pipeline_b,
            to_npc="b",
            source="witnessed",
            subject_id="chenmo",
            attr_id="chenmo.health_1",
            events=[
                {
                    "tick": 10,
                    "event_type": "npc.hidden_emerge",
                    "payload": {"npc_id": "chenmo", "attr_ids": ["chenmo.health_1"]},
                    "witnesses": ["b"],
                }
            ],
            observed_tick=10,
            content="陈默在阴雨天咳得直不起腰。",
            tick=11,
        )
        assert entry is not None
        # 落在 B 名下（复制写，非共享读）
        assert entry.npc_id == "b"
        assert entry.source == "dialogue"
        # 判定置信继承（witnessed 0.9）
        assert entry.importance == pytest.approx(0.9)
        visible = [e.id for e in pipeline_b.iter_visible("b")]
        assert entry.id in visible

    def test_retell_denied_verdict_writes_nothing(self) -> None:
        """判定拒绝 → 不写、返回 None（结构化拒绝，无副作用）。"""
        from sim.npc.propagation import retell

        store = InMemoryStore()
        pipeline_b = MemoryWritePipeline(store=store)

        entry = retell(
            pipeline=pipeline_b,
            to_npc="c",  # c 不在 witnesses
            source="witnessed",
            subject_id="chenmo",
            attr_id="chenmo.health_1",
            events=[
                {
                    "tick": 10,
                    "event_type": "npc.hidden_emerge",
                    "payload": {"npc_id": "chenmo", "attr_ids": ["chenmo.health_1"]},
                    "witnesses": ["b"],
                }
            ],
            observed_tick=10,
            content="陈默在阴雨天咳得直不起腰。",
            tick=11,
        )
        assert entry is None
        assert len(list(pipeline_b.iter_visible("c"))) == 0

    def test_retell_told_decays_confidence(self) -> None:
        """told 路：置信 = teller 知识 0.9 × 0.6 = 0.54（衰减在 retell 内算）。"""
        from sim.npc.propagation import retell

        store = InMemoryStore()
        pipeline_b = MemoryWritePipeline(store=store)

        entry = retell(
            pipeline=pipeline_b,
            to_npc="b",
            source="told",
            subject_id="chenmo",
            attr_id="chenmo.health_1",
            events=[],
            teller_knowledge={
                "confidence": 0.9,
                "subject_npc_id": "chenmo",
                "subject_attr_id": "chenmo.health_1",
                "invalidated": False,
            },
            content="听人说陈默有咳疾。",
            tick=12,
        )
        assert entry is not None
        assert entry.importance == pytest.approx(0.9 * 0.6)

    def test_retell_respects_banned_scan_of_holder(self) -> None:
        """B 的写入门照扫：banned 内容经 B 管线拒写（R6 复制写=走门，非旁路）。"""
        from sim.npc.propagation import retell

        store = InMemoryStore()
        pipeline_b = MemoryWritePipeline(store=store)

        # 「AI」在禁词表且不在 REWRITE_MAP → 直拒（unrewritable）；
        # retell 即使判定通过，banned content 也过不了 B 的门（retell 不绕门）。
        entry = retell(
            pipeline=pipeline_b,
            to_npc="b",
            source="told",
            subject_id="chenmo",
            attr_id="chenmo.health_1",
            events=[],
            teller_knowledge={
                "confidence": 0.9,
                "subject_npc_id": "chenmo",
                "subject_attr_id": "chenmo.health_1",
                "invalidated": False,
            },
            content="有人说陈默其实是 AI 变的。",
            tick=13,
        )
        assert entry is None
        assert len(list(pipeline_b.iter_visible("b"))) == 0
