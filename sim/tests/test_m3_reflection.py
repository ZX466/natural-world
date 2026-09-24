"""M3 批次 B-B2：反思批处理（DESIGN §15「每游戏日 1 次」；m3-plan 批次 B 架构细化）。

TDD RED 先行。契约（m3-plan §3 B-B2）：
- reflection_due(tick)：日切纯函数（tick % TICKS_PER_GAME_DAY == 0），weather 同款
  判日切模式；**不进每 tick 路径**（防呆红线——世界循环固定序「事件结算后」调用）；
- run_reflection(...)：gather（当日 source="event" 的可见记忆）→ 摘要文本
  （M3 阶段规则化拼装，LLM 摘要挂载点预留）→ write(source="reason")
  （反思产物是普通记忆条目，治理/检索/向量全链复用，无特例——R7）；
- LLM 缺位/无素材降级：无可见记忆 → 不产摘要不写（零产物）；
- 摘要产物不绕扫描面：走 write() 唯一入口（S1/R7 纪律）。
"""

from __future__ import annotations

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.llm.memory_scan import InMemoryStore, MemoryWritePipeline


def _ok_entry(result) -> object:
    assert result.accepted and result.entry is not None
    return result.entry


class TestReflectionDue:
    def test_due_on_day_boundary(self) -> None:
        from sim.npc.reflection import reflection_due

        assert reflection_due(0) is True
        assert reflection_due(TICKS_PER_GAME_DAY) is True
        assert reflection_due(TICKS_PER_GAME_DAY * 7) is True

    def test_not_due_mid_day(self) -> None:
        from sim.npc.reflection import reflection_due

        assert reflection_due(1) is False
        assert reflection_due(TICKS_PER_GAME_DAY - 1) is False
        assert reflection_due(TICKS_PER_GAME_DAY + 1) is False


class TestRunReflection:
    def _pipeline(self) -> MemoryWritePipeline:
        return MemoryWritePipeline(store=InMemoryStore())

    def test_writes_reason_summary_from_day_events(self) -> None:
        """有当日 event 源记忆 → 摘要写入 source="reason"（R7：走 write 唯一入口）。"""
        from sim.npc.reflection import run_reflection

        pipeline = self._pipeline()
        _ok_entry(
            pipeline.write(
                npc_id="chenmo",
                content="阴雨天里修好了屋檐。",
                source="event",
                event_seq=1,
                importance=0.6,
                emotion_tag="warm",
            )
        )
        _ok_entry(
            pipeline.write(
                npc_id="chenmo",
                content="河边遇见了陌生的旅人。",
                source="event",
                event_seq=2,
                importance=0.5,
                emotion_tag=None,
            )
        )

        entry = run_reflection(pipeline=pipeline, npc_id="chenmo", day=1)
        assert entry is not None
        assert entry.source == "reason"
        assert entry.npc_id == "chenmo"
        # 摘要覆盖当日素材（内容级断言：含两条素材的关键词，非 LLM 原文）
        assert "屋檐" in entry.content and "旅人" in entry.content

    def test_no_material_no_entry(self) -> None:
        """无当日素材 → 不产摘要不写（零产物，LLM 缺位降级同口径）。"""
        from sim.npc.reflection import run_reflection

        pipeline = self._pipeline()
        assert run_reflection(pipeline=pipeline, npc_id="chenmo", day=1) is None
        assert len(list(pipeline.iter_visible("chenmo"))) == 0

    def test_ignores_non_event_source(self) -> None:
        """只有非 event 源（reason/dialogue）的记忆不进当日素材（防自我吞尾）。"""
        from sim.npc.reflection import run_reflection

        pipeline = self._pipeline()
        _ok_entry(
            pipeline.write(
                npc_id="chenmo",
                content="昨日的反思还想起来。",
                source="reason",
                event_seq=None,
                importance=0.5,
                emotion_tag=None,
            )
        )

        assert run_reflection(pipeline=pipeline, npc_id="chenmo", day=1) is None

    def test_summary_passes_banned_scan(self) -> None:
        """摘要过写入门：素材含禁词时该素材被排除，摘要不夹带（S1/R7）。"""
        from sim.npc.reflection import run_reflection

        pipeline = self._pipeline()
        # 「AI」在禁词表且不可改写 → write 拒 → 不在素材里
        rejected = pipeline.write(
            npc_id="chenmo",
            content="有人说他是 AI。",
            source="event",
            event_seq=1,
            importance=0.5,
            emotion_tag=None,
        )
        assert not rejected.accepted
        _ok_entry(
            pipeline.write(
                npc_id="chenmo",
                content="屋檐修好了。",
                source="event",
                event_seq=2,
                importance=0.5,
                emotion_tag=None,
            )
        )

        entry = run_reflection(pipeline=pipeline, npc_id="chenmo", day=1)
        assert entry is not None
        assert "屋檐" in entry.content
        assert "AI" not in entry.content

    def test_day_filters_materials(self) -> None:
        """日过滤接口：MemoryEntry 是内存形（无 tick 列）→ InMemory 下 day 参数
        不再过滤（调用方约定窗口）；SQL store 的 tick 过滤随 store 扩展接入。
        此处锁接口不炸 + source 过滤仍生效。"""
        from sim.npc.reflection import run_reflection

        pipeline = self._pipeline()
        _ok_entry(
            pipeline.write(
                npc_id="chenmo",
                content="今天的事。",
                source="event",
                event_seq=1,
                importance=0.5,
                emotion_tag=None,
            )
        )
        entry = run_reflection(pipeline=pipeline, npc_id="chenmo", day=0)
        assert entry is not None
