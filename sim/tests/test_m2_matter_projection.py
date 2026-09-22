"""M2-D4 数据层对账 — MatterLedger ↔ MatterPayload ↔ matter_state 三方一致性。

判据（docs/data/schema.md §14/§17）：`matter_state` = 事件流的持久化投影，
「快照 + 事件重放可**逐位重建**」。本文件端到端驱动账本 → 产事件 → flush 投影，
逐列核对三方一致性，把当前契约锁进测试。

覆盖：
- integrity：ledger.integrity ↔ payload.durability ↔ matter_state.integrity
  （decay/damage/build/collapse）；
- is_rubble：ledger 终态 ↔ matter_state.is_rubble。
- decay_rate：**已知缺口**（§17.2）——当前投影不承载账本静态率（占位测试，待裁决）。

与 test_m2_matter.py（结算语义）/ test_m2_runtime_store.py（投影机制）互补：
本文件只做**三方对账**，不重复各自单元语义。
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import EventKind
from sim.core.persistence.database import init_database
from sim.core.persistence.models import MatterState
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore
from sim.world.matter import MatterLedger


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
class TestIntegrityTripleConsistency:
    """integrity ↔ payload.durability ↔ matter_state.integrity 三方一致。"""

    async def test_decay_integrity_roundtrip(self, store, session: AsyncSession) -> None:
        ledger = MatterLedger()
        ledger.register("food-1", integrity=1.0, decay_rate=0.1)
        events = ledger.settle(tick=100, seed=0)
        ns = NpcStore(store)
        await ns.flush_tick(events)

        row = await session.get(MatterState, "food-1")
        assert row is not None
        # 三方：账本 = payload.durability = 投影列（投影 clip(0,1) 不改变 0..1 值）
        snap = ledger.state("food-1")
        assert events[0].payload["durability"] == pytest.approx(snap.integrity)
        assert row.integrity == pytest.approx(snap.integrity)

    async def test_build_then_damage_integrity(self, store, session: AsyncSession) -> None:
        ledger = MatterLedger()
        ledger.register("wall-1", integrity=1.0, decay_rate=0.0)
        ns = NpcStore(store)
        await ns.flush_tick([ledger.build("wall-1", amount=0.0, tick=1)])
        dmg = ledger.damage("wall-1", amount=-0.35, tick=2)
        await ns.flush_tick([dmg])

        row = await session.get(MatterState, "wall-1")
        assert row is not None
        snap = ledger.state("wall-1")
        assert dmg.payload["durability"] == pytest.approx(snap.integrity)
        assert row.integrity == pytest.approx(0.65)

    async def test_collapse_integrity_zero(self, store, session: AsyncSession) -> None:
        ledger = MatterLedger()
        ledger.register("hut-1", integrity=0.05, decay_rate=0.1)
        events = ledger.settle(tick=200, seed=0)
        ns = NpcStore(store)
        await ns.flush_tick(events)

        row = await session.get(MatterState, "hut-1")
        assert row is not None
        assert row.integrity == pytest.approx(0.0)
        assert ledger.state("hut-1").integrity == pytest.approx(0.0)


@pytest.mark.t1
class TestRubbleTripleConsistency:
    """is_rubble 终态：ledger ↔ matter_state（投影按 COLLAPSE 或 integrity≤0 推导）。"""

    async def test_decay_to_zero_marks_rubble(self, store, session: AsyncSession) -> None:
        ledger = MatterLedger()
        ledger.register("hut-1", integrity=0.05, decay_rate=0.1)
        events = ledger.settle(tick=200, seed=0)
        assert EventKind.MATTER_COLLAPSE in {e.event_type for e in events}
        ns = NpcStore(store)
        await ns.flush_tick(events)

        row = await session.get(MatterState, "hut-1")
        assert row is not None
        assert row.is_rubble is ledger.state("hut-1").is_rubble is True

    async def test_damage_to_zero_marks_rubble(self, store, session: AsyncSession) -> None:
        ledger = MatterLedger()
        ledger.register("wall-1", integrity=0.2, decay_rate=0.0)
        dmg = ledger.damage("wall-1", amount=-0.5, tick=10)
        ns = NpcStore(store)
        await ns.flush_tick([dmg])

        row = await session.get(MatterState, "wall-1")
        assert row is not None
        assert row.is_rubble is True
        assert ledger.state("wall-1").is_rubble is True

    async def test_live_object_not_rubble(self, store, session: AsyncSession) -> None:
        ledger = MatterLedger()
        ledger.register("wall-1", integrity=1.0, decay_rate=0.0)
        ns = NpcStore(store)
        await ns.flush_tick([ledger.build("wall-1", amount=0.0, tick=1)])

        row = await session.get(MatterState, "wall-1")
        assert row is not None
        assert row.is_rubble is False


@pytest.mark.t1
class TestDecayRateKnownGap:
    """§17.2 已知缺口：账本静态 decay_rate 无事件承载 → 投影不持久化。

    xfail（非 strict）：当 M2-D4 缺口被裁决修复（payload 携带 decay_rate →
    投影写列）后本测试将 XPASS，提示移除/改写成正向断言。
    """

    @pytest.mark.xfail(
        reason="§17.2 decay_rate 无事件承载，投影落 0.0（待 Claude 裁决方案 A/B）",
        strict=False,
    )
    async def test_decay_rate_persisted_from_ledger(self, store, session: AsyncSession) -> None:
        ledger = MatterLedger()
        ledger.register("food-1", integrity=1.0, decay_rate=0.1)
        ns = NpcStore(store)
        await ns.flush_tick([ledger.build("food-1", amount=0.0, tick=1)])

        row = await session.get(MatterState, "food-1")
        assert row is not None
        # 期望：投影承载账本静态率；当前 = 0.0（缺口）
        assert row.decay_rate == pytest.approx(ledger.state("food-1").decay_rate)
