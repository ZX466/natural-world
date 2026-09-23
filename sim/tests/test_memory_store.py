"""D04 记忆表读写链路测试（TASK-004 / D04）。

覆盖：
- SqlMemoryStore 读写往返：write→iter_visible→supersede（审计可见/检索过滤）
- 拒写不落库（S4）：扫描拒绝 → npc_memories 无行
- 内存实现 vs SQLite 实现行为一致性抽查
- entropy_log.event_seq 回填（flush 同事务，D04 记账项）

验收命令：
  uv run pytest sim/tests/test_memory_scan.py sim/tests/test_persistence_m3.py
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from sim.core.persistence.memory_store import SqlMemoryStore
from sim.llm.memory_scan import (
    REASON_BANNED_WORD,
    InMemoryStore,
    MemoryEntry,
    MemoryWritePipeline,
    WriteResult,
    make_entry,
)

# 直通扫描的干净文本（无禁词）
CLEAN = "小满帮我把屋檐的瓦片一片片归回了原位"


def _ok_entry(result) -> MemoryEntry:
    """write() 断言接受并返回非 None 的 MemoryEntry（收窄可选类型）。"""
    assert result.accepted and result.entry is not None
    return result.entry


def _create_schema(db_path: str) -> sqlite3.Connection:
    """用 Alembic 建全表，返回连接（同步 sqlite3）。"""
    import os
    import subprocess
    import sys

    env = {**os.environ, "WORLD_DB_URL": f"sqlite+aiosqlite:///{db_path}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return sqlite3.connect(db_path)


@pytest.fixture
def sql_store(tmp_path: Path) -> Iterator[SqlMemoryStore]:
    conn = _create_schema(str(tmp_path / "mem.db"))
    store = SqlMemoryStore(conn, branch_id="main", created_at_tick=42)
    yield store
    conn.close()


def _write(pipeline: MemoryWritePipeline, content: str, **kw) -> WriteResult:
    kw.setdefault("source", "event")
    kw.setdefault("event_seq", 1)
    kw.setdefault("importance", 0.5)
    kw.setdefault("emotion_tag", None)
    return pipeline.write("chenmo", content, **kw)


# ---------------------------------------------------------------------------
# 读写往返（验收项 1）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestSqlReadWriteRoundtrip:
    def test_write_then_iter_visible(self, sql_store: SqlMemoryStore) -> None:
        p = MemoryWritePipeline(store=sql_store)
        r = _write(p, CLEAN, importance=0.7, emotion_tag="warm")
        entry = _ok_entry(r)

        rows = list(p.iter_visible("chenmo"))
        assert len(rows) == 1
        got = rows[0]
        assert got.id == entry.id
        assert got.content == CLEAN
        assert got.source == "event"
        assert got.event_seq == 1
        assert got.importance == 0.7
        assert got.emotion_tag == "warm"

    def test_supersede_filters_but_audit_visible(self, sql_store: SqlMemoryStore) -> None:
        """S5：标记后检索不可见，审计 get 可见；内容字段不变。"""
        p = MemoryWritePipeline(store=sql_store)
        old = _ok_entry(_write(p, CLEAN))
        new = _ok_entry(_write(p, "那夜的风把檐铃吹得很轻"))

        p.supersede(old.id, new.id, REASON_BANNED_WORD)

        visible_ids = [e.id for e in p.iter_visible("chenmo")]
        assert old.id not in visible_ids
        assert new.id in visible_ids

        audit = p.get(old.id)
        assert audit.superseded_by == new.id
        assert audit.invalid_reason == REASON_BANNED_WORD
        assert audit.content == CLEAN  # 内容未被篡改（append-only）

    def test_supersede_requires_existing_replacement(self, sql_store: SqlMemoryStore) -> None:
        p = MemoryWritePipeline(store=sql_store)
        r = _ok_entry(_write(p, CLEAN))
        with pytest.raises(KeyError):
            p.supersede(r.id, "nonexistent", REASON_BANNED_WORD)

    def test_persists_across_store_instances(self, tmp_path: Path) -> None:
        """落库持久化：新建 store 实例仍可读回（非纯内存）。"""
        db = str(tmp_path / "persist.db")
        conn = _create_schema(db)
        store1 = SqlMemoryStore(conn, created_at_tick=1)
        p1 = MemoryWritePipeline(store=store1)
        rid = _ok_entry(_write(p1, CLEAN)).id
        conn.close()

        conn2 = sqlite3.connect(db)
        store2 = SqlMemoryStore(conn2, created_at_tick=1)
        p2 = MemoryWritePipeline(store=store2)
        got = p2.get(rid)
        assert got.content == CLEAN
        conn2.close()


# ---------------------------------------------------------------------------
# 拒写不落库（S4，验收项 2）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestRejectDoesNotPersist:
    def test_rejected_scan_not_persisted(self, sql_store: SqlMemoryStore) -> None:
        p = MemoryWritePipeline(store=sql_store)
        # 5 个禁词远超 REWRITE_MAX_HITS → 拒写
        r = p.write(
            "chenmo",
            "这是游戏里 AI 模型 玩家 运气 存档",
            source="reason",
            event_seq=9,
            importance=0.9,
            emotion_tag=None,
        )
        assert not r.accepted and r.action == "rejected"
        assert len(p) == 0  # 库中零行
        assert list(p.iter_visible("chenmo")) == []

    def test_reject_does_not_touch_existing_rows(self, sql_store: SqlMemoryStore) -> None:
        p = MemoryWritePipeline(store=sql_store)
        good = _ok_entry(_write(p, CLEAN))
        p.write(
            "chenmo",
            "游戏 AI 模型 玩家 运气 存档",
            source="reason",
            event_seq=9,
            importance=0.9,
            emotion_tag=None,
        )
        assert len(p) == 1
        assert p.get(good.id).content == CLEAN


# ---------------------------------------------------------------------------
# 内存 vs SQLite 行为一致性（验收项 3）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestStoreConsistency:
    def test_same_semantics_both_impls(self, tmp_path: Path) -> None:
        conn = _create_schema(str(tmp_path / "consist.db"))
        sql_store = SqlMemoryStore(conn, created_at_tick=0)
        mem_store = InMemoryStore()

        results = {}
        for name, store in (("mem", mem_store), ("sql", sql_store)):
            p = MemoryWritePipeline(store=store)
            a = _ok_entry(_write(p, CLEAN))
            b = _ok_entry(_write(p, "风停了，篝火只剩灰"))
            p.supersede(a.id, b.id, REASON_BANNED_WORD)
            results[name] = {
                "len": len(p),
                "visible": sorted(e.content for e in p.iter_visible("chenmo")),
                "audit_superseded": p.get(a.id).superseded_by == b.id,
                "audit_content": p.get(a.id).content,
            }

        assert results["mem"] == results["sql"]
        conn.close()

    def test_supersede_is_idempotent_target(self, sql_store: SqlMemoryStore) -> None:
        """两次 supersede 指向同一新条目，治理列保持最终值。"""
        p = MemoryWritePipeline(store=sql_store)
        a = _ok_entry(_write(p, CLEAN))
        b = _ok_entry(_write(p, "另一个干净的句子"))
        p.supersede(a.id, b.id, REASON_BANNED_WORD)
        p.supersede(a.id, b.id, REASON_BANNED_WORD)
        assert p.get(a.id).superseded_by == b.id

    def test_invalid_reason_alone_hides_entry(self, sql_store: SqlMemoryStore) -> None:
        """M3-B1 双列口径（m3-plan 批次 B 前置裁决，R3 修复）：
        裸置 invalid_reason（superseded_by 仍 NULL）的条目**不可见**——
        双治理列任一非空即从 iter_visible 过滤；审计 get 仍可见（append-only）。
        场景：manual_review 类治理只置 invalid_reason，不成对 supersede。"""
        p = MemoryWritePipeline(store=sql_store)
        a = _ok_entry(_write(p, CLEAN))
        b = _ok_entry(_write(p, "井边的青苔记得每场雨"))
        # 直改治理列（manual_review 路径：无替代条目，禁造 supersede 链）
        sql_store._conn.execute(
            "UPDATE npc_memories SET invalid_reason = 'manual_review' WHERE entry_id = ?",
            (a.id,),
        )
        sql_store._conn.commit()

        visible_ids = [e.id for e in p.iter_visible("chenmo")]
        assert a.id not in visible_ids  # 裸置 invalid_reason = 检索不可见
        assert b.id in visible_ids
        audit = p.get(a.id)  # 审计面不变（S5 append-only）
        assert audit.invalid_reason == "manual_review"
        assert audit.superseded_by is None


# ---------------------------------------------------------------------------
# make_entry 工厂（S1 守卫：构造点收敛）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestMakeEntryFactory:
    def test_make_entry_defaults(self) -> None:
        e = make_entry(
            entry_id="x",
            npc_id="n",
            content="c",
            source="reason",
            event_seq=None,
            importance=0.5,
            emotion_tag=None,
        )
        assert e.superseded_by is None and e.invalid_reason is None


# ---------------------------------------------------------------------------
# entropy_log.event_seq 回填（D04 记账项，验收项 4）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestEntropyEventSeqBackfill:
    async def test_flush_backfills_event_seq(self) -> None:
        """entropy_inject 事件的熵行回填 event_seq = 该事件分配到的 seq。"""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from sim.core.events import EventKind, WorldEvent
        from sim.core.flush import flush_events
        from sim.core.persistence.database import init_database
        from sim.core.persistence.models import EntropyLog
        from sim.core.persistence.store import SqlEventStore

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        await init_database(engine)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        store = SqlEventStore(sf)

        events = [
            WorldEvent(
                tick=1,
                event_type=EventKind.ENTROPY_INJECT,
                actor_id="world",
                payload={"stream": "world.weather", "material": "ab" * 16},
            ),
        ]
        await flush_events(store, events, branch_id="main")

        async with sf() as session:
            rows = (await session.execute(select(EntropyLog))).scalars().all()
        assert len(rows) == 1
        # 首个事件的 seq = 1 → 回填
        assert rows[0].event_seq == 1

        # 再 flush 一批：seq 递增，event_seq 随之回填
        events2 = [
            WorldEvent(
                tick=2,
                event_type=EventKind.ENTROPY_INJECT,
                actor_id="world",
                payload={"stream": "world.weather", "material": "cd" * 16},
            ),
        ]
        await flush_events(store, events2, branch_id="main")
        async with sf() as session:
            stmt = select(EntropyLog).order_by(EntropyLog.id)
            rows = (await session.execute(stmt)).scalars().all()
        assert [r.event_seq for r in rows] == [1, 2]

        await engine.dispose()
