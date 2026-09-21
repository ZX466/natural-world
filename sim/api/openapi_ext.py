"""OpenAPI 补全 — WS components 注入（kilo K03 差异回写 + M2-K1 改写，2026-09-21）。

FastAPI 只为 HTTP 路由生成 schema：WS 消息与设置页响应模型的缺口由
本模块补——custom_openapi 在自动 schema 之上追加 WS 消息 schemas。

**M2-K1 改写（kilo 发现 1/2/4 采纳）**：`components.wsMessages` 是
openapi-typescript **不读**的私有扩展（只读 `components.schemas`）——改为把
14 成员联合（`WsMessage` = oneOf + discriminator.type）直接写进
`components.schemas`，与 shared/openapi.json（kilo 维护的协议快照）同构。
`--src <sim>/openapi.json` 从此可全量生成（消除 sim↔前端漂移的前置）。

形状对齐：ws.py 实发（channel 字段在每成员上、error 无 ref——发现 5）；
hello/hello_ack（W6 鉴权握手）**故意不进联合**（安全域裁决，勿补齐）。
"""

from __future__ import annotations

from typing import Any

from fastapi.openapi.utils import get_openapi

from sim.api.main import app


#: 通用信封字段（每成员都带；ws_seq=传输序号非世界 tick）。
def _envelope(
    channel: str, msg_type: str, extra_props: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["v", "ws_seq", "channel", "type", *required],
        "properties": {
            "v": {"type": "string", "description": "协商后的协议版本 major.minor"},
            "ws_seq": {"type": "integer", "minimum": 0},
            "channel": {"type": "string", "enum": [channel]},
            "type": {"type": "string", "enum": [msg_type]},
            **extra_props,
        },
        "additionalProperties": False,
    }


_ACTOR = {
    "type": "object",
    "required": ["rtoken", "x", "y"],
    "properties": {
        "rtoken": {"type": "string", "description": "rt- 前缀不透明替身"},
        "x": {"type": "integer"},
        "y": {"type": "integer"},
        "facing": {"type": "string"},
        "sprite": {"type": "string"},
        "anim": {"type": "string"},
    },
    "additionalProperties": False,
}

_WS_SCHEMAS: dict[str, dict[str, Any]] = {
    # ── client → sim（_ALLOWED_CLIENT_TYPES 白名单，出戏边界硬校验）──
    "PlayerImpulseMessage": _envelope(
        "control",
        "player_impulse",
        {
            "text": {
                "type": "string",
                "maxLength": 64,
                "description": "玩家原始直觉输入；sim 负责叙事化",
            },
            "preset": {"type": "string", "nullable": True},
        },
        ["text"],
    ),
    "SetControlMessage": _envelope(
        "control",
        "set_control",
        {
            "action": {"type": "string", "enum": ["pause", "resume", "set_speed"]},
            "speed": {"type": "integer", "enum": [1, 4, 16]},
        },
        ["action"],
    ),
    "LoadAnchorMessage": _envelope(
        "session", "load_anchor", {"anchor_id": {"type": "string"}}, ["anchor_id"]
    ),
    "MoveRequestMessage": _envelope(
        "control",
        "move_request",
        {
            "target_x": {
                "type": "integer",
                "description": "目标格坐标；sim 寻路并驱动主角（无 rtoken）",
            },
            "target_y": {"type": "integer"},
        },
        ["target_x", "target_y"],
    ),
    "SyncRequestMessage": _envelope("session", "sync_request", {}, []),
    # ── sim → client ──
    "FullSnapshotMessage": _envelope(
        "render",
        "full_snapshot",
        {
            "actors": {"type": "array", "items": _ACTOR},
            "lights": {"type": "array", "items": {"type": "object"}},
            "structures": {"type": "array", "items": {"type": "object"}},
            "map": {
                "type": "object",
                "properties": {
                    "w": {"type": "integer"},
                    "h": {"type": "integer"},
                    "tileset": {"type": "string"},
                },
            },
            "weather": {
                "type": "object",
                "properties": {"visual": {"type": "string"}, "ambient_light": {"type": "number"}},
            },
            "combat": {"type": ["object", "null"]},
        },
        ["actors", "lights", "structures", "map", "weather", "combat"],
    ),
    "StateDeltaMessage": _envelope(
        "render",
        "state_delta",
        {"actors": {"type": "array", "items": _ACTOR}},
        ["actors"],
    ),
    "PerceptionMessage": _envelope(
        "narrative",
        "perception",
        {
            "sense": {
                "type": "string",
                "enum": ["sight", "sound", "smell", "touch", "interoception"],
            },
            "content": {
                "type": "string",
                "description": "第一人称戏内文本；无数值无系统词（出戏边界）",
            },
            "subject": {"type": "string", "nullable": True},
        },
        ["sense", "content"],
    ),
    "MonologueMessage": _envelope(
        "narrative",
        "monologue",
        {
            "content": {"type": "string"},
            "reaction": {
                "type": "object",
                "nullable": True,
                "properties": {
                    "form": {"type": "string", "enum": ["bubble", "thought", "plan"]},
                    "content": {"type": "string"},
                },
            },
        },
        ["content"],
    ),
    "ImpulseFeedbackMessage": _envelope(
        "narrative",
        "impulse_feedback",
        {
            "accepted": {"type": "boolean"},
            "content": {"type": "string", "description": "sim 的戏内回应（叙事化，非系统措辞）"},
        },
        ["accepted", "content"],
    ),
    "CombatEventMessage": _envelope(
        "render",
        "combat_event",
        {
            "kind": {"type": "string"},
            "attacker": {"type": "string", "nullable": True},
            "defender": {"type": "string", "nullable": True},
        },
        ["kind"],
    ),
    "TimescaleMessage": _envelope("render", "timescale", {"rate": {"type": "number"}}, ["rate"]),
    "ControlAckMessage": _envelope(
        "session",
        "control_ack",
        {"ack_of": {"type": "string"}, "ok": {"type": "boolean"}},
        ["ack_of", "ok"],
    ),
    # error：sim 实发无 ref（kilo 发现 5 对齐）；快照侧 required 亦按此修正
    "WsErrorMessage": _envelope(
        "error",
        "error",
        {
            "code": {"type": "string"},
            "message": {"type": "string", "description": "戏内文风，不向玩家显示系统措辞"},
        },
        ["code", "message"],
    ),
}

#: type 判别值（与各成员 enum 严格一致——手写表，测试锁死）。
_TYPE_OF: dict[str, str] = {
    "PlayerImpulseMessage": "player_impulse",
    "SetControlMessage": "set_control",
    "LoadAnchorMessage": "load_anchor",
    "MoveRequestMessage": "move_request",
    "SyncRequestMessage": "sync_request",
    "FullSnapshotMessage": "full_snapshot",
    "StateDeltaMessage": "state_delta",
    "PerceptionMessage": "perception",
    "MonologueMessage": "monologue",
    "ImpulseFeedbackMessage": "impulse_feedback",
    "CombatEventMessage": "combat_event",
    "TimescaleMessage": "timescale",
    "ControlAckMessage": "control_ack",
    "WsErrorMessage": "error",
}

#: 判别联合（oneOf + discriminator.type；与 shared/openapi.json 的 WsMessage 同构）。
_WS_UNION: dict[str, Any] = {
    "oneOf": [{"$ref": f"#/components/schemas/{name}"} for name in _WS_SCHEMAS],
    "discriminator": {
        "propertyName": "type",
        "mapping": {_TYPE_OF[name]: f"#/components/schemas/{name}" for name in _WS_SCHEMAS},
    },
}


def custom_openapi() -> dict[str, Any]:
    """自动 schema + WS 消息 schemas（components.schemas.WsMessage 联合）。挂到 app.openapi。"""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description="临河镇 sim — WS 消息契约见 components.schemas.WsMessage（oneOf 联合）",
        routes=app.routes,
    )
    components = schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    schemas.update(_WS_SCHEMAS)
    schemas["WsMessage"] = _WS_UNION
    app.openapi_schema = schema
    return schema


def install() -> None:
    """把 custom_openapi 装到 app（main.py lifespan 前调用一次）。"""
    app.openapi = custom_openapi
