"""Snapshot retention, cold marking and recovery contracts on isolated SQLite."""

import gzip
import json

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.core.clock import GameClock
from sim.core.events import npc_death_event, tile_changed_event, world_create_event
from sim.core.persistence import fork, world_restore
from sim.core.persistence import store as store_module
from sim.core.persistence.models import Branch, Event, Snapshot
from sim.core.persistence.store import SqlEventStore
from sim.core.persistence.world_restore import WorldCheckpoint, flush_world, restore_world
from sim.core.rng import RngRegistry
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus

pytestmark = pytest.mark.t1


async def seed(store):
    loop = TickLoop(GameClock(), build_default_bus(), WorldState())
    loop.enqueue(world_create_event(0, 42, ("chenmo", "villager_01")))
    await store.append("main", [event.to_store_dict() for event in loop.drain_events()])
    return loop


async def write(store, loop, tick, *, writer="flush", branch="main"):
    # Retention metadata cases may jump days without simulating unrelated systems.
    loop.state = loop.state.model_copy(update={"tick": tick})
    loop.clock.restore_tick(tick)
    event = tile_changed_event(tick, 0, 0, 7)
    if writer == "flush":
        await flush_world(store, branch, loop, [event])
    else:
        await store.append(branch, [event.to_store_dict()])
        async with store.session_factory() as session:
            seq = await session.scalar(select(func.max(Event.seq)).where(Event.branch_id == branch))
        await store.write_snapshot(
            branch, tick, seq, WorldCheckpoint.capture(loop).model_dump_json().encode()
        )


async def snapshots(store, branch="main"):
    async with store.session_factory() as session:
        rows = (
            await session.scalars(
                select(Snapshot)
                .where(Snapshot.branch_id == branch)
                .order_by(Snapshot.tick, Snapshot.seq)
            )
        ).all()
        return [(row.seq, row.tick, row.is_cold, row.snapshot_data) for row in rows]


async def noop():
    pass


@pytest.mark.parametrize("writer", ["direct", "flush"])
@pytest.mark.parametrize("autoflush", [True, False])
async def test_keeps_eight_recent_plus_one_first_for_each_of_three_days(engine, writer, autoflush):
    store = SqlEventStore(async_sessionmaker(engine, expire_on_commit=False, autoflush=autoflush))
    loop = await seed(store)
    ticks = [
        *range(34),
        *range(TICKS_PER_GAME_DAY, TICKS_PER_GAME_DAY + 33),
        *range(2 * TICKS_PER_GAME_DAY, 2 * TICKS_PER_GAME_DAY + 33),
    ]
    for tick in ticks:
        await write(store, loop, tick, writer=writer)
    rows = await snapshots(store)
    assert len(rows) == 11
    assert [row[1] for row in rows[:3]] == [0, TICKS_PER_GAME_DAY, 2 * TICKS_PER_GAME_DAY]
    assert [row[1] for row in rows[3:]] == ticks[-8:]
    assert all(not row[2] for row in rows)
    assert len(await store.read_range("main", 0, 1000)) == 101


@pytest.mark.parametrize("writer", ["direct", "flush"])
async def test_same_tick_uses_seq_to_keep_exactly_one_daily_first(store, writer):
    loop = await seed(store)
    for _ in range(100):
        await write(store, loop, 42, writer=writer)
    rows = await snapshots(store)
    assert [row[0] for row in rows] == [2, *range(94, 102)]
    assert len(rows) == 9
    old = await store.latest_snapshot("main", 42, max_seq=50)
    assert old is not None and old.seq == 2
    assert await store.latest_snapshot("main", 42, max_seq=1) is None


async def test_same_day_growth_plateaus_and_overlapping_keepers_are_not_duplicated(store):
    loop = await seed(store)
    counts = {}
    for index in range(1, 101):
        await write(store, loop, index)
        if index in (1, 8, 9, 10, 50, 100):
            counts[index] = len(await snapshots(store))
    assert counts == {1: 1, 8: 8, 9: 9, 10: 9, 50: 9, 100: 9}
    print("snapshot-growth", json.dumps(counts, sort_keys=True))


async def test_pruning_leaves_other_branches_and_cold_daily_first_unchanged(store):
    loop = await seed(store)
    blob = WorldCheckpoint.capture(loop).model_dump_json().encode()
    await store.write_snapshot("main", 0, 1, blob)
    async with store.session_factory.begin() as session:
        await session.execute(
            update(Snapshot).where(Snapshot.branch_id == "main").values(is_cold=True)
        )
        session.add(Branch(id="other", status="active", is_current=False))
    await store.append(
        "other",
        [
            world_create_event(0, 42, ("chenmo",)).to_store_dict(),
            *[tile_changed_event(i, 0, 0, 7).to_store_dict() for i in range(1, 21)],
        ],
    )
    async with store.session_factory.begin() as session:
        session.add_all(
            Snapshot(
                branch_id="other", seq=i, tick=i, snapshot_data=gzip.compress(blob), is_cold=False
            )
            for i in range(1, 22)
        )
    other_before = await snapshots(store, "other")
    cold_before = (await snapshots(store))[0]
    for index in range(1, 101):
        await write(store, loop, index)
    rows = await snapshots(store)
    assert len(rows) == 9  # Eight hot + the already-cold daily first, not an extra hot first.
    assert rows[0] == cold_before
    assert sum(not row[2] for row in rows) == 8
    assert await snapshots(store, "other") == other_before


async def test_legacy_abandoned_rows_are_never_pruned_even_when_not_marked_cold(store):
    loop = await seed(store)
    blob = gzip.compress(WorldCheckpoint.capture(loop).model_dump_json().encode())
    async with store.session_factory.begin() as session:
        await session.execute(
            update(Branch).where(Branch.id == "main").values(status="abandoned", is_current=False)
        )
        session.add_all(
            Snapshot(branch_id="main", seq=i, tick=i, snapshot_data=blob, is_cold=False)
            for i in range(1, 21)
        )
    before = await snapshots(store)
    await store.write_snapshot("main", 21, 21, b"{}")
    after = await snapshots(store)
    assert after[:20] == before
    assert len(after) == 21


async def test_head_fork_marks_all_parent_snapshots_cold_without_deleting_history(store):
    loop = await seed(store)
    for index in range(1, 101):
        await write(store, loop, index)
    before = await snapshots(store)
    events = await store.read_range("main", 0, 1000)
    await fork.fork_from_anchor(
        store.session_factory,
        parent_branch_id="main",
        fork_seq=events[-1]["seq"],
        fork_tick=100,
        preflush=noop,
        new_branch_id="child",
    )
    after = await snapshots(store)
    assert len(after) == len(before)
    assert all(row[2] for row in after)
    assert [(r[0], r[1], r[3]) for r in after] == [(r[0], r[1], r[3]) for r in before]
    assert await store.read_range("main", 0, 1000) == events
    await write(store, loop, 101, branch="child")
    assert await snapshots(store) == after
    assert all(not row[2] for row in await snapshots(store, "child"))


@pytest.mark.parametrize("writer", ["direct", "flush"])
async def test_retention_failure_rolls_back_new_snapshot_and_any_deletion(
    store, monkeypatch, writer
):
    loop = await seed(store)
    for index in range(1, 11):
        await write(store, loop, index, writer=writer)
    before = await snapshots(store)
    events = await store.read_range("main", 0, 1000)

    async def fail_after_pruning(session, branch):
        from sim.core.persistence.snapshot_policy import prune_hot_snapshots

        await prune_hot_snapshots(session, branch)
        raise RuntimeError("retention failed")

    target = world_restore if writer == "flush" else store_module
    monkeypatch.setattr(target, "prune_hot_snapshots", fail_after_pruning, raising=False)
    with pytest.raises(RuntimeError, match="retention failed"):
        await write(store, loop, 11, writer=writer)
    assert await snapshots(store) == before
    # Direct write_snapshot has a separate event commit by contract; flush_world must roll both back.
    after_events = await store.read_range("main", 0, 1000)
    assert after_events == events if writer == "flush" else after_events[:-1] == events


async def test_cold_mark_failure_rolls_back_the_entire_fork(store, monkeypatch):
    loop = await seed(store)
    await write(store, loop, 1)
    before = await snapshots(store)
    events = await store.read_range("main", 0, 1000)

    async def fail_after_marking(session, branch):
        from sim.core.persistence.snapshot_policy import mark_branch_snapshots_cold

        await mark_branch_snapshots_cold(session, branch)
        raise RuntimeError("cold marking failed")

    monkeypatch.setattr(fork, "mark_branch_snapshots_cold", fail_after_marking, raising=False)
    with pytest.raises(RuntimeError, match="cold marking failed"):
        await fork.fork_from_anchor(
            store.session_factory,
            parent_branch_id="main",
            fork_seq=events[-1]["seq"],
            fork_tick=1,
            preflush=noop,
            new_branch_id="rolled-back",
        )
    assert await snapshots(store) == before
    assert await store.read_range("main", 0, 1000) == events
    async with store.session_factory() as session:
        assert await session.get(Branch, "rolled-back") is None
        assert (await session.get(Branch, "main")).status == "active"


async def test_pruned_historical_checkpoint_replays_to_identical_full_json(store):
    loop = TickLoop(GameClock(), build_default_bus(), WorldState())
    loop.enqueue(world_create_event(0, 42, ("chenmo", "villager_01")))
    RngRegistry(world_seed=42).generator("retained.baseline", loop.context.rng_cache).random(7)
    await flush_world(store, "main", loop, loop.drain_events())
    expected = None
    cutoff = None
    for tick in range(1, 81):
        if tick == 1:
            loop.issue_move("chenmo", [(x, 0) for x in range(12)])
        loop._tick_once()
        if tick == 10:
            loop.enqueue(npc_death_event(tick=tick, entity_id="villager_01"))
        if tick == 15:
            loop.issue_combat_scale(True)
        loop.enqueue(tile_changed_event(tick, 0, 0, 7))
        await flush_world(store, "main", loop, loop.drain_events())
        if tick == 30:
            before = await restore_world(store, "main")
            expected = WorldCheckpoint.capture(before).model_dump_json()
            assert expected == WorldCheckpoint.capture(loop).model_dump_json()
            cutoff = (await store.read_range("main", 0, 10000))[-1]["seq"]
    assert expected is not None and cutoff is not None
    assert all(row[0] != cutoff for row in await snapshots(store))
    chosen = await store.latest_snapshot("main", 10000, max_seq=cutoff)
    assert chosen is not None and chosen.tick == 0
    async with store.session_factory.begin() as session:
        session.add(
            Branch(
                id="past",
                forked_from_branch="main",
                forked_from_seq=cutoff,
                status="active",
                is_current=False,
            )
        )
    after = await restore_world(store, "past")
    assert WorldCheckpoint.capture(after).model_dump_json() == expected


async def test_history_without_any_qualified_snapshot_still_replays_exactly(store):
    loop = TickLoop(GameClock(), build_default_bus(), WorldState())
    loop.enqueue(world_create_event(0, 42, ("chenmo",)))
    loop.issue_move("chenmo", [(x, 0) for x in range(12)])
    for tick in range(1, 31):
        loop._tick_once()
        loop.enqueue(tile_changed_event(tick, 0, 0, 7))
    await store.append("main", [event.to_store_dict() for event in loop.drain_events()])
    restored = await restore_world(store, "main")
    assert (
        WorldCheckpoint.capture(restored).model_dump_json()
        == WorldCheckpoint.capture(loop).model_dump_json()
    )
