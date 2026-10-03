"""M5-A5 T1 钉子 — 0012 `branches.is_current` + 开线闸收紧（R-4 数据面）

条款：`docs/data/m5-r4-active-branch-contract.md`（R-4.1 真源 / R-4.2.1 闸门 /
R-4.3 载体方案 A / R-4.4 fork 后的当前行归属）。触发缺陷 = codex S4 的 R-4：分支硬编码
`'main'`，分叉后记档指错世界线。

本文件钉住**数据面**四件事（fork.py 的当前行交接属 Claude 的 R-4 施工单，不在本刀）：

1. **载体**：部分唯一索引 ``ux_branches_current ON branches(is_current) WHERE
   is_current = 1`` ——「至多一个当前」由 **DB 层**保证（第二个 1 ⇒ IntegrityError），
   钉住它是**部分**索引（`WHERE` 子句真在 DDL 里；全列唯一会让两条 0 行互撞）；
2. **回填**（0010 同款判据：必要的、幂等、零行合法）：**唯一** active 置 1；**≥2 个
   active ⇒ 一行都不置**（**不 recency 兜底**——recency 会把「玩家在跑的线」换成
   「最近被分叉出去的线」，正是 R-4 要根治的病，且**静默错**）；
3. **开线闸**（R-4.2.1）：「不存在即开线」收紧为「**仅当无当前行**才可开线」；已有当前行
   时向别分支开线 ⇒ fail-closed，且**不留分支行、不吃 seq 号**。⚠️ 收紧只针对
   **开线**，不针对「写既有行」——读档子线（active 但 `is_current=0`）必须照写不误
   （R-4.4：多条读档线并存合法）；
4. **真源读入口**：`SqlEventStore.current_branch_id()` 查不到当前行 ⇒ 抛
   `NoCurrentBranchError`，**绝不回退 `'main'`**（哪怕库里真有一条名为 `main` 的行）。

⚠️ **二阶守卫纪律**：`test_backfill_ambiguous_*` 两钉留了 recency 对照组——把判据换成
「按 created_at 取最新」会红（0010 是 recency 回填，本迁移**故意不是**，两者不可混）。
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.fork import fork_from_anchor
from sim.core.persistence.models import Branch, Event
from sim.core.persistence.store import (
    CurrentBranchConflictError,
    InactiveBranchError,
    NoCurrentBranchError,
    SqlEventStore,
)

PARENT = "main"
CHILD = "fork-b"
GRAND = "fork-c"

#: SQLite 报「撞了哪条唯一约束」时给的是**列**而不是索引名（行式表的老行为）；
#: 索引名 + WHERE 子句另由 `test_partial_unique_index_ddl` 钉。
_UNIQUE_IS_CURRENT_MSG = "UNIQUE constraint failed: branches.is_current"

#: 与 0012 迁移逐字相同的回填语句（另有一条源码比对钉防漂移）。
BACKFILL_SQL = (
    "UPDATE branches SET is_current = 1 WHERE id = ("
    " SELECT id FROM branches WHERE status = 'active'"
    " AND (SELECT COUNT(*) FROM branches WHERE status = 'active') = 1)"
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


def _branch(branch_id: str, *, status: str = "active", is_current: bool = False, **kw: Any):
    return Branch(id=branch_id, status=status, is_current=is_current, **kw)


def _lod_event(tick: int, npc_id: str = "chenmo") -> dict:
    return {
        "tick": tick,
        "event_type": "npc.lod_change",
        "actor_id": npc_id,
        "target_id": None,
        "parent_seq": None,
        "payload": {"npc_id": npc_id, "from_lod": 1, "to_lod": 2, "reason": "enter_range"},
        "witnesses": [],
        "entropy_ref": None,
    }


async def _noop_preflush() -> None:
    return None


async def _run_backfill(session: AsyncSession) -> None:
    await session.execute(sa_text(BACKFILL_SQL))
    await session.commit()


async def _branch_row(session: AsyncSession, branch_id: str) -> Branch:
    """取分支行；不存在即**测试失败**（`session.get` 的 Optional 只会掩盖问题）。"""
    row = await session.get(Branch, branch_id)
    assert row is not None, f"分支行不存在: {branch_id}"
    return row


async def _flags(session: AsyncSession) -> list[tuple[str, str, bool]]:
    rows = (await session.execute(select(Branch.id, Branch.status, Branch.is_current))).all()
    return sorted((str(r[0]), str(r[1]), bool(r[2])) for r in rows)


# ---------------------------------------------------------------------------
# 1. 载体：列 + 部分唯一索引
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestCurrentCarrier:
    async def test_column_defaults_false(self, session: AsyncSession) -> None:
        """新分支行默认 `is_current=False`（既有行既不回填也不翻真）。"""
        session.add(_branch(PARENT))
        await session.commit()
        session.expire_all()
        assert (await _branch_row(session, PARENT)).is_current is False

    async def test_partial_unique_index_ddl(self, engine) -> None:
        """索引是**部分**唯一索引：`WHERE is_current = 1` 真在 DDL 里。

        钉住「部分」二字：全列唯一索引会让两条 `is_current=0` 的行互撞
        （读档子线并存就不可能了）。
        """
        async with engine.begin() as conn:
            rows = (
                await conn.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE type='index'"
                    " AND name='ux_branches_current'"
                )
            ).all()
        assert len(rows) == 1, "ux_branches_current 未被 create_all 建出"
        ddl = str(rows[0][0])
        assert "UNIQUE" in ddl.upper()
        assert "WHERE is_current = 1" in ddl, f"部分索引缺 WHERE 子句：{ddl}"

    async def test_second_current_row_integrity_error(self, session: AsyncSession) -> None:
        """DB 层不变量（R-4.7 #4）：第二个 `is_current=1` ⇒ IntegrityError。"""
        session.add(_branch("b1", is_current=True))
        await session.commit()
        session.add(_branch("b2", is_current=True))
        with pytest.raises(IntegrityError) as exc:
            await session.commit()
        await session.rollback()
        assert _UNIQUE_IS_CURRENT_MSG in str(exc.value), "撞的不是部分唯一索引（钉错了约束）"

    async def test_many_non_current_rows_allowed(self, session: AsyncSession) -> None:
        """多条 `is_current=0` 并存合法（R-4.4 读档子线并存）。"""
        session.add_all([_branch(f"b{i}") for i in range(5)])
        await session.commit()
        assert len(await _flags(session)) == 5

    async def test_switch_current_single_transaction(self, session: AsyncSession) -> None:
        """显式切换（R-4.5）：**同一事务**内清旧置新成功 —— 载体能承载交接。"""
        session.add_all([_branch("old", is_current=True), _branch("new")])
        await session.commit()

        await session.execute(update(Branch).where(Branch.id == "old").values(is_current=False))
        await session.execute(update(Branch).where(Branch.id == "new").values(is_current=True))
        await session.commit()
        session.expire_all()
        current = (
            (await session.execute(select(Branch.id).where(Branch.is_current.is_(True))))
            .scalars()
            .all()
        )
        assert list(current) == ["new"]

    async def test_switch_without_clearing_hits_index(self, session: AsyncSession) -> None:
        """不清旧就置新 ⇒ IntegrityError：head-fork 的当前行交接**必须同事务**。

        这是给 R-4 施工单的硬约束钉：`fork.py` 里「父封存 + 子置当前」若不在同一
        事务内先后执行，第二步直接撞唯一索引 ⇒ 整批回滚（宁可不分，不留两个当前）。
        """
        session.add_all([_branch("old", is_current=True), _branch("new")])
        await session.commit()

        with pytest.raises(IntegrityError) as exc:
            await session.execute(update(Branch).where(Branch.id == "new").values(is_current=True))
        await session.rollback()
        assert _UNIQUE_IS_CURRENT_MSG in str(exc.value), "撞的不是部分唯一索引（钉错了约束）"
        session.expire_all()
        assert (await _branch_row(session, "new")).is_current is False, "失败的交接把新分支置真了"


# ---------------------------------------------------------------------------
# 2. 回填判据（0010 同款：必要的 / 幂等 / 零行合法）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestCurrentBackfill:
    async def test_unique_active_marked(self, session: AsyncSession) -> None:
        """唯一 active ⇒ 它被置 1；abandoned 行保持 0。"""
        session.add_all(
            [
                _branch("live", is_current=False, created_at=100.0),
                _branch("dead", status="abandoned", created_at=200.0),
            ]
        )
        await session.commit()

        await _run_backfill(session)

        assert await _flags(session) == [("dead", "abandoned", False), ("live", "active", True)]

    async def test_no_active_zero_rows_legal(self, session: AsyncSession) -> None:
        """0 个 active ⇒ 零行更新是合法态（空库 / 全封存），不炸。"""
        await _run_backfill(session)
        assert await _flags(session) == []
        session.add(_branch("dead", status="abandoned", created_at=9.0))
        await session.commit()
        await _run_backfill(session)
        assert await _flags(session) == [("dead", "abandoned", False)]

    async def test_two_active_marks_none(self, session: AsyncSession) -> None:
        """**≥2 个 active ⇒ 一行都不置**（世界线状态歧义 ⇒ fail-closed）。"""
        session.add_all([_branch("a1", created_at=100.0), _branch("a2", created_at=200.0)])
        await session.commit()

        await _run_backfill(session)

        assert await _flags(session) == [
            ("a1", "active", False),
            ("a2", "active", False),
        ], "歧义库被 recency 兜底选了一个（静默换线 = R-4 的病）"

    async def test_ambiguous_beats_recency_control_group(self, session: AsyncSession) -> None:
        """二阶守卫：对照组 = 0010 的 recency 口径，**两条都被钉**。

        两条 active、时间戳相差 100 秒（recency 必选 `a2`）⇒ 回填判据仍全 0。
        哪天有人把判据抄成 recency，本钉子转红。
        """
        session.add_all([_branch("a1", created_at=100.0), _branch("a2", created_at=200.0)])
        await session.commit()

        await _run_backfill(session)
        recency_pick = (
            await session.execute(
                sa_text("SELECT id FROM branches ORDER BY created_at DESC LIMIT 1")
            )
        ).scalar_one()
        assert str(recency_pick) == "a2", "对照组前提失效（时间戳没拉开）"
        assert all(flag is False for _id, _s, flag in await _flags(session)), (
            "判据被 recency 污染：歧义库必须全 0，让调用方报「世界线状态歧义」"
        )

    async def test_idempotent(self, session: AsyncSession) -> None:
        """幂等：重跑三次仍恰一行 1（0010 同款纪律）。"""
        session.add_all([_branch("live"), _branch("dead", status="abandoned")])
        await session.commit()

        await _run_backfill(session)
        await _run_backfill(session)
        await _run_backfill(session)

        assert await _flags(session) == [("dead", "abandoned", False), ("live", "active", True)]

    async def test_preserves_other_columns(self, session: AsyncSession) -> None:
        """只动当前位：id/status/谱系/rng_state/时间戳逐项不变。"""
        session.add(
            _branch(
                "live",
                forked_from_branch="root",
                forked_from_seq=7,
                rng_state="{}",
                created_at=123.0,
            )
        )
        await session.commit()
        before = await _branch_row(session, "live")
        snapshot = (
            before.forked_from_branch,
            before.forked_from_seq,
            before.rng_state,
            before.status,
            before.created_at,
        )

        await _run_backfill(session)
        session.expire_all()
        after = await _branch_row(session, "live")
        assert after.is_current is True
        assert (
            after.forked_from_branch,
            after.forked_from_seq,
            after.rng_state,
            after.status,
            after.created_at,
        ) == snapshot


# ---------------------------------------------------------------------------
# 3. 开线闸收紧（R-4.2.1）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestOpenLineGate:
    async def test_zero_current_opens_line_as_current(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """正例：库中无当前行 ⇒ 开线成功，且新行就是当前行。"""
        await store.append(PARENT, [_lod_event(tick=1)])

        assert await _flags(session) == [(PARENT, "active", True)]
        assert await store.current_branch_id() == PARENT

    async def test_second_line_rejected_when_current_exists(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """负例：已有当前行时向别分支开线 ⇒ fail-closed（R-4.2.1）。"""
        await store.append(PARENT, [_lod_event(tick=1)])

        with pytest.raises(CurrentBranchConflictError):
            await store.append("brand-new", [_lod_event(tick=1)])

    async def test_conflict_is_inactive_branch_error_subclass(self) -> None:
        """闸门只有一个出口：冲突异常是 `InactiveBranchError` 子类（既有 handler 不用改）。"""
        assert issubclass(CurrentBranchConflictError, InactiveBranchError)

    async def test_rejected_open_line_leaves_no_trace(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """被拒的开线不留半写（C6）：既无分支行，也无事件行。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        before = (await session.execute(select(Event.branch_id, Event.seq))).all()

        with pytest.raises(CurrentBranchConflictError):
            await store.append("brand-new", [_lod_event(tick=1)])

        session.expire_all()
        assert await session.get(Branch, "brand-new") is None, "被拒的开线留了分支行"
        assert (await session.execute(select(Event.branch_id, Event.seq))).all() == before

    async def test_open_line_allowed_after_current_cleared(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """显式切换（R-4.5）后原当前被清 0 ⇒ 可以开新线（闸门只认「有无当前行」）。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        await session.execute(update(Branch).where(Branch.id == PARENT).values(is_current=False))
        await session.commit()

        await store.append("world-2", [_lod_event(tick=1)])

        assert await store.current_branch_id() == "world-2"
        assert await _flags(session) == [(PARENT, "active", False), ("world-2", "active", True)]

    async def test_append_to_current_active_still_works(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """放行路径零回归：当前 active 分支继续可写，seq 连号。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        await store.append(PARENT, [_lod_event(tick=2)])

        seqs = (
            (await session.execute(select(Event.seq).where(Event.branch_id == PARENT)))
            .scalars()
            .all()
        )
        assert list(seqs) == [1, 2]

    async def test_append_to_active_non_current_allowed(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """读档子线（active 但 `is_current=0`）**照写不误**（R-4.4：并存合法）。

        反向钉：若把闸门误收紧成「非当前即不可写」，历史点读档线会被写死。
        """
        session.add_all([_branch(PARENT, is_current=True), _branch("archive-line")])
        await session.commit()

        await store.append("archive-line", [_lod_event(tick=1)])

        seqs = (
            (await session.execute(select(Event.seq).where(Event.branch_id == "archive-line")))
            .scalars()
            .all()
        )
        assert list(seqs) == [1]
        assert await store.current_branch_id() == PARENT, "读档线的写入不该动当前行"

    async def test_append_to_abandoned_still_rejected(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """裁 5 原语义零回归：非 active 分支仍被拒（当前分支是哪条不影响它）。"""
        session.add_all([_branch(PARENT, is_current=True), _branch("dead", status="abandoned")])
        await session.commit()

        with pytest.raises(InactiveBranchError):
            await store.append("dead", [_lod_event(tick=1)])


# ---------------------------------------------------------------------------
# 4. 真源读入口（R-4.1：fail-closed，禁 'main' 兜底）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestCurrentReadSource:
    async def test_returns_the_is_current_row(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        session.add_all([_branch("no"), _branch("yes", is_current=True)])
        await session.commit()
        assert await store.current_branch_id() == "yes"

    async def test_raises_when_zero_current(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """零当前行 ⇒ 抛 `NoCurrentBranchError`（不返回 None，让调用方无从忽略）。"""
        session.add_all([_branch("a"), _branch("b")])
        await session.commit()
        with pytest.raises(NoCurrentBranchError):
            await store.current_branch_id()

    async def test_never_falls_back_to_main(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """库里**有一条**名为 `main` 的行（但非当前）⇒ 仍然报错。

        R-4.1 的病根就是「回退 `'main'`」。这条钉子让任何 `or 'main'` /
        `DEFAULT_BRANCH_ID` 兜底立刻变红。
        """
        session.add(_branch(PARENT, is_current=False))
        await session.commit()
        with pytest.raises(NoCurrentBranchError):
            await store.current_branch_id()

    async def test_ambiguous_active_rows_do_not_pick_by_recency(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """两条 active 都 `is_current=0`（回填后的歧义库）⇒ 报错，不按 created_at 选。"""
        session.add_all([_branch("a1", created_at=100.0), _branch("a2", created_at=200.0)])
        await session.commit()
        with pytest.raises(NoCurrentBranchError):
            await store.current_branch_id()


# ---------------------------------------------------------------------------
# 5. fork 后的当前行归属（R-4.4，**数据面**：fork.py 交接归施工单）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestForkCurrentOwnership:
    async def test_head_fork_keeps_at_most_one_current(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """head-fork 后「至多一个当前」仍成立（DB 层保证，与 fork 实现无关）。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        current = (
            await session.execute(
                select(func.count()).select_from(Branch).where(Branch.is_current.is_(True))
            )
        ).scalar_one()
        assert current <= 1, "fork 之后出现两个当前世界线"

    async def test_head_fork_parent_sealed_child_writable(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """head-fork 的数据面归属：父封存（拒写）+ 子 active（可写）。

        R-4 交接落地（fork.py 施工，2026-10-03）：head-fork 交接当前行给子——
        子 `is_current=1` + 父 `abandoned`（K9 §1.6 R-4.4 目标态；原断言
        「父 True/子 False」是交接前现状，随施工更新）。
        """
        await store.append(PARENT, [_lod_event(tick=1)])
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )

        with pytest.raises(InactiveBranchError):
            await store.append(PARENT, [_lod_event(tick=2)])
        await store.append(CHILD, [_lod_event(tick=2)])
        session.expire_all()
        assert await _flags(session) == [
            (CHILD, "active", True),
            (PARENT, "abandoned", False),
        ], "fork 后父子归属/当前位与 R-4.4 交接后语义不符（子当前 + 父 abandoned）"

    async def test_anchor_fork_parent_keeps_current_child_coexists(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """anchor-fork 的数据面归属：**父保持当前**，子线并存且可写（R-4.4）。

        模拟形态（历史点读档线由施工单/fork 单造）：父行仍 active + `is_current=1`，
        子行 active + `is_current=0`。当前行不动、子线可写 ⇒ 与 head-fork 的
        「移交」语义区分得开。
        """
        await store.append(PARENT, [_lod_event(tick=1)])
        session.add(_branch(GRAND))
        await session.commit()

        await store.append(GRAND, [_lod_event(tick=1)])

        assert await store.current_branch_id() == PARENT, "读档子线抢走了当前行"
        assert await _flags(session) == [
            (GRAND, "active", False),
            (PARENT, "active", True),
        ]

    async def test_handover_pattern_parent_clear_then_child_set(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """head-fork 交接的**载体可用**：同事务「父清 0 → 子置 1」后当前行即子分支。

        施工单（`fork.py`）按这个形态落即可；本钉证明载体 + 唯一索引支持它。
        """
        await store.append(PARENT, [_lod_event(tick=1)])
        session.add(_branch(CHILD))
        await session.commit()

        await session.execute(update(Branch).where(Branch.id == PARENT).values(is_current=False))
        await session.execute(update(Branch).where(Branch.id == CHILD).values(is_current=True))
        await session.commit()

        assert await store.current_branch_id() == CHILD


# ---------------------------------------------------------------------------
# 6. 迁移往返（scratch DB + 全 revision id；**绝不**用仓根 world.db）
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


def _insert_branch(db: Path, rows: list[tuple[str, str, float]]) -> None:
    conn = sqlite3.connect(str(db))
    try:
        for branch_id, status, created_at in rows:
            conn.execute(
                "INSERT INTO branches (id, status, created_at) VALUES (?, ?, ?)",
                (branch_id, status, created_at),
            )
        conn.commit()
    finally:
        conn.close()


def _select_current(db: Path) -> list[tuple[str, int]]:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT id, is_current FROM branches ORDER BY id").fetchall()
    finally:
        conn.close()


class TestAlembic0012:
    def test_upgrade_backfills_unique_active(self, tmp_path: Path) -> None:
        """真跑一遍：0011 态的既有库 upgrade 到 0012，唯一 active 被置 1。"""
        assert _alembic(tmp_path, "upgrade", "0011_anchor_packages").returncode == 0
        _insert_branch(
            tmp_path / "mig.db",
            [("live", "active", 100.0), ("dead", "abandoned", 200.0)],
        )

        assert _alembic(tmp_path, "upgrade", "0012_branches_current").returncode == 0
        assert _select_current(tmp_path / "mig.db") == [("dead", 0), ("live", 1)]

    def test_upgrade_on_empty_branches_table(self, tmp_path: Path) -> None:
        """空分支表升级不炸（零行更新是合法态）。"""
        assert _alembic(tmp_path, "upgrade", "0012_branches_current").returncode == 0
        assert _select_current(tmp_path / "mig.db") == []

    def test_upgrade_ambiguous_marks_none(self, tmp_path: Path) -> None:
        """歧义库（2 active）升级后全 0 —— 迁移里也没有 recency 兜底。"""
        assert _alembic(tmp_path, "upgrade", "0011_anchor_packages").returncode == 0
        _insert_branch(
            tmp_path / "mig.db",
            [("a1", "active", 100.0), ("a2", "active", 200.0)],
        )

        assert _alembic(tmp_path, "upgrade", "0012_branches_current").returncode == 0
        assert _select_current(tmp_path / "mig.db") == [("a1", 0), ("a2", 0)]

    def test_round_trip_0011_0012(self, tmp_path: Path) -> None:
        """0011 ↔ 0012 逐级往返：回填结果保持、升级幂等（回填不撤销，同 0010）。"""
        assert _alembic(tmp_path, "upgrade", "0011_anchor_packages").returncode == 0
        _insert_branch(
            tmp_path / "mig.db",
            [("live", "active", 100.0), ("dead", "abandoned", 200.0)],
        )

        assert _alembic(tmp_path, "upgrade", "0012_branches_current").returncode == 0
        assert _alembic(tmp_path, "downgrade", "0011_anchor_packages").returncode == 0
        assert _alembic(tmp_path, "upgrade", "0012_branches_current").returncode == 0

        assert _select_current(tmp_path / "mig.db") == [("dead", 0), ("live", 1)]
        conn = sqlite3.connect(str(tmp_path / "mig.db"))
        try:
            version = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        finally:
            conn.close()
        assert version == [("0012_branches_current",)]

    def test_downgrade_drops_column_and_index(self, tmp_path: Path) -> None:
        """downgrade 结构性回退：列与部分索引都没了（往返不留残骸）。"""
        assert _alembic(tmp_path, "upgrade", "0012_branches_current").returncode == 0
        assert _alembic(tmp_path, "downgrade", "0011_anchor_packages").returncode == 0

        conn = sqlite3.connect(str(tmp_path / "mig.db"))
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(branches)")}
            idx = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='index'"
                " AND name='ux_branches_current'"
            ).fetchone()
        finally:
            conn.close()
        assert "is_current" not in cols
        assert idx[0] == 0

    def test_upgrade_is_repeatable(self, tmp_path: Path) -> None:
        """重复 upgrade 不炸（幂等）。"""
        assert _alembic(tmp_path, "upgrade", "0012_branches_current").returncode == 0
        assert _alembic(tmp_path, "upgrade", "0012_branches_current").returncode == 0


# ---------------------------------------------------------------------------
# helpers / 纪律
# ---------------------------------------------------------------------------


def test_backfill_statement_matches_migration_source() -> None:
    """钉住「测试跑的语句 == 迁移源码里的语句」（versions 目录不是包，按源码比对）。"""
    src = (
        Path(__file__).resolve().parents[1]
        / "core"
        / "persistence"
        / "alembic"
        / "versions"
        / "0012_branches_current.py"
    ).read_text(encoding="utf-8")

    def _norm(text: str) -> str:
        return " ".join(text.replace('"', "").split())

    assert _norm(BACKFILL_SQL) in _norm(src), "0012 迁移里的回填语句与钉子不一致"


def test_partial_index_where_matches_migration_source() -> None:
    """索引名与 WHERE 子句同样逐字比对，防「模型/迁移/钉子」三处漂移。"""
    src = (
        Path(__file__).resolve().parents[1]
        / "core"
        / "persistence"
        / "alembic"
        / "versions"
        / "0012_branches_current.py"
    ).read_text(encoding="utf-8")
    assert '"ux_branches_current"' in src
    assert 'CURRENT_INDEX_WHERE = "is_current = 1"' in src
    # 0012 必须接在 0011 之后（revision 链不许分叉）
    assert 'down_revision: str | None = "0011_anchor_packages"' in src
    assert 'revision: str = "0012_branches_current"' in src
