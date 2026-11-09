"""离线补跑：受控时长、真实 tick 钩子、append-only 落库与启动时序。"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import func, select

from sim.core.clock import GameClock, TimeScale
from sim.core.events import npc_monologue_event, world_create_event
from sim.core.persistence.models import Event, Snapshot
from sim.core.persistence.world_restore import expand_world, flush_world, restore_world
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
        b - a <= 240
        for a, b in zip(
            [start, *[r[0] for r in batches[:-1]]], [r[0] for r in batches], strict=True
        )
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
    """封顶机制本身：上限一到就停，剩余时长记 `offline.capped` 后丢弃。

    显式给 ``max_ticks`` 而不是靠默认值——默认上限已收敛到一小时（见下一条），
    这条测试守的是「封顶 + 记日志」这条路径，不是那个数字。
    """
    from structlog.testing import capture_logs

    loop = make_loop()
    start = loop.state.tick

    async def flush(*args):
        pass

    with capture_logs() as logs:
        result = await advance_offline()(
            loop, offline_seconds=30 * 86400, flush=flush, max_ticks=86400
        )
    assert loop.state.tick == start + 86400
    assert result.advanced_ticks == 86400
    assert result.discarded_seconds == 30 * 86400 - 1440
    assert any(row["event"] == "offline.capped" for row in logs)


async def test_default_cap_is_one_game_hour_so_a_long_stop_boots_quickly():
    """A stop longer than 24 real minutes used to replay a whole game day.

    Every tick costs ~4ms with the live NPC hooks attached, so the one-day cap
    turned every restart into a ~250s boot. The default is now one game hour:
    long enough that the world still moves while the server was down, short
    enough that the boot stays inside the same performance budget.
    """
    loop = make_loop()
    start = loop.state.tick

    async def flush(*args):
        pass

    result = await advance_offline()(loop, offline_seconds=30 * 86400, flush=flush)
    assert result.advanced_ticks == 3600
    assert loop.state.tick == start + 3600


async def test_cap_is_configurable_from_the_environment(monkeypatch):
    """Operators pick how much downtime the world replays."""
    monkeypatch.setenv("LZ_OFFLINE_CATCHUP_MAX_TICKS", "900")
    loop = make_loop()
    start = loop.state.tick

    async def flush(*args):
        pass

    result = await advance_offline()(loop, offline_seconds=30 * 86400, flush=flush)
    assert result.advanced_ticks == 900
    assert loop.state.tick == start + 900


@pytest.mark.parametrize("raw", ["0", "-5", "abc", "86401"])
async def test_invalid_cap_environment_value_is_rejected(monkeypatch, raw):
    monkeypatch.setenv("LZ_OFFLINE_CATCHUP_MAX_TICKS", raw)
    loop = make_loop()

    async def flush(*args):
        raise AssertionError("invalid cap must not flush")

    with pytest.raises(ValueError):
        await advance_offline()(loop, offline_seconds=60, flush=flush)


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
    initial_payloads = [row.payload for row in initial_rows]
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
    assert all("offline" not in payload and "1000" not in payload for payload in initial_payloads)


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
    history = await store.read_branch_history("main")
    for _ in range(2):
        replay = expand_world({}, history)
        replay.replay_until(loop.state.tick)
        assert replay.state.state_hash() == loop.state.state_hash()


async def test_flush_failure_stops_progress_and_restores_speed():
    loop = make_loop()
    loop.clock.set_speed(16)
    start = loop.state.tick
    calls = []

    async def fail(events, consumed, final):
        calls.append(consumed)
        raise RuntimeError("simulated disk failure")

    with pytest.raises(RuntimeError, match="disk failure"):
        await advance_offline()(loop, offline_seconds=60, flush=fail)
    assert calls == [4]
    assert loop.state.tick == start + 240
    assert loop.clock.speed == 16
