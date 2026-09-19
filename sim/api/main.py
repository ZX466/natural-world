"""FastAPI 应用装配 — M0（sim/api/main.py）。

路由：/api/health（戏外探针）/ /api/world/map（碰撞层静态资产，HTTP 不走 WS）/
/ws（WS 网关）。启动即建世界（创世事件走 apply），驱动任务随 lifespan 起。
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from sim.api.settings import router as settings_router
from sim.api.ws import (
    ConnectionManager,
    handle_client_message,
    map_static_payload,
    run_world_driver,
    snapshot_payload,
)
from sim.core.events import world_create_event
from sim.core.persistence.database import create_session_factory, init_database
from sim.core.persistence.store import SqlEventStore
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.world.map import TileMap

manager = ConnectionManager()

# M0：默认 32x32 开阔图（占位；内容管线接入后由 sim/content 加载 Tiled 转换产物）


def _default_map() -> TileMap:
    from sim.world.map import CHUNK_SIZE, Chunk

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


async def build_loop() -> tuple[TickLoop, Any]:
    """组装世界：store（建表）+ bus + TickLoop + 创世。返回 (loop, store)。"""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///world.db")
    await init_database(engine)  # 开发库快速起步；生产走 alembic upgrade head
    session_factory = create_session_factory(engine)
    store = SqlEventStore(session_factory)
    loop = TickLoop(clock=_make_clock(), bus=build_default_bus(), state=WorldState(world_seed=42))
    loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
    return loop, store


def _make_clock():
    from sim.core.clock import GameClock

    return GameClock(speed=1.0)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    import asyncio

    loop, store = await build_loop()
    tile_map = _default_map()

    async def on_flush(events: list[Any]) -> None:
        from sim.core.flush import flush_events

        await flush_events(store, events)

    app.state.loop = loop
    app.state.store = store
    app.state.tile_map = tile_map
    app.state.driver = asyncio.create_task(run_world_driver(loop, manager, tile_map, on_flush))
    yield
    app.state.driver.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await app.state.driver


app = FastAPI(title="临河镇 sim", version="0.1.0", lifespan=lifespan)
app.include_router(settings_router)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    loop: TickLoop = app.state.loop
    return {
        "status": "ok",
        "world_running": True,
        "in_combat": loop.context.combat_active,
    }


@app.get("/api/world/map")
async def world_map() -> dict[str, Any]:
    """碰撞层静态资产（codex 意见 5：走 HTTP 不走 WS；kilo chunk 提案已批）。"""
    return map_static_payload(app.state.tile_map)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    manager.register(ws)
    pf = _pathfinder()
    try:
        # 接入即发全量快照（kilo ws-protocol：sync 的答案）
        await ws.send_json(snapshot_payload(app.state.loop, app.state.tile_map))
        while True:
            raw = await ws.receive_json()
            reply = handle_client_message(raw, app.state.loop, pf)
            if reply is not None:
                await ws.send_json(reply)
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(ws)


def _pathfinder():
    from sim.world.pathfinding import Pathfinder

    return Pathfinder(app.state.tile_map)
