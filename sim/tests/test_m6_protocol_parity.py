"""协议面 live↔快照全量对拍钉 + `StateDeltaMessage` 字段面闭合钉（M6-K7）

**闭合的缺口**：`gen-protocol --check` **只校「生成物 ↔ 快照」**，不校「live ↔ 快照」⇒
「sim 加了路由/响应但快照没跟上」这类漂移**不会自动报红**。M6-K1 实测过一次（诊断路由漏进快照，
从 A11 落地到 M6-K1 才发现），K6 审计又实测出**响应码缺口双向**（本单已补齐）。

**本文件两组钉**
- ① `TestLiveSnapshotParity`：paths 键集 + **responses 双向集合** + 响应体 `$ref`，
  **系统性差异走显式白名单**（每条带理由），任何**新增**差异立刻红。
- ② `TestStateDeltaFieldSurface`：`StateDeltaMessage.properties` 键集**闭合**，
  带**迷雾 `fog` 例外登记**（B 案落地时改钉不加键即红——K6 自曝的薄弱点闭环）。

**白名单纪律**：白名单是**欠账登记**，不是「允许漂移」。每条都写清「为什么现在接受」与「谁负责补」；
删白名单条目=必须真的把两侧对齐。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import sim.api.openapi_ext as ext
from sim.api.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO_ROOT / "shared" / "openapi.json"

#: ② `state_delta` 字段面白名单（render 通道的可见世界变化载体）。
#: **闭合**=不在表里的键不许出现（防「顺手加个 fauna[]/power[]」）。
STATE_DELTA_WHITELIST: frozenset[str] = frozenset(
    {"v", "ws_seq", "channel", "type", "actors", "lights", "structures", "plan", "weather"}
)

#: **预登记例外**：迷雾视觉 B 案要给 `state_delta` 加**可选** `fog={revealed:[{cx,cy}]}`
#: （`m6-content-outbound-prestudy.md` §3.3 已写死形状）。本表把该键登记为「**将来合法**」，
#: 于是 B 案落地时只需改本表（去掉注释即生效），而**别的**新键仍会红。
#: ⚠ 若 B 案**最终不做**（裁 42 未采），把 `fog` 从这里移除即可——那时它就是未授权键。
STATE_DELTA_RESERVED_OPTIONAL: frozenset[str] = frozenset({"fog"})


def _live() -> dict[str, Any]:
    """**线上真实** spec：必须先跑 `openapi_ext.install()`（main.py:170 同一入口）。"""
    ext.install()
    return app.openapi()


def _snapshot() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def specs() -> tuple[dict[str, Any], dict[str, Any]]:
    return _live(), _snapshot()


def _ops(spec: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for path, item in spec.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if isinstance(op, dict) and method in {"get", "post", "put", "patch", "delete"}:
                out[(path, method)] = op
    return out


# ---------------------------------------------------------------------------
# ① live ↔ 快照全量对拍（responses 双向 + 响应体 $ref）
# ---------------------------------------------------------------------------

#: **系统性差异白名单**：`{(方法, 路径): {响应码}}`，含义=「live 有、快照故意不收」。
#: **M6-K7 补齐后为空**（`POST /api/anchors` 的 400/422 + 其余 8 条 422 已进快照，裁 42-2）。
#: 白名单是**欠债登记**：新增条目必须在本行写清理由 + 指向审计/裁决出处，否则视为腐烂。
SYSTEMATIC_LIVE_ONLY: dict[tuple[str, str], dict[str, str]] = {}

#: 结构性 live-only schemas（FastAPI 自动校验模型，快照按体例不收——裁 42-2 已裁「422 不进快照
#: 之外的情形」不再新增；这两张是 FastAPI 的**自动**模型，不归协议面管）。
SYSTEMATIC_LIVE_ONLY_SCHEMAS: frozenset[str] = frozenset({"HTTPValidationError", "ValidationError"})

#: 结构性 snapshot-only schemas（手工补的 WS 信封，live 无对应——`WsEnvelope` 是刻意保留的文档面）。
SYSTEMATIC_SNAPSHOT_ONLY_SCHEMAS: frozenset[str] = frozenset({"WsEnvelope"})


class TestLiveSnapshotParity:
    def test_paths_key_set_identical(self, specs: tuple[dict[str, Any], dict[str, Any]]) -> None:
        """paths 键集**双向零差**（路由面闭合：新增路由漏注入快照会红）。"""
        live, snap = specs
        live_only = sorted(set(live["paths"]) - set(snap["paths"]))
        snap_only = sorted(set(snap["paths"]) - set(live["paths"]))
        assert not live_only, f"live 有、快照无的路由（漏注入）：{live_only}"
        assert not snap_only, f"快照有、live 无的路由（快照写了但没实现）：{snap_only}"

    def test_schemas_key_set_identical_except_systematic(
        self, specs: tuple[dict[str, Any], dict[str, Any]]
    ) -> None:
        """schemas 键集除**系统性白名单**外双向零差。"""
        live, snap = specs
        live_only = set(live["components"]["schemas"]) - set(snap["components"]["schemas"])
        snap_only = set(snap["components"]["schemas"]) - set(live["components"]["schemas"])
        assert live_only <= SYSTEMATIC_LIVE_ONLY_SCHEMAS, (
            f"live 独有 schema（非系统性）：{sorted(live_only)}"
        )
        assert snap_only <= SYSTEMATIC_SNAPSHOT_ONLY_SCHEMAS, (
            f"快照独有 schema（非系统性）：{sorted(snap_only)}"
        )

    def test_responses_parity_both_directions(
        self, specs: tuple[dict[str, Any], dict[str, Any]]
    ) -> None:
        """**responses 双向集合对拍**——本单闭合 K6 §3.3 的双向缺口。

        允许的 live-only 差=`SYSTEMATIC_LIVE_ONLY` 白名单（今天为空：M6-K7 已把
        `POST /api/anchors` 的 400/422 补进快照）。允许的 snap-only 差=**空**
        （快照不得声明 live 没有的响应码——那会让下游按不存在的面生成代码）。
        """
        live, snap = specs
        live_ops, snap_ops = _ops(live), _ops(snap)
        offenders: list[str] = []
        for key in sorted(set(live_ops) | set(snap_ops)):
            method, path = key
            live_codes = set(live_ops.get(key, {}).get("responses", {}))
            snap_codes = set(snap_ops.get(key, {}).get("responses", {}))
            allowed = set(SYSTEMATIC_LIVE_ONLY.get(key, {}))
            extra_live = live_codes - snap_codes - allowed
            extra_snap = snap_codes - live_codes
            if extra_live:
                offenders.append(f"{method.upper()} {path}: live-only {sorted(extra_live)}")
            if extra_snap:
                offenders.append(f"{method.upper()} {path}: snap-only {sorted(extra_snap)}")
        assert offenders == [], f"响应码集合两侧不一致：{offenders}"

    def test_success_response_schema_ref_identical(
        self, specs: tuple[dict[str, Any], dict[str, Any]]
    ) -> None:
        """成功响应体（2xx）的 `$ref` 逐路由相同（防「快照响应体指向错 schema」）。"""
        live, snap = specs
        live_ops, snap_ops = _ops(live), _ops(snap)
        offenders: list[str] = []
        for key in sorted(set(live_ops) & set(snap_ops)):
            method, path = key
            for code in sorted(set(live_ops[key]["responses"]) & set(snap_ops[key]["responses"])):
                if not code.startswith("2"):
                    continue
                lref = live_ops[key]["responses"][code].get("content", {})
                sref = snap_ops[key]["responses"][code].get("content", {})
                lref = next(iter(lref.values())).get("schema") if lref else None
                sref = next(iter(sref.values())).get("schema") if sref else None
                if lref != sref:
                    offenders.append(f"{method.upper()} {path} {code}: {lref} vs {sref}")
        assert offenders == [], f"成功响应体模型不一致：{offenders}"

    def test_systematic_whitelist_is_empty_or_documented(self) -> None:
        """**白名单纪律**：当前应为空（M6-K7 已把 responses 差异全部对齐）。

        若将来必须加条目（=接受某条 live-only 差异），须同时在本测试里补一条说明，
        否则「白名单」会退化成「漂移许可证」。
        """
        assert SYSTEMATIC_LIVE_ONLY == {}, (
            f"responses 白名单非空：{SYSTEMATIC_LIVE_ONLY}——"
            "要么把两侧对齐，要么在本格写明接受理由与审计出处"
        )


# ---------------------------------------------------------------------------
# ② `StateDeltaMessage` 字段面闭合（带迷雾 `fog` 例外登记）
# ---------------------------------------------------------------------------


class TestStateDeltaFieldSurface:
    def test_state_delta_keys_closed(self, specs: tuple[dict[str, Any], dict[str, Any]]) -> None:
        """`StateDeltaMessage.properties` 键集**闭合**（K6 自曝薄弱点的闭环）。

        防的是「顺手给 `state_delta` 加个 `fauna[]`/`power[]`」——那会让内容面或权力面
        借一条 delta 帧进协议面，而 K5 ②组（查 kind 值）与 K11（查路由）都抓不到**字段面**。
        """
        live, snap = specs
        allowed = STATE_DELTA_WHITELIST | STATE_DELTA_RESERVED_OPTIONAL
        for label, spec in (("live", live), ("snapshot", snap)):
            props = set(spec["components"]["schemas"]["StateDeltaMessage"]["properties"])
            extra = props - allowed
            assert not extra, (
                f"{label} 的 state_delta 出现未授权字段 {sorted(extra)}——"
                f"新字段须走 versioning §7（并把键加进白名单；迷雾视觉 B 案已预登记）"
            )

    def test_additional_properties_stays_false(
        self, specs: tuple[dict[str, Any], dict[str, Any]]
    ) -> None:
        """`StateDeltaMessage` 仍 `additionalProperties: false`（封闭载体，防未知字段透传）。"""
        _live, snap = specs
        schema = snap["components"]["schemas"]["StateDeltaMessage"]
        assert schema.get("additionalProperties") is False, schema.get("additionalProperties")

    def test_reserved_fog_not_present_yet(
        self, specs: tuple[dict[str, Any], dict[str, Any]]
    ) -> None:
        """**例外登记的现状**：`fog` 仍是「预登记但未落地」。

        B 案落地时本钉会红（提示把 `STATE_DELTA_RESERVED_OPTIONAL` 的例外转正），
        B 案裁掉时只需删 `STATE_DELTA_RESERVED_OPTIONAL` 里的 `fog`——两条路都有提示。
        """
        _live, snap = specs
        props = set(snap["components"]["schemas"]["StateDeltaMessage"]["properties"])
        if "fog" in STATE_DELTA_RESERVED_OPTIONAL:
            assert "fog" not in props, (
                "state_delta 已含 fog——迷雾视觉 B 案落地了：请把 "
                "STATE_DELTA_RESERVED_OPTIONAL 的例外转正进白名单并更新本钉说明"
            )
