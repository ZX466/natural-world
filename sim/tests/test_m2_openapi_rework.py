"""M2-A2 第四项：openapi_ext 对齐快照返工验收（kilo K3 清单施工，2026-09-22）。

判据（docs/api/ws-message-diff.md §4.1）：本机生成物与 shared/openapi.json 结构
diff 归零（白名单外）。本文件把 K3 清单的关键差异逐条锁进测试，作为返工的
RED 基线；kilo 复验用其私有 diff 脚本做全量对账，两口径互补。

- 17 个缺失子 schema 进 components.schemas（§2.1 #1-#17）
- 61 处字段级差异归零：ADD/DEL/MOD（§1.1-§1.5）
- 4 处 channel 错值归零（§1.6）
- ext 侧 nullable 计数 = 0（§3.2 自检线）
- 信封 v 无 description（§1.7，1 行消 14 处）
- HTTP response_model：health=HealthStatus、world_map=WorldMapResponse（§2.1 #15/#16）
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

ADDED_SCHEMAS: frozenset[str] = frozenset(
    {
        "Actor",
        "ActorDelta",
        "Light",
        "LightDelta",
        "Structure",
        "StructureDelta",
        "Weather",
        "MapInfo",
        "RToken",
        "Facing",
        "CombatInfo",
        "Projectile",
        "Hit",
        "MonologueReaction",
        "HealthStatus",
        "WorldMapResponse",
        "MapChunk",
    }
)


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LZ_MASTER_KEY", Fernet.generate_key().decode())
    import sim.api.settings as settings_mod

    settings_mod._profile_store = settings_mod.ProfileStore(f"sqlite:///{tmp_path}/settings.db")
    from sim.api.main import app

    with TestClient(app) as c:
        yield c
    settings_mod._profile_store = None


@pytest.fixture()
def schemas(client: TestClient) -> dict:
    return client.get("/openapi.json").json()["components"]["schemas"]


class TestSubSchemasAdded:
    """§2.1 #1-#17：17 个子 schema 全部进 components.schemas。"""

    def test_17_schemas_present(self, schemas: dict) -> None:
        missing = ADDED_SCHEMAS - set(schemas)
        assert not missing, f"缺失: {sorted(missing)}"

    def test_rtoken_opaque_shape(self, schemas: dict) -> None:
        """RToken = type string + description（不透明替身，9 处引用的公共叶）。"""
        rt = schemas["RToken"]
        assert rt["type"] == "string"
        assert "description" in rt

    def test_facing_enum(self, schemas: dict) -> None:
        assert schemas["Facing"] == {"type": "string", "enum": ["n", "e", "s", "w"]}

    def test_actor_required_six_via_ref(self, schemas: dict) -> None:
        """Actor: required 6 字段，rtoken/facing 走 $ref（§2.1 #1）。"""
        actor = schemas["Actor"]
        assert set(actor["required"]) == {"rtoken", "sprite", "x", "y", "facing", "anim"}
        assert actor["properties"]["rtoken"] == {"$ref": "#/components/schemas/RToken"}
        assert actor["properties"]["facing"] == {"$ref": "#/components/schemas/Facing"}
        assert actor["properties"]["tint"] == {"type": "integer"}

    def test_delta_required_only_rtoken(self, schemas: dict) -> None:
        """ActorDelta/LightDelta/StructureDelta：required 仅 rtoken（增量语义）。"""
        for name in ("ActorDelta", "LightDelta", "StructureDelta"):
            assert schemas[name]["required"] == ["rtoken"], name

    def test_actor_delta_has_op(self, schemas: dict) -> None:
        """ActorDelta.op:enum[add,remove]（§4.1 缺省视为 update——协议契约不能省）。"""
        op = schemas["ActorDelta"]["properties"]["op"]
        assert op["type"] == "string"
        assert op["enum"] == ["add", "remove"]

    def test_health_status_shape(self, schemas: dict) -> None:
        hs = schemas["HealthStatus"]
        assert set(hs["required"]) == {"status", "world_running", "in_combat"}
        assert hs["properties"]["status"]["enum"] == ["ok"]

    def test_world_map_response_shape(self, schemas: dict) -> None:
        wm = schemas["WorldMapResponse"]
        assert set(wm["required"]) == {"w", "h", "tileset", "chunks"}
        assert wm["properties"]["chunks"]["items"] == {
            "$ref": "#/components/schemas/MapChunk"
        }
        chunk = schemas["MapChunk"]
        assert set(chunk["required"]) == {"cx", "cy", "collision_b64"}


class TestWsMemberFieldDiffs:
    """§1.1-§1.5：WS 成员字段级差异归零。"""

    def test_full_snapshot_refs_and_combat_optional(self, schemas: dict) -> None:
        """§1.1：五集合 $ref 化 + combat 改 oneOf-null 并移出 required。"""
        full = schemas["FullSnapshotMessage"]
        props = full["properties"]
        assert props["actors"]["items"] == {"$ref": "#/components/schemas/Actor"}
        assert props["lights"]["items"] == {"$ref": "#/components/schemas/Light"}
        assert props["structures"]["items"] == {"$ref": "#/components/schemas/Structure"}
        assert props["map"] == {"$ref": "#/components/schemas/MapInfo"}
        assert props["weather"] == {"$ref": "#/components/schemas/Weather"}
        assert props["combat"] == {
            "oneOf": [
                {"$ref": "#/components/schemas/CombatInfo"},
                {"type": "null"},
            ]
        }
        assert "combat" not in full["required"]
        assert set(full["required"]) == {
            "v", "ws_seq", "channel", "type",
            "map", "lights", "actors", "structures", "weather",
        }

    def test_state_delta_refs_and_optionals(self, schemas: dict) -> None:
        """§1.2：ActorDelta $ref + lights/structures/weather 补 optional。"""
        delta = schemas["StateDeltaMessage"]
        props = delta["properties"]
        assert props["actors"]["items"] == {"$ref": "#/components/schemas/ActorDelta"}
        assert props["lights"]["items"] == {"$ref": "#/components/schemas/LightDelta"}
        assert props["structures"]["items"] == {"$ref": "#/components/schemas/StructureDelta"}
        assert props["weather"] == {"$ref": "#/components/schemas/Weather"}
        assert set(delta["required"]) == {"v", "ws_seq", "channel", "type", "actors"}

    def test_perception_form_added_subject_deleted(self, schemas: dict) -> None:
        """§1.3/§3.1：form 补（oneOf-null 形），subject 整字段删除。"""
        per = schemas["PerceptionMessage"]
        assert "subject" not in per["properties"]
        assert per["properties"]["form"] == {
            "oneOf": [
                {"type": "string", "enum": ["bubble", "thought", "plan"]},
                {"type": "null"},
            ]
        }

    def test_monologue_form_required_reaction_deleted(self, schemas: dict) -> None:
        """§1.4：form 补 + 进 required；reaction 整字段删除（W7 字段最小化）。"""
        mono = schemas["MonologueMessage"]
        assert "reaction" not in mono["properties"]
        assert mono["properties"]["form"] == {
            "type": "string", "enum": ["bubble", "thought", "plan"]
        }
        assert "form" in mono["required"]

    def test_impulse_feedback_new_fields(self, schemas: dict) -> None:
        """§1.5：accepted/content 删；injected/cue/reaction_monologue 补 + required。"""
        fb = schemas["ImpulseFeedbackMessage"]
        props = fb["properties"]
        assert "accepted" not in props and "content" not in props
        assert props["injected"] == {"type": "boolean"}
        assert props["cue"]["enum"] == ["accepted", "hesitation", "complaint", "resistance"]
        assert props["reaction_monologue"] == {
            "$ref": "#/components/schemas/MonologueReaction"
        }
        assert set(fb["required"]) == {
            "v", "ws_seq", "channel", "type", "injected", "cue", "reaction_monologue",
        }

    def test_combat_event_fields_replaced(self, schemas: dict) -> None:
        """§1.5：kind/attacker/defender 删；exchange/rtoken/posture_visual/exchange_resolved。"""
        ce = schemas["CombatEventMessage"]
        props = ce["properties"]
        assert not {"kind", "attacker", "defender"} & set(props)
        assert props["exchange"]["minimum"] == 0
        assert props["rtoken"] == {"$ref": "#/components/schemas/RToken"}
        assert props["projectiles"]["items"] == {"$ref": "#/components/schemas/Projectile"}
        assert props["hits"]["items"] == {"$ref": "#/components/schemas/Hit"}
        assert set(ce["required"]) == {
            "v", "ws_seq", "channel", "type",
            "exchange", "rtoken", "posture_visual", "exchange_resolved",
        }

    def test_timescale_mode_active_note_no_rate(self, schemas: dict) -> None:
        """§1.5/§3.1：mode/active 补 + required；note 用 oneOf-null 形；rate 删。"""
        ts = schemas["TimescaleMessage"]
        props = ts["properties"]
        assert "rate" not in props
        assert props["mode"]["enum"] == ["normal", "combat"]
        assert props["active"] == {"type": "boolean"}
        assert props["note"] == {"oneOf": [{"type": "string"}, {"type": "null"}]}
        assert set(ts["required"]) == {"v", "ws_seq", "channel", "type", "mode", "active"}

    def test_control_ack_action_applied_speed(self, schemas: dict) -> None:
        """§1.5：ack_of/ok 删；action/applied/speed 补（ws.py 实发形状）。"""
        ack = schemas["ControlAckMessage"]
        props = ack["properties"]
        assert "ack_of" not in props and "ok" not in props
        assert props["action"]["enum"] == ["pause", "resume", "set_speed"]
        assert props["applied"] == {"type": "boolean"}
        assert props["speed"]["enum"] == [1, 4, 16]
        assert set(ack["required"]) == {"v", "ws_seq", "channel", "type", "action", "applied"}

    def test_sync_request_reason_required(self, schemas: dict) -> None:
        assert schemas["SyncRequestMessage"]["properties"]["reason"] == {"type": "string"}
        assert "reason" in schemas["SyncRequestMessage"]["required"]

    def test_player_impulse_preset_oneof_null(self, schemas: dict) -> None:
        """§3.1：preset 改 oneOf-null 形（ext 侧；快照侧由 kilo 复验前改）。"""
        assert schemas["PlayerImpulseMessage"]["properties"]["preset"] == {
            "oneOf": [{"type": "string"}, {"type": "null"}]
        }

    def test_ws_error_ref_field(self, schemas: dict) -> None:
        """§1.5：ref 字段补齐（string, required；不指 $ref 引用外部 schema）。"""
        err = schemas["WsErrorMessage"]
        assert err["properties"]["ref"] == {"type": "string"}
        assert set(err["required"]) == {
            "v", "ws_seq", "channel", "type", "ref", "code", "message",
        }


class TestChannelFixes:
    """§1.6：4 处 channel 错值归零。"""

    @pytest.mark.parametrize(
        ("member", "channel"),
        [
            ("MoveRequestMessage", "render"),
            ("TimescaleMessage", "control"),
            ("ControlAckMessage", "control"),
            ("ImpulseFeedbackMessage", "control"),
        ],
    )
    def test_channel_values(self, schemas: dict, member: str, channel: str) -> None:
        assert schemas[member]["properties"]["channel"]["enum"] == [channel]


class TestEnvelopeAndNullable:
    """§1.7 信封 v description + §3.2 nullable 自检线。"""

    def test_envelope_v_has_no_description(self, schemas: dict) -> None:
        """§1.7：14 成员的 v 均无 description（推荐动作①：删 ext 侧）。"""
        members = [
            n
            for n, s in schemas.items()
            if (n.endswith("Message") and "properties" in s) or n == "WsErrorMessage"
        ]
        assert len(members) >= 14  # 14 成员全体在内（WsMessage 联合体无 properties，不查）
        for name in members:
            assert "description" not in schemas[name]["properties"]["v"], name

    def test_no_nullable_keyword_anywhere(self, schemas: dict) -> None:
        """§3.2 自检：ext 生成物中 nullable 关键字计数 = 0（当前 5 处）。"""

        def walk(node: object) -> int:
            if isinstance(node, dict):
                return int("nullable" in node) + sum(walk(v) for v in node.values())
            if isinstance(node, list):
                return sum(walk(v) for v in node)
            return 0

        assert walk(schemas) == 0


class TestHttpRoutes:
    """§2.1 #15/#16：HTTP 路由挂 response_model。"""

    def test_health_response_ref(self, client: TestClient) -> None:
        schema = client.get("/openapi.json").json()
        ref = schema["paths"]["/api/health"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert ref == {"$ref": "#/components/schemas/HealthStatus"}

    def test_world_map_response_ref(self, client: TestClient) -> None:
        schema = client.get("/openapi.json").json()
        ref = schema["paths"]["/api/world/map"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert ref == {"$ref": "#/components/schemas/WorldMapResponse"}

    def test_health_endpoint_runtime_shape(self, client: TestClient) -> None:
        """response_model 不改运行时白名单（回归锚：health 实发 3 字段）。"""
        body = client.get("/api/health").json()
        assert set(body) == {"status", "world_running", "in_combat"}

    def test_world_map_endpoint_runtime_shape(self, client: TestClient) -> None:
        body = client.get("/api/world/map").json()
        assert set(body) == {"w", "h", "tileset", "chunks"}
        assert set(body["chunks"][0]) == {"cx", "cy", "collision_b64"}


class TestRegression:
    """既有锚不回退（test_openapi_ext.py 8 用例的承重断言子集）。"""

    def test_ws_union_14_members_intact(self, schemas: dict) -> None:
        union = schemas["WsMessage"]
        assert len(union["oneOf"]) == 14
        assert len(union["discriminator"]["mapping"]) == 14

    def test_snapshot_required_now_matches_k3(self, schemas: dict) -> None:
        """旧锚（combat 在 required）被 K3 推翻：required 不再含 combat。"""
        snap = schemas["FullSnapshotMessage"]
        assert "combat" not in snap["required"]
        assert set(snap["properties"]) == {
            "v", "ws_seq", "channel", "type",
            "map", "lights", "actors", "structures", "weather", "combat",
        }
