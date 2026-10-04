"""协议版本断言钉（M5-K14 甲案升 1.1；M6-K2 诊断面进快照升 1.2）

**为什么要有这个文件**：版本号在仓里有**两个落点**——`sim/api/ws.py::_PROTOCOL_VERSION`（真相源）
与 `client/src/net/ws.ts::PROTOCOL_VERSION`（第二落点），而两处各写各的**漂移过一次**
（sim 0.1 / client 0.1，P05 才统一）。本文件把「两处相等」与「不得回退」钉成断言，
让下一次升版不再是靠记忆。

**钉的四条**：
1. **防回退**：sim 常量必须是 `1.1`（升 minor 是登记事件，不是随手改）；
2. **跨树防漂移**：前端常量与 sim 常量**逐字相等**（白盒读 `ws.ts` 源码，不 import TS）；
3. **信封取自常量**：帧构造点（`snapshot_payload` 等）不得硬写 `"1.0"` 这类字面量；
4. **登记一致性**：`versioning.md` §7 必须有 1.1 行，且登记的三个 minor 变更与代码事实相符
   （`fast_forward` action / `GET /api/anchors/current` / `PlanDelta` 封闭 schema /
   `GET /{anchor_id}`）。

**已知刻意不钉的一条**：`shared/openapi.json` 的 `info.version` 仍是 FastAPI 默认 `1.0.0`——
**它不是 WS 协议版本的真相源**（versioning §5 说「双处记录」，但 HTTP 侧未接同源常量）。
本单所有权不含 `shared/`（红线：版本升动物理快照会让 `gen-protocol --check` 失去门禁意义），
故只断言 **major 一致**（同为 1.x），把「HTTP 侧接同源」登记为待办，见本文件末尾说明。
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

#: 当前版本（1.1=裁 34-1 甲案三个 minor；1.2=M6-K2 诊断面进快照，仍是 minor）。
EXPECTED_VERSION = "1.2"

#: 登记在 §7 的 minor 变更关键词（doc 同步钉用，避免「登记与代码各说各话」）。
REGISTERED_MINOR_KEYWORDS = (
    "fast_forward",
    "/api/anchors/current",
    "PlanDelta",
    "AnchorMaterializationStatus",
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
    def test_sim_version_is_expected(self) -> None:
        """sim 侧常量 = `1.1`（防回退：降版会让新前端按旧契约解析）。"""
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

    def test_snapshot_info_version_major_matches(self) -> None:
        """`info.version` 与 WS 版本 **major 一致**（刻刻意：HTTP 侧未接同源常量，见文件末尾）。"""
        info = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["info"]
        ws_major = _PROTOCOL_VERSION.split(".")[0]
        assert str(info.get("version", "")).startswith(f"{ws_major}."), (
            f"快照 info.version={info.get('version')!r} 与 WS major {ws_major} 不同源"
        )


class TestRegistrationSync:
    def test_section7_has_1_1_row(self) -> None:
        """§7 变更登记表必须有 `1.1` 行（登记缺失 = 升版没走流程）。"""
        assert f"| {EXPECTED_VERSION} |" in _registration_section(), (
            f"versioning.md §7 缺 {EXPECTED_VERSION} 行——升版必须登记（§7）"
        )

    def test_section7_lists_three_minor_changes(self) -> None:
        """1.1 行的登记须点名三个 minor 变更（关键词齐 ⇒ 登记不是空话）。"""
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
# 待办（不在本单所有权，随下一轮 versioning 单处理）
# ---------------------------------------------------------------------------
# 1. **`info.version` 未接同源常量**：versioning §5 写「`shared/openapi.json` 的 `info.version`
#    与 WS 信封 `v` 双处记录版本」，但 HTTP 侧是 FastAPI 默认 `1.0.0`，与 WS 版本无联动。
#    要接成同源需改 FastAPI app 的 `version=`（`sim/api/main.py`）——那是**另一个落点**，
#    且会改动快照（本单红线：版本升不动物理快照）。故本单只断言 major 一致。
# 2. **前端升版未跑类型面门禁**：`PROTOCOL_VERSION` 是普通常量（非生成的协议类型），
#    前端侧无编译期校验；本文件的跨树钉是唯一守卫 ⇒ **改版本必跑本文件**。
