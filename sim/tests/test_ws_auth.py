"""W6 WS 鉴权测试 — M1 前置项（codex M0 终审裁定 → TASK-004 实施）。

口径（对应 m1-checklist W6）：
- 无 token / 错 token → hello 得 auth_error，且此后消息仍需鉴权门；
- 伪 Origin（非白名单）→ 握手层直接 close(4003)；
- 合法 token + 合法 Origin → 揥入、快照下发、hello_ack；
- token 比对用 hmac.compare_digest（时序侧信道防护）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from sim.api.main import app
from sim.api.ws import reset_ws_auth_token, ws_auth_token


def _greet(ws) -> None:
    """接入问候两帧：全量快照 + session_state 初值帧（M5-K3 / 裁 21-A D-5+D-6）。

    鉴权门管的是**命令**消息，接入问候不入门（只读）。本组用例断言的是命令回复，
    故先把两帧问候消费掉。
    """
    assert ws.receive_json()["type"] == "full_snapshot"
    assert ws.receive_json()["type"] == "session_state"


def _command_reply(ws):
    # 世界广播与命令回执共用连接；只跳过表现帧，不把它们误当回执。
    for _ in range(50):
        frame = ws.receive_json()
        if frame["type"] in {"error", "hello_ack", "control_ack"}:
            return frame
    raise AssertionError("no command reply received")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr("sim.api.main._active_profile_snapshot_provider", lambda: lambda: None)
    reset_ws_auth_token()
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as c:
        yield c
    reset_ws_auth_token()


class TestW6Auth:
    @pytest.mark.parametrize(
        "command",
        [
            {"type": "move_request", "channel": "render", "target_x": 8, "target_y": 4},
            {"type": "set_control", "channel": "control", "action": "pause"},
            {"type": "player_impulse", "channel": "control", "text": "去街上看看。"},
            {"type": "load_anchor", "channel": "session", "anchor_id": "missing"},
        ],
    )
    def test_commands_without_hello_are_rejected(self, client, command):
        with client.websocket_connect("/ws") as ws:
            _greet(ws)
            ws.send_json(command)
            reply = ws.receive_json()
            assert reply["type"] == "error"
            assert reply["code"] == "auth_error"
            assert reply["ref"] == command["type"]

    def test_bad_hello_cannot_unlock_commands(self, client):
        with client.websocket_connect("/ws") as ws:
            _greet(ws)
            ws.send_json({"type": "hello", "channel": "session", "token": "invalid"})
            assert ws.receive_json()["code"] == "auth_error"
            ws.send_json({"type": "set_control", "channel": "control", "action": "pause"})
            assert ws.receive_json()["code"] == "auth_error"

    def test_http_token_unlocks_only_the_authenticated_connection(self, client):
        response = client.get("/api/ws-token", headers={"origin": "http://localhost:5173"})
        assert response.status_code == 200
        assert set(response.json()) == {"token"}
        assert response.headers["cache-control"] == "no-store"
        with client.websocket_connect("/ws") as ws:
            _greet(ws)
            ws.send_json({"type": "hello", "channel": "session", **response.json()})
            assert ws.receive_json()["type"] == "hello_ack"
            ws.send_json({"type": "set_control", "channel": "control", "action": "pause"})
            assert _command_reply(ws)["type"] == "control_ack"
            with client.websocket_connect("/ws") as other:
                _greet(other)
                other.send_json({"type": "set_control", "channel": "control", "action": "pause"})
                assert other.receive_json()["code"] == "auth_error"

    @pytest.mark.parametrize(
        "headers",
        [
            {"origin": "https://evil.example"},
            {"host": "evil.example"},
            {"origin": "null"},
        ],
    )
    def test_token_route_rejects_untrusted_origin_or_host(self, client, headers):
        assert client.get("/api/ws-token", headers=headers).status_code == 403

    def test_no_token_rejected(self, client: TestClient):
        """无 token 的 hello → auth_error。"""
        with client.websocket_connect("/ws") as ws:
            _greet(ws)  # 快照仍下发（只读）
            ws.send_json({"type": "hello", "channel": "session"})
            reply = ws.receive_json()
            assert reply["type"] == "error" and reply["code"] == "auth_error"

    def test_wrong_token_rejected(self, client: TestClient):
        """错 token → auth_error（不透露原因细节）。"""
        with client.websocket_connect("/ws") as ws:
            _greet(ws)
            ws.send_json({"type": "hello", "channel": "session", "token": "fake-token"})
            reply = ws.receive_json()
            assert reply["code"] == "auth_error"

    def test_valid_token_accepted(self, client: TestClient):
        """合法 token → hello_ack。"""
        token = ws_auth_token()
        with client.websocket_connect("/ws") as ws:
            _greet(ws)
            ws.send_json({"type": "hello", "channel": "session", "token": token})
            reply = ws.receive_json()
            assert reply["type"] == "hello_ack"

    def test_non_browser_connection_allowed(self, client: TestClient):
        """无 Origin 头（同机直连 / 测试客户端）→ 放行。"""
        with client.websocket_connect("/ws") as ws:
            _greet(ws)

    def test_spoofed_origin_rejected(self):
        """伪 Origin（恶意网页）→ 揥手层 close 4003。"""
        reset_ws_auth_token()
        with (
            TestClient(app) as c,
            pytest.raises(WebSocketDisconnect),
            c.websocket_connect("/ws", headers={"origin": "http://evil.example"}) as ws,
        ):
            ws.receive_json()
        reset_ws_auth_token()

    def test_legit_origin_accepted(self):
        """白名单 Origin（Vite dev）→ 接入正常。"""
        reset_ws_auth_token()
        with (
            TestClient(app) as c,
            c.websocket_connect("/ws", headers={"origin": "http://localhost:5173"}) as ws,
        ):
            _greet(ws)
        reset_ws_auth_token()

    def test_token_stable_within_process(self, client: TestClient):
        """同进程 token 不变（避免运行期失效）。"""
        t1 = ws_auth_token()
        t2 = ws_auth_token()
        assert t1 == t2 and len(t1) >= 32

    def test_hello_after_auth_still_gated(self, client: TestClient):
        """鉴权通过后仍受消息门禁（鉴权不提权）。"""
        token = ws_auth_token()
        with client.websocket_connect("/ws") as ws:
            _greet(ws)
            ws.send_json({"type": "hello", "channel": "session", "token": token})
            assert ws.receive_json()["type"] == "hello_ack"
            ws.send_json({"type": "evil_action", "channel": "render"})
            reply = ws.receive_json()
            assert reply["type"] == "error" and reply["code"] == "unknown_type"
