"""Real SQL restores and historical forks of legacy, airborne and landed actors."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sim.core.clock import GameClock
from sim.core.events import EventKind, Gait, jump_started_event, move_event, world_create_event
from sim.core.persistence.anchor_package import (
    collect_corpus_rows,
    encode_corpus_blob,
    write_anchor_package,
)
from sim.core.persistence.database import init_database
from sim.core.persistence.fork_orchestration import orchestrate_materialized_load_anchor
from sim.core.persistence.models import PlayerAnchor
from sim.core.persistence.store import SqlEventStore
from sim.core.persistence.world_restore import (
    flush_world,
    materialization_hooks,
    restore_world,
)
from sim.core.rng import RngRegistry
from sim.core.rng_state import capture_rng_state
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.world.weather import WEATHER_STREAM

pytestmark = pytest.mark.t1

LEGACY_FIXTURE = Path(__file__).parent / "fixtures" / "legacy-locomotion-world.json"
FLIGHTS = [("walk", (1, 0), 2), ("run", (2, 0), 3)]


@asynccontextmanager
async def open_store(database: Path) -> AsyncIterator[SqlEventStore]:
    """Closing and reopening the file must discard every engine/session cache."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    try:
        await init_database(engine)
        yield SqlEventStore(async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()


@pytest.mark.parametrize("next_action", ["move", "stop", "jump"])
async def test_cold_sql_tail_after_a_completed_player_step_uses_the_current_frontier(
    tmp_path: Path, next_action: str
) -> None:
    """Native held input records another command after a real step, between ticks."""
    database = tmp_path / "player-frontier.db"
    live = TickLoop(GameClock(), build_default_bus(), WorldState())
    live.enqueue(world_create_event(0, 42, ("chenmo", "villager_1")))
    async with open_store(database) as store:
        await flush_world(store, "main", live, live.drain_events())
        live.issue_move("villager_1", [(0, y) for y in range(10)])
        live.issue_move("chenmo", [(x, 0) for x in range(10)], gait="walk")
        live.advance_frame(12 / 60)
        assert live.state.entities["chenmo"].pos == (1, 0)
        if next_action == "jump":
            live.enqueue(jump_started_event(12, "chenmo", (1, 0), (2, 0), 1, 2))
        else:
            path = [(1, 0)] if next_action == "stop" else [(1, 0), (2, 0)]
            live.issue_move("chenmo", path, gait="walk" if next_action == "stop" else "run")
        expected = live.state
        await store.append("main", [event.to_store_dict() for event in live.drain_events()])
    async with open_store(database) as cold:
        restored = await restore_world(cold, "main")
        assert restored.state.model_dump(mode="json") == expected.model_dump(mode="json")
        assert restored.state.state_hash() == expected.state_hash()


def jumping_world(gait: Gait, goal: tuple[int, int], height: int) -> TickLoop:
    loop = TickLoop(GameClock(), build_default_bus(), WorldState())
    loop.enqueue(world_create_event(0, 731, ("chenmo",)))
    loop.enqueue(jump_started_event(0, "chenmo", (0, 0), goal, 1, height, gait=gait))
    return loop


async def save_airborne_anchor(store: SqlEventStore, loop: TickLoop) -> int:
    history = await store.read_branch_history("main")
    seq = history[-1]["seq"]
    snapshot = await store.latest_snapshot("main", loop.state.tick, max_seq=seq)
    assert snapshot is not None
    registry = RngRegistry(world_seed=loop.state.world_seed)
    rng_state = capture_rng_state(registry, loop.context.rng_cache, (WEATHER_STREAM,))
    async with store.session_factory.begin() as session:
        session.add(
            PlayerAnchor(
                id="airborne",
                name="半空",
                branch_id="main",
                tick=loop.state.tick,
                seq=seq,
                agent_override="{}",
                protected=True,
                updated_at=0.0,
                created_at=0.0,
            )
        )
        await write_anchor_package(
            session,
            anchor_id="airborne",
            branch_id="main",
            tick=loop.state.tick,
            seq=seq,
            rng_state=rng_state,
            agent_override="{}",
            corpus_blob=encode_corpus_blob(await collect_corpus_rows(session, "main")),
            state_hash=loop.state.state_hash(),
            snapshot=snapshot,
        )
    return seq


@pytest.mark.parametrize("snapshot_format", ["legacy", "checkpoint"])
async def test_legacy_sql_snapshot_cold_restore_preserves_baseline_hash(
    tmp_path: Path, snapshot_format: str
) -> None:
    reference = json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))
    assert reference["baseline"] == "51d1e2f"
    state = reference["state"]
    payload = state
    if snapshot_format == "checkpoint":
        # Encode the old checkpoint shape directly, without the new model serializer.
        payload = {
            "format": "world.v1",
            "state": state,
            "combat_active": False,
            "chaos_chain": 0.0,
            "rng_states": {},
        }
    database = tmp_path / "legacy.db"
    async with open_store(database) as store:
        genesis = world_create_event(0, state["world_seed"], tuple(state["entities"]))
        await store.append("main", [genesis.to_store_dict()])
        await store.write_snapshot(
            "main", state["tick"], 1, json.dumps(payload, ensure_ascii=False).encode()
        )

    async with open_store(database) as cold:
        restored = await restore_world(cold, "main")
        assert restored.state.model_dump(mode="json") == state
        assert restored.state.state_hash() == reference["state_hash"]
        assert restored.clock.tick == state["tick"]
        assert restored.pending_events == []


@pytest.mark.parametrize(("gait", "goal", "height"), FLIGHTS)
async def test_airborne_checkpoint_and_later_landing_tail_restore_the_live_hash(
    tmp_path: Path, gait: Gait, goal: tuple[int, int], height: int
) -> None:
    database = tmp_path / "flight-tail.db"
    live = jumping_world(gait, goal, height)
    live.advance_frame(18 / 60)
    airborne = live.state
    assert airborne.tick == 18
    assert airborne.entities["chenmo"].jump is not None
    assert airborne.entities["chenmo"].jump.airborne
    async with open_store(database) as store:
        await flush_world(store, "main", live, live.drain_events())

    async with open_store(database) as cold:
        resumed = await restore_world(cold, "main")
        assert resumed.state.state_hash() == airborne.state_hash()
        assert resumed.state.entities["chenmo"].gait == gait
        live.advance_frame(18 / 60)
        resumed.advance_frame(18 / 60)
        assert resumed.state.state_hash() == live.state.state_hash()
        tail = resumed.drain_events()
        landings = [event for event in tail if event.event_type is EventKind.JUMP_LANDED]
        assert len(landings) == 1
        assert landings[0].tick == 36
        # Leave the old airborne checkpoint as the newest snapshot, forcing tail replay.
        await cold.append("main", [event.to_store_dict() for event in tail])

    async with open_store(database) as cold:
        restored = await restore_world(cold, "main")
        assert restored.state.tick == live.state.tick == 36
        assert restored.state.state_hash() == live.state.state_hash()
        assert restored.state.entities["chenmo"].pos == goal
        jump = restored.state.entities["chenmo"].jump
        assert jump is not None and not jump.airborne
        assert jump.landed_at == 36
        assert jump.landed_height == height
        assert restored.pending_events == []


@pytest.mark.parametrize(("gait", "goal", "height"), FLIGHTS)
async def test_high_standing_checkpoint_retains_completed_flight_after_cold_restore(
    tmp_path: Path, gait: Gait, goal: tuple[int, int], height: int
) -> None:
    database = tmp_path / "landed.db"
    live = jumping_world(gait, goal, height)
    live.advance_frame(36 / 60)
    expected = live.state
    assert expected.tick == 36
    async with open_store(database) as store:
        await flush_world(store, "main", live, live.drain_events())

    async with open_store(database) as cold:
        restored = await restore_world(cold, "main")
        assert restored.state.model_dump(mode="json") == expected.model_dump(mode="json")
        assert restored.state.state_hash() == expected.state_hash()
        actor = restored.state.entities["chenmo"]
        assert actor.pos == goal and actor.gait == gait
        assert actor.jump is not None and not actor.jump.airborne
        assert actor.jump.landed_at == 36 and actor.jump.landed_height == height
        restored.advance_frame(1 / 60)
        assert restored.state.entities["chenmo"] == actor
        assert not any(
            event.event_type is EventKind.JUMP_LANDED for event in restored.drain_events()
        )


@pytest.mark.parametrize(("gait", "goal", "height"), FLIGHTS)
async def test_midflight_anchor_fork_preserves_flight_and_excludes_parent_future(
    tmp_path: Path, gait: Gait, goal: tuple[int, int], height: int
) -> None:
    database = tmp_path / "fork.db"
    parent = jumping_world(gait, goal, height)
    parent.advance_frame(18 / 60)
    airborne = parent.state
    async with open_store(database) as store:
        await flush_world(store, "main", parent, parent.drain_events())
        cutoff = await save_airborne_anchor(store, parent)
        parent.advance_frame(18 / 60)
        later_goal = (goal[0] + 1, goal[1])
        parent.enqueue(move_event(36, "chenmo", goal, later_goal, (goal, later_goal), gait="run"))
        parent.advance_frame(24 / 60)
        assert parent.state.entities["chenmo"].pos == later_goal
        await flush_world(store, "main", parent, parent.drain_events())
        parent_history = await store.read_branch_history("main")
        assert any(
            row["seq"] > cutoff and row["event_type"] == EventKind.JUMP_LANDED
            for row in parent_history
        )

    async def already_flushed() -> None:
        return None

    async with open_store(database) as cold:
        fork, materialized = await orchestrate_materialized_load_anchor(
            cold.session_factory,
            anchor_id="airborne",
            flush_in_flight=already_flushed,
            hooks=materialization_hooks(target_tick=18),
            store=cold,
            new_branch_id="child",
            make_current=True,
        )
        assert fork.forked_from_seq == cutoff
        assert materialized.world.state.state_hash() == airborne.state_hash()
        assert await cold.current_branch_id() == "child"
        history = await cold.read_branch_history("child")
        assert all(row["branch_id"] != "main" or row["seq"] <= cutoff for row in history)
        assert not any(row["event_type"] == EventKind.JUMP_LANDED for row in history)

    async with open_store(database) as cold:
        child = await restore_world(cold, "child")
        assert child.state.state_hash() == airborne.state_hash()
        assert child.state.entities["chenmo"].jump == airborne.entities["chenmo"].jump
        assert child.state.entities["chenmo"].gait == gait
        child.advance_frame(18 / 60)
        completed = child.state
        await cold.append("child", [event.to_store_dict() for event in child.drain_events()])

    async with open_store(database) as cold:
        restored = await restore_world(cold, "child")
        assert restored.state.state_hash() == completed.state_hash()
        actor = restored.state.entities["chenmo"]
        assert actor.pos == goal and actor.gait == gait
        assert actor.jump is not None and not actor.jump.airborne
        assert actor.jump.landed_at == 36 and actor.jump.landed_height == height
        history = await cold.read_branch_history("child")
        landings = [row for row in history if row["event_type"] == EventKind.JUMP_LANDED]
        assert len(landings) == 1 and landings[0]["branch_id"] == "child"
        assert all(row["branch_id"] != "main" or row["seq"] <= cutoff for row in history)
        assert await cold.read_branch_history("main") == parent_history
