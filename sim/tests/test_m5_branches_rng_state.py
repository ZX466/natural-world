"""M5-A-DATA T1 钉子 — 0009 `branches.rng_state` + fork 事务内原子落库（裁 27-B b2）

**为什么落这一列**（D3-c §6.3 实测，裁 27-B 采 b2）：分叉点两侧的随机流必须**承接抽签
进度**，否则接缝处行为跳变（T2 破）。`RngRegistry` 只记 `world_seed` + 熵材料，**抽签进度
活在调用方持有的 PCG64 生成器里** ⇒ 存一个 seed **不足**（实测「只承接 registry」后续抽签
必然跳变），必须承接**可序列化状态包**（≈198 B/流，`sim/core/rng_state.py`）。

**为什么落在 `branches.rng_state` 而不是快照**（b2 > b1）：
- 分支**自带**状态 ⇒ **可连续分叉链**（child 的状态可作为 grandchild 的输入，逐级承接）；
- 落库在 **fork 事务内** ⇒ 与克隆同生共死（要么都成，要么都回滚，无半写）；
- b1（写进子分支第一份快照）零 schema，但状态只存在于那一份快照——连续分叉时**祖父分支
  状态无处可取**，且快照内容契约要加键。

**NULL 的语义**：`NULL` = 该分支**没有承接过**随机状态（根分支、或调用方未提供）⇒ 读档
后随机流从头开始。**这必须被看见**：`fork_from_anchor` 在未收到 `rng_state` 时发
warning（漏传 = 接缝跳变风险，是调用方的 bug 不是存储的 bug）。
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.fork import ForkError, fork_from_anchor
from sim.core.persistence.models import Branch, Event, NpcMemory
from sim.core.persistence.store import SqlEventStore
from sim.core.rng import RngRegistry
from sim.core.rng_state import capture_rng_state, restore_rng_state

PARENT = "main"
CHILD = "fork-b"
GRANDCHILD = "fork-c"
STREAMS = ("world.weather", "combat.critical", "npc.decide")


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


async def _noop_preflush() -> None:
    return None


def _lod(tick: int) -> dict:
    return {
        "tick": tick,
        "event_type": "npc.lod_change",
        "actor_id": "chenmo",
        "target_id": None,
        "parent_seq": None,
        "payload": {"npc_id": "chenmo", "from_lod": 1, "to_lod": 2, "reason": "enter_range"},
        "witnesses": [],
        "entropy_ref": None,
    }


def _seeded_state(world_seed: int = 7, draws: int = 11) -> tuple[RngRegistry, dict, str]:
    reg = RngRegistry(world_seed=world_seed)
    cache: dict[str, np.random.Generator] = {}
    for name in STREAMS:
        reg.generator(name, cache).random(draws)
    return reg, cache, capture_rng_state(reg, cache, STREAMS)


# ---------------------------------------------------------------------------
# 1. schema 形状
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestBranchesRngStateSchema:
    def test_column_exists_and_nullable(self) -> None:
        col = cast("type[Branch]", Branch).__table__.columns["rng_state"]
        assert col.nullable, "rng_state 必须可空（NULL = 未承接状态）"
        assert str(col.type).upper() in {"TEXT", "VARCHAR"}

    def test_migration_0009_round_trip(self, tmp_path: Path) -> None:
        """0008 <-> 0009 往返（**全 revision id** + scratch DB，绝不用仓内 world.db）。"""
        env = {"WORLD_DB_URL": f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}"}
        run = lambda *args: subprocess.run(  # noqa: E731
            [sys.executable, "-m", "alembic", *args],
            cwd=str(Path(__file__).resolve().parents[2]),
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=False,
        )
        db = tmp_path / "mig.db"

        up = run("upgrade", "head")
        assert up.returncode == 0, up.stderr
        conn = sqlite3.connect(str(db))
        try:
            assert "rng_state" in {r[1] for r in conn.execute("PRAGMA table_info(branches)")}
        finally:
            conn.close()

        down = run("downgrade", "0008_m5_fork_identity")
        assert down.returncode == 0, down.stderr
        conn = sqlite3.connect(str(db))
        try:
            assert "rng_state" not in {r[1] for r in conn.execute("PRAGMA table_info(branches)")}
            # 列消失但既有行与分支身份不受影响
            assert conn.execute("SELECT COUNT(*) FROM branches").fetchone()[0] == 0
        finally:
            conn.close()

        up2 = run("upgrade", "head")
        assert up2.returncode == 0, up2.stderr
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(branches)")}
        finally:
            conn.close()
        assert {"id", "forked_from_branch", "forked_from_seq", "status", "rng_state"} <= cols


# ---------------------------------------------------------------------------
# 2. fork 事务内原子落库
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestForkPersistsRngState:
    async def test_state_written_into_child_branch_row(
        self, store, session: AsyncSession
    ) -> None:
        await store.append(PARENT, [_lod(1), _lod(2)])
        _reg, _cache, blob = _seeded_state()

        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=2,
            fork_tick=2,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
            rng_state=blob,
        )
        assert result.rng_state_persisted is True

        session.expire_all()
        child = await session.get(Branch, CHILD)
        parent = await session.get(Branch, PARENT)
        assert child is not None and child.rng_state == blob
        assert parent is not None and parent.rng_state is None, "父分支状态被改写"

    async def test_missing_state_reports_warning_and_null(
        self, store, session: AsyncSession
    ) -> None:
        """未提供 rng_state → 列留 NULL + 明确 warning（漏传是调用方的 bug，须被看见）。"""
        await store.append(PARENT, [_lod(1), _lod(2)])
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=2,
            fork_tick=2,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        assert result.rng_state is None
        assert result.rng_state_persisted is False
        assert any("rng_state" in w for w in result.warnings), result.warnings
        session.expire_all()
        child = await session.get(Branch, CHILD)
        assert child is not None and child.rng_state is None

    async def test_rollback_leaves_no_half_written_state(
        self, store, session: AsyncSession
    ) -> None:
        """指针悬空 → ForkError 整批回滚：子分支行**与** rng_state 一起消失（原子性）。"""
        from sim.core.persistence.models import Knowledge

        await store.append(PARENT, [_lod(1), _lod(2)])
        session.add(
            Knowledge(
                holder_id="x",
                fact="teller 不存在",
                confidence=0.4,
                source="told",
                learned_at=0,
                branch_id=PARENT,
                source_knowledge_id=9999,
            )
        )
        await session.commit()
        _reg, _cache, blob = _seeded_state()

        with pytest.raises(ForkError, match="source_knowledge_id"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=2,
                fork_tick=2,
                new_branch_id=CHILD,
                preflush=_noop_preflush,
                rng_state=blob,
            )
        assert await session.get(Branch, CHILD) is None, "回滚后仍留了子分支行"

    async def test_continuous_fork_chain_carries_state(
        self, store, session: AsyncSession
    ) -> None:
        """连续分叉：子分支的状态可作为下一次 fork 的输入（b2 的核心好处）。"""
        await store.append(PARENT, [_lod(1), _lod(2)])
        _reg, _cache, blob = _seeded_state()
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=2,
            fork_tick=2,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
            rng_state=blob,
        )

        # 子分支推进后（事件 + 抽签都动过）再分叉
        await store.append(CHILD, [_lod(3)])
        session.expire_all()
        child_row = await session.get(Branch, CHILD)
        assert child_row is not None
        cache2: dict[str, np.random.Generator] = {}
        reg2 = restore_rng_state(cast(str, child_row.rng_state), cache2, STREAMS)
        for name in STREAMS:
            cache2[reg2.draw_key(name)].random(3)
        blob2 = capture_rng_state(reg2, cache2, STREAMS)

        # 子分支的 seq **从 1 重新开始**（事件不克隆）⇒ 它的头部是 (fork-b, 1)
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=CHILD,
            fork_seq=1,
            fork_tick=3,
            new_branch_id=GRANDCHILD,
            preflush=_noop_preflush,
            rng_state=blob2,
        )
        session.expire_all()
        gc = await session.get(Branch, GRANDCHILD)
        assert gc is not None and gc.rng_state == blob2
        assert gc.forked_from_branch == CHILD

    async def test_end_to_end_seam_continuity(self, store, session: AsyncSession) -> None:
        """端到端：父分支抽签 → fork 落库 → 从子分支行读回 → 后续抽签与父分支续跑逐位一致。"""
        await store.append(PARENT, [_lod(1), _lod(2)])
        reg, cache, blob = _seeded_state()
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=2,
            fork_tick=2,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
            rng_state=blob,
        )

        session.expire_all()
        child_row = await session.get(Branch, CHILD)
        assert child_row is not None
        child_cache: dict[str, np.random.Generator] = {}
        child_reg = restore_rng_state(cast(str, child_row.rng_state), child_cache, STREAMS)

        for name in STREAMS:
            assert np.array_equal(
                cache[reg.draw_key(name)].random(16),
                child_cache[child_reg.draw_key(name)].random(16),
            ), f"流 {name} 在读档接缝处跳变（T2 红线）"


# ---------------------------------------------------------------------------
# 3. 不碰的表（回归守卫）
# ---------------------------------------------------------------------------


@pytest.mark.t1
async def test_fork_still_touches_no_events_or_memories(
    store, session: AsyncSession
) -> None:
    """0009 只加一列：事件与语料仍零改动（裁 6 (c) / C6 口径不变）。"""
    await store.append(PARENT, [_lod(1), _lod(2)])
    session.add(
        NpcMemory(
            entry_id="e-1",
            npc_id="chenmo",
            branch_id=PARENT,
            content="主线记忆",
            source="event",
            importance=0.5,
            created_at_tick=0,
            event_seq=1,
        )
    )
    await session.commit()
    before_events = ((await session.execute(select(Event.branch_id, Event.seq))).all())
    before_mem = (
        (
            await session.execute(
                select(NpcMemory.entry_id).where(NpcMemory.branch_id == PARENT)
            )
        )
        .scalars()
        .all()
    )

    _reg, _cache, blob = _seeded_state()
    await fork_from_anchor(
        store.session_factory,
        parent_branch_id=PARENT,
        fork_seq=2,
        fork_tick=2,
        new_branch_id=CHILD,
        preflush=_noop_preflush,
        rng_state=blob,
    )
    after_events = ((await session.execute(select(Event.branch_id, Event.seq))).all())
    after_parent_mem = (
        (
            await session.execute(
                select(NpcMemory.entry_id).where(NpcMemory.branch_id == PARENT)
            )
        )
        .scalars()
        .all()
    )
    assert sorted(after_events) == sorted(before_events)
    # 父分支的语料行逐条不变（克隆只往子分支加，且 entry_id 已重映射）
    assert sorted(after_parent_mem) == sorted(before_mem)
