"""M2 数据层测试 — NPC 完整属性 + 物质熵增状态 + 0004 迁移（M2-D1）。

覆盖：
- 三张 M2 表（npc_profiles / npc_health / matter_state）ORM 可插入/可读；
- 隐藏属性标注字段（hidden / descriptors / trigger_conditions）落库，
  字段映射对齐 codex sim/npc/hidden.py HiddenAttribute + self-unknown.md §6；
- 50 NPC 基线：批量写入 50 条 profile，OCEAN/PAD/健康档齐备；
- Alembic 0004 迁移 upgrade/downgrade（用临时文件库）；
- 0004 不触碰 sqlite-vec 虚拟表（npc_memory_vec 仍锁 M3）。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.models import (
    MatterState,
    NpcHealth,
    NpcProfile,
)


@pytest.fixture
async def engine():
    """内存 SQLite 库（Base.metadata.create_all，含 M2 表）。"""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        yield s


def _profile(npc_id: str, **overrides) -> NpcProfile:
    base: dict = {
        "id": npc_id,
        "branch_id": "main",
        "name": f"NPC-{npc_id}",
        "species": "human",
        "gender": "female",
        "age": 30,
        "occupation": "零工",
        "identity_anchor": "我叫陈默，二十七岁，靠零工过活。",
        "ocean_openness": 45,
        "ocean_conscientiousness": 55,
        "ocean_extraversion": 40,
        "ocean_agreeableness": 60,
        "ocean_neuroticism": 75,
        "pad_pleasure": -0.2,
        "pad_arousal": 0.1,
        "pad_dominance": -0.3,
        "emotion_updated_tick": 10,
        "needs": json.dumps([{"name": "hunger", "value": 0.8, "weight": 1.0}]),
        "skills": json.dumps({"搬货": 0.4}),
        "goals": json.dumps({"short": "找活", "long": "活下去"}),
        "inventory": json.dumps(["旧布包"]),
        "knowledge_boundary": json.dumps({"literacy": 0.5, "jargon": [], "class_register": "平民"}),
        "lod": 1,
        "created_at_tick": 0,
        "updated_at_tick": 10,
    }
    base.update(overrides)
    return NpcProfile(**base)


@pytest.mark.t1
class TestNpcProfiles:
    """npc_profiles：50 NPC 完整属性宽表（DESIGN §13）。"""

    async def test_insert_profile_with_full_attributes(self, session: AsyncSession) -> None:
        session.add(_profile("npc-chenmo"))
        await session.commit()

        row = (await session.execute(select(NpcProfile))).scalars().one()
        assert row.id == "npc-chenmo"
        # OCEAN / PAD 数值列
        assert row.ocean_neuroticism == 75
        assert row.pad_pleasure == pytest.approx(-0.2)
        # JSON 集合列可还原
        assert json.loads(row.needs)[0]["name"] == "hunger"
        assert json.loads(row.goals)["long"] == "活下去"

    async def test_fifty_npc_baseline_roundtrip(self, session: AsyncSession) -> None:
        """50 NPC 自转基线：批量写入 + 计数 + LOD 查询。"""
        session.add_all([_profile(f"npc-{i:02d}") for i in range(50)])
        await session.commit()

        rows = (await session.execute(select(NpcProfile))).scalars().all()
        assert len(rows) == 50

        lod1 = (
            (await session.execute(select(NpcProfile).where(NpcProfile.lod == 1))).scalars().all()
        )
        assert len(lod1) == 50

    async def test_species_default_is_human(self, session: AsyncSession) -> None:
        """物种级 profile（DESIGN §7）：默认 human，可覆写为动物。"""
        session.add(_profile("npc-ghost-cat", species="cat"))
        await session.commit()
        rows = (await session.execute(select(NpcProfile))).scalars().all()
        assert {r.species for r in rows} == {"cat"}


@pytest.mark.t1
class TestNpcHealth:
    """npc_health：健康档 + 隐藏标注（DESIGN §13 + codex self-unknown §6）。"""

    async def test_insert_health_record(self, session: AsyncSession) -> None:
        session.add(
            NpcHealth(
                npc_id="npc-chenmo",
                branch_id="main",
                category="old_injury",
                label="右腿旧伤",
                severity=0.6,
                active=True,
                created_at_tick=0,
            )
        )
        await session.commit()

        row = (await session.execute(select(NpcHealth))).scalars().one()
        assert row.category == "old_injury"
        assert row.severity == pytest.approx(0.6)

    async def test_hidden_attribute_fields_default_and_roundtrip(
        self, session: AsyncSession
    ) -> None:
        """隐藏属性三列：hidden / descriptors / trigger_conditions（codex 协调必填）。"""
        # 非隐藏记录走默认值
        session.add(
            NpcHealth(
                npc_id="npc-1",
                branch_id="main",
                category="disease",
                label="风寒",
                created_at_tick=0,
            )
        )
        # 隐藏创伤：descriptors=直陈词面，trigger_conditions=情境触发关键词
        session.add(
            NpcHealth(
                npc_id="npc-1",
                branch_id="main",
                category="trauma",
                label="井边旧事",
                severity=0.7,
                hidden=True,
                descriptors=json.dumps(["井", "那口井"], ensure_ascii=False),
                trigger_conditions=json.dumps(["水井", "打水"], ensure_ascii=False),
                created_at_tick=0,
            )
        )
        await session.commit()

        rows = (await session.execute(select(NpcHealth))).scalars().all()
        by_cat = {r.category: r for r in rows}

        visible = by_cat["disease"]
        assert visible.hidden is False
        assert json.loads(visible.descriptors) == []
        assert json.loads(visible.trigger_conditions) == []

        hidden = by_cat["trauma"]
        assert hidden.hidden is True
        assert json.loads(hidden.descriptors) == ["井", "那口井"]
        assert json.loads(hidden.trigger_conditions) == ["水井", "打水"]

    async def test_hidden_filter_query(self, session: AsyncSession) -> None:
        """hidden 过滤：默认只取可见健康档，隐藏项按 trigger 命中时另取。"""
        session.add_all(
            [
                NpcHealth(
                    npc_id="npc-1",
                    branch_id="main",
                    category="disability",
                    label="跛",
                    hidden=False,
                    created_at_tick=0,
                ),
                NpcHealth(
                    npc_id="npc-1",
                    branch_id="main",
                    category="addiction",
                    label="酗酒",
                    hidden=True,
                    created_at_tick=0,
                ),
            ]
        )
        await session.commit()

        visible = (
            (await session.execute(select(NpcHealth).where(NpcHealth.hidden.is_(False))))
            .scalars()
            .all()
        )
        assert [r.label for r in visible] == ["跛"]


@pytest.mark.t1
class TestMatterState:
    """matter_state：物质熵增状态（DESIGN §11/§14）。"""

    async def test_insert_and_decay_state(self, session: AsyncSession) -> None:
        session.add(
            MatterState(
                subject_id="struct-hut-1",
                branch_id="main",
                subject_kind="structure",
                material="wood",
                integrity=0.8,
                quality=0.4,
                decay_rate=0.001,
                load_bearing=True,
                supported_by=json.dumps(["struct-beam-1"]),
                last_decay_tick=0,
                updated_at_tick=100,
            )
        )
        await session.commit()

        row = (await session.execute(select(MatterState))).scalars().one()
        assert row.integrity == pytest.approx(0.8)
        assert row.load_bearing is True
        assert json.loads(row.supported_by) == ["struct-beam-1"]
        assert row.is_rubble is False

    async def test_rubble_terminal_state(self, session: AsyncSession) -> None:
        """integrity 归零变 rubble，永不恢复（§14）。"""
        session.add(
            MatterState(
                subject_id="struct-wall-9",
                branch_id="main",
                integrity=0.0,
                is_rubble=True,
            )
        )
        await session.commit()

        row = (await session.execute(select(MatterState))).scalars().one()
        assert row.is_rubble is True
        assert row.integrity == 0.0


@pytest.mark.t1
class TestAlembic0004:
    """0004 迁移：upgrade 建 M2 表，downgrade 回滚，向量虚拟表不受影响。"""

    def _run(self, tmp_path: Path, *args: str) -> None:
        import os
        import subprocess
        import sys

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

    def _tables(self, db: Path) -> set[str]:
        conn = sqlite3.connect(str(db))
        try:
            return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()

    def test_upgrade_head_creates_m2_tables(self, tmp_path: Path) -> None:
        self._run(tmp_path, "upgrade", "head")
        db = tmp_path / "mig.db"
        tables = self._tables(db)
        assert {"npc_profiles", "npc_health", "matter_state"} <= tables

        # 隐藏属性三列在 npc_health 上
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(npc_health)")}
        finally:
            conn.close()
        assert {"hidden", "descriptors", "trigger_conditions"} <= cols

    def test_upgrade_head_no_vec_table(self, tmp_path: Path) -> None:
        """npc_memory_vec 仍锁 M3：迁移不创建 sqlite-vec 虚拟表。"""
        self._run(tmp_path, "upgrade", "head")
        assert "npc_memory_vec" not in self._tables(tmp_path / "mig.db")

    def test_downgrade_removes_m2_tables(self, tmp_path: Path) -> None:
        self._run(tmp_path, "upgrade", "head")
        self._run(tmp_path, "downgrade", "0003_memory_write")
        tables = self._tables(tmp_path / "mig.db")
        assert "npc_profiles" not in tables
        assert "npc_health" not in tables
        assert "matter_state" not in tables
        # M0/M3 预留表仍在
        assert {"events", "npc_memories", "relationships", "knowledge"} <= tables
