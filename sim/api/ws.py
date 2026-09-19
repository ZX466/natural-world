"""WS 网关 — M0 渲染闭环的服务端（m0-core.md §5.1 + kilo ws-protocol.md）。

职责：外层 asyncio 驱动（喂 real_dt 给 TickLoop）→ 每帧 drain 事件落库、
增量广播。客户端消息一律视为不可信输入：type 白名单 + channel 校验
（codex C04 抽查意见，服务端是边界）。

出戏边界（W 系列）：state_delta/full_snapshot 只含 rtoken/位置/精灵名等
戏内渲染字段；tick/seed/branch/内部 id 绝不出网关。
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any

import structlog
from fastapi import WebSocket

from sim.core.tick import TickLoop
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder

logger = structlog.get_logger(__name__)

_PROTOCOL_VERSION = "0.1"
FRAME_BUDGET_SECONDS = 1 / 60  # 1x 驱动节拍；真实倍率由 GameClock.advance 换算

_ALLOWED_CLIENT_TYPES = {"move_request", "set_control", "sync_request", "hello"}


def _rtoken(entity_id: str) -> str:
    """内部 id → 不透明替身。M0 用固定前缀哈希；映射表属世界真相不出网关。"""
    import hashlib

    return "rt-" + hashlib.sha256(entity_id.encode()).hexdigest()[:12]


class ConnectionManager:
    """WS 连接登记与广播。"""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    def register(self, ws: WebSocket) -> None:
        self._connections.append(ws)

    def unregister(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)

    @property
    def count(self) -> int:
        return len(self._connections)

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister(ws)


def snapshot_payload(loop: TickLoop, tile_map: TileMap) -> dict[str, Any]:
    """全量快照（full_snapshot）。rtoken 替身；无 tick/seed/内部 id。

    sprite 名也从 rtoken 派生（内部 entity_id 不可出网关——W 系列出戏边界）。
    """
    actors = []
    for entity_id, entity in loop.state.entities.items():
        rt = _rtoken(entity_id)
        actors.append(
            {
                "rtoken": rt,
                "x": entity.pos[0],
                "y": entity.pos[1],
                "facing": "s",
                "sprite": rt,
                "anim": "idle",
            }
        )
    return {
        "type": "full_snapshot",
        "channel": "render",
        "v": _PROTOCOL_VERSION,
        "ws_seq": 0,
        "actors": actors,
        "lights": [],
        "structures": [],
        "map": {"w": tile_map.width, "h": tile_map.height, "tileset": "grid"},
        "weather": {"visual": "clear", "ambient_light": 1.0},
        "combat": None,
    }


def delta_payload(loop: TickLoop, moved_entity_ids: set[str]) -> dict[str, Any]:
    """增量（state_delta）。只含移动过的实体。"""
    actors = []
    for entity_id in moved_entity_ids:
        entity = loop.state.entities.get(entity_id)
        if entity is None:
            continue
        actors.append({"rtoken": _rtoken(entity_id), "x": entity.pos[0], "y": entity.pos[1]})
    return {
        "type": "state_delta",
        "channel": "render",
        "v": _PROTOCOL_VERSION,
        "ws_seq": 0,
        "actors": actors,
    }


def map_static_payload(tile_map: TileMap) -> dict[str, Any]:
    """碰撞层 HTTP 端点载荷（kilo 提案按 chunk 模式，codex 意见 5：静态资产不走 WS）。"""
    chunks = []
    for (cx, cy), chunk in sorted(tile_map.chunks.items()):
        bits = bytes(1 if w else 0 for w in chunk.collision)
        chunks.append({"cx": cx, "cy": cy, "collision_b64": base64.b64encode(bits).decode()})
    return {
        "w": tile_map.width,
        "h": tile_map.height,
        "tileset": "grid",
        "chunks": chunks,
    }


def handle_client_message(
    raw: dict[str, Any], loop: TickLoop, pf: Pathfinder
) -> dict[str, Any] | None:
    """不可信输入处理：type 白名单 + 字段校验。返回要回给该客户端的载荷（或 None）。

    move_request：目标格校验（界内+可通行）→ sim 寻路 → issue_move（走 apply 唯一写路径）。
    """
    msg_type = raw.get("type")
    if msg_type not in _ALLOWED_CLIENT_TYPES:
        logger.warning("ws.rejected_type", msg_type=str(msg_type))
        return {
            "type": "error",
            "channel": "error",
            "v": _PROTOCOL_VERSION,
            "ws_seq": 0,
            "code": "unknown_type",
            "message": "unsupported message type",
        }
    if raw.get("channel") != _CHANNEL_FOR.get(msg_type):
        return {
            "type": "error",
            "channel": "error",
            "v": _PROTOCOL_VERSION,
            "ws_seq": 0,
            "code": "bad_channel",
            "message": "channel mismatch",
        }

    if msg_type == "move_request":
        protagonist_id = _protagonist_id(loop)
        if protagonist_id is None:
            return None
        tx, ty = raw.get("target_x"), raw.get("target_y")
        if not (isinstance(tx, int) and isinstance(ty, int)):
            return None
        try:
            path = pf.find(loop.state.entities[protagonist_id].pos, (tx, ty))
        except ValueError:
            return None  # 不可达/不可通行：静默忽略（客户端已预检）
        loop.issue_move(protagonist_id, list(path))
        return None

    if msg_type == "sync_request":
        return {
            "type": "control_ack",
            "channel": "control",
            "v": _PROTOCOL_VERSION,
            "ws_seq": 0,
            "action": "resume",
            "applied": True,
            "speed": 1,
        }
    return None


_CHANNEL_FOR = {
    "move_request": "render",
    "set_control": "control",
    "sync_request": "session",
    "hello": "session",
}


def _protagonist_id(loop: TickLoop) -> str | None:
    """M0：主角=实体表第一个 id（陈默）；M1 由协议显式指定。"""
    for entity_id in loop.state.entities:
        return entity_id
    return None


async def run_world_driver(
    loop: TickLoop,
    manager: ConnectionManager,
    tile_map: TileMap,
    on_flush: Any = None,
) -> None:
    """外层 asyncio 驱动：固定节拍喂 real_dt → drain 事件（on_flush 落库）→ 广播增量。

    广播先于落库是有意设计（codex M0 评审意见 8）：WS 观察者先看到状态、
    事件日志稍后补齐——戏内通道无审计语义，不为观察者引入额外延迟。
    """
    last = time.monotonic()
    seq = 0
    while True:
        await asyncio.sleep(FRAME_BUDGET_SECONDS)
        now = time.monotonic()
        real_dt = now - last
        last = now
        n = loop.advance_frame(real_dt)
        if n == 0 and manager.count == 0:
            continue
        moved = loop.drain_delta()
        events = loop.drain_events()
        if events and on_flush is not None:
            await on_flush(events)
        if moved:
            seq += 1
            payload = delta_payload(loop, moved)
            payload["ws_seq"] = seq
            await manager.broadcast_json(payload)
