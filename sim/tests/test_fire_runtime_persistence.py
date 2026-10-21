"""DA-03 前置：火格、生命周期事件与真实落库必须一致。"""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from sim.core.events import coin_grant_event
from sim.core.persistence.database import create_session_factory, init_database
from sim.core.persistence.fire_store import FireStore
from sim.core.persistence.fork import fork_from_anchor
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore
from sim.npc.fire_runtime import FireRuntime


@pytest.fixture
async def spread_fire():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_database(engine)
    store = SqlEventStore(create_session_factory(engine))
    runtime = FireRuntime()
    writer = NpcStore(store)
    try:
        await writer.flush_tick(runtime.ignite_at(tick=0, x=10, y=10))
        for tick in range(1, 4):
            await writer.flush_tick(runtime.step(tick=tick))
        yield store, runtime, writer
    finally:
        await engine.dispose()


async def test_spread_cells_match_lifecycle_replay_after_three_steps(spread_fire):
    store, runtime, _ = spread_fire
    rows = await FireStore(store).materialize_fires_replay()
    recorded = {
        (row.fire_id, row.x, row.y, row.ignited_tick) for row in rows.values() if row.active
    }
    live = {(cell.fire_id, cell.x, cell.y, cell.ignited_tick) for cell in runtime.cells}
    assert recorded == live
    assert len({cell.fire_id for cell in runtime.cells}) == len(runtime.cells)


async def test_spread_fire_can_burn_out_without_repeated_extinction_writes(spread_fire):
    store, runtime, writer = spread_fire
    for tick in range(4, 35):
        await writer.flush_tick(runtime.step(tick=tick, walkable=set()))
    rows = await FireStore(store).materialize_fires_replay()
    assert runtime.cells == ()
    assert all(not row.active for row in rows.values())


async def test_child_extinction_follows_ancestor_ignition_even_with_smaller_sequence():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_database(engine)
    store = SqlEventStore(create_session_factory(engine))
    runtime = FireRuntime()
    try:
        await NpcStore(store).flush_tick(
            [
                coin_grant_event(0, "chenmo", 1, "工钱"),
                coin_grant_event(0, "chenmo", 1, "工钱"),
                *runtime.ignite_at(tick=0, x=10, y=10),
            ]
        )

        async def preflush():
            return None

        await fork_from_anchor(
            store.session_factory,
            parent_branch_id="main",
            fork_seq=3,
            fork_tick=0,
            preflush=preflush,
            new_branch_id="child",
        )
        for tick in range(1, 13):
            await NpcStore(store, branch_id="child").flush_tick(
                runtime.step(tick=tick, walkable=set())
            )
        fires = FireStore(store, branch_id="child")
        before = await fires.materialize_fires_replay(upto_seq=0)
        after = await fires.materialize_fires_replay(upto_seq=1)
        assert before["fire-1"].active
        assert after["fire-1"].ended_tick == 12
        assert not after["fire-1"].active
    finally:
        await engine.dispose()
