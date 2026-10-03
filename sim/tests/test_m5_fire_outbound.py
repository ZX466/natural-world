"""M5-K13 火灾生态 · 出站面零变更守卫钉（`docs/api/m5-fire-api-prestudy.md` 判定钉化）

**背景**：K12 判定批次 D 火灾的出站面**零变更**——事件走新增 `fire.*` kind（事件流内部），
烧毁走既有 `structure.collapsed{cause:"damage"}` 族，火光走既有 `Light.kind`（**自由 string**），
`shared/` 与 `shared/protocol.ts` **零 diff**。「零变更」若无机器门禁，下一波顺手加个
`GET /api/fires` 或把 `Light.kind` 改成 enum 就把批次 D 的接口面扩了，而**没人会发现**。
本文件把 K12 的判定逐条钉成可执行断言：**生产码零改动**（只读 `sim/api/`、`sim/core/`、`shared/`）。

## skip-locked 口径（与 opencode A6 同款）

- **锁信号** = `EventKind.FIRE_*` 出现（派单指定）。kind 登记 = opencode 批次 D 数据面施工面，
  在它之前本组钉**锁定跳过**而不是假红——门禁要分得清「新缺陷」与「已知待施工」。
- **解锁时机** = kind 登记合入后，pytest 重新收集即自动转绿，无需人工摘标记。
- **今天即绿**的组（不依赖 opencode）：快照零漂移、`Light.kind` 自由 string、白盒负钉、
  归因键集决策锁。反向保护：先立的钉会把后来的实现约束住（K12 的判定不许被静默推翻）。

## 五组分工（组名 = 类名前缀）

| 组 | 状态 | 钉的是 |
|---|---|---|
| ① `TestSnapshotZeroDrift` | 今天即绿 | 产物零 fire；帧 type 闭合集 15 项；paths 零火灾路由 |
| ② `TestLightKindFreeString` | 今天即绿 | `Light.kind` 自由 string；`kind="fire"` 过既有形状 |
| ③ `TestEventStreamNotFrameType` | skip-locked | fire kind **只在** `PAYLOAD_MODELS`，零进快照 |
| ④ `TestNoFireLiteralInApiLayer` | 今天即绿 | **白盒负钉**：`sim/api/*.py` 字面量零 `fire` |
| ⑤ `TestAttributionKeys` | 半 locked | fire payload **零归因键** + 键集决策锁 |

② 的完整判据（载荷过咽喉闸逐字不变）见 `test_fire_light_payload_fits_existing_shape`；
④ 防的是「火灾专用出站口」= 归因泄漏通道（K12 §3 封堵第三条）。

⚠ **为什么 ④ 是白盒负钉而不是行为钉**：将来若有人真要一个火灾出站面（哪怕只是日志字段名），
行为钉测不出来（功能正常），而这条会在**代码层**报红，逼其走 CR 重新裁 D-10/出站面边界。
"""

from __future__ import annotations

import ast
import io
import json
import tokenize
from pathlib import Path
from typing import Any

import pytest

from sim.api.outbound_guard import (
    AUTHORITY_FORBIDDEN_KEYS,
    find_authority_keys,
    strip_authority_fields,
)
from sim.core.events import EventKind
from sim.core.persistence.event_validation import PAYLOAD_MODELS

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO_ROOT / "shared" / "openapi.json"
GENERATED = REPO_ROOT / "shared" / "protocol.ts"
API_DIR = REPO_ROOT / "sim" / "api"

#: 现有 WS 帧 type 闭合集（快照 `WsMessage.discriminator.mapping` 的 15 项）。
#: 抄自快照当日值——**新增帧即红**（D-10/K12 §2 论证 A：事件 kind 不是帧 type）。
WS_FRAME_TYPES: frozenset[str] = frozenset(
    {
        "player_impulse",
        "set_control",
        "load_anchor",
        "move_request",
        "sync_request",
        "full_snapshot",
        "state_delta",
        "perception",
        "monologue",
        "impulse_feedback",
        "combat_event",
        "timescale",
        "control_ack",
        "session_state",
        "error",
    }
)

#: 归因键集（K12 §3 封堵第一条：事件层零归因）。
#: 只作用于 **fire payload**（其他族有合法同名字段：`StructureCollapsedPayload.cause` 是物理类目、
#: `StructureStartedPayload.built_by` 是施工者），故不做全局禁键。
#: 逃生舱：若 fire 事件确需物理类目字段，走 CR 同时改本集与 K12 §1.3，不要偷偷加键。
ATTRIBUTION_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "actor_id",
        "actor",
        "igniter",
        "cause",
        "cause_human",
        "culprit",
        "blame",
        "attribution",
        "responsible",
        "ordered_by",
        "instigator",
        "witness",
    }
)


def _snapshot() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _fire_kinds() -> list[str]:
    """已登记的 fire 事件 kind（锁信号，A6 同款口径）。"""
    return [
        member.value for name, member in EventKind.__members__.items() if name.startswith("FIRE_")
    ]


def _fire_payload_models() -> dict[str, Any]:
    return {
        kind: PAYLOAD_MODELS[EventKind(kind)]
        for kind in _fire_kinds()
        if EventKind(kind) in PAYLOAD_MODELS
    }


requires_fire_kinds = pytest.mark.skipif(
    not _fire_kinds(),
    reason="fire.* 事件 kind 未登记（opencode 批次 D 数据面施工面）——登记合入后自动解锁",
)


def _docstring_lines(src: str) -> set[int]:
    """docstring 覆盖的行号集合（口径说明里允许提 fire/归因等词）。"""
    lines: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def _fire_string_literals(src: str) -> list[tuple[int, str]]:
    """源码里含 `fire` 的**字符串字面量**（行号, 值）；docstring 除外。"""
    skip = _docstring_lines(src)
    hits: list[tuple[int, str]] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.STRING or tok.start[0] in skip:
            continue
        try:
            value = ast.literal_eval(tok.string)
        except (ValueError, SyntaxError):
            continue
        if isinstance(value, str) and "fire" in value.lower():
            hits.append((tok.start[0], value))
    return hits


# ---------------------------------------------------------------------------
# ① 快照零漂移（今天即绿）
# ---------------------------------------------------------------------------


class TestSnapshotZeroDrift:
    def test_generated_artifacts_have_no_fire(self) -> None:
        """`shared/` 两件产物零 fire 命中——批次 D 出站面零变更的可测代理。

        真门禁是命令 `node tools/gen-protocol.ts --check`（EXIT 0）；本钉把「零漂移」的
        **可测部分**（产物里没有火灾面）常态化，避免只在收编时靠人跑命令。
        """
        for path in (SNAPSHOT, GENERATED):
            text = path.read_text(encoding="utf-8").lower()
            assert "fire" not in text, f"{path.name} 出现 fire 字面量——批次 D 出站面被扩了？"

    def test_ws_frame_type_set_unchanged(self) -> None:
        """WS 帧 type 判别器映射仍 15 项闭合集，且零 fire——新增帧即红。"""
        mapping = _snapshot()["components"]["schemas"]["WsMessage"]["discriminator"]["mapping"]
        assert set(mapping) == set(WS_FRAME_TYPES), (
            f"WS 帧 type 集变了：新增 {sorted(set(mapping) - WS_FRAME_TYPES)}/"
            f"消失 {sorted(WS_FRAME_TYPES - set(mapping))}"
        )
        assert not [t for t in mapping if "fire" in t.lower()]

    def test_snapshot_paths_have_no_fire_route(self) -> None:
        """paths 键零 fire——没有人顺手开过火灾专用路由（K12 §2 论证 C）。"""
        offenders = [p for p in _snapshot()["paths"] if "fire" in p.lower()]
        assert offenders == [], f"出现了火灾面路由：{offenders}"


# ---------------------------------------------------------------------------
# ② Light.kind 自由 string（今天即绿）——K12 §2 论证 B 的钉化
# ---------------------------------------------------------------------------


class TestLightKindFreeString:
    def test_light_kind_is_free_string(self) -> None:
        """`Light.kind` 必须仍是**自由 string**：火光靠 `kind="fire"` 零变更表达。

        若有人把它改成 enum（哪怕只是加一个 `fire` 选项）⇒ 快照与生成物都变 ⇒ 批次 D
        从「零变更」变成「minor 枚举扩展」，必须走 versioning §7 登记。此钉让它**当场红**。
        """
        kind_schema = _snapshot()["components"]["schemas"]["Light"]["properties"]["kind"]
        assert kind_schema == {"type": "string"}, (
            f"Light.kind 不再是自由 string：{json.dumps(kind_schema, ensure_ascii=False)}——"
            "火光表达应走既有自由字符串，扩枚举须走 versioning §7 登记"
        )

    def test_structure_phase_still_three_values(self) -> None:
        """`Structure.phase` 仍是三项枚举——**不扩** `burning`（K12 §5 待裁 3）。"""
        phase = _snapshot()["components"]["schemas"]["Structure"]["properties"]["phase"]
        assert phase.get("enum") == ["built", "collapsing", "rubble"], (
            f"Structure.phase 枚举变了：{phase.get('enum')}——"
            "燃烧是火势不是构件状态；扩它等于一次快照变更（须 versioning §7 登记）"
        )

    def test_fire_light_payload_fits_existing_shape(self) -> None:
        """`kind="fire"` 的灯位载荷**过既有形状**（键集=required）且过咽喉闸零改动。"""
        light = _snapshot()["components"]["schemas"]["Light"]
        payload = {"rtoken": "rt_f1", "x": 30, "y": 22, "kind": "fire", "radius": 5, "flicker": 0.4}
        assert set(payload) == set(light["required"]), (
            f"火光载荷形状与既有 Light 不符：多 {sorted(set(payload) - set(light['required']))}/"
            f"缺 {sorted(set(light['required']) - set(payload))}"
        )
        extra_props = set(light["properties"]) - set(payload)
        assert not extra_props or extra_props <= {"kind"}, "载荷未覆盖 Light 的全部声明字段"
        # 咽喉闸（K11）：火光载荷不是权力面 ⇒ 逐字不变、零剥除
        clean, stripped = strip_authority_fields(payload)
        assert stripped == [] and clean == payload
        assert find_authority_keys(payload) == []


# ---------------------------------------------------------------------------
# ③ 事件流非帧 type（skip-locked）
# ---------------------------------------------------------------------------


@requires_fire_kinds
class TestEventStreamNotFrameType:
    def test_fire_kinds_registered_in_payload_models(self) -> None:
        """每个 fire kind 都登记进 `PAYLOAD_MODELS` 闭合集（K11 P3 同款体例）。"""
        missing = [kind for kind in _fire_kinds() if EventKind(kind) not in PAYLOAD_MODELS]
        assert missing == [], f"fire kind 未登记 payload 模型（W-D1 钉将红）：{missing}"

    def test_fire_kinds_absent_from_snapshot(self) -> None:
        """fire kind 的值**零出现在快照任何位置**——事件流是内部面，不进协议快照。"""
        blob = json.dumps(_snapshot(), ensure_ascii=False).lower()
        for kind in _fire_kinds():
            assert kind.lower() not in blob, f"{kind} 出现在协议快照里——事件 kind 泄漏到出站面了"

    def test_fire_kinds_absent_from_ws_discriminator(self) -> None:
        """fire kind 不是 WS 帧 type（与 ① 的闭合集钉互补：判别力在"值级别"）。"""
        mapping = _snapshot()["components"]["schemas"]["WsMessage"]["discriminator"]["mapping"]
        offenders = [k for k in mapping if k.lower().startswith("fire")]
        assert offenders == [], f"fire 被加成 WS 帧 type：{offenders}"


# ---------------------------------------------------------------------------
# ④ 白盒负钉：sim/api 零 fire 字面量（今天即绿）
# ---------------------------------------------------------------------------


class TestNoFireLiteralInApiLayer:
    def test_sim_api_has_no_fire_string_literal(self) -> None:
        """`sim/api/*.py` 的字符串字面量零 `fire`——防未来有人给火灾开专用出站口。

        专用出站口=归因泄漏通道（K12 §3 封堵第三条）：火势一旦有了自己的路由/投影，
        「谁放任火蔓延」就有了可被稳定读取的结构化出口。
        """
        offenders: list[str] = []
        for path in sorted(API_DIR.glob("*.py")):
            for lineno, value in _fire_string_literals(path.read_text(encoding="utf-8")):
                offenders.append(f"{path.name}:{lineno}:{value}")
        assert offenders == [], f"sim/api 出现 fire 字面量（专用出站口？）：{offenders}"

    def test_scan_detects_planted_literal(self) -> None:
        """反假绿：扫描器对**植入**的 fire 字面量必须报警（否则负钉可能永不触发）。"""
        planted = (
            'ROUTE = "/api/fires"\n'
            "\n"
            "\n"
            "def f() -> str:\n"
            '    """docstring 里的 fire 不算"""\n'
            '    return "fire.spread"\n'
        )
        hits = _fire_string_literals(planted)
        assert [line for line, _ in hits] == [1, 6], f"扫描器判别力不足：{hits}"


# ---------------------------------------------------------------------------
# ⑤ 归因键双保险（半 skip-locked）
# ---------------------------------------------------------------------------


@requires_fire_kinds
class TestAttributionKeys:
    def test_fire_payloads_have_no_attribution_keys(self) -> None:
        """fire payload **零归因键**——与 opencode 的 `extra="forbid"` 双保险。

        **面不同**：他在**数据面构造**时封闭字段（拒外来键），我在**出站面扫描**已登记模型的
        键集（拒设计时的归因意图）。两面都绿才叫「无归因」：只绿一面可能是构造漏了或扫描漏了。
        """
        offenders: list[str] = []
        for kind, model in _fire_payload_models().items():
            fields = set(model.model_fields)
            hit = sorted(fields & ATTRIBUTION_FORBIDDEN_KEYS)
            if hit:
                offenders.append(f"{kind}:{hit}")
        assert offenders == [], (
            f"fire payload 带归因键（D-10 泄漏面，K12 §3 封堵第一条）：{offenders}"
        )

    def test_fire_payloads_are_closed_models(self) -> None:
        """fire payload 必须 `extra="forbid"` 封闭（与既有 19 kind 同款体例）。"""
        for kind, model in _fire_payload_models().items():
            assert model.model_config.get("extra") == "forbid", f"{kind} 的 payload 未封闭"


class TestAttributionDecisionLock:
    def test_attribution_keys_not_in_guard_keyset(self) -> None:
        """锁 K12 §5 待裁 4 的决策：归因键**不进** K11 禁键集。

        理由（写死在此钉的 docstring 里，防后人「顺手补一下」）：K11 键集是 **codex 资产**
        （权力族、活资产、只增不减、须同 CR）；而 fire 归因的防线是 **payload 白名单**
        （本文件上一钉），不是键集。加键是空转，且会让键集语义从「权力」漂成「一切敏感词」。
        """
        assert not (ATTRIBUTION_FORBIDDEN_KEYS & AUTHORITY_FORBIDDEN_KEYS), (
            "归因键混进了 K11 权力键集——两者判层不同（归因属事件面，权力属出站面），"
            "扩键须同 CR 并改 K12 §5 待裁 4"
        )

    def test_guard_does_not_strip_attribution_keys(self) -> None:
        """咽喉闸**不**自动剥除归因键——正因如此，fire 归因必须在 payload 白名单层拦。

        本钉把「K11 闸不是 fire 归因的防线」这一事实钉住：若哪天闸开始剥归因键，
        说明有人改了防线归属（可接受），但必须是有意识的改动而非误改。
        """
        payload = {"kind": "fire", "actor_id": "npc-chenmo"}
        clean, stripped = strip_authority_fields(payload)
        assert stripped == [] and clean == payload
        assert find_authority_keys(payload) == []
