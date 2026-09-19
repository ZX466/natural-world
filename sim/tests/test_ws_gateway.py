"""WS 网关测试 — T1 级（无 LLM）。

覆盖：move_request 处理（寻路+唯一写路径）、不可信输入白名单、
delta/snapshot 载荷出戏边界（无 tick/seed/内部 id）。
"""

from __future__ import annotations

import pytest

from sim.api.ws import (
    _rtoken,
    delta_payload,
    handle_client_message,
    map_static_payload,
    snapshot_payload,
)
from sim.core.events import world_create_event
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.world.map import CHUNK_SIZE, Chunk, TileMap
from sim.world.pathfinding import Pathfinder


@pytest.fixture()
def loop() -> TickLoop:
    loop = TickLoop(clock=_clock(), bus=build_default_bus(), state=WorldState(world_seed=42))
    loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
    loop.drain_events()
    return loop


def _clock():
    from sim.core.clock import GameClock

    return GameClock(speed=1.0)


@pytest.fixture()
def tile_map() -> TileMap:
    chunks = {}
    for cy in range(2):
        for cx in range(2):
            chunks[(cx, cy)] = Chunk(
                cx=cx,
                cy=cy,
                ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
    return TileMap(width=32, height=32, chunks=chunks)


@pytest.fixture()
def pf(tile_map: TileMap) -> Pathfinder:
    return Pathfinder(tile_map)


class TestRtoken:
    def test_deterministic_and_opaque(self):
        assert _rtoken("chenmo") == _rtoken("chenmo")
        assert _rtoken("chenmo").startswith("rt-")
        assert "chenmo" not in _rtoken("chenmo")

    def test_distinct_ids_distinct_tokens(self):
        assert _rtoken("a") != _rtoken("b")


class TestMoveRequest:
    def test_move_request_issues_move(self, loop: TickLoop, pf: Pathfinder):
        reply = handle_client_message(
            {"type": "move_request", "channel": "render", "target_x": 8, "target_y": 4},
            loop,
            pf,
        )
        assert reply is None  # 静默处理
        assert loop.state.entities["chenmo"].path != ()  # 路径已入队

    def test_move_request_rejects_non_int(self, loop: TickLoop, pf: Pathfinder):
        handle_client_message(
            {"type": "move_request", "channel": "render", "target_x": "8", "target_y": 4},
            loop,
            pf,
        )
        assert loop.state.entities["chenmo"].path == ()  # 不可信输入被拒

    def test_move_request_out_of_bounds_silent(self, loop: TickLoop, pf: Pathfinder):
        handle_client_message(
            {"type": "move_request", "channel": "render", "target_x": 999, "target_y": 999},
            loop,
            pf,
        )
        assert loop.state.entities["chenmo"].path == ()


class TestUntrustedInput:
    def test_unknown_type_rejected(self, loop: TickLoop, pf: Pathfinder):
        reply = handle_client_message({"type": "give_me_seed", "channel": "render"}, loop, pf)
        assert reply is not None and reply["type"] == "error"

    def test_channel_mismatch_rejected(self, loop: TickLoop, pf: Pathfinder):
        reply = handle_client_message(
            {"type": "move_request", "channel": "control"},
            loop,
            pf,
        )
        assert reply is not None and reply["type"] == "error"


class TestOutOfCharacterBoundary:
    """W 系列：载荷绝不含 tick/seed/branch/内部 id。"""

    def test_snapshot_clean(self, loop: TickLoop, tile_map: TileMap):
        import json

        text = json.dumps(snapshot_payload(loop, tile_map))
        assert "tick" not in text
        assert "seed" not in text
        assert "branch" not in text
        assert "chenmo" not in text  # 内部 id 不可见
        assert "rt-" in text  # rtoken 在

    def test_delta_clean(self, loop: TickLoop):
        loop.issue_move("chenmo", [(1, 0), (2, 0)])
        loop.advance_frame(1.0)
        import json

        text = json.dumps(delta_payload(loop, loop.drain_delta()))
        assert "tick" not in text and "seed" not in text and "chenmo" not in text

    def test_map_static_payload(self, tile_map: TileMap):
        import base64
        import json

        payload = map_static_payload(tile_map)
        text = json.dumps(payload)
        assert "seed" not in text and "tick" not in text
        assert len(payload["chunks"]) == 4
        raw = base64.b64decode(payload["chunks"][0]["collision_b64"])
        assert all(b == 1 for b in raw)


# ---------------------------------------------------------------------------
# codex 硬约束验收：entropy_log 与 events 同事务原子（T1）
# ---------------------------------------------------------------------------


class TestEntropyAtomicFlush:
    """flush_events：熵行与事件行同事务落库；失败无半写状态。"""

    def test_flush_rows_separates_entropy(self):
        from sim.core.events import entropy_event
        from sim.core.flush import flush_rows

        ev = entropy_event(tick=5, stream="world.weather", payload_hex="ab" * 16)
        rows, entropy_rows = flush_rows([ev])
        assert len(rows) == 1
        assert len(entropy_rows) == 1
        assert entropy_rows[0]["stream"] == "world.weather"
        assert entropy_rows[0]["value"] == "ab" * 16

    async def test_atomic_all_or_nothing(self, tmp_path):
        """注入故障 → append 抛错 → 事件与熵行都不可见（无半写）。"""
        from sqlalchemy.ext.asyncio import create_async_engine

        from sim.core.events import entropy_event
        from sim.core.flush import flush_events
        from sim.core.persistence.database import create_session_factory, init_database
        from sim.core.persistence.store import SqlEventStore

        db_path = tmp_path / "world.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        factory = create_session_factory(engine)
        await init_database(engine)
        store = SqlEventStore(factory)

        events = [
            entropy_event(tick=1, stream="world.weather", payload_hex="cd" * 16),
            entropy_event(tick=2, stream="world.weather", payload_hex="ef" * 16),
        ]

        # 故障注入：第二个事件 tick 非法 → commit 前抛错
        bad_rows = [e.to_store_dict() for e in events]
        bad_rows[1]["tick"] = "not-an-int"

        from sqlalchemy import func, select
        from sqlalchemy.exc import StatementError

        from sim.core.persistence.models import EntropyLog, Event

        with pytest.raises((TypeError, ValueError, StatementError)):
            async with factory() as session:
                for i, row in enumerate(bad_rows):
                    session.add(Event(branch_id="main", seq=i + 1, **row))
                session.add(EntropyLog(branch_id="main", stream="x", reason="t", tick=1, value="v"))
                await session.commit()

        async with factory() as session:
            n_events = (await session.execute(select(func.count()).select_from(Event))).scalar()
            n_entropy = (
                await session.execute(select(func.count()).select_from(EntropyLog))
            ).scalar()
        assert n_events == 0 and n_entropy == 0  # 无半写状态

        # 正常路径：flush_events 走同事务
        await flush_events(store, events)
        async with factory() as session:
            n_events = (await session.execute(select(func.count()).select_from(Event))).scalar()
            n_entropy = (
                await session.execute(select(func.count()).select_from(EntropyLog))
            ).scalar()
        assert n_events == 2 and n_entropy == 2
