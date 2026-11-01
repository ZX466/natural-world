"""离线补跑：受控时长、真实 tick 钩子、append-only 落库与启动时序。"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import func, select

from sim.core.clock import GameClock, TimeScale
from sim.core.events import npc_monologue_event, world_create_event
from sim.core.persistence.models import Event, Snapshot
from sim.core.persistence.world_restore import flush_world, restore_world
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus


def make_loop():
    loop = TickLoop(GameClock(), build_default_bus(), WorldState(world_seed=42))
    loop.enqueue(world_create_event(0, 42, ("chenmo",)))
    loop.advance_frame(1 / 60)
    return loop


def advance_offline():
    return importlib.import_module("sim.world.offline").advance_offline


@pytest.mark.parametrize("speed", [0, 1, 4, 16])
async def test_one_minute_uses_existing_normal_scale_and_restores_speed(speed):
    loop = make_loop()
    loop.drain_events()
    loop.clock.set_speed(speed)
    start = loop.state.tick
    batches = []
    decisions = []
    loop.attach_npc_runtime(lambda state, tick: decisions.append(tick))

    async def flush(events, consumed, final):
        batches.append((loop.state.tick, consumed, final))

    result = await advance_offline()(loop, offline_seconds=60, flush=flush)
    assert result.advanced_ticks == 3600
    assert loop.state.tick == loop.clock.tick == start + 3600
    assert loop.clock.speed == speed
    assert decisions and len(decisions) == 360
    assert batches[-1][1:] == (60, True)
    assert all(
        b - a <= 240 for a, b in zip([start, *[r[0] for r in batches]], [r[0] for r in batches])
    )


async def test_combat_scale_is_respected_and_no_llm_is_needed():
    loop = make_loop()
    loop.enter_combat()
    start = loop.state.tick

    async def flush(*args):
        pass

    result = await advance_offline()(loop, offline_seconds=60, flush=flush)
    assert loop.state.tick == start + 60
    assert result.advanced_ticks == 60
    assert loop.clock.timescale is TimeScale.COMBAT


async def test_thirty_days_cap_at_one_game_day_and_log_discarded_seconds():
    from structlog.testing import capture_logs

    loop = make_loop()
    start = loop.state.tick

    async def flush(*args):
        pass

    with capture_logs() as logs:
        result = await advance_offline()(loop, offline_seconds=30 * 86400, flush=flush)
    assert loop.state.tick == start + 86400
    assert result.advanced_ticks == 86400
    assert result.discarded_seconds == 30 * 86400 - 1440
    assert any(row["event"] == "offline.capped" for row in logs)


@pytest.mark.parametrize("seconds", [-1, float("nan"), float("inf"), True, "60"])
async def test_invalid_elapsed_time_is_rejected_before_mutation(seconds):
    loop = make_loop()
    before = loop.state.state_hash()

    async def flush(*args):
        raise AssertionError("invalid input must not flush")

    with pytest.raises((TypeError, ValueError)):
        await advance_offline()(loop, offline_seconds=seconds, flush=flush)
    assert loop.state.state_hash() == before


async def test_checkpoint_watermark_is_control_metadata_and_idle_tail_is_durable(store, session):
    loop = make_loop()
    await flush_world(store, "main", loop, loop.drain_events(), checkpoint_at=1000.0)
    initial_rows = (await session.scalars(select(Event))).all()
    initial_count = len(initial_rows)
    start = loop.state.tick

    async def flush(events, consumed, final):
        await flush_world(
            store, "main", loop, events, checkpoint_at=1000 + consumed, force_checkpoint=final
        )

    result = await advance_offline()(loop, offline_seconds=0.1, flush=flush)
    assert result.advanced_ticks == 6
    restored = await restore_world(store, "main")
    assert restored.state.tick == start + 6
    assert restored.state.state_hash() == loop.state.state_hash()
    session.expire_all()
    assert await session.scalar(select(func.count()).select_from(Event)) == initial_count
    snapshot = await session.scalar(select(Snapshot))
    assert snapshot.created_at == 1000.1
    assert all("offline" not in row.payload and "1000" not in row.payload for row in initial_rows)


async def test_real_hook_events_are_appended_and_replay_is_identical(store, session):
    loop = make_loop()
    await flush_world(store, "main", loop, loop.drain_events())
    before = await session.scalar(select(func.count()).select_from(Event))
    loop.attach_npc_runtime(
        lambda state, tick: [npc_monologue_event(tick, "chenmo", "bubble", "风从河面吹过。")]
    )

    async def flush(events, consumed, final):
        await flush_world(
            store, "main", loop, events, checkpoint_at=1000 + consumed, force_checkpoint=final
        )

    await advance_offline()(loop, offline_seconds=1, flush=flush)
    session.expire_all()
    assert await session.scalar(select(func.count()).select_from(Event)) > before
    first = await restore_world(store, "main")
    second = await restore_world(store, "main")
    assert first.state.state_hash() == second.state.state_hash() == loop.state.state_hash()
