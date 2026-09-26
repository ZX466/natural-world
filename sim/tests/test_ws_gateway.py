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


@pytest.fixture(autouse=True)
def _reset_gateway_state():
    """网关模块级会话态（暂停前倍率栈 / anchor 登记）逐用例隔离，防跨用例污染。"""
    from sim.api import ws as ws_mod

    ws_mod.reset_pre_pause_speed()
    ws_mod.reset_anchor_registry()
    yield
    ws_mod.reset_pre_pause_speed()
    ws_mod.reset_anchor_registry()


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

    def test_move_request_non_int_target_bad_target(self, loop: TickLoop, pf: Pathfinder):
        """8.6 / §4：非法类型目标升级为 error{code:"bad_target"}（不再静默）。"""
        for tx, ty in (("8", 4), (8, None), (True, 4), (8.5, 4)):
            reply = handle_client_message(
                {"type": "move_request", "channel": "render", "target_x": tx, "target_y": ty},
                loop,
                pf,
            )
            assert reply is not None, f"({tx!r},{ty!r}) 不得静默"
            assert reply["type"] == "error"
            assert reply["ref"] == "move_request"
            assert reply["code"] == "bad_target"

    def test_move_request_unreachable_stays_silent(self, loop: TickLoop, pf: Pathfinder):
        """§4 权衡：不可达保留静默（客户端预测已覆盖，避免高频噪声）。"""
        reply = handle_client_message(
            {"type": "move_request", "channel": "render", "target_x": 999, "target_y": 999},
            loop,
            pf,
        )
        assert reply is None

    def test_move_request_no_protagonist_silent(self, loop: TickLoop, pf: Pathfinder):
        """主角不存在仍是世界态问题（非客户端输入缺陷）——保留静默。"""
        empty = TickLoop(clock=loop.clock, bus=loop.bus, state=WorldState(world_seed=7))
        reply = handle_client_message(
            {"type": "move_request", "channel": "render", "target_x": 4, "target_y": 4},
            empty,
            pf,
        )
        assert reply is None


class TestUntrustedInput:
    def test_unknown_type_rejected(self, loop: TickLoop, pf: Pathfinder):
        reply = handle_client_message({"type": "give_me_seed", "channel": "render"}, loop, pf)
        assert reply is not None and reply["type"] == "error"

    def test_error_carries_ref_of_rejected_type(self, loop: TickLoop, pf: Pathfinder):
        """K3 附注 2 + ws-protocol §4.5：error.ref = 被拒消息 type（schema required 锚）。"""
        reply = handle_client_message({"type": "give_me_seed", "channel": "render"}, loop, pf)
        assert reply is not None
        assert reply["ref"] == "give_me_seed"
        reply2 = handle_client_message({"type": "move_request", "channel": "control"}, loop, pf)
        assert reply2 is not None
        assert reply2["ref"] == "move_request"

    def test_channel_mismatch_rejected(self, loop: TickLoop, pf: Pathfinder):
        reply = handle_client_message(
            {"type": "move_request", "channel": "control"},
            loop,
            pf,
        )
        assert reply is not None and reply["type"] == "error"


class TestSyncRequest:
    """K4 提案 §5/§8.7（M5-K5 首修）：sync_request 必须回 full_snapshot，
    旧实现错回 control_ack（与 set_control 确认语义冲突，客户端无法据此重建世界）。"""

    def test_sync_request_returns_full_snapshot(self, loop: TickLoop, pf: Pathfinder):
        reply = handle_client_message(
            {"type": "sync_request", "channel": "session", "reason": "reconnect"},
            loop,
            pf,
        )
        assert reply is not None
        assert reply["type"] == "full_snapshot"
        assert reply["channel"] == "render"

    def test_sync_request_not_control_ack(self, loop: TickLoop, pf: Pathfinder):
        """回归钉（回错型）：不得退回 set_control 的确认帧型。"""
        reply = handle_client_message(
            {"type": "sync_request", "channel": "session", "reason": "gap_detected"},
            loop,
            pf,
        )
        assert reply is not None
        assert reply["type"] != "control_ack"
        assert "action" not in reply and "applied" not in reply and "speed" not in reply

    def test_sync_request_snapshot_matches_connect_snapshot(
        self, loop: TickLoop, pf: Pathfinder, tile_map: TileMap
    ):
        """回帧与连接即发的全量快照同形（ws-protocol.md §4.4：full_snapshot 响应见 §4.1）。"""
        reply = handle_client_message(
            {"type": "sync_request", "channel": "session"},
            loop,
            pf,
        )
        assert reply is not None
        assert set(reply.keys()) == set(snapshot_payload(loop, tile_map).keys())

    def test_sync_request_snapshot_clean(self, loop: TickLoop, pf: Pathfinder):
        import json

        reply = handle_client_message(
            {"type": "sync_request", "channel": "session", "reason": "after_load"},
            loop,
            pf,
        )
        assert reply is not None
        text = json.dumps(reply)
        assert "tick" not in text and "seed" not in text and "branch" not in text
        assert "chenmo" not in text  # 内部 id 不可见
        assert "rt-" in text

    def test_sync_request_wrong_channel_rejected(self, loop: TickLoop, pf: Pathfinder):
        """session 通道约束仍在（channel 校验前置于分发块）。"""
        reply = handle_client_message({"type": "sync_request", "channel": "control"}, loop, pf)
        assert reply is not None and reply["type"] == "error"
        assert reply["code"] == "bad_channel"


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

    def test_snapshot_key_whitelist(self, loop: TickLoop, tile_map: TileMap):
        """键白名单快照断言（codex P3 #3）：载荷键封闭集合，
        新增字段必须过本测试 + 安全域评审，防文本 grep 漏报。"""
        payload = snapshot_payload(loop, tile_map)
        top_keys = set(payload.keys())
        assert top_keys == {
            "type",
            "channel",
            "v",
            "ws_seq",
            "actors",
            "lights",
            "structures",
            "map",
            "weather",
            "combat",
        }
        for actor in payload["actors"]:
            assert set(actor.keys()) == {"rtoken", "x", "y", "facing", "sprite", "anim"}
        assert set(payload["map"].keys()) == {"w", "h", "tileset"}

    def test_delta_key_whitelist(self, loop: TickLoop):
        """delta 键白名单同口径。"""
        loop.issue_move("chenmo", [(1, 0), (2, 0)])
        loop.advance_frame(1.0)
        payload = delta_payload(loop, loop.drain_delta())
        assert set(payload.keys()) == {"type", "channel", "v", "ws_seq", "actors"}
        for actor in payload["actors"]:
            assert set(actor.keys()) == {"rtoken", "x", "y"}

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
# K4 提案 §7 验收对表（1-6、18）— set_control 分发块（M5-K6 施工）
# ---------------------------------------------------------------------------


class TestSetControl:
    """K4 提案 §1：set_control 分发块契约。原白名单放行但静默 return None。"""

    def test_set_speed_applies(self, loop: TickLoop, pf: Pathfinder):
        """§7 #1：set_speed → control_ack（applied 恒 true，8.1）+ clock 生效。"""
        reply = handle_client_message(
            {"type": "set_control", "channel": "control", "action": "set_speed", "speed": 4},
            loop,
            pf,
        )
        assert reply is not None
        assert reply["type"] == "control_ack"
        assert reply["channel"] == "control"
        assert reply["action"] == "set_speed"
        assert reply["applied"] is True
        assert reply["speed"] == 4
        assert loop.clock.speed == 4.0

    def test_pause_then_resume_restores_previous_speed(self, loop: TickLoop, pf: Pathfinder):
        """§7 #2：pause → speed=0 并存暂停前倍率；resume → 恢复该值。"""
        loop.clock.set_speed(4.0)
        paused = handle_client_message(
            {"type": "set_control", "channel": "control", "action": "pause"}, loop, pf
        )
        assert paused is not None
        assert paused["type"] == "control_ack"
        assert paused["action"] == "pause"
        assert "speed" not in paused  # pause 的 ack 不带 speed（schema speed 无 0）
        assert loop.clock.speed == 0.0

        resumed = handle_client_message(
            {"type": "set_control", "channel": "control", "action": "resume"}, loop, pf
        )
        assert resumed is not None
        assert resumed["type"] == "control_ack"
        assert resumed["action"] == "resume"
        assert resumed["speed"] == 4
        assert loop.clock.speed == 4.0

    def test_pause_from_default_speed_resumes_to_one(self, loop: TickLoop, pf: Pathfinder):
        """暂停前为默认 1x 时，resume 回 1（_pre_pause_speed 无值 → 1.0）。"""
        handle_client_message(
            {"type": "set_control", "channel": "control", "action": "pause"}, loop, pf
        )
        reply = handle_client_message(
            {"type": "set_control", "channel": "control", "action": "resume"}, loop, pf
        )
        assert reply is not None
        assert reply["speed"] == 1
        assert loop.clock.speed == 1.0

    def test_speed_bool_rejected(self, loop: TickLoop, pf: Pathfinder):
        """§7 #3 bool 陷阱：JSON true 是 int 子类且 true ∈ {1,4,16}——必须排除。"""
        reply = handle_client_message(
            {"type": "set_control", "channel": "control", "action": "set_speed", "speed": True},
            loop,
            pf,
        )
        assert reply is not None
        assert reply["type"] == "error"
        assert reply["ref"] == "set_control"
        assert reply["code"] == "bad_speed"
        assert loop.clock.speed == 1.0  # clock 未被污染

    def test_speed_out_of_enum_rejected(self, loop: TickLoop, pf: Pathfinder):
        """§7 #4：speed=8 不在 {1,4,16} → bad_speed，clock 不变。"""
        for bad in (8, 0, 2, 32):
            reply = handle_client_message(
                {"type": "set_control", "channel": "control", "action": "set_speed", "speed": bad},
                loop,
                pf,
            )
            assert reply is not None and reply["code"] == "bad_speed", f"speed={bad} 应被拒"
        assert loop.clock.speed == 1.0

    def test_speed_missing_or_non_int_rejected(self, loop: TickLoop, pf: Pathfinder):
        """§1.4：set_speed 缺 speed / 字符串 / null 均回 bad_speed。"""
        for payload in ({}, {"speed": "4"}, {"speed": None}, {"speed": 4.5}):
            reply = handle_client_message(
                {"type": "set_control", "channel": "control", "action": "set_speed", **payload},
                loop,
                pf,
            )
            assert reply is not None and reply["code"] == "bad_speed", f"{payload} 应被拒"

    def test_unknown_action_rejected(self, loop: TickLoop, pf: Pathfinder):
        """§7 #5：action 非三值 → bad_action。"""
        reply = handle_client_message(
            {"type": "set_control", "channel": "control", "action": "nope"}, loop, pf
        )
        assert reply is not None
        assert reply["type"] == "error"
        assert reply["ref"] == "set_control"
        assert reply["code"] == "bad_action"

    def test_missing_action_rejected(self, loop: TickLoop, pf: Pathfinder):
        """action 缺失同属 bad_action。"""
        reply = handle_client_message({"type": "set_control", "channel": "control"}, loop, pf)
        assert reply is not None and reply["code"] == "bad_action"

    def test_no_silent_drop_on_illegal(self, loop: TickLoop, pf: Pathfinder):
        """§7 #6 回归钉：任意非法 set_control 的 reply 非 None（不得退回静默）。"""
        cases = [
            {"action": "nope"},
            {"action": "set_speed", "speed": 8},
            {"action": "set_speed"},
            {"action": 42},
            {},
        ]
        for extra in cases:
            reply = handle_client_message(
                {"type": "set_control", "channel": "control", **extra}, loop, pf
            )
            assert reply is not None, f"set_control{extra} 不得静默"

    def test_extra_speed_on_pause_tolerated(self, loop: TickLoop, pf: Pathfinder):
        """8.2：pause/resume 携带 speed 容忍忽略（不报错），与 move_request 宽容风格一致。"""
        loop.clock.set_speed(16.0)
        reply = handle_client_message(
            {"type": "set_control", "channel": "control", "action": "pause", "speed": 4}, loop, pf
        )
        assert reply is not None
        assert reply["type"] == "control_ack"
        assert loop.clock.speed == 0.0
        reply2 = handle_client_message(
            {"type": "set_control", "channel": "control", "action": "resume", "speed": 1}, loop, pf
        )
        assert reply2 is not None and reply2["type"] == "control_ack"
        assert loop.clock.speed == 16.0  # 用暂停前值，不信任 resume 带的 speed

    def test_clock_untouched_when_rejected(self, loop: TickLoop, pf: Pathfinder):
        """拒绝面硬约束：非法输入绝不改 clock。"""
        loop.clock.set_speed(4.0)
        handle_client_message(
            {"type": "set_control", "channel": "control", "action": "banana"}, loop, pf
        )
        assert loop.clock.speed == 4.0


# ---------------------------------------------------------------------------
# K4 提案 §7 验收对表（7-10）— player_impulse 注册 + 处理（M5-K6 施工）
# ---------------------------------------------------------------------------


class TestPlayerImpulse:
    """K4 提案 §2：原未注册 → unknown_type；现注册 + 入站校验 + 乐观 impulse_feedback。"""

    def test_registered_returns_feedback(self, loop: TickLoop, pf: Pathfinder):
        """§7 #7：一帧内回 optimistic impulse_feedback（不 await LLM）。"""
        reply = handle_client_message(
            {"type": "player_impulse", "channel": "control", "text": "去赚钱"},
            loop,
            pf,
        )
        assert reply is not None
        assert reply["type"] == "impulse_feedback"
        assert reply["channel"] == "control"
        assert reply["injected"] is True
        assert reply["cue"] in {"accepted", "hesitation", "complaint", "resistance"}
        assert set(reply["reaction_monologue"].keys()) == {"form", "content"}
        assert reply["reaction_monologue"]["form"] in {"bubble", "thought", "plan"}

    def test_no_longer_unknown_type(self, loop: TickLoop, pf: Pathfinder):
        """§7 #10 回归：注册后不得再回 unknown_type。"""
        reply = handle_client_message(
            {"type": "player_impulse", "channel": "control", "text": "今天不去上工"},
            loop,
            pf,
        )
        assert reply is not None and reply["type"] != "error"
        assert reply.get("code") != "unknown_type"

    def test_too_long_rejected(self, loop: TickLoop, pf: Pathfinder):
        """§7 #8：text > 64 字 → impulse_too_long，message 为戏内文风。"""
        reply = handle_client_message(
            {"type": "player_impulse", "channel": "control", "text": "啊" * 65},
            loop,
            pf,
        )
        assert reply is not None
        assert reply["type"] == "error"
        assert reply["ref"] == "player_impulse"
        assert reply["code"] == "impulse_too_long"
        assert reply["message"] == "话说得太长了，说不清。"

    def test_max_length_text_accepted(self, loop: TickLoop, pf: Pathfinder):
        """64 字整是 schema maxLength 边界，应通过。"""
        reply = handle_client_message(
            {"type": "player_impulse", "channel": "control", "text": "甲" * 64},
            loop,
            pf,
        )
        assert reply is not None and reply["type"] == "impulse_feedback"

    def test_blank_text_rejected(self, loop: TickLoop, pf: Pathfinder):
        """§7 #9：空串/全空白 → bad_impulse（空念头无语义）。"""
        for text in ("", "   ", "\t\n "):
            reply = handle_client_message(
                {"type": "player_impulse", "channel": "control", "text": text},
                loop,
                pf,
            )
            assert reply is not None and reply["code"] == "bad_impulse", f"text={text!r} 应被拒"

    def test_missing_or_non_string_text_rejected(self, loop: TickLoop, pf: Pathfinder):
        """§2.3：text 缺失/非字符串 → bad_impulse。"""
        for payload in ({}, {"text": 42}, {"text": None}, {"text": ["去"]}):
            reply = handle_client_message(
                {"type": "player_impulse", "channel": "control", **payload}, loop, pf
            )
            assert reply is not None and reply["code"] == "bad_impulse", f"{payload} 应被拒"

    def test_preset_non_string_tolerated(self, loop: TickLoop, pf: Pathfinder):
        """§2.3：preset 非 string/null 容忍忽略（前向兼容标签，不阻塞）。"""
        reply = handle_client_message(
            {"type": "player_impulse", "channel": "control", "text": "走走", "preset": 42},
            loop,
            pf,
        )
        assert reply is not None and reply["type"] == "impulse_feedback"

    def test_preset_null_accepted(self, loop: TickLoop, pf: Pathfinder):
        reply = handle_client_message(
            {"type": "player_impulse", "channel": "control", "text": "歇着", "preset": None},
            loop,
            pf,
        )
        assert reply is not None and reply["type"] == "impulse_feedback"

    def test_does_not_touch_world_state(self, loop: TickLoop, pf: Pathfinder):
        """§2.4『不要做的事』：handler 不直接改 Agent 状态（写路径唯一 = apply）。"""
        before = {
            eid: (e.pos, e.path) for eid, e in loop.state.entities.items()
        }
        handle_client_message(
            {"type": "player_impulse", "channel": "control", "text": "我想出门"}, loop, pf
        )
        after = {eid: (e.pos, e.path) for eid, e in loop.state.entities.items()}
        assert before == after

    def test_error_message_is_in_character(self, loop: TickLoop, pf: Pathfinder):
        """anchors-api.md:250 红线：error message 戏内第一人称、无系统措辞。"""
        reply = handle_client_message(
            {"type": "player_impulse", "channel": "control", "text": ""}, loop, pf
        )
        assert reply is not None
        assert reply["code"] == "bad_impulse"
        assert reply["message"]  # 非空
        for banned in ("error", "invalid", "null", "None", "字段", "schema"):
            assert banned not in reply["message"], f"message 不应含系统词 {banned}"


# ---------------------------------------------------------------------------
# K4 提案 §7 验收对表（11-13）— load_anchor 注册 + 会话语义（M5-K6 施工）
# ---------------------------------------------------------------------------


@pytest.fixture()
def anchors() -> set[str]:
    """进程内 anchor id 集（同步查表替身——真实查询走 async DB，见 §3.4 决策注记）。"""
    from sim.api import ws as ws_mod

    ws_mod._ANCHOR_IDS.clear()
    ws_mod._ANCHOR_IDS.update({"9f3c1a7b2e04", "aabbccddeeff"})
    return ws_mod._ANCHOR_IDS


class TestLoadAnchor:
    """K4 提案 §3：原未注册 → unknown_type；现注册 + 失败不断线 + 成功同步快照。"""

    def test_registered_unknown_anchor_returns_load_failed(
        self, loop: TickLoop, pf: Pathfinder, anchors: set[str]
    ):
        """§7 #11：anchor 不存在 → load_failed error 帧（不断线）。"""
        reply = handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": "0123456789ab"},
            loop,
            pf,
        )
        assert reply is not None
        assert reply["type"] == "error"
        assert reply["ref"] == "load_anchor"
        assert reply["code"] == "load_failed"

    def test_bad_anchor_id_shape(self, loop: TickLoop, pf: Pathfinder, anchors: set[str]):
        """§3.3：anchor_id 缺失/非字符串 → bad_anchor。"""
        for payload in ({}, {"anchor_id": 42}, {"anchor_id": None}, {"anchor_id": ["x"]}):
            reply = handle_client_message(
                {"type": "load_anchor", "channel": "session", **payload}, loop, pf
            )
            assert reply is not None and reply["code"] == "bad_anchor", f"{payload} 应被拒"

    def test_underscore_prefix_not_rejected(
        self, loop: TickLoop, pf: Pathfinder, anchors: set[str]
    ):
        """§7 #13 不透明串纪律：anc_ 前缀不特征拒绝，走正常查表 → load_failed。"""
        reply = handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": "anc_01"}, loop, pf
        )
        assert reply is not None
        assert reply["type"] == "error"
        assert reply["code"] == "load_failed"
        assert reply["code"] != "bad_anchor"

    def test_success_returns_full_snapshot(
        self, loop: TickLoop, pf: Pathfinder, anchors: set[str], tile_map: TileMap
    ):
        """§7 #12 + 8.4 定案：短期同步路径复用 snapshot_payload。"""
        from sim.api import ws as ws_mod

        ws_mod._ANCHOR_LOAD_HOOK = lambda _anchor_id: True
        try:
            reply = handle_client_message(
                {"type": "load_anchor", "channel": "session", "anchor_id": "9f3c1a7b2e04"},
                loop,
                pf,
            )
        finally:
            ws_mod._ANCHOR_LOAD_HOOK = None
        assert reply is not None
        assert reply["type"] == "full_snapshot"
        assert set(reply.keys()) == set(snapshot_payload(loop, tile_map).keys())

    def test_hook_failure_returns_load_failed(
        self, loop: TickLoop, pf: Pathfinder, anchors: set[str]
    ):
        """载入执行异常（重放损坏等）→ load_failed，不得炸断 handler。"""
        from sim.api import ws as ws_mod

        def boom(_anchor_id: str) -> bool:
            raise RuntimeError("replay corrupted")

        ws_mod._ANCHOR_LOAD_HOOK = boom
        try:
            reply = handle_client_message(
                {"type": "load_anchor", "channel": "session", "anchor_id": "9f3c1a7b2e04"},
                loop,
                pf,
            )
        finally:
            ws_mod._ANCHOR_LOAD_HOOK = None
        assert reply is not None
        assert reply["type"] == "error"
        assert reply["code"] == "load_failed"

    def test_connection_stays_alive_after_failure(
        self, loop: TickLoop, pf: Pathfinder, anchors: set[str]
    ):
        """§3.3 硬约束：失败后连接可继续收发（不断线）——handler 不抛异常。"""
        first = handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": "ffffffffffff"},
            loop,
            pf,
        )
        assert first is not None and first["type"] == "error"
        second = handle_client_message(
            {"type": "player_impulse", "channel": "control", "text": "还在吗"}, loop, pf
        )
        assert second is not None and second["type"] == "impulse_feedback"

    def test_anc_prefix_id_is_opaque_not_validated(
        self, loop: TickLoop, pf: Pathfinder, anchors: set[str]
    ):
        """§6.5：anchor_id 是不透明串——合法集里的项不得因形状被拒。"""
        from sim.api import ws as ws_mod

        ws_mod._ANCHOR_LOAD_HOOK = lambda _anchor_id: True
        try:
            for odd in ("anc_01", "not-a-hex-at-all", "", "x" * 200):
                reply = handle_client_message(
                    {"type": "load_anchor", "channel": "session", "anchor_id": odd}, loop, pf
                )
                assert reply is not None
                if odd == "":
                    assert reply["code"] == "bad_anchor"  # 空串归 bad_anchor（缺失同义）
                    continue
                assert reply["type"] == "full_snapshot", f"{odd!r} 不得因形状被拒"
        finally:
            ws_mod._ANCHOR_LOAD_HOOK = None


# ---------------------------------------------------------------------------
# K4 提案 §7 验收对表（15-18）— error code 词表 + 注册成对（M5-K6 施工）
# ---------------------------------------------------------------------------


class TestErrorCodeVocabulary:
    """§5.1 / 8.8：code 一律小写 snake，且 ∈ 词表。"""

    #: 提案 §5.1 全量词表（10 项）
    VOCABULARY: frozenset[str] = frozenset(
        {
            "unknown_type",
            "bad_channel",
            "auth_error",
            "bad_action",
            "bad_speed",
            "bad_impulse",
            "impulse_too_long",
            "bad_anchor",
            "load_failed",
            "bad_target",
        }
    )

    def _codes(self) -> set[str]:
        """直接取 ws 模块的 code 常量（防词表与实现脱节）。"""
        from sim.api import ws as ws_mod

        found = {
            v for k, v in vars(ws_mod).items() if k.startswith("_ERROR_") and isinstance(v, str)
        }
        assert found, "应至少解析出若干 code"
        return found

    def test_codes_are_subset_of_vocabulary(self):
        assert self._codes() <= self.VOCABULARY, f"越界 code：{self._codes() - self.VOCABULARY}"

    def test_codes_all_lowercase_snake(self):
        for code in self._codes():
            assert code == code.lower(), f"{code} 含大写——违反 8.8"

    def test_every_reply_path_code_in_vocabulary(
        self, loop: TickLoop, pf: Pathfinder, anchors: set[str]
    ):
        """运行时逐个触发所有 error 路径，断言 code 在词表内。"""
        triggers = [
            {"type": "nosuch", "channel": "x"},
            {"type": "sync_request", "channel": "control"},
            {"type": "move_request", "channel": "control"},
            {"type": "set_control", "channel": "control", "action": "nope"},
            {"type": "set_control", "channel": "control", "action": "set_speed", "speed": 8},
            {"type": "player_impulse", "channel": "control", "text": ""},
            {"type": "player_impulse", "channel": "control", "text": "长" * 65},
            {"type": "load_anchor", "channel": "session"},
            {"type": "load_anchor", "channel": "session", "anchor_id": "000000000000"},
            {"type": "move_request", "channel": "render", "target_x": "8", "target_y": 4},
        ]
        for raw in triggers:
            reply = handle_client_message(raw, loop, pf)
            assert reply is not None, f"{raw['type']} 不得静默"
            assert reply["type"] == "error", f"{raw} 应回 error（得 {reply.get('type')}）"
            assert reply["code"] in self.VOCABULARY, f"{raw} code={reply['code']} 越界"


class TestDispatchRegistration:
    """§7 #18：C→S 五类消息在白名单与 channel 表成对注册（防落单 → bad_channel）。"""

    def test_all_client_types_paired(self):
        from sim.api import ws as ws_mod

        allowed = ws_mod._ALLOWED_CLIENT_TYPES
        channels = ws_mod._CHANNEL_FOR
        expected = {"move_request", "set_control", "sync_request", "hello"}
        expected |= {"player_impulse", "load_anchor"}
        assert allowed == expected, f"白名单缺项：{expected - allowed}"
        assert channels.keys() == expected, "channel 表与白名单必须一一对应（防 §2.2 落单）"

    def test_known_channels(self):
        from sim.api import ws as ws_mod

        ch = ws_mod._CHANNEL_FOR
        assert ch["player_impulse"] == "control"
        assert ch["load_anchor"] == "session"
        assert ch["move_request"] == "render"
        assert ch["set_control"] == "control"
        assert ch["sync_request"] == "session"
        assert ch["hello"] == "session"


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
