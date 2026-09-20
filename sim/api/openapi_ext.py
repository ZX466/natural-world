"""OpenAPI 补全 — WS components 注入（kilo K03 差异回写，2026-09-20）。

FastAPI 只为 HTTP 路由生成 schema：WS 消息与设置页响应模型的缺口由
本模块补——custom_openapi 在自动 schema 之上追加 ws components。
口径与 shared/openapi.json（kilo 维护）一致：sim 是唯一真相源，
shared 由 tools/gen-protocol.ts 从本端点生成。
"""

from __future__ import annotations

from typing import Any

from fastapi.openapi.utils import get_openapi

from sim.api.main import app

#: 服务端 → 客户端 WS 消息（render/session 通道载荷形状，与 ws.py 实现一致）。
_WS_SERVER_MESSAGES: dict[str, dict[str, Any]] = {
    "WsFullSnapshot": {
        "type": "object",
        "required": ["type", "channel", "v", "ws_seq", "actors"],
        "properties": {
            "type": {"const": "full_snapshot"},
            "channel": {"const": "render"},
            "v": {"type": "string"},
            "ws_seq": {"type": "integer"},
            "actors": {
                "type": "array",
                "items": {
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
                },
            },
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
                "properties": {
                    "visual": {"type": "string"},
                    "ambient_light": {"type": "number"},
                },
            },
            "combat": {"type": ["object", "null"]},
        },
    },
    "WsStateDelta": {
        "type": "object",
        "required": ["type", "channel", "v", "ws_seq", "actors"],
        "properties": {
            "type": {"const": "state_delta"},
            "channel": {"const": "render"},
            "v": {"type": "string"},
            "ws_seq": {"type": "integer"},
            "actors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["rtoken", "x", "y"],
                    "properties": {
                        "rtoken": {"type": "string"},
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                    },
                },
            },
        },
    },
}

#: 客户端 → 服务端 WS 消息（_ALLOWED_CLIENT_TYPES 白名单，出戏边界硬校验）。
_WS_CLIENT_MESSAGES: dict[str, dict[str, Any]] = {
    "WsMoveRequest": {
        "type": "object",
        "required": ["type", "target_x", "target_y"],
        "properties": {
            "type": {"const": "move_request"},
            "target_x": {"type": "integer"},
            "target_y": {"type": "integer"},
        },
    },
    "WsSetControl": {
        "type": "object",
        "required": ["type"],
        "properties": {"type": {"const": "set_control"}, "controlled": {"type": "boolean"}},
    },
    "WsSyncRequest": {
        "type": "object",
        "required": ["type"],
        "properties": {"type": {"const": "sync_request"}},
    },
    "WsHello": {
        "type": "object",
        "required": ["type"],
        "properties": {"type": {"const": "hello"}},
    },
}


def custom_openapi() -> dict[str, Any]:
    """自动 schema + WS components。挂到 app.openapi。"""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description="临河镇 sim — WS 消息契约见 components.wsMessages",
        routes=app.routes,
    )
    schema.setdefault("components", {})["wsMessages"] = {
        "serverToClient": _WS_SERVER_MESSAGES,
        "clientToServer": _WS_CLIENT_MESSAGES,
    }
    app.openapi_schema = schema
    return schema


def install() -> None:
    """把 custom_openapi 装到 app（main.py lifespan 前调用一次）。"""
    app.openapi = custom_openapi
