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


@pytest.fixture()
def client():
    reset_ws_auth_token()
    with TestClient(app) as c:
        yield c
    reset_ws_auth_token()


class TestW6Auth:
    def test_no_token_rejected(self, client: TestClient):
        """无 token 的 hello → auth_error。"""
        with client.websocket_connect("/ws") as ws:
            greeting = ws.receive_json()
            assert greeting["type"] == "full_snapshot"  # 快照仍下发（只读）
            ws.send_json({"type": "hello", "channel": "session"})
            reply = ws.receive_json()
            assert reply["type"] == "error" and reply["code"] == "auth_error"

    def test_wrong_token_rejected(self, client: TestClient):
        """错 token → auth_error（不透露原因细节）。"""
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"type": "hello", "channel": "session", "token": "fake-token"})
            reply = ws.receive_json()
            assert reply["code"] == "auth_error"

    def test_valid_token_accepted(self, client: TestClient):
        """合法 token → hello_ack。"""
        token = ws_auth_token()
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"type": "hello", "channel": "session", "token": token})
            reply = ws.receive_json()
            assert reply["type"] == "hello_ack"

    def test_non_browser_connection_allowed(self, client: TestClient):
        """无 Origin 头（同机直连 / 测试客户端）→ 放行。"""
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "full_snapshot"

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
            assert ws.receive_json()["type"] == "full_snapshot"
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
            ws.receive_json()
            ws.send_json({"type": "hello", "channel": "session", "token": token})
            assert ws.receive_json()["type"] == "hello_ack"
            ws.send_json({"type": "evil_action", "channel": "render"})
            reply = ws.receive_json()
            assert reply["type"] == "error" and reply["code"] == "unknown_type"
