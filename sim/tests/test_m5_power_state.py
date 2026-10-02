"""M5-A7 T1 钉子 — 批次 C 权力机制数据面（0013 `npc_power` + `PowerStore`）

设计稿 `docs/data/m5-power-data-preplan.md`（裁 31-1：预研稿推荐案 = 施工案）；判据
`docs/security/m5-authority-criteria-preplan.md`（D-10 不可见 / 红线 A / 红线 B）。

本文件钉住四组不变量：

1. **表形态**（§1）：复合 PK `(branch_id, npc_id)`、量纲 CHECK、``tick >= 0`` CHECK、
   **零索引**（PK 前导列即 branch_id，再加索引是冗余）；**模型与迁移同源**（反射列集
   逐列对齐，防「改了模型忘了迁移」——0006/0008 时代的漂移源）。
2. **迁移往返**（§2）：scratch DB + **全 revision id**（不钉 head：A5 血的纪律）、
   空表升级、重复 upgrade 幂等、downgrade 清表；迁移源码与钉子里的判据文本逐字同源。
3. **读写面 fail-closed**（§3）：NaN/Inf、tick 倒流、非法 id、分支非 active 一律
   **零写**；批内一条非法 ⇒ **全批零写**；越界**夹取但如实上报** ``clamped``；
   读面**纯读**、未知 id 不在结果、同 id 跨分支隔离。
4. **分叉克隆 + 禁面**（§4）：克隆逐字节等于父分支当前值、父行不动（C6）、
   **权力不落事件流**（零新 kind，红线 A 的执行形态）、**列名是禁键集内的绊线**
   （红线 B：意外出站即被 codex 递归扫当场抓住）、A3 地基分类已登记第 4 张不可重建表。

⚠️ **量纲假设**：`[POWER_MIN, POWER_MAX]` 归一是本单推荐（裁 31-1 授权）。机制若要原始分
⇒ 改三处同源常量 + 一支放宽 CHECK 的迁移；钉子会随之提醒（`test_range_constants_agree`）。
"""

from __future__ import annotations

import math
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.event_validation import PAYLOAD_MODELS
from sim.core.persistence.fork import fork_from_anchor
from sim.core.persistence.models import (
    POWER_MAX,
    POWER_MIN,
    Branch,
    Event,
    NpcPower,
)
from sim.core.persistence.power_store import PowerState, PowerStore, PowerWriteError
from sim.core.persistence.store import InactiveBranchError, SqlEventStore

PARENT = "main"
CHILD = "fork-b"
ARCHIVE = "archive-line"

#: 与 codex `m5-authority-criteria-preplan.md` §3 红线 B 同源的禁键集。
#: 本地抄一份而不是 import 对方的测试模块：判据资产归 codex，本钉只做**同源断言**——
#: 若 codex 扩禁键集，本文件的「绊线钉」会红，提醒同步（而不是静默失配）。
AUTHORITY_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "authority",
        "power",
        "rank",
        "authority_level",
        "power_level",
        "dominance",
        "prestige",
        "influence",
        "authority_score",
    }
)


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


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


@pytest.fixture
async def power(store: SqlEventStore, session: AsyncSession) -> PowerStore:
    """默认分支已存在的 `PowerStore`（写面要过分支闸门 ⇒ 分支行必须先落库）。"""
    session.add(Branch(id=PARENT, status="active", is_current=True))
    await session.commit()
    return PowerStore(store, branch_id=PARENT)


async def _rows(session: AsyncSession) -> list[tuple[str, str, float, int]]:
    """整表读回（排序后逐位比对；测试只认正向读回，不靠回滚证明）。"""
    result = await session.execute(
        select(NpcPower.branch_id, NpcPower.npc_id, NpcPower.power_level, NpcPower.updated_at_tick)
    )
    return sorted((str(r[0]), str(r[1]), float(r[2]), int(r[3])) for r in result.all())


# ---------------------------------------------------------------------------
# 1. 表形态
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestPowerTableShape:
    async def test_columns_and_composite_pk(self, session: AsyncSession) -> None:
        """列集与复合 PK：分叉后同 npc_id 跨分支共存（0008 npc_profiles 同款）。"""
        session.add_all(
            [
                NpcPower(branch_id=PARENT, npc_id="chenmo", power_level=0.5, updated_at_tick=3),
                NpcPower(branch_id=CHILD, npc_id="chenmo", power_level=-0.5, updated_at_tick=9),
            ]
        )
        await session.commit()
        assert await _rows(session) == [
            (CHILD, "chenmo", -0.5, 9),
            (PARENT, "chenmo", 0.5, 3),
        ]

    async def test_duplicate_row_same_branch_rejected(self, session: AsyncSession) -> None:
        """同 `(branch_id, npc_id)` 二次插入 ⇒ IntegrityError（幂等写走 UPSERT 语义）。"""
        session.add(NpcPower(branch_id=PARENT, npc_id="chenmo", power_level=0.1))
        await session.commit()
        session.add(NpcPower(branch_id=PARENT, npc_id="chenmo", power_level=0.2))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_level_range_checked_by_db(self, session: AsyncSession) -> None:
        """量纲 CHECK 在**数据库层**（绕过写面直接 ORM 写也会被拒 = 第二道防线）。"""
        for out_of_range in (POWER_MAX + 0.1, POWER_MIN - 0.1):
            session.add(
                NpcPower(
                    branch_id=PARENT,
                    npc_id=f"npc-{out_of_range}",
                    power_level=out_of_range,
                    updated_at_tick=0,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()

    async def test_negative_tick_checked_by_db(self, session: AsyncSession) -> None:
        """`updated_at_tick >= 0` CHECK：负 tick 是调用方 bug，不许进库。"""
        session.add(NpcPower(branch_id=PARENT, npc_id="chenmo", updated_at_tick=-1))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_no_redundant_index_beyond_pk(self, session: AsyncSession) -> None:
        """**零索引**是设计决定：PK 前导列即 branch_id ⇒ 分支查询走 PK 前缀。

        钉它是因为「顺手加一支 idx_*_branch」看起来无害，但会让克隆/迁移面多一处漂移源。
        """
        ddl = (
            (
                await session.execute(
                    sa_text(
                        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='npc_power'"
                    )
                )
            )
            .scalars()
            .all()
        )
        named = sorted(str(s) for s in ddl if s and "sqlite_autoindex" not in str(s))
        assert named == [], f"npc_power 出现了计划外索引：{named}"

    def test_range_constants_agree(self) -> None:
        """量纲三处同源：模型常量 = 写面常量 = 迁移源码文本。"""
        from sim.core.persistence import power_store

        assert (power_store.POWER_MIN, power_store.POWER_MAX) == (POWER_MIN, POWER_MAX)
        assert (POWER_MIN, POWER_MAX) == (-1.0, 1.0), "量纲被改动：见预研稿 §4 待裁点 1"
        src = (
            Path(__file__).resolve().parents[1]
            / "core"
            / "persistence"
            / "alembic"
            / "versions"
            / "0013_power_state.py"
        ).read_text(encoding="utf-8")
        assert "power_level >= {POWER_MIN} AND power_level <= {POWER_MAX}" in src or (
            f"power_level >= {POWER_MIN} AND power_level <= {POWER_MAX}" in src
        ), "迁移 CHECK 文本与模型/写面常量不同源"

    def test_model_columns_match_migration_source(self) -> None:
        """模型列集 == 迁移列集（源码逐名比对，防「改了模型忘了写迁移」）。"""
        src = (
            Path(__file__).resolve().parents[1]
            / "core"
            / "persistence"
            / "alembic"
            / "versions"
            / "0013_power_state.py"
        ).read_text(encoding="utf-8")
        declared = {str(c.name) for c in NpcPower.__table__.columns}
        for column in declared:
            assert f'sa.Column("{column}"' in src, f"迁移缺列 {column}"
        for name in ("ck_npc_power_level_range", "ck_npc_power_tick_nonneg"):
            assert name in src, f"迁移缺 CHECK {name}"
        assert 'op.drop_table("npc_power")' in src, "downgrade 未 drop 表"


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


def _table_exists(db: Path) -> bool:
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='npc_power'"
        ).fetchone()
    finally:
        conn.close()
    return bool(row[0])


def _version(db: Path) -> str:
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    finally:
        conn.close()
    return str(rows[0][0])


class TestAlembic0013:
    def test_upgrade_creates_table_on_0012_db(self, tmp_path: Path) -> None:
        """从 0012 态升级建表成功（既有库零行 ⇒ 无回填可失败）。"""
        assert _alembic(tmp_path, "upgrade", "0012_branches_current").returncode == 0
        assert _alembic(tmp_path, "upgrade", "0013_power_state").returncode == 0
        assert _table_exists(tmp_path / "mig.db")
        assert _version(tmp_path / "mig.db") == "0013_power_state"

    def test_upgrade_is_repeatable(self, tmp_path: Path) -> None:
        """重复 upgrade 到同一 revision id 不炸（幂等）。"""
        assert _alembic(tmp_path, "upgrade", "0013_power_state").returncode == 0
        assert _alembic(tmp_path, "upgrade", "0013_power_state").returncode == 0

    def test_round_trip_0012_0013_preserves_rows(self, tmp_path: Path) -> None:
        """0012 ↔ 0013 逐级往返：0013 自己的行随表 drop 而空（**刻意**，见下）。"""
        assert _alembic(tmp_path, "upgrade", "0013_power_state").returncode == 0
        db = tmp_path / "mig.db"
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO npc_power"
                " (branch_id, npc_id, power_level, updated_at_tick, created_at)"
                " VALUES ('main', 'chenmo', 0.4, 12, 1.0)"
            )
            conn.commit()
        finally:
            conn.close()

        assert _alembic(tmp_path, "downgrade", "0012_branches_current").returncode == 0
        assert not _table_exists(db), "downgrade 未 drop 表"
        assert _alembic(tmp_path, "upgrade", "0013_power_state").returncode == 0

        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute("SELECT branch_id, npc_id FROM npc_power").fetchall()
        finally:
            conn.close()
        assert rows == [], "降级重建后应为空（权力态是运行期累计量，降级即放弃这段历史）"
        assert _version(db) == "0013_power_state"

    def test_downgrade_then_upgrade_keeps_other_tables(self, tmp_path: Path) -> None:
        """降 0013 只碰本表：events / branches 等既有表不受牵连。"""
        assert _alembic(tmp_path, "upgrade", "0013_power_state").returncode == 0
        assert _alembic(tmp_path, "downgrade", "0012_branches_current").returncode == 0
        conn = sqlite3.connect(str(tmp_path / "mig.db"))
        try:
            tables = {
                str(r[0])
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "npc_power" not in tables
        assert {"events", "branches", "player_anchors", "anchor_packages"} <= tables


# ---------------------------------------------------------------------------
# 3. 读写面（fail-closed）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestPowerWriteSurface:
    async def test_first_apply_creates_row_from_zero(self, power: PowerStore) -> None:
        """首次写建行，基线 0（未表态 ≡ 0，与读面「无行 = 兜底 0」同口径）。"""
        state = await power.apply("chenmo", 0.25, tick=7)
        assert state == PowerState(npc_id="chenmo", power_level=0.25, updated_at_tick=7)
        assert (await power.materialize())["chenmo"].power_level == pytest.approx(0.25)

    async def test_apply_accumulates_and_advances_tick(self, power: PowerStore) -> None:
        """增量累加 + `updated_at_tick` 前进（衰减游标由写面维护，读面纯读）。"""
        await power.apply("chenmo", 0.2, tick=10)
        state = await power.apply("chenmo", 0.3, tick=20)
        assert state.power_level == pytest.approx(0.5)
        assert state.updated_at_tick == 20
        assert (await power.materialize(["chenmo"]))["chenmo"].updated_at_tick == 20

    async def test_apply_batch_writes_many_in_one_go(self, power: PowerStore) -> None:
        """批量 = 一次事务多行（分叉/衰减后的整批更新不进热路径逐行开销）。"""
        results = await power.apply_batch({"a": 0.1, "b": -0.2, "c": 0.0}, tick=5)
        assert set(results) == {"a", "b", "c"}
        assert {k: v.power_level for k, v in results.items()} == pytest.approx(
            {"a": 0.1, "b": -0.2, "c": 0.0}
        )

    async def test_empty_batch_is_noop(self, power: PowerStore) -> None:
        """空批 no-op：不开事务、不校验分支（无写入 = 无副作用）。"""
        assert await power.apply_batch({}, tick=1) == {}

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    async def test_nan_and_inf_rejected_zero_write(
        self, power: PowerStore, session: AsyncSession, bad: float
    ) -> None:
        """NaN/Inf 拒（**必须显式查**：NaN 与任何值比较都返回 False）。"""
        with pytest.raises(PowerWriteError):
            await power.apply("chenmo", bad, tick=1)
        assert await _rows(session) == []

    async def test_tick_regression_rejected_zero_write(
        self, power: PowerStore, session: AsyncSession
    ) -> None:
        """tick 倒流拒：静默接受会让衰减算错且不可复现。"""
        await power.apply("chenmo", 0.1, tick=100)
        with pytest.raises(PowerWriteError, match="tick"):
            await power.apply("chenmo", 0.1, tick=99)
        session.expire_all()
        assert await _rows(session) == [(PARENT, "chenmo", pytest.approx(0.1), 100)]

    @pytest.mark.parametrize("bad_tick", [-1, "5", 1.0, True])
    async def test_bad_tick_rejected(self, power: PowerStore, bad_tick: object) -> None:
        """非 int / 负数 / bool tick 全拒（bool 是 int 的子类，必须显式排除）。"""
        with pytest.raises(PowerWriteError):
            await power.apply("chenmo", 0.1, tick=bad_tick)  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad_id", ["", None, 7])
    async def test_bad_npc_id_rejected(self, power: PowerStore, bad_id: object) -> None:
        """空串 / 非 str 的 npc_id 拒（空 id 会造出永不被决策层命中的幽灵行）。"""
        with pytest.raises(PowerWriteError):
            await power.apply(bad_id, 0.1, tick=1)  # type: ignore[arg-type]

    async def test_out_of_range_clamped_and_reported(self, power: PowerStore) -> None:
        """越界**夹取但如实上报** `clamped`（不抛，避免一次溢出打断整个 tick）。"""
        state = await power.apply("chenmo", 5.0, tick=1)
        assert state.power_level == pytest.approx(POWER_MAX)
        assert state.clamped is True, "夹取必须如实上报，调用方要能发现"
        below = await power.apply("other", -5.0, tick=1)
        assert below.power_level == pytest.approx(POWER_MIN)
        assert below.clamped is True

    async def test_in_range_write_reports_not_clamped(self, power: PowerStore) -> None:
        """正常写入 `clamped=False`（「没夹」也是事实，别让调用方猜）。"""
        assert (await power.apply("chenmo", 0.1, tick=1)).clamped is False

    async def test_batch_all_or_nothing(self, power: PowerStore, session: AsyncSession) -> None:
        """批内一条非法 ⇒ **全批零写**（不会出现「a 写了 b 没写」的半批）。"""
        with pytest.raises(PowerWriteError):
            await power.apply_batch({"a": 0.1, "b": float("nan")}, tick=1)
        assert await _rows(session) == []

    async def test_inactive_branch_rejected_zero_write(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """封存分支拒写（复用 `InactiveBranchError`：分叉后父线封存，禁污染）。"""
        session.add_all(
            [
                Branch(id=PARENT, status="active", is_current=True),
                Branch(id=ARCHIVE, status="abandoned", is_current=False),
            ]
        )
        await session.commit()
        with pytest.raises(InactiveBranchError):
            await PowerStore(store, branch_id=ARCHIVE).apply("chenmo", 0.1, tick=1)
        assert await _rows(session) == []

    async def test_unknown_branch_rejected_zero_write(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """分支不存在也拒（开线只走事件库闸门，权力写面不偷偷开线）。"""
        with pytest.raises(InactiveBranchError):
            await PowerStore(store, branch_id="ghost-line").apply("chenmo", 0.1, tick=1)
        assert await _rows(session) == []


@pytest.mark.t1
class TestPowerReadSurface:
    async def test_materialize_filters_and_omits_unknown(
        self, power: PowerStore, session: AsyncSession
    ) -> None:
        """未知 id 不在结果（调用方兜底 0，同 `NpcStore.materialize` 口径）。"""
        session.add_all(
            [
                NpcPower(branch_id=PARENT, npc_id="a", power_level=0.1),
                NpcPower(branch_id=PARENT, npc_id="b", power_level=0.2),
            ]
        )
        await session.commit()
        assert set(await power.materialize(["a", "ghost"])) == {"a"}
        assert set(await power.materialize([])) == set()
        assert set(await power.materialize()) == {"a", "b"}

    async def test_materialize_is_branch_isolated(
        self, power: PowerStore, session: AsyncSession
    ) -> None:
        """分支隔离：同 npc_id 跨分支两行，读面只回本分支（0008 纪律）。"""
        session.add_all(
            [
                NpcPower(branch_id=PARENT, npc_id="chenmo", power_level=0.4),
                NpcPower(branch_id=CHILD, npc_id="chenmo", power_level=-0.4),
            ]
        )
        await session.commit()
        assert (await power.materialize(["chenmo"]))["chenmo"].power_level == pytest.approx(0.4)

    async def test_materialize_is_pure_read(self, power: PowerStore, session: AsyncSession) -> None:
        """纯读：读两次不改任何行、也不推进 `updated_at_tick`（读不得变成写）。"""
        await power.apply("chenmo", 0.2, tick=3)
        before = await _rows(session)
        await power.materialize()
        await power.materialize(["chenmo"])
        session.expire_all()
        assert await _rows(session) == before

    async def test_returned_state_is_frozen(self, power: PowerStore) -> None:
        """返回 frozen dataclass（读面产物不可被就地改写 = 内存态不漂移）。"""
        await power.apply("chenmo", 0.2, tick=1)
        state = (await power.materialize(["chenmo"]))["chenmo"]
        with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError（运行时类型）
            state.power_level = 0.9  # type: ignore[misc]
        assert (await power.materialize(["chenmo"]))["chenmo"].power_level == pytest.approx(0.2)

    async def test_no_power_values_in_events(
        self, power: PowerStore, session: AsyncSession
    ) -> None:
        """**权力不落事件流**（红线 A 的执行形态）：写权力后 events 行集零变化。"""
        await power.apply_batch({"a": 0.5, "b": -0.5}, tick=4)
        count = (await session.execute(select(func.count()).select_from(Event))).scalar_one()
        assert count == 0, "权力写面产生了事件行（红线 A：事件 kind 集合必须零新增）"


# ---------------------------------------------------------------------------
# 4. 分叉克隆 + 禁面
# ---------------------------------------------------------------------------


async def _power_rows(session: AsyncSession, branch_id: str) -> list[tuple[str, float, int]]:
    """单分支读回（克隆逐位比对用；id 升序，结果确定可复现）。"""
    rows = (
        await session.execute(
            select(NpcPower.npc_id, NpcPower.power_level, NpcPower.updated_at_tick)
            .where(NpcPower.branch_id == branch_id)
            .order_by(NpcPower.npc_id)
        )
    ).all()
    return [(str(r[0]), float(r[1]), int(r[2])) for r in rows]


async def _noop_preflush() -> None:
    return None


@pytest.mark.t1
class TestForkClone:
    async def test_fork_clones_rows_byte_equal(
        self, power: PowerStore, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """克隆 = 父分支当前值逐字节（`INSERT…SELECT` 换 branch_id，零 id 重映射）。"""
        await power.apply_batch({"a": 0.3, "b": -0.7}, tick=8)
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=0,
            fork_tick=0,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        session.expire_all()
        assert await _power_rows(session, CHILD) == await _power_rows(session, PARENT)

    async def test_fork_leaves_parent_rows_untouched(
        self, power: PowerStore, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """C6：分叉只增不减——父分支的权力行不被改（那是那段时间线的历史事实）。"""
        await power.apply("a", 0.3, tick=8)
        before = await _power_rows(session, PARENT)
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=0,
            fork_tick=0,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        session.expire_all()
        assert await _power_rows(session, PARENT) == before

    async def test_child_writes_do_not_touch_parent(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """分叉后子分支各写各的（0012 闸门只锁开线，读档子线照写不误）。"""
        session.add(Branch(id=PARENT, status="active", is_current=True))
        await session.commit()
        parent_power = PowerStore(store, branch_id=PARENT)
        await parent_power.apply("a", 0.3, tick=8)
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=0,
            fork_tick=0,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        child_power = PowerStore(store, branch_id=CHILD)
        await child_power.apply("a", -0.9, tick=9)
        session.expire_all()
        # 子分支的基线 = 克隆来的父值 0.3，再叠加增量 -0.9 ⇒ -0.6（**继承 + 增量**都成立）
        assert await _power_rows(session, CHILD) == [("a", pytest.approx(-0.6), 9)]
        assert await _power_rows(session, PARENT) == [("a", pytest.approx(0.3), 8)]


class TestForbiddenSurface:
    def test_event_kinds_unchanged_by_batch_c(self) -> None:
        """红线 A：批次 C **零新增 kind**（codex 已把 kind 集合钉死）。"""
        kinds = {str(getattr(k, "value", k)) for k in PAYLOAD_MODELS}
        hits = sorted(AUTHORITY_FORBIDDEN_KEYS & {k.lower() for k in kinds})
        assert not hits, f"事件 kind 出现权力族：{hits}（D-10：PAYLOAD_MODELS 闭合集不得扩容）"
        assert "power.changed" not in kinds and "authority.changed" not in kinds

    def test_state_columns_are_forbidden_key_tripwires(self) -> None:
        """**命名即绊线**：状态列名落在 codex 禁键集内 ⇒ 意外出站即被扫红。

        这是反直觉但刻意的设计（D-10：权力永不出站）。若将来有人把 `power_level` 改成
        中性名（如 `level`），本钉转红 ⇒ 逼着先想清楚「这个值会不会被序列化出去」。
        """
        state_columns = {"power_level", "updated_at_tick"}
        tripwires = state_columns & AUTHORITY_FORBIDDEN_KEYS
        assert tripwires == {"power_level"}, (
            f"状态列的绊线名变了：{sorted(state_columns)} ∩ 禁键集 = {sorted(tripwires)}；"
            "改名前先确认该值永不出站（D-10），并同步 codex 禁键集"
        )

    def test_registered_as_fourth_unrebuildable_table(self) -> None:
        """登记钉：加了不可重建表却没登记 ⇒ A3 §3.2 的「语料一致」条件会说谎。"""
        a3 = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "data"
            / "m5-anchor-materialization-preplan.md"
        ).read_text(encoding="utf-8")
        assert "npc_power" in a3, "A3 地基分类未登记 npc_power（第 4 张不可重建表）"

    def test_preplan_and_schema_doc_exist(self) -> None:
        """设计稿与 schema 登记同在（数据面契约不许只活在代码里）。"""
        root = Path(__file__).resolve().parents[2] / "docs" / "data"
        assert (root / "m5-power-data-preplan.md").exists()
        assert "npc_power" in (root / "schema.md").read_text(encoding="utf-8")


def test_clamp_bounds_are_finite() -> None:
    """量纲常量本身必须是有限数（否则 CHECK 与夹取都失去意义）。"""
    assert math.isfinite(POWER_MIN) and math.isfinite(POWER_MAX)
    assert POWER_MIN < POWER_MAX


def test_mapping_keys_are_strings() -> None:
    """`apply_batch` 的入参类型约定（str → float）由签名表达；此处钉住读取侧的用法说明。

    故意写成「读一次签名」的钉：把 `Mapping[str, float]` 的键值约定显式留在测试里，
    免得将来有人传 `Mapping[int, float]`（会在运行期才炸）。
    """
    hints = PowerStore.apply_batch.__annotations__
    assert "Mapping[str, float]" in str(hints)
