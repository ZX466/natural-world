"""主树独立探针：不复用 codex verify.py，自测第十五轮四条交付的关键不变量。

纪律：
- 只用临时 SQLite，绝不碰真实 world.db；
- 结束 dispose 连接、删除前校验目录归属。
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from itertools import pairwise
from pathlib import Path

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))


async def probe_offline_bounds() -> None:
    """① 离线推进：批上限、cap、C5、C6、玩家档零写。"""
    from sim.core.clock import GameClock
    from sim.core.events import npc_monologue_event, world_create_event
    from sim.core.persistence.world_restore import flush_world, restore_world
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState, build_default_bus
    from sim.world.offline import advance_offline

    tmp = Path(tempfile.mkdtemp(prefix="probe-offline-"))
    try:
        from sqlalchemy import func, select

        from sim.core.persistence.database import (
            create_engine,
            create_session_factory,
            init_database,
        )
        from sim.core.persistence.models import Event
        from sim.core.persistence.store import SqlEventStore

        engine = create_engine(f"sqlite+aiosqlite:///{(tmp / 'w.db').as_posix()}")
        await init_database(engine)
        factory = create_session_factory(engine)
        store = SqlEventStore(factory)

        loop = TickLoop(GameClock(), build_default_bus(), WorldState(world_seed=42))
        loop.enqueue(world_create_event(0, 42, ("chenmo",)))
        loop.advance_frame(1 / 60)
        await flush_world(store, "main", loop, loop.drain_events())

        batches: list[int] = []
        loop.attach_npc_runtime(
            lambda state, tick: [npc_monologue_event(tick, "chenmo", "bubble", "河面起风了。")]
        )

        async def flush(events, consumed, final):
            batches.append(loop.state.tick)
            await flush_world(
                store, "main", loop, events, checkpoint_at=1000 + consumed, force_checkpoint=final
            )

        # 1) 60 秒 = 3600 tick，每批 ≤ 240
        start = loop.state.tick
        await advance_offline(loop, offline_seconds=60, flush=flush)
        advanced = loop.state.tick - start
        steps = [start, *batches]
        max_step = max((b - a for a, b in pairwise(steps)), default=0)
        record("①60秒推进3600tick", advanced == 3600, f"advanced={advanced}")
        record("①每批≤240tick", max_step <= 240, f"max_step={max_step}")

        # 2) C6：事件只增不减
        async with factory() as s:
            before = await s.scalar(select(func.count()).select_from(Event))
        await advance_offline(loop, offline_seconds=1, flush=flush)
        async with factory() as s:
            after = await s.scalar(select(func.count()).select_from(Event))
        record("①C6 事件只增不减", after >= before, f"{before} -> {after}")

        # 3) C5：两遍重放 hash 相同
        first = await restore_world(store, "main")
        second = await restore_world(store, "main")
        same = first.state.state_hash() == second.state.state_hash() == loop.state.state_hash()
        record("①C5 两遍重放 hash 相同", same)

        # 4) 墙钟不进事件 payload
        async with factory() as s:
            payloads = (await s.scalars(select(Event.payload))).all()
        leak = [p for p in payloads if "offline" in str(p) or "1000" in str(p)]
        record("①墙钟不进 payload", not leak, f"leaked={len(leak)}")

        # 5) 30 天 cap 到 1 游戏日
        res = await advance_offline(loop, offline_seconds=30 * 86400, flush=flush)
        record("①30天cap到86400tick", res.advanced_ticks == 86400, f"advanced={res.advanced_ticks}")
        record("①cap有丢弃秒数", res.discarded_seconds > 0, f"discarded={res.discarded_seconds}")

        # 6) 玩家档零写
        from sim.core.persistence.models import PlayerAnchor

        async with factory() as s:
            n = await s.scalar(select(func.count()).select_from(PlayerAnchor))
        record("①玩家档零写入", n == 0, f"anchors={n}")

        await engine.dispose()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def probe_offline_restart() -> None:
    """① 重启不重复补跑：同墙钟再启动新增 tick = 0。"""
    from sim.core.clock import GameClock
    from sim.core.events import world_create_event
    from sim.core.persistence.database import create_engine, create_session_factory, init_database
    from sim.core.persistence.offline_store import checkpoint_epoch, last_recorded_at
    from sim.core.persistence.store import SqlEventStore
    from sim.core.persistence.world_restore import flush_world
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState, build_default_bus
    from sim.world.offline import advance_offline

    tmp = Path(tempfile.mkdtemp(prefix="probe-restart-"))
    try:
        engine = create_engine(f"sqlite+aiosqlite:///{(tmp / 'w.db').as_posix()}")
        await init_database(engine)
        factory = create_session_factory(engine)
        store = SqlEventStore(factory)
        loop = TickLoop(GameClock(), build_default_bus(), WorldState(world_seed=42))
        loop.enqueue(world_create_event(0, 42, ("chenmo",)))
        loop.advance_frame(1 / 60)
        await flush_world(store, "main", loop, loop.drain_events(), checkpoint_at=1000.0)

        async def flush(events, consumed, final):
            await flush_world(
                store, "main", loop, events, checkpoint_at=1000 + consumed, force_checkpoint=final
            )

        await advance_offline(loop, offline_seconds=60, flush=flush)
        watermark = await last_recorded_at(store, "main")
        record("①水位推进到 1060", watermark == 1060.0, f"watermark={watermark}")

        # 同墙钟再启动 ⇒ offline_seconds=0 ⇒ 零推进
        same_wall = checkpoint_epoch(watermark) - watermark
        res = await advance_offline(loop, offline_seconds=same_wall, flush=flush)
        record("①同墙钟重启零补跑", res.advanced_ticks == 0, f"advanced={res.advanced_ticks}")
        await engine.dispose()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe_t5_no_threshold() -> None:
    """③ T5 只取证不定线：源码不得含完成率阈值常量。"""
    src = Path("sim/tests/golden/assertions/errands_rate.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))
    bad = [ln for ln in code.splitlines() if "0.8" in ln or "80" in ln.replace("80%", "")]
    record("③errands_rate 无硬阈值", not bad, f"suspect={bad[:2]}")


def probe_soak_constant() -> None:
    """④ soak 常量仍为 0（只取证不提值）。"""
    src = Path("sim/tests/bench/test_bench_soak.py").read_text(encoding="utf-8")
    ok = "SOAK_ENTITY_LOSS_PER_GAME_DAY = 0" in src
    record("④soak 常量仍为 0", ok)


def probe_audio_no_deps() -> None:
    """② 音效零新依赖、零资产、零协议变更。"""
    import json

    pkg = json.loads(Path("client/package.json").read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    banned = [k for k in deps if any(x in k.lower() for x in ("howler", "tone", "audio"))]
    record("②无音频 npm 依赖", not banned, f"found={banned}")

    audio_files = [
        p
        for p in Path("client").rglob("*")
        if p.suffix.lower() in {".mp3", ".ogg", ".wav"} and "node_modules" not in str(p)
    ]
    record("②无音频资产文件", not audio_files, f"count={len(audio_files)}")

    protocol = Path("client/src/net/ws.ts").read_text(encoding="utf-8")
    record("②协议仍 1.14", "PROTOCOL_VERSION = '1.14'" in protocol)


def probe_audio_default_muted() -> None:
    """② 音效默认静音（autoplay 安全）。"""
    src = Path("client/src/game/audio/world-audio.ts").read_text(encoding="utf-8")
    ok = "muted: true" in src
    record("②默认静音", ok)


async def main() -> None:
    await probe_offline_bounds()
    await probe_offline_restart()
    probe_t5_no_threshold()
    probe_soak_constant()
    probe_audio_no_deps()
    probe_audio_default_muted()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n主树独立探针：{passed}/{len(RESULTS)} 通过\n")
    for name, ok, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    if passed != len(RESULTS):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
