"""M3-C3 后续件 — matter 注册立账事件持久化（§19.4 裁决方案 A）。

覆盖：register 返回 MATTER_BUILD 立账事件、flush_tick 快照不丢、flush_events
纯事件冷启重放不丢、注册后快照/重放逐位相等、amount=0 不扭曲 integrity、
重复注册不替换、x/y=-1 未定位不触发 chunk 失效。
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import EventKind, WorldEvent
from sim.core.flush import flush_events
from sim.core.persistence.database import init_database
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore
from sim.world.matter import MatterLedger
from sim.world.pathfinding import event_tile_position


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
    return {
        matter_id: (snapshot.integrity, snapshot.decay_rate, snapshot.is_rubble)
        for matter_id, snapshot in ledger._items.items()
    }


class TestRegisterEventContract:
    def test_register_returns_build_event(self) -> None:
        ledger = MatterLedger()

        event = ledger.register("crate-1", integrity=0.63, decay_rate=0.02, tick=7)

        assert isinstance(event, WorldEvent)
        assert event.event_type is EventKind.MATTER_BUILD
        assert event.tick == 7
        assert event.payload == {
            "matter_id": "crate-1",
            "x": -1,
            "y": -1,
            "amount": 0.0,
            "durability": 0.63,
            "decay_rate": 0.02,
            "note": "register",
        }

    def test_duplicate_register_preserves_first_snapshot(self) -> None:
        ledger = MatterLedger()
        first = ledger.register("wall-1", integrity=0.8, decay_rate=0.0, tick=1)

        with pytest.raises(ValueError, match="物质对象重复注册"):
            ledger.register("wall-1", integrity=0.1, decay_rate=0.9, tick=2)

        snapshot = ledger.state("wall-1")
        assert (snapshot.integrity, snapshot.decay_rate) == (0.8, 0.0)
        assert first.payload["durability"] == 0.8

    def test_invalid_event_payload_does_not_half_register(self) -> None:
        ledger = MatterLedger()

        with pytest.raises(ValueError):
            ledger.register("invalid-1", integrity=0.5, decay_rate=0.0, x=4096)

        assert ledger._items == {}

    def test_unlocated_registration_does_not_trigger_chunk_invalidation(self) -> None:
        event = MatterLedger().register("unlocated-1", integrity=0.5, decay_rate=0.0)

        assert event.payload["x"] == -1
        assert event.payload["y"] == -1
        assert event_tile_position(event) is None

    def test_located_registration_forwards_coordinates(self) -> None:
        event = MatterLedger().register("located-1", integrity=0.5, decay_rate=0.0, x=8, y=12)

        assert (event.payload["x"], event.payload["y"]) == (8, 12)
        assert event_tile_position(event) == (8, 12)


class TestRegisterPersistence:
    async def test_flush_tick_materializes_registered_object(self, store) -> None:
        event = MatterLedger().register("crate-1", integrity=0.63, decay_rate=0.02, tick=7)
        ns = NpcStore(store)

        await ns.flush_tick([event])
        materialized = await ns.materialize_matter(["crate-1"])

        snapshot = materialized.state("crate-1")
        assert (snapshot.integrity, snapshot.decay_rate, snapshot.is_rubble) == (0.63, 0.02, False)

    async def test_flush_events_replay_survives_cold_start(self, store) -> None:
        event = MatterLedger().register("cold-1", integrity=0.4, decay_rate=0.01, tick=3)
        ns = NpcStore(store)

        await flush_events(store, [event])

        assert (await ns.materialize_matter())._items == {}
        replayed = await ns.materialize_matter_replay()
        snapshot = replayed.state("cold-1")
        assert (snapshot.integrity, snapshot.decay_rate, snapshot.is_rubble) == (0.4, 0.01, False)

    async def test_registration_only_snapshot_and_replay_are_bit_equal(self, store) -> None:
        event = MatterLedger().register("hut-1", integrity=0.73, decay_rate=0.04, tick=11)
        ns = NpcStore(store)

        await ns.flush_tick([event])

        snapshot = await ns.materialize_matter()
        replay = await ns.materialize_matter_replay()

        assert _ledger_state(snapshot) == _ledger_state(replay)
        assert _ledger_state(replay) == {"hut-1": (0.73, 0.04, False)}

    async def test_zero_amount_does_not_distort_register_integrity(self, store) -> None:
        event = MatterLedger().register("shelf-1", integrity=0.61, decay_rate=0.015, tick=5)
        ns = NpcStore(store)

        assert event.payload["amount"] == 0.0
        assert event.payload["durability"] == 0.61

        await ns.flush_tick([event])

        snapshot = await ns.materialize_matter(["shelf-1"])
        replay = await ns.materialize_matter_replay(["shelf-1"])
        assert snapshot.state("shelf-1").integrity == 0.61
        assert replay.state("shelf-1").integrity == 0.61
