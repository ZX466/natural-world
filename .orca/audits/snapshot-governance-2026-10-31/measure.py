"""Reproduce retention evidence using only owned temporary SQLite databases."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def method_digest(source: str, name: str) -> str:
    module = ast.parse(source)
    cls = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "SqlEventStore"
    )
    method = next(
        node for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    )
    return hashlib.sha256(ast.dump(method, include_attributes=False).encode()).hexdigest()


async def measure(directory: Path) -> dict:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine

    from sim.core.clock import GameClock
    from sim.core.events import tile_changed_event, world_create_event
    from sim.core.persistence.database import create_session_factory, init_database
    from sim.core.persistence.fork import fork_from_anchor
    from sim.core.persistence.models import Branch, Snapshot
    from sim.core.persistence.store import SqlEventStore
    from sim.core.persistence.world_restore import flush_world
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState, build_default_bus
    from sim.tests.test_snapshot_retention import (
        test_history_without_any_qualified_snapshot_still_replays_exactly,
        test_pruned_historical_checkpoint_replays_to_identical_full_json,
    )

    engine = create_async_engine(f"sqlite+aiosqlite:///{directory / 'measurement.db'}")
    await init_database(engine)
    sf = create_session_factory(engine)
    store = SqlEventStore(sf)

    async def rows():
        async with sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Snapshot)
                        .where(Snapshot.branch_id == "main")
                        .order_by(Snapshot.tick, Snapshot.seq)
                    )
                ).all()
            )

    async def put(loop, tick):
        loop.state = loop.state.model_copy(update={"tick": tick})
        loop.clock.restore_tick(tick)
        loop.enqueue(tile_changed_event(tick, 0, 0, 7))
        await flush_world(store, "main", loop, loop.drain_events())

    try:
        loop = TickLoop(GameClock(), build_default_bus(), WorldState())
        loop.enqueue(world_create_event(0, 42, ("chenmo",)))
        await store.append("main", [event.to_store_dict() for event in loop.drain_events()])
        growth = []
        for index in range(1, 1001):
            await put(loop, index)
            if index in (1, 8, 9, 10, 100, 250, 1000):
                current = await rows()
                growth.append(
                    {
                        "writes": index,
                        "hot": sum(not row.is_cold for row in current),
                        "total": len(current),
                    }
                )
        assert growth == [
            {"writes": 1, "hot": 1, "total": 1},
            {"writes": 8, "hot": 8, "total": 8},
            {"writes": 9, "hot": 9, "total": 9},
            {"writes": 10, "hot": 9, "total": 9},
            {"writes": 100, "hot": 9, "total": 9},
            {"writes": 250, "hot": 9, "total": 9},
            {"writes": 1000, "hot": 9, "total": 9},
        ]
        for day in (1, 2):
            for offset in range(50):
                await put(loop, day * 86400 + offset)
        before = await rows()
        daily_first = []
        for row in before:
            if not daily_first or row.tick // 86400 != daily_first[-1] // 86400:
                daily_first.append(row.tick)
        assert daily_first == [1, 86400, 172800]
        assert len(before) == 11
        before_keys = [
            (row.seq, row.tick, hashlib.sha256(row.snapshot_data).hexdigest()) for row in before
        ]
        events_before = await store.read_range("main", 0, 2**62 - 1)

        async def preflush():
            pass

        await fork_from_anchor(
            sf,
            parent_branch_id="main",
            fork_seq=events_before[-1]["seq"],
            fork_tick=172849,
            preflush=preflush,
            new_branch_id="measurement-child",
        )
        after = await rows()
        after_keys = [
            (row.seq, row.tick, hashlib.sha256(row.snapshot_data).hexdigest()) for row in after
        ]
        events_after = await store.read_range("main", 0, 2**62 - 1)
        assert before_keys == after_keys and all(row.is_cold for row in after)
        assert events_before == events_after and len(events_after) == 1101
        async with sf() as session:
            assert (await session.get(Branch, "main")).status == "abandoned"
        report = {
            "same_day_growth": growth,
            "three_days": {
                "writes": 1100,
                "hot_rows": len(before),
                "daily_first_ticks": daily_first,
                "all_kept_ticks": [row.tick for row in before],
            },
            "abandoned": {
                "rows_before": len(before),
                "rows_after": len(after),
                "all_cold": True,
                "keys_and_gzip_sha256_equal": before_keys == after_keys,
                "events_before": len(events_before),
                "events_after": len(events_after),
                "event_rows_equal": True,
            },
        }
    finally:
        await engine.dispose()

    # Execute the permanent full-JSON recovery assertions in separate empty databases.
    for filename, check in (
        ("historical.db", test_pruned_historical_checkpoint_replays_to_identical_full_json),
        ("fallback.db", test_history_without_any_qualified_snapshot_still_replays_exactly),
    ):
        recovery_engine = create_async_engine(f"sqlite+aiosqlite:///{directory / filename}")
        await init_database(recovery_engine)
        try:
            await check(SqlEventStore(create_session_factory(recovery_engine)))
        finally:
            await recovery_engine.dispose()
    report["recovery"] = {
        "historical_checkpoint_json_equal": True,
        "no_qualified_snapshot_json_equal": True,
        "comparison": (
            "WorldCheckpoint.capture(loop).model_dump_json(), including RNG/combat/chaos fields"
        ),
    }
    old = (
        await asyncio.to_thread(
            subprocess.check_output,
            ["git", "show", "c706b40:sim/core/persistence/store.py"],
            cwd=ROOT,
        )
    ).decode("utf-8")
    current = (ROOT / "sim/core/persistence/store.py").read_text(encoding="utf-8")
    old_digest, current_digest = (
        method_digest(old, "latest_snapshot"),
        method_digest(current, "latest_snapshot"),
    )
    assert old_digest == current_digest
    report["latest_snapshot_ast_sha256"] = current_digest
    report["latest_snapshot_unchanged"] = True
    report["conditions"] = (
        "Production flush/fork paths in owned temporary SQLite files; no API/browser/model calls "
        "or production database writes. Per-flush checkpoint states are "
        "explicit deterministic fixtures."
    )
    return report


def main():
    tmp_root = (ROOT / ".orca/tmp").resolve()
    tmp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="snapshot-governance-", dir=tmp_root) as temp:
        directory = Path(temp).resolve()
        assert directory.is_relative_to(tmp_root)
        try:
            report = asyncio.run(measure(directory))
        finally:
            assert directory.resolve().is_relative_to(tmp_root)
    (Path(__file__).parent / "acceptance.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
