"""M6 内容面出站守卫钉（`docs/api/m6-content-outbound-prestudy.md` 的 C5「随落随钉」预置）

**背景**：M6 内容面四模块（生态 / 动物三只 / 语言阶层 / 迷雾）在 Claude 域施工（对齐 `fire.py`
体例），而它们**要不要进 WS/协议面**已由 K4 预研稿逐条判定并论证：

| 事件 | K4 判定 | 本文件的钉 |
|---|---|---|
| `ecology.shift` | 事件流零投影（视觉走既有 `Weather.visual`） | ①登记 + ②零帧面 + ④闸 |
| `fauna.tick` | 事件流 + 复用既有 `actors[]`（零 schema） | ①登记 + ②零帧面 + ④闸 |
| `speech.shift` | 事件流零投影；**只写可达性布尔** | ①登记 + ③**零数值** + ④闸 |
| `fog.reveal` | 事件流 + 服务端投影过滤（视觉另立单） | ①登记 + ②零帧面 + ④闸 |

**skip-locked 双态口径（A6/A1 体例）**
- **锁信号** = 四 kind 出现在 `EventKind`（`ECOLOGY_`/`FAUNA_`/`SPEECH_`/`FOG_` 前缀）。
  今天为假（22 个 kind 里零内容面 kind）⇒ 锁定组**跳过**而不是假红——门禁要分得清
  「新缺陷」与「已知待施工」。
- **解锁时机** = 施工合入后 pytest 重新收集即自动转绿，**无需人工摘标记**。
- **解锁路径已预验证**（K13 手法）：用既有 kind `fire.ignited` 实跑通了
  `PAYLOAD_MODELS[EventKind(kind)]` / `model_fields` / `model_config["extra"]` 三段查表，
  避免「解锁那天才发现查表写错」。
- **⑤ 咽喉闸继承钉今天即绿**（它不依赖 kind 落地：锁的是「内容面不许另开发送路径」）。

**红线恒等式**：`len(PAYLOAD_MODELS) == len(EventKind)`（codex 红线 A③）——新增 kind 未登记
payload 模型即红；这条本身**今天即绿**，不锁。

**⑤ CI 覆盖钉（今天即绿）**：本文件命名 `test_m6_*.py`（项目体例）+ CI 的 pytest 步骤是
`uv run pytest -m "not bench"`（**全量**，`.github/workflows/ci.yml`）⇒ 无需另建 M6 步即已进门禁；
钉子把这条写死，免得日后有人以为「靠命名进某个 M6 步」。
"""

from __future__ import annotations

import ast
import inspect
import io
import json
import re
import tokenize
from pathlib import Path
from typing import Any

import pytest

from sim.api.main import app  # 必须先于 openapi_ext import（半初始化模块坑）
from sim.api.outbound_guard import OUTBOUND_FORBIDDEN_KEYS
from sim.api.ws import ConnectionManager
from sim.core.events import EventKind
from sim.core.persistence.event_validation import PAYLOAD_MODELS

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO_ROOT / "shared" / "openapi.json"
GENERATED = REPO_ROOT / "shared" / "protocol.ts"
API_DIR = REPO_ROOT / "sim" / "api"

#: 四内容事件（K4 拟名；以施工落地名为准，判定按**前缀**匹配故改名不影响本组钉）。
CONTENT_PREFIXES = ("ECOLOGY_", "FAUNA_", "SPEECH_", "FOG_")

#: K13 归因键集（事件层零归因；面不同——本组扫的是**内容事件 payload**）。
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

#: ③ speech 零数值：语言阶层的**社会分层读数**禁进 payload（S4 判据：只写可达性布尔）。
SOCIAL_HIERARCHY_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "tier",
        "tier_id",
        "level",
        "rank_level",
        "class",
        "class_id",
        "caste",
        "stratum",
        "literacy_rate",
        "literacy",
        "readability",
        "population",
        "headcount",
        "count",
        "ranking",
        "rank",
        "score",
        "index",
        "percent",
        "ratio",
    }
)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _content_kinds() -> dict[str, str]:
    """已登记的内容面 kind：``{成员名: kind 值}``（锁信号）。"""
    return {
        name: member.value
        for name, member in EventKind.__members__.items()
        if name.startswith(CONTENT_PREFIXES)
    }


def _speech_kinds() -> list[str]:
    return [name for name in _content_kinds() if name.startswith("SPEECH_")]


def _payload_model(kind_value: str) -> Any:
    """取 payload 模型（解锁后走的就是这条路；今天用 `fire.ignited` 预验证过）。"""
    return PAYLOAD_MODELS[EventKind(kind_value)]


def _docstring_lines(src: str) -> set[int]:
    """docstring 覆盖的行号集合（口径说明里允许提 WS/出站等词，故白盒扫时要剔掉）。"""
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


def _code_tokens(src: str) -> list[tokenize.TokenInfo]:
    """去注释与 docstring 的 token 列表。"""
    skip = _docstring_lines(src)
    return [
        tok
        for tok in tokenize.generate_tokens(io.StringIO(src).readline)
        if tok.type != tokenize.COMMENT and tok.start[0] not in skip
    ]


def _stream_with_offsets(tokens: list[tokenize.TokenInfo]) -> tuple[str, list[int]]:
    """拼 token 流并给出每个 token 在流里的字符偏移（区间比较必须同一口径）。"""
    parts: list[str] = []
    offsets: list[int] = []
    pos = 0
    for tok in tokens:
        offsets.append(pos)
        parts.append(tok.string)
        pos += len(tok.string) + 1
    return " ".join(parts), offsets


def _span_of(stream: str, marker: str) -> tuple[int, int] | None:
    """`marker` 在 token 流里的区间：起=marker 起点，止=下一个 `def`。"""
    start = stream.find(marker)
    if start < 0:
        return None
    nxt = stream.find("def ", start + len(marker))
    return (start, nxt if nxt > 0 else len(stream))


requires_content_kinds = pytest.mark.skipif(
    not _content_kinds(),
    reason=(
        "M6 内容面四 kind 尚未登记（Claude 域施工中，对齐 fire.py 体例）——"
        "锁信号 = EventKind 出现 ECOLOGY_/FAUNA_/SPEECH_/FOG_ 前缀成员，登记后自动解锁"
    ),
)


# ---------------------------------------------------------------------------
# 0 红线恒等式（今天即绿，不锁）：kind 与 payload 模型一一对应
# ---------------------------------------------------------------------------


class TestPayloadModelRedline:
    def test_payload_models_cover_all_kinds(self) -> None:
        """codex 红线 A③ 恒等式：`len(PAYLOAD_MODELS) == len(EventKind)`。"""
        assert len(PAYLOAD_MODELS) == len(EventKind), (
            f"kind 与 payload 模型数量不等：kinds={len(EventKind)} "
            f"models={len(PAYLOAD_MODELS)}——新增 kind 必须同 commit 登记（W-D1）"
        )

    def test_content_names_absent_from_live_spec_today(self) -> None:
        """内容面命名**零**出现在 live spec（今天即绿；四 kind 落地后由 ② 组接棒细查）。

        立这条是为了**今天就锁住判据方向**：将来有人顺手加个内容面端点/帧，它会在这里报红。
        """
        blob = json.dumps(app.openapi(), ensure_ascii=False).lower()
        for token in ("/api/ecology", "/api/fauna", "/api/speech", "/api/fog"):
            assert token not in blob, f"live spec 出现内容面路由：{token}"


# ---------------------------------------------------------------------------
# ① kind 登记钉（skip-locked）：登记 + 封闭 + 零归因键
# ---------------------------------------------------------------------------


@requires_content_kinds
class TestContentKindRegistration:
    def test_all_content_kinds_registered_in_payload_models(self) -> None:
        """四个前缀下的 kind **都**进了 `PAYLOAD_MODELS`（红线 A 恒等式的分组版）。"""
        missing = [
            name
            for name, value in _content_kinds().items()
            if EventKind(value) not in PAYLOAD_MODELS
        ]
        assert missing == [], f"内容面 kind 未登记 payload 模型：{missing}"

    def test_content_payloads_are_closed_models(self) -> None:
        """内容面 payload 必须 `extra="forbid"` 封闭（与既有 22 kind 同款体例）。"""
        offenders = [
            name
            for name, value in _content_kinds().items()
            if _payload_model(value).model_config.get("extra") != "forbid"
        ]
        assert offenders == [], f"内容面 payload 未封闭（extra != forbid）：{offenders}"

    def test_content_payloads_have_no_attribution_keys(self) -> None:
        """**内容面 payload 零归因键**（K13 归因键集；与 K11 咽喉闸双保险，面不同）。

        K4 §4 的判断：`ecology.shift` 的归因风险最高——「谁砍的树导致河浊」是问责表，
        而问责表=权力叙事的入口。本钉让它在**数据面构造**层就红。
        """
        offenders: list[str] = []
        for name, value in _content_kinds().items():
            hit = sorted(set(_payload_model(value).model_fields) & ATTRIBUTION_FORBIDDEN_KEYS)
            if hit:
                offenders.append(f"{name}:{hit}")
        assert offenders == [], f"内容面 payload 带归因键（D-10 邻接泄漏面，K4 §4）：{offenders}"

    def test_content_payloads_have_no_outbound_forbidden_keys(self) -> None:
        """内容面 payload 零出站禁键（K11 两层：权力键 + 随机流状态键）。"""
        offenders: list[str] = []
        for name, value in _content_kinds().items():
            hit = sorted(set(_payload_model(value).model_fields) & OUTBOUND_FORBIDDEN_KEYS)
            if hit:
                offenders.append(f"{name}:{hit}")
        assert offenders == [], f"内容面 payload 含出站禁键：{offenders}"


# ---------------------------------------------------------------------------
# ② 零帧面钉（skip-locked）：四 kind 零进快照帧判别器 + 生成物零命中
# ---------------------------------------------------------------------------


@requires_content_kinds
class TestNoContentSurfaceOnFrames:
    def test_content_kinds_absent_from_snapshot_discriminator(self) -> None:
        """四 kind **零**进 `WsMessage` 判别器映射（WS 帧 type 闭合集，codex 红线 A①）。"""
        mapping = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["components"]["schemas"][
            "WsMessage"
        ]["discriminator"]["mapping"]
        offenders = [
            t for t in mapping if t.lower().startswith(("ecology", "fauna", "speech", "fog"))
        ]
        assert offenders == [], f"内容面 kind 被加成 WS 帧 type：{offenders}"

    def test_content_kinds_absent_from_snapshot_anywhere(self) -> None:
        """四 kind 的值**零**出现在快照任何位置（事件流是内部面，不进协议快照）。"""
        blob = json.dumps(
            json.loads(SNAPSHOT.read_text(encoding="utf-8")), ensure_ascii=False
        ).lower()
        for _name, value in _content_kinds().items():
            assert value.lower() not in blob, f"{value} 出现在协议快照里——内容面泄漏到出站面了"

    def test_generated_typescript_has_no_content_kind(self) -> None:
        """生成物 `shared/protocol.ts` 零命中（`gen-protocol --check` 的可测代理）。"""
        text = GENERATED.read_text(encoding="utf-8").lower()
        for token in ("ecology.", "fauna.", "speech.", "fog."):
            assert token not in text, f"生成物出现 {token}——内容面进协议面了？"

    def test_live_paths_have_no_content_route(self) -> None:
        """live spec 的 `paths` 零内容面路由（K4 C2「帧面零字段」，路由面同判）。"""
        offenders = [
            p
            for p in app.openapi()["paths"]
            if any(p.lower().startswith(f"/api/{x}") for x in ("ecology", "fauna", "speech", "fog"))
        ]
        assert offenders == [], f"出现内容面路由：{offenders}"


# ---------------------------------------------------------------------------
# ③ speech 零数值钉（skip-locked）：只写可达性布尔，禁阶层/人数/排名
# ---------------------------------------------------------------------------


@requires_content_kinds
class TestSpeechNoSocialHierarchyNumbers:
    def test_speech_payload_has_no_hierarchy_number_keys(self) -> None:
        """`speech.*` payload **禁**阶层级别/人数/排名类键（S4 判据，K4 §4 硬纪律 2）。

        语言阶层=社会分层=权力的**影子**（D-10 B2/B3）。玩家可见的只能是**自述式叙事**
        （「这字我认得」），系统**不得**告知「你现在处于第几层」。
        """
        offenders: list[str] = []
        kinds = _content_kinds()
        for name in _speech_kinds():
            hit = sorted(
                set(_payload_model(kinds[name]).model_fields)
                & SOCIAL_HIERARCHY_FORBIDDEN_KEYS
            )
            if hit:
                offenders.append(f"{name}:{hit}")
        assert offenders == [], (
            f"speech payload 带社会分层数值键（D-10 邻接，K4 §4）：{offenders}——只写可达性布尔"
        )

    def test_speech_payload_types_are_categorical(self) -> None:
        """`speech.*` payload 的字段**不得是数值型**（int/float）——层号、人数、比率都算。

        判据=pydantic 字段注解：数值型（`int`/`float`，含 `Optional`/`list` 包裹）在
        speech 面上零容忍；布尔与字面量枚举（可达性）是唯一合法形态。
        （⚠ M6 修：`_speech_kinds()` 返回**成员名**（`SPEECH_SHIFT`），而 StrEnum
        的 `EventKind(x)` 是**按值**查找（`speech.shift`）——原实现 `EventKind(name)`
        必 ValueError；取值走 `_content_kinds()[name]`。）
        """
        numeric = re.compile(r"\b(int|float)\b")
        offenders: list[str] = []
        kinds = _content_kinds()
        for name in _speech_kinds():
            model = _payload_model(kinds[name])
            for field, info in model.model_fields.items():
                annotation = str(info.annotation)
                if numeric.search(annotation):
                    offenders.append(f"{name}.{field}: {annotation}")
        assert offenders == [], f"speech payload 含数值字段（社会分层读数）：{offenders}"


# ---------------------------------------------------------------------------
# ④ 咽喉闸继承钉（今天即绿）：内容面若走 WS 出站，必过 K11 咽喉闸，无旁路
# ---------------------------------------------------------------------------


class TestThroatGateInherited:
    def test_ws_send_path_wires_the_guard(self) -> None:
        """咽喉接线在位（白盒，承 K11 钉）：`_send_to` 必须调剥除函数。

        两个函数名都认（K15 起 canonical 名为 `strip_outbound_forbidden`）。
        """
        source = inspect.getsource(ConnectionManager._send_to)
        wired = "strip_outbound_forbidden" in source or "strip_authority_fields" in source
        assert wired, "WS 出站咽喉未接剥离闸"

    def test_no_bypass_send_path_in_sim_api(self) -> None:
        """**防旁路**：除咽喉本体与已登记的 legacy 端点外，`sim/api/` 零 `.send_json(` 直发。

        为什么要有这条：内容面若自己持有连接对象直发，K11 咽喉闸（两层禁键同一递归）
        的全部保证归零——出站闸是**唯一**的机械防线，绕过它等于没装。

        **已登记的豁免（pre-existing，M6-K5 实测发现，已报告给 Claude）**：
        `main.py::ws_endpoint`（legacy WSGI 全量回帧端点 `:316-352`）有 3 处
        `ws.send_json(...)` 直发，**不经咽喉** ⇒ 那条路径上的帧**不过出站闸**。
        本钉把它**显式列入豁免**（而不是假红），这样将来**新增**任何旁路都会立刻报红。
        收口建议（不在本单所有权）：让 legacy 端点改走 `ConnectionManager.send_json_to`。

        判据=**精确的 `.send_json(` 形态**：排除 `send_json_to`（manager 的定向投递，
        它自己走咽喉）与 `def send_json_to`（定义）。
        """
        offenders: list[str] = []
        for path in sorted(API_DIR.glob("*.py")):
            tokens = _code_tokens(path.read_text(encoding="utf-8"))
            stream, offsets = _stream_with_offsets(tokens)
            allowed = [
                span
                for span in (_span_of(stream, "def _send_to"), _span_of(stream, "def ws_endpoint"))
                if span is not None
            ]
            for index, tok in enumerate(tokens):
                if tok.string != "send_json":
                    continue
                is_attribute_call = index > 0 and tokens[index - 1].string == "."
                is_call = index + 1 < len(tokens) and tokens[index + 1].string == "("
                if not (is_attribute_call and is_call):
                    continue
                if any(lo <= offsets[index] <= hi for lo, hi in allowed):
                    continue
                offenders.append(f"{path.name}:{tok.start[0]}")
        assert offenders == [], f"出现绕过咽喉闸的 `.send_json(` 直发：{offenders}"

    def test_content_modules_do_not_import_websocket(self) -> None:
        """世界/领域层**不得**持有 WS 连接（内容面是纯函数 + 事件，C1）。

        判据=`sim/world/*.py` 与 `sim/core/**/*.py` 零 WebSocket 依赖
        （`fastapi` / `WebSocket`）——要出站只能经事件 → driver → manager。
        """
        offenders: list[str] = []
        for pattern in ("sim/world/*.py", "sim/core/**/*.py"):
            for path in sorted(REPO_ROOT.glob(pattern)):
                text = path.read_text(encoding="utf-8")
                for needle in ("from fastapi", "import fastapi", "WebSocket"):
                    if needle in text:
                        offenders.append(f"{path.relative_to(REPO_ROOT)}:{needle}")
        assert offenders == [], f"世界/领域层出现 WebSocket 依赖（内容面不该能出站）：{offenders}"


# ---------------------------------------------------------------------------
# ⑤ CI 覆盖钉（今天即绿）：命名体例 + CI 走全量（不是「某个 M6 步」）
# ---------------------------------------------------------------------------


class TestCiCoverage:
    def test_file_name_follows_project_glob(self) -> None:
        """本文件名落在项目体例 `test_m6_*.py` 内（与 M1~M5 同族命名）。"""
        assert Path(__file__).name.startswith("test_m6_"), Path(__file__).name

    def test_ci_runs_full_suite(self) -> None:
        """CI 的 pytest 步骤是**全量** `pytest -m "not bench"` ⇒ 本文件天然进门禁。

        ⚠ 更正一个流传说法：CI 里**没有**「M5/M6 步」；coverage 靠全量步 + 若干按路径的
        命名信号步。本钉把实况写死，免得日后有人以为「换个名字就不进门禁」。
        """
        ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert 'uv run pytest -m "not bench"' in ci, "CI 的全量 pytest 步不见了——本文件会脱门禁"
