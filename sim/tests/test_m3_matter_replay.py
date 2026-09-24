"""M3-C2 — 物质账本重放路径 + 两入口逐位相等校验（§19.3）。

§19.3 一致性判据：**快照路径**（`NpcStore.materialize_matter` 直读 `matter_state`）
与**重放路径**（`NpcStore.materialize_matter_replay` 折叠 `events` 表内 `matter.*`）
必须产出**逐位相等**的 `MatterLedger`——同一折叠规则（`fold_matter_snapshot`，与
`_project_matter` 同源），防两套语义分叉。

覆盖：全量重放逐位相等 / 含 COLLAPSE 终态 / decay_rate 携带（§17.2 方案 A）/
id 过滤（未知 id 不在结果）/ 分支隔离 / 重放纯读（不落 matter_state）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import EventKind, matter_event
from sim.core.persistence.database import init_database
from sim.core.persistence.models import MatterState
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


def _ledger_state(ledger) -> dict[str, tuple[float, float, bool]]:
    """归一化为可比对的纯元组映射（逐位相等用）。"""
    return {
        mid: (snap.integrity, snap.decay_rate, snap.is_rubble)
        for mid, snap in ledger._items.items()
    }


class TestMatterReplayTwoEntry:
    async def test_replay_bit_equal_to_snapshot(self, store) -> None:
        """§19.3 主判据：多事件序列后，两入口逐位相等。"""
        ns = NpcStore(store)
        await ns.flush_tick(
            [matter_event(1, EventKind.MATTER_BUILD, "wall-1", durability=0.9, decay_rate=0.02)]
        )
        await ns.flush_tick(
            [
                matter_event(
                    2,
                    EventKind.MATTER_DECAY,
                    "wall-1",
                    amount=-0.02,
                    durability=0.88,
                    decay_rate=0.02,
                )
            ]
        )
        await ns.flush_tick(
            [matter_event(3, EventKind.MATTER_DAMAGE, "wall-1", amount=-0.5, durability=0.38)]
        )
        await ns.flush_tick(
            [matter_event(4, EventKind.MATTER_BUILD, "wall-2", durability=0.5, decay_rate=0.01)]
        )

        snapshot = await ns.materialize_matter()
        replay = await ns.materialize_matter_replay()

        assert _ledger_state(snapshot) == _ledger_state(replay)
        # 值也对（非只形状相等）
        assert replay.state("wall-1").integrity == 0.38
        assert replay.state("wall-1").decay_rate == 0.02
        assert replay.state("wall-2").integrity == 0.5

    async def test_replay_bit_equal_with_collapse_terminal(self, store) -> None:
        """COLLAPSE 终态（rubble 不可逆）两入口逐位相等。"""
        ns = NpcStore(store)
        await ns.flush_tick(
            [matter_event(1, EventKind.MATTER_BUILD, "tower", durability=0.3, decay_rate=0.05)]
        )
        await ns.flush_tick(
            [matter_event(2, EventKind.MATTER_COLLAPSE, "tower", amount=-0.3, durability=0.0)]
        )

        snapshot = await ns.materialize_matter()
        replay = await ns.materialize_matter_replay()

        assert _ledger_state(snapshot) == _ledger_state(replay)
        assert replay.state("tower").is_rubble is True
        assert replay.state("tower").integrity == 0.0

    async def test_replay_decay_rate_carrying_matches(self, store) -> None:
        """§17.2 方案 A：DECAY 事件携带账本静态率 → 两入口同率（重放保真）。"""
        ns = NpcStore(store)
        await ns.flush_tick(
            [matter_event(1, EventKind.MATTER_BUILD, "hut", durability=0.7, decay_rate=0.03)]
        )
        await ns.flush_tick(
            [
                matter_event(
                    2,
                    EventKind.MATTER_DECAY,
                    "hut",
                    amount=-0.03,
                    durability=0.67,
                    decay_rate=0.03,
                )
            ]
        )

        snapshot = await ns.materialize_matter()
        replay = await ns.materialize_matter_replay()

        assert _ledger_state(snapshot) == _ledger_state(replay)
        assert replay.state("hut").decay_rate == 0.03

    async def test_replay_filters_unknown_ids(self, store) -> None:
        """`materialize_matter_replay(ids)`：未知 id 不在结果（与快照路径同口径）。"""
        ns = NpcStore(store)
        await ns.flush_tick([matter_event(1, EventKind.MATTER_BUILD, "wall-1", durability=0.6)])

        assert set((await ns.materialize_matter_replay(["wall-1", "ghost"]))._items) == {"wall-1"}
        assert (await ns.materialize_matter_replay([]))._items == {}

    async def test_replay_branch_isolated(self, store) -> None:
        """分支隔离：重放只看本分支 events（R4 纪律）。"""
        ns_main = NpcStore(store, branch_id="main")
        ns_b = NpcStore(store, branch_id="branch-b")
        await ns_main.flush_tick(
            [matter_event(1, EventKind.MATTER_BUILD, "w-main", durability=0.7)]
        )
        await ns_b.flush_tick([matter_event(1, EventKind.MATTER_BUILD, "w-b", durability=0.3)])

        assert set((await ns_main.materialize_matter_replay())._items) == {"w-main"}
        assert set((await ns_b.materialize_matter_replay())._items) == {"w-b"}

    async def test_replay_is_pure_read(self, store, engine) -> None:
        """重放纯读：不写 matter_state（C4 唯一写路径不变）。"""
        ns = NpcStore(store)
        await ns.flush_tick([matter_event(1, EventKind.MATTER_BUILD, "wall-1", durability=0.6)])

        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as s:
            before = (await s.execute(select(MatterState))).scalars().all()

        await ns.materialize_matter_replay()
        await ns.materialize_matter_replay()

        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as s:
            after = (await s.execute(select(MatterState))).scalars().all()
        assert len(before) == len(after) == 1
