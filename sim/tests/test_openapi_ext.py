"""OpenAPI 补全测试 — M2-K1 改写验收（kilo 发现 1/2/4/5 采纳，2026-09-21）。

- settings 路由带 response_model（ProfileListItem 进 components）
- WS 消息 14 成员 + WsMessage oneOf 联合进 **components.schemas**
  （旧 components.wsMessages 私有扩展已废除——openapi-typescript 不读）
- WsFullSnapshot required 与 ws.snapshot_payload 实际输出一致（防漂移锚）
- discriminator.mapping 全覆盖（--src 全量生成的前置断言）
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

#: 14 成员（type 判别值 → schema 名）；hello/hello_ack 故意不进（W6 安全裁决）。
EXPECTED_MEMBERS: dict[str, str] = {
    "player_impulse": "PlayerImpulseMessage",
    "set_control": "SetControlMessage",
    "load_anchor": "LoadAnchorMessage",
    "move_request": "MoveRequestMessage",
    "sync_request": "SyncRequestMessage",
    "full_snapshot": "FullSnapshotMessage",
    "state_delta": "StateDeltaMessage",
    "perception": "PerceptionMessage",
    "monologue": "MonologueMessage",
    "impulse_feedback": "ImpulseFeedbackMessage",
    "combat_event": "CombatEventMessage",
    "timescale": "TimescaleMessage",
    "control_ack": "ControlAckMessage",
    "error": "WsErrorMessage",
}


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

    def test_ws_union_in_schemas_14_members(self, client: TestClient):
        """WsMessage oneOf 联合在 components.schemas（kilo 发现 1/2 采纳）。"""
        schema = client.get("/openapi.json").json()
        schemas = schema["components"]["schemas"]
        ws = schemas["WsMessage"]
        refs = {r["$ref"].rsplit("/", 1)[-1] for r in ws["oneOf"]}
        assert refs == set(EXPECTED_MEMBERS.values())
        # 旧私有扩展不再注入（openapi-typescript 不读，防两处真相）
        assert "wsMessages" not in schema["components"]

    def test_discriminator_mapping_covers_all(self, client: TestClient):
        """discriminator.type mapping 14 键全覆盖且指向正确成员（--src 全量生成前置）。"""
        schema = client.get("/openapi.json").json()
        mapping = schema["components"]["schemas"]["WsMessage"]["discriminator"]["mapping"]
        assert set(mapping.keys()) == set(EXPECTED_MEMBERS.keys())
        for type_val, schema_name in EXPECTED_MEMBERS.items():
            assert mapping[type_val] == f"#/components/schemas/{schema_name}"

    def test_each_member_channel_and_type(self, client: TestClient):
        """每成员自带 channel enum + type enum（信封字段下沉到成员——联合收窄可用）。"""
        schema = client.get("/openapi.json").json()
        schemas = schema["components"]["schemas"]
        for type_val, name in EXPECTED_MEMBERS.items():
            member = schemas[name]
            assert member["properties"]["type"]["enum"] == [type_val], name
            assert "channel" in member["properties"], name

    def test_ws_request_body_schemas_registered(self, client: TestClient):
        """HTTP 请求体 schema（ProfileCreate/Update）照旧在位（kilo 契约 4 件套）。"""
        schema = client.get("/openapi.json").json()
        components = schema["components"]["schemas"]
        assert "ProfileCreate" in components
        assert "ProfileUpdate" in components

    def test_snapshot_schema_matches_payload(self, client: TestClient):
        """FullSnapshotMessage required 与快照一致（防漂移锚）。

        K3 修正（ws-message-diff.md §1.1）：combat 是 optional（oneOf CombatInfo/null），
        不再进 required——旧锚（combat ∈ required）随 K3 返工推翻。
        """
        schema = client.get("/openapi.json").json()
        snap = schema["components"]["schemas"]["FullSnapshotMessage"]
        assert set(snap["required"]) == {
            "v",
            "ws_seq",
            "channel",
            "type",
            "map",
            "lights",
            "actors",
            "structures",
            "weather",
        }
        assert snap["properties"]["type"]["enum"] == ["full_snapshot"]
        assert snap["properties"]["combat"]["oneOf"] == [
            {"$ref": "#/components/schemas/CombatInfo"},
            {"type": "null"},
        ]

    def test_error_member_keeps_ref_field(self, client: TestClient):
        """error 消息保留 ref 字段（K3 附注 2 修正：「无 ref」指不用 $ref 引外部
        schema，字段本身要保留——ws-protocol.md §4.5 有它；required 含 ref）。"""
        schema = client.get("/openapi.json").json()
        err = schema["components"]["schemas"]["WsErrorMessage"]
        assert err["properties"]["ref"] == {"type": "string"}
        assert "ref" in err["required"]

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
