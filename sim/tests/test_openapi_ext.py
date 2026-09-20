"""OpenAPI 补全测试 — kilo K03 差异回写验收（2026-09-20）。

- settings 路由带 response_model（ProfileListItem 进 components）
- WS components 注入（serverToClient / clientToServer）
- gen-protocol 可全量生成（/openapi.json 含全部 4 请求体 + WS 消息）
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LZ_MASTER_KEY", Fernet.generate_key().decode())
    import sim.api.settings as settings_mod

    settings_mod._profile_store = settings_mod.ProfileStore(f"sqlite:///{tmp_path}/settings.db")
    from sim.api.main import app

    with TestClient(app) as c:
        yield c
    settings_mod._profile_store = None


class TestOpenApiExt:
    def test_profile_list_item_in_components(self, client: TestClient):
        schema = client.get("/openapi.json").json()
        components = schema["components"]["schemas"]
        assert "ProfileListItem" in components
        item = components["ProfileListItem"]
        assert set(item["properties"]) == {
            "id",
            "name",
            "base_url",
            "model",
            "temperature",
            "max_tokens",
            "active",
            "api_key_hint",
        }

    def test_ws_components_injected(self, client: TestClient):
        schema = client.get("/openapi.json").json()
        ws = schema["components"]["wsMessages"]
        assert set(ws["serverToClient"]) == {"WsFullSnapshot", "WsStateDelta"}
        assert set(ws["clientToServer"]) == {
            "WsMoveRequest",
            "WsSetControl",
            "WsSyncRequest",
            "WsHello",
        }

    def test_ws_request_body_schemas_registered(self, client: TestClient):
        """HTTP 请求体 schema（ProfileCreate/Update）照旧在位（kilo 契约 4 件套）。"""
        schema = client.get("/openapi.json").json()
        components = schema["components"]["schemas"]
        assert "ProfileCreate" in components
        assert "ProfileUpdate" in components

    def test_snapshot_schema_matches_payload(self, client: TestClient):
        """WsFullSnapshot 的 required 字段与 ws.snapshot_payload 实际输出一致（防漂移锚）。"""
        schema = client.get("/openapi.json").json()
        snap = schema["components"]["wsMessages"]["serverToClient"]["WsFullSnapshot"]
        assert set(snap["required"]) == {"type", "channel", "v", "ws_seq", "actors"}
        assert snap["properties"]["type"]["const"] == "full_snapshot"

    def test_response_model_filters_fields(self, client: TestClient):
        """response_model 生效：API 响应仍是 8 字段白名单（K5 回归锚）。"""
        body = {
            "name": "x",
            "base_url": "https://api.deepseek.com/v1",
            "model": "m",
            "api_key": "sk-test-7777",
        }
        resp = client.post("/api/settings/profiles", json=body)
        assert resp.status_code == 201
        assert set(resp.json().keys()) == {
            "id",
            "name",
            "base_url",
            "model",
            "temperature",
            "max_tokens",
            "active",
            "api_key_hint",
        }
