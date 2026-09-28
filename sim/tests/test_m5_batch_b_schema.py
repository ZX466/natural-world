"""M5-K3 批次 B 的协议面硬判据（openapi_ext → 快照 → 生成物 三段不变量）。

三硬判据（派单原文）：
1. **ext ↔ 快照逐字段相等**（`sim/api/openapi_ext.py` 是注入源，`shared/openapi.json`
   是唯一真相源；两处漂移即协议面静默分叉）；
2. **实发项 ⊆ schema 属性**（`additionalProperties:false` 镜像——多发一个键就是协议违约，
   K9 抓 PlanDelta 用的就是这条）；
3. **生成物 TS 含新键**（`shared/protocol.ts` 是前端唯一可达面，`gen-protocol` 产物非手写）。

本类锁住批次 B 新增/改动的四个 schema：`SessionAnchor`（新）、`SessionStateMessage`
（新）、`SetControlMessage`（扩 action 枚举 + 增 `advance_hours`）、`ControlAckMessage`
（扩 action 枚举 + 增 `paused`）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sim.api.ws import (
    ControlState,
    fast_forward_done_frames,
    handle_client_message,
    session_state_payload,
)
from sim.core.events import world_create_event
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.world.map import CHUNK_SIZE, Chunk, TileMap
from sim.world.pathfinding import Pathfinder

#: 批次 B 涉及的 schema 名（判据覆盖面显式列出，新增成员须同步扩这里）。
BATCH_B_SCHEMAS = (
    "SessionAnchor",
    "SessionStateMessage",
    "SetControlMessage",
    "ControlAckMessage",
)


def _schemas() -> dict[str, Any]:
    """shared/openapi.json 快照（gen-protocol 的唯一真相源）。"""
    path = Path(__file__).parents[2] / "shared" / "openapi.json"
    return json.loads(path.read_text(encoding="utf-8"))["components"]["schemas"]


def _protocol_ts() -> str:
    return (Path(__file__).parents[2] / "shared" / "protocol.ts").read_text(encoding="utf-8")


def _loop() -> TickLoop:
    from sim.core.clock import GameClock

    loop = TickLoop(
        clock=GameClock(speed=1.0), bus=build_default_bus(), state=WorldState(world_seed=42)
    )
    loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
    loop.drain_events()
    return loop


def _tile_map() -> TileMap:
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


class TestSetControlSchema:
    def test_action_enum_has_fast_forward_and_keeps_others(self) -> None:
        props = _schemas()["SetControlMessage"]["properties"]
        assert set(props["action"]["enum"]) == {
            "pause",
            "resume",
            "set_speed",
            "fast_forward",
        }

    def test_speed_enum_unchanged(self) -> None:
        """D-2 不扩 speed 枚举（§10 锁 {1,4,16}）。"""
        props = _schemas()["SetControlMessage"]["properties"]
        assert props["speed"]["enum"] == [1, 4, 16]

    def test_advance_hours_is_optional_bounded_integer(self) -> None:
        schema = _schemas()["SetControlMessage"]
        assert schema["properties"]["advance_hours"] == {
            "type": "integer",
            "minimum": 1,
            "maximum": 168,
            "description": "快进目标时长（游戏小时，叙事化单位；服务端换算 tick，"
            "tick 零出网关）。仅 action=fast_forward 时有效",
        }
        assert "advance_hours" not in schema["required"]


class TestControlAckSchema:
    def test_action_enum_includes_fast_forward(self) -> None:
        props = _schemas()["ControlAckMessage"]["properties"]
        assert set(props["action"]["enum"]) == {
            "pause",
            "resume",
            "set_speed",
            "fast_forward",
        }

    def test_paused_is_optional_boolean(self) -> None:
        schema = _schemas()["ControlAckMessage"]
        assert schema["properties"]["paused"] == {
            "type": "boolean",
            "description": "暂停态（D-3 幂等单值）：省略=未表达；true=仍暂停，"
            "此时 speed 是恢复后倍率而非当前生效倍率",
        }
        assert "paused" not in schema["required"]

    def test_speed_enum_still_excludes_zero(self) -> None:
        """G-1：枚举无 0 是第一道防线，ack 侧断言锁住。"""
        props = _schemas()["ControlAckMessage"]["properties"]
        assert props["speed"]["enum"] == [1, 4, 16]


class TestSessionStateSchema:
    def test_anchor_component_closed_two_keys(self) -> None:
        schema = _schemas()["SessionAnchor"]
        assert schema["additionalProperties"] is False
        assert set(schema["properties"]) == {"name", "story_label"}
        assert set(schema["required"]) == {"name", "story_label"}

    def test_envelope_and_payload(self) -> None:
        schema = _schemas()["SessionStateMessage"]
        props = schema["properties"]
        assert schema["additionalProperties"] is False
        assert props["type"]["enum"] == ["session_state"]
        assert props["channel"]["enum"] == ["session"]
        assert props["speed"]["enum"] == [1, 4, 16]
        assert props["paused"]["type"] == "boolean"
        assert props["anchor"] == {
            "oneOf": [{"$ref": "#/components/schemas/SessionAnchor"}, {"type": "null"}]
        }
        assert props["notice"]["oneOf"] == [{"type": "string"}, {"type": "null"}]
        assert set(schema["required"]) == {
            "v",
            "ws_seq",
            "channel",
            "type",
            "speed",
            "paused",
            "anchor",
            "notice",
        }


class TestUnionRegistration:
    def test_type_of_mapping(self) -> None:
        import sim.api.main  # noqa: F401  # 先初始化 main，防 openapi_ext→main 循环导入
        from sim.api.openapi_ext import _TYPE_OF

        assert _TYPE_OF["SessionStateMessage"] == "session_state"

    def test_union_and_discriminator_carry_new_member(self) -> None:
        schemas = _schemas()
        refs = {r["$ref"] for r in schemas["WsMessage"]["oneOf"]}
        assert "#/components/schemas/SessionStateMessage" in refs
        mapping = schemas["WsMessage"]["discriminator"]["mapping"]
        assert mapping["session_state"] == "#/components/schemas/SessionStateMessage"


class TestExtSourceMatchesSnapshot:
    """双处同步铁律：注入源与快照逐字段相等（派单硬判据 1）。"""

    def test_batch_b_schemas_equal(self) -> None:
        import sim.api.main  # noqa: F401  # 先初始化 main，防 openapi_ext→main 循环导入
        from sim.api.openapi_ext import _SUB_SCHEMAS, _WS_SCHEMAS

        live = {**_SUB_SCHEMAS, **_WS_SCHEMAS}
        snapshot = _schemas()
        for name in BATCH_B_SCHEMAS:
            assert live[name] == snapshot[name], f"{name} ext 与快照漂移"


class TestGeneratedTsCarriesNewKeys:
    """生成物含新键（派单硬判据 3；protocol.ts 非手写）。"""

    def test_new_components_present(self) -> None:
        text = _protocol_ts()
        assert "readonly SessionStateMessage: {" in text
        assert "readonly SessionAnchor: {" in text

    def test_new_fields_and_enum_values_present(self) -> None:
        text = _protocol_ts()
        assert "readonly advance_hours?: number;" in text
        assert "readonly paused?: boolean;" in text
        # SetControl + ControlAck 两处 action 枚举都含 fast_forward
        assert text.count("'fast_forward'") >= 2
        assert "readonly type: 'session_state';" in text
        assert "readonly get: operations['getCurrentAnchor'];" in text


class TestEmittedFramesWithinSchema:
    """实发项 ⊆ schema 属性（派单硬判据 2）。"""

    def _assert_within(self, frame: dict[str, Any], schema_name: str) -> None:
        allowed = set(_schemas()[schema_name]["properties"])
        assert set(frame) <= allowed, f"越界键：{set(frame) - allowed}"

    def test_control_ack_variants(self) -> None:
        from sim.api.ws import _handle_set_control

        loop, control = _loop(), ControlState()
        for msg in (
            {"action": "set_speed", "speed": 4},
            {"action": "pause"},
            {"action": "resume"},
            {"action": "fast_forward", "advance_hours": 1},
        ):
            frame = _handle_set_control(
                {"type": "set_control", "channel": "control", **msg}, loop, control
            )
            if isinstance(frame, dict) and frame["type"] == "control_ack":
                self._assert_within(frame, "ControlAckMessage")

    def test_fast_forward_completion_frames(self) -> None:
        control = ControlState()
        control.request_fast_forward(3_600)
        frames = fast_forward_done_frames(_loop(), _tile_map(), control)
        self._assert_within(frames[0], "ControlAckMessage")
        self._assert_within(frames[1], "FullSnapshotMessage")

    def test_session_state_frame(self) -> None:
        frame = session_state_payload(
            speed=1,
            paused=False,
            anchor={"name": "档", "story_label": "第三日 · 夜"},
            notice="你回来了",
        )
        self._assert_within(frame, "SessionStateMessage")

    def test_error_frame_still_within_schema(self) -> None:
        loop, pf = _loop(), Pathfinder(_tile_map())
        reply = handle_client_message(
            {"type": "set_control", "channel": "control", "action": "fast_forward"},
            loop,
            pf,
            ControlState(),
        )
        assert isinstance(reply, dict)
        self._assert_within(reply, "WsErrorMessage")
