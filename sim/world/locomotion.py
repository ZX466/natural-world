"""Logical-tick flight completion; terrain authority is provided by the map adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sim.core.events import Gait, JumpMotion, WorldEvent, jump_landed_event, jump_started_event

if TYPE_CHECKING:
    from sim.core.world import WorldState
    from sim.world.pathfinding import Pathfinder


def trajectory_clear(pathfinder: Pathfinder, flight: JumpMotion) -> bool:
    """Supercover the short segment; test the minimum arc height in each column."""
    if pathfinder.height_at(*flight.goal) != flight.target_height:
        return False
    x0, y0 = flight.start
    x1, y1 = flight.goal
    dx, dy = x1 - x0, y1 - y0
    for y in range(min(y0, y1), max(y0, y1) + 1):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            enter, leave = 0.0, 1.0
            for origin, direction, cell in [(x0 + 0.5, dx, x), (y0 + 0.5, dy, y)]:
                if direction == 0:
                    if not cell <= origin <= cell + 1:
                        enter, leave = 1.0, 0.0
                        break
                    continue
                a, b = (cell - origin) / direction, (cell + 1 - origin) / direction
                enter, leave = max(enter, min(a, b)), min(leave, max(a, b))
            if enter > leave:
                continue
            floor = min(
                flight.start_height
                + (flight.target_height - flight.start_height) * p
                + 4 * flight.arc_height * p * (1 - p)
                for p in [enter, leave]
            )
            if pathfinder.height_at(x, y) > floor + 1e-9:
                return False
    return True


def plan_jump(
    state: WorldState, entity_id: str, goal: tuple[int, int], gait: Gait, pathfinder: Pathfinder
) -> WorldEvent:
    actor = state.entities.get(entity_id)
    if (
        actor is None
        or actor.incapacitated_until is not None
        or (actor.jump is not None and actor.jump.airborne)
    ):
        raise ValueError("actor cannot jump")
    if gait not in ("walk", "run") or len(goal) != 2 or any(type(v) is not int for v in goal):
        raise ValueError("invalid jump request")
    if not pathfinder.tile_map.in_bounds(*actor.pos) or not pathfinder.tile_map.in_bounds(*goal):
        raise ValueError("jump out of bounds")
    target_height = pathfinder.height_at(*goal)
    if target_height == 0:
        raise ValueError("jump has no landing surface")
    event = jump_started_event(
        state.tick,
        entity_id,
        actor.pos,
        goal,
        pathfinder.height_at(*actor.pos),
        target_height,
        gait=gait,
    )
    flight = JumpMotion.model_validate(
        {k: v for k, v in event.payload.items() if k not in {"entity_id", "gait"}}
    )
    if not trajectory_clear(pathfinder, flight):
        raise ValueError("jump trajectory is obstructed")
    return event


def landing_events(state: WorldState, tick: int, pathfinder: Pathfinder | None) -> list[WorldEvent]:
    events = []
    for entity_id, entity in sorted(state.entities.items()):
        flight = entity.jump
        if flight is None or not flight.airborne:
            continue
        obstructed = pathfinder is not None and not trajectory_clear(pathfinder, flight)
        if not obstructed and tick < flight.started_at + flight.duration:
            continue
        goal = flight.start if obstructed else flight.goal
        height = pathfinder.height_at(*goal) if pathfinder is not None else flight.target_height
        events.append(
            jump_landed_event(
                tick,
                entity_id,
                flight.start,
                goal,
                height,
                flight.started_at,
                reason="obstructed" if obstructed else "landed",
            )
        )
    return events
