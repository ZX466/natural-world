"""Protocol 1.16 locomotion contract; OpenAPI generation never starts the app."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

SNAPSHOT = Path(__file__).resolve().parents[2] / "shared" / "openapi.json"


@pytest.fixture(params=("live", "snapshot"))
def schemas(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    if request.param == "snapshot":
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))["components"]["schemas"]
    from sim.api.main import app
    from sim.api.openapi_ext import install

    monkeypatch.setattr(app, "openapi_schema", None)
    install()
    return app.openapi()["components"]["schemas"]


def test_jump_request_has_only_target_and_optional_gait(schemas: dict[str, Any]) -> None:
    assert "JumpRequestMessage" in schemas
    request = schemas["JumpRequestMessage"]
    assert request["additionalProperties"] is False
    assert set(request["required"]) == {"v", "ws_seq", "channel", "type", "target_x", "target_y"}
    props = request["properties"]
    assert set(props) == {"v", "ws_seq", "channel", "type", "target_x", "target_y", "gait"}
    assert props["channel"]["enum"] == ["render"]
    assert props["type"]["enum"] == ["jump_request"]
    for target in ("target_x", "target_y"):
        assert props[target]["type"] == "integer"
        assert props[target]["minimum"] == 0
    assert props["gait"]["type"] == "string"
    assert props["gait"]["enum"] == ["walk", "run"]
    assert "walk" in props["gait"]["description"]


def test_move_request_preserves_legacy_omission(schemas: dict[str, Any]) -> None:
    request = schemas["MoveRequestMessage"]
    assert "gait" in request["properties"]
    assert request["properties"]["gait"]["enum"] == ["walk", "run"]
    assert "gait" not in request["required"]
    assert "default" not in request["properties"]["gait"]


@pytest.mark.parametrize("name", ("Actor", "ActorDelta"))
def test_actor_locomotion_is_optional_and_jump_can_be_cleared(
    schemas: dict[str, Any], name: str
) -> None:
    schema = schemas[name]
    props = schema["properties"]
    legacy = {"rtoken", "sprite", "x", "y", "facing", "anim", "tint", "name"}
    if name == "ActorDelta":
        legacy.add("op")
    assert set(props) == legacy | {"elevation", "gait", "jump"}
    assert set(schema["required"]) == (
        {"rtoken", "sprite", "x", "y", "facing", "anim"} if name == "Actor" else {"rtoken"}
    )
    assert {"elevation", "gait", "jump"}.isdisjoint(schema["required"])
    assert props["elevation"]["type"] == "integer"
    assert props["elevation"]["minimum"] == 0
    assert props["elevation"]["maximum"] == 3
    assert props["gait"]["enum"] == ["walk", "run"]
    assert props["jump"]["oneOf"] == [{"$ref": "#/components/schemas/JumpVisual"}, {"type": "null"}]
    assert schema["additionalProperties"] is False


def test_jump_visual_is_closed_and_bounded_without_internal_time(schemas: dict[str, Any]) -> None:
    assert "JumpVisual" in schemas
    schema = schemas["JumpVisual"]
    fields = {
        "rtoken",
        "start_x",
        "start_y",
        "goal_x",
        "goal_y",
        "start_height",
        "target_height",
        "progress",
        "active",
        "duration",
        "arc_height",
    }
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(schema["required"]) == fields
    props = schema["properties"]
    assert props["rtoken"]["type"] == "string"
    for field in ("start_x", "start_y", "goal_x", "goal_y"):
        assert props[field]["type"] == "integer"
        assert props[field]["minimum"] == 0
    for field in ("start_height", "target_height"):
        assert props[field] == {"type": "integer", "minimum": 0, "maximum": 3}
    assert props["progress"] == {"type": "number", "minimum": 0, "maximum": 1}
    assert props["active"] == {"type": "boolean"}
    for field, maximum in (("duration", 4), ("arc_height", 2)):
        assert props[field]["type"] == "number"
        assert props[field]["exclusiveMinimum"] == 0
        assert props[field]["maximum"] == maximum


def test_jump_request_is_in_the_discriminated_union(schemas: dict[str, Any]) -> None:
    union = schemas["WsMessage"]
    ref = "#/components/schemas/JumpRequestMessage"
    assert {"$ref": ref} in union["oneOf"]
    assert union["discriminator"]["mapping"]["jump_request"] == ref
    # Reserved perception retains its frozen shape and union membership.
    assert union["discriminator"]["mapping"]["perception"] == (
        "#/components/schemas/PerceptionMessage"
    )


def test_locomotion_live_schemas_match_the_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    from sim.api.main import app
    from sim.api.openapi_ext import install

    monkeypatch.setattr(app, "openapi_schema", None)
    install()
    live = app.openapi()["components"]["schemas"]
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["components"]["schemas"]
    for name in (
        "MoveRequestMessage",
        "JumpRequestMessage",
        "Actor",
        "ActorDelta",
        "JumpVisual",
        "WsMessage",
    ):
        assert name in live and name in snapshot
        assert live[name] == snapshot[name], name
