"""Headless timing probe: real move handler/path/clock, no browser/network/model."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def make_loop(start_tick: int):
    from sim.core.clock import GameClock
    from sim.core.tick import TickLoop
    from sim.core.world import EntityState, WorldState, build_default_bus
    from sim.tests.test_p_rebuild_tile_map_contract import make_open_map
    from sim.world.pathfinding import Pathfinder

    clock = GameClock()
    clock.restore_tick(start_tick)
    loop = TickLoop(
        clock=clock,
        bus=build_default_bus(),
        state=WorldState(
            world_seed=7,
            tick=start_tick,
            entities={"chenmo": EntityState(entity_id="chenmo", pos=(5, 5))},
        ),
    )
    return loop, Pathfinder(make_open_map())


def request(loop, pathfinder, target):
    from sim.api.ws import _handle_move_request

    reply = _handle_move_request({"target_x": target[0], "target_y": target[1]}, loop, pathfinder)
    assert reply is None


def run():
    from sim.core.tick import entity_move_phase

    delays = []
    for phase in range(15):
        loop, pf = make_loop(phase)
        request(loop, pf, (6, 5))
        for _ in range(60):
            loop.advance_frame(1 / 60)
            if loop.state.entities["chenmo"].pos != (5, 5):
                delays.append(round((loop.state.tick - phase) * 1000 / 60, 3))
                break
        else:
            raise AssertionError("no first step")
    loop, pf = make_loop(0)
    request(loop, pf, (6, 5))
    for _ in range(5):
        loop.advance_frame(1 / 60)
    origin = loop.state.entities["chenmo"].pos
    request(loop, pf, origin)
    for _ in range(60):
        loop.advance_frame(1 / 60)
    assert loop.state.entities["chenmo"].pos == origin
    loop, pf = make_loop(0)
    request(loop, pf, (15, 5))
    previous = (5, 5)
    moves = []
    for tick in range(120):
        loop.advance_frame(1 / 60)
        current = loop.state.entities["chenmo"].pos
        if current != previous:
            moves.append(tick)
        previous = current
    keyboard_loop, keyboard_pf = make_loop(0)
    request(keyboard_loop, keyboard_pf, (6, 5))
    previous = (5, 5)
    keyboard_moves = []
    for tick in range(120):
        keyboard_loop.advance_frame(1 / 60)
        current = keyboard_loop.state.entities["chenmo"].pos
        if current != previous:
            keyboard_moves.append(tick)
            request(keyboard_loop, keyboard_pf, (current[0] + 1, current[1]))
        previous = current
    return {
        "mode": "real deterministic server loop, 60tps, zero transport delay",
        "chenmo_phase": entity_move_phase("chenmo"),
        "neighbor_first_step_ms_by_start_phase": delays,
        "keyboard_and_pointer_first_step_ms": {"min": min(delays), "max": max(delays)},
        "cancel_current_cell_prevents_later_step": True,
        "straight_path_steps_during_second_second": sum(tick >= 60 for tick in moves),
        "successive_neighbor_steps_during_second_second": sum(
            tick >= 60 for tick in keyboard_moves
        ),
        "note": (
            "Start-inclusive paths consume one phase before the first changed position. "
            "No sim semantics were changed."
        ),
    }


with contextlib.redirect_stdout(io.StringIO()):
    result = run()
output = json.dumps(result, ensure_ascii=False, indent=2)
Path(__file__).with_name("server-timing.json").write_text(output + "\n", encoding="utf-8")
print(output)
