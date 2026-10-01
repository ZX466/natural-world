"""M5-A4 T1 钉子 — 0011 `anchor_packages` 建表（设计稿 A3 §1.1）

`anchor_packages` = anchor 世界态物化包：**只建表、不回填**（老档无包且 anchor 时刻
`rng_state` 不可得 ⇒ 不可物化，A3 §2）。故本迁移是纯 `create_table`：无 batch、无数据
语句、无 `world.db` 参与。

钉子纪律照 0010：真跑迁移 / 列与约束 / 空库零行 / 逐级往返 / 幂等 / autogenerate 零漂移
（漂移在门禁里跑 `alembic revision --autogenerate` 验，本文件只管结构与往返）。
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        yield s


def _alembic(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {"WORLD_DB_URL": f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(Path(__file__).resolve().parents[2]),
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# 1. 结构（ORM + 真跑迁移）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestAnchorPackagesTable:
    async def test_table_exists_with_meta(self, engine) -> None:
        async with engine.connect() as conn:
            names = await conn.run_sync(lambda c: sa.inspect(c).get_table_names())
        assert "anchor_packages" in names

    async def test_columns_and_nullability(self, engine) -> None:
        async with engine.connect() as conn:
            cols = await conn.run_sync(lambda c: sa.inspect(c).get_columns("anchor_packages"))
        got = {c["name"]: c["nullable"] for c in cols}
        assert got == {
            "anchor_id": False,  # PK
            "branch_id": False,
            "tick": False,
            "seq": False,
            "snapshot_seq": True,  # 引用，可空（无快照 ⇒ 全前缀重放）
            "snapshot_tick": True,
            "rng_state": True,  # NULL ⇒ 该档不可物化（禁 seed 派生兜底）
            "agent_override": False,
            "corpus_blob": True,  # gzip JSON
            "state_hash": True,
            "schema_version": False,
            "created_at": False,
        }

    async def test_anchor_id_is_primary_key(self, engine) -> None:
        """1:1 于 player_anchors ⇒ 单列 PK（不设 FK：删除语义归 kilo 的 CRUD 面）。"""
        async with engine.connect() as conn:
            pk = await conn.run_sync(lambda c: sa.inspect(c).get_pk_constraint("anchor_packages"))
        assert pk["constrained_columns"] == ["anchor_id"]

    async def test_snapshot_pair_check_constraint(self, session: AsyncSession) -> None:
        """快照引用「两列同有或同无」：只给一列 ⇒ CHECK 拒（IntegrityError，execute 即抛）。"""
        with pytest.raises(IntegrityError):
            await session.execute(
                sa.text(
                    "INSERT INTO anchor_packages (anchor_id, branch_id, tick, seq, snapshot_seq,"
                    " agent_override, schema_version, created_at)"
                    " VALUES ('a1', 'main', 10, 20, 20, '{}', 1, 0.0)"
                )
            )
            await session.commit()

    async def test_both_snapshot_columns_or_neither(self, session: AsyncSession) -> None:
        await session.execute(
            sa.text(
                "INSERT INTO anchor_packages (anchor_id, branch_id, tick, seq, snapshot_seq,"
                " snapshot_tick, agent_override, schema_version, created_at)"
                " VALUES ('a1', 'main', 10, 20, 20, 10, '{}', 1, 0.0)"
            )
        )
        await session.commit()
        assert (
            await session.execute(sa.text("SELECT COUNT(*) FROM anchor_packages"))
        ).scalar_one() == 1

    async def test_round_trip_values(self, session: AsyncSession) -> None:
        """gzip blob / NULL 语义原样存还（LargeBinary + 可空引用列不被吞）。"""
        import gzip
        import json

        blob = gzip.compress(json.dumps({"rows": 3}).encode())
        await session.execute(
            sa.text(
                "INSERT INTO anchor_packages (anchor_id, branch_id, tick, seq, rng_state,"
                " agent_override, corpus_blob, schema_version, created_at)"
                " VALUES ('a1', 'main', 10, 20, NULL, :ov, :blob, 1, 0.0)"
            ),
            {"ov": '{"npc":"x"}', "blob": blob},
        )
        await session.commit()
        row = (
            await session.execute(
                sa.text(
                    "SELECT rng_state, agent_override, corpus_blob FROM anchor_packages"
                    " WHERE anchor_id = 'a1'"
                )
            )
        ).one()
        assert row.rng_state is None
        assert row.agent_override == '{"npc":"x"}'
        assert bytes(row.corpus_blob) == blob

    async def test_null_package_is_legal(self, session: AsyncSession) -> None:
        """零行是合法态（老档无包）；插入时快照引用两列皆 NULL。"""
        await session.commit()
        assert (
            await session.execute(sa.text("SELECT COUNT(*) FROM anchor_packages"))
        ).scalar_one() == 0
        await session.execute(
            sa.text(
                "INSERT INTO anchor_packages (anchor_id, branch_id, tick, seq, agent_override,"
                " schema_version, created_at) VALUES ('a1', 'main', 1, 1, '{}', 1, 0.0)"
            )
        )
        await session.commit()


# ---------------------------------------------------------------------------
# 2. 迁移（scratch DB + 全 revision id）
# ---------------------------------------------------------------------------


class TestAlembic0011:
    def test_upgrade_creates_table_on_empty_db(self, tmp_path: Path) -> None:
        """空库 upgrade head ⇒ 表在、零行。"""
        assert _alembic(tmp_path, "upgrade", "head").returncode == 0
        conn = sqlite3.connect(str(tmp_path / "mig.db"))
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(anchor_packages)")]
            count = conn.execute("SELECT COUNT(*) FROM anchor_packages").fetchone()[0]
        finally:
            conn.close()
        assert "anchor_id" in cols and "rng_state" in cols
        assert count == 0

    def test_downgrade_upgrade_round_trip(self, tmp_path: Path) -> None:
        """0010 ↔ 0011 逐级往返：表消失再回来，version 复原。

        ⚠️ 往返一律**钉具体 revision id**、不钉 `head`（A4 自修纪律）：钉 head 会随
        新迁移（如 0012）前进而假红——本用例断的是 0010/0011 这一段，不是「从 0010 到
        最新」的任意路径。
        """
        assert _alembic(tmp_path, "upgrade", "0010_protected_backfill").returncode == 0
        assert _alembic(tmp_path, "upgrade", "0011_anchor_packages").returncode == 0
        assert _alembic(tmp_path, "downgrade", "0010_protected_backfill").returncode == 0

        conn = sqlite3.connect(str(tmp_path / "mig.db"))
        try:
            gone = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='anchor_packages'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert gone == 0

        assert _alembic(tmp_path, "upgrade", "0011_anchor_packages").returncode == 0
        conn = sqlite3.connect(str(tmp_path / "mig.db"))
        try:
            back = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='anchor_packages'"
            ).fetchone()[0]
            version = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        finally:
            conn.close()
        assert back == 1
        assert version == [("0011_anchor_packages",)]

    def test_data_survives_downgrade_upgrade(self, tmp_path: Path) -> None:
        """0011 往返只丢自己的表：锚点行**必须**幸存；包行随表 drop 而空（可重建）。

        降级丢包是有意的：包是「存档时固化一次」的派生物（可重算），而 `player_anchors`
        是玩家资产不可丢。0011 是纯 `create_table`，无数据语句可保。
        """
        assert _alembic(tmp_path, "upgrade", "head").returncode == 0
        conn = sqlite3.connect(str(tmp_path / "mig.db"))
        try:
            conn.execute(
                "INSERT INTO player_anchors (id, name, branch_id, tick, seq, agent_override,"
                " protected, updated_at, created_at)"
                " VALUES ('a1', '档', 'main', 1, 1, '{}', 1, 1.0, 1.0)"
            )
            conn.execute(
                "INSERT INTO anchor_packages (anchor_id, branch_id, tick, seq, agent_override,"
                " schema_version, created_at) VALUES ('a1', 'main', 1, 1, '{}', 1, 1.0)"
            )
            conn.commit()
        finally:
            conn.close()

        assert _alembic(tmp_path, "downgrade", "0010_protected_backfill").returncode == 0
        assert _alembic(tmp_path, "upgrade", "head").returncode == 0

        conn = sqlite3.connect(str(tmp_path / "mig.db"))
        try:
            anchors = conn.execute("SELECT COUNT(*) FROM player_anchors").fetchone()[0]
            packages = conn.execute("SELECT COUNT(*) FROM anchor_packages").fetchone()[0]
        finally:
            conn.close()
        assert anchors == 1, "玩家档行被 0011 往返牵连丢了"
        assert packages == 0, "降级 drop 表后重建应为空（包是可重算派生物）"

    def test_upgrade_is_repeatable(self, tmp_path: Path) -> None:
        """幂等：连续 upgrade 到同一 revision id 不炸（已在该 version 时 alembic no-op）。"""
        assert _alembic(tmp_path, "upgrade", "0011_anchor_packages").returncode == 0
        assert _alembic(tmp_path, "upgrade", "0011_anchor_packages").returncode == 0
        conn = sqlite3.connect(str(tmp_path / "mig.db"))
        try:
            version = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        finally:
            conn.close()
        assert version == [("0011_anchor_packages",)]
