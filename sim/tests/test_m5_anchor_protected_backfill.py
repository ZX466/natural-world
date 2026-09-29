"""M5-A2 T1 钉子 — 0010「最新档强制保护」回填（GAP-B，裁 28 号段裁定）

**要做什么**：0008 已加 `player_anchors.protected` 列（裁 9），但**既有行全是 0** ——
「最新档必须受保护」这条产品语义（kilo M5-K5 提的 GAP-B）没有落进数据。0010 做
**只回填不切列**的迁移：把末梢那一档置 `protected=1`。

**判据与 K3 `/current` 同口径**（kilo `sim/api/anchors.py::current_item`）：
`ORDER BY updated_at DESC, id DESC LIMIT 1` —— **同刻多行按 id 降序兜底**，保证
多档同刻时结果**确定**（可复现）。**全表无行时零行更新是合法态**（不是错误）。

**只回填、不切读路径**（裁 26-C④）：读路径仍是派生式
（`anchors.py::list_items` 的 `row.updated_at >= max(updated_at)`），CRUD 单才切成
读列。⚠️ 两口径在**同刻多行**时会不一致（派生式标 N 行、回填标 1 行）——已在回执里
上报给 kilo（`list_items` 需补 `id` 兜底，或 CRUD 落地后派生式退休）。

**downgrade 不撤销回填**（有意决定）：0010 的效果是「让既有事实与读路径一致」，撤销它
反而会让「列」与「仍在役的派生式」互相矛盾（派生式仍会把末梢算成 protected=True）。
故 downgrade 只做**结构性**回退（无 schema 变化 ⇒ 实为 no-op），并在
`test_round_trip_0009_0010` 里钉住「往返后回填结果不变、可重复执行」。
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.models import PlayerAnchor

BACKFILL_SQL = (
    "UPDATE player_anchors SET protected = 1 WHERE id = ("
    " SELECT id FROM player_anchors ORDER BY updated_at DESC, id DESC LIMIT 1)"
)


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


def _anchor(anchor_id: str, *, updated_at: float, name: str = "档") -> PlayerAnchor:
    return PlayerAnchor(
        id=anchor_id,
        name=name,
        branch_id="main",
        tick=0,
        seq=0,
        agent_override="{}",
        updated_at=updated_at,
        created_at=updated_at,
    )


# ---------------------------------------------------------------------------
# 1. 回填判据
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestProtectedBackfill:
    async def test_exactly_one_row_protected(self, session: AsyncSession) -> None:
        """多档不同 updated_at → 恰一行 protected=1（末梢那档）。"""
        session.add_all(
            [
                _anchor("a1", updated_at=100.0, name="第一天"),
                _anchor("a2", updated_at=300.0, name="第三天"),
                _anchor("a3", updated_at=200.0, name="第二天"),
            ]
        )
        await session.commit()

        await _run_backfill(session)

        rows = (
            (await session.execute(select(PlayerAnchor).order_by(PlayerAnchor.id))).scalars().all()
        )
        assert [(r.id, r.protected) for r in rows] == [
            ("a1", False),
            ("a2", True),
            ("a3", False),
        ]

    async def test_tie_break_by_id_desc(self, session: AsyncSession) -> None:
        """同刻多行 → 按 id 降序兜底，**只**标 id 最大的一行（与 K3 /current 同口径）。"""
        session.add_all(
            [
                _anchor("a1", updated_at=100.0),
                _anchor("b9", updated_at=100.0),
                _anchor("c5", updated_at=100.0),
            ]
        )
        await session.commit()

        await _run_backfill(session)

        rows = (
            (await session.execute(select(PlayerAnchor).order_by(PlayerAnchor.id))).scalars().all()
        )
        assert [(r.id, r.protected) for r in rows] == [
            ("a1", False),
            ("b9", False),
            ("c5", True),
        ], "同刻兜底不是 id 降序"

    async def test_idempotent(self, session: AsyncSession) -> None:
        """幂等：重跑不翻更多行（仍恰一行 protected=1）。"""
        session.add_all(
            [_anchor("a1", updated_at=100.0), _anchor("a2", updated_at=200.0)]
        )
        await session.commit()

        await _run_backfill(session)
        await _run_backfill(session)
        await _run_backfill(session)

        protected = (
            (
                await session.execute(
                    select(func.count())
                    .select_from(PlayerAnchor)
                    .where(PlayerAnchor.protected.is_(True))
                )
            ).scalar_one()
        )
        assert protected == 1

    async def test_empty_table_is_legal(self, session: AsyncSession) -> None:
        """全表无行 → 零行更新，不炸（子查询返回 NULL，`WHERE id = NULL` 匹配零行）。"""
        await _run_backfill(session)
        assert (
            await session.execute(select(func.count()).select_from(PlayerAnchor))
        ).scalar_one() == 0

    async def test_single_row_table(self, session: AsyncSession) -> None:
        """只有一档 → 它就是末梢，被标保护。"""
        session.add(_anchor("solo", updated_at=42.0))
        await session.commit()
        await _run_backfill(session)
        row = (await session.execute(select(PlayerAnchor))).scalar_one()
        assert row.protected is True

    async def test_backfill_does_not_touch_other_columns(self, session: AsyncSession) -> None:
        """只回填保护位：游标/名字/agent_override 逐字段不变。"""
        session.add(_anchor("a1", updated_at=100.0, name="原名"))
        await session.commit()
        before = (
            (await session.execute(select(PlayerAnchor))).scalar_one()
        )
        snapshot = (before.id, before.name, before.branch_id, before.tick, before.seq,
                    before.agent_override, before.updated_at)

        await _run_backfill(session)
        session.expire_all()
        after = (await session.execute(select(PlayerAnchor))).scalar_one()
        assert after.protected is True
        assert (after.id, after.name, after.branch_id, after.tick, after.seq,
                after.agent_override, after.updated_at) == snapshot


# ---------------------------------------------------------------------------
# 2. 迁移往返（scratch DB + 全 revision id）
# ---------------------------------------------------------------------------


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


class TestAlembic0010:
    def test_backfill_on_real_data(self, tmp_path: Path) -> None:
        """真跑一遍迁移：先造既有行（0009 态），upgrade head 后恰一行受保护。"""
        assert _alembic(tmp_path, "upgrade", "0009_branches_rng_state").returncode == 0
        db = tmp_path / "mig.db"
        conn = sqlite3.connect(str(db))
        try:
            now = time.time()
            for anchor_id, updated in (("a1", now), ("a2", now + 10), ("a3", now + 20)):
                conn.execute(
                    "INSERT INTO player_anchors"
                    " (id, name, branch_id, tick, seq, agent_override, protected,"
                    "  updated_at, created_at)"
                    " VALUES (?, ?, 'main', 0, 0, '{}', 0, ?, ?)",
                    (anchor_id, f"档-{anchor_id}", updated, updated),
                )
            conn.commit()
        finally:
            conn.close()

        assert _alembic(tmp_path, "upgrade", "head").returncode == 0
        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute(
                "SELECT id, protected FROM player_anchors ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        assert rows == [("a1", 0), ("a2", 0), ("a3", 1)]

    def test_upgrade_on_empty_anchor_table(self, tmp_path: Path) -> None:
        """空 anchors 库升级不炸（零行更新是合法态）。"""
        assert _alembic(tmp_path, "upgrade", "head").returncode == 0

    def test_round_trip_0009_0010(self, tmp_path: Path) -> None:
        """0009 ↔ 0010 逐级往返：回填结果保持、升级幂等（downgrade **不撤销**回填）。"""
        assert _alembic(tmp_path, "upgrade", "0009_branches_rng_state").returncode == 0
        db = tmp_path / "mig.db"
        conn = sqlite3.connect(str(db))
        try:
            now = time.time()
            for anchor_id, updated in (("a1", now), ("a2", now + 10)):
                conn.execute(
                    "INSERT INTO player_anchors"
                    " (id, name, branch_id, tick, seq, agent_override, protected,"
                    "  updated_at, created_at)"
                    " VALUES (?, ?, 'main', 0, 0, '{}', 0, ?, ?)",
                    (anchor_id, anchor_id, updated, updated),
                )
            conn.commit()
        finally:
            conn.close()

        assert _alembic(tmp_path, "upgrade", "head").returncode == 0
        assert _alembic(tmp_path, "downgrade", "0009_branches_rng_state").returncode == 0
        assert _alembic(tmp_path, "upgrade", "head").returncode == 0

        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute(
                "SELECT id, protected FROM player_anchors ORDER BY id"
            ).fetchall()
            version = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        finally:
            conn.close()
        assert rows == [("a1", 0), ("a2", 1)], "往返后回填结果变了"
        assert version == [("0010_protected_backfill",)]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _run_backfill(session: AsyncSession) -> None:
    """执行与 0010 迁移逐字相同的 UPDATE（经 ORM 连接，便于与夹具同库比对）。"""
    await session.execute(sa_text(BACKFILL_SQL))
    await session.commit()


def test_backfill_statement_matches_migration_source() -> None:
    """钉住「测试跑的语句 == 迁移源码里的语句」（versions 目录不是包，按源码比对）。"""
    src = (
        Path(__file__).resolve().parents[1]
        / "core"
        / "persistence"
        / "alembic"
        / "versions"
        / "0010_protected_backfill.py"
    ).read_text(encoding="utf-8")
    def _norm(text: str) -> str:
        # 迁移里 SQL 是跨行拼接的字面量：归一空白并去掉引号后比对
        return " ".join(text.replace('"', "").split())

    assert _norm(BACKFILL_SQL) in _norm(src), "0010 迁移里的回填语句与钉子不一致"
