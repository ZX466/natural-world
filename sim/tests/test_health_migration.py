"""0015 用隔离文件库验证历史行回填、唯一键和往返回滚。"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


def test_legacy_health_migration_round_trip(tmp_path):
    database = tmp_path / "legacy.db"

    def migrate(action, revision):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", action, revision],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "WORLD_DB_URL": f"sqlite+aiosqlite:///{database}"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert result.returncode == 0, result.stderr

    migrate("upgrade", "0014_fires")
    with sqlite3.connect(database) as connection:
        connection.execute("""INSERT INTO npc_health (id,npc_id,branch_id,category,label,severity,
            active,hidden,descriptors,trigger_conditions,created_at_tick,created_at)
            VALUES (42,'chenmo','main','trauma','入夜心悸',0.3,1,1,
            '["入夜心悸"]','["夜深了"]',7,'2026-10-31 00:00:00')""")
        original = connection.execute("SELECT * FROM npc_health").fetchall()
    migrate("upgrade", "head")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT code FROM npc_health").fetchone() == ("42",)
        assert (
            next(
                row
                for row in connection.execute("PRAGMA table_info(npc_health)")
                if row[1] == "code"
            )[3]
            == 1
        )
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            connection.execute(
                "INSERT INTO npc_health SELECT NULL,npc_id,branch_id,category,label,"
                "severity,active,hidden,descriptors,trigger_conditions,notes,"
                "created_at_tick,created_at,code FROM npc_health"
            )
    migrate("downgrade", "0014_fires")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM npc_health").fetchall() == original
        assert "code" not in {row[1] for row in connection.execute("PRAGMA table_info(npc_health)")}
    migrate("upgrade", "head")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT code FROM npc_health").fetchone() == ("42",)
