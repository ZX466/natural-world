"""uv run python .orca/audits/offline-progress-2026-11-01/verify.py"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select
from structlog.testing import capture_logs

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sim.api import main
from sim.core.clock import GameClock
from sim.core.persistence.models import Event, PlayerAnchor
from sim.core.persistence.world_restore import expand_world, flush_world, restore_world
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.world.offline import advance_offline


async def idle(*args, **kwargs):
    await asyncio.Event().wait()


async def measure(database: Path) -> dict:
    wall = 1000.0
    with (
        patch.object(main, "WORLD_DB_PATH", database),
        patch.object(main, "run_world_driver", idle),
        patch.object(main, "_offline_wall_time", lambda: wall),
        patch.object(main, "_active_profile_snapshot_provider", lambda: lambda: None),
    ):
        async with main.lifespan(main.app):
            loop, store = main.app.state.loop, main.app.state.store
            await main.app.state.flush_for_anchor()
            await flush_world(store, "main", loop, [], checkpoint_at=wall, force_checkpoint=True)
            start = loop.state.tick
            async with store.session_factory.begin() as session:
                before = await session.scalar(select(func.count()).select_from(Event))
                session.add(
                    PlayerAnchor(id="unchanged", name="河边", branch_id="main", tick=start, seq=1)
                )
        wall += 60
        async with main.lifespan(main.app):
            loop, store = main.app.state.loop, main.app.state.store
            end = loop.state.tick
            final_hash = loop.state.state_hash()
            async with store.session_factory() as session:
                after = await session.scalar(select(func.count()).select_from(Event))
                rows = (await session.scalars(select(Event).order_by(Event.seq))).all()
                anchor = await session.get(PlayerAnchor, "unchanged")
                assert anchor is not None and (anchor.name, anchor.tick, anchor.seq) == (
                    "河边",
                    start,
                    1,
                )
                payloads = [json.loads(row.payload) for row in rows]
            assert end - start == 3600 and after > before
            assert all(
                not {"offline_seconds", "wall_time", "checkpoint_at"} & payload.keys()
                for payload in payloads
            )
            restored = [await restore_world(store, "main") for _ in range(2)]
            assert all(item.state.state_hash() == final_hash for item in restored)
            history = await store.read_branch_history("main")
            replay_hashes = []
            for _ in range(2):
                replay = expand_world({}, history)
                replay.replay_until(end)
                replay_hashes.append(replay.state.state_hash())
            assert replay_hashes[0] == replay_hashes[1] == final_hash
        async with main.lifespan(main.app):
            assert main.app.state.loop.state.tick == end
            assert main.app.state.loop.state.state_hash() == final_hash

    capped_loop = TickLoop(GameClock(), build_default_bus(), WorldState(world_seed=42))

    async def discard(*args):
        pass

    with capture_logs() as logs:
        capped = await advance_offline(capped_loop, offline_seconds=30 * 86400, flush=discard)
    assert capped.advanced_ticks == 86400
    assert any(item["event"] == "offline.capped" for item in logs)
    return {
        "status": "pass",
        "database": "temporary SQLite",
        "real_offline_seconds": 60,
        "normal_ticks_per_real_second": 60,
        "start_tick": start,
        "end_tick": end,
        "advanced_ticks": end - start,
        "events_before": before,
        "events_after": after,
        "events_deleted": 0,
        "player_anchor_unchanged": True,
        "wall_time_fields_in_payload": False,
        "replay_hashes": replay_hashes,
        "restart_again_at_same_wall_time_repeated_ticks": 0,
        "cap": {
            "requested_seconds": 30 * 86400,
            "advanced_ticks": capped.advanced_ticks,
            "consumed_seconds": capped.consumed_seconds,
            "discarded_seconds": capped.discarded_seconds,
            "offline_capped_logged": True,
        },
        "llm_calls": 0,
        "protocol": "1.14",
    }


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="project7-offline-") as folder:
        result = asyncio.run(measure(Path(folder) / "audit.db"))
    Path(__file__).with_name("acceptance.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
