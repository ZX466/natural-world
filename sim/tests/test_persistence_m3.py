"""M3 预留表 + 0002 迁移 + sqlite-vec 脚手架测试（TASK-003 / D03）。

覆盖：
- M3 空表建表（npc_memories / relationships / knowledge）可插入
- entropy_log.event_seq 列存在且可写
- sqlite-vec 虚拟表创建 + 向量插查（脚手架自检）
- Alembic 0002 迁移 upgrade/downgrade（用临时文件库）
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.models import (
    EntropyLog,
    Knowledge,
    NpcMemory,
    Relationship,
)
from sim.core.persistence.vector import (
    DEFAULT_EMBEDDING_DIM,
    create_memory_vec_table,
    memory_vec_exists,
)


@pytest.fixture
async def engine():
    """内存 SQLite 库（Base.metadata.create_all，含 M3 表）。"""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        yield s


@pytest.mark.t1
class TestM3ReservedTables:
    """M3 表先建空表，M1 阶段仅验证 schema 可写。"""

    async def test_npc_memory_insert(self, session: AsyncSession) -> None:
        m = NpcMemory(
            npc_id="npc-1",
            event_seq=42,
            branch_id="main",
            content="我看见篝火在雨里熄灭。",
            importance=0.8,
            emotion_tag="melancholy",
            distortion=0.0,
            created_at_tick=100,
        )
        session.add(m)
        await session.commit()
        assert m.id is not None

    async def test_npc_memory_inferred_no_event(self, session: AsyncSession) -> None:
        """event_seq NULL = 推理/转述（schema §5）。"""
        m = NpcMemory(
            npc_id="npc-1",
            event_seq=None,
            branch_id="main",
            content="我猜他撒谎了。",
            importance=0.3,
            distortion=0.1,
            created_at_tick=101,
        )
        session.add(m)
        await session.commit()
        assert m.event_seq is None

    async def test_relationship_insert_directed(self, session: AsyncSession) -> None:
        """有向关系双向存储：A→B 与 B→A 各一行。"""
        session.add(
            Relationship(
                branch_id="main", owner_id="a", other_id="b", trust=0.5, affection=0.2
            )
        )
        session.add(
            Relationship(
                branch_id="main", owner_id="b", other_id="a", trust=-0.1, fear=0.4
            )
        )
        await session.commit()

        from sqlalchemy import select

        rows = (await session.execute(select(Relationship))).scalars().all()
        assert len(rows) == 2
        assert {(r.owner_id, r.other_id) for r in rows} == {("a", "b"), ("b", "a")}

    async def test_knowledge_insert(self, session: AsyncSession) -> None:
        session.add(
            Knowledge(
                holder_id="npc-1",
                fact="村东有口枯井",
                confidence=0.9,
                source="witnessed",
                learned_at=50,
                branch_id="main",
            )
        )
        await session.commit()

        from sqlalchemy import select

        rows = (await session.execute(select(Knowledge))).scalars().all()
        assert rows[0].source == "witnessed"

    async def test_entropy_log_event_seq_column(self, session: AsyncSession) -> None:
        """entropy_log.event_seq（codex 终审记账项）可写。"""
        session.add(
            EntropyLog(
                stream="world",
                reason="turn 5 injection",
                tick=5,
                value="deadbeef",
                branch_id="main",
                event_seq=42,
            )
        )
        await session.commit()

        from sqlalchemy import select

        row = (await session.execute(select(EntropyLog))).scalars().one()
        assert row.event_seq == 42


@pytest.mark.t1
class TestSqliteVecScaffold:
    """sqlite-vec 虚拟表脚手架（M1 只验证能力，M3 锁维度）。"""

    def test_create_vec_table_and_search(self, tmp_path: Path) -> None:
        db = tmp_path / "vec.db"
        conn = sqlite3.connect(str(db))
        try:
            create_memory_vec_table(conn, dim=8)
            assert memory_vec_exists(conn)

            # 插入两个 8 维向量并做近邻查询
            import struct

            def blob(vals: list[float]) -> bytes:
                return struct.pack(f"{len(vals)}f", *vals)

            conn.execute(
                "INSERT INTO npc_memory_vec(rowid, embedding) VALUES (1, ?)",
                (blob([1.0, 0, 0, 0, 0, 0, 0, 0]),),
            )
            conn.execute(
                "INSERT INTO npc_memory_vec(rowid, embedding) VALUES (2, ?)",
                (blob([0, 1.0, 0, 0, 0, 0, 0, 0]),),
            )
            conn.commit()

            rows = conn.execute(
                "SELECT rowid, distance FROM npc_memory_vec "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT 1",
                (blob([0.9, 0.1, 0, 0, 0, 0, 0, 0]),),
            ).fetchall()
            assert rows[0][0] == 1  # 最接近 [1,0,...]
        finally:
            conn.close()

    def test_default_dim_constant(self) -> None:
        assert DEFAULT_EMBEDDING_DIM in (384, 768)


@pytest.mark.t1
class TestAlembic0002:
    """0002 迁移：upgrade 建全表，downgrade 回滚。"""

    def _run(self, tmp_path: Path, *args: str) -> None:
        import subprocess
        import sys

        env = {
            "WORLD_DB_URL": f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}",
        }
        import os

        full_env = {**os.environ, **env}
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=str(Path(__file__).resolve().parents[2]),
            env=full_env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    def test_upgrade_head_creates_all_tables(self, tmp_path: Path) -> None:
        self._run(tmp_path, "upgrade", "head")
        db = tmp_path / "mig.db"
        conn = sqlite3.connect(str(db))
        try:
            tbl_sql = "SELECT name FROM sqlite_master WHERE type='table'"
            tables = {r[0] for r in conn.execute(tbl_sql)}
        finally:
            conn.close()
        assert {
            "events",
            "branches",
            "snapshots",
            "player_anchors",
            "entropy_log",
            "llm_profiles",
            "npc_memories",
            "relationships",
            "knowledge",
        } <= tables
        # entropy_log.event_seq 列
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(entropy_log)")}
        finally:
            conn.close()
        assert "event_seq" in cols

    def test_downgrade_removes_m3_tables(self, tmp_path: Path) -> None:
        self._run(tmp_path, "upgrade", "head")
        self._run(tmp_path, "downgrade", "0001_m0_initial")
        db = tmp_path / "mig.db"
        conn = sqlite3.connect(str(db))
        try:
            tbl_sql = "SELECT name FROM sqlite_master WHERE type='table'"
            tables = {r[0] for r in conn.execute(tbl_sql)}
        finally:
            conn.close()
        assert "npc_memories" not in tables
        assert "relationships" not in tables
        assert "knowledge" not in tables
        assert "events" in tables  # M0 表仍在
