"""M5-K11 权力机制 API 面（契约稿 `docs/api/m5-power-api.md`）：出站投影剥除 + 零新路由/零新码。

钉子分五组（对应契约稿 §4）：
- `TestForbiddenKeyScanner`：递归禁键扫描与剥除的**纯函数**语义（含跨域键集对拍）；
- `TestOutboundStrip`：WS 出站咽喉（`ConnectionManager._send_to`）实测剥除；
- `TestWhiteboxNails`：**白盒负钉**——禁键集单一真相源 + 咽喉接线在位；
- `TestErrorCodeSeal`：错误码面零新增（权力不可见 ⇒ 连错误码都不能成为权力存在性的信号）；
- `TestHttpSurfaceSeal`：HTTP 面结构性密封（全部路由声明 `response_model` + 快照零权力路径）。

**与 codex S3 的分工**：codex 的 `test_m5_authority_surface.py` 锁「现状零命中」（红线 A/B 的
闭合枚举与递归扫描）。本文件锁**施工形态**——剥除闸在出站咽喉上真的接了、键集与 codex 同源、
HTTP 面靠 `response_model` 结构密封。两者不重复：codex 那份在**帧构造层**测，本份在**咽喉层**测。
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from fastapi import WebSocket

from sim.api.errors import _TYPE_TITLE
from sim.api.outbound_guard import (
    AUTHORITY_FORBIDDEN_KEYS,
    OUTBOUND_FORBIDDEN_KEYS,
    RANDOM_STATE_ALIAS_KEYS,
    RANDOM_STATE_FORBIDDEN_KEYS,
    OutboundAuthorityLeak,
    assert_outbound_clean,
    find_authority_keys,
    find_forbidden_keys,
    find_random_state_keys,
    leak_events,
    reset_leak_events,
    strip_authority_fields,
    strip_outbound_forbidden,
)
from sim.api.ws import ConnectionManager

# 禁键集本体是 AUTHORITY_FORBIDDEN_KEYS（键级判层，codex 红线 B）；此处不另立第二套。
_DIRTY: dict[str, Any] = {
    "type": "state_delta",
    "channel": "render",
    "actors": [{"rtoken": "ab12cd34", "x": 3, "y": 4, "authority": 0.7, "rank": 2}],
    "meta": {"nested": {"power_level": 2, "keep": 1}},
    "rows": [[{"dominance": 0.1, "prestige": 5}]],
    "keep_me": "原样保留",
}

_CLEAN: dict[str, Any] = {
    "type": "monologue",
    "channel": "narrative",
    "form": "thought",
    "content": "……我这么做真是没道理。",
}


@pytest.fixture(autouse=True)
def _clean_leak_events() -> Any:
    reset_leak_events()
    yield
    reset_leak_events()


class _FakeWS:
    """假 WebSocket：只实现 send_json（duck type，cast 满足 FastAPI 标注）。"""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)


def _keys_recursive(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.append(str(key).lower())
            out.extend(_keys_recursive(value))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            out.extend(_keys_recursive(item))
    return out


def _live_paths() -> dict[str, Any]:
    """**live** OpenAPI 的 `paths`（M6-K2 起为路由面断言的唯一来源）。

    ⚠ **不要用 `app.routes`**：本仓 anchors/world 路由在 `_IncludedRouter` 包装里，
    `app.routes` 只有 9 条、看不到 `/api/anchors/*` ⇒ 基于它的路由面断言会**假绿**
    （M6-K1 实测发现的坑，K11 那条钉中过招）。
    """
    from sim.api.main import app  # 必须先于 openapi_ext import（半初始化模块坑）

    return app.openapi().get("paths", {})


# ---------------------------------------------------------------------------
# ① 递归禁键扫描与剥除（纯函数层）
# ---------------------------------------------------------------------------


class TestForbiddenKeyScanner:
    def test_find_hits_recursively(self) -> None:
        hits = set(find_authority_keys(_DIRTY))
        assert {"authority", "rank", "power_level", "dominance", "prestige"} <= hits

    def test_strip_is_pure_and_deep(self) -> None:
        """剥除**不改入参**（纯函数）：调用方的原对象必须逐字保持。"""
        before = json.dumps(_DIRTY, sort_keys=True, ensure_ascii=False)
        clean, stripped = strip_outbound_forbidden(_DIRTY)
        assert json.dumps(_DIRTY, sort_keys=True, ensure_ascii=False) == before, (
            "剥除函数就地改了入参——出站构造点会拿到被掏空的 dict"
        )
        assert stripped, "剥除记录为空：出站面发生了静默丢字段，无观测即无追查"
        assert not (set(_keys_recursive(clean)) & AUTHORITY_FORBIDDEN_KEYS)

    def test_strip_keeps_siblings_and_scalars(self) -> None:
        clean, _ = strip_outbound_forbidden(_DIRTY)
        assert clean["keep_me"] == "原样保留"
        assert clean["actors"][0]["rtoken"] == "ab12cd34", "同层非禁键字段被误删"
        assert clean["meta"]["nested"]["keep"] == 1, "嵌套层非禁键字段被误删"
        assert clean["rows"][0][0] == {}, "列表套 dict 的深层禁键未被剥除"

    def test_strip_is_idempotent_and_clean_noop(self) -> None:
        clean, _ = strip_outbound_forbidden(_DIRTY)
        again, stripped_again = strip_outbound_forbidden(clean)
        assert stripped_again == [], "二次剥除仍有命中：剥除不完整"
        assert json.dumps(again, sort_keys=True, ensure_ascii=False) == json.dumps(
            clean, sort_keys=True, ensure_ascii=False
        )
        passthrough, stripped = strip_outbound_forbidden(_CLEAN)
        assert stripped == []
        assert passthrough == _CLEAN

    def test_keys_are_case_insensitive(self) -> None:
        dirty = {"Authority": 1, "POWER": 2}
        assert set(find_authority_keys(dirty)) == {"authority", "power"}
        clean, _ = strip_outbound_forbidden(dirty)
        assert clean == {}

    def test_key_set_matches_codex_redline_b(self) -> None:
        """**跨域防漂移**：与 codex 红线 B 的键集逐字同源（两份定义不许各改各的）。"""
        from sim.tests.test_m5_authority_surface import (
            AUTHORITY_FORBIDDEN_KEYS as REDLINE_KEYS,
        )

        assert AUTHORITY_FORBIDDEN_KEYS == REDLINE_KEYS, (
            "生产侧禁键集与 codex 红线 B 不一致——键集是活资产，须同 CR 两侧同步"
        )

    def test_assert_outbound_clean_raises_with_paths(self) -> None:
        assert_outbound_clean(_CLEAN)  # 干净面不抛
        with pytest.raises(OutboundAuthorityLeak) as exc:
            assert_outbound_clean(_DIRTY)
        message = str(exc.value)
        assert "authority" in message, f"异常未指名禁键：{message}"


# ---------------------------------------------------------------------------
# ② WS 出站咽喉实测（构造点测不到的那一面）
# ---------------------------------------------------------------------------


class TestOutboundStrip:
    @pytest.mark.asyncio
    async def test_ws_send_strips_forbidden_keys(self) -> None:
        """经 `ConnectionManager` 真发一次：落进假 WS 的帧必须零禁键。"""
        mgr = ConnectionManager()
        ws = _FakeWS()
        mgr.register(cast("WebSocket", ws))
        await mgr.broadcast_json(_DIRTY)
        assert len(ws.sent) == 1
        leaked = sorted(set(_keys_recursive(ws.sent[0])) & AUTHORITY_FORBIDDEN_KEYS)
        assert not leaked, f"出站帧仍带权力键：{leaked}"
        assert ws.sent[0]["type"] == "state_delta" and ws.sent[0]["keep_me"] == "原样保留"
        events = leak_events()
        assert events == [
            "$.actors[0].authority",
            "$.actors[0].rank",
            "$.meta.nested.power_level",
            "$.rows[0][0].dominance",
            "$.rows[0][0].prestige",
        ], f"剥除留痕与实际剥除路径不符（生产上等于静默丢字段）：{events}"

    @pytest.mark.asyncio
    async def test_ws_send_clean_payload_untouched(self) -> None:
        """干净载荷**逐字不变**且零观测记录（闸门不得扰动正常出站面）。"""
        mgr = ConnectionManager()
        ws = _FakeWS()
        mgr.register(cast("WebSocket", ws))
        await mgr.broadcast_json(_CLEAN)
        assert ws.sent == [_CLEAN]
        assert leak_events() == []

    @pytest.mark.asyncio
    async def test_directed_send_also_strips(self) -> None:
        """定向投递面（`send_to_subscriber`）同样过闸——它们共用 `_send_to`。"""
        mgr = ConnectionManager()
        ws = _FakeWS()
        mgr.register(cast("WebSocket", ws), subscriber_id="npc-chenmo")
        await mgr.send_to_subscriber("npc-chenmo", _DIRTY)
        assert not (set(_keys_recursive(ws.sent[0])) & AUTHORITY_FORBIDDEN_KEYS)


# ---------------------------------------------------------------------------
# ③ 白盒负钉
# ---------------------------------------------------------------------------


class TestWhiteboxNails:
    def test_forbidden_key_literals_only_in_guard_module(self) -> None:
        """两层禁键的字面量在 `sim/api/` 生产代码里**只允许出现在闸门模块**。

        别处硬写 'authority'/'power_level'/'rng_state'/'world_seed' 之类 = 第二个真相源，
        扩键时必漏一处。（K15 起覆盖面从权力 9 键扩到**两层并集**。）
        """
        api_dir = Path("sim/api")
        allowed = {"outbound_guard.py"}
        offenders: list[str] = []
        for path in sorted(api_dir.glob("*.py")):
            if path.name in allowed:
                continue
            text = path.read_text(encoding="utf-8")
            for key in OUTBOUND_FORBIDDEN_KEYS:
                if f'"{key}"' in text or f"'{key}'" in text:
                    offenders.append(f"{path.name}:{key}")
        assert offenders == [], f"禁键字面量散落在闸门之外：{offenders}"

    def test_send_path_wires_the_guard(self) -> None:
        """咽喉接线在位（白盒）：`_send_to` 源码必须调用剥除函数。

        两个函数名都认（K15 起 canonical 名为 `strip_outbound_forbidden`，
        `strip_authority_fields` 是保留的 K11 别名）——**认函数不认文件名**，
        防的是「闸被摘掉」，不是「改了名」。
        """
        source = inspect.getsource(ConnectionManager._send_to)
        wired = "strip_outbound_forbidden" in source or "strip_authority_fields" in source
        assert wired, "WS 出站咽喉未接剥离闸——新帧可绕过构造层直发"

    def test_no_authority_exception_leaks_into_http_errors(self) -> None:
        """自检异常不得注册成 HTTP 机器码（否则「权力存在」有了对外错误信号）。"""
        assert not [k for k in _TYPE_TITLE if "authority" in k or "power" in k]


# ---------------------------------------------------------------------------
# ④ 错误码面零新增（D-10：权力完全不可见）
# ---------------------------------------------------------------------------


class TestErrorCodeSeal:
    def test_ws_error_vocabulary_has_no_power_code(self) -> None:
        """WS 错误码词表（`_ERROR_*`）零权力族、且仍是 11 项闭合集。"""
        from sim.api import ws as ws_module

        codes = {
            getattr(ws_module, name)
            for name in dir(ws_module)
            if name.startswith("_ERROR_") and isinstance(getattr(ws_module, name), str)
        }
        assert len(codes) == 11, f"错误码词表不是 11 项闭合集：{sorted(codes)}"
        assert not [c for c in codes if "authority" in c or "power" in c]

    def test_snapshot_has_no_power_response_code(self) -> None:
        """快照 `components.responses` 的机器码零权力族（登记单 §2.1 的反向钉）。"""
        from sim.api.main import app  # 必须先于 openapi_ext import（半初始化模块坑）

        schema = app.openapi()
        blob = json.dumps(schema.get("components", {}).get("responses", {}), ensure_ascii=False)
        assert "authority" not in blob and "power" not in blob

    def test_error_type_titles_unchanged_count(self) -> None:
        """`_TYPE_TITLE` 仍是既有 6 项——权力面不新增任何 HTTP 机器码。"""
        assert len(_TYPE_TITLE) == 6, f"HTTP 机器码词表变了：{sorted(_TYPE_TITLE)}"


# ---------------------------------------------------------------------------
# ⑤ HTTP 面结构性密封（「零新路由」论证的可执行形式）
# ---------------------------------------------------------------------------


class TestHttpSurfaceSeal:
    def test_every_http_route_declares_response_model(self) -> None:
        """HTTP 出站面的结构性密封：FastAPI 按 `response_model` 序列化 ⇒ 未声明字段不出现。

        **这是 HTTP 侧不另装中间件的理由**（契约稿 §3.2）：没有 `response_model` 的路由
        等于没有闸，出现一个即红。

        ⚠ **M6-K2 修（假绿修复）**：断言源从 `app.routes` 换成 **live spec 的 `paths`**——本仓
        anchors/world 路由挂在 `_IncludedRouter` 包装里，`app.routes` 实测只有 **9 条**、看不到
        任何 `/api/anchors/*` ⇒ 旧版实际只在查 `/api/health` 与 `/api/world/map`。
        判据=**200 段是否带 content schema**（FastAPI 按 `response_model` 过滤；未声明时
        200 段退化成空 `{}`）；204 段（无响应体）按「声明过 operation」放行。
        """
        paths = _live_paths()
        methods = {"get", "post", "put", "patch", "delete"}

        def _sealed(op: dict[str, Any]) -> bool:
            ok = op.get("responses", {}).get("200")
            if ok is None:
                return bool(op.get("responses"))  # 如 204：无响应体也算已声明
            content = ok.get("content") or {}
            schema = next(iter(content.values())).get("schema", {}) if content else {}
            return bool(schema.get("$ref") or schema.get("type"))

        missing = sorted(
            f"{path}:{method.upper()}"
            for path, ops in paths.items()
            if path.startswith("/api/")
            for method, op in ops.items()
            if method in methods and not _sealed(op)
        )
        assert missing == [], f"这些 /api 操作没有响应模型声明（无结构密封）：{missing}"
        assert any(p.startswith("/api/anchors") for p in paths), (
            "live spec 里一条 anchors 路径都没有——断言源又空了（先查路由是否被挪走）"
        )

    def test_snapshot_paths_have_no_power_route(self) -> None:
        """零新路由的可执行形式：快照 paths 键零 authority/power 族。"""
        from sim.api.main import app

        paths = app.openapi().get("paths", {})
        offenders = [p for p in paths if "authority" in p or "power" in p]
        assert offenders == [], f"出现了权力面路由：{offenders}"


# ---------------------------------------------------------------------------
# ⑥ 随机流状态层（S11 F-1，K15）：与权力层**同一递归**剥除，键名**以真源为准**
# ---------------------------------------------------------------------------

#: 含随机流状态的出站载荷（照 `sim/core/rng_state.py` 的包形状与 0009 列名构造）。
_RNG_DIRTY: dict[str, Any] = {
    "type": "session_state",
    "channel": "session",
    "notice": "你回到了先前的那段日子",
    "anchor": {"name": "第一日", "story_label": "开春"},
    "rng_state": '{"v":1,"registry":{},"streams":{}}',
    "world_seed": 20260919,
    "materials": {"npc": "9f2c…"},
    "streams": {"npc": {"bit_generator": "PCG64", "has_uint32": 0, "uinteger": 128}},
    "rng_state_persisted": True,
    "seed": 7,
}


class TestRandomStateOutboundStrip:
    @pytest.mark.asyncio
    async def test_rng_state_keys_stripped_at_ws_throat(self) -> None:
        """随机流状态键出站即剥 + 留痕（WS 咽喉实测，对照权力键钉体例）。"""
        mgr = ConnectionManager()
        ws = _FakeWS()
        mgr.register(cast("WebSocket", ws))
        await mgr.broadcast_json(_RNG_DIRTY)
        assert len(ws.sent) == 1
        sent = ws.sent[0]
        leaked = sorted(set(_keys_recursive(sent)) & RANDOM_STATE_FORBIDDEN_KEYS)
        assert not leaked, f"出站帧仍带随机流键：{leaked}"
        assert find_random_state_keys(sent) == []
        assert find_authority_keys(sent) == []
        # 合法字段逐字保留（闸门不得顺手掏空叙事面）
        assert sent["notice"] and sent["anchor"]["story_label"] == "开春"
        assert leak_events() == [
            "$.rng_state",
            "$.world_seed",
            "$.materials",
            "$.streams.npc.bit_generator",
            "$.streams.npc.has_uint32",
            "$.streams.npc.uinteger",
            "$.rng_state_persisted",
            "$.seed",
        ], f"随机流键剥除留痕与实际不符：{leak_events()}"

    def test_generic_rng_container_keys_are_not_stripped(self) -> None:
        """**刻意不剥**通用容器键（`streams`/`state`/`registry`/`key`/`v`）。

        剥掉一个叫 `state` 的合法字段=静默丢数据，比漏扫更坏；而这些容器的内容已被
        特异叶子键（`bit_generator`/`world_seed`/`rng_state`）兜住。本钉把这个取舍钉住，
        防后人「补全面」时把它们加进去。
        """
        payload = {"streams": {"a": 1}, "state": "running", "registry": "npc", "key": "k", "v": 1}
        clean, stripped = strip_outbound_forbidden(payload)
        assert stripped == [] and clean == payload

    def test_random_state_keys_trace_to_source_of_truth(self) -> None:
        """**以真源为准，防第二套**：非别名键必须能在真源里逐键找到出处。

        真源分两类，各自对拍：
        1. **域内真源**（文本可查）：`sim/core/rng_state.py`（包结构与字段名）、
           `sim/core/rng.py`（`RngRegistry.world_seed` / `.materials`）、
           0009 迁移（`branches.rng_state` 列名）、`fork.py`（`ForkResult.rng_state_persisted`）；
        2. **numpy 真源**（运行时可查）：`bit_generator.state` 的键集——断言**所有非通用键
           都被本层覆盖**（numpy 哪天加键，本钉会报出来，不靠人记得补）。
        """
        sources = "\n".join(
            Path(p).read_text(encoding="utf-8")
            for p in (
                "sim/core/rng_state.py",
                "sim/core/rng.py",
                "sim/core/persistence/alembic/versions/0009_branches_rng_state.py",
                "sim/core/persistence/fork.py",
            )
        )
        numpy_state = np.random.default_rng(7).bit_generator.state
        numpy_keys = set(numpy_state) | set(numpy_state["state"])
        generic = {"state", "inc"}  # 通用容器键，刻意不剥（见另一钉的理由）
        derived = RANDOM_STATE_FORBIDDEN_KEYS - RANDOM_STATE_ALIAS_KEYS - numpy_keys
        untraceable = sorted(key for key in derived if key not in sources)
        assert untraceable == [], f"这些键不在真源里（自造第二套？）：{untraceable}——补出处或删键"
        uncovered = sorted(numpy_keys - generic - RANDOM_STATE_FORBIDDEN_KEYS)
        assert uncovered == [], f"numpy 抽签状态新增了键但本层未覆盖：{uncovered}"
        # 别名层必须**显式登记**且与真源层不相交（防别名层悄悄膨胀）
        assert not (RANDOM_STATE_ALIAS_KEYS & RANDOM_STATE_FORBIDDEN_KEYS), (
            "别名键与真源键重叠——同一键登记两遍"
        )
        assert RANDOM_STATE_ALIAS_KEYS <= OUTBOUND_FORBIDDEN_KEYS

    def test_two_layers_share_one_recursion(self) -> None:
        """两层**同一递归**（不分两套扫描）：一次调用两层键全被剥，按层取证也可用。"""
        payload = {"authority": 0.7, "rng_state": "{}", "ok": 1}
        clean, stripped = strip_outbound_forbidden(payload)
        assert stripped == ["$.authority", "$.rng_state"]
        assert clean == {"ok": 1}
        assert find_authority_keys(payload) == ["authority"]
        assert find_random_state_keys(payload) == ["rng_state"]
        assert find_forbidden_keys(payload) == ["authority", "rng_state"]

    def test_assert_outbound_clean_reports_rng_layer(self) -> None:
        """自检异常必须**报出层**（否则排障时分不清是权力漏还是随机流漏）。"""
        with pytest.raises(OutboundAuthorityLeak) as exc:
            assert_outbound_clean(_RNG_DIRTY)
        message = str(exc.value)
        assert "random_state" in message and "rng_state" in message, f"异常未指明层与键：{message}"

    def test_k11_alias_still_strips_both_layers(self) -> None:
        """K11 别名 `strip_authority_fields` **保留且同语义**（含随机流层）。

        别名存在的理由：`sim/tests/test_m5_fire_outbound.py`（K13 守卫钉）仍按 K11 的名字
        导入；删别名会让别人的钉变红——**接口演进不许静默破坏既有钉**。
        """
        payload = {"authority": 1, "rng_state": "{}", "keep": 2}
        aliased_clean, aliased_stripped = strip_authority_fields(payload)
        canonical_clean, canonical_stripped = strip_outbound_forbidden(payload)
        assert aliased_clean == canonical_clean
        assert aliased_stripped == canonical_stripped == ["$.authority", "$.rng_state"]
        assert find_authority_keys(payload) == ["authority"]
        assert find_random_state_keys(payload) == ["rng_state"]
