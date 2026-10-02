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

import pytest
from fastapi import WebSocket

from sim.api.errors import _TYPE_TITLE
from sim.api.outbound_guard import (
    AUTHORITY_FORBIDDEN_KEYS,
    OutboundAuthorityLeak,
    assert_outbound_clean,
    find_authority_keys,
    leak_events,
    reset_leak_events,
    strip_authority_fields,
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
        clean, stripped = strip_authority_fields(_DIRTY)
        assert json.dumps(_DIRTY, sort_keys=True, ensure_ascii=False) == before, (
            "剥除函数就地改了入参——出站构造点会拿到被掏空的 dict"
        )
        assert stripped, "剥除记录为空：出站面发生了静默丢字段，无观测即无追查"
        assert not (set(_keys_recursive(clean)) & AUTHORITY_FORBIDDEN_KEYS)

    def test_strip_keeps_siblings_and_scalars(self) -> None:
        clean, _ = strip_authority_fields(_DIRTY)
        assert clean["keep_me"] == "原样保留"
        assert clean["actors"][0]["rtoken"] == "ab12cd34", "同层非禁键字段被误删"
        assert clean["meta"]["nested"]["keep"] == 1, "嵌套层非禁键字段被误删"
        assert clean["rows"][0][0] == {}, "列表套 dict 的深层禁键未被剥除"

    def test_strip_is_idempotent_and_clean_noop(self) -> None:
        clean, _ = strip_authority_fields(_DIRTY)
        again, stripped_again = strip_authority_fields(clean)
        assert stripped_again == [], "二次剥除仍有命中：剥除不完整"
        assert json.dumps(again, sort_keys=True, ensure_ascii=False) == json.dumps(
            clean, sort_keys=True, ensure_ascii=False
        )
        passthrough, stripped = strip_authority_fields(_CLEAN)
        assert stripped == []
        assert passthrough == _CLEAN

    def test_keys_are_case_insensitive(self) -> None:
        dirty = {"Authority": 1, "POWER": 2}
        assert set(find_authority_keys(dirty)) == {"authority", "power"}
        clean, _ = strip_authority_fields(dirty)
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
        """禁键字面量在 `sim/api/` 生产代码里**只允许出现在闸门模块**。

        别处硬写 'authority'/'power_level' 之类 = 第二个真相源，扩键时必漏一处。
        """
        api_dir = Path("sim/api")
        allowed = {"outbound_guard.py"}
        offenders: list[str] = []
        for path in sorted(api_dir.glob("*.py")):
            if path.name in allowed:
                continue
            text = path.read_text(encoding="utf-8")
            for key in AUTHORITY_FORBIDDEN_KEYS:
                if f'"{key}"' in text or f"'{key}'" in text:
                    offenders.append(f"{path.name}:{key}")
        assert offenders == [], f"禁键字面量散落在闸门之外：{offenders}"

    def test_send_path_wires_the_guard(self) -> None:
        """咽喉接线在位（白盒）：`_send_to` 源码必须调用剥除函数。"""
        source = inspect.getsource(ConnectionManager._send_to)
        assert "strip_authority_fields" in source, "WS 出站咽喉未接剥离闸——新帧可绕过构造层直发"

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
        """
        from sim.api.main import app

        missing = [
            f"{getattr(route, 'path', '?')}:{','.join(sorted(getattr(route, 'methods', []) or []))}"
            for route in app.routes
            if getattr(route, "methods", None)
            and getattr(route, "path", "").startswith("/api/")
            and getattr(route, "response_model", None) is None
        ]
        assert missing == [], f"这些 /api 路由没有 response_model（无结构密封）：{missing}"

    def test_snapshot_paths_have_no_power_route(self) -> None:
        """零新路由的可执行形式：快照 paths 键零 authority/power 族。"""
        from sim.api.main import app

        paths = app.openapi().get("paths", {})
        offenders = [p for p in paths if "authority" in p or "power" in p]
        assert offenders == [], f"出现了权力面路由：{offenders}"
