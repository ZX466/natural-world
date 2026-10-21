"""DA-02：真实历史档必须恢复后才确认，并让后续事件写入选中的子线。"""

import asyncio

import pytest

from sim.api import main, ws
from sim.api.anchors import AnchorStore
from sim.core.events import npc_death_event


@pytest.fixture(params=["with_future_events", "quiet_head"])
async def saved_world(tmp_path, monkeypatch, request):
    async def idle_driver(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "run_world_driver", idle_driver)
    frames = []

    async def capture(frame):
        frames.append(frame)

    monkeypatch.setattr(main.manager, "broadcast_json", capture)
    async with main.lifespan(main.app):
        app = main.app
        await app.state.flush_for_anchor()
        loop = app.state.loop
        store = app.state.store
        anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
        rows = await store.read_range("main", 0, 100000)
        saved_hash = loop.state.state_hash()
        old = anchors.create_item(
            "旧日河风",
            branch_id="main",
            tick=loop.state.tick,
            seq=rows[-1]["seq"],
            rng_state=app.state.rng_capture(),
            state_hash=saved_hash,
        )
        if request.param == "with_future_events":
            loop.advance_frame(1.0)
            loop.enqueue(npc_death_event(tick=loop.state.tick, entity_id="villager_01"))
            await app.state.flush_for_anchor()
        rows = await store.read_range("main", 0, 100000)
        anchors.create_item(
            "后来的事",
            branch_id="main",
            tick=loop.state.tick,
            seq=rows[-1]["seq"],
            rng_state=app.state.rng_capture(),
            state_hash=loop.state.state_hash(),
        )
        ws.register_anchor_id(old.id, "旧日河风", "风吹河面")
        yield app, old.id, saved_hash, rows[-1]["seq"], frames
    ws.reset_anchor_registry()


async def test_queued_load_does_not_confirm_with_the_old_world(saved_world):
    app, anchor_id, _, _, _ = saved_world
    reply = ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        ws.ControlState(),
    )
    assert reply is None, "请求登记时还没有读档完成，不能先回旧世界的成功帧"


async def test_historical_load_restores_world_and_activates_child_before_confirmation(saved_world):
    app, anchor_id, saved_hash, parent_head, frames = saved_world
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        ws.ControlState(),
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, True)
    assert app.state.loop.state.state_hash() == saved_hash
    assert app.state.loop.clock.tick == app.state.loop.state.tick
    assert "villager_01" in app.state.loop.state.entities
    child = await app.state.store.current_branch_id()
    assert child != "main"
    from sqlalchemy import select

    from sim.core.persistence.models import PlayerAnchor

    async with app.state.store.session_factory() as session:
        selected = await session.scalar(
            select(PlayerAnchor.id).where(PlayerAnchor.protected.is_(True))
        )
    assert selected == anchor_id, "当前游标必须跟随实际载入的存档"
    assert [frame["type"] for frame in frames] == ["session_state", "timescale", "full_snapshot"]
    assert frames[1]["active"] == app.state.loop.context.combat_active

    app.state.loop.issue_move("chenmo", [(100, 53), (101, 53)])
    await app.state.flush_for_anchor()
    assert await app.state.store.read_range(child, 1, 100000)
    parent_rows = await app.state.store.read_range("main", 0, 100000)
    assert parent_rows[-1]["seq"] == parent_head
    restored, reopened = await main.build_loop()
    try:
        assert restored.state.state_hash() == app.state.loop.state.state_hash()
        assert await reopened.current_branch_id() == child
    finally:
        await reopened.session_factory.kw["bind"].dispose()


async def test_invalid_rng_leaves_live_world_and_current_branch_untouched(saved_world):
    from sqlalchemy import update

    from sim.core.persistence.models import AnchorPackage

    app, anchor_id, _, parent_head, frames = saved_world
    state_before = app.state.loop.state.state_hash()
    async with app.state.store.session_factory.begin() as session:
        await session.execute(
            update(AnchorPackage).where(AnchorPackage.anchor_id == anchor_id).values(rng_state="{}")
        )
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        ws.ControlState(),
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, False)
    assert app.state.loop.state.state_hash() == state_before
    assert await app.state.store.current_branch_id() == "main"
    assert [frame["type"] for frame in frames] == ["error"]
    parent_rows = await app.state.store.read_range("main", 0, 100000)
    assert parent_rows[-1]["seq"] == parent_head


async def test_decision_started_before_load_cannot_execute_in_restored_world(
    saved_world, monkeypatch
):
    from sim.agent.driver import ChenmoDriver

    app, anchor_id, _, _, _ = saved_world
    entered, release, executed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def held_decision(self, *args, **kwargs):
        entered.set()
        await release.wait()
        return True

    def record_execution(self, *args, **kwargs):
        executed.set()
        return 0

    monkeypatch.setattr(ChenmoDriver, "decide_once", held_decision)
    monkeypatch.setattr(ChenmoDriver, "execute_pending", record_execution)
    app.state.chenmo_driver.request_decision()
    await asyncio.wait_for(entered.wait(), timeout=5)
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        ws.ControlState(),
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, True)
    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not executed.is_set(), "旧分支等待中的模型决策不能在读档后的世界执行"


async def test_projection_failure_stops_world_without_sending_success(saved_world, monkeypatch):
    app, anchor_id, _, _, frames = saved_world

    async def failed_map(*args, **kwargs):
        raise RuntimeError("synthetic projection failure")

    monkeypatch.setattr(main, "rebuild_tile_map", failed_map)
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        ws.ControlState(),
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, False)
    assert not app.state.world_source_ready
    assert app.state.loop.clock.speed == 0
    assert [frame["type"] for frame in frames] == ["error"]


async def test_fork_failure_rolls_back_world_selection_checkpoint_and_anchor(
    saved_world, monkeypatch
):
    from sqlalchemy import func, select

    from sim.core.persistence import fork
    from sim.core.persistence.models import Branch, PlayerAnchor, Snapshot

    app, anchor_id, _, _, frames = saved_world
    state_before = app.state.loop.state.state_hash()

    async def failed_clone(*args, **kwargs):
        raise RuntimeError("synthetic transaction failure")

    monkeypatch.setattr(fork, "_clone_bounded", failed_clone)
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        ws.ControlState(),
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, False)
    assert app.state.loop.state.state_hash() == state_before
    assert await app.state.store.current_branch_id() == "main"
    async with app.state.store.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Branch)) == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(Snapshot).where(Snapshot.branch_id != "main")
            )
            == 0
        )
        anchor = await session.get(PlayerAnchor, anchor_id)
        assert anchor is not None and not anchor.protected
    assert [frame["type"] for frame in frames] == ["error"]
