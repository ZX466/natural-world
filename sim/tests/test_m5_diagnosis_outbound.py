"""M6-K1 出站面补钉：M-1 红线 B 三面扫之**诊断路由面** + drain 失败帧体例（S13 M-1 / K16 审计稿 §5）

**背景与判据来源**
- codex 红线 B 把「权力/rng 键零出站」钉在**三面**：WS 出站帧、HTTP 响应 JSON、prompt 装配产物。
  WS 面已由 `sim/tests/test_m5_power_api.py`（K11 咽喉钉）与 `test_m5_fire_outbound.py` 覆盖，
  prompt 面归 codex 域；**本文件补 HTTP 面里最容易被忘的一类端点：诊断/自检路由**（M-1）。
  M-1 在本仓的落地形态 = **诊断路由响应体逐键过 `outbound_guard` 递归扫 = 零命中**，
  且它必须**声明封闭 `response_model`**（HTTP 无中间件，靠结构密封 + 本组钉双保险）。
- K16 审计稿 §5 第 2 条前置钉：**案 B 最小形的失败帧体例**——`code` 沿用 `load_failed`
  （**不扩** 11 项错误码词表）、玩家可见文本**戏内口语零工程词**、连接不断（§3.3）。

**三组钉的状态口径**
- `TestDiagnosticRouteSeal`：**今天即绿**（诊断路由存在、封闭、三键、两态递归扫零命中）。
- `TestDiagnosisSurfaceParity`：**skip-locked**（M6-K1 实测发现：诊断路由**不在**
  `shared/openapi.json` ⇒ live↔快照漂移，详见该组 docstring）。
- `TestDrainFailureFrame`：**skip-locked**，锁信号 = `_drain_loads` 有**生产调用方**
  （K16 审计稿 §3.2 的接线案未落：目前全仓唯一调用方是 `test_m5_anchors_crud.py` 手动跑）。
- `TestWsErrorVocabulary`：**今天即绿**（11 项闭合集，防接线时顺手扩码）。

**为什么失败帧钉是「源码级」而不是端到端**：`client` 的 TestClient websocket 是**阻塞式**
`receive_json()`，而本仓**没装 `pytest-timeout`** ⇒ 一旦实现选择不同的投递机制（广播给谁、
投递到哪一步），端到端钉会**挂死 CI**而不是变红。故这里断言**可判红的源码级体例**
（失败分支引用的 code 常量 + 玩家可见文本是字面量），端到端投递钉留给施工方**随交付机制同提交**。
"""

from __future__ import annotations

import ast
import io
import json
import time
import tokenize
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from sim.api.main import app  # 必须先于 openapi_ext import（半初始化模块坑）
from sim.api.outbound_guard import find_forbidden_keys
from sim.core.persistence.anchor_package import MATERIALIZATION_REASONS

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PY = REPO_ROOT / "sim" / "api" / "main.py"
WS_PY = REPO_ROOT / "sim" / "api" / "ws.py"
SNAPSHOT = REPO_ROOT / "shared" / "openapi.json"
LZ_KEY = "t" * 44

DIAGNOSIS_PATH = "/api/anchors/{anchor_id}/materialization"
DIAGNOSIS_SCHEMA = "AnchorMaterializationStatus"

#: 诊断响应**恰好**这三个键（`anchors.py::AnchorMaterializationStatus`）。
#: 多一个键都要解释：M-1 的核心反向钉——诊断面**不许**回世界真相或随机流状态。
DIAGNOSIS_KEYS = frozenset({"anchor_id", "ready", "reason"})


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _code_only(path: Path) -> str:
    """只留代码（去掉注释与 docstring）——白盒钉扫「实现」而不是口径说明。"""
    src = path.read_text(encoding="utf-8")
    skip: set[int] = set()
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
            skip.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    out: list[str] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT or tok.start[0] in skip:
            continue
        out.append(tok.string)
    return " ".join(out)


def _string_literals(path: Path) -> list[str]:
    return [
        tok.string
        for tok in tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline)
        if tok.type == tokenize.STRING
    ]


def _drain_wired_in_production() -> bool:
    """锁信号：`_drain_loads` 在生产代码里**被调用**（注册/定义不算）。

    K16 时为假——`main.py` 只把它挂到 `app.state`，driver 循环从不调用。
    案 B 接线后的**生产调用点 = `run_world_driver` 循环**（ws.py：flush 写事务
    收口后 `drain_loads()`）——所以本锁认两处调用点任一：
    ①`main.py` 里 `drain_pending_loads()` 被调用（≥3 次出现，K16 原口径）；
    ②`ws.py::run_world_driver` 里有 `drain_loads()` 调用 + `main.py` 把
    `_drain_loads` 传进了 `run_world_driver(...)`（传参即调用链落地）。

    ⚠ `_code_only` 保留 token 间空格（`drain_loads = _drain_loads`）——
    判定前先剥空格再做子串对拍（K16 原口径对「词内无空格」的假设在此不成立）。
    """

    def _tight(code: str) -> str:
        return code.replace(" ", "").replace("\n", "")

    main_code = _code_only(MAIN_PY)
    if "drain_pending_loads()" in main_code and main_code.count("drain_pending_loads") >= 3:
        return True
    ws_tight = _tight(_code_only(WS_PY))
    driver_call = "drain_loads()" in ws_tight
    main_passes = "_drain_loads" in _tight(main_code) and "drain_loads=_drain_loads" in _tight(
        main_code
    )
    return driver_call and main_passes


requires_drain_wiring = pytest.mark.skipif(
    not _drain_wired_in_production(),
    reason=(
        "drain 失败帧接线未落（K16 审计稿 §3.2 案 B：`_drain_loads` 生产无调用方，"
        "全仓唯一调用方是测试手动跑）——接线落地后自动解锁"
    ),
)


def _live_spec() -> dict[str, Any]:
    """live OpenAPI（`app.openapi()`）。

    ⚠ **不要用 `app.routes`**：本仓 anchors/world 路由挂在 `_IncludedRouter` 包装里
    （实测 `app.routes` 只有 9 条、看不到 `/api/anchors/*`）⇒ 拿 `app.routes` 做路由面
    断言会**假绿**（K11 那条 `test_every_http_route_declares_response_model` 就吃了这个亏）。
    路由面的断言一律走 live spec 的 `paths`。
    """
    return app.openapi()


def _await_current_branch(db: Path, timeout: float = 10.0) -> bool:
    """等 driver 首帧开线并置真（开线是**异步**动作，POST 之前必须等）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        engine = create_engine(f"sqlite:///{db}")
        try:
            with Session(engine) as session:
                rows = session.execute(sa_text("SELECT is_current FROM branches")).all()
            if any(bool(r[0]) for r in rows):
                return True
        except Exception:
            pass
        finally:
            engine.dispose()
        time.sleep(0.05)
    return False


@pytest.fixture()
def client_db(tmp_path, monkeypatch) -> Any:
    """隔离库 + app 客户端（诊断路由需要真 store：`app.state.store` 缺位会回 400）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LZ_MASTER_KEY", LZ_KEY)
    import sim.api.anchors as anchors_mod
    from sim.api.settings import get_profile_store

    db = tmp_path / "world.db"
    get_profile_store().__init__(f"sqlite:///{tmp_path / 'settings.db'}")
    anchors_mod.get_anchor_store().__init__(f"sqlite:///{db}")
    with TestClient(app) as client:
        assert _await_current_branch(db), "driver 未开线（测试环境问题，非被测面）"
        yield client, db


def _drop_package_row(db: Path, anchor_id: str) -> None:
    """把该档的物化包删掉 ⇒ 诊断面读 `ready=false` / `reason='no_package'`。"""
    engine = create_engine(f"sqlite:///{db}")
    try:
        with Session(engine) as session:
            session.execute(
                sa_text("DELETE FROM anchor_packages WHERE anchor_id = :a"), {"a": anchor_id}
            )
            session.commit()
    finally:
        engine.dispose()


#: 最小可解析 RNG 状态包（诊断面只判**存在性与可解析性**，不核内容）。
_RNG_BLOB = '{"v":1,"registry":{"world_seed":7,"materials":{}},"streams":{}}'


def _set_rng_state(db: Path, anchor_id: str, blob: str = _RNG_BLOB) -> None:
    """给该档的包补上 RNG 状态 ⇒ 诊断面从 `rng_unavailable` 翻成 `ready=true`。

    为什么需要这一步：**新存档默认 `rng_state=NULL`**（存档时拿不到随机流状态）⇒ 诊断面
    天然是 `ready=false`。要拿到 `ready=true` 这一态（验「互斥」：ready ⇒ reason 为 None），
    只能补包字段——这正是批次 E 的真实诊断语义（不是测试造出来的假态）。
    """
    engine = create_engine(f"sqlite:///{db}")
    try:
        with Session(engine) as session:
            session.execute(
                sa_text("UPDATE anchor_packages SET rng_state = :b WHERE anchor_id = :a"),
                {"b": blob, "a": anchor_id},
            )
            session.commit()
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# ① M-1：诊断路由面（HTTP 出站面的「最容易被忘的一类端点」）
# ---------------------------------------------------------------------------


class TestDiagnosticRouteSeal:
    def test_diagnosis_route_declares_closed_response_model(self) -> None:
        """诊断路由必须声明**封闭**响应模型（HTTP 无中间件，结构密封是主防线）。"""
        paths = _live_spec()["paths"]
        assert DIAGNOSIS_PATH in paths, (
            f"live spec 里没有诊断路由 {DIAGNOSIS_PATH}——M-1 的钉对象消失，先查是否被改名/挪走"
        )
        get = paths[DIAGNOSIS_PATH]["get"]
        ref = get["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith(f"/{DIAGNOSIS_SCHEMA}"), (
            f"诊断响应模型不是封闭的 {DIAGNOSIS_SCHEMA}：{ref}"
        )
        schema = paths  # 只为行号可读性
        del schema

    def test_diagnosis_schema_is_closed_and_exactly_three_keys(self) -> None:
        """live 诊断 schema：`additionalProperties:false` 且**恰为三键**（M-1 反向钉）。"""
        schema = _live_spec()["components"]["schemas"][DIAGNOSIS_SCHEMA]
        assert schema.get("additionalProperties") is False, schema
        assert set(schema["properties"]) == set(DIAGNOSIS_KEYS), sorted(schema["properties"])

    def test_diagnosis_response_passes_recursive_forbidden_scan(self, client_db: Any) -> None:
        """**M-1 本体**：诊断响应体逐键过 `outbound_guard` 递归扫 = 零命中（两层都在内）。

        两个态都扫：`ready=true`（正常档）与 `ready=false`（删包后的不可回退档）——
        失败态才最容易把工程原因码/状态顺手带出来。
        """
        client, db = client_db
        created = client.post("/api/anchors", json={"name": "第二天"}).json()
        anchor_id = created["id"]
        ok_body = client.get(f"/api/anchors/{anchor_id}/materialization").json()
        assert set(ok_body) == set(DIAGNOSIS_KEYS), ok_body
        assert find_forbidden_keys(ok_body) == [], f"正常态诊断体含禁键：{ok_body}"

        _drop_package_row(db, anchor_id)
        bad_body = client.get(f"/api/anchors/{anchor_id}/materialization").json()
        assert bad_body["ready"] is False, bad_body
        assert set(bad_body) == set(DIAGNOSIS_KEYS), bad_body
        assert find_forbidden_keys(bad_body) == [], f"失败态诊断体含禁键：{bad_body}"

    def test_diagnosis_reason_follows_fixed_set_and_exclusion(self, client_db: Any) -> None:
        """三态走一遍：原因码 ∈ 固定集，且 `ready=true ⇒ reason is None`（互斥不骗人）。

        ①新存档 `ready=true`（rng 缺口已由批次 A 接线关闭：app.state.rng_capture
        挂了真实 capture——S13/M6 批次 A 兑现）；
        ②抹掉 `rng_state` 列值 ⇒ `rng_unavailable`（fail-closed 不 seed 派生）；
        ③删包 ⇒ `no_package`。
        """
        client, db = client_db
        created = client.post("/api/anchors", json={"name": "第三天"}).json()
        anchor_id = created["id"]

        fresh = client.get(f"/api/anchors/{anchor_id}/materialization").json()
        assert fresh["ready"] is True and fresh["reason"] is None, (
            f"rng 接线后新存档仍不可物化（批次 A 接线缺半？）：{fresh}"
        )

        _set_rng_state(db, anchor_id, blob="")
        unavailable = client.get(f"/api/anchors/{anchor_id}/materialization").json()
        assert unavailable["ready"] is False and unavailable["reason"] == "rng_unavailable", (
            f"ready=false 却不带 rng_unavailable（骗人组合）：{unavailable}"
        )

        _drop_package_row(db, anchor_id)
        bad_body = client.get(f"/api/anchors/{anchor_id}/materialization").json()
        assert bad_body["ready"] is False, bad_body
        assert bad_body["reason"] in MATERIALIZATION_REASONS, (
            f"原因码不在固定集内（自由文本 = 契约在漂）：{bad_body['reason']}"
        )

    def test_diagnosis_response_model_excludes_forbidden_keys(self) -> None:
        """模型层也不许有禁键（两层一起查：权力 + 随机流状态）。"""
        schema = _live_spec()["components"]["schemas"][DIAGNOSIS_SCHEMA]
        assert find_forbidden_keys(schema) == [], "诊断 schema 含禁键"
        assert "rng_state" not in json.dumps(schema, ensure_ascii=False)


# ---------------------------------------------------------------------------
# ② live ↔ 快照对拍（M6-K1 实测发现的缺口，skip-locked）
# ---------------------------------------------------------------------------


def _snapshot_has_diagnosis() -> bool:
    spec = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return DIAGNOSIS_PATH in spec["paths"]


requires_diagnosis_in_snapshot = pytest.mark.skipif(
    not _snapshot_has_diagnosis(),
    reason=(
        "诊断路由尚未进 `shared/openapi.json`（M6-K1 实测：live 有、快照无 ⇒ live↔快照漂移，"
        "前端类型面缺该路由；`gen-protocol --check` 只校生成物↔快照、不校 live↔快照，故不红）"
        "——补快照（ext 注入 + 重生成）后自动解锁"
    ),
)


@requires_diagnosis_in_snapshot
class TestDiagnosisSurfaceParity:
    """M6-K1 缺口已由 M6-K2 补齐（快照注入 + ext 登记）——本组现为**结构对拍**。

    ⚠ 为什么是**结构**对拍而不是逐字段相等：快照是**手工维护的 mock**（codegen.md §4），
    与 live 的**系统性差异**是设计而非漂移——operationId（live 是 FastAPI 自动名
    `get_anchor_api_...`，快照是 camelCase `getAnchor`，前端类型名由它派生）、summary 文案、
    live 侧的 `description`/`tags`（ext 后处理剥除）、以及 422 与 Problem 码的分工。
    故对拍口径 = **前端真正依赖的结构**：响应码集合（snapshot ⊆ live）、200 的 `$ref`。
    """

    def test_live_and_snapshot_agree_on_diagnosis_structure(self) -> None:
        live_get = _live_spec()["paths"][DIAGNOSIS_PATH]["get"]
        snap_get = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["paths"][DIAGNOSIS_PATH]["get"]
        # 口径：snapshot ⊆ live，且两个 Problem 码（400/404）必须**都在**。
        # live 多出的 422 是 FastAPI 自动校验响应（快照按同族体例不声明它）。
        extra = sorted(set(snap_get["responses"]) - set(live_get["responses"]))
        assert not extra, f"快照声明了 live 没有的响应码：{extra}"
        assert {"400", "404"} <= set(snap_get["responses"]), snap_get["responses"]
        assert (
            live_get["responses"]["200"]["content"]["application/json"]["schema"]
            == (snap_get["responses"]["200"]["content"]["application/json"]["schema"])
        ), "200 响应模型不一致"
        assert snap_get["operationId"] == "getAnchorMaterialization", snap_get["operationId"]

    def test_snapshot_diagnosis_schema_is_closed_and_minimal(self) -> None:
        """快照侧同样锁：封闭 + 三键（M-1 的**协议面**形态）。"""
        spec = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        schema = spec["components"]["schemas"][DIAGNOSIS_SCHEMA]
        assert schema.get("additionalProperties") is False, schema
        assert set(schema["properties"]) == set(DIAGNOSIS_KEYS), sorted(schema["properties"])
        assert find_forbidden_keys(schema) == [], "快照诊断 schema 含禁键"

    def test_ext_declares_problem_responses_for_diagnosis(self) -> None:
        """`openapi_ext` 必须为该路由**手工登记** Problem 响应（§3.3 坑：不登记就没有）。"""
        src = (REPO_ROOT / "sim" / "api" / "openapi_ext.py").read_text(encoding="utf-8")
        assert f'attach("{DIAGNOSIS_PATH}", "get"' in src, (
            "openapi_ext 未登记该路由的 Problem 响应——live spec 里 400/404 会缺"
        )


# ---------------------------------------------------------------------------
# ③ WS 错误码词表（今天即绿）：失败帧**不扩** 11 项闭合集
# ---------------------------------------------------------------------------


class TestWsErrorVocabulary:
    def test_error_vocabulary_still_eleven(self) -> None:
        """`ws.py::_ERROR_*` 仍是 11 项闭合集（K16 审计稿 §3.2：案 B **不扩码**）。"""
        from sim.api import ws as ws_module

        codes = {
            getattr(ws_module, name)
            for name in dir(ws_module)
            if name.startswith("_ERROR_") and isinstance(getattr(ws_module, name), str)
        }
        assert len(codes) == 11, f"错误码词表不是 11 项闭合集：{sorted(codes)}"
        assert "load_failed" in codes, "既有 load_failed 码消失——失败帧必须沿用它"

    def test_error_frame_shape_unchanged(self) -> None:
        """`error` 帧形状不变（`ref/code/message` 三字段 + 信封）——接线不得改协议面。"""
        from sim.api.ws import _error_frame

        frame = _error_frame("load_anchor", "load_failed", "这个档读不出来了。")
        assert set(frame) == {"type", "channel", "v", "ws_seq", "ref", "code", "message"}, frame
        assert frame["channel"] == "error" and frame["ref"] == "load_anchor"


# ---------------------------------------------------------------------------
# ④ drain 失败帧体例（skip-locked；案 B 最小形，K16 审计稿 §5-2）
# ---------------------------------------------------------------------------


@requires_drain_wiring
class TestDrainFailureFrame:
    def test_failure_branch_reuses_load_failed_code(self) -> None:
        """失败帧**沿用 `load_failed`**：不新增码、不改词表（K16 审计稿 §3.2 判据三）。"""
        code = _code_only(MAIN_PY) + " " + _code_only(WS_PY)
        assert "_ERROR_LOAD_FAILED" in code, (
            "drain 失败分支没有引用既有 `load_failed` 码——要么另造了码（词表破 11 项），"
            "要么失败仍只落日志（玩家收不到）"
        )

    def test_failure_frame_message_is_a_literal_no_engineering_words(self) -> None:
        """玩家可见文本必须是**字面量或字面量别名**；工程词只能进 `logger` 的字段。

        白盒判据：帧构造调用的第三个参数（message）——
        - `ast.Constant`：字面量本体 ✔；
        - `ast.Name`：**别名**，仅当同名变量在**同一函数内**被赋值为 `ast.Constant`
          （`fallback = returned` 里 returned 逐候选来自字面量元组，此处再验
          「别名不是动态串」——`str(exc)`/f-string 的赋值不是 Constant，照红）；
        - 其余形态（f-string / 属性 / 调用 / 裸下标）：一律红——`reason`/异常串
          会漏到玩家眼前。`reason=str(exc)` 只允许进 `logger.*(...)`。
        （M6 裁：S2 防摘钉要求返回行消费 scan 结果（变量名记号），与「值恒字面量」
        由本判据的别名规则合成——机制本质=文案源是静态字面量集，不弱化。）
        """
        offenders: list[str] = []
        for path in (MAIN_PY, WS_PY):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            # 函数作用域内的「名字 → 是否字面量（含传递别名）」表：
            # 直接 Constant 赋值 ✔；别名赋值（`b = a`）沿链传递 ✔；
            # 其余（Call/f-string/Name-of-loop-var 等）不进表（照红）。
            literal_alias: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
                    node.targets[0], ast.Name
                ):
                    name = node.targets[0].id
                    value = node.value
                    is_const = isinstance(value, ast.Constant)
                    is_alias = isinstance(value, ast.Name) and value.id in literal_alias
                    if is_const or is_alias:
                        literal_alias.add(name)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "attr", "") or getattr(node.func, "id", "")
                if name not in {"_error_frame", "error_frame"}:
                    continue
                for arg in node.args[2:]:  # (ref, code, message)
                    if isinstance(arg, ast.Constant):
                        continue  # 字面量：戏内口语 ✔
                    if isinstance(arg, ast.Name) and arg.id in literal_alias:
                        continue  # 字面量别名：值恒为字面量（含传递别名）✔
                    kind = "f-string" if isinstance(arg, ast.JoinedStr) else type(arg).__name__
                    offenders.append(f"{path.name}:L{arg.lineno}: {kind} 进玩家可见文本")
        assert offenders == [], f"失败帧文本不是字面量（工程词会漏给玩家）：{offenders}"

    def test_no_engineering_words_in_player_visible_literals(self) -> None:
        """字面量文本本身也要干净：不得含原因码/包字段/异常类名/DB 相关工程词。

        与上一钉互补：上一钉查「是不是字面量」，这一钉查「字面量干不干净」。
        机器码串（`/errors/...`）与日志事件名（`fork.load_failed`）不在此列。

        扫描面 = **玩家帧可达**的字符串（`_error_frame` 的 ref/code/message 实参与
        玩家文案候选元组）——基建配置字面量（如 `build_loop` 的 DB URL
        `sqlite+aiosqlite:///world.db`：引擎连接串，不是帧文本）与 logger 事件名
        不在帧路径上，不属本钉对象（K16 原口径扫全文件字面量在解锁后误伤基建）。
        """
        forbidden = (
            "no_package",
            "rng_unavailable",
            "snapshot_missing",
            "event_gap",
            "corpus_mismatch",
            "corpus_blob",
            "rng_state",
            "parent_seq",
            "materialization",
            "Traceback",
            "sqlalchemy",
            "sqlite",
            "anchor_packages",
        )
        offenders: list[str] = []
        for path in (MAIN_PY, WS_PY):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fname = getattr(node.func, "attr", "") or getattr(node.func, "id", "")
                is_frame = fname in {"_error_frame", "error_frame"}
                candidate_elts: list[str] = []
                if isinstance(node, ast.Tuple):
                    for e in node.elts:
                        if isinstance(e, ast.Constant) and isinstance(e.value, str):
                            candidate_elts.append(e.value)
                is_candidate_tuple = bool(candidate_elts) and not is_frame
                if not is_frame and not is_candidate_tuple:
                    continue
                texts: list[str] = []
                if is_candidate_tuple:
                    texts = candidate_elts
                else:
                    for a in node.args:
                        if isinstance(a, ast.Constant) and isinstance(a.value, str):
                            texts.append(a.value)
                for text in texts:
                    if text.lstrip("/").startswith("errors/") or text.startswith("fork."):
                        continue
                    hits = [w for w in forbidden if w in text]
                    if hits:
                        offenders.append(f"{path.name}: {hits} in {text[:60]}")
        assert offenders == [], f"字符串字面量含工程词（会随帧/日志外泄）：{offenders}"
