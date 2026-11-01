"""uv run python .orca/audits/soak-loss-2026-11-01/measure.py

沿用 run_soak 的内存引擎口径；不访问数据库，不调用模型，不改任何阈值。
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sim.agent.combat_exec import CombatLedger
from sim.core.events import npc_death_event
from sim.tests.bench.soak import TICKS_PER_GAME_DAY, make_mock_feeder, run_soak
from sim.tests.bench.test_bench_soak import SOAK_ENTITY_LOSS_PER_GAME_DAY
from sim.tests.golden.driver import smoke_loop


def simulate(*, seed: int, days: int, lethal: bool) -> dict:
    loop = smoke_loop(n_entities=50, world_seed=seed)
    loop.state = loop.state.model_copy(
        update={
            "entities": {
                entity_id: entity.model_copy(update={"pos": (index % 8, index // 8), "path": ()})
                for index, (entity_id, entity) in enumerate(loop.state.entities.items())
            }
        }
    )
    ledger = CombatLedger()
    attacks = []
    deaths = []

    def fight(state, tick):
        if tick % 3600 != 0:
            return None
        living = sorted(state.entities)
        pairs = [
            (left, right)
            for index, left in enumerate(living)
            for right in living[index + 1 :]
            if sum(
                abs(a - b)
                for a, b in zip(state.entities[left].pos, state.entities[right].pos, strict=True)
            )
            <= 2
        ]
        if not pairs:
            return None
        digest = hashlib.sha256(f"soak-combat:{seed}:{tick}".encode()).digest()
        attacker, target = pairs[int.from_bytes(digest[:8], "big") % len(pairs)]
        if digest[8] & 1:
            attacker, target = target, attacker
        outcome = ledger.apply_attack(attacker, target, tick=tick, seed=seed)
        attacks.append(
            {
                "tick": tick,
                "attacker": attacker,
                "target": target,
                "outcome": outcome.outcome,
                "damage": outcome.damage,
                "target_hp": outcome.target_hp,
            }
        )
        if outcome.outcome != "kill":
            return None
        deaths.append({"tick": tick, "entity_id": target})
        return [npc_death_event(tick, entity_id=target)]

    if lethal:
        loop.attach_maintenance(fight)
    start = time.perf_counter()
    result = run_soak(
        loop,
        days * TICKS_PER_GAME_DAY,
        window_ticks=TICKS_PER_GAME_DAY,
        feeder=make_mock_feeder(grid_w=8, grid_h=8),
    )
    wall_seconds = time.perf_counter() - start
    net_loss = result.entity_count_start - result.entity_count_end
    assert result.total_ticks == days * TICKS_PER_GAME_DAY
    assert net_loss == len(deaths)
    return {
        "seed": seed,
        "days": days,
        "ticks": result.total_ticks,
        "entities_start": result.entity_count_start,
        "entities_end": result.entity_count_end,
        "deaths": len(deaths),
        "births": 0,
        "net_loss": net_loss,
        "net_loss_per_game_day": net_loss / days,
        "derivation": f"{net_loss} deaths / {days} game days = {net_loss / days} entities/game-day",
        "attacks": attacks,
        "death_trace": deaths,
        "state_hash": loop.state.state_hash(),
        "wall_seconds": wall_seconds,
        "pending_peak": result.pending_peak,
        "windows": [
            {
                "start_tick": window.start_tick,
                "ticks": window.n_ticks,
                "mean_tick_ms": window.mean_ms,
                "p99_tick_ms": window.p99_ms,
            }
            for window in result.windows
        ],
    }


if __name__ == "__main__":
    control = simulate(seed=7, days=3, lethal=False)
    first = simulate(seed=7, days=3, lethal=True)
    repeated = simulate(seed=7, days=3, lethal=True)
    keys = (
        "entities_start",
        "entities_end",
        "deaths",
        "net_loss",
        "attacks",
        "death_trace",
        "state_hash",
    )
    assert all(first[key] == repeated[key] for key in keys)
    assert first["deaths"] > 0
    assert SOAK_ENTITY_LOSS_PER_GAME_DAY == 0
    measurement = {
        "status": "pass",
        "stage_b_removes_entities": True,
        "scenario": (
            "50 actors, 8x8 moving arena; once per game hour choose an in-range pair "
            "by seeded SHA-256; real CombatLedger settlement then enqueue npc.death"
        ),
        "control": control,
        "lethal": first,
        "repeated": repeated,
        "same_seed_repeated_semantics_equal": True,
        "threshold_unchanged": SOAK_ENTITY_LOSS_PER_GAME_DAY,
        "threshold_decision": "pending user; intentionally no new numeric assertion bound",
        "limitations": (
            "Controlled hazard fixture; not a natural population loss estimate. "
            "Existing soak in-memory simulation, no SQLite/development database, no LLM or browser."
        ),
    }
    Path(__file__).with_name("measurement.json").write_text(
        json.dumps(measurement, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "control_loss": control["net_loss"],
                "lethal": first["derivation"],
                "deterministic": True,
                "threshold": SOAK_ENTITY_LOSS_PER_GAME_DAY,
            },
            ensure_ascii=False,
        )
    )
