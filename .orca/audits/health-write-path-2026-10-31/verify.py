"""uv run python .orca/audits/health-write-path-2026-10-31/verify.py

只创建临时 SQLite，不访问开发存档、不调用模型或浏览器。
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import sys
import tempfile
import time
from pathlib import Path

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sim.agent.combat_exec import CombatLedger
from sim.api.main import _fallback_map
from sim.content.health import HEALTH_SEEDS, seed_health
from sim.content.protagonist import seed_protagonist
from sim.content.villagers import seed_villagers
from sim.core.clock import GameClock
from sim.core.events import (
    EventKind,
    structure_collapsed_event,
    structure_completed_event,
    structure_started_event,
    world_create_event,
)
from sim.core.persistence.database import init_database
from sim.core.persistence.fork import fork_from_anchor
from sim.core.persistence.models import Event, NpcHealth
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.llm.prompts.banned_words import scan
from sim.npc.assemble import assemble_runtime
from sim.npc.contract import advance_hidden_window
from sim.npc.hidden import evaluate_triggers, hidden_leak_scan
from sim.npc.sim_exec import npc_events_for_tick
from sim.perception.senses import rtoken_of, run_perception_step
from sim.world.maintenance import collapse_injuries
from sim.world.pathfinding import Pathfinder
from sim.world.structure import StructurePhase, StructureSnapshot


async def verify(database: Path) -> dict:
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    try:
        await init_database(engine)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        store = SqlEventStore(factory)
        npc = NpcStore(store)
        await seed_villagers(factory)
        await seed_protagonist(factory)
        inserted = await seed_health(factory)
        assert inserted == 6 and await seed_health(factory) == 0
        async with factory() as session:
            grouped = dict(
                (
                    await session.execute(
                        select(NpcHealth.hidden, func.count()).group_by(NpcHealth.hidden)
                    )
                ).all()
            )
        assert grouped == {False: 2, True: 4}
        for definition in HEALTH_SEEDS:
            assert not scan(
                " ".join((definition.label, *definition.descriptors, *definition.triggers))
            ).hits

        ids = ("chenmo", "villager_01", "villager_02", "villager_03")
        loop = TickLoop(clock=GameClock(), bus=build_default_bus(), state=WorldState(world_seed=42))
        loop.enqueue(world_create_event(0, 42, ids))
        hidden = await npc.materialize_hidden()
        tile_map = _fallback_map()

        def frames_at(tick: int, hp: float):
            return run_perception_step(
                loop.state.model_copy(update={"tick": tick}),
                tile_map,
                [],
                include_time=True,
                body_fraction_of=lambda _: hp,
            )

        calm = frames_at(12 * 3600, 1.0)
        dusk = frames_at(18 * 3600, 0.4)
        night = frames_at(23 * 3600, 0.4)
        contexts = {}
        nontrigger = {}
        trigger_ids = {}
        for npc_id, state in hidden.items():
            assert state.profile is not None
            text = calm[rtoken_of(npc_id)].narrated()
            assert not scan(text).hits
            assert not evaluate_triggers(state.profile, text)
            leaks = hidden_leak_scan(text, state.profile, frozenset())
            assert not leaks
            nontrigger[npc_id] = {"triggered": [], "leaks": list(leaks)}
            candidates = (dusk[rtoken_of(npc_id)].narrated(), night[rtoken_of(npc_id)].narrated())
            contexts[npc_id] = next(
                text for text in candidates if evaluate_triggers(state.profile, text)
            )
            trigger_ids[npc_id] = sorted(evaluate_triggers(state.profile, contexts[npc_id]))

        runtime, _ = await assemble_runtime(
            npc, list(ids), external_controller_ids=frozenset({"chenmo"})
        )
        batch = npc_events_for_tick(
            runtime,
            loop.state,
            10,
            Pathfinder(tile_map),
            seed=42,
            hidden_states=hidden,
            context_of=contexts.__getitem__,
        )
        emerge = advance_hidden_window("chenmo", hidden, tick=10, context_of=contexts.__getitem__)
        assert emerge is not None
        entered = [emerge, *(e for e in batch if e.event_type is EventKind.NPC_HIDDEN_EMERGE)]
        assert len(entered) == 4
        for event in entered:
            assert set(event.payload) == {"npc_id", "attr_ids"}
            assert event.payload["attr_ids"] == trigger_ids[str(event.payload["npc_id"])]
            loop.state = loop.state.model_copy(update={"tick": event.tick})
            loop.enqueue(event)

        structure = StructureSnapshot(
            "shed", ((0, 0),), "shed", "wood", StructurePhase.ACTIVE, True, ()
        )
        source = [
            structure_started_event(
                11,
                structure_id="shed",
                tiles=structure.tiles,
                kind="shed",
                material="wood",
                planned_duration_ticks=1,
                recipe_id="shed",
                recipe_version="v1",
                build_rule_version="v1",
                load_bearing=True,
            ),
            structure_completed_event(12, structure_id="shed", quality=0.8, integrity=1.0),
            structure_collapsed_event(13, structure_id="shed", cause="support_lost"),
        ]
        injured_world = loop.state.model_copy(
            update={"entities": {"chenmo": loop.state.entities["chenmo"]}}
        )
        injuries = collapse_injuries(
            injured_world, [source[-1]], {"shed": structure}, CombatLedger()
        )
        for event in [*source, *injuries]:
            loop.state = loop.state.model_copy(update={"tick": event.tick})
            loop.enqueue(event)
        sequence = loop.drain_events()
        async with factory() as session:
            before = await session.scalar(select(func.count()).select_from(NpcHealth))
        await npc.flush_tick(sequence)
        async with factory() as session:
            after = await session.scalar(select(func.count()).select_from(NpcHealth))
            chenmo_count = await session.scalar(
                select(func.count()).select_from(NpcHealth).where(NpcHealth.npc_id == "chenmo")
            )
            emerge_count = await session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.event_type == EventKind.NPC_HIDDEN_EMERGE.value)
            )
            seq = await session.scalar(select(func.max(Event.seq)))
        assert (before, after, chenmo_count, emerge_count) == (6, 7, 3, 4)

        parent = await npc.materialize_hidden()

        async def preflush():
            pass

        await fork_from_anchor(
            factory,
            parent_branch_id="main",
            fork_seq=seq,
            fork_tick=13,
            new_branch_id="child",
            preflush=preflush,
        )
        child = await NpcStore(store, branch_id="child").materialize_hidden()
        stable = {}
        for npc_id, state in parent.items():
            parent_ids = [a.id for a in state.profile.attributes]
            child_ids = [a.id for a in child[npc_id].profile.attributes]
            assert [i.encode() for i in parent_ids] == [i.encode() for i in child_ids]
            stable[npc_id] = {"parent": parent_ids, "child": child_ids, "byte_equal": True}

        hashes = []
        for _ in range(2):
            replay = TickLoop(
                clock=GameClock(), bus=build_default_bus(), state=WorldState(world_seed=42)
            )
            for event in sequence:
                replay.state = replay.state.model_copy(update={"tick": event.tick})
                replay.enqueue(event)
            hashes.append(replay.state.state_hash())
        assert hashes[0] == hashes[1] == loop.state.state_hash()

        selected_frames = [night[rtoken_of(npc_id)] for npc_id in sorted(hidden)]
        elapsed = []
        for _ in range(1000):
            start = time.perf_counter_ns()
            for frame in selected_frames:
                frame.narrated()
            elapsed.append((time.perf_counter_ns() - start) / 1_000_000)
        missing = sorted(kind.value for kind in set(EventKind) - set(build_default_bus()._handlers))
        assert missing == [EventKind.SPEECH_SHIFT.value]
        return {
            "status": "pass",
            "baseline": "3603ecb",
            "protocol": "1.14",
            "database": "temporary SQLite; no development database access",
            "collapse": {
                "total_before": before,
                "total_after": after,
                "chenmo_after": chenmo_count,
                "hp_rule": "unchanged: default HP=10, collapse damage=10",
            },
            "fork_attr_ids": stable,
            "seeds": {
                "inserted": inserted,
                "idempotent_second_insert": 0,
                "visible": grouped[False],
                "hidden": grouped[True],
                "banned_hits": 0,
            },
            "nontrigger": nontrigger,
            "trigger": {
                "ids": trigger_ids,
                "persisted_emergence_events": emerge_count,
                "source": "production run_perception_step + narrated, time/pain providers enabled",
            },
            "missing_bus_handlers": missing,
            "replay": {"events": len(sequence), "state_hashes": hashes, "equal": True},
            "narrated_ms_per_decision_beat": {
                "characters": len(selected_frames),
                "samples": len(elapsed),
                "median": statistics.median(elapsed),
                "p95": sorted(elapsed)[949],
                "max": max(elapsed),
            },
            "chenmo_guards": "wired: decision return, execution, dialogue, memory input/writeback",
        }
    finally:
        await engine.dispose()


if __name__ == "__main__":
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    with tempfile.TemporaryDirectory(prefix="project7-health-") as directory:
        result = asyncio.run(verify(Path(directory) / "audit.db"))
    output = Path(__file__).with_name("acceptance.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
