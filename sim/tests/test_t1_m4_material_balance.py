"""M4-D2d T1 钉子 — MATERIAL_MOVED 消费端同批事务 + 材料守恒。

口径：`world:*` 是外部供给基准，允许净负；`npc/structure` 余额不得为负。
每个 MATERIAL_MOVED 对同材料 from/to 一减一加，净额守恒。
"""

from __future__ import annotations

import math

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import material_moved_event
from sim.core.persistence.database import init_database
from sim.core.persistence.models import Event, MaterialBalance, Structure
from sim.core.persistence.npc_store import NpcStore, NpcStoreError
from sim.core.persistence.store import SqlEventStore

BALANCE_TOLERANCE = 1e-9


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


def move(
    tick: int,
    *,
    from_ref: str,
    to_ref: str,
    quantity: float = 1.0,
    structure_id: str = "",
):
    return material_moved_event(
        tick,
        transfer_id=f"t-{tick}",
        material_id="wood",
        quantity=quantity,
        from_ref=from_ref,
        to_ref=to_ref,
        reason="build_consumed",
        structure_id=structure_id,
    )


def _total(balances: dict[tuple[str, str], float], material_id: str = "wood") -> float:
    return sum(
        quantity
        for (ref, current_material), quantity in balances.items()
        if current_material == material_id
    )


@pytest.mark.t1
class TestMaterialConservation:
    async def test_world_supply_credits_structure_and_conserves(self, store) -> None:
        ns = NpcStore(store)
        await ns.flush_tick(
            [
                move(
                    1,
                    from_ref="world:stockpile",
                    to_ref="structure:hut-1",
                    quantity=2.0,
                    structure_id="hut-1",
                )
            ]
        )

        balances = await ns.materialize_material_balances()
        assert balances[("structure:hut-1", "wood")] == pytest.approx(2.0)
        assert balances[("world:stockpile", "wood")] == pytest.approx(-2.0)
        assert math.isclose(_total(balances), 0.0, abs_tol=BALANCE_TOLERANCE)

    async def test_multi_move_batch_conserves(self, store) -> None:
        ns = NpcStore(store)
        await ns.flush_tick(
            [
                move(1, from_ref="world:stockpile", to_ref="npc:chenmo", quantity=3.0),
                move(2, from_ref="npc:chenmo", to_ref="structure:hut-1", quantity=1.25),
                move(3, from_ref="world:stockpile", to_ref="structure:hut-1", quantity=0.75),
            ]
        )

        balances = await ns.materialize_material_balances()
        assert math.isclose(_total(balances), 0.0, abs_tol=BALANCE_TOLERANCE)
        assert balances[("npc:chenmo", "wood")] == pytest.approx(1.75)
        assert balances[("structure:hut-1", "wood")] == pytest.approx(2.0)

    async def test_snapshot_and_replay_bit_equal(self, store) -> None:
        ns = NpcStore(store)
        await ns.flush_tick(
            [
                move(1, from_ref="world:stockpile", to_ref="npc:chenmo", quantity=2.0),
                move(2, from_ref="npc:chenmo", to_ref="structure:hut-1", quantity=0.5),
            ]
        )

        snapshot = await ns.materialize_material_balances()
        replay = await ns.materialize_material_balances_replay()
        assert snapshot == replay

    async def test_branch_isolated(self, store) -> None:
        main = NpcStore(store, branch_id="main")
        fork = NpcStore(store, branch_id="fork")
        event = move(1, from_ref="world:stockpile", to_ref="npc:chenmo", quantity=1.0)
        await main.flush_tick([event])
        await fork.flush_tick([event])

        assert (await main.materialize_material_balances())[("npc:chenmo", "wood")] == 1.0
        assert (await fork.materialize_material_balances())[("npc:chenmo", "wood")] == 1.0

    async def test_material_filter(self, store) -> None:
        ns = NpcStore(store)
        await ns.flush_tick(
            [
                material_moved_event(
                    1,
                    transfer_id="w-1",
                    material_id="wood",
                    quantity=1.0,
                    from_ref="world:stockpile",
                    to_ref="npc:chenmo",
                    reason="build_reserved",
                ),
                material_moved_event(
                    2,
                    transfer_id="s-1",
                    material_id="stone",
                    quantity=1.0,
                    from_ref="world:quarry",
                    to_ref="npc:chenmo",
                    reason="build_reserved",
                ),
            ]
        )
        balances = await ns.materialize_material_balances(["stone"])
        assert set(balances) == {("world:quarry", "stone"), ("npc:chenmo", "stone")}


@pytest.mark.t1
class TestMaterialRollback:
    async def test_npc_debit_insufficient_rolls_back_batch(self, store, session) -> None:
        ns = NpcStore(store)
        await ns.flush_tick(
            [move(1, from_ref="world:stockpile", to_ref="npc:chenmo", quantity=1.0)]
        )
        before_events = (await session.execute(select(Event))).scalars().all()
        before_balances = await ns.materialize_material_balances()

        with pytest.raises(NpcStoreError, match="余额不足"):
            await ns.flush_tick(
                [
                    move(2, from_ref="npc:chenmo", to_ref="structure:hut-1", quantity=0.5),
                    move(3, from_ref="npc:chenmo", to_ref="structure:hut-2", quantity=2.0),
                ]
            )

        assert (await session.execute(select(Event))).scalars().all() == before_events
        assert await ns.materialize_material_balances() == before_balances

    async def test_invalid_move_rolls_back_structure_projection(self, store, session) -> None:
        ns = NpcStore(store)
        structure_event = material_moved_event(
            1,
            transfer_id="t-1",
            material_id="wood",
            quantity=1.0,
            from_ref="world:stockpile",
            to_ref="structure:hut-1",
            reason="build_consumed",
            structure_id="hut-1",
        )
        invalid = move(2, from_ref="npc:ghost", to_ref="structure:hut-2", quantity=1.0)

        with pytest.raises(NpcStoreError, match="余额不足"):
            await ns.flush_tick([structure_event, invalid])

        assert (await session.execute(select(Event))).scalars().all() == []
        assert (await session.execute(select(Structure))).scalars().all() == []
        assert (await session.execute(select(MaterialBalance))).scalars().all() == []
