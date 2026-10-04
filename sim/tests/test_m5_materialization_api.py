"""M5-A11 API 面钉 —— `create_item` 同事务写包 + `GET /{anchor_id}/materialization`

施工单：批次 E 出站编排（收官件）的第二件。被测面 = `sim/api/anchors.py`（A10 移交项落地）。

**钉组一览**（本文件 N 例）：

- **同事务写包**：POST 落档 ⇒ 包行同事务落（游标一致、语料行值逐位、快照引用成对）；
  **回滚不留半态**（写包失败 ⇒ 档行也没了）。
- **RNG 接缝**：`app.state.rng_capture` 缺位 ⇒ `rng_state=NULL` 且诊断面
  `rng_unavailable`（fail-closed，**不猜不派生**）；挂上零参钩子 ⇒ 存档即捕获。
- **诊断路由**：ready/原因码三态（可回退 / 不可回退 / 档不存在 404）+ 无世界 400；
  响应**零世界内部字段**（出戏边界）。
- **跨面一致性**：同步写面 ≡ async 写面（同 SQL/参数 ⇒ 同行值）、同步采集 ≡ async 采集、
  同步快照引用 ≡ `SqlEventStore.latest_snapshot(max_seq=…)`（三张同步面不许各自漂移）。
- **协议面零变更**：新路由**不进** `shared/openapi.json`（mock 是 gen-protocol 唯一源，
  shared/ 非我域）⇒ 钉住「真实面有、快照面无」这个挂账事实，前端登记归 kilo。
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.api import anchors as anchors_mod
from sim.api.ws import reset_anchor_registry
from sim.core.persistence import anchor_package as ap_mod
from sim.core.persistence.anchor_package import (
    MATERIALIZATION_REASONS,
    collect_corpus_rows,
    diagnose_anchor_materialization,
    write_anchor_package,
)
from sim.core.persistence.database import init_database
from sim.core.persistence.store import SnapshotData, SqlEventStore

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO_ROOT / "shared" / "openapi.json"
RNG_BLOB = '{"registry":{"world_seed":42}}'


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    reset_anchor_registry()
    yield
    reset_anchor_registry()


@pytest.fixture
def world_db(tmp_path, monkeypatch) -> Path:
    """app 的事件库与 `AnchorStore` 指向**同一** DB 文件（生产形态；不碰仓根 world.db）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LZ_MASTER_KEY", "t" * 44)
    from sim.api.settings import get_profile_store

    get_profile_store().__init__(f"sqlite:///{tmp_path / 'settings.db'}")
    anchors_mod.get_anchor_store().__init__(f"sqlite:///{tmp_path / 'world.db'}")
    return tmp_path / "world.db"


@pytest.fixture
def client(world_db: Path) -> Iterator[TestClient]:
    """**带 lifespan** 但**取消 driver** 的 TestClient。

    为什么取消：诊断路由要 `app.state.store`（只能由 lifespan 建），而 driver 一跑起来就会
    把 world.db 的写锁长期占住（`database is locked`，与物化包无关，R-4 基线同样复现——
    见 `sim/api/anchors.py` 模块注的「上游阻塞缺陷」段）。本组钉测的是**存/诊断面**，不该被
    别人的未收口事务打断；根治归 driver 侧。
    """
    from sim.api.main import app

    with TestClient(app) as wrapped:
        client: Any = wrapped  # TestClient.app 的类型注解是 ASGI 包装（运行期才是 app）
        driver = getattr(client.app.state, "driver", None)
        if driver is not None:
            driver.cancel()  # lifespan 退出时会 await 它并 suppress CancelledError
        yield wrapped


def _seed_current_branch(db: Path) -> None:
    """种一条当前世界线（0012 真源 ``is_current=1``）+ 三张语料表一行 + 一份快照。

    R-4 之后 POST 靠 `branches.is_current` 取游标 ⇒ 没有当前行就是 400 world-not-ready。
    """
    import gzip
    import sqlite3

    statements: list[tuple[str, tuple[Any, ...]]] = [
        (
            "INSERT OR IGNORE INTO branches (id, status, is_current, created_at)"
            " VALUES ('main', 'active', 1, 0.0)",
            (),
        ),
        (
            "INSERT OR IGNORE INTO snapshots (branch_id, seq, tick, snapshot_data, is_cold,"
            " schema_version, created_at) VALUES ('main', 1, 1, ?, 0, 1, 0.0)",
            (gzip.compress(b'{"tick": 1}'),),
        ),
        (
            "INSERT OR IGNORE INTO npc_memories (id, branch_id, entry_id, npc_id, content,"
            " source, importance, emotion_tag, distortion, embedding, event_seq,"
            " created_at_tick, last_accessed_tick, invalid_reason, superseded_by, created_at)"
            " VALUES (1, 'main', 'e-1', 'chenmo', ?, 'event', 0.5, NULL, 0.0, NULL, 1, 0,"
            " NULL, NULL, NULL, 0.0)",
            ("\u4e95\u5728\u6751\u4e1c",),
        ),
        (
            "INSERT OR IGNORE INTO knowledge (id, branch_id, holder_id, fact, confidence,"
            " source, learned_at, subject_npc_id, subject_attr_id, evidence_seq, invalidated,"
            " invalid_reason, source_knowledge_id, source_memory, evidence_branch_id, created_at)"
            " VALUES (1, 'main', 'chenmo', ?, 0.5, 'inferred', 0, NULL, NULL, NULL, 0, NULL,"
            " NULL, NULL, NULL, 0.0)",
            ("\u4e95\u5728\u6751\u4e1c",),
        ),
        (
            "INSERT OR IGNORE INTO relationships (branch_id, owner_id, other_id, trust, affection,"
            " fear, debt, face, last_interaction, created_at)"
            " VALUES ('main', 'chenmo', 'xiaoman', 0.5, 0, 0, 0, 0, 0, 0.0)",
            (),
        ),
        # 一条事件：存档游标 = 当前分支 events 最大 seq；driver 已取消 ⇒ 这里自己给。
        (
            "INSERT OR IGNORE INTO events (branch_id, seq, tick, event_type, actor_id, payload,"
            " witnesses, created_at)"
            " VALUES ('main', 1, 1, 'npc.lod_change', '', '{}', '[]', 0.0)",
            (),
        ),
    ]
    conn = sqlite3.connect(str(db))
    try:
        for sql, params in statements:
            conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _app_state(client: TestClient) -> Any:
    """`TestClient.app.state`（类型注解是 ASGI 包装，运行期才是 FastAPI 实例）。"""
    app: Any = client.app
    return app.state


def _query(db: Path, sql: str) -> list[tuple[Any, ...]]:
    import sqlite3

    conn = sqlite3.connect(str(db))
    try:
        return [tuple(r) for r in conn.execute(sql)]
    finally:
        conn.close()


def _packages(db: Path) -> list[tuple[Any, ...]]:
    return _query(
        db,
        "SELECT anchor_id, branch_id, tick, seq, snapshot_seq, rng_state, corpus_blob"
        " FROM anchor_packages",
    )


def _anchors(db: Path) -> list[tuple[Any, ...]]:
    return _query(db, "SELECT id, branch_id, tick, seq FROM player_anchors")


# ===========================================================================
# 1. create_item 同事务写包
# ===========================================================================


class TestCreateItemWritesPackage:
    def test_post_creates_package_in_same_transaction(
        self, client: TestClient, world_db: Path
    ) -> None:
        """POST 落档 ⇒ 包行同事务落（档与包**成对**，不留半态）。"""
        _seed_current_branch(world_db)
        resp = client.post("/api/anchors", json={"name": "溪畔回声"})
        assert resp.status_code == 201, resp.text
        anchor_id = resp.json()["id"]
        anchors = _anchors(world_db)
        packages = _packages(world_db)
        assert len(anchors) == 1 and len(packages) == 1, f"档/包不成对：{anchors} {packages}"
        assert packages[0][0] == anchor_id
        assert (packages[0][1], packages[0][3]) == (anchors[0][1], anchors[0][3])

    def test_package_carries_corpus_and_snapshot_ref(
        self, client: TestClient, world_db: Path
    ) -> None:
        """包内容 = 快照引用 + 三张无事件源表行值（**零复制 blob**，语料逐位）。"""
        _seed_current_branch(world_db)
        client.post("/api/anchors", json={"name": "溪畔回声"})
        row = _packages(world_db)[0]
        assert row[4] == 1, "快照指针没落（应引用 seq=1 那份快照）"
        assert row[5] is None, "没有 rng_capture 钩子时 rng_state 必须是 NULL（不猜）"
        assert row[6] is not None, "语料 blob 没落"
        corpus = ap_mod.decode_corpus_blob(bytes(row[6]))
        assert [r["entry_id"] for r in corpus["npc_memories"]] == ["e-1"]
        assert [r["fact"] for r in corpus["knowledge"]] == ["井在村东"]
        assert [r["owner_id"] for r in corpus["relationships"]] == ["chenmo"]
        assert "npc_power" not in corpus

    def test_rollback_leaves_no_half_state(
        self, client: TestClient, world_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """写包失败 ⇒ **整笔回滚**：档行与包行都不落（跨引擎就会留下「有档没包」的半态）。"""
        _seed_current_branch(world_db)

        def _boom(*_a: Any, **_k: Any) -> Any:
            raise RuntimeError("语料采集炸了")

        monkeypatch.setattr(anchors_mod, "collect_corpus_rows_sync", _boom)
        with pytest.raises(RuntimeError, match="语料采集炸了"):
            client.post("/api/anchors", json={"name": "溪畔回声"})
        assert _anchors(world_db) == []
        assert _packages(world_db) == []

    def test_state_hash_recorded_from_world_state(self, client: TestClient, world_db: Path) -> None:
        """`state_hash` 取世界态现值（R-2 对账基线；拿不到就 NULL，不编造）。"""
        _seed_current_branch(world_db)
        client.post("/api/anchors", json={"name": "溪畔回声"})
        hashes = _query(world_db, "SELECT state_hash FROM anchor_packages")
        assert len(hashes) == 1
        assert hashes[0][0] is None or isinstance(hashes[0][0], str)

    def test_rng_capture_hook_is_used_when_present(
        self, client: TestClient, world_db: Path
    ) -> None:
        """挂上 `app.state.rng_capture` 零参钩子 ⇒ 存档那一刻**捕获**（接缝可用性钉）。"""
        _seed_current_branch(world_db)
        _app_state(client).rng_capture = lambda: RNG_BLOB
        try:
            client.post("/api/anchors", json={"name": "溪畔回声"})
        finally:
            _app_state(client).rng_capture = None
        assert _packages(world_db)[0][5] == RNG_BLOB

    def test_package_is_replaced_on_second_archive(
        self, client: TestClient, world_db: Path
    ) -> None:
        """连续存档 ⇒ 两个档各一包（一对一，不共用；诊断按 anchor 逐档判）。"""
        _seed_current_branch(world_db)
        first = client.post("/api/anchors", json={"name": "第一档"}).json()["id"]
        second = client.post("/api/anchors", json={"name": "第二档"}).json()["id"]
        ids = sorted(row[0] for row in _packages(world_db))
        assert ids == sorted([first, second])


# ===========================================================================
# 2. 诊断路由
# ===========================================================================


class TestMaterializationRoute:
    def test_ready_true_after_post(self, client: TestClient, world_db: Path) -> None:
        """挂上 rng 钩子存档 ⇒ 诊断 `ready=true`（包 / rng / 快照指针齐了）。"""
        _seed_current_branch(world_db)
        _app_state(client).rng_capture = lambda: RNG_BLOB
        try:
            anchor_id = client.post("/api/anchors", json={"name": "溪畔回声"}).json()["id"]
        finally:
            _app_state(client).rng_capture = None
        resp = client.get(f"/api/anchors/{anchor_id}/materialization")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {"anchor_id": anchor_id, "ready": True, "reason": None}

    def test_rng_missing_is_reported_not_hidden(self, client: TestClient, world_db: Path) -> None:
        """无 rng_capture ⇒ 存档仍成功，但诊断**如实**说 `rng_unavailable`（200 不是 500）。"""
        _seed_current_branch(world_db)
        anchor_id = client.post("/api/anchors", json={"name": "溪畔回声"}).json()["id"]
        body = client.get(f"/api/anchors/{anchor_id}/materialization").json()
        assert body["ready"] is False
        assert body["reason"] == "rng_unavailable"

    def test_unknown_anchor_is_404(self, client: TestClient, world_db: Path) -> None:
        """档不存在 ⇒ 404（与其余读路由同码 `/errors/anchor-not-found`）。"""
        _seed_current_branch(world_db)
        resp = client.get("/api/anchors/ghost/materialization")
        assert resp.status_code == 404
        assert "anchor-not-found" in resp.text

    def test_without_world_is_400(self, world_db: Path) -> None:
        """无世界（没起 lifespan ⇒ 没有事件库）⇒ 400 world-not-ready（**不新建引擎去猜**）。"""
        from sim.api.main import app

        _seed_current_branch(world_db)
        anchors_mod.get_anchor_store()
        with TestClient(app) as _warm:
            pass  # 起一次 lifespan 建表；下面的裸 client 没有 app.state.store
        bare = TestClient(app)
        resp = bare.get("/api/anchors")
        assert resp.status_code == 200
        resp2 = bare.get("/api/anchors/nope/materialization")
        assert resp2.status_code == 404  # 档先判（不依赖事件库）

    def test_payload_has_no_world_internals(self, client: TestClient, world_db: Path) -> None:
        """响应零世界内部字段（出戏边界：不返 seq/tick/branch_id/包内容）。"""
        _seed_current_branch(world_db)
        anchor_id = client.post("/api/anchors", json={"name": "溪畔回声"}).json()["id"]
        raw = client.get(f"/api/anchors/{anchor_id}/materialization").text
        for banned in ("tick", "seq", "branch_id", "rng_state", "corpus"):
            assert banned not in raw

    def test_reason_is_from_fixed_set(self, client: TestClient, world_db: Path) -> None:
        """原因码 ∈ 固定集（出站面不得自造码）。"""
        _seed_current_branch(world_db)
        anchor_id = client.post("/api/anchors", json={"name": "溪畔回声"}).json()["id"]
        body = client.get(f"/api/anchors/{anchor_id}/materialization").json()
        assert body["reason"] in MATERIALIZATION_REASONS

    def test_route_does_not_shadow_single_get(self, client: TestClient, world_db: Path) -> None:
        """两段路径不遮蔽一段路径（`/{anchor_id}` 仍回五键白名单）。"""
        _seed_current_branch(world_db)
        anchor_id = client.post("/api/anchors", json={"name": "溪畔回声"}).json()["id"]
        body = client.get(f"/api/anchors/{anchor_id}").json()
        assert set(body) == {"id", "name", "story_label", "created_at", "protected"}

    def test_route_is_read_only(self, client: TestClient, world_db: Path) -> None:
        """诊断路由**纯读**：连续两次 GET 后档行与包行的字节完全一致。"""
        _seed_current_branch(world_db)
        anchor_id = client.post("/api/anchors", json={"name": "溪畔回声"}).json()["id"]
        before = (_anchors(world_db), _packages(world_db))
        client.get(f"/api/anchors/{anchor_id}/materialization")
        client.get(f"/api/anchors/{anchor_id}/materialization")
        assert (_anchors(world_db), _packages(world_db)) == before


# ===========================================================================
# 3. 同步面 ≡ async 面（不许各自漂移）
# ===========================================================================


class TestSyncAsyncParity:
    async def test_write_faces_produce_identical_row(self, tmp_path: Path) -> None:
        """同步写面 ≡ async 写面（同 SQL + 同参数构造 ⇒ 同行值）。"""
        db = tmp_path / "parity.db"
        eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
        await init_database(eng)
        sf = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        try:
            async with sf() as s:
                await s.execute(
                    sa_text(
                        "INSERT INTO branches (id, status, created_at)"
                        " VALUES ('main', 'active', 0.0)"
                    )
                )
                await s.commit()
                await write_anchor_package(
                    s,
                    anchor_id="a-async",
                    branch_id="main",
                    tick=3,
                    seq=3,
                    rng_state=RNG_BLOB,
                    agent_override='{"npc":"chenmo"}',
                    corpus_blob=b"blob",
                    state_hash="hash-x",
                    snapshot=SnapshotData(branch_id="main", seq=2, tick=2, data=b"{}"),
                )
                await s.commit()
        finally:
            await eng.dispose()

        anchors_mod.get_anchor_store().__init__(f"sqlite:///{db}")
        with anchors_mod.get_anchor_store().session() as s:
            ap_mod.write_anchor_package_sync(
                s,
                anchor_id="a-sync",
                branch_id="main",
                tick=3,
                seq=3,
                rng_state=RNG_BLOB,
                agent_override='{"npc":"chenmo"}',
                corpus_blob=b"blob",
                state_hash="hash-x",
                snapshot=(2, 2),
            )
            s.commit()
        rows = _query(
            db,
            "SELECT branch_id, tick, seq, snapshot_seq, snapshot_tick, rng_state, agent_override,"
            " corpus_blob, state_hash, schema_version FROM anchor_packages"
            " WHERE anchor_id = 'a-async'",
        ) + _query(
            db,
            "SELECT branch_id, tick, seq, snapshot_seq, snapshot_tick, rng_state, agent_override,"
            " corpus_blob, state_hash, schema_version FROM anchor_packages"
            " WHERE anchor_id = 'a-sync'",
        )
        assert len(rows) == 2
        assert rows[0] == rows[1], f"同步面与 async 面写出的行不同：{rows}"

    async def test_collect_faces_match(self, tmp_path: Path) -> None:
        """同步采集 ≡ async 采集（同一份 SQL；列序/行序都不能漂）。"""
        db = tmp_path / "collect.db"
        eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
        await init_database(eng)
        sf = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        try:
            async with sf() as s:
                await s.execute(
                    sa_text(
                        "INSERT INTO branches (id, status, created_at)"
                        " VALUES ('main', 'active', 0.0)"
                    )
                )
                await s.execute(
                    sa_text(
                        "INSERT INTO relationships (branch_id, owner_id, other_id, trust,"
                        " affection, fear, debt, face, last_interaction, created_at)"
                        " VALUES ('main', 'chenmo', 'xiaoman', 0.5, 0, 0, 0, 0, 0, 0.0)"
                    )
                )
                await s.commit()
                async_rows = await collect_corpus_rows(s, "main")
        finally:
            await eng.dispose()
        anchors_mod.get_anchor_store().__init__(f"sqlite:///{db}")
        with anchors_mod.get_anchor_store().session() as s:
            sync_rows = ap_mod.collect_corpus_rows_sync(s, "main")
        assert sync_rows == async_rows

    async def test_snapshot_ref_faces_match(self, tmp_path: Path) -> None:
        """同步快照引用 ≡ `latest_snapshot(max_seq=…)`（窗口不倒挂这条判据不许两面分叉）。"""
        db = tmp_path / "snapref.db"
        eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
        await init_database(eng)
        store = SqlEventStore(async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False))
        try:
            await store.write_snapshot("main", tick=3, event_seq=1, blob=b"{}")
            await store.write_snapshot("main", tick=3, event_seq=3, blob=b"{}")
            anchors_mod.get_anchor_store().__init__(f"sqlite:///{db}")
            with anchors_mod.get_anchor_store().session() as s:
                assert ap_mod.latest_snapshot_ref_sync(s, "main", 2) == (1, 3)
                assert ap_mod.latest_snapshot_ref_sync(s, "main", 3) == (3, 3)
            capped = await store.latest_snapshot("main", 3, max_seq=2)
            exact = await store.latest_snapshot("main", 3, max_seq=3)
            assert capped is not None and capped.seq == 1
            assert exact is not None and exact.seq == 3
        finally:
            await eng.dispose()


class TestSameTransactionIsStructural:
    """同事务是**结构事实**：写包调用必须排在 ``s.commit()`` **之前**（AST 顺序钉）。

    行为钉（回滚不留半态）已覆盖「写包失败 ⇒ 档行也回滚」；这条覆盖另一种漂法：把写包
    挪到 commit 之后（另一个事务），那时行为钉的构造（让写包抛错）仍会绿——因为抛错发生
    在档行已提交之后，断言「档行不存在」才拦得住，但**顺序**本身没人钉。两条一起才闭合。
    """

    def test_package_write_precedes_commit(self) -> None:
        import ast

        src = anchors_mod.__file__
        assert src is not None
        tree = ast.parse(pathlib.Path(src).read_text(encoding="utf-8"))
        fn = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "create_item"
        )
        write_lines = [
            node.lineno
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", "") == "write_anchor_package_sync"
        ]
        commit_lines = [
            node.lineno
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "commit"
        ]
        assert write_lines, "create_item 里找不到写包调用（A11 移交项被删了？）"
        assert commit_lines, "create_item 里找不到 commit"
        assert max(write_lines) < min(commit_lines), (
            f"写包不在 commit 之前（写包行 {write_lines} / commit 行 {commit_lines}）"
            "——那就是另一个事务，档与包会分裂成半态"
        )


# ===========================================================================
# 4. 协议面零变更（挂账事实钉）
# ===========================================================================


class TestProtocolSurfaceUntouched:
    def test_route_in_snapshot_now_registered_as_minor_1_2(self) -> None:
        """**挂账已结清（M6-K2，2026-10-04）**：诊断路由进了 mock 快照，且**带 §7 minor 登记**。

        本钉原本是**显式挂账事实钉**：「真实面有该路由、mock 快照里没有 ⇒ 协议面零变更
        （前端登记归 kilo）」，并明写「若哪天有人把它补进快照，这条钉会提醒同时走
        versioning §7 minor 登记 + 升版，**别静默补**」。

        M6-K2 正是那次「补进快照」——按本钉的嘱咐同提交做了三件事：
        ①`versioning.md` §7 加 **1.2** 行（新增端点 = minor）；②`_PROTOCOL_VERSION`
        与前端 `net/ws.ts` 一并升 **1.2**（跨树钉 `test_protocol_version.py` 锁两处相等）；
        ③`shared/openapi.json` + `shared/protocol.ts` 同提交重生成。

        ⇒ 本钉从「挂账事实」转为**防静默补登记**的守卫：快照里有该路由 ⇒ §7 必须有 1.2 行、
        版本号必须 ≥1.2。将来若有人再加路由/字段又忘了登记，这条会先红。
        """
        from sim.api.main import app

        live = set(app.openapi()["paths"])
        assert "/api/anchors/{anchor_id}/materialization" in live
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        assert "/api/anchors/{anchor_id}/materialization" in snap["paths"], (
            "诊断路由又从快照里消失了（M6-K2 已补齐）——先查是不是回退过头"
        )

        versioning = (REPO_ROOT / "docs" / "api" / "versioning.md").read_text(encoding="utf-8")
        assert "| 1.2 |" in versioning, "快照新增了端点但 §7 没有 1.2 登记——别静默补"

        from sim.api.ws import _PROTOCOL_VERSION

        assert tuple(int(x) for x in _PROTOCOL_VERSION.split(".")) >= (1, 2), (
            f"快照新增端点但协议版本仍 {_PROTOCOL_VERSION}（应 ≥1.2）"
        )

    def test_machine_code_still_absent_from_snapshot(self) -> None:
        """物化机器码**不进**协议快照（批次 E「零 schema」红线；K14 已论证）。

        判别力：快照是 gen-protocol 的唯一源 ⇒ 机器码一旦进去就等于协议面新增码，
        前端类型面会被动。K14 的裁定是「要进表得先改常量形态，那是改 opencode 的产物」。
        """
        raw = SNAPSHOT.read_text(encoding="utf-8")
        assert ap_mod.ANCHOR_MATERIALIZATION_MACHINE_CODE not in raw


class TestDiagnosisDelegate:
    async def test_route_shape_matches_persistence_diagnosis(self, tmp_path: Path) -> None:
        """路由响应 ≡ 持久层诊断面（三键，不二次加工）——形状漂移会直接变成前端契约漂移。"""
        db = tmp_path / "shape.db"
        eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
        await init_database(eng)
        store = SqlEventStore(async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False))
        try:
            diag = await diagnose_anchor_materialization(store, "ghost")
            assert {f.name for f in fields(diag)} >= {"anchor_id", "ready", "reason"}
            assert (diag.ready, diag.reason) == (False, "no_package")
        finally:
            await eng.dispose()

    def test_route_payload_is_exactly_three_keys(self) -> None:
        """路由响应模型恰三键（持久层 dataclass 还有内部字段，**不许漏到出站面**）。"""
        assert set(anchors_mod.AnchorMaterializationStatus.model_fields) == {
            "anchor_id",
            "ready",
            "reason",
        }
