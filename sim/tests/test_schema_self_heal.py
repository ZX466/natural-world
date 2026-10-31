"""legacy 存档升级自愈：`create_all` 建出的库没有 alembic_version，须能补齐新列。

2026-10-31 实测缺陷：主树 `world.db`（187857 事件 / tick 36000）由
`init_database` 的 `Base.metadata.create_all` 建出——`create_all` 只建缺失的表，
**不给已存在的表加列**。`0015_health_code` 引入的 `npc_health.code` 因此永远补不上，
应用启动直接 `OperationalError: no such column: npc_health.code`。

本文件钉住自愈契约：`ensure_schema(engine)` 必须让 legacy 库升到 head，
且不丢任何事件行。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

#: 旧库形状：npc_health 无 code 列（0004 + 0008~0014 之后的真实结构）。
_LEGACY_HEALTH_DDL = """
CREATE TABLE npc_health (
    id INTEGER NOT NULL,
    npc_id VARCHAR NOT NULL,
    branch_id VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    label VARCHAR NOT NULL,
    severity FLOAT NOT NULL,
    active BOOLEAN NOT NULL,
    hidden BOOLEAN NOT NULL,
    descriptors TEXT NOT NULL,
    trigger_conditions TEXT NOT NULL,
    notes TEXT,
    created_at_tick INTEGER NOT NULL,
    created_at FLOAT NOT NULL,
    PRIMARY KEY (id)
)
"""


def _make_legacy_db(path: Path, *, health_rows: int = 0) -> None:
    """造一个「create_all 建出、无 alembic_version」的旧库。"""
    from sim.core.persistence.database import init_database  # noqa: F401  (文档锚点)

    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE IF EXISTS npc_health")
        connection.execute(_LEGACY_HEALTH_DDL)
        connection.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, tick INTEGER)")
        for i in range(health_rows):
            connection.execute(
                "INSERT INTO npc_health VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    i + 1,
                    "chenmo",
                    "main",
                    "trauma",
                    "入夜心悸",
                    0.3,
                    1,
                    1,
                    '["入夜心悸"]',
                    '["夜深了"]',
                    None,
                    i,
                    0.0,
                ),
            )


def _columns(path: Path, table: str) -> list[str]:
    with sqlite3.connect(path) as connection:
        return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


@pytest.mark.t1
def test_ensure_schema_adds_code_column_to_legacy_database(tmp_path):
    """核心缺陷：legacy 库必须被补上 `npc_health.code`。"""
    from sim.core.persistence.database import ensure_schema

    database = tmp_path / "legacy.db"
    _make_legacy_db(database)
    assert "code" not in _columns(database, "npc_health"), "前置条件：旧库本无 code 列"

    async def run() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
        try:
            await ensure_schema(engine)
        finally:
            await engine.dispose()

    import asyncio

    asyncio.run(run())

    assert "code" in _columns(database, "npc_health"), "ensure_schema 未补齐 code 列"


@pytest.mark.t1
def test_ensure_schema_preserves_legacy_health_rows(tmp_path):
    """历史健康行必须原样保留，并回填 code（不回填即 NOT NULL 失败）。"""
    from sim.core.persistence.database import ensure_schema

    database = tmp_path / "legacy.db"
    _make_legacy_db(database, health_rows=2)

    async def run() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
        try:
            await ensure_schema(engine)
        finally:
            await engine.dispose()

    import asyncio

    asyncio.run(run())

    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT id, npc_id, label, code FROM npc_health").fetchall()
    assert len(rows) == 2, "历史健康行丢失"
    # 回填口径：旧自增 id 的十进制文本（0015 的既定迁移语义）
    assert [r[3] for r in rows] == ["1", "2"]


@pytest.mark.t1
def test_ensure_schema_keeps_events_untouched(tmp_path):
    """C6：事件行一行不动。"""
    from sim.core.persistence.database import ensure_schema

    database = tmp_path / "legacy.db"
    _make_legacy_db(database)
    with sqlite3.connect(database) as connection:
        for i in range(5):
            connection.execute("INSERT INTO events VALUES (?, ?)", (i, i))

    async def run() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
        try:
            await ensure_schema(engine)
        finally:
            await engine.dispose()

    import asyncio

    asyncio.run(run())

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 5


@pytest.mark.t1
def test_ensure_schema_is_idempotent(tmp_path):
    """第二次调用必须是 no-op（已到 head 就什么都不做）。"""
    from sim.core.persistence.database import ensure_schema

    database = tmp_path / "legacy.db"
    _make_legacy_db(database)

    async def run() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
        try:
            await ensure_schema(engine)
            await ensure_schema(engine)
        finally:
            await engine.dispose()

    import asyncio

    asyncio.run(run())

    assert "code" in _columns(database, "npc_health")
    with sqlite3.connect(database) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert version == ("0015_health_code",), "第二次调用改动了版本"


@pytest.mark.t1
def test_ensure_schema_stamps_fresh_create_all_database(tmp_path):
    """全新 create_all 库（无 alembic_version）也要能自愈到 head。"""
    from sim.core.persistence.database import ensure_schema

    database = tmp_path / "fresh.db"

    async def run() -> None:
        from sim.core.persistence.database import init_database

        engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
        try:
            await init_database(engine)  # 新库：create_all 直接建出含 code 的表
            await ensure_schema(engine)
        finally:
            await engine.dispose()

    import asyncio

    asyncio.run(run())

    with sqlite3.connect(database) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert version == ("0015_health_code",)
