"""Event-backed player pace/flight and legacy canonical-state compatibility."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim.core.clock import GameClock
from sim.core.events import EventKind, Gait, WorldEvent, jump_started_event, move_event
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus

FIXTURE = Path(__file__).parent / "fixtures/legacy-locomotion-world.json"


def make_loop(state: WorldState | None = None) -> TickLoop:
    current = state or WorldState(entities={"chenmo": EntityState(entity_id="chenmo", pos=(0, 0))})
    clock = GameClock()
    clock.restore_tick(current.tick)
    return TickLoop(clock=clock, bus=build_default_bus(), state=current)


def begin_jump(
    loop: TickLoop,
    *,
    goal: tuple[int, int],
    start_height: int = 1,
    target_height: int = 2,
    gait: Gait = "walk",
    entity_id: str = "chenmo",
) -> None:
    actor = loop.state.entities[entity_id]
    loop.enqueue(
        jump_started_event(
            loop.state.tick, entity_id, actor.pos, goal, start_height, target_height, gait=gait
        )
    )


def test_old_world_json_and_hash_remain_byte_compatible() -> None:
    reference = json.loads(FIXTURE.read_text(encoding="utf-8"))
    state = WorldState.model_validate(reference["state"])
    assert state.model_dump(mode="json") == reference["state"]
    assert state.state_hash() == reference["state_hash"]


def test_npc_600_tick_trajectory_hash_matches_captured_old_kernel() -> None:
    reference = json.loads(FIXTURE.read_text(encoding="utf-8"))["movement_reference"]
    state = WorldState(
        world_seed=reference["world_seed"],
        entities={
            eid: EntityState(
                entity_id=eid,
                pos=(0, index),
                path=tuple((x, index) for x in range(reference["path_length"])),
            )
            for index, eid in enumerate(reference["entity_ids"])
        },
    )
    loop = make_loop(state)
    for _ in range(10):
        loop.advance_frame(1)
    assert loop.state.tick == reference["after_tick"]
    assert loop.state.state_hash() == reference["after_hash"]


@pytest.mark.parametrize(("gait", "tiles"), [("walk", 2), ("run", 4)])
def test_explicit_player_pace_moves_two_or_four_cells_per_second(gait: Gait, tiles: int) -> None:
    loop = make_loop()
    path = tuple((x, 0) for x in range(101))
    loop.enqueue(move_event(0, "chenmo", path[0], path[-1], path, gait=gait))
    assert loop.state.entities["chenmo"].path[0] == (1, 0)
    loop.advance_frame(1)
    assert loop.state.entities["chenmo"].pos == (tiles, 0)
    assert loop.clock.tick == 60


def test_pace_is_recorded_but_legacy_move_payload_shape_is_unchanged() -> None:
    args = (0, "chenmo", (0, 0), (1, 0), ((0, 0), (1, 0)))
    assert "gait" not in move_event(*args).payload
    event = move_event(*args, gait="walk")
    assert event.payload["gait"] == "walk"
    loop = make_loop()
    loop.enqueue(event)
    assert loop.state.model_dump(mode="json")["entities"]["chenmo"]["gait"] == "walk"


@pytest.mark.parametrize("target_height", [2, 3])
def test_jump_lands_on_high_block_and_can_jump_back_down(target_height: int) -> None:
    loop = make_loop()
    begin_jump(loop, goal=(1, 0), target_height=target_height)
    loop.advance_frame(0.5)
    actor = loop.state.entities["chenmo"]
    assert actor.pos == (0, 0)
    assert actor.jump is not None
    assert actor.jump.airborne
    loop.advance_frame(0.1)
    actor = loop.state.entities["chenmo"]
    assert actor.pos == (1, 0)
    assert actor.jump is not None
    assert not actor.jump.airborne
    assert actor.jump.landed_at == 36
    assert actor.jump.landed_height == target_height
    begin_jump(loop, goal=(0, 0), start_height=target_height, target_height=1)
    loop.advance_frame(0.6)
    actor = loop.state.entities["chenmo"]
    assert actor.jump is not None
    assert actor.pos == (0, 0) and not actor.jump.airborne
    assert actor.jump.landed_height == 1
    landed = [e for e in loop.pending_events if e.event_type.value == "actor.jump_landed"]
    assert len(landed) == 2


def test_mid_flight_json_restore_finishes_at_same_tick_and_hash() -> None:
    live = make_loop()
    begin_jump(live, goal=(1, 0), target_height=3)
    live.advance_frame(0.25)
    restored = make_loop(WorldState.model_validate_json(live.state.model_dump_json()))
    live.advance_frame(0.5)
    restored.advance_frame(0.5)
    assert live.state.state_hash() == restored.state.state_hash()
    assert restored.state.entities["chenmo"].pos == (1, 0)
    jump = restored.state.entities["chenmo"].jump
    assert jump is not None
    assert jump.landed_at == 36


def test_logged_flight_replays_without_redeciding_terrain() -> None:
    live = make_loop()
    initial = live.state
    begin_jump(live, goal=(1, 0), target_height=3)
    live.advance_frame(1)
    history = live.drain_events()
    replay = make_loop(initial)
    for event in history:
        replay.replay_until(event.tick)
        replay.enqueue(event)
    replay.replay_until(live.state.tick)
    assert replay.state.state_hash() == live.state.state_hash()


def test_ground_move_cannot_interrupt_an_airborne_jump() -> None:
    loop = make_loop()
    begin_jump(loop, goal=(1, 0))
    before = loop.state.entities["chenmo"]
    loop.enqueue(move_event(0, "chenmo", (0, 0), (0, 1), ((0, 0), (0, 1)), gait="run"))
    assert loop.state.entities["chenmo"] == before
    loop.advance_frame(0.6)
    assert loop.state.entities["chenmo"].pos == (1, 0)


def test_incapacitated_actor_does_not_start_jump_but_flight_gravity_can_finish() -> None:
    loop = make_loop()
    begin_jump(loop, goal=(1, 0))
    loop.enqueue(
        WorldEvent(
            tick=0,
            event_type=EventKind.AGENT_INCAPACITATED,
            payload={"entity_id": "chenmo", "recover_at": 120},
        )
    )
    loop.advance_frame(0.6)
    actor = loop.state.entities["chenmo"]
    assert actor.pos == (1, 0)
    assert actor.jump is not None
    assert not actor.jump.airborne
    before = loop.state
    begin_jump(loop, goal=(0, 0), start_height=2, target_height=1)
    assert loop.state == before


def test_recovery_replaces_flight_instead_of_landing_at_an_old_destination() -> None:
    loop = make_loop()
    begin_jump(loop, goal=(1, 0))
    loop.enqueue(
        WorldEvent(
            tick=0,
            event_type=EventKind.AGENT_INCAPACITATED,
            payload={"entity_id": "chenmo", "recover_at": 2},
        )
    )
    loop.advance_frame(2 / 60)
    loop.enqueue(
        WorldEvent(
            tick=2,
            event_type=EventKind.AGENT_RECOVERED,
            payload={"entity_id": "chenmo", "pos": (0, 1)},
        )
    )
    assert loop.state.entities["chenmo"].jump is None
    loop.advance_frame(1)
    assert loop.state.entities["chenmo"].pos == (0, 1)


def test_completed_flight_does_not_prevent_the_next_ground_path() -> None:
    loop = make_loop()
    begin_jump(loop, goal=(1, 0))
    loop.advance_frame(0.6)
    loop.enqueue(
        move_event(loop.state.tick, "chenmo", (1, 0), (2, 0), ((1, 0), (2, 0)), gait="run")
    )
    loop.advance_frame(1)
    assert loop.state.entities["chenmo"].pos == (2, 0)


def test_death_during_flight_never_emits_a_landing_for_removed_actor() -> None:
    loop = make_loop(WorldState(entities={"jumper": EntityState(entity_id="jumper", pos=(0, 0))}))
    begin_jump(loop, goal=(1, 0), entity_id="jumper")
    loop.enqueue(
        WorldEvent(tick=0, event_type=EventKind.NPC_DEATH, payload={"entity_id": "jumper"})
    )
    loop.advance_frame(1)
    assert not any(e.event_type.value == "actor.jump_landed" for e in loop.pending_events)
