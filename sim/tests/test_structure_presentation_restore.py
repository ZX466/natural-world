"""DA-05：真实启动/读档/落库入口应同步建筑表现账本。"""

import asyncio

import pytest
from sqlalchemy import update

from sim.api import main, ws
from sim.api.anchors import AnchorStore
from sim.core.events import (
    structure_collapsed_event,
    structure_completed_event,
    structure_removed_event,
    structure_started_event,
)
from sim.core.persistence.models import Structure
from sim.core.persistence.npc_store import NpcStore


@pytest.fixture(autouse=True)
def isolated_presentation(monkeypatch):
    async def idle_driver(*args, **kwargs):
        await asyncio.Event().wait()

    frames = []

    async def capture(frame):
        frames.append(frame)

    monkeypatch.setattr(main, "run_world_driver", idle_driver)
    monkeypatch.setattr(main.manager, "broadcast_json", capture)
    ws.reset_structures()
    ws.reset_anchor_registry()
    yield frames
    ws.reset_structures()
    ws.reset_anchor_registry()


async def complete(app, sid, pos=(100, 53)):
    tick = app.state.loop.state.tick
    app.state.loop.enqueue(
        structure_started_event(
            tick,
            structure_id=sid,
            tiles=(pos,),
            kind="wall",
            material="wood",
            planned_duration_ticks=100,
            recipe_id="wall",
            recipe_version="1",
            build_rule_version="m4-v1",
        )
    )
    app.state.loop.enqueue(
        structure_completed_event(tick, structure_id=sid, quality=1.0, integrity=1.0)
    )
    await app.state.flush_for_anchor()


async def save(app, anchors, name):
    await app.state.flush_for_anchor()
    branch = await app.state.store.current_branch_id()
    rows = await app.state.store.read_branch_history(branch)
    return anchors.create_item(
        name,
        branch_id=branch,
        tick=app.state.loop.state.tick,
        seq=rows[-1]["seq"],
        rng_state=app.state.rng_capture(),
        state_hash=app.state.loop.state.state_hash(),
    ).id


async def load(app, anchor_id):
    assert ws._ANCHOR_LOAD_HOOK is not None
    ws._ANCHOR_LOAD_HOOK(anchor_id)
    await app.state.drain_pending_loads()
    assert app.state.load_outcomes[-1] == (anchor_id, True)


def phases():
    return {row["rtoken"]: row["phase"] for row in ws._structures_snapshot_payload()}


async def test_load_clears_stale_structure_ledger(tmp_path, isolated_presentation):
    async with main.lifespan(main.app):
        app = main.app
        anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
        before = await save(app, anchors, "before")
        await complete(app, "future")
        await save(app, anchors, "after")
        assert phases() == {"st-future": "built"}

        await load(app, before)

        branch = await app.state.store.current_branch_id()
        source = await NpcStore(app.state.store, branch_id=branch).materialize_structures()
        history = await app.state.store.read_branch_history(branch)
        structure_events = [r for r in history if r["event_type"].startswith("structure.")]
        assert phases() == {}, (
            f"branch structure source={list(source)}, bounded structure events={structure_events}"
        )
        snapshots = [f for f in isolated_presentation if f["type"] == "full_snapshot"]
        assert snapshots[-1]["structures"] == []


async def test_load_restores_current_branch_structures(tmp_path):
    async with main.lifespan(main.app):
        app = main.app
        anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
        await complete(app, "house")
        await complete(app, "ruin", (101, 53))
        app.state.loop.enqueue(
            structure_collapsed_event(app.state.loop.state.tick, structure_id="ruin", cause="decay")
        )
        target = await save(app, anchors, "saved-buildings")
        await complete(app, "future", (102, 53))
        await save(app, anchors, "future")

        await load(app, target)

        assert phases() == {"st-house": "built", "st-ruin": "rubble"}


@pytest.mark.parametrize("terminal", ["collapsed", "removed"])
async def test_load_restores_structure_before_future_terminal_event(tmp_path, terminal):
    async with main.lifespan(main.app):
        app = main.app
        anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
        await complete(app, "house")
        target = await save(app, anchors, "before-terminal")
        tick = app.state.loop.state.tick
        app.state.loop.enqueue(
            structure_collapsed_event(tick, structure_id="house", cause="decay")
            if terminal == "collapsed"
            else structure_removed_event(tick, structure_id="house", reason="demolished")
        )
        await save(app, anchors, "after-terminal")

        await load(app, target)

        assert phases() == {"st-house": "built"}


async def test_nested_load_bounds_each_ancestor_structure_history(tmp_path):
    async with main.lifespan(main.app):
        app = main.app
        anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
        await complete(app, "ancestor")
        ancestor_target = await save(app, anchors, "ancestor-target")
        await complete(app, "ancestor-future", (102, 53))
        await save(app, anchors, "ancestor-head")
        await load(app, ancestor_target)
        await complete(app, "child", (101, 53))
        child_target = await save(app, anchors, "child-target")
        await complete(app, "child-future", (103, 53))
        await save(app, anchors, "child-head")

        await load(app, child_target)

        assert phases() == {"st-ancestor": "built", "st-child": "built"}


@pytest.mark.parametrize("branch", ["main", "child"])
async def test_restart_populates_structures_from_branch(tmp_path, branch):
    async with main.lifespan(main.app):
        app = main.app
        await complete(app, "house")
        expected = {"st-house": "built"}
        if branch == "child":
            anchors = AnchorStore(f"sqlite:///{tmp_path / 'world.db'}")
            target = await save(app, anchors, "before-future")
            await complete(app, "future", (102, 53))
            await save(app, anchors, "after-future")
            await load(app, target)
            await complete(app, "child-only", (101, 53))
            app.state.loop.enqueue(
                structure_collapsed_event(
                    app.state.loop.state.tick, structure_id="house", cause="decay"
                )
            )
            await app.state.flush_for_anchor()
            expected = {"st-house": "rubble", "st-child-only": "built"}

    # 冷进程不会保留模块账本；重建必须来自当前分支，而不是上次内存或 main。
    ws.reset_structures()
    async with main.lifespan(main.app):
        assert phases() == expected


@pytest.mark.parametrize(
    ("domain_phase", "wire_phase"),
    [
        ("active", "built"),
        ("collapsing", "collapsing"),
        ("rubble", "rubble"),
        ("planned", None),
        ("building", None),
    ],
)
async def test_startup_maps_all_domain_phases(domain_phase, wire_phase):
    async with main.lifespan(main.app):
        await complete(main.app, "s1")
        async with main.app.state.store.session_factory.begin() as session:
            await session.execute(update(Structure).values(phase=domain_phase))

    # 投影行是启动的既有真源；中间相位没有独立事件，直接覆盖该列模拟既有存档。
    ws.reset_structures()
    async with main.lifespan(main.app):
        assert phases() == ({} if wire_phase is None else {"st-s1": wire_phase})


@pytest.mark.parametrize("terminal", ["collapsed", "removed"])
async def test_collapse_and_remove_projected(terminal):
    async with main.lifespan(main.app):
        app = main.app
        await complete(app, "s1")
        assert phases() == {"st-s1": "built"}  # 也建立广播基准。
        tick = app.state.loop.state.tick
        event = (
            structure_collapsed_event(tick, structure_id="s1", cause="decay")
            if terminal == "collapsed"
            else structure_removed_event(tick, structure_id="s1", reason="demolished")
        )
        app.state.loop.enqueue(event)
        await app.state.flush_for_anchor()
        delta = ws.delta_payload(app.state.loop, set()).get("structures", [])

        if terminal == "collapsed":
            assert phases() == {"st-s1": "rubble"}
            assert delta == [{"op": "add", "rtoken": "st-s1", "x": 100, "y": 53, "phase": "rubble"}]
        else:
            assert phases() == {}
            assert delta == [{"op": "remove", "rtoken": "st-s1"}]
        assert ws._structures_delta_payload() == []
        history = await app.state.store.read_branch_history("main")
        assert sum(row["event_type"] == "tile_changed" for row in history) == 1
