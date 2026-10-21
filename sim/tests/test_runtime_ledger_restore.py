"""DA-03：真实历史读档按谱系恢复余额与活火，不携带父线未来。"""

import asyncio

import pytest

from sim.api import main, ws
from sim.api.anchors import AnchorStore
from sim.core.events import coin_grant_event
from sim.core.persistence.fire_store import FireStore
from sim.world.economy import CoinLedger


async def save_anchor(app, anchors, name):
    await app.state.flush_for_anchor()
    branch = await app.state.store.current_branch_id()
    rows = await app.state.store.read_range(branch, 0, 100000)
    return anchors.create_item(
        name,
        branch_id=branch,
        tick=app.state.loop.state.tick,
        seq=rows[-1]["seq"] if rows else 0,
        rng_state=app.state.rng_capture(),
        state_hash=app.state.loop.state.state_hash(),
    )


async def load_anchor(app, anchor_id):
    assert ws._ANCHOR_LOAD_HOOK is not None
    ws._ANCHOR_LOAD_HOOK(anchor_id)
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, True)


@pytest.fixture(params=["active", "closed", "empty"])
async def saved_ledgers(tmp_path, monkeypatch, request):
    async def idle_driver(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "run_world_driver", idle_driver)
    async with main.lifespan(main.app):
        app = main.app
        await app.state.flush_for_anchor()
        loop = app.state.loop
        fire = app.state.fire_runtime
        occupied = {entity.pos for entity in loop.state.entities.values()}
        tile_map = app.state.tile_map
        positions = [
            (x, y)
            for y in range(tile_map.height)
            for x in range(tile_map.width)
            if tile_map.is_walkable(x, y) and (x, y) not in occupied
        ][:3]
        first, active, future = positions
        if request.param != "empty":
            for event in fire.ignite_at(tick=0, x=first[0], y=first[1]):
                loop.enqueue(event)
            for tick in range(1, 13):
                for event in fire.step(tick=tick, walkable=set()):
                    loop.enqueue(event)
        if request.param == "active":
            assert app.state.coin_ledger.apply_grant("chenmo", 100, tick=50)
            loop.enqueue(coin_grant_event(50, "chenmo", 100, "工钱"))
            for event in fire.ignite_at(tick=50, x=active[0], y=active[1]):
                loop.enqueue(event)
        anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
        old = await save_anchor(app, anchors, "账本之初")
        expected_seq = {"empty": 0, "closed": 1, "active": 2}[request.param]
        expected_cells = {("fire-2", *active, 50)} if request.param == "active" else set()
        expected_balance = 100 if request.param == "active" else 0
        # 同 tick 的后续事实仍属父线未来；不能只按 tick 过滤。
        assert app.state.coin_ledger.apply_grant("chenmo", 777, tick=loop.state.tick)
        loop.enqueue(coin_grant_event(loop.state.tick, "chenmo", 777, "后来的工钱"))
        for event in fire.ignite_at(tick=loop.state.tick, x=future[0], y=future[1]):
            loop.enqueue(event)
        await save_anchor(app, anchors, "未来账本")
        yield app, anchors, old.id, expected_balance, expected_cells, expected_seq, positions
    ws.reset_anchor_registry()


async def test_loading_anchor_restores_recorded_coin_balance(saved_ledgers):
    app, _, anchor_id, expected, _, _, _ = saved_ledgers
    await load_anchor(app, anchor_id)
    assert app.state.coin_ledger.balance_of("chenmo") == expected


async def test_loading_anchor_restores_active_fire_cells_and_sequence(saved_ledgers):
    app, _, anchor_id, _, expected_cells, expected_seq, _ = saved_ledgers
    await load_anchor(app, anchor_id)
    runtime = app.state.fire_runtime
    assert {
        (cell.fire_id, cell.x, cell.y, cell.ignited_tick) for cell in runtime.cells
    } == expected_cells
    assert runtime.fire_seq == expected_seq
    branch = await app.state.store.current_branch_id()
    replayed = await FireStore(app.state.store, branch_id=branch).materialize_fires_replay()
    assert {
        (row.fire_id, row.x, row.y, row.ignited_tick) for row in replayed.values() if row.active
    } == expected_cells


async def test_new_fire_after_load_does_not_reuse_recorded_ids(saved_ledgers):
    app, _, anchor_id, _, expected_cells, expected_seq, positions = saved_ledgers
    await load_anchor(app, anchor_id)
    events = app.state.fire_runtime.ignite_at(
        tick=app.state.loop.state.tick, x=positions[2][0], y=positions[2][1]
    )
    assert events[0].payload["fire_id"] == f"fire-{expected_seq + 1}"
    for event in events:
        app.state.loop.enqueue(event)
    await app.state.flush_for_anchor()
    branch = await app.state.store.current_branch_id()
    replayed = await FireStore(app.state.store, branch_id=branch).materialize_fires_replay()
    assert {row.fire_id for row in replayed.values() if row.active} == (
        {cell[0] for cell in expected_cells} | {f"fire-{expected_seq + 1}"}
    )


@pytest.mark.parametrize("saved_ledgers", ["active"], indirect=True)
async def test_second_load_preserves_ancestor_prefix_and_excludes_both_futures(saved_ledgers):
    app, anchors, first_id, _, _, _, positions = saved_ledgers
    await load_anchor(app, first_id)
    assert app.state.coin_ledger.apply_grant("chenmo", -40, tick=60)
    app.state.loop.enqueue(coin_grant_event(60, "chenmo", -40, "买药"))
    for event in app.state.fire_runtime.ignite_at(tick=60, x=positions[2][0], y=positions[2][1]):
        app.state.loop.enqueue(event)
    second = await save_anchor(app, anchors, "分支账本")
    assert app.state.coin_ledger.apply_grant("chenmo", 500, tick=60)
    app.state.loop.enqueue(coin_grant_event(60, "chenmo", 500, "分支未来工钱"))
    await save_anchor(app, anchors, "分支未来")
    await load_anchor(app, second.id)
    assert app.state.coin_ledger.balance_of("chenmo") == 60
    assert {cell.fire_id for cell in app.state.fire_runtime.cells} == {"fire-2", "fire-3"}
    assert app.state.fire_runtime.fire_seq == 3


def test_invalid_recorded_debit_cannot_replace_ledger_with_negative_or_partial_balance():
    ledger = CoinLedger()
    assert ledger.apply_grant("chenmo", 100, tick=0)
    bad_history = [
        coin_grant_event(1, "villager_01", 20, "工钱").to_store_dict(),
        coin_grant_event(2, "chenmo", -1, "买药").to_store_dict(),
    ]
    with pytest.raises(ValueError, match="negative balance"):
        ledger.restore_from_events(bad_history)
    assert ledger.balance_of("chenmo") == 100
    assert ledger.balance_of("villager_01") == 0


# ---------------------------------------------------------------------------
# 主树补充：进程重启（冷启动）也必须重建账本
# ---------------------------------------------------------------------------


async def test_cold_start_rebuilds_coin_balance_and_active_fires(tmp_path, monkeypatch):
    """DA-03 补：`coin_ledger`/`fire_runtime` 在 lifespan 构造，build_loop 只恢复世界。

    进程重启后两本账若不接线，余额归零（村民工钱凭空消失）且 `fire_seq` 归零
    ⇒ 下一场火重新签发 `fire-1`，与库里既有 `fire-1` 撞主键，`flush_tick` 抛
    `FireWriteError`（`ws.py` 驱动循环无 try/except ⇒ 世界直接停摆）。
    """

    async def idle_driver(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "run_world_driver", idle_driver)
    monkeypatch.chdir(tmp_path)
    captured = []

    async def capture(frame):
        captured.append(frame)

    monkeypatch.setattr(main.manager, "broadcast_json", capture)

    async with main.lifespan(main.app):
        app = main.app
        loop = app.state.loop
        assert app.state.coin_ledger.apply_grant("chenmo", 500, tick=loop.state.tick)
        loop.enqueue(coin_grant_event(loop.state.tick, "chenmo", 500, "工钱"))
        positions = [
            (x, y)
            for y in range(app.state.tile_map.height)
            for x in range(app.state.tile_map.width)
            if app.state.tile_map.is_walkable(x, y)
        ]
        for event in app.state.fire_runtime.ignite_at(
            tick=loop.state.tick, x=positions[0][0], y=positions[0][1]
        ):
            loop.enqueue(event)
        await app.state.flush_for_anchor()

    async with main.lifespan(main.app):
        app2 = main.app
        assert app2.state.loop.state.tick > 0
        assert app2.state.coin_ledger.balance_of("chenmo") == 500
        assert {cell.fire_id for cell in app2.state.fire_runtime.cells} == {"fire-1"}
        assert app2.state.fire_runtime.fire_seq == 1
        # 重启后的新火不得复用既有 ID（否则 flush 撞主键）
        events = app2.state.fire_runtime.ignite_at(
            tick=app2.state.loop.state.tick, x=positions[1][0], y=positions[1][1]
        )
        assert events[0].payload["fire_id"] == "fire-2"
        for event in events:
            app2.state.loop.enqueue(event)
        await app2.state.flush_for_anchor()
