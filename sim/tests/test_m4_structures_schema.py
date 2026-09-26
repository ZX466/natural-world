"""M4-D2a T1 钉子 — structures 瘦身表 + matter 复合身份 + 0006 迁移往返。"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import EventKind, matter_event
from sim.core.persistence.database import init_database
from sim.core.persistence.models import MatterState, Structure
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def store(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return SqlEventStore(sf)


@pytest.fixture
async def session(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        yield s


@pytest.mark.t1
class TestStructureSchema:
    def test_structure_columns_are_topology_only(self) -> None:
        columns = set(cast(Table, Structure.__table__).columns.keys())
        assert columns == {
            "branch_id",
            "structure_id",
            "tiles",
            "kind",
            "material",
            "phase",
            "load_bearing",
            "supported_by",
            "owner_id",
            "built_by",
            "built_at",
            "created_at",
        }
        assert not {"integrity", "quality", "decay_rate", "is_rubble"} & columns

    def test_structure_composite_primary_key(self) -> None:
        assert [c.name for c in cast(Table, Structure.__table__).primary_key.columns] == [
            "branch_id",
            "structure_id",
        ]

    def test_matter_state_composite_primary_key(self) -> None:
        assert [c.name for c in cast(Table, MatterState.__table__).primary_key.columns] == [
            "branch_id",
            "subject_id",
        ]

    def test_structure_indexes(self) -> None:
        names = {index.name for index in cast(Table, Structure.__table__).indexes}
        assert {"idx_struct_branch", "idx_struct_owner", "idx_struct_phase"} <= names

    async def test_same_structure_id_coexists_across_branches(self, session: AsyncSession) -> None:
        session.add_all(
            [
                Structure(
                    branch_id="main",
                    structure_id="hut-1",
                    tiles=json.dumps([[0, 0]]),
                    kind="wood_hut",
                    material="wood",
                    phase="active",
                ),
                Structure(
                    branch_id="branch-b",
                    structure_id="hut-1",
                    tiles=json.dumps([[8, 8]]),
                    kind="wood_hut",
                    material="wood",
                    phase="building",
                ),
            ]
        )
        await session.commit()

        rows = (await session.execute(select(Structure))).scalars().all()
        assert {(row.branch_id, row.structure_id, row.phase) for row in rows} == {
            ("main", "hut-1", "active"),
            ("branch-b", "hut-1", "building"),
        }


@pytest.mark.t1
class TestMatterProjectionBranchIdentity:
    async def test_same_matter_id_projects_per_branch(self, store, session: AsyncSession) -> None:
        main = NpcStore(store, branch_id="main")
        branch_b = NpcStore(store, branch_id="branch-b")

        await main.flush_tick([matter_event(1, EventKind.MATTER_BUILD, "shared", durability=0.9)])
        await branch_b.flush_tick(
            [matter_event(2, EventKind.MATTER_BUILD, "shared", durability=0.3)]
        )

        rows = (await session.execute(select(MatterState))).scalars().all()
        actual = sorted((row.branch_id, row.integrity) for row in rows)
        assert [row[0] for row in actual] == ["branch-b", "main"]
        assert actual[0][1] == pytest.approx(0.3)
        assert actual[1][1] == pytest.approx(0.9)


class TestAlembic0006:
    def _run(self, tmp_path: Path, *args: str) -> None:
        env = {"WORLD_DB_URL": f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}"}
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=str(Path(__file__).resolve().parents[2]),
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    def test_upgrade_creates_structures_and_composite_pk(self, tmp_path: Path) -> None:
        self._run(tmp_path, "upgrade", "head")
        db = tmp_path / "mig.db"
        conn = sqlite3.connect(str(db))
        try:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert "structures" in tables
            struct_cols = {r[1] for r in conn.execute("PRAGMA table_info(structures)")}
            matter_pk = [
                (r[1], r[5]) for r in conn.execute("PRAGMA table_info(matter_state)") if r[5]
            ]
        finally:
            conn.close()

        assert {
            "branch_id",
            "structure_id",
            "tiles",
            "kind",
            "material",
            "phase",
            "load_bearing",
            "supported_by",
        } <= struct_cols
        assert {name for name, _ in matter_pk} == {"branch_id", "subject_id"}
        assert {pk for _, pk in matter_pk} == {1, 2}

    def test_round_trip_0006(self, tmp_path: Path) -> None:
        self._run(tmp_path, "upgrade", "head")
        self._run(tmp_path, "downgrade", "0005_m3_knowledge_governance")
        conn = sqlite3.connect(str(tmp_path / "mig.db"))
        try:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "structures" not in tables

        self._run(tmp_path, "upgrade", "head")
        conn = sqlite3.connect(str(tmp_path / "mig.db"))
        try:
            matter_pk = [r[1] for r in conn.execute("PRAGMA table_info(matter_state)") if r[5]]
        finally:
            conn.close()
        assert set(matter_pk) == {"branch_id", "subject_id"}
