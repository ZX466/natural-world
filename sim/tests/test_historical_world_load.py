"""DA-02：真实历史档必须恢复后才确认，并让后续事件写入选中的子线。"""

import asyncio
import json

import pytest
from fastapi import WebSocket

from sim.api import anchors as anchors_api
from sim.api import main, settings, ws
from sim.api.anchors import AnchorStore
from sim.core.events import npc_death_event, tile_changed_event


@pytest.fixture(autouse=True)
def isolated_api_stores(tmp_path, monkeypatch, isolated_world_database):
    db_url = f"sqlite:///{tmp_path / 'world.db'}"
    anchors = AnchorStore(db_url)
    profiles = settings.ProfileStore(db_url)
    monkeypatch.setattr(anchors_api, "_anchor_store", anchors)
    monkeypatch.setattr(settings, "_profile_store", profiles)
    yield
    anchors._engine.dispose()
    profiles._engine.dispose()


def _recording_socket(frames, incoming=()) -> WebSocket:
    messages = iter(incoming)
    connecting = True

    async def receive():
        nonlocal connecting
        if connecting:
            connecting = False
            return {"type": "websocket.connect"}
        try:
            raw = next(messages)
        except StopIteration:
            return {"type": "websocket.disconnect", "code": 1000}
        return {"type": "websocket.receive", "text": json.dumps(raw)}

    async def send(message):
        if message["type"] == "websocket.send":
            frames.append(json.loads(message["text"]))

    return WebSocket({"type": "websocket", "path": "/ws", "headers": []}, receive, send)


@pytest.fixture(params=["with_future_events", "quiet_head"])
async def saved_world(tmp_path, monkeypatch, request):
    async def idle_driver(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "run_world_driver", idle_driver)
    frames = []

    manager = ws.ConnectionManager()
    connection = _recording_socket(frames)
    await connection.accept()
    manager.register(connection)
    manager.mark_authenticated(connection)
    monkeypatch.setattr(main, "manager", manager)
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


@pytest.fixture()
async def single_save(tmp_path, monkeypatch):
    """只存**一档**的世界（该档即末梢，`protected=True`）。

    `saved_world` 存了两档 ⇒ 旧档自动降级为 `protected=False`，因此抓不到
    「末梢档读不出来」（2026-11-03 实机发现的缺陷）。本夹具只存一档。
    """

    async def idle_driver(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "run_world_driver", idle_driver)
    frames = []

    # 第二十一轮起 `session_state` **按连接定向投递**（`send_to_control`），
    # 只 patch `broadcast_json` 会漏掉那一帧（只捕获到 timescale/full_snapshot）。
    # 用真 ConnectionManager + 记录 socket，与 `saved_world` 同款。
    manager = ws.ConnectionManager()
    connection = _recording_socket(frames)
    await connection.accept()
    manager.register(connection)
    manager.mark_authenticated(connection)
    monkeypatch.setattr(main, "manager", manager)
    async with main.lifespan(main.app):
        app = main.app
        await app.state.flush_for_anchor()
        loop = app.state.loop
        store = app.state.store
        anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
        rows = await store.read_range("main", 0, 100000)
        only = anchors.create_item(
            "唯一一档",
            branch_id="main",
            tick=loop.state.tick,
            seq=rows[-1]["seq"],
            rng_state=app.state.rng_capture(),
            state_hash=loop.state.state_hash(),
        )
        ws.register_anchor_id(only.id, "唯一一档", "河面刚起雾")
        yield app, only.id, frames
    ws.reset_anchor_registry()


async def test_load_the_only_anchor_after_saving_it(single_save):
    """存完立刻读：新建档是末梢（protected=True），必须能载入。

    修前 `locate_anchor` 带 `AND protected = 0` ⇒ 回 `load_failed`
    「这个档读不出来了。」（实机复现：存一档后点读档，面板无任何反应）。
    """
    from sqlalchemy import select

    from sim.core.persistence.models import PlayerAnchor

    app, anchor_id, frames = single_save
    async with app.state.store.session_factory() as session:
        saved = await session.scalar(
            select(PlayerAnchor.protected).where(PlayerAnchor.id == anchor_id)
        )
    assert saved is True, "前置：唯一存档必须是末梢（protected=True）"

    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        ws.ControlState(),
    )
    await app.state.drain_pending_loads()

    assert app.state.load_outcomes[-1] == (anchor_id, True)
    assert [frame["type"] for frame in frames] == ["session_state", "timescale", "full_snapshot"]


async def test_reloading_a_previously_loaded_anchor(single_save):
    """读过再读：读档成功后该档被回写为 protected=1，仍必须能再读。"""
    from sqlalchemy import select

    from sim.core.persistence.models import PlayerAnchor

    app, anchor_id, _frames = single_save
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        ws.ControlState(),
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, True)

    # 读档即把该档设为当前游标 ⇒ protected 回写为 1
    async with app.state.store.session_factory() as session:
        assert (
            await session.scalar(select(PlayerAnchor.protected).where(PlayerAnchor.id == anchor_id))
        ) is True

    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        ws.ControlState(),
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, True), "二次读档不得因 protected 回写而失败"


async def test_historical_load_restores_terrain_and_rebinds_live_surface_observer(single_save):
    app, anchor_id, _ = single_save
    loop = app.state.loop
    x, y = main.SPAWN_TILE
    assert app.state.pathfinder.height_at(x, y) == 1
    assert app.state.tile_map.is_walkable(x, y)

    # Same-tick edits after the saved sequence must be excluded from its child line.
    loop.enqueue(tile_changed_event(loop.state.tick, x, y, 0, height=3))
    assert app.state.surface.height_at(x, y) == 3
    assert app.state.pathfinder.height_at(x, y) == 3
    assert not app.state.tile_map.is_walkable(x, y)
    await app.state.flush_for_anchor()

    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        loop,
        app.state.pathfinder,
        main.manager.controls()[0],
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, True)
    assert app.state.surface.height_at(x, y) == 1
    assert app.state.pathfinder.height_at(x, y) == 1
    assert app.state.tile_map.is_walkable(x, y)

    loop.enqueue(tile_changed_event(loop.state.tick, x, y, 0, height=2))
    assert app.state.surface.height_at(x, y) == 2
    assert app.state.pathfinder.height_at(x, y) == 2
    assert not app.state.tile_map.is_walkable(x, y)
    await app.state.flush_for_anchor()
    assert app.state.surface.height_at(x, y) == 2


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
    # `ref` 是客户端路由的唯一依据（runtime.ts 按 ref=load_anchor 才进存档面板提示位），
    # 它硬编码在 main.py 的失败广播里 ⇒ 必须端到端钉住，别只在帧构造器层面测。
    assert frames[0]["ref"] == "load_anchor"
    assert frames[0]["code"] == "load_failed"
    parent_rows = await app.state.store.read_range("main", 0, 100000)
    assert parent_rows[-1]["seq"] == parent_head


async def test_historical_load_restores_npc_profile_and_runtime_after_later_death(saved_world):
    """Exercise the actual synchronous save and queued player-load path together."""
    from sim.core.persistence.npc_store import NpcStore

    app, anchor_id, _, _, _ = saved_world
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        ws.ControlState(),
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, True)
    branch = await app.state.store.current_branch_id()
    profiles = await NpcStore(app.state.store, branch_id=branch).materialize()
    assert "villager_01" in app.state.loop.state.entities
    assert "villager_01" in profiles
    assert "villager_01" in app.state.npc_runtime.profiles
    assert profiles["villager_01"].name == "赵铁"


async def test_historical_load_clears_old_branch_monologue_history(saved_world):
    """读档 = 分叉 ⇒ 旧分支的心声账本不得随快照灌进新分支面板。

    修前 `_MONO_HISTORY` 全仓无 `.clear()`，读档成功后
    `broadcast_json(snapshot_payload(...))` 带着旧分支最近 20 条出站，
    客户端逐条 `pushMonologue` ⇒ 新世界面板先被旧线内容冲一遍。
    """
    from collections import deque

    app, anchor_id, _, _, frames = saved_world
    # 本测试直接改模块级账本（读档路径清的就是它）。断言失败时别把脏数据
    # 留给后面的用例 —— 用 try/finally 兜底清一次（正常路径已由被测代码清空）。
    try:
        ws._MONO_HISTORY.append(
            ("villager_07", ws.monologue_payload("bubble", "旧分支的嘟囔", name="某某"))
        )
        assert len(ws._MONO_HISTORY) == 1
        ws.handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
            app.state.loop,
            app.state.pathfinder,
            ws.ControlState(),
        )
        await app.state.drain_pending_loads()
        assert app.state.load_outcomes[-1] == (anchor_id, True)
        assert len(ws._MONO_HISTORY) == 0, "旧分支心声账本必须随分叉清空"
        snapshot = next(f for f in frames if f["type"] == "full_snapshot")
        assert snapshot["monologue_history"] == []
        assert isinstance(ws._MONO_HISTORY, deque)
    finally:
        ws._MONO_HISTORY.clear()


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

    async def failed_surface(*args, **kwargs):
        raise RuntimeError("synthetic projection failure")

    monkeypatch.setattr(main, "rebuild_surface", failed_surface)
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


async def _other_saved_anchor(app, anchor_id):
    """Main owns the protected-anchor fix; use the other valid saved cursor here."""
    from sqlalchemy import select

    from sim.core.persistence.models import PlayerAnchor

    async with app.state.store.session_factory() as session:
        other = await session.scalar(select(PlayerAnchor.id).where(PlayerAnchor.id != anchor_id))
    assert other is not None
    return other


@pytest.mark.parametrize("speed", [1, 4, 16])
@pytest.mark.parametrize("paused", [False, True])
async def test_projection_failure_then_success_restores_requesting_control(
    saved_world, monkeypatch, speed, paused
):
    app, anchor_id, _, _, frames = saved_world
    control = main.manager.controls()[0]
    loop = app.state.loop
    recovery_anchor = await _other_saved_anchor(app, anchor_id)
    ws.handle_client_message(
        {"type": "set_control", "channel": "control", "action": "set_speed", "speed": speed},
        loop,
        app.state.pathfinder,
        control,
    )
    if paused:
        ws.handle_client_message(
            {"type": "set_control", "channel": "control", "action": "pause"},
            loop,
            app.state.pathfinder,
            control,
        )
    real_surface = main.rebuild_surface

    async def failed_surface(*args, **kwargs):
        raise RuntimeError("synthetic projection failure")

    monkeypatch.setattr(main, "rebuild_surface", failed_surface)
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        loop,
        app.state.pathfinder,
        control,
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, False)
    assert not app.state.world_source_ready
    assert loop.clock.speed == 0
    assert [frame["type"] for frame in frames] == ["error"]

    monkeypatch.setattr(main, "rebuild_surface", real_surface)
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": recovery_anchor},
        loop,
        app.state.pathfinder,
        control,
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (recovery_anchor, True)
    assert app.state.world_source_ready
    assert loop.clock.speed == (0 if paused else speed)
    state = next(frame for frame in frames if frame["type"] == "session_state")
    assert (state["speed"], state["paused"]) == (speed, paused)
    assert (control.effective_speed(), control.paused) == (speed, paused)
    if paused:
        reply = ws.handle_client_message(
            {"type": "set_control", "channel": "control", "action": "resume"},
            loop,
            app.state.pathfinder,
            control,
        )
        assert isinstance(reply, dict)
        assert reply["type"] == "control_ack"
        assert loop.clock.speed == speed


async def test_load_session_state_preserves_each_connections_control(saved_world):
    app, anchor_id, _, _, paused_frames = saved_world
    paused_control = main.manager.controls()[0]
    live_frames = []

    live_socket = _recording_socket(live_frames)
    await live_socket.accept()
    live_control = ws.ControlState()
    main.manager.register(live_socket, control=live_control)
    main.manager.mark_authenticated(live_socket)
    for control, speed in ((paused_control, 4), (live_control, 16)):
        ws.handle_client_message(
            {"type": "set_control", "channel": "control", "action": "set_speed", "speed": speed},
            app.state.loop,
            app.state.pathfinder,
            control,
        )
        if control is paused_control:
            ws.handle_client_message(
                {"type": "set_control", "channel": "control", "action": "pause"},
                app.state.loop,
                app.state.pathfinder,
                control,
            )
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        live_control,
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, True)
    assert app.state.loop.clock.speed == 16
    assert [(frame["type"]) for frame in paused_frames] == [
        "session_state",
        "timescale",
        "full_snapshot",
    ]
    assert (paused_frames[0]["speed"], paused_frames[0]["paused"]) == (4, True)
    assert (live_frames[0]["speed"], live_frames[0]["paused"]) == (16, False)
    assert paused_control.paused and not live_control.paused


async def test_duplicate_queued_load_returns_error_without_another_fork(saved_world):
    from sqlalchemy import func, select

    from sim.core.persistence.models import Branch

    app, anchor_id, _, _, _ = saved_world
    raw = {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id}
    args = (app.state.loop, app.state.pathfinder, main.manager.controls()[0])
    assert ws.handle_client_message(raw, *args) is None
    reply = ws.handle_client_message(raw, *args)
    assert isinstance(reply, dict), "重复读档必须显式拒绝，不能再次静默入队"
    assert (reply["type"], reply["ref"], reply["code"]) == (
        "error",
        "load_anchor",
        "load_failed",
    )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes == [(anchor_id, True)]
    async with app.state.store.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Branch)) == 2


async def test_duplicate_in_flight_load_is_rejected(saved_world, monkeypatch):
    app, anchor_id, _, _, _ = saved_world
    entered, release = asyncio.Event(), asyncio.Event()
    real_surface = main.rebuild_surface

    async def held_surface(*args, **kwargs):
        entered.set()
        await release.wait()
        return await real_surface(*args, **kwargs)

    monkeypatch.setattr(main, "rebuild_surface", held_surface)
    raw = {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id}
    args = (app.state.loop, app.state.pathfinder, main.manager.controls()[0])
    assert ws.handle_client_message(raw, *args) is None
    draining = asyncio.create_task(app.state.drain_pending_loads())
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        reply = ws.handle_client_message(raw, *args)
        assert isinstance(reply, dict), "执行中的读档也必须防重"
        assert reply["code"] == "load_failed"
    finally:
        release.set()
        await draining
    assert app.state.load_outcomes == [(anchor_id, True)]


async def test_failed_load_releases_duplicate_guard_for_retry(saved_world):
    app, _, _, _, _ = saved_world
    raw = {"type": "load_anchor", "channel": "session", "anchor_id": "missing-anchor"}
    args = (app.state.loop, app.state.pathfinder, main.manager.controls()[0])
    for _ in range(2):
        assert ws.handle_client_message(raw, *args) is None
        duplicate = ws.handle_client_message(raw, *args)
        assert isinstance(duplicate, dict)
        assert duplicate["code"] == "load_failed"
        await app.state.drain_pending_loads()
    assert app.state.load_outcomes == [("missing-anchor", False), ("missing-anchor", False)]


async def test_distinct_queued_anchors_each_fork_once(saved_world):
    from sqlalchemy import func, select

    from sim.core.persistence.models import Branch

    app, anchor_id, _, _, _ = saved_world
    other = await _other_saved_anchor(app, anchor_id)
    for current in (anchor_id, other):
        assert (
            ws.handle_client_message(
                {"type": "load_anchor", "channel": "session", "anchor_id": current},
                app.state.loop,
                app.state.pathfinder,
                main.manager.controls()[0],
            )
            is None
        )
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes == [(anchor_id, True), (other, True)]
    async with app.state.store.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Branch)) == 3


async def test_queued_load_uses_updated_control_even_after_requester_disconnects(saved_world):
    app, anchor_id, _, _, _ = saved_world
    control = ws.ControlState(speed_before_pause=16)
    departed_frames = []
    connection = _recording_socket(departed_frames)
    await connection.accept()
    main.manager.register(connection, control=control)
    main.manager.mark_authenticated(connection)
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        control,
    )
    # An accepted request retains this session's latest intent, not a speed snapshot.
    ws.handle_client_message(
        {"type": "set_control", "channel": "control", "action": "set_speed", "speed": 4},
        app.state.loop,
        app.state.pathfinder,
        control,
    )
    main.manager.unregister(connection)
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, True)
    assert app.state.loop.clock.speed == 4
    assert not departed_frames


async def test_fault_gate_blocks_control_but_accepts_authenticated_recovery(
    saved_world, monkeypatch
):
    app, anchor_id, _, _, _ = saved_world
    recovery_anchor = await _other_saved_anchor(app, anchor_id)
    real_surface = main.rebuild_surface

    async def failed_surface(*args, **kwargs):
        raise RuntimeError("synthetic projection failure")

    monkeypatch.setattr(main, "rebuild_surface", failed_surface)
    ws.handle_client_message(
        {"type": "load_anchor", "channel": "session", "anchor_id": anchor_id},
        app.state.loop,
        app.state.pathfinder,
        main.manager.controls()[0],
    )
    await app.state.drain_pending_loads()
    assert not app.state.world_source_ready
    monkeypatch.setattr(main, "rebuild_surface", real_surface)
    incoming = iter(
        [
            {"type": "load_anchor", "channel": "session", "anchor_id": recovery_anchor},
            {"type": "hello", "channel": "session", "token": ws.ws_auth_token()},
            {"type": "set_control", "channel": "control", "action": "set_speed", "speed": 4},
            {"type": "load_anchor", "channel": "session", "anchor_id": recovery_anchor},
        ]
    )
    replies = []

    await main.ws_endpoint(_recording_socket(replies, incoming))
    errors = [frame for frame in replies if frame["type"] == "error"]
    assert [(frame["ref"], frame["code"]) for frame in errors] == [
        ("load_anchor", "auth_error"),
        ("set_control", "bad_action"),
    ]
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes == [(anchor_id, False), (recovery_anchor, True)]
    assert app.state.world_source_ready
    assert app.state.loop.clock.speed == 1


async def test_fork_failure_rolls_back_world_selection_checkpoint_and_anchor(
    saved_world, monkeypatch
):
    from sqlalchemy import func, select

    from sim.core.persistence import fork
    from sim.core.persistence.models import Branch, NpcProfile, PlayerAnchor, Snapshot

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
                select(func.count()).select_from(NpcProfile).where(NpcProfile.branch_id != "main")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(Snapshot).where(Snapshot.branch_id != "main")
            )
            == 0
        )
        anchor = await session.get(PlayerAnchor, anchor_id)
        assert anchor is not None and not anchor.protected
    assert [frame["type"] for frame in frames] == ["error"]
