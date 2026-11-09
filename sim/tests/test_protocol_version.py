"""协议版本断言钉（M5-K14 甲案升 1.1；M6-K2 诊断面进快照升 1.2）

**为什么要有这个文件**：版本号在仓里有**两个落点**——`sim/api/ws.py::_PROTOCOL_VERSION`（真相源）
与 `client/src/net/ws.ts::PROTOCOL_VERSION`（第二落点），而两处各写各的**漂移过一次**
（sim 0.1 / client 0.1，P05 才统一）。本文件把「两处相等」与「不得回退」钉成断言，
让下一次升版不再是靠记忆。

**钉的四条**：
1. **防回退**：sim 常量必须是当前登记版本（升 minor 是登记事件，不是随手改）；
2. **跨树防漂移**：前端常量与 sim 常量**逐字相等**（白盒读 `ws.ts` 源码，不 import TS）；
3. **信封取自常量**：帧构造点（`snapshot_payload` 等）不得硬写 `"1.0"` 这类字面量；
4. **登记一致性**：`versioning.md` §7 必须有当前版本行，既有及新增契约关键词保留。

live OpenAPI 与快照 `info.version` 也必须精确等于当前登记版本；不再仅校验 major。
早期 HTTP 版本未接同源的历史记录保留在 versioning.md，不能作为当前漂移例外。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sim.api.ws import _PROTOCOL_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
WS_TS = REPO_ROOT / "client" / "src" / "net" / "ws.ts"
SNAPSHOT = REPO_ROOT / "shared" / "openapi.json"
VERSIONING = REPO_ROOT / "docs" / "api" / "versioning.md"

#: 当前登记版本；1.17 为既有光源增量补齐新增、更新与移除。
EXPECTED_VERSION = "1.17"

#: 登记在 §7 的 minor 变更关键词（doc 同步钉用，避免「登记与代码各说各话」）。
REGISTERED_MINOR_KEYWORDS = (
    "voxel_request",
    "voxel_state",
    "voxel_edits",
    "fast_forward",
    "/api/anchors/current",
    "PlanDelta",
    "AnchorMaterializationStatus",
    "Actor.name",
    "MonologueMessage.name",
    "jump_request",
    "gait",
    "elevation",
    "JumpVisual",
    "LightDelta",
)


def _client_version() -> str:
    src = WS_TS.read_text(encoding="utf-8")
    match = re.search(r"const\s+PROTOCOL_VERSION\s*=\s*'([^']+)'", src)
    assert match is not None, (
        "client/src/net/ws.ts 找不到 PROTOCOL_VERSION 常量（前端版本落点被删？）"
    )
    return match.group(1)


def _registration_section() -> str:
    text = VERSIONING.read_text(encoding="utf-8")
    start = text.index("## 7. 变更登记")
    end = text.index("## 8.", start)
    return text[start:end]


class TestProtocolVersion:
    def test_live_light_lifecycle_schema_matches_snapshot_without_new_required_keys(self):
        from sim.api.main import app

        expected = {
            "type": "object",
            "required": ["rtoken"],
            "properties": {
                "op": {"type": "string", "enum": ["add", "remove"]},
                "rtoken": {"$ref": "#/components/schemas/RToken"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "kind": {"type": "string"},
                "radius": {"type": "number"},
                "flicker": {"type": "number"},
            },
            "additionalProperties": False,
        }
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        assert app.openapi()["components"]["schemas"]["LightDelta"] == expected
        assert snapshot["components"]["schemas"]["LightDelta"] == expected

    def test_live_openapi_version_matches_the_envelope_version(self):
        from sim.api.main import app

        assert app.openapi()["info"]["version"] == EXPECTED_VERSION

    def test_live_inventory_schema_matches_the_authoritative_protocol_snapshot(self):
        from sim.api.main import app

        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        assert (
            app.openapi()["components"]["schemas"]["VoxelInventory"]
            == snapshot["components"]["schemas"]["VoxelInventory"]
        )

    def test_live_full_snapshot_schema_matches_the_authoritative_protocol_snapshot(self):
        from sim.api.main import app

        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        schema = app.openapi()["components"]["schemas"]["FullSnapshotMessage"]
        assert schema == snapshot["components"]["schemas"]["FullSnapshotMessage"]
        assert "monologue_history" not in schema["required"]
        assert schema["properties"]["monologue_history"] == {
            "type": "array",
            "items": {"$ref": "#/components/schemas/MonologueMessage"},
        }

    def test_inventory_schema_adds_optional_materials_without_opening_extra_fields(
        self,
    ):
        schema = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["components"]["schemas"][
            "VoxelInventory"
        ]
        assert schema["required"] == ["earth"]
        assert schema["additionalProperties"] is False
        assert set(schema["properties"]) == {"earth", "stone", "wood"}
        for material in ("earth", "stone", "wood"):
            assert schema["properties"][material]["type"] == "integer"
            assert schema["properties"][material]["minimum"] == 0

    def test_sim_version_is_expected(self) -> None:
        """sim 侧常量为当前登记版本，防止新版字段被按旧契约解析。"""
        assert _PROTOCOL_VERSION == EXPECTED_VERSION, (
            f"协议版本 = {_PROTOCOL_VERSION}，应为 {EXPECTED_VERSION}"
            "——升/降版是登记事件（versioning §7），不是随手改"
        )

    def test_version_shape_is_major_minor(self) -> None:
        """形态是 `major.minor`（无 patch、无前缀）——§1 的版本号模型。"""
        assert re.fullmatch(r"\d+\.\d+", _PROTOCOL_VERSION), (
            f"版本号形态不合 §1（major.minor）：{_PROTOCOL_VERSION}"
        )

    def test_client_version_matches_sim(self) -> None:
        """**跨树防漂移**：前端 `ws.ts` 常量必须与 sim 逐字相等。

        这条是本文件的核心：历史上 sim 0.1 / client 0.1 各写各的，靠人记才修好。
        """
        client = _client_version()
        assert client == _PROTOCOL_VERSION, (
            f"前端 PROTOCOL_VERSION={client} ≠ sim {_PROTOCOL_VERSION}——信封 v 会被对端按错版本解析"
        )

    def test_envelope_uses_constant_not_literal(self) -> None:
        """帧信封 `v` 取自常量（源码级扫描），不是硬写字面量。

        8 = 现有帧构造点数量（full_snapshot / state_delta / monologue / session_state /
        perception / combat / timescale / impulse_feedback）。新增帧却不同步加 `v` ⇒ 此数
        不变 ⇒ 门禁看不出问题；所以这钉盯的是**「不许出现硬写字面量」**这个方向。
        """
        src = (REPO_ROOT / "sim" / "api" / "ws.py").read_text(encoding="utf-8")
        assert '"v": "' not in src, "帧构造点出现硬写的 v 字面量——应统一取 _PROTOCOL_VERSION"
        assert src.count('"v": _PROTOCOL_VERSION') >= 8, (
            "帧构造点的 v 用量少于 8——新增帧时是否漏了信封？"
        )

    def test_snapshot_info_version_matches(self) -> None:
        """Current snapshot, client envelope and live spec use one registered version."""
        info = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["info"]
        assert info.get("version") == EXPECTED_VERSION == _client_version() == _PROTOCOL_VERSION, (
            f"快照 info.version={info.get('version')!r} 与 WS {_PROTOCOL_VERSION} 不同源"
        )


class TestRegistrationSync:
    def test_section7_has_1_1_row(self) -> None:
        """§7 变更登记表必须有当前版本行。"""
        assert f"| {EXPECTED_VERSION} |" in _registration_section(), (
            f"versioning.md §7 缺 {EXPECTED_VERSION} 行——升版必须登记（§7）"
        )

    def test_section7_lists_three_minor_changes(self) -> None:
        """既有与新增 minor 契约关键词都须在登记中可追溯。"""
        section = _registration_section()
        missing = [kw for kw in REGISTERED_MINOR_KEYWORDS if kw not in section]
        assert missing == [], f"§7 登记缺关键词：{missing}"

    def test_section7_minor_row_mentions_commit_hashes(self) -> None:
        """1.1 登记须带 commit hash（可追到具体变更，不靠『大概是那三个』）。

        1.2 行按体例写「commit 见收编落账」（收编时 hash 才定），故本钉只对 1.1 行断言。"""
        section = _registration_section()
        rows = [line for line in section.splitlines() if line.startswith("| 1.1 |")]
        assert rows, "§7 缺 1.1 行"
        hashes = re.findall(r"`([0-9a-f]{7,40})`", rows[0])
        assert len(hashes) >= 3, (
            f"1.1 行只找到 {len(hashes)} 个 commit hash（应 ≥3，对应三个 minor）"
        )


# ---------------------------------------------------------------------------
# 版本落点纪律
# ---------------------------------------------------------------------------
# `PROTOCOL_VERSION` 是普通常量，不由协议类型生成；改版本必须运行本文件，
# 同时检查 live/快照 info.version、前后端信封及变更登记，再跑生成物漂移检查。
