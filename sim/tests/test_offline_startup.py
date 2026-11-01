"""隔离 SQLite 的真实停服/重启与元数据兼容性。"""

import asyncio
import importlib

import pytest
from sqlalchemy import func, select

from sim.core.persistence.models import Event, PlayerAnchor
from sim.core.persistence.world_restore import flush_world


async def idle_driver(*args, **kwargs):
    await asyncio.Event().wait()


async def test_one_minute_restart_really_runs_world_and_does_not_repeat(monkeypatch):
    from sim.api import main
    from sim.world import offline

    wall = 1000.0
    monkeypatch.setattr(main, "run_world_driver", idle_driver)
    monkeypatch.setattr(main, "_offline_wall_time", lambda: wall, raising=False)
    real_advance = offline.advance_offline
    calls = []

    async def checked_advance(*args, **kwargs):
        assert not any(
            "_chenmo_loop" in getattr(task.get_coro(), "__qualname__", "")
            for task in asyncio.all_tasks()
            if not task.done()
        )
        calls.append(kwargs["offline_seconds"])
        return await real_advance(*args, **kwargs)

    monkeypatch.setattr(offline, "advance_offline", checked_advance)
    async with main.lifespan(main.app):
        loop = main.app.state.loop
        store = main.app.state.store
        await main.app.state.flush_for_anchor()
        await flush_world(store, "main", loop, [], checkpoint_at=wall, force_checkpoint=True)
        start = loop.state.tick
        async with store.session_factory.begin() as session:
            before = await session.scalar(select(func.count()).select_from(Event))
            session.add(PlayerAnchor(id="kept", name="河边", branch_id="main", tick=start, seq=1))
    wall += 60
    async with main.lifespan(main.app):
        loop = main.app.state.loop
        assert loop.state.tick == start + 3600
        assert loop.clock.tick == loop.state.tick
        result_hash = loop.state.state_hash()
        store = main.app.state.store
        async with store.session_factory() as session:
            after = await session.scalar(select(func.count()).select_from(Event))
            assert after > before
            anchor = await session.get(PlayerAnchor, "kept")
            assert (anchor.name, anchor.tick, anchor.seq) == ("河边", start, 1)
    async with main.lifespan(main.app):
        assert main.app.state.loop.state.tick == start + 3600
        assert main.app.state.loop.state.state_hash() == result_hash
    assert calls == [60]


@pytest.mark.parametrize(
    "value,epoch",
    [
        (1000.5, 1000.5),
        ("1000.5", 1000.5),
        ("1970-01-01T00:16:40Z", 1000.0),
        ("1970-01-01 00:16:40", 1000.0),
    ],
)
def test_legacy_checkpoint_wall_formats(value, epoch):
    module = importlib.import_module("sim.core.persistence.offline_store")
    assert module.checkpoint_epoch(value) == epoch


@pytest.mark.parametrize("value", [None, True, -1, "nan", "bad-date"])
def test_corrupted_wall_metadata_is_rejected(value):
    module = importlib.import_module("sim.core.persistence.offline_store")
    with pytest.raises(ValueError):
        module.checkpoint_epoch(value)
