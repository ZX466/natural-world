"""Additive 1.14 schemas and authenticated live voxel-state delivery."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from sim.api import main

ROOT = Path(__file__).resolve().parents[2]


def test_voxel_schemas_match_the_snapshot_without_replacing_the_legacy_source():
    snapshot = json.loads((ROOT / "shared/openapi.json").read_text(encoding="utf8"))
    live = main.app.openapi()
    assert snapshot["info"]["version"] == "1.14"
    names = ("VoxelEdit", "VoxelDig", "VoxelInventory", "VoxelRequestMessage", "VoxelStateMessage")
    for name in names:
        assert live["components"]["schemas"][name] == snapshot["components"]["schemas"][name]
        assert snapshot["components"]["schemas"][name]["additionalProperties"] is False
    for message in ("FullSnapshotMessage", "StateDeltaMessage"):
        schema = snapshot["components"]["schemas"][message]
        assert "voxel_edits" in schema["properties"]
        assert "voxel_edits" not in schema["required"]
    union = snapshot["components"]["schemas"]["WsMessage"]
    assert union["discriminator"]["mapping"]["voxel_state"].endswith("/VoxelStateMessage")
    assert union["discriminator"]["mapping"]["voxel_request"].endswith("/VoxelRequestMessage")


def receive_until(socket, wanted):
    seen = []
    for _ in range(80):
        frame = socket.receive_json()
        seen.append(frame)
        if frame["type"] == wanted:
            return frame, seen
    raise AssertionError(f"missing frame {wanted}")


def test_real_websocket_requires_hello_before_inventory_or_edits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with (
        TestClient(main.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client,
        client.websocket_connect("/ws", headers={"origin": "http://127.0.0.1:5173"}) as socket,
    ):
        socket.send_json(
            {"type": "voxel_request", "channel": "render", "action": "place", "x": 100, "y": 53}
        )
        error, before = receive_until(socket, "error")
        assert error["code"] == "auth_error"
        assert not any(frame["type"] == "voxel_state" for frame in before)
        credentials = client.get(
            "/api/ws-token", headers={"origin": "http://127.0.0.1:5173"}
        ).json()
        socket.send_json({"type": "hello", "channel": "session", "token": credentials["token"]})
        receive_until(socket, "hello_ack")
        state, _ = receive_until(socket, "voxel_state")
        assert state["v"] == "1.14"
        assert state["inventory"] == {"earth": 0, "stone": 0, "wood": 0}
        assert state["dig"] is None
        assert main.app.state.voxel_runtime.snapshot()["inventory"]["earth"] == 0
