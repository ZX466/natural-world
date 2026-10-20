"""独立评审红钉：存档先落待写事件；LLM 等待后仍使用同意图对白。"""

import asyncio
import contextlib
from typing import cast

from fastapi.testclient import TestClient

from sim.agent.driver import ChenmoDriver
from sim.api import anchors
from sim.api.main import app
from sim.api.settings import get_profile_store
from sim.content.protagonist import build_anchor
from sim.core.clock import GameClock
from sim.core.events import move_event, npc_monologue_event
from sim.core.persistence.models import PlayerAnchor
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.llm.client import LlmClient, ProfileSnapshot
from sim.npc.speech_register import SpeechContext
from sim.tests.test_m4c_llm_driver import _fake_result, _FakeProfile


def test_save_flushes_pending_events_before_capturing_cursor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    get_profile_store().__init__(f"sqlite:///{tmp_path / 'settings.db'}")
    store = anchors.get_anchor_store()
    store.__init__(f"sqlite:///{tmp_path / 'world.db'}")
    with TestClient(app) as client:

        async def stop_driver():
            for _ in range(500):
                if await app.state.store.current_branch_id_or_none() is not None:
                    break
                await asyncio.sleep(0.01)
            app.state.driver.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await app.state.driver

        assert client.portal is not None
        client.portal.call(stop_driver)
        seq = anchors.get_current_seq()

        def queue_events():
            loop = app.state.loop
            start = loop.state.entities["chenmo"].pos
            goal = next(
                (start[0] + dx, start[1] + dy)
                for dx, dy in ((1, 0), (-1, 0), (0, 1))
                if app.state.tile_map.is_walkable(start[0] + dx, start[1] + dy)
            )
            loop.enqueue(move_event(loop.state.tick, "chenmo", start, goal, (start, goal)))
            loop.enqueue(npc_monologue_event(loop.state.tick, "chenmo", "bubble", "药铺还忙着。"))

        client.portal.call(queue_events)
        response = client.post("/api/anchors", json={"name": "留步"})
        assert response.status_code == 201
        with store.session() as session:
            row = session.get(PlayerAnchor, response.json()["id"])
            assert row is not None and row.seq == seq + 2


def test_dialogue_survives_world_tick_advance_during_llm():
    state = WorldState(
        entities={nid: EntityState(entity_id=nid, pos=(0, 0)) for nid in ("chenmo", "friend")}
    )
    loop = TickLoop(GameClock(speed=1), build_default_bus(), state)

    class Llm:
        async def complete(self, profile, messages, **kwargs):
            if kwargs.get("max_tokens_override") == 64:
                loop.state = loop.state.model_copy(update={"tick": 5})
                return _fake_result("小满，您先慢坐，茶还热着。")
            return _fake_result('{"action":"talk_to","target_id":"friend","reason":"我想问问近况"}')

    driver = ChenmoDriver(
        build_anchor(),
        cast("LlmClient", Llm()),
        lambda: cast("ProfileSnapshot", _FakeProfile()),
        speech_context_provider=lambda target: SpeechContext("士绅"),
    )
    assert asyncio.run(driver.decide_once(loop.state, 0))
    driver.execute_pending(loop, pathfinder=None)
    lines = [e.payload["line"] for e in loop.drain_events() if e.event_type.value == "npc.chat"]
    assert lines == ["小满，您先慢坐，茶还热着。"]


def test_production_build_completion_projects_all_tiles(tmp_path, monkeypatch):
    from sim.api import ws
    from sim.tests.test_build_entry_live import town_and_site

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ws, "_STRUCTURES", {})
    monkeypatch.setattr(ws, "_structures_broadcast", {})
    get_profile_store().__init__(f"sqlite:///{tmp_path / 'settings.db'}")
    anchors.get_anchor_store().__init__(f"sqlite:///{tmp_path / 'world.db'}")
    with TestClient(app) as client:

        async def complete_build():
            app.state.driver.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await app.state.driver
            _, pos = town_and_site()
            loop = app.state.loop
            runtime = app.state.build_runtime
            event = runtime.start("chenmo", pos, tick=loop.state.tick)
            assert event is not None
            loop.enqueue(event)
            finish = ((loop.state.tick + runtime.active_duration() + 9) // 10) * 10
            loop.state = loop.state.model_copy(update={"tick": finish})
            loop.advance_frame(1 / 60)
            await app.state.flush_for_anchor()
            from sim.api.main import _pathfinder

            assert not _pathfinder().tile_map.is_walkable(*pos)
            return ws.snapshot_payload(loop, runtime.tile_map)["structures"]

        assert client.portal is not None
        assert len(client.portal.call(complete_build)) == 4


def test_already_flushed_events_are_broadcast_without_second_write(monkeypatch):
    from collections import deque

    import pytest

    from sim.api import ws
    from sim.api.ws import ConnectionManager
    from sim.tests.test_build_entry_live import town_and_site

    monkeypatch.setattr(ws, "_MONO_HISTORY", deque(maxlen=200))
    town, _ = town_and_site()
    loop = TickLoop(GameClock(speed=1), build_default_bus(), WorldState(tick=12345))
    loop.pending_broadcast_events.append(
        npc_monologue_event(12345, "review_actor", "bubble", "铺子里还有热茶。")
    )
    written = []
    sent = []

    class Manager:
        count = 1

        def any_fast_forward_active(self):
            return False

        async def broadcast_json(self, frame):
            if frame["type"] == "monologue":
                sent.append(frame)
                raise asyncio.CancelledError

    async def flush(events):
        written.extend(events)

    async def run():
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(
                ws.run_world_driver(
                    loop, cast("ConnectionManager", Manager()), town, on_flush=flush
                ),
                timeout=2,
            )

    asyncio.run(run())
    assert written == []
    assert len(sent) == 1 and sent[0]["content"] == "铺子里还有热茶。"
    assert loop.pending_broadcast_events == []


def test_ambiguous_world_stays_unavailable_without_opening_main(tmp_path, monkeypatch):
    import time

    from sim.core.persistence.models import Branch

    monkeypatch.chdir(tmp_path)
    get_profile_store().__init__(f"sqlite:///{tmp_path / 'settings.db'}")
    store = anchors.get_anchor_store()
    store.__init__(f"sqlite:///{tmp_path / 'world.db'}")
    with store.session() as session:
        session.add_all([Branch(id=nid, status="active", is_current=False) for nid in ("a", "b")])
        session.commit()
    with TestClient(app) as client:
        time.sleep(0.05)  # 多个驱动帧窗口后仍不可猜测当前线。
        assert client.get("/api/health").json()["world_running"] is False
        assert client.post("/api/anchors", json={"name": "歇脚"}).status_code == 400
        with store.session() as session:
            assert {row.id for row in session.query(Branch).all()} == {"a", "b"}
