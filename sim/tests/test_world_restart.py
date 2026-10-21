"""DA-01：真实启动入口必须接续已持久化世界，不能再次创世。"""

import pytest

from sim.api.main import build_loop
from sim.core.events import npc_death_event
from sim.core.persistence.npc_store import NpcStore


@pytest.mark.asyncio
async def test_restart_restores_saved_world_without_a_second_genesis(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    loop, store = await build_loop()
    loop.advance_frame(1.0)
    loop.enqueue(npc_death_event(tick=loop.state.tick, entity_id="villager_01"))
    await NpcStore(store).flush_tick(loop.drain_events())
    rows = await store.read_branch_history("main")
    await store.write_snapshot(
        "main", loop.state.tick, rows[-1]["seq"], loop.state.model_dump_json().encode()
    )
    expected = loop.state.state_hash()
    await store.session_factory.kw["bind"].dispose()

    restored, reopened = await build_loop()
    try:
        assert restored.state.state_hash() == expected
        assert restored.clock.tick == restored.state.tick
        assert restored.pending_events == []
        await NpcStore(reopened).flush_tick(restored.drain_events())
        history = await reopened.read_branch_history("main")
        assert sum(row["event_type"] == "world.create" for row in history) == 1
    finally:
        await reopened.session_factory.kw["bind"].dispose()


@pytest.mark.asyncio
async def test_production_flush_checkpoints_world_and_random_progress(tmp_path, monkeypatch):
    from sim.core.persistence.world_restore import flush_world
    from sim.core.rng import RngRegistry

    monkeypatch.chdir(tmp_path)
    loop, store = await build_loop()
    registry = RngRegistry(world_seed=42)
    rng = registry.generator("test.restart", loop.context.rng_cache)
    rng.random(7)
    loop.issue_combat_scale(True)
    await flush_world(store, "main", loop, loop.drain_events())
    expected = loop.state.state_hash()
    next_draw = rng.random()
    await store.session_factory.kw["bind"].dispose()

    restored, reopened = await build_loop()
    try:
        assert restored.state.state_hash() == expected
        assert restored.context.combat_active
        assert registry.generator("test.restart", restored.context.rng_cache).random() == next_draw
        assert restored.clock.tick == restored.state.tick
    finally:
        await reopened.session_factory.kw["bind"].dispose()


@pytest.mark.asyncio
async def test_restart_replays_snapshot_tail_without_running_npc_hooks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    loop, store = await build_loop()
    await NpcStore(store).flush_tick(loop.drain_events())
    history = await store.read_branch_history("main")
    await store.write_snapshot(
        "main", loop.state.tick, history[-1]["seq"], loop.state.model_dump_json().encode()
    )
    loop.advance_frame(1.0)
    loop.enqueue(npc_death_event(tick=loop.state.tick, entity_id="villager_01"))
    await NpcStore(store).flush_tick(loop.drain_events())
    expected = loop.state.state_hash()
    await store.session_factory.kw["bind"].dispose()

    restored, reopened = await build_loop()
    try:
        assert restored.state.state_hash() == expected
        assert not restored.pending_events
    finally:
        await reopened.session_factory.kw["bind"].dispose()


@pytest.mark.asyncio
async def test_restart_refuses_duplicate_genesis_instead_of_appending_more(tmp_path, monkeypatch):
    from sim.core.events import world_create_event

    monkeypatch.chdir(tmp_path)
    loop, store = await build_loop()
    await NpcStore(store).flush_tick(loop.drain_events())
    await NpcStore(store).flush_tick([world_create_event(0, 42, ("chenmo",))])
    await store.session_factory.kw["bind"].dispose()
    with pytest.raises(ValueError, match="genesis"):
        await build_loop()


@pytest.mark.asyncio
async def test_restart_uses_current_child_and_respects_ancestor_cutoff(tmp_path, monkeypatch):
    from sqlalchemy import update

    from sim.core.persistence.models import Branch

    monkeypatch.chdir(tmp_path)
    loop, store = await build_loop()
    await NpcStore(store).flush_tick(loop.drain_events())
    history = await store.read_branch_history("main")
    cutoff = history[-1]["seq"]
    await store.write_snapshot(
        "main", loop.state.tick, cutoff, loop.state.model_dump_json().encode()
    )
    expected = loop.state.state_hash()
    loop.enqueue(npc_death_event(tick=loop.state.tick, entity_id="villager_01"))
    await NpcStore(store).flush_tick(loop.drain_events())
    await store.write_snapshot(
        "main", loop.state.tick, cutoff + 1, loop.state.model_dump_json().encode()
    )
    async with store.session_factory.begin() as session:
        await session.execute(update(Branch).values(is_current=False))
        session.add(
            Branch(
                id="child",
                forked_from_branch="main",
                forked_from_seq=cutoff,
                status="active",
                is_current=True,
            )
        )
    await store.session_factory.kw["bind"].dispose()

    restored, reopened = await build_loop()
    try:
        assert await reopened.current_branch_id() == "child"
        assert restored.state.state_hash() == expected
        assert "villager_01" in restored.state.entities
        assert restored.pending_events == []
    finally:
        await reopened.session_factory.kw["bind"].dispose()


@pytest.mark.asyncio
async def test_snapshot_and_events_roll_back_together(tmp_path, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    from sim.core.persistence.world_restore import flush_world

    monkeypatch.chdir(tmp_path)
    loop, store = await build_loop()
    # 冲突游标使检查点写入失败，事件也必须回滚，不能留半批。
    await store.write_snapshot("main", 0, len(loop.pending_events), b"{}")
    try:
        with pytest.raises(IntegrityError):
            await flush_world(store, "main", loop, loop.pending_events)
        assert await store.read_range("main", 0, 10000) == []
    finally:
        await store.session_factory.kw["bind"].dispose()


@pytest.mark.parametrize("ticks", [1, 14, 15, 61, 1000])
def test_replayed_movement_matches_live_movement(ticks):
    from sim.core.clock import GameClock
    from sim.core.events import world_create_event
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState, build_default_bus

    live = TickLoop(GameClock(), build_default_bus(), WorldState())
    live.enqueue(world_create_event(0, 42, ("chenmo", "villager_01")))
    for entity_id in live.state.entities:
        live.issue_move(entity_id, [(x, 0) for x in range(30)])
    replayed = TickLoop(GameClock(), build_default_bus(), live.state)
    for _ in range(ticks):
        live._tick_once()
    replayed.replay_until(ticks)
    assert replayed.state.state_hash() == live.state.state_hash()


@pytest.mark.asyncio
async def test_child_initial_checkpoint_does_not_reapply_ancestor_genesis(tmp_path, monkeypatch):
    from sqlalchemy import update

    from sim.core.persistence.models import Branch

    monkeypatch.chdir(tmp_path)
    loop, store = await build_loop()
    await NpcStore(store).flush_tick(loop.drain_events())
    history = await store.read_branch_history("main")
    async with store.session_factory.begin() as session:
        await session.execute(update(Branch).values(is_current=False))
        session.add(
            Branch(
                id="child",
                forked_from_branch="main",
                forked_from_seq=history[-1]["seq"],
                is_current=True,
            )
        )
    await store.write_snapshot("child", loop.state.tick, 0, loop.state.model_dump_json().encode())
    loop.enqueue(npc_death_event(tick=loop.state.tick, entity_id="villager_02"))
    await NpcStore(store, branch_id="child").flush_tick(loop.drain_events())
    expected = loop.state.state_hash()
    await store.session_factory.kw["bind"].dispose()
    restored, reopened = await build_loop()
    try:
        assert restored.state.state_hash() == expected
    finally:
        await reopened.session_factory.kw["bind"].dispose()
