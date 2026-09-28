"""M5-D3-a T1 钉子 — 0008 分叉身份四件（裁 1 / 3 / 4 / 9）

0008 是**读档 = 分叉**（DESIGN §12）的身份前置：分支身份要能承载「同一业务 id 在不同分支
各自存在」，跨分支引用要能表达「这个 seq 住在另一个分支」。四件：

| 件 | 表 | 变更 | 裁决 |
|---|---|---|---|
| a | `npc_profiles` | 主键 `id` → **`(branch_id, id)`** | 裁 1（F1，硬前置） |
| — | `events` | 加 **`parent_branch_id`** | 裁 3（谱系解析在查询层，不做第三套折叠规则） |
| d | `knowledge` | 加 **`evidence_branch_id`** + 成对 CHECK | 裁 4（封 C4 跨分支悬空） |
| — | `player_anchors` | 加 **`protected`** | 裁 9（与 kilo K7 锚点面合并，同表一支） |

两条成对不变式（DB CHECK 可表达，故落 DB；沿 0005「可表达约束进 DB」的先例）：
- `events.parent_branch_id IS NULL OR parent_seq IS NOT NULL`——指名父分支却没给 seq 无意义；
- `knowledge.evidence_branch_id IS NULL OR evidence_seq IS NOT NULL`——同上。
**单向**而非等值：`(NULL, 42)` 是合法且常见的「父事件/证据就在本分支」（既有行全是这种），
只有「给了分支却没给 seq」才是残缺引用。

本文件同时钉住 0008-a 顺带封掉的一个**跨分支写**（`npc_store._project_lod_change`
原先按 `npc_id` 单键取行、不看分支——分叉后子分支的 LOD 事件会写到父分支那一行）。

门禁：0008 往返零漂移用**全 revision id + scratch DB**（本树根 `world.db` 是脏库，
`alembic_version` 缺失但表已存在 → `upgrade head` 撞 `branches` exists，绝不用）。
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import ColumnDefault, Table, select
from sqlalchemy.dialects import sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from sim.core.events import npc_lod_change_event
from sim.core.persistence.database import init_database
from sim.core.persistence.models import Event, Knowledge, NpcProfile, PlayerAnchor
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore

BRANCH_MAIN = "main"
BRANCH_FORK = "fork-a"


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


def _profile(
    npc_id: str,
    *,
    branch_id: str = BRANCH_MAIN,
    lod: int = 1,
    name: str = "",
) -> NpcProfile:
    return NpcProfile(
        id=npc_id,
        branch_id=branch_id,
        name=name or f"NPC-{npc_id}",
        identity_anchor="我叫陈默。",
        ocean_neuroticism=75,
        lod=lod,
    )


# ---------------------------------------------------------------------------
# 1. ORM 形状（迁移前就把目标形状钉死）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestForkIdentitySchema:
    def test_npc_profile_composite_primary_key(self) -> None:
        assert [c.name for c in cast(Table, NpcProfile.__table__).primary_key.columns] == [
            "branch_id",
            "id",
        ]

    def test_events_parent_branch_id_column(self) -> None:
        cols = cast(Table, Event.__table__).columns
        assert "parent_branch_id" in cols
        assert cols["parent_branch_id"].nullable, "parent_branch_id 必须可空（NULL = 同分支）"

    def test_knowledge_evidence_branch_id_column(self) -> None:
        cols = cast(Table, Knowledge.__table__).columns
        assert "evidence_branch_id" in cols
        assert cols["evidence_branch_id"].nullable

    def test_cross_branch_reference_pair_constraints_exist(self) -> None:
        """两条成对不变式必须落 DB CHECK（可表达约束进 DB，沿 0005 先例）。"""
        events_sql = str(
            CreateTable(cast(Table, Event.__table__)).compile(dialect=sqlite.dialect())
        )
        knowledge_sql = str(
            CreateTable(cast(Table, Knowledge.__table__)).compile(dialect=sqlite.dialect())
        )
        assert "ck_events_parent_branch_pair" in events_sql
        assert "ck_knowledge_evidence_pair" in knowledge_sql

    def test_player_anchor_protected_column(self) -> None:
        col = cast(Table, PlayerAnchor.__table__).columns["protected"]
        assert not col.nullable
        default = cast(ColumnDefault[object], col.default)
        assert default.arg is False, "protected 缺省必须是 False"

    def test_new_indexes_present(self) -> None:
        events_idx = {i.name for i in cast(Table, Event.__table__).indexes}
        know_idx = {i.name for i in cast(Table, Knowledge.__table__).indexes}
        assert "idx_events_parent_branch" in events_idx
        assert "idx_knowledge_evidence" in know_idx


# ---------------------------------------------------------------------------
# 2. 行为：同 id 跨分支共存 + 跨分支写封口 + 成对引用
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestCrossBranchIdentity:
    async def test_same_npc_id_coexists_across_branches(self, session: AsyncSession) -> None:
        """0008-a 的核心能力：同 npc_id 在两个分支各一行、各自独立取值。"""
        session.add_all(
            [
                _profile("chenmo", branch_id=BRANCH_MAIN, lod=1, name="陈默·主线"),
                _profile("chenmo", branch_id=BRANCH_FORK, lod=2, name="陈默·分叉"),
            ]
        )
        await session.commit()

        rows = (await session.execute(select(NpcProfile))).scalars().all()
        assert {(r.branch_id, r.lod, r.name) for r in rows} == {
            (BRANCH_MAIN, 1, "陈默·主线"),
            (BRANCH_FORK, 2, "陈默·分叉"),
        }

    async def test_materialize_reads_only_own_branch(self, store, session: AsyncSession) -> None:
        session.add_all(
            [
                _profile("chenmo", branch_id=BRANCH_MAIN, name="主线"),
                _profile("chenmo", branch_id=BRANCH_FORK, name="分叉"),
            ]
        )
        await session.commit()

        main_profiles = await NpcStore(store, branch_id=BRANCH_MAIN).materialize()
        fork_profiles = await NpcStore(store, branch_id=BRANCH_FORK).materialize()
        assert main_profiles["chenmo"].name == "主线"
        assert fork_profiles["chenmo"].name == "分叉"

    async def test_lod_projection_is_branch_scoped(self, store, session: AsyncSession) -> None:
        """分叉后子分支的 LOD 事件**不得**改到父分支那一行（跨分支写封口）。"""
        session.add_all(
            [
                _profile("chenmo", branch_id=BRANCH_MAIN, lod=1),
                _profile("chenmo", branch_id=BRANCH_FORK, lod=1),
            ]
        )
        await session.commit()

        fork_store = NpcStore(store, branch_id=BRANCH_FORK)
        await fork_store.flush_tick([npc_lod_change_event(5, "chenmo", 1, 2, "enter_range")])

        session.expire_all()
        rows = (await session.execute(select(NpcProfile))).scalars().all()
        by_branch = {r.branch_id: r.lod for r in rows}
        assert by_branch[BRANCH_FORK] == 2, "分叉分支的 LOD 投影未生效"
        assert by_branch[BRANCH_MAIN] == 1, "LOD 投影串写到父分支行（跨分支写）"

    async def test_parent_branch_id_persists_and_defaults_null(
        self, store, session: AsyncSession
    ) -> None:
        """`parent_branch_id` 随 append 透传（同 `parent_seq` 口径）；缺省 NULL = 同分支。"""
        await store.append(
            BRANCH_FORK,
            [
                {
                    "tick": 1,
                    "event_type": "npc.lod_change",
                    "actor_id": "chenmo",
                    "target_id": None,
                    "parent_seq": 7,
                    "parent_branch_id": BRANCH_MAIN,
                    "payload": {
                        "npc_id": "chenmo",
                        "from_lod": 1,
                        "to_lod": 2,
                        "reason": "enter_range",
                    },
                    "witnesses": [],
                    "entropy_ref": None,
                }
            ],
        )
        await store.append(
            BRANCH_FORK,
            [
                {
                    "tick": 2,
                    "event_type": "npc.lod_change",
                    "actor_id": "chenmo",
                    "target_id": None,
                    "parent_seq": None,
                    "parent_branch_id": None,
                    "payload": {
                        "npc_id": "chenmo",
                        "from_lod": 2,
                        "to_lod": 1,
                        "reason": "leave_range",
                    },
                    "witnesses": [],
                    "entropy_ref": None,
                }
            ],
        )

        rows = (await session.execute(select(Event))).scalars().all()
        assert [(r.parent_seq, r.parent_branch_id) for r in rows] == [
            (7, BRANCH_MAIN),
            (None, None),
        ]

    async def test_knowledge_evidence_branch_round_trip(self, session: AsyncSession) -> None:
        """跨分支证据可表达：`(evidence_branch_id, evidence_seq)` 二元组。"""
        row = Knowledge(
            holder_id="chenmo",
            fact="他手上有伤",
            confidence=0.8,
            source="witnessed",
            learned_at=10,
            branch_id=BRANCH_FORK,
            evidence_seq=42,
            evidence_branch_id=BRANCH_MAIN,
        )
        session.add(row)
        await session.commit()

        got = (
            await session.execute(
                select(Knowledge).where(
                    Knowledge.branch_id == BRANCH_FORK, Knowledge.holder_id == "chenmo"
                )
            )
        ).scalar_one()
        assert (got.evidence_seq, got.evidence_branch_id) == (42, BRANCH_MAIN)

    async def test_evidence_branch_without_seq_rejected(self, session: AsyncSession) -> None:
        """残缺引用（给了分支没给 seq）→ DB CHECK 拒。"""
        session.add(
            Knowledge(
                holder_id="chenmo",
                fact="残缺引用",
                confidence=0.5,
                source="witnessed",
                learned_at=10,
                branch_id=BRANCH_FORK,
                evidence_seq=None,
                evidence_branch_id=BRANCH_MAIN,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_evidence_seq_without_branch_allowed(self, session: AsyncSession) -> None:
        """既有形态 `(NULL, seq)` = 证据在本分支，必须仍然合法（单向 CHECK）。"""
        session.add(
            Knowledge(
                holder_id="chenmo",
                fact="本分支目击",
                confidence=0.5,
                source="witnessed",
                learned_at=10,
                branch_id=BRANCH_MAIN,
                evidence_seq=3,
                evidence_branch_id=None,
            )
        )
        await session.commit()
        rows = (await session.execute(select(Knowledge))).scalars().all()
        assert len(rows) == 1 and rows[0].evidence_seq == 3

    async def test_player_anchor_protected_defaults_false(self, session: AsyncSession) -> None:
        anchor = PlayerAnchor(
            id="a" * 12,
            name="第一天",
            branch_id=BRANCH_MAIN,
            tick=10,
            seq=3,
            agent_override=json.dumps({}),
        )
        session.add(anchor)
        await session.commit()
        session.expire_all()
        got = await session.get(PlayerAnchor, "a" * 12)
        assert got is not None
        assert got.protected is False

        got.protected = True
        await session.commit()
        session.expire_all()
        again = await session.get(PlayerAnchor, "a" * 12)
        assert again is not None and again.protected is True


# ---------------------------------------------------------------------------
# 3. 0008 迁移往返（scratch DB + 全 revision id）
# ---------------------------------------------------------------------------


class TestAlembic0008:
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

    @staticmethod
    def _inspect(db: Path) -> dict[str, object]:
        conn = sqlite3.connect(str(db))
        try:
            profile_pk = [r[1] for r in conn.execute("PRAGMA table_info(npc_profiles)") if r[5]]
            event_cols = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
            know_cols = {r[1] for r in conn.execute("PRAGMA table_info(knowledge)")}
            anchor_cols = {r[1] for r in conn.execute("PRAGMA table_info(player_anchors)")}
            return {
                "profile_pk": profile_pk,
                "event_cols": event_cols,
                "know_cols": know_cols,
                "anchor_cols": anchor_cols,
            }
        finally:
            conn.close()

    def test_upgrade_head_has_four_changes(self, tmp_path: Path) -> None:
        self._run(tmp_path, "upgrade", "head")
        info = self._inspect(tmp_path / "mig.db")

        assert set(info["profile_pk"]) == {"branch_id", "id"}, (  # type: ignore[arg-type]
            "npc_profiles 主键未改复合"
        )
        assert "parent_branch_id" in info["event_cols"]  # type: ignore[operator]
        assert "evidence_branch_id" in info["know_cols"]  # type: ignore[operator]
        assert "protected" in info["anchor_cols"]  # type: ignore[operator]

    def test_round_trip_0008(self, tmp_path: Path) -> None:
        """head → 0007（**全 revision id**）→ head：结构与数据都在。"""
        self._run(tmp_path, "upgrade", "head")
        self._run(tmp_path, "downgrade", "0007_m4_material_balances")

        down = self._inspect(tmp_path / "mig.db")
        assert set(down["profile_pk"]) == {"id"}, (  # type: ignore[arg-type]
            "downgrade 未把 npc_profiles 主键还原为单列"
        )
        assert "parent_branch_id" not in down["event_cols"]  # type: ignore[operator]
        assert "evidence_branch_id" not in down["know_cols"]  # type: ignore[operator]
        assert "protected" not in down["anchor_cols"]  # type: ignore[operator]

        self._run(tmp_path, "upgrade", "head")
        up = self._inspect(tmp_path / "mig.db")
        assert set(up["profile_pk"]) == {"branch_id", "id"}  # type: ignore[arg-type]
        assert "parent_branch_id" in up["event_cols"]  # type: ignore[operator]
        assert "evidence_branch_id" in up["know_cols"]  # type: ignore[operator]
        assert "protected" in up["anchor_cols"]  # type: ignore[operator]
