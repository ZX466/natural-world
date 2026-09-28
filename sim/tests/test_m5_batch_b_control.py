"""M5-K3 批次 B：fast_forward 新 action（D-2）+ 暂停语义批（D-3 幂等单值，清 G-1~G-4）。

判据源自 `docs/arch/m5-rulings.md` 裁 21-A §A：
- **D-2**：`speed` 枚举**不扩**（§10 锁 {1,4,16}）；快进走**新 action** `fast_forward`
  （长跨度推进、批处理语义）。serverToClient **零新增消息**（D-4）——完成信号复用
  `control_ack`，重同步一律全量（D-7）。
- **D-3 幂等单值**：`pause` 幂等（不重压记忆倍率）/ `resume` 无暂停回 `bad_action`
  （G-2：不得静默改速）/ 暂停中 `set_speed` **只改记忆值**（G-3：不解除暂停）。
- **G-1 协议违约清零**：任何 `control_ack` 出站帧的 `speed`（若存在）必 ∈ {1,4,16}
   ——旧实现 `pause→pause→resume` 实发 `speed:0` 破 `ControlAckMessage` 枚举。
- **G-4**：会话态**连接级**——两个 `ControlState` 互不串，模块级 `_PRE_PAUSE_SPEED` 消失。

出戏边界：`advance_hours` 是**叙事化时长**（游戏小时，1..168），服务端换算 tick；
**tick/seq/branch_id 零出网关**（ws-protocol §5）——线格式永不带 tick。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi import WebSocket

from sim.api import ws as ws_mod
from sim.api.ws import (
    ALLOWED_CONTROL_SPEEDS,
    FAST_FORWARD_MAX_HOURS,
    ControlState,
    fast_forward_done_frames,
    frames_of,
    handle_client_message,
    step_fast_forward,
)
from sim.core.events import world_create_event
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.world.map import CHUNK_SIZE, Chunk, TileMap
from sim.world.pathfinding import Pathfinder

#: `ControlAckMessage.speed` 的 schema 枚举（openapi_ext 侧同源，测试独立复述）。
ACK_SPEED_ENUM = frozenset({1, 4, 16})


@pytest.fixture(autouse=True)
def _clean_gateway_session_state() -> Iterator[None]:
    """模块级兜底控制态（未传 control 的直接调用）+ anchor 登记逐用例隔离。"""
    ws_mod.reset_legacy_control()
    ws_mod.reset_anchor_registry()
    yield
    ws_mod.reset_legacy_control()
    ws_mod.reset_anchor_registry()


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


@pytest.fixture()
def control() -> ControlState:
    return ControlState()


def _send(loop: TickLoop, pf: Pathfinder, control: ControlState, **msg: Any) -> Any:
    return handle_client_message(
        {"type": "set_control", "channel": "control", **msg}, loop, pf, control
    )


class TestPauseIdempotentSingleValue:
    """D-3：幂等单值。"""

    def test_pause_then_resume_restores_speed(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        assert _send(loop, pf, control, action="set_speed", speed=4)["speed"] == 4
        paused = _send(loop, pf, control, action="pause")
        assert paused["action"] == "pause"
        assert paused["applied"] is True
        assert paused["paused"] is True
        assert "speed" not in paused  # 枚举无 0，pause 不回 speed
        assert loop.clock.speed == 0.0
        resumed = _send(loop, pf, control, action="resume")
        assert resumed["speed"] == 4
        assert resumed["paused"] is False
        assert loop.clock.speed == 4.0

    def test_pause_is_idempotent_and_keeps_remembered_speed(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        """幂等：连按两次 pause 不得把记忆倍率压成 0（G-1 根因）。"""
        _send(loop, pf, control, action="set_speed", speed=4)
        first = _send(loop, pf, control, action="pause")
        second = _send(loop, pf, control, action="pause")
        assert first["applied"] is True and second["applied"] is True
        assert second["paused"] is True
        assert control.speed_before_pause == 4.0
        assert _send(loop, pf, control, action="resume")["speed"] == 4

    def test_resume_without_pause_is_error_and_leaves_speed(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        """G-2：无暂停 resume 不得静默改速，也不得回 applied:true 的假 ack。"""
        _send(loop, pf, control, action="set_speed", speed=16)
        reply = _send(loop, pf, control, action="resume")
        assert reply["type"] == "error"
        assert reply["code"] == "bad_action"
        assert loop.clock.speed == 16.0

    def test_set_speed_while_paused_only_moves_memory(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        """G-3：暂停中 set_speed 不解除暂停（clock 仍 0），只改记忆倍率。"""
        _send(loop, pf, control, action="set_speed", speed=1)
        _send(loop, pf, control, action="pause")
        ack = _send(loop, pf, control, action="set_speed", speed=16)
        assert ack["speed"] == 16
        assert ack["paused"] is True
        assert loop.clock.speed == 0.0
        assert control.paused is True
        assert _send(loop, pf, control, action="resume")["speed"] == 16
        assert loop.clock.speed == 16.0

    def test_speed_always_within_schema_enum(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        """G-1：混合动作序列下，任何 ack 的 speed 都必在 schema 枚举内。"""
        script: list[dict[str, Any]] = [
            {"action": "pause"},
            {"action": "pause"},
            {"action": "set_speed", "speed": 16},
            {"action": "pause"},
            {"action": "resume"},
            {"action": "resume"},
            {"action": "set_speed", "speed": 4},
            {"action": "pause"},
            {"action": "set_speed", "speed": 1},
            {"action": "resume"},
        ]
        for msg in script:
            reply = _send(loop, pf, control, **msg)
            if reply is None or reply.get("type") != "control_ack":
                continue
            if "speed" in reply:
                assert reply["speed"] in ACK_SPEED_ENUM, f"越枚举：{reply}"

    def test_corrupt_clock_speed_cannot_leak_zero(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        """兜底：即使 clock.speed 被外部写坏，ack 也不得出现 0。"""
        loop.clock.set_speed(1.0)
        _send(loop, pf, control, action="pause")
        loop.clock.set_speed(0.0)  # 绕过控制面直接写坏
        _send(loop, pf, control, action="pause")
        resumed = _send(loop, pf, control, action="resume")
        assert resumed["speed"] in ACK_SPEED_ENUM


class TestControlStateIsolation:
    """G-4：会话态连接级。"""

    def test_two_controls_do_not_share_memory(
        self, loop: TickLoop, pf: Pathfinder
    ) -> None:
        a, b = ControlState(), ControlState()
        _send(loop, pf, a, action="set_speed", speed=4)
        _send(loop, pf, a, action="pause")
        assert a.paused is True and b.paused is False
        assert b.speed_before_pause == 1.0
        assert _send(loop, pf, b, action="set_speed", speed=16)["speed"] == 16
        assert a.speed_before_pause == 4.0
        assert _send(loop, pf, a, action="resume")["speed"] == 4

    def test_module_level_pause_stack_is_gone(self) -> None:
        """白盒：旧实现是模块级 list（多连接互窃倍率）。"""
        assert not hasattr(ws_mod, "_PRE_PAUSE_SPEED")

    def test_manager_owns_per_connection_control(self) -> None:
        """连接级状态挂在 ConnectionManager（每连接一个 ControlState）。"""
        manager = ws_mod.ConnectionManager()
        ws_a, ws_b = cast("WebSocket", object()), cast("WebSocket", object())
        manager.register(ws_a)
        manager.register(ws_b)
        try:
            assert manager.control_of(ws_a) is not manager.control_of(ws_b)
        finally:
            manager.unregister(ws_a)
            manager.unregister(ws_b)


class TestFastForwardAction:
    """D-2：fast_forward 新 action（批处理语义 + 参数校验）。"""

    def test_missing_advance_hours_rejected(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        reply = _send(loop, pf, control, action="fast_forward")
        assert reply["type"] == "error"
        assert reply["code"] == "bad_advance"
        assert control.pending_fast_forward is None

    @pytest.mark.parametrize("hours", [0, -1, 169, True, 1.5, "2", None])
    def test_invalid_advance_hours_rejected(
        self, hours: Any, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        reply = _send(loop, pf, control, action="fast_forward", advance_hours=hours)
        assert reply["type"] == "error"
        assert reply["code"] == "bad_advance"
        assert control.pending_fast_forward is None

    def test_boundary_hours_accepted(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        assert _send(loop, pf, control, action="fast_forward", advance_hours=1) is None
        assert control.pending_fast_forward == 3_600
        control.cancel_fast_forward()
        assert (
            _send(loop, pf, control, action="fast_forward", advance_hours=FAST_FORWARD_MAX_HOURS)
            is None
        )
        assert control.pending_fast_forward == FAST_FORWARD_MAX_HOURS * 3_600

    def test_accepted_request_is_silent_until_done(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        """受理不发帧：ack 是「完成」信号不是「受理」信号（不得撒谎 applied）。"""
        assert _send(loop, pf, control, action="fast_forward", advance_hours=2) is None
        assert control.pending_fast_forward == 7_200

    def test_rejected_while_paused(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        _send(loop, pf, control, action="pause")
        reply = _send(loop, pf, control, action="fast_forward", advance_hours=1)
        assert reply["type"] == "error"
        assert reply["code"] == "bad_advance"
        assert control.pending_fast_forward is None

    def test_duplicate_request_rejected(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        _send(loop, pf, control, action="fast_forward", advance_hours=1)
        reply = _send(loop, pf, control, action="fast_forward", advance_hours=1)
        assert reply["type"] == "error"
        assert reply["code"] == "bad_advance"
        assert control.pending_fast_forward == 3_600

    def test_pause_cancels_in_flight(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        _send(loop, pf, control, action="fast_forward", advance_hours=6)
        assert control.pending_fast_forward is not None
        ack = _send(loop, pf, control, action="pause")
        assert ack["action"] == "pause"
        assert control.pending_fast_forward is None
        assert loop.clock.speed == 0.0


class TestFastForwardDriverStep:
    """驱动侧：按帧预算摊还推进 + 终态两帧（ack + 全量重同步，D-7）。"""

    def test_step_advances_ticks_and_terminates(
        self, loop: TickLoop, control: ControlState
    ) -> None:
        control.request_fast_forward(3_600)
        total = 0
        for _ in range(20):
            total += step_fast_forward(loop, [control], budget=240)
            if control.pending_fast_forward == 0:
                break
        assert total == 3_600
        assert control.pending_fast_forward == 0
        assert loop.state.tick == 3_600

    def test_step_respects_budget_and_shares_across_connections(self, loop: TickLoop) -> None:
        """跨连接共享同一帧预算；按登记顺序消耗，先到先得（不吃穿预算）。"""
        a, b = ControlState(), ControlState()
        a.request_fast_forward(100)  # 小额先满足
        b.request_fast_forward(10_000)
        moved = step_fast_forward(loop, [a, b], budget=240)
        assert moved == 240  # 100 给 a，其余 140 给 b
        assert a.pending_fast_forward == 0
        assert b.pending_fast_forward == 10_000 - 140

    def test_step_never_exceeds_budget(self, loop: TickLoop) -> None:
        a, b, c = ControlState(), ControlState(), ControlState()
        for control in (a, b, c):
            control.request_fast_forward(5_000)
        assert step_fast_forward(loop, [a, b, c], budget=240) <= 240

    def test_step_noop_without_requests(self, loop: TickLoop, control: ControlState) -> None:
        assert step_fast_forward(loop, [control], budget=240) == 0
        assert loop.state.tick == 0

    def test_step_noop_while_paused(self, loop: TickLoop, control: ControlState) -> None:
        """世界停 ⇒ 快进不推进（rate=0 分支），不死循环空转。"""
        control.request_fast_forward(3_600)
        loop.clock.set_speed(0.0)
        assert step_fast_forward(loop, [control], budget=240) == 0
        assert control.pending_fast_forward == 3_600

    def test_done_frames_are_ack_then_full_snapshot(
        self, loop: TickLoop, control: ControlState, tile_map: TileMap
    ) -> None:
        control.request_fast_forward(3_600)
        control.speed_before_pause = 4.0
        frames = fast_forward_done_frames(loop, tile_map, control)
        assert [f["type"] for f in frames] == ["control_ack", "full_snapshot"]
        ack = frames[0]
        assert ack["action"] == "fast_forward"
        assert ack["applied"] is True
        assert ack["speed"] == 4
        assert ack["paused"] is False
        assert frames[1]["channel"] == "render"

    def test_done_frames_carry_no_internal_ids(
        self, loop: TickLoop, control: ControlState, tile_map: TileMap
    ) -> None:
        control.request_fast_forward(3_600)
        for frame in fast_forward_done_frames(loop, tile_map, control):
            text = repr(frame)
            for banned in ("tick", "branch_id", "entity_id", "seed"):
                assert banned not in text


class TestFramesOf:
    """K4 §0.1 单回复通道在 M5-K3 增补：分叉需「告知帧 + 全量」两帧。"""

    def test_none_and_dict_and_list(self) -> None:
        assert frames_of(None) == []
        assert frames_of({"type": "a"}) == [{"type": "a"}]
        two = [{"type": "a"}, {"type": "b"}]
        assert frames_of(two) == two


class TestAllowedControlSpeeds:
    def test_speed_enum_unchanged(self) -> None:
        """D-2：speed 枚举不扩（§10 锁 {1,4,16}）——批次 B 的第一道不变量。"""
        assert set(ALLOWED_CONTROL_SPEEDS) == ACK_SPEED_ENUM
