"""OpenAPI 补全 — WS components 注入（M2-A2 第四项按 K3 清单返工，2026-09-22）。

FastAPI 只为 HTTP 路由生成 schema：WS 消息与设置页响应模型的缺口由
本模块补——custom_openapi 在自动 schema 之上追加 WS 消息 schemas。

**M2-K3 返工（docs/api/ws-message-diff.md 验收清单，真相源 shared/openapi.json）**：
- 14 个公共子 schema 以精确 dict 注入（Actor/ActorDelta/Light/LightDelta/
  Structure/StructureDelta/Weather/MapInfo/RToken/Facing/CombatInfo/
  Projectile/Hit/MonologueReaction）——它们是 WS 成员 $ref 化的落点；
- 12 个 WS 成员逐字段对齐快照（61 处字段级差异归零、4 处 channel 错值归零、
  信封 v 无 description、nullable 计数=0——一律 oneOf:[…,null] 形）；
- HealthStatus/WorldMapResponse/MapChunk 由 main.py 的 response_model 生成
  （本文件不重复定义，见 main.py 路由）。

形状对齐依据：ws.py 实发（ControlAck 三项=action/applied/speed、channel=control）；
hello/hello_ack（W6 鉴权握手）**故意不进联合**（安全域裁决，勿补齐）。
anchors 三 schema 与 ProblemDetail 由路由 response_model 生成（M5-CRUD 已施工，2026-09-30）；
responses.Problem 由 `_attach_problem_responses` 注入（§5.1 手抄清单）。

**M5-K10（裁 19 CRITICAL 修复，2026-09-27）**：新增 `PlanDelta` 第 15 个公共子
schema（`{rtoken→RToken, text}`，both required，`additionalProperties: False`）+
`StateDeltaMessage.plan`（`readonly PlanDelta[]`，**不进 required**）。K7 曾先于
schema 实发 `state_delta.plan`（K9 抓为 CRITICAL 缝：schema 无该键且信封全局
`additionalProperties:false`）。本处定义必须与 shared/openapi.json 快照**逐字段相等**
（钉子在 sim/tests/test_m5_plan_delta.py::TestPlanDeltaSchema）。
"""

from __future__ import annotations

from typing import Any

from fastapi.openapi.utils import get_openapi

from sim.api.main import app


#: 通用信封字段（每成员都带；ws_seq=传输序号非世界 tick）。
#: v 无 description（§1.7：快照 14 成员均无，删 ext 侧消 14 处 diff）。
def _envelope(
    channel: str, msg_type: str, extra_props: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["v", "ws_seq", "channel", "type", *required],
        "properties": {
            "v": {"type": "string"},
            "ws_seq": {"type": "integer", "minimum": 0},
            "channel": {"type": "string", "enum": [channel]},
            "type": {"type": "string", "enum": [msg_type]},
            **extra_props,
        },
        "additionalProperties": False,
    }


def _member(
    channel: str,
    msg_type: str,
    extra_props: dict[str, Any],
    required: list[str],
    *,
    description: str | None = None,
) -> dict[str, Any]:
    """_envelope + 可选成员级 description（快照 Monologue/ImpulseFeedback/MoveRequest 有）。"""
    member = _envelope(channel, msg_type, extra_props, required)
    if description is not None:
        member["description"] = description
    return member


#: 公共子 schema（K3 §2.1 #1-#14）——与 shared/openapi.json 逐字段一致。
_SUB_SCHEMAS: dict[str, dict[str, Any]] = {
    # 裁 21-A / M5-K2（D-8 口径订正，实现不动）：rtoken 是**稳定派生**
    # （ws.py::_rtoken = sha256(entity_id)[:12]），跨连接与跨分支都不变——
    # 早期描述写「连接生命周期内有效、重连由 full_snapshot 重分配」与实现相悖。
    # 现行口径三句见 docs/api/ws-protocol.md §5「rtoken 规则」。
    "RToken": {
        "type": "string",
        "description": "不透明渲染替身：仅用于精灵跟踪，与内部 entity_id 解耦、"
        "不可反查游戏状态；由 sim 稳定派生（同一实体恒得同一 rtoken，"
        "跨连接与跨分支均不变），rtoken 不等于身份标识、不等于跨分支连续性，"
        "重连与读档分叉后一律以 full_snapshot 全量重建前端状态"
        "（ws-protocol.md §5 / 裁 21-A）",
    },
    "Facing": {"type": "string", "enum": ["n", "e", "s", "w"]},
    "Actor": {
        "type": "object",
        "required": ["rtoken", "sprite", "x", "y", "facing", "anim"],
        "properties": {
            "rtoken": {"$ref": "#/components/schemas/RToken"},
            "sprite": {"type": "string"},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "facing": {"$ref": "#/components/schemas/Facing"},
            "anim": {"type": "string"},
            "tint": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    "ActorDelta": {
        "type": "object",
        "required": ["rtoken"],
        "properties": {
            "op": {"type": "string", "enum": ["add", "remove"]},
            "rtoken": {"$ref": "#/components/schemas/RToken"},
            "sprite": {"type": "string"},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "facing": {"$ref": "#/components/schemas/Facing"},
            "anim": {"type": "string"},
            "tint": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    "Light": {
        "type": "object",
        "required": ["rtoken", "x", "y", "kind", "radius", "flicker"],
        "properties": {
            "rtoken": {"$ref": "#/components/schemas/RToken"},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "kind": {"type": "string"},
            "radius": {"type": "number"},
            "flicker": {"type": "number"},
        },
        "additionalProperties": False,
    },
    "LightDelta": {
        "type": "object",
        "required": ["rtoken"],
        "properties": {
            "rtoken": {"$ref": "#/components/schemas/RToken"},
            "flicker": {"type": "number"},
        },
        "additionalProperties": False,
    },
    "Structure": {
        "type": "object",
        "required": ["rtoken", "tileset_ref", "x", "y", "phase"],
        "properties": {
            "rtoken": {"$ref": "#/components/schemas/RToken"},
            "tileset_ref": {"type": "string"},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "phase": {"type": "string", "enum": ["built", "collapsing", "rubble"]},
        },
        "additionalProperties": False,
    },
    "StructureDelta": {
        "type": "object",
        "required": ["rtoken"],
        "properties": {
            "op": {"type": "string", "enum": ["add", "remove"]},
            "rtoken": {"$ref": "#/components/schemas/RToken"},
            "tileset_ref": {"type": "string"},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "phase": {"type": "string", "enum": ["built", "collapsing", "rubble"]},
        },
        "additionalProperties": False,
    },
    "Weather": {
        "type": "object",
        "required": ["visual", "ambient_light"],
        "properties": {
            "visual": {"type": "string"},
            "ambient_light": {"type": "number"},
        },
        "additionalProperties": False,
    },
    "MapInfo": {
        "type": "object",
        "required": ["tileset", "w", "h"],
        "properties": {
            "tileset": {"type": "string"},
            "w": {"type": "integer", "minimum": 0},
            "h": {"type": "integer", "minimum": 0},
        },
        "additionalProperties": False,
    },
    # M5-K10（裁 19 CRITICAL 修复）：K7 state_delta.plan 顶层数组的**项** schema。
    # 形状从 ws.py::delta_payload 现发数据对拍（逐字段相等，防「实现先跑 schema
    # 后补」再次打架）：{"rtoken": _rtoken(entity_id), "text": plan_text}。
    # `text` 可空串（前端收起看板 = 明确无计划）；账本空时 state_delta **不发
    # plan 键**（可选字段不制造噪声），故项内无 "有无计划" 标志位。
    "PlanDelta": {
        "type": "object",
        "required": ["rtoken", "text"],
        "properties": {
            "rtoken": {"$ref": "#/components/schemas/RToken"},
            "text": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "CombatInfo": {
        "type": "object",
        "required": ["active"],
        "properties": {"active": {"type": "boolean"}},
        "additionalProperties": False,
    },
    "Projectile": {
        "type": "object",
        "required": ["rtoken", "kind", "x0", "y0", "x1", "y1", "dur"],
        "properties": {
            "rtoken": {"$ref": "#/components/schemas/RToken"},
            "kind": {"type": "string"},
            "x0": {"type": "integer"},
            "y0": {"type": "integer"},
            "x1": {"type": "integer"},
            "y1": {"type": "integer"},
            "dur": {"type": "number"},
        },
        "additionalProperties": False,
    },
    "Hit": {
        "type": "object",
        "required": ["rtoken", "visual", "bleed"],
        "properties": {
            "rtoken": {"$ref": "#/components/schemas/RToken"},
            "visual": {"type": "string"},
            "bleed": {"type": "string", "enum": ["none", "light", "heavy"]},
        },
        "additionalProperties": False,
    },
    "MonologueReaction": {
        "type": "object",
        "required": ["form", "content"],
        "properties": {
            "form": {"type": "string", "enum": ["bubble", "thought", "plan"]},
            "content": {"type": "string"},
        },
        "additionalProperties": False,
    },
    # M5-K3：玩家档游标指针（零原始数值——禁 tick/seq/branch_id/agent_override）。
    # 与 `AnchorListItem`（戏外 HTTP 面）同构但更窄：WS 侧只需叙事化标签两项。
    "SessionAnchor": {
        "type": "object",
        "required": ["name", "story_label"],
        "properties": {
            "name": {"type": "string", "description": "档名（玩家自取）"},
            "story_label": {
                "type": "string",
                "description": "叙事化时间标签（非 tick 数值；未就绪时空串）",
            },
        },
        "additionalProperties": False,
    },
}

#: oneOf-null 通用形（§3.2：禁 nullable——openapi-typescript 不产 | null）。
def _oneof_null(inner: dict[str, Any]) -> dict[str, Any]:
    return {"oneOf": [inner, {"type": "null"}]}


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
            "preset": _oneof_null({"type": "string"}),
        },
        ["text"],
    ),
    # M5-K3 / 裁 21-A D-2：action 增 `fast_forward`（长跨度推进，**speed 枚举不扩**——
    # DESIGN §10 明文锁 {1,4,16}，扩枚举会连带内核 ALLOWED_SPEEDS 与前端三处）。
    # 推进目标用**叙事化时长**（游戏小时）而非 tick：tick 是禁出网关的世界机器节拍
    # （ws-protocol §5），换算在服务端做。
    "SetControlMessage": _envelope(
        "control",
        "set_control",
        {
            "action": {
                "type": "string",
                "enum": ["pause", "resume", "set_speed", "fast_forward"],
            },
            "speed": {"type": "integer", "enum": [1, 4, 16]},
            "advance_hours": {
                "type": "integer",
                "minimum": 1,
                "maximum": 168,
                "description": "快进目标时长（游戏小时，叙事化单位；服务端换算 tick，"
                "tick 零出网关）。仅 action=fast_forward 时有效",
            },
        },
        ["action"],
    ),
    "LoadAnchorMessage": _envelope(
        "session", "load_anchor", {"anchor_id": {"type": "string"}}, ["anchor_id"]
    ),
    "MoveRequestMessage": _member(
        "render",
        "move_request",
        {
            "target_x": {"type": "integer", "description": "目标格 X（整数格坐标）"},
            "target_y": {"type": "integer", "description": "目标格 Y（整数格坐标）"},
        },
        ["target_x", "target_y"],
        description="玩家点击寻路：客户端只发目标格坐标，sim 负责寻路并驱动主角；"
        "无 rtoken（服务端知道主角是谁）",
    ),
    "SyncRequestMessage": _envelope(
        "session", "sync_request", {"reason": {"type": "string"}}, ["reason"]
    ),
    # ── sim → client ──
    "FullSnapshotMessage": _envelope(
        "render",
        "full_snapshot",
        {
            "map": {"$ref": "#/components/schemas/MapInfo"},
            "lights": {"type": "array", "items": {"$ref": "#/components/schemas/Light"}},
            "actors": {"type": "array", "items": {"$ref": "#/components/schemas/Actor"}},
            "structures": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/Structure"},
            },
            "weather": {"$ref": "#/components/schemas/Weather"},
            "combat": _oneof_null({"$ref": "#/components/schemas/CombatInfo"}),
        },
        # 快照口径：combat optional（可为 null=无战斗）
        ["map", "lights", "actors", "structures", "weather"],
    ),
    "StateDeltaMessage": _envelope(
        "render",
        "state_delta",
        {
            "actors": {"type": "array", "items": {"$ref": "#/components/schemas/ActorDelta"}},
            "lights": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/LightDelta"},
            },
            "structures": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/StructureDelta"},
            },
            # M5-K10（裁 19 修复）：K7 起的 plan 顶层可选键——计划看板数据面
            # （m4-plan 裁 14-3：后端只保证 plan 状态进 state_delta；渲染归前端）。
            # **顶层**而非塞 ActorDelta：改计划不必伴随移动，塞 ActorDelta 会被
            # driver 的 moved 过滤漏掉。可选（不进 required）：账本空则不发该键。
            "plan": {"type": "array", "items": {"$ref": "#/components/schemas/PlanDelta"}},
            "weather": {"$ref": "#/components/schemas/Weather"},
        },
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
            "content": {"type": "string", "description": "第一人称叙事，无数值无系统词"},
            "form": _oneof_null(
                {"type": "string", "enum": ["bubble", "thought", "plan"]}
            ),
        },
        ["sense", "content"],
    ),
    "MonologueMessage": _member(
        "narrative",
        "monologue",
        {
            "form": {"type": "string", "enum": ["bubble", "thought", "plan"]},
            "content": {
                "type": "string",
                "description": "第一人称叙事化独白，无数值无系统词",
            },
        },
        ["form", "content"],
        description="M1 独白三形态呈现（§8）；content 必须第一人称世界内语言、"
        "无数值无系统词，永不直接渲染 LLM 原始思维链",
    ),
    "ImpulseFeedbackMessage": _member(
        "control",
        "impulse_feedback",
        {
            "injected": {"type": "boolean"},
            "cue": {
                "type": "string",
                "enum": ["accepted", "hesitation", "complaint", "resistance"],
            },
            "reaction_monologue": {"$ref": "#/components/schemas/MonologueReaction"},
        },
        ["injected", "cue", "reaction_monologue"],
        description="M1 念头注入即时反馈（§10 意愿冲突度表现）；cue 是表现提示而非"
        "冲突度数值，reaction_monologue 为第一人称自我怀疑（非被操纵感）",
    ),
    "CombatEventMessage": _envelope(
        "render",
        "combat_event",
        {
            "exchange": {
                "type": "integer",
                "minimum": 0,
                "description": "本战斗内序，非世界 tick",
            },
            "rtoken": {"$ref": "#/components/schemas/RToken"},
            "posture_visual": {"type": "string"},
            "projectiles": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/Projectile"},
            },
            "hits": {"type": "array", "items": {"$ref": "#/components/schemas/Hit"}},
            "exchange_resolved": {"type": "boolean"},
        },
        ["exchange", "rtoken", "posture_visual", "exchange_resolved"],
    ),
    "TimescaleMessage": _envelope(
        "control",
        "timescale",
        {
            "mode": {"type": "string", "enum": ["normal", "combat"]},
            "active": {"type": "boolean"},
            "note": _oneof_null({"type": "string"}),
        },
        ["mode", "active"],
    ),
    # M5-K3 / D-3：新增可选 `paused`（暂停态直读，省前端推断；省略=未表达），
    # action 增 `fast_forward`（快进完成的终态 ack；D-2）。`speed` 枚举仍无 0——
    # 这是 G-1（`pause→pause→resume` 实发 speed:0 破 schema）的 schema 侧防线。
    "ControlAckMessage": _envelope(
        "control",
        "control_ack",
        {
            "action": {
                "type": "string",
                "enum": ["pause", "resume", "set_speed", "fast_forward"],
            },
            "speed": {"type": "integer", "enum": [1, 4, 16]},
            "paused": {
                "type": "boolean",
                "description": "暂停态（D-3 幂等单值）：省略=未表达；true=仍暂停，"
                "此时 speed 是恢复后倍率而非当前生效倍率",
            },
            "applied": {"type": "boolean"},
        },
        ["action", "applied"],
    ),
    # M5-K3 / 裁 21-A D-5+D-6 合并一帧：连接期初值（刻度/暂停态/游标指针）
    # + 分叉告知（叙事化一行）。零原始数值：speed 只在 {1,4,16}（暂停时=恢复后
    # 倍率）、anchor 只带 name+story_label、notice 是戏内口语行。
    "SessionStateMessage": _envelope(
        "session",
        "session_state",
        {
            "speed": {"type": "integer", "enum": [1, 4, 16]},
            "paused": {"type": "boolean"},
            "anchor": _oneof_null({"$ref": "#/components/schemas/SessionAnchor"}),
            "notice": _oneof_null({"type": "string"}),
        },
        ["speed", "paused", "anchor", "notice"],
    ),
    # ref 字段本身保留（ws-protocol.md §4.5）；「无 ref」指不用 $ref 引外部 schema
    "WsErrorMessage": _envelope(
        "error",
        "error",
        {
            "ref": {"type": "string"},
            "code": {"type": "string"},
            "message": {"type": "string", "description": "戏内文风，不向玩家显示系统措辞"},
        },
        ["ref", "code", "message"],
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
    "SessionStateMessage": "session_state",
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


def _strip_pydantic_decorations(node: Any) -> Any:
    """确定性后处理：剥 pydantic 自动装饰，对齐快照形状（K3 §4.1 判绿前置）。

    - title：pydantic 给每个字段/模型自动加「Title Case」装饰 title；快照 0 处
      （唯一 `title` 是 ProblemDetail 的业务字段名，其值是 {"type":"string"}，
      不含 "type" 键的同名键不匹配本规则，安全）。
    - minimum/maximum：ge=0 等约束被 pydantic 序列化为 0.0 浮点；快照是 0 整数。
    - description=""：模型级 json_schema_extra={"description": ""} 抑制 docstring
      进 schema（pydantic 无「不生成 description」开关）；快照无此键 → 空串剥除。
    递归纯函数（返回新结构，不原地改——项目 immutability 规约）。
    """
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if (
                k == "title"
                and isinstance(v, str)
                and isinstance(node.get("type"), str)
            ):
                continue  # 装饰 title（schema 节点上的字符串 title）
            if k == "description" and v == "":
                continue  # 抑制 docstring 的空占位（快照无 description 键）
            if k in ("minimum", "maximum") and isinstance(v, float) and v.is_integer():
                out[k] = int(v)
                continue
            out[k] = _strip_pydantic_decorations(v)
        return out
    if isinstance(node, list):
        return [_strip_pydantic_decorations(v) for v in node]
    return node



def _attach_problem_responses(schema: dict[str, Any]) -> None:
    """anchors 路由 Problem 响应声明（M5-S9 / anchors-api.md §5.1 手抄清单）。

    exception_handler 产出的响应**不会自动进** /openapi.json（§3.3 关键坑）——
    必须在此手注。快照 components.responses.Problem 已就绪（K3 前瞻式声明）；
    live 侧在此对齐。调用点在 get_openapi(...) 之后（否则 paths 被重建冲掉）。
    """
    components = schema.setdefault("components", {})
    # R-2（K7 HIGH）：responses.Problem 悬空 $ref 修复——live 侧同时注入
    # ProblemDetail schema（快照那份的字段级副本；快照侧对账归 kilo 域）。
    schemas_map = components.setdefault("schemas", {})
    schemas_map.setdefault(
        "ProblemDetail",
        {
            "type": "object",
            "required": ["title", "status"],
            "properties": {
                "type": {"type": "string"},
                "title": {"type": "string"},
                "status": {"type": "integer"},
                "detail": {"type": "string"},
            },
            "additionalProperties": False,
        },
    )
    problem = {"$ref": "#/components/schemas/ProblemDetail"}
    components.setdefault("responses", {})["Problem"] = {
        "description": "RFC 7807 问题详情（戏外工程措辞，不回灌 Agent）",
        "content": {"application/json": {"schema": problem}},
    }
    problem_resp = {"$ref": "#/components/responses/Problem"}

    def attach(route_key: str, method: str, codes: list[str]) -> None:
        op = schema["paths"].get(route_key, {}).get(method)
        if op is None:
            return
        for code in codes:
            op.setdefault("responses", {})[code] = dict(problem_resp)

    attach("/api/anchors", "post", ["400", "422"])  # 世界未就绪 / 校验失败
    attach("/api/anchors/current", "get", ["404"])  # R-3②：空库 404（K3 前瞻声明对齐）
    # M6-K7（K6 审计 §3.3 反向缺口）：路由确实抛 404，此前 attach 清单漏了
    attach("/api/anchors/{anchor_id}", "get", ["404"])  # 不存在
    attach("/api/anchors/{anchor_id}", "patch", ["404", "422"])  # 不存在 / 校验失败
    attach("/api/anchors/{anchor_id}", "delete", ["404", "409"])  # 不存在 / 末梢受保护
    # M6-K2：只读诊断面（批次 E）——`exception_handler` 产的 400/404 不会自动进
    # /openapi.json（§3.3 关键坑），故与快照同款手工登记。
    attach("/api/anchors/{anchor_id}/materialization", "get", ["400", "404"])  # 无世界 / 档不存在
    # M6-K7（K6 审计 §3.3 反向缺口）：这三条**确实抛 404**（`settings.py` 抛
    # `/errors/profile-not-found`），快照也声明了，但 attach 清单此前漏了 ⇒ live spec 缺 404 声明，
    # 与快照不一致。补齐后 live↔快照在这四条路由上对齐。
    attach("/api/settings/profiles/{profile_id}", "patch", ["404"])  # 档案不存在
    attach("/api/settings/profiles/{profile_id}", "delete", ["404"])  # 档案不存在
    attach("/api/settings/profiles/{profile_id}/activate", "post", ["404"])  # 档案不存在

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
    schemas.update(_SUB_SCHEMAS)
    schemas.update(_WS_SCHEMAS)
    schemas["WsMessage"] = _WS_UNION
    _attach_problem_responses(schema)
    schema = _strip_pydantic_decorations(schema)
    app.openapi_schema = schema
    return schema


def install() -> None:
    """把 custom_openapi 装到 app（main.py lifespan 前调用一次）。"""
    app.openapi = custom_openapi
