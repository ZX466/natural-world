"""WS 网关 — M0 渲染闭环的服务端（m0-core.md §5.1 + kilo ws-protocol.md）。

职责：外层 asyncio 驱动（喂 real_dt 给 TickLoop）→ 每帧 drain 事件落库、
增量广播。客户端消息一律视为不可信输入：type 白名单 + channel 校验
（codex C04 抽查意见，服务端是边界）。

六类 C→S 消息各有 `_handle_*` 纯分发块（契约见 docs/api/ws-dispatch-proposal.md）：
move_request / hello / sync_request / set_control / player_impulse / load_anchor。
`handle_client_message` 同步、无 IO、可单测——异步面（落库、驱动、LLM）全在网关外层。

出戏边界（W 系列）：state_delta/full_snapshot 只含 rtoken/位置/精灵名等
戏内渲染字段；tick/seed/branch/内部 id 绝不出网关。

M5-K8 意愿独白 S2C（产码走事件流）——两案对比与主张：
- 案 A（采纳）：NPC 独白先落 **`npc.monologue` WorldEvent**（§14 世界真相进事件
  日志），WS 侧只做「事件 → 帧」投影按 form 投递。可重放、可审计、与 npc.act /
  matter.* 同口径；内容零改写（逐位一致）。
- 案 B（否决）：直接构造 monologue 帧广播、不落事件日志。省一次投影，但**帧不
  可重放/重连不可重建**（§14 铁律），且绕过事件白名单护栏（数值可夹带）。
  流量收益微不足道（每帧一次 delta 内可选批量带出），不足以抵倒可重放性。
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import secrets
import time
from typing import Any

import structlog
from fastapi import WebSocket

from sim.core.calendar import game_time
from sim.core.events import EventKind, WorldEvent
from sim.core.tick import TickLoop
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder

logger = structlog.get_logger(__name__)

_PROTOCOL_VERSION = "1.0"  # versioning.md §1 基线 1.0（major.minor）；与前端 net/ws.ts 同步
FRAME_BUDGET_SECONDS = 1 / 60  # 1x 驱动节拍；真实倍率由 GameClock.advance 换算

# K4 提案 §2.2/§3.2：五类 C→S 消息在此与 _CHANNEL_FOR **成对**注册
# （落单会让 ws.py 的 channel 校验回 bad_channel——§7 #18 有配对钉子）。
_ALLOWED_CLIENT_TYPES = {
    "move_request",
    "set_control",
    "sync_request",
    "hello",
    "player_impulse",
    "load_anchor",
}

# §5.1 / 8.8：error code 全量词表（一律小写 snake；§7 #15 有越界钉子）
_ERROR_UNKNOWN_TYPE = "unknown_type"
_ERROR_BAD_CHANNEL = "bad_channel"
_ERROR_AUTH = "auth_error"
_ERROR_BAD_ACTION = "bad_action"
_ERROR_BAD_SPEED = "bad_speed"
_ERROR_BAD_IMPULSE = "bad_impulse"
_ERROR_IMPULSE_TOO_LONG = "impulse_too_long"
_ERROR_BAD_ANCHOR = "bad_anchor"
_ERROR_LOAD_FAILED = "load_failed"
_ERROR_BAD_TARGET = "bad_target"

# ---------------------------------------------------------------------------
# W6 WS 鉴权（codex M1 终审前置项；cline P04 结论：零新依赖）
# 方案：启动期本地 token + Origin/Host 白名单双层。
# - token：进程启动生成，M0/M1 单机形态下经同源 HTTP 端点下发（/api/ws-token）；
#   客户端 connect 后首条消息必须为 {"type":"hello","token": ...}，hmac 比对。
# - Origin：握手前校验，白名单 = 同机来源（localhost/127.0.0.1 + 扩展）。
#   防：恶意网页探测 ws://127.0.0.1:8000/ws（浏览器会带真实 Origin）。
#   已知边界：非浏览器客户端可伪造 Origin——对 M1 本机威胁模型（防网页
#   匿名接入）足够；M2 若开放局域网需升级 token 为每连接一次性挑战。
# ---------------------------------------------------------------------------
_ALLOWED_ORIGINS = frozenset(
    {
        "http://localhost:5173",  # Vite dev
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "null",  # file:// 页面（E2E 冒烟用）——仅 localhost 绑定下无实害
    }
)

_WS_AUTH_TOKEN: str | None = None  # 懒生成（首次取用时）


def ws_auth_token() -> str:
    """进程级 WS 鉴权 token（启动后不变；测试可用 reset_ws_auth_token 重置）。"""
    global _WS_AUTH_TOKEN
    if _WS_AUTH_TOKEN is None:
        _WS_AUTH_TOKEN = secrets.token_urlsafe(32)
    return _WS_AUTH_TOKEN


def reset_ws_auth_token() -> None:
    """测试辅助：清空 token（下个请求重新生成）。"""
    global _WS_AUTH_TOKEN
    _WS_AUTH_TOKEN = None


def check_origin(origin: str | None) -> bool:
    """握手 Origin 校验。None（非浏览器/同源直连）放行——绑定 127.0.0.1 下无实害。"""
    if origin is None:
        return True
    return origin in _ALLOWED_ORIGINS


def check_hello_auth(raw: dict[str, Any]) -> bool:
    """hello 消息携带的 token 比对（hmac.compare_digest 防时序侧信道）。"""
    provided = raw.get("token")
    if not isinstance(provided, str):
        return False
    return hmac.compare_digest(provided, ws_auth_token())


def _rtoken(entity_id: str) -> str:
    """内部 id → 不透明替身。M0 用固定前缀哈希；映射表属世界真相不出网关。

    12 hex = 48 bit，碰撞期望在实体规模 ≤10^4 时可忽略（n²/2^49）；
    超过该规模或出现实体身份安全语义前，扩到 16 hex 并复审。
    """
    import hashlib

    return "rt-" + hashlib.sha256(entity_id.encode()).hexdigest()[:12]


class ConnectionManager:
    """WS 连接登记与广播。"""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        #: 每连接订阅者身份（K8 独白投递面路由）：WebSocket → entity_id。
        #: 缺席=旁观者（未绑定视角，默认）；在册=绑定该实体视角的「本人」连接。
        #: 无身份登记时全部按旁观者处理（向后兼容 M0-M5：现有测试不传 subscriber）。
        self._subscribers: dict[WebSocket, str] = {}

    def register(self, ws: WebSocket, subscriber_id: str | None = None) -> None:
        """登记连接；subscriber_id 非空=绑定该实体视角（本人面板），空=旁观者。"""
        self._connections.append(ws)
        if subscriber_id is not None:
            self._subscribers[ws] = subscriber_id

    def unregister(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        self._subscribers.pop(ws, None)

    @property
    def count(self) -> int:
        return len(self._connections)

    def subscriber_of(self, ws: WebSocket) -> str | None:
        """该连接绑定的实体视角 id；None=旁观者。"""
        return self._subscribers.get(ws)

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        await self._send_to(self._connections, payload)

    async def send_to_subscriber(self, entity_id: str, payload: dict[str, Any]) -> None:
        """定向投递：只发给绑定该实体视角的连接（独白 thought 面板用）。"""
        targets = [ws for ws in self._connections if self._subscribers.get(ws) == entity_id]
        await self._send_to(targets, payload)

    async def _send_to(self, targets: list[WebSocket], payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister(ws)


#: 独白 form → 投递面（M5-K8 契约，§8 三形态）。
#: - bubble：头顶气泡，**旁观者可见** → 广播全部连接；
#: - thought：思维面板，**仅本人可见**（他人不可知心里话）→ 定向订阅者；
#: - plan：计划看板，**旁观者可见**（计划是外在可观察行为面，非私密）→ 广播。
#: 帧本身不带 actor/rtoken（ws-protocol §4.2 W7 字段最小化：独白只含 form+content），
#: 故路由**只能由服务端按 form 决定**，不进载荷——这是刻意的出戏边界（防客户端反推）。
MONOLOGUE_DELIVERY_ALL = frozenset({"bubble", "plan"})
MONOLOGUE_DELIVERY_SELF = frozenset({"thought"})


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
    """增量（state_delta）。只含移动过的实体。

    `plan` 是顶层可选键（m4-plan 裁 14-3：改计划不必伴随移动——塞 ActorDelta
    会被 moved 过滤漏掉，故与 actors/lights 并列）。账本为空则**不发该键**
    （可选字段不制造噪声）；已清计划的实体发 `text:""`（前端收起看板）。
    rtoken 替身出网关；账本可能残留已注销实体 → 按世界表过滤。
    """
    from sim.npc.plan_view import registry

    actors = []
    for entity_id in moved_entity_ids:
        entity = loop.state.entities.get(entity_id)
        if entity is None:
            continue
        actors.append({"rtoken": _rtoken(entity_id), "x": entity.pos[0], "y": entity.pos[1]})
    payload: dict[str, Any] = {
        "type": "state_delta",
        "channel": "render",
        "v": _PROTOCOL_VERSION,
        "ws_seq": 0,
        "actors": actors,
    }
    known = registry().entries()
    plan_items = [
        {"rtoken": _rtoken(entity_id), "text": plan_text}
        for entity_id, plan_text in sorted(known.items())
        if entity_id in loop.state.entities
    ]
    if plan_items:
        payload["plan"] = plan_items
    return payload


def monologue_payload(form: str, content: str) -> dict[str, Any]:
    """独白帧（monologue，narrative 通道；§8 三形态）。

    帧只含 form + content（ws-protocol §4.2 W7 字段最小化：**无 rtoken/actor**）。
    投递面由 `route_monologue` 按 form 决定，不进载荷（出戏边界）。
    """
    return {
        "type": "monologue",
        "channel": "narrative",
        "v": _PROTOCOL_VERSION,
        "ws_seq": 0,
        "form": form,
        "content": content,
    }


def monologue_events_to_frames(events: list[WorldEvent]) -> list[tuple[str, dict[str, Any]]]:
    """本帧 npc.monologue 事件 → [(actor_id, 帧), ...]（K8 事件进流案的 WS 侧）。

    事件是真相来源（§14，进事件日志可重放）；本函数只做「事件 → 投递单元」的
    投影，**不改内容**（逐位一致：帧 content 即事件 payload content）。actor_id
    从事件 actor_id 取（路由用，不出网关——帧里没有它）。
    """
    frames: list[tuple[str, dict[str, Any]]] = []
    for e in events:
        if e.event_type is not EventKind.NPC_MONOLOGUE:
            continue
        payload = e.payload
        frames.append(
            (
                e.actor_id,
                monologue_payload(str(payload["form"]), str(payload["content"])),
            )
        )
    return frames


async def route_monologue(manager: ConnectionManager, actor_id: str, frame: dict[str, Any]) -> None:
    """按 form 投递独白帧（M5-K8 投递面契约）。

    - bubble/plan → 广播（旁观者可见：气泡/看板是外在可观察面）；
    - thought    → 定向本人（思维面板=私密心里话，他人不可知）；
    - 未知 form   → fail-closed 不投递（不猜面，防未来档位扩展时误广播私密内容）。
    """
    form = str(frame.get("form", ""))
    if form in MONOLOGUE_DELIVERY_ALL:
        await manager.broadcast_json(frame)
    elif form in MONOLOGUE_DELIVERY_SELF:
        await manager.send_to_subscriber(actor_id, frame)
    # 未知 form：静默不投（fail-closed）


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
    """不可信输入处理：type 白名单 + channel 校验。返回要回给该客户端的载荷（或 None）。

    分发块：move_request / hello / sync_request / set_control / player_impulse / load_anchor
    （各 _handle_* 是纯函数，可单测；契约见 docs/api/ws-dispatch-proposal.md §1-§3）。
    """
    msg_type = raw.get("type")
    if msg_type not in _ALLOWED_CLIENT_TYPES:
        logger.warning("ws.rejected_type", msg_type=str(msg_type))
        return _error_frame(str(msg_type), _ERROR_UNKNOWN_TYPE, "unsupported message type")
    if raw.get("channel") != _CHANNEL_FOR.get(msg_type):
        return _error_frame(str(msg_type), _ERROR_BAD_CHANNEL, "channel mismatch")

    if msg_type == "move_request":
        return _handle_move_request(raw, loop, pf)
    if msg_type == "hello":
        # W6：hello 是鉴权握手。token 对 → 确认；错/缺 → auth_error（客户端应重连取新 token）
        if check_hello_auth(raw):
            return {
                "type": "hello_ack",
                "channel": "session",
                "v": _PROTOCOL_VERSION,
                "ws_seq": 0,
            }
        return _error_frame("hello", _ERROR_AUTH, "authentication failed")
    if msg_type == "sync_request":
        return _handle_sync_request(loop, pf)
    if msg_type == "set_control":
        return _handle_set_control(raw, loop)
    if msg_type == "player_impulse":
        return _handle_player_impulse(raw)
    if msg_type == "load_anchor":
        return _handle_load_anchor(raw, loop, pf)
    return None


def _error_frame(ref: str, code: str, message: str) -> dict[str, Any]:
    """WsErrorMessage 统一构造（§5.1：code 一律小写 snake）。"""
    return {
        "type": "error",
        "channel": "error",
        "v": _PROTOCOL_VERSION,
        "ws_seq": 0,
        "ref": ref,
        "code": code,
        "message": message,
    }


def _handle_move_request(
    raw: dict[str, Any], loop: TickLoop, pf: Pathfinder
) -> dict[str, Any] | None:
    """§4 / 8.6：非法类型目标升级为 error{code:"bad_target"}；不可达保留静默。

    （高频消息，error 帧会增加噪声——权衡见 §4，kilo 建议只升非法类型。）
    """
    protagonist_id = _protagonist_id(loop)
    if protagonist_id is None:
        return None  # 主角不存在是世界态问题，非客户端输入缺陷
    tx, ty = raw.get("target_x"), raw.get("target_y")
    # bool 是 int 子类：JSON true/false 会被当 1/0 送寻路（codex P3 #1）
    if not (
        isinstance(tx, int)
        and isinstance(ty, int)
        and not isinstance(tx, bool)
        and not isinstance(ty, bool)
    ):
        return _error_frame("move_request", _ERROR_BAD_TARGET, "那个地方去不了。")
    try:
        path = pf.find(loop.state.entities[protagonist_id].pos, (tx, ty))
    except ValueError:
        return None  # 不可达/不可通行：静默忽略（客户端已预检，§4 权衡结论）
    loop.issue_move(protagonist_id, list(path))
    return None


def _handle_sync_request(loop: TickLoop, pf: Pathfinder) -> dict[str, Any]:
    """K4 提案 §5 / §8.7（M5-K5 首修）：契约要求回全量 full_snapshot。

    （旧代码错回 control_ack，与 set_control 确认语义冲突；tile_map 经 pf.tile_map 取，
    Pathfinder 已持引用见 pathfinding.py:96-98——§8.5 备选案，签名不变。）
    """
    return snapshot_payload(loop, pf.tile_map)


def _handle_set_control(raw: dict[str, Any], loop: TickLoop) -> dict[str, Any]:
    """K4 提案 §1：set_control 分发块（原静默 return None——客户端永远收不到 ack）。

    applied 恒 true（8.1 占位，§1.3）；pause/resume 携带 speed 容忍忽略（8.2）；
    speed 校验必须排除 bool（§1.4：JSON true 是 int 子类且 true ∈ {1,4,16}）。
    """
    action = raw.get("action")
    if action == "set_speed":
        speed = raw.get("speed")
        # bool 是 int 子类 → isinstance(True, int) 为真，必须显式排除
        if not isinstance(speed, int) or isinstance(speed, bool) or speed not in (1, 4, 16):
            return _error_frame("set_control", _ERROR_BAD_SPEED, "快不了那么慢，也快不了那么快。")
        loop.clock.set_speed(float(speed))
        return _control_ack("set_speed", speed=speed)
    if action == "pause":
        _PRE_PAUSE_SPEED.append(loop.clock.speed)  # 连接级会话状态（§1.2：不进 GameClock）
        loop.clock.set_speed(0.0)
        return _control_ack("pause")
    if action == "resume":
        restored = _PRE_PAUSE_SPEED.pop() if _PRE_PAUSE_SPEED else 1.0
        loop.clock.set_speed(restored)
        return _control_ack("resume", speed=int(restored))
    return _error_frame("set_control", _ERROR_BAD_ACTION, "不知道要怎么调。")


def _control_ack(action: str, speed: int | None = None) -> dict[str, Any]:
    """ControlAckMessage 构造（§1.2：pause 的 ack 不带 speed——schema enum 无 0）。"""
    ack: dict[str, Any] = {
        "type": "control_ack",
        "channel": "control",
        "v": _PROTOCOL_VERSION,
        "ws_seq": 0,
        "action": action,
        "applied": True,  # 8.1：恒 true 占位；未来钳制场景再引入 false
    }
    if speed is not None:
        ack["speed"] = speed
    return ack


# §1.2：pause 前的倍率 = 连接级会话状态。栈形即可覆盖「pause→pause」；
# M2 多连接前改为 ConnectionManager 每连接字段（提案 §1.2 注记）。
_PRE_PAUSE_SPEED: list[float] = []


def reset_pre_pause_speed() -> None:
    """测试辅助：清空暂停前倍率栈。"""
    _PRE_PAUSE_SPEED.clear()


def _handle_player_impulse(raw: dict[str, Any]) -> dict[str, Any]:
    """K4 提案 §2：注册 + 入站校验 + 乐观 impulse_feedback（ws-protocol.md §6 入网即回）。

    同步纯函数：不 await LLM、不改 Agent 状态（写路径唯一 = apply）。
    冲突度规则表 / 叙事化模板归 LLM 域（8.3）,本块按占位 cue 与模板作答。
    """
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        return _error_frame("player_impulse", _ERROR_BAD_IMPULSE, "念头还没成形。")
    if len(text) > 64:  # PlayerImpulseMessage.text maxLength 64
        return _error_frame("player_impulse", _ERROR_IMPULSE_TOO_LONG, "话说得太长了，说不清。")
    return {
        "type": "impulse_feedback",
        "channel": "control",
        "v": _PROTOCOL_VERSION,
        "ws_seq": 0,
        "injected": True,  # §2.5：已接受并投递（不保证 LLM 已处理——异步）
        "cue": _impulse_cue(text),
        "reaction_monologue": {
            "form": "thought",
            "content": "这话我记下了。",
        },
    }


def _impulse_cue(text: str) -> str:
    """§8.3 占位：冲突度规则表在 M4 前由 LLM 域定稿；此处只做非接受态的粗判。

    **M5-K7 钩子缝**：真实规则表接入点 = `WillingnessExpression.band → cue`
    映射（映射表在 `sim/npc/plan_view.py` 的 `band_to_cue`，will.py 四档
    pure function 是输入真源）。接入时执行器把 `WillingnessVerdict.band`
    透传到本函数签名（新增 band 参即可，词面启发式分支整体退役）；在那之前
    本占位保持既有语义不回退——问号/感叹号启发式已有测试钉住。
    """
    stripped = text.strip()
    if stripped.endswith(("？", "?")):
        return "hesitation"
    if stripped.endswith(("！", "!")):
        return "complaint"
    return "accepted"


_ANCHOR_IDS: set[str] = set()  # anchor id 集（真实查询走 async DB，见 _ANCHOR_SYNCHRONOUS 注记）
#: 载入钩子（同步布尔契约）。默认 None → 只查 _ANCHOR_IDS 存在性。
#: ws_endpoint 装配时挂真实「定位→快照→重放」入口（§3.4 长期 driver 路径）。
_ANCHOR_LOAD_HOOK: Any = None


def reset_anchor_registry() -> None:
    """测试辅助：清空 anchor id 集与载入钩子。"""
    _ANCHOR_IDS.clear()
    global _ANCHOR_LOAD_HOOK
    _ANCHOR_LOAD_HOOK = None


def register_anchor_id(anchor_id: str) -> None:
    """登记已知 anchor id（后台 HTTP/落库路径调用；供 WS 分发块同步查表）。"""
    _ANCHOR_IDS.add(anchor_id)


def _handle_load_anchor(
    raw: dict[str, Any], loop: TickLoop, pf: Pathfinder
) -> dict[str, Any] | None:
    """K4 提案 §3：注册 + 失败不断线 + 成功短期同步 full_snapshot（8.4 定案）。

    anchor_id 是**不透明串**（§6.5：禁 anc_ 之类前缀特征校验）——非法只回 bad_anchor，
    形状不被特征拒绝。载入执行失败（重放损坏等）降级为 load_failed，绝不炸断 handler。
    """
    anchor_id = raw.get("anchor_id")
    if not isinstance(anchor_id, str) or not anchor_id:
        return _error_frame("load_anchor", _ERROR_BAD_ANCHOR, "没这个档。")
    try:
        ok = (
            _ANCHOR_LOAD_HOOK(anchor_id)
            if _ANCHOR_LOAD_HOOK is not None
            else (anchor_id in _ANCHOR_IDS)
        )
    except Exception:
        # 重放中世界状态损坏等执行异常：降级 load_failed，连接保持（§3.3）
        logger.warning("ws.anchor_load_failed", reason="hook_exception")
        return _error_frame("load_anchor", _ERROR_LOAD_FAILED, "这个档读不出来了。")
    if not ok:
        return _error_frame("load_anchor", _ERROR_LOAD_FAILED, "这个档读不出来了。")
    # 短期同步路径（§3.4）：复用 snapshot_payload；长期 driver 化后本分支由广播接替。
    return snapshot_payload(loop, pf.tile_map)


_CHANNEL_FOR = {
    "move_request": "render",
    "set_control": "control",
    "sync_request": "session",
    "hello": "session",
    "player_impulse": "control",
    "load_anchor": "session",
}


def _protagonist_id(loop: TickLoop) -> str | None:
    """M0：主角=实体表第一个 id（陈默）；M1 由协议显式指定。"""
    for entity_id in loop.state.entities:
        return entity_id
    return None


#: 主角连接的独白订阅者标识（M5-K8 投递面路由）。
#: 由**服务端**取主角 id（不采客户端自报，防身份自授/越权读他人思维面板）；
#: 玩家连接=本人视角，其余连接=旁观者。真实多视角切换（M1 协议显式指定主角）
#: 到位后此处替换为「按连接绑定的视角实体」，ConnectionManager 无需再改。
def subscriber_for_protagonist(loop: TickLoop) -> str | None:
    """连接订阅者身份：主角 id（无实体时 None=纯旁观者）。"""
    return _protagonist_id(loop)


async def run_world_driver(
    loop: TickLoop,
    manager: ConnectionManager,
    tile_map: TileMap,
    on_flush: Any = None,
    on_day_switch: Any = None,
) -> None:
    """外层 asyncio 驱动：固定节拍喂 real_dt → drain 事件（on_flush 落库）→ 广播增量。

    广播先于落库是有意设计（codex M0 评审意见 8）：WS 观察者先看到状态、
    事件日志稍后补齐——戏内通道无审计语义，不为观察者引入额外延迟。

    on_day_switch(day)：日切钩子（M3 B-B2 反思批处理挂载点，m3-plan 批次 B
    「世界循环在固定执行序事件结算后调用」）。同步回调（run_reflection 是
    纯同步批处理；无 IO，LLM 摘要挂载点在 _llm_summarize 内部决策缝）。
    **跨越判定**（prev_day != new_day
    时逐日各回调一次）而非 reflection_due 等值判定——帧驱动一帧推进 0..N tick
    （16x 下 ~16 tick/帧，catch-up 上限 240），等值点会被整帧跳过（75-94% 的
    日切丢失）；多日跨越按日序逐个补发，missed days 不静默吞。时序：on_flush
    之后（反思素材须当日事件已落库）。
    """
    last = time.monotonic()
    seq = 0
    prev_day = game_time(loop.state.tick).day
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
        if on_day_switch is not None:
            new_day = game_time(loop.state.tick).day
            if new_day != prev_day:
                for day in range(prev_day + 1, new_day + 1):
                    on_day_switch(day)
                prev_day = new_day
        if moved:
            seq += 1
            payload = delta_payload(loop, moved)
            payload["ws_seq"] = seq
            await manager.broadcast_json(payload)
        # K8：意愿独白帧（事件进流案的 WS 侧投影）。按 form 投递面路由；
        # 事件已随上面 on_flush 落库（真相先于投递，与 delta 同帧；广播在落库之后
        # 与主 delta 相反是有意的——独白是「已发生」的叙述，须事件先入日志）。
        for actor_id, frame in monologue_events_to_frames(events):
            seq += 1
            frame["ws_seq"] = seq
            await route_monologue(manager, actor_id, frame)
