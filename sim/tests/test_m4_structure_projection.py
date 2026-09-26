"""M4-D2b — structures 投影/重放共用单折叠 + 快照/重放逐位相等。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import (
    structure_checkpoint_event,
    structure_collapsed_event,
    structure_completed_event,
    structure_removed_event,
    structure_started_event,
)
from sim.core.persistence.database import init_database
from sim.core.persistence.models import Structure
from sim.core.persistence.npc_store import NpcStore, NpcStoreError
from sim.core.persistence.store import SqlEventStore
from sim.world.structure import StructurePhase


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


def started(
    tick: int = 1,
    *,
    structure_id: str = "hut-1",
    branch_id: str = "main",
    owner_id: str = "chenmo",
    built_by: str = "npc-01",
    tiles: tuple[tuple[int, int], ...] = ((1, 0), (0, 0)),
    kind: str = "wood_hut",
):
    return structure_started_event(
        tick,
        structure_id=structure_id,
        tiles=tiles,
        kind=kind,
        material="wood",
        owner_id=owner_id,
        built_by=built_by,
        load_bearing=True,
        supported_by=("wall-2", "wall-1"),
        planned_duration_ticks=86_400,
        recipe_id="hut.v1",
        recipe_version="1",
        build_rule_version="m4-v1",
        branch_id=branch_id,
    )


def _state(ledger: dict) -> dict:
    return {
        structure_id: (
            snapshot.tiles,
            snapshot.kind,
            snapshot.material,
            snapshot.phase,
            snapshot.load_bearing,
            snapshot.supported_by,
            snapshot.owner_id,
            snapshot.built_by,
            snapshot.built_at,
        )
        for structure_id, snapshot in ledger.items()
    }


@pytest.mark.t1
class TestStructureTwoEntry:
    async def test_full_lifecycle_bit_equal(self, store) -> None:
        ns = NpcStore(store)
        await ns.flush_tick([started()])
        await ns.flush_tick(
            [
                structure_checkpoint_event(
                    86_400,
                    structure_id="hut-1",
                    progress=0.5,
                    quality=0.4,
                    integrity=1.0,
                    build_rule_version="m4-v1",
                )
            ]
        )
        await ns.flush_tick(
            [structure_completed_event(172_800, structure_id="hut-1", quality=0.4, integrity=1.0)]
        )

        snapshot = await ns.materialize_structures()
        replay = await ns.materialize_structures_replay()
        assert _state(snapshot) == _state(replay)
        assert snapshot["hut-1"].phase is StructurePhase.ACTIVE
        assert snapshot["hut-1"].built_at == 172_800

    async def test_collapse_rubble_tombstone_bit_equal(self, store) -> None:
        ns = NpcStore(store)
        await ns.flush_tick(
            [
                started(),
                structure_completed_event(2, structure_id="hut-1", quality=0.5, integrity=1.0),
            ]
        )
        await ns.flush_tick(
            [structure_collapsed_event(3, structure_id="hut-1", cause="support_lost")]
        )

        snapshot = await ns.materialize_structures()
        replay = await ns.materialize_structures_replay()
        assert _state(snapshot) == _state(replay)
        assert snapshot["hut-1"].phase is StructurePhase.RUBBLE

    async def test_removed_absent_from_both_paths(self, store) -> None:
        ns = NpcStore(store)
        await ns.flush_tick([started()])
        await ns.flush_tick([structure_removed_event(2, structure_id="hut-1", reason="demolished")])

        assert await ns.materialize_structures() == {}
        assert await ns.materialize_structures_replay() == {}

    async def test_cleanup_removes_rubble_tombstone(self, store) -> None:
        ns = NpcStore(store)
        await ns.flush_tick([started()])
        await ns.flush_tick(
            [
                structure_collapsed_event(2, structure_id="hut-1", cause="decay"),
                structure_removed_event(3, structure_id="hut-1", reason="cleanup"),
            ]
        )

        assert await ns.materialize_structures() == {}
        assert await ns.materialize_structures_replay() == {}

    async def test_empty_optional_columns_roundtrip_as_empty_string(
        self, store, session: AsyncSession
    ) -> None:
        ns = NpcStore(store)
        await ns.flush_tick([started(owner_id="", built_by="")])
        snapshot = (await ns.materialize_structures())["hut-1"]
        row = (await session.execute(select(Structure))).scalars().one()

        assert row.owner_id is None
        assert row.built_by is None
        assert snapshot.owner_id == ""
        assert snapshot.built_by == ""

    async def test_started_and_checkpoint_same_batch(self, store) -> None:
        ns = NpcStore(store)
        await ns.flush_tick(
            [
                started(),
                structure_checkpoint_event(
                    86_400,
                    structure_id="hut-1",
                    progress=0.5,
                    quality=0.5,
                    integrity=1.0,
                    build_rule_version="m4-v1",
                ),
            ]
        )
        assert (await ns.materialize_structures())["hut-1"].phase is StructurePhase.BUILDING

    async def test_replay_filters_ids(self, store) -> None:
        ns = NpcStore(store)
        await ns.flush_tick([started()])
        assert set(await ns.materialize_structures_replay(["hut-1", "ghost"])) == {"hut-1"}
        assert await ns.materialize_structures_replay([]) == {}

    async def test_replay_branch_isolated(self, store) -> None:
        main = NpcStore(store, branch_id="main")
        fork = NpcStore(store, branch_id="fork")
        await main.flush_tick([started()])
        await fork.flush_tick(
            [
                started(
                    structure_id="hut-1",
                    branch_id="fork",
                    tiles=((9, 9),),
                    kind="stone_wall",
                )
            ]
        )

        main_snapshot = (await main.materialize_structures_replay())["hut-1"]
        fork_snapshot = (await fork.materialize_structures_replay())["hut-1"]
        assert main_snapshot.phase is StructurePhase.BUILDING
        assert fork_snapshot.phase is StructurePhase.BUILDING
        assert main_snapshot.kind == "wood_hut"
        assert fork_snapshot.kind == "stone_wall"
        assert main_snapshot.tiles == ((0, 0), (1, 0))
        assert fork_snapshot.tiles == ((9, 9),)

    async def test_replay_is_pure_read(self, store, session: AsyncSession) -> None:
        ns = NpcStore(store)
        await ns.flush_tick([started()])
        before = (await session.execute(select(Structure))).scalars().all()
        await ns.materialize_structures_replay()
        after = (await session.execute(select(Structure))).scalars().all()
        assert len(before) == len(after) == 1


@pytest.mark.t1
class TestStructureProjectionGuards:
    async def test_duplicate_started_rolls_back(self, store, session: AsyncSession) -> None:
        ns = NpcStore(store)
        with pytest.raises(NpcStoreError, match="重复开始"):
            await ns.flush_tick([started(), started(tick=2)])
        assert (await session.execute(select(Structure))).scalars().all() == []

    async def test_orphan_checkpoint_rolls_back(self, store, session: AsyncSession) -> None:
        ns = NpcStore(store)
        event = structure_checkpoint_event(
            1,
            structure_id="ghost",
            progress=0.1,
            quality=0.5,
            integrity=1.0,
            build_rule_version="m4-v1",
        )
        with pytest.raises(NpcStoreError, match="未知结构"):
            await ns.flush_tick([event])
        assert (await session.execute(select(Structure))).scalars().all() == []

    async def test_malformed_tiles_row_fails_closed(self, session: AsyncSession) -> None:
        session.add(
            Structure(
                branch_id="main",
                structure_id="bad",
                tiles=json.dumps([{"x": 0}]),
                kind="wood_hut",
                material="wood",
                phase="active",
            )
        )
        await session.commit()
        ns = NpcStore(SqlEventStore(async_sessionmaker(session.bind, class_=AsyncSession)))
        with pytest.raises(NpcStoreError, match="tiles"):
            await ns.materialize_structures()
