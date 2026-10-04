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

M5-K3 批次 B（裁 21-A §A，本文件是主要施工面）：

- **D-2 fast_forward（新 action，不扩 speed 枚举）**：受理**静默**（`control_ack` 是
  「完成」信号不是「受理」信号，不得借 applied 占位撒谎），服务端按帧预算摊还
  推进，终态回**两帧** = `control_ack{action:fast_forward}` + **全量 `full_snapshot`**
  （D-7）。serverToClient **零新增消息**（D-4；`rate_change` 只登记预留名）。
- **D-3 暂停语义批（幂等单值，清 G-1~G-4）**：会话态落 `ControlState` **连接级**
  （挂在 `ConnectionManager`，清模块级 `_PRE_PAUSE_SPEED` 全局）；`pause` 幂等 /
  `resume` 无暂停回 `bad_action` / 暂停中 `set_speed` 只改记忆倍率。
- **D-5+D-6 session 首帧合并**：`session_state` 一帧承载连接期初值（刻度/暂停态/
  游标指针）与分叉告知（叙事化一行），**零原始数值**；读档成功 = 告知帧 + 全量两帧。
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any

import structlog
from fastapi import WebSocket

from sim.agent.impulse_gate import impulse_gate
from sim.api.outbound_guard import record_outbound_leak, strip_outbound_forbidden
from sim.core.calendar import TICKS_PER_GAME_HOUR, game_time
from sim.core.clock import MAX_CATCHUP_REAL_SECONDS
from sim.core.events import EventKind, WorldEvent
from sim.core.tick import TickLoop
from sim.llm.prompts.banned_words import scan
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder

logger = structlog.get_logger(__name__)

#: WS 信封 `v` 的**唯一真相源**（versioning.md §1：major.minor）。
#: 前端 `client/src/net/ws.ts` 的 `PROTOCOL_VERSION` 是第二落点，必须与本值逐字相等
#: ——历史上两处各写各的（sim 0.1 / client 0.1）漂移过一次，现由
#: `sim/tests/test_protocol_version.py` 的跨树钉锁死。**改一处必改另一处。**
#: 1.1 = M5 三个 minor 级变更（fast_forward / anchors current+SessionAnchor / GET /{id} /
#: PlanDelta 封闭），登记见 versioning.md §7。
_PROTOCOL_VERSION = "1.1"
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
# M5-K3（D-2）：fast_forward 参数面专用码。语义既非 speed 也非 action——
# 复用 bad_speed/bad_target 都会让前端的可重试判断失真。
_ERROR_BAD_ADVANCE = "bad_advance"

# ---------------------------------------------------------------------------
# M5-K3 控制面常量（裁 21-A D-2/D-3）
# ---------------------------------------------------------------------------

#: `set_control.speed` / `ControlAckMessage.speed` 的合法值（DESIGN §10 明文锁
#: {1,4,16}，与 `clock.ALLOWED_SPEEDS` 对齐）。**M5 不扩枚举**：快进走
#: `fast_forward` 新 action（长跨度推进语义），扩枚举会连带内核校验与前端三处改动。
ALLOWED_CONTROL_SPEEDS: tuple[int, ...] = (1, 4, 16)

#: 暂停时的隐含倍率（不进协议：schema 枚举无 0；`ControlAckMessage.speed` 省略该键）。
PAUSED_CLOCK_SPEED = 0.0

#: fast_forward 单次请求上限（游戏小时）。7 游戏日 = 604 800 tick，按 240 tick/帧
#: 摊还约 42 真实秒——超出请分次请求，避免一次请求长期占住世界推进。
FAST_FORWARD_MAX_HOURS = 168

#: fast_forward 单帧 tick 预算。与内核 `tick._MAX_TICKS_PER_FRAME`（240）同值——
#: 240 tick / 60 tick/s = 4.0 s = `clock.MAX_CATCHUP_REAL_SECONDS`，正好是内核
#: 单帧封顶而不被 clock 二次截断。**pi 的 perf 红线（thresholds 提案）落地后
#: 此处按提案调整**，本轮只保证「不破内核封顶」。
FAST_FORWARD_TICKS_PER_FRAME = 240

#: 未暂停时的默认倍率（`resume` 无记忆值时回落；G-1 防线之一）。
DEFAULT_CONTROL_SPEED = 1.0


@dataclass
class ControlState:
    """连接级控制会话态（M5-K3 / 裁 21-A D-3 幂等单值）。

    **不进 `GameClock`**（K6 §1.2）：clock 只表达「世界此刻跑多快」，本对象表达
    「这个连接按过什么键」。挂在 `ConnectionManager` 上（每连接一个）——旧实现是
    模块级 `_PRE_PAUSE_SPEED` 栈，多连接互窃倍率（K9 记的 G-4）。

    字段：
    - `paused`：暂停态独立表示（旧实现里暂停 ≡ `speed=0`，于是任何 `set_speed`
      都能单方面解除暂停——G-3）；
    - `speed_before_pause`：记忆倍率。`pause` 幂等不重压它，暂停中 `set_speed`
      只改它，恒为 `ALLOWED_CONTROL_SPEEDS` 之一（structurally 排除 G-1 的
      `speed:0` 越枚举）；
    - `pending_fast_forward`：在途快进的**剩余 tick**；`None`=无在途。
    """

    paused: bool = False
    speed_before_pause: float = DEFAULT_CONTROL_SPEED
    pending_fast_forward: int | None = None

    def effective_speed(self) -> int:
        """给协议面用的刻度读数：未暂停=当前倍率，暂停=恢复后倍率（枚举无 0）。"""
        speed = self.speed_before_pause if self.paused else self.current_clock_speed()
        return int(speed) if int(speed) in ALLOWED_CONTROL_SPEEDS else int(
            DEFAULT_CONTROL_SPEED
        )

    def current_clock_speed(self) -> float:
        """记忆值缺省时给 1.0（连接刚建、还没按过键）。"""
        return (
            self.speed_before_pause
            if self.speed_before_pause in (float(s) for s in ALLOWED_CONTROL_SPEEDS)
            else DEFAULT_CONTROL_SPEED
        )

    def request_fast_forward(self, ticks: int) -> None:
        """登记在途快进（D-2：受理静默，完成才回帧）。"""
        self.pending_fast_forward = int(ticks)

    def cancel_fast_forward(self) -> None:
        """取消在途快进（pause 语义：世界停了，跳转就停；不再回完成帧）。"""
        self.pending_fast_forward = None

    def consume_fast_forward(self, advanced: int) -> None:
        """扣减已推进 tick；归零即完成（保留 0 而非 None，供驱动侧判「本帧完成」）。"""
        if self.pending_fast_forward is None:
            return
        self.pending_fast_forward = max(0, self.pending_fast_forward - max(0, advanced))

    @property
    def fast_forward_done(self) -> bool:
        return self.pending_fast_forward == 0

    def reset(self) -> None:
        self.paused = False
        self.speed_before_pause = DEFAULT_CONTROL_SPEED
        self.pending_fast_forward = None


#: 兼容未传 `control` 的直接调用（测试与旧调用点）。**生产 `ws_endpoint` 必传每连接
#: `ControlState`**（K6 §8.5 铁律「签名三参不变」由「第四参可选」满足）。
_LEGACY_CONTROL = ControlState()


def reset_legacy_control() -> None:
    """测试辅助：重置兼容用兜底控制态（每用例隔离，防跨用例污染）。"""
    _LEGACY_CONTROL.reset()

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
        #: 每连接控制会话态（M5-K3 / D-3 G-4：连接级，连接断开即丢）。
        self._controls: dict[WebSocket, ControlState] = {}

    def register(
        self, ws: WebSocket, subscriber_id: str | None = None, control: ControlState | None = None
    ) -> None:
        """登记连接；subscriber_id 非空=绑定该实体视角（本人面板），空=旁观者。

        control 省略时自动建一个（每连接独立，D-3 幂等单值的状态载体）。
        """
        self._connections.append(ws)
        if subscriber_id is not None:
            self._subscribers[ws] = subscriber_id
        self._controls[ws] = control if control is not None else ControlState()

    def unregister(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        self._subscribers.pop(ws, None)
        # 控制态随连接丢弃（断线重连=新连接新状态；暂停不跨连接延续）
        self._controls.pop(ws, None)

    @property
    def count(self) -> int:
        return len(self._connections)

    def subscriber_of(self, ws: WebSocket) -> str | None:
        """该连接绑定的实体视角 id；None=旁观者。"""
        return self._subscribers.get(ws)

    def control_of(self, ws: WebSocket) -> ControlState:
        """该连接的控制会话态（未登记连接回兜底态，避免调用方 None 判断）。"""
        return self._controls.get(ws, _LEGACY_CONTROL)

    def controls(self) -> list[ControlState]:
        """全部在册连接的控制态（驱动侧快进摊还遍历用）。"""
        return list(self._controls.values())

    def fast_forward_completions(self) -> list[tuple[WebSocket, ControlState]]:
        """本帧刚完成快进的连接（`pending == 0`）——驱动侧定向回完成帧用。"""
        return [(ws, c) for ws, c in self._controls.items() if c.fast_forward_done]

    def any_fast_forward_active(self) -> bool:
        return any(c.pending_fast_forward is not None for c in self._controls.values())

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        await self._send_to(self._connections, payload)

    async def send_json_to(self, ws: WebSocket, payload: dict[str, Any]) -> None:
        """单连接投递（快进完成帧/首帧这类定向出站）。"""
        await self._send_to([ws], payload)

    async def send_to_subscriber(self, entity_id: str, payload: dict[str, Any]) -> None:
        """定向投递：只发给绑定该实体视角的连接（独白 thought 面板用）。"""
        targets = [ws for ws in self._connections if self._subscribers.get(ws) == entity_id]
        await self._send_to(targets, payload)

    async def _send_to(self, targets: list[WebSocket], payload: dict[str, Any]) -> None:
        # M5-K11（D-10 权力不可见）+ M5-K15（S11 F-1 随机流补扫）：**全部** WS 出站帧的
        # 唯一咽喉——广播/定向/订阅者三面都走这里，故闸接在此处即全覆盖。两层禁键
        # （权力 9 键 + 随机流状态键）**同一递归**剥除并留痕：出站面出现禁键本身就是缺陷，
        # 剥除只是止血（m5-power-api.md §3.1 / S11 F-1）。
        payload, stripped = strip_outbound_forbidden(payload)
        if stripped:
            record_outbound_leak(stripped)
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
    raw: dict[str, Any], loop: TickLoop, pf: Pathfinder, control: ControlState | None = None
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """不可信输入处理：type 白名单 + channel 校验。返回要回给该客户端的帧（或帧列表/None）。

    分发块：move_request / hello / sync_request / set_control / player_impulse / load_anchor
    （各 _handle_* 是纯函数，可单测；契约见 docs/api/ws-dispatch-proposal.md §1-§3）。

    **M5-K3 增补两点**（K4 §0.1「单回复通道」的窄化）：
    1. `control` 第四参可选——D-3 的会话态是**连接级**（G-4），生产 `ws_endpoint`
       传 `manager.control_of(ws)`；省略时回落模块级兜底态（兼容旧调用点）。
    2. 返回值放宽为 `dict | list[dict] | None`——**仅读档成功**返回两帧
       （分叉告知 + 全量快照）。其余分发块仍返回单帧/None。
    """
    msg_type = raw.get("type")
    if msg_type not in _ALLOWED_CLIENT_TYPES:
        logger.warning("ws.rejected_type", msg_type=str(msg_type))
        return _error_frame(str(msg_type), _ERROR_UNKNOWN_TYPE, "unsupported message type")
    if raw.get("channel") != _CHANNEL_FOR.get(msg_type):
        return _error_frame(str(msg_type), _ERROR_BAD_CHANNEL, "channel mismatch")

    ctrl = control if control is not None else _LEGACY_CONTROL
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
        return _handle_set_control(raw, loop, ctrl)
    if msg_type == "player_impulse":
        return _handle_player_impulse(raw)
    if msg_type == "load_anchor":
        return _handle_load_anchor(raw, loop, pf, ctrl)
    return None


def frames_of(reply: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """分发块返回值 → 帧列表（K4 §0.1 单回复通道的增补摊平器）。

    网关侧：`for frame in frames_of(reply): await ws.send_json(frame)`。
    """
    if reply is None:
        return []
    if isinstance(reply, list):
        return list(reply)
    return [reply]


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


def _handle_set_control(
    raw: dict[str, Any], loop: TickLoop, control: ControlState
) -> dict[str, Any] | None:
    """K4 提案 §1 + M5-K3 批次 B：set_control 分发块（D-2 快进 / D-3 幂等单值）。

    D-3（裁 21-A，替 K6 §1.2 的栈方案）——**幂等单值**：
    - `pause` 幂等：已暂停再按不重压记忆倍率（旧栈把 0.0 压进去，`resume` 时
      `int(restored)==0` 实发出 `control_ack{speed:0}`，**破 `ControlAckMessage`
      枚举 [1,4,16]** = G-1；本实现从结构上排除该路径）；
    - `resume` 无暂停 → `bad_action` 错误帧（G-2：旧实现静默把倍率改回 1x 且回
      `applied:true`，是未声明的状态变更）；
    - 暂停中 `set_speed` **只改记忆倍率**、不解除暂停（G-3：旧实现暂停 ≡ speed=0，
      于是任何 `set_speed` 都能单方面解除暂停）；同时 `pause` 取消在途快进。

    D-2（快进）——`fast_forward{advance_hours}`：长跨度推进批处理，**受理静默**
    （返回 None）；完成由驱动侧回 `control_ack{action:fast_forward}` + 全量快照。
    """
    action = raw.get("action")
    if action == "set_speed":
        speed = raw.get("speed")
        # bool 是 int 子类 → isinstance(True, int) 为真，必须显式排除
        if (
            not isinstance(speed, int)
            or isinstance(speed, bool)
            or speed not in ALLOWED_CONTROL_SPEEDS
        ):
            return _error_frame("set_control", _ERROR_BAD_SPEED, "快不了那么慢，也快不了那么快。")
        if control.paused:
            # 暂停中变速只改记忆值（不解除暂停）；ack 带 paused 让前端不必推断
            control.speed_before_pause = float(speed)
            return _control_ack("set_speed", speed=speed, paused=True)
        loop.clock.set_speed(float(speed))
        return _control_ack("set_speed", speed=speed, paused=False)
    if action == "pause":
        if not control.paused:
            control.speed_before_pause = _rememberable_speed(loop)
            loop.clock.set_speed(PAUSED_CLOCK_SPEED)
            control.paused = True
        control.cancel_fast_forward()  # 世界要停 → 在途跳转随之取消
        return _control_ack("pause", paused=True)
    if action == "resume":
        if not control.paused:
            return _error_frame("set_control", _ERROR_BAD_ACTION, "本来就没停。")
        restored = control.speed_before_pause
        loop.clock.set_speed(restored)
        control.paused = False
        return _control_ack("resume", speed=int(restored), paused=False)
    if action == "fast_forward":
        hours = raw.get("advance_hours")
        if (
            not isinstance(hours, int)
            or isinstance(hours, bool)
            or not 1 <= hours <= FAST_FORWARD_MAX_HOURS
        ):
            return _error_frame("set_control", _ERROR_BAD_ADVANCE, "一下子走不了那么远。")
        if control.paused:
            return _error_frame("set_control", _ERROR_BAD_ADVANCE, "停着呢，走不了。")
        if control.pending_fast_forward is not None:
            return _error_frame("set_control", _ERROR_BAD_ADVANCE, "日子已经在往前走了。")
        control.request_fast_forward(hours * TICKS_PER_GAME_HOUR)
        return None  # 受理静默：ack 是完成信号，不撒谎 applied
    return _error_frame("set_control", _ERROR_BAD_ACTION, "不知道要怎么调。")


def _rememberable_speed(loop: TickLoop) -> float:
    """把当前倍率折成「可记忆值」（协议枚举内）。

    G-1 的第二道防线：即便 `clock.speed` 被绕过控制面写坏（0.0/NaN/任意浮点），
    记忆值也只可能是 {1,4,16} 之一 ⇒ `control_ack.speed` 结构上永不越枚举。
    """
    current = loop.clock.speed
    return float(current) if current in (float(s) for s in ALLOWED_CONTROL_SPEEDS) else (
        DEFAULT_CONTROL_SPEED
    )


def _control_ack(
    action: str, speed: int | None = None, paused: bool | None = None
) -> dict[str, Any]:
    """ControlAckMessage 构造。

    §1.2：`pause` 的 ack 不带 speed——schema enum 无 0。D-3 新增可选 `paused`：
    省略 = 未表达（老客户端兼容）；给出则前端可直接渲染暂停态而不必推断。
    """
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
    if paused is not None:
        ack["paused"] = paused
    return ack


def step_fast_forward(
    loop: TickLoop, requests: list[ControlState], budget: int = FAST_FORWARD_TICKS_PER_FRAME
) -> int:
    """把本帧 tick 预算在**在途快进**请求间摊还。返回本帧实际推进 tick 数。

    D-2 批处理语义：不阻塞事件循环（长跨度推进若在分发块里同步跑完会把 WS
    握手/广播一起卡住），改为「每帧推一点」。约束：
    - 跨连接**共享**同一预算（世界只有一份，多人同抢会互相把帧预算吃穿）；
    - 合成 `real_dt` 经 `clock.advance` 换算，受内核 `MAX_CATCHUP_REAL_SECONDS`
      与 `tick._MAX_TICKS_PER_FRAME` 双封顶 ⇒ 恒 ≤ budget；
    - 世界停（clock.speed=0）时本帧不推进（rate<=0 分支），不空转；
    - 快进期间的推进**照常产出事件**，由同帧 drain 落库（不进旁路）。
    """
    active = [c for c in requests if c.pending_fast_forward]
    if not active:
        return 0
    rate = loop.clock.ticks_per_real_second()
    if rate <= 0:
        return 0
    advanced_total = 0
    for control in active:
        remaining = budget - advanced_total
        if remaining <= 0:
            break
        want = min(int(control.pending_fast_forward or 0), remaining)
        if want <= 0:
            continue
        dt = min(want / rate, MAX_CATCHUP_REAL_SECONDS)
        advanced = loop.advance_frame(dt)
        control.consume_fast_forward(advanced)
        advanced_total += advanced
    return advanced_total


def fast_forward_done_frames(
    loop: TickLoop, tile_map: TileMap, control: ControlState
) -> list[dict[str, Any]]:
    """快进完成的出站两帧：终态 ack + **全量**重同步（D-7）。

    serverToClient 零新增消息（D-4）⇒ 完成信号复用 `control_ack`；因跨越了
    长时间跨度，重同步走全量而非增量（rtoken ≠ 跨分支/跨跨度连续性，见
    ws-protocol §5 rtoken 规则）。前端在等待期显示「片刻后……」叙事化过渡
    （与读档同一措辞口径）。
    """
    return [
        _control_ack(
            "fast_forward", speed=control.effective_speed(), paused=control.paused
        ),
        snapshot_payload(loop, tile_map),
    ]


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
    # M4-A2（裁 19-F2）：入站三扫接线（I-1 banned / I-3 操纵感；I-2 hidden 的
    # target_profile 随批次 A 感知层接线注入——玩家念头是全局注入，当前无特定
    # 目标 NPC 可查）。拒收 → injected:false + 结构化 error 码（不新增戏外词面），
    # observation 标签只进 dev 日志（S3 行为表 §6）。
    verdict = impulse_gate(text)
    if not verdict.admitted:
        code = {
            "too_many_hits": _ERROR_IMPULSE_TOO_LONG,
        }.get(verdict.reason or "", _ERROR_BAD_IMPULSE)
        logger.warning(
            "ws.impulse_rejected",
            reason=verdict.reason,
            observation=verdict.observation or "",
        )
        return _error_frame("player_impulse", code, "这个念头进不去。")
    cleaned = verdict.content
    return {
        "type": "impulse_feedback",
        "channel": "control",
        "v": _PROTOCOL_VERSION,
        "ws_seq": 0,
        "injected": True,  # §2.5：已接受并投递（不保证 LLM 已处理——异步）
        "cue": _impulse_cue(cleaned),
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
#: anchor 叙事标签（M5-K3 / D-5+D-6 供数）：id → {name, story_label}。
#: 落库路径（`sim/api/anchors.py::_item_payload`）在注册 id 的同时登记标签，
#: 于是 `load_anchor` 分发块能**纯内存**组出分叉告知帧，无需在 handler 里查库。
_ANCHOR_LABELS: dict[str, dict[str, str]] = {}
#: 载入钩子（同步布尔契约）。默认 None → 只查 _ANCHOR_IDS 存在性。
#: ws_endpoint 装配时挂真实「定位→快照→重放」入口（§3.4 长期 driver 路径）。
_ANCHOR_LOAD_HOOK: Any = None


def set_anchor_load_hook(hook: Any) -> None:
    """注册生产载入钩子（main.py lifespan 装配；读档=分叉编排缝）。

    hook 契约（同步布尔）：`(anchor_id: str) -> bool`——True=已分叉换线；
    抛异常=执行失败（handler 降级 load_failed）。None 卸载。
    """
    global _ANCHOR_LOAD_HOOK
    _ANCHOR_LOAD_HOOK = hook


def reset_anchor_registry() -> None:
    """测试辅助：清空 anchor id 集/标签表与载入钩子。"""
    _ANCHOR_IDS.clear()
    _ANCHOR_LABELS.clear()
    global _ANCHOR_LOAD_HOOK
    _ANCHOR_LOAD_HOOK = None


def register_anchor_id(anchor_id: str, name: str = "", story_label: str = "") -> None:
    """登记已知 anchor id + 叙事标签（后台 HTTP/落库路径调用）。

    两个用途：①`load_anchor` 的存在性判定（WS 分发块同步查表集）；②D-6 分叉告知
    帧的游标指针（零原始数值：只有 name + story_label）。name/story_label 省略时
    退化为空串——旧注册点（只给 id）仍可用，只是告知文案不带档名。

    **必须成对**：删档路径调 `unregister_anchor_id`（M5-K6 / 裁 27-C D-15 / 28-C S-7）
    ——本表是**只增不减**的进程内缓存，不摘除就会让已删档在 WS 侧继续「存在」。
    """

    _ANCHOR_IDS.add(anchor_id)
    _ANCHOR_LABELS[anchor_id] = {"name": name, "story_label": story_label}


def unregister_anchor_id(anchor_id: str) -> None:
    """从同步查表集与标签表**摘除**一个 anchor id（`register_anchor_id` 的成对面）。

    用途（M5-K6 / 裁 27-C D-15 采）：`DELETE /api/anchors/{id}` 成功后由调用方
    （CRUD 单，Claude 域施工）调用，否则已删档在 WS 侧仍然「存在」——
    `load_anchor` 查表命中会回**假成功**（无 hook 时甚至直接给一份全量快照）。

    摘除后的错误映射（K5 C-3 口径，**不新增 error code**）：`load_anchor` 查表未命中
    → `load_failed`（「存在过但已删」归载入失败成立；`bad_anchor` 的语义是「形状
    非法/缺失」）。分叉告知帧的游标指针同步退化为 `anchor=null`。

    幂等：未注册的 id 摘除是 no-op（`discard`/`pop(None)` 语义）。
    """
    _ANCHOR_IDS.discard(anchor_id)
    _ANCHOR_LABELS.pop(anchor_id, None)


def anchor_pointer(anchor_id: str) -> dict[str, str] | None:
    """已登记 anchor 的游标指针（`{name, story_label}`）；未登记回 None。"""
    return _ANCHOR_LABELS.get(anchor_id)


def _handle_load_anchor(
    raw: dict[str, Any], loop: TickLoop, pf: Pathfinder, control: ControlState | None = None
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """K4 提案 §3：注册 + 失败不断线 + 成功回 full_snapshot（M5-K3 增补告知帧）。

    anchor_id 是**不透明串**（§6.5：禁 anc_ 之类前缀特征校验）——非法只回 bad_anchor，
    形状不被特征拒绝。载入执行失败（重放损坏等）降级为 load_failed，绝不炸断 handler。

    **M5-K3（D-6）**：成功路径返回**两帧**——`session_state`（分叉告知：一行叙事化
    文本 + 游标指针；branch_id/seq/tick 一律不出网关）与随后的全量 `full_snapshot`。
    失败路径仍是单帧 error（§3.3 连接不断）。
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
        return _load_failed_frame()
    if not ok:
        return _load_failed_frame()
    # 短期同步路径（§3.4）：复用 snapshot_payload；长期 driver 化后本分支由广播接替。
    pointer = anchor_pointer(anchor_id)
    ctrl = control if control is not None else _LEGACY_CONTROL
    notice_frame = session_state_payload(
        speed=ctrl.effective_speed(),
        paused=ctrl.paused,
        anchor=pointer,
        notice=fork_notice(pointer.get("name", "") if pointer else ""),
    )
    return [notice_frame, snapshot_payload(loop, pf.tile_map)]


def _load_failed_frame() -> dict[str, Any]:
    """构造物化失败的玩家帧，并在最终文案边界执行案 A 终扫。"""
    message = "这个档读不出来了。"
    if not scan(message).hits:
        return _error_frame("load_anchor", _ERROR_LOAD_FAILED, message)

    logger.warning("ws.anchor_load_message_degraded", reason="banned_message_outbound")
    for fallback in ("档打不开。", "读不了。", "打不开。"):
        if not scan(fallback).hits:
            return _error_frame("load_anchor", _ERROR_LOAD_FAILED, fallback)

    logger.error("ws.anchor_load_message_fallback_invalid")
    return _error_frame("load_anchor", _ERROR_LOAD_FAILED, "")


def session_state_payload(
    speed: int,
    paused: bool,
    anchor: dict[str, str] | None = None,
    notice: str | None = None,
) -> dict[str, Any]:
    """`session_state` 帧构造（M5-K3 / 裁 21-A D-5+D-6 **一帧承载**）。

    连接期初值（刻度 / 暂停态 / 游标指针）与分叉告知（叙事化一行）合成一帧——
    避免两次新增消息（旧 client 静默忽略未知 type，versioning §3 铁律）。

    **零原始数值**：`speed` 只在 {1,4,16}（暂停时=恢复后倍率，不是 0）；`anchor`
    只带 `name` + `story_label`；`notice` 是戏内口语行。tick/seq/branch_id/
    entity_id 零出现（ws-protocol §5）。
    """
    return {
        "type": "session_state",
        "channel": "session",
        "v": _PROTOCOL_VERSION,
        "ws_seq": 0,
        "speed": int(speed),
        "paused": bool(paused),
        "anchor": ({"name": anchor.get("name", ""), "story_label": anchor.get("story_label", "")})
        if anchor
        else None,
        "notice": notice,
    }


def fork_notice(anchor_name: str) -> str:
    """分叉告知文案（戏外口语行；不含量词数值、不出现分支/快照等系统词）。

    F-6 出站纵深（m5-fork-evidence-preplan.md §4.2 表态 2c）：注册侧（POST/PATCH）
    已 fail-closed 拦禁词档名，此处对**存量行**终扫兜底——命中禁词 → 退化为
    无档名兜底行，**不静默放行**（不扩词表，消费现行 scan()）。
    """
    if anchor_name and scan(f"你回到了「{anchor_name}」那段日子").hits:
        logger.warning("ws.fork_notice_degraded", reason="banned_name_outbound")
        return "你回到了先前的那段日子"
    return f"你回到了「{anchor_name}」那段日子" if anchor_name else "你回到了先前的那段日子"


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

    **M5-K3 批次 B（D-2 快进）**：有在途 `fast_forward` 时，本帧额外按
    `FAST_FORWARD_TICKS_PER_FRAME` 预算摊还推进（跨连接共享预算），并**抑制逐帧
    `state_delta` 广播**——长跨度跳转期间逐帧增量会让前端插值错乱；客户端显示
    「片刻后……」叙事化过渡（同读档口径），完成时定向回两帧（ack + 全量快照）。
    快进产生的**事件照常同帧落库**，不走旁路（世界真相不因呈现方式打折）。
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
        fast_forwarding = manager.any_fast_forward_active()
        if n == 0 and manager.count == 0:
            continue
        if fast_forwarding:
            step_fast_forward(loop, manager.controls())
        moved = set() if fast_forwarding else loop.drain_delta()
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
        # M5-K3：快进完成 → 定向回「终态 ack + 全量重同步」（D-7 一律全量）
        for ws, control in manager.fast_forward_completions():
            for frame in fast_forward_done_frames(loop, tile_map, control):
                seq += 1
                frame["ws_seq"] = seq
                await manager.send_json_to(ws, frame)
