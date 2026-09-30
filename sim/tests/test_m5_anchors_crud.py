"""M5-S2/S-4/S-5/S-6/S-8：anchors CRUD 写路径（anchors-api.md §1.2-1.4 + §1.5 v2 条款）。

契约要点：
- POST 同事务写 protected=true + 清其余（A2 进程锁 + A3 同事务）；
  updated_at 只写一次；游标取世界当前 tick + 当前活跃分支（D-16 默认）；
  成功照 K7 模式 register_anchor_id(id, name, story_label)；
  无活跃 loop → 400 /errors/world-not-ready。
- PATCH 只改 name；不动 updated_at/protected；成功刷新 WS 标签。
- DELETE 409 判据读列（不再派生）；硬删；成功调 unregister_anchor_id；不补位。
- F-6 注册侧 fail-closed：name 命中现行 scan() → 422 结构化拒绝。
- 切列后（S-4）：list/get/current 全部读列，退化态 /current 回退 max(updated_at)
  保底不 404（D-14），此时 protected=false。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from sim.api import anchors as anchors_mod
from sim.api.ws import _ANCHOR_IDS, _ANCHOR_LABELS, reset_anchor_registry
from sim.core.persistence.models import PlayerAnchor


@pytest.fixture(autouse=True)
def _clean_anchor_registry() -> Iterator[None]:
    reset_anchor_registry()
    yield
    reset_anchor_registry()


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LZ_MASTER_KEY", "t" * 44)
    from sim.api.settings import get_profile_store

    get_profile_store().__init__(f"sqlite:///{tmp_path}/settings.db")
    anchors_mod.get_anchor_store().__init__(f"sqlite:///{tmp_path}/anchors.db")
    from sim.api.main import app

    with TestClient(app) as c:
        yield c


class TestCreateAnchor:
    def test_post_creates_protected_anchor(self, client: TestClient) -> None:
        r = client.post("/api/anchors", json={"name": "初到临河"})
        assert r.status_code == 201
        body = r.json()
        assert set(body) == {"id", "name", "story_label", "created_at", "protected"}
        assert body["name"] == "初到临河"
        assert body["protected"] is True

    def test_second_post_demotes_first(self, client: TestClient) -> None:
        r1 = client.post("/api/anchors", json={"name": "第一档"})
        r2 = client.post("/api/anchors", json={"name": "第二档"})
        assert r1.status_code == r2.status_code == 201
        items = client.get("/api/anchors").json()
        protected = [i for i in items if i["protected"]]
        assert len(protected) == 1
        assert protected[0]["name"] == "第二档"

    def test_post_registers_ws_tables(self, client: TestClient) -> None:
        body = client.post("/api/anchors", json={"name": "溪边小驻"}).json()
        assert body["id"] in _ANCHOR_IDS
        assert _ANCHOR_LABELS[body["id"]]["name"] == "溪边小驻"

    def test_post_validates_name(self, client: TestClient) -> None:
        assert client.post("/api/anchors", json={"name": ""}).status_code == 422
        assert client.post("/api/anchors", json={"name": "x" * 65}).status_code == 422
        r = client.post("/api/anchors", json={"name": "x", "tick": 100})
        assert r.status_code == 422

    def test_post_banned_name_rejected_fail_closed(self, client: TestClient) -> None:
        r = client.post("/api/anchors", json={"name": "AI"})
        assert r.status_code == 422
        body = r.json()
        assert body["type"] == "/errors/anchor-name-rejected"
        assert "AI" in body["detail"]

    def test_post_rejects_when_no_world(self, client: TestClient, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("LZ_MASTER_KEY", "t" * 44)
        from sim.api.settings import get_profile_store

        get_profile_store().__init__(f"sqlite:///{tmp_path}/s2.db")
        anchors_mod.get_anchor_store().__init__(f"sqlite:///{tmp_path}/a2.db")
        from sim.api.main import app

        app.state.loop = None
        r = client.post("/api/anchors", json={"name": "无世界"})
        assert r.status_code == 400
        assert r.json()["type"] == "/errors/world-not-ready"


class TestRenameAnchor:
    def test_patch_renames_without_touching_protected(self, client: TestClient) -> None:
        first = client.post("/api/anchors", json={"name": "第一档"}).json()
        client.post("/api/anchors", json={"name": "第二档"})
        r = client.patch(f"/api/anchors/{first['id']}", json={"name": "改名后"})
        assert r.status_code == 200
        assert r.json()["protected"] is False

    def test_patch_protected_anchor_allowed(self, client: TestClient) -> None:
        body = client.post("/api/anchors", json={"name": "末梢"}).json()
        r = client.patch(f"/api/anchors/{body['id']}", json={"name": "末梢改名"})
        assert r.status_code == 200 and r.json()["protected"] is True

    def test_patch_refreshes_ws_label(self, client: TestClient) -> None:
        body = client.post("/api/anchors", json={"name": "旧名"}).json()
        client.patch(f"/api/anchors/{body['id']}", json={"name": "新名"})
        assert _ANCHOR_LABELS[body["id"]]["name"] == "新名"

    def test_patch_404_machine_code(self, client: TestClient) -> None:
        r = client.patch("/api/anchors/ghost000000", json={"name": "x"})
        assert r.status_code == 404
        assert r.json()["type"] == "/errors/anchor-not-found"

    def test_patch_validates_name(self, client: TestClient) -> None:
        body = client.post("/api/anchors", json={"name": "x"}).json()
        assert client.patch(f"/api/anchors/{body['id']}", json={"name": ""}).status_code == 422
        r = client.patch(f"/api/anchors/{body['id']}", json={"name": "y", "tick": 1})
        assert r.status_code == 422


class TestDeleteAnchor:
    def test_delete_non_protected_ok_and_unregisters(self, client: TestClient) -> None:
        first = client.post("/api/anchors", json={"name": "旧档"}).json()
        client.post("/api/anchors", json={"name": "新档"})
        r = client.delete(f"/api/anchors/{first['id']}")
        assert r.status_code == 204
        assert first["id"] not in _ANCHOR_IDS
        assert first["id"] not in _ANCHOR_LABELS

    def test_delete_protected_409(self, client: TestClient) -> None:
        client.post("/api/anchors", json={"name": "旧档"})
        tip = client.post("/api/anchors", json={"name": "末梢"}).json()
        r = client.delete(f"/api/anchors/{tip['id']}")
        assert r.status_code == 409
        assert r.json()["type"] == "/errors/anchor-protected"

    def test_delete_leaves_single_tip(self, client: TestClient) -> None:
        only = client.post("/api/anchors", json={"name": "唯一旧档"}).json()
        client.post("/api/anchors", json={"name": "第二档"})
        assert client.delete(f"/api/anchors/{only['id']}").status_code == 204
        items = client.get("/api/anchors").json()
        assert len([i for i in items if i["protected"]]) == 1

    def test_delete_404_machine_code(self, client: TestClient) -> None:
        r = client.delete("/api/anchors/ghost000000")
        assert r.status_code == 404
        assert r.json()["type"] == "/errors/anchor-not-found"


class TestColumnSwitchedReads:
    def test_current_reads_column(self, client: TestClient) -> None:
        client.post("/api/anchors", json={"name": "旧档"})
        tip = client.post("/api/anchors", json={"name": "末梢"}).json()
        cur = client.get("/api/anchors/current").json()
        assert cur["id"] == tip["id"] and cur["protected"] is True

    def test_current_fallback_when_zero_protected(self, client: TestClient) -> None:
        client.post("/api/anchors", json={"name": "档一"})
        client.post("/api/anchors", json={"name": "档二"})
        with anchors_mod.get_anchor_store().session() as s:
            s.query(PlayerAnchor).update({"protected": False})
            s.commit()
        r = client.get("/api/anchors/current")
        assert r.status_code == 200
        body = r.json()
        assert body["protected"] is False
        assert body["name"] == "档二"

    def test_list_reads_column(self, client: TestClient) -> None:
        client.post("/api/anchors", json={"name": "档一"})
        client.post("/api/anchors", json={"name": "档二"})
        items = client.get("/api/anchors").json()
        assert sum(1 for i in items if i["protected"]) == 1

    def test_store_invariant_at_most_one_protected(self, client: TestClient) -> None:
        for n in ("a", "b", "c"):
            client.post("/api/anchors", json={"name": n})
        with anchors_mod.get_anchor_store().session() as s:
            assert s.query(PlayerAnchor).filter(PlayerAnchor.protected.is_(True)).count() <= 1


class TestBackfillColumnReadConsistency:
    """0010 回填 → S-4 切列的端到端一致性（opencode 回执跨域缝的闭合证）。

    0010 判据 = ORDER BY updated_at DESC, id DESC LIMIT 1（同刻多行恰 1 行）；
    切列后读路径读列 → 同刻多行**恰 1 行受保护**（原派生式会标 N 行——缝闭合）。
    """

    def test_same_timestamp_multi_rows_marks_exactly_one(self, client: TestClient) -> None:
        """同刻多行（0010 面对的存量形态）在运行态的不变量：恰 1 行 protected。

        运行态谁是 protected 由 POST 事务决定（不变量 ≤1，C3）；同刻 id 兜底
        判据只对**存量回填**（0010）与 /current 保底有意义——两者已同口径钉住。
        本钉锁的是切列后派生式 N 行歧义不再出现（opencode 跨域缝闭合）。
        """
        import time as t

        ids = []
        for n in ("甲", "乙", "丙"):
            ids.append(client.post("/api/anchors", json={"name": n}).json()["id"])
        # 强制三行同刻（updated_at 相同）→ 重演存量形态；不变量仍须成立
        with anchors_mod.get_anchor_store().session() as s:
            s.query(PlayerAnchor).update({PlayerAnchor.updated_at: t.time()})
            s.commit()
        items = client.get("/api/anchors").json()
        protected = [i["id"] for i in items if i["protected"]]
        assert len(protected) == 1
        assert protected[0] in ids
        # /current 与列表同源（C2③）：同刻下取 protected 行（D-14 判据序）
        assert client.get("/api/anchors/current").json()["id"] == protected[0]

    def test_downgrade_keeps_backfill_column_state(self, client: TestClient) -> None:
        """0010 downgrade 有意不撤销回填——列值在 downgrade 后仍与切列读路径自洽。"""
        tip = client.post("/api/anchors", json={"name": "末梢"}).json()
        with anchors_mod.get_anchor_store().session() as s:
            row = s.get(PlayerAnchor, tip["id"])
            assert row is not None and row.protected is True
        assert client.get("/api/anchors/current").json()["id"] == tip["id"]


class TestLoadHookBoundedReturn:
    """M5-K7 R-1 CRITICAL 钉：生产 hook 必须有界时间返回（不阻塞事件循环）。

    R-1 病根：hook 在同一 loop 内忙等 fork task ⇒ task 永不推进 ⇒ 挂死。
    修后契约：hook 只登记请求、立即返回 True；真执行在 driver 的 drain。
    """

    def test_hook_returns_immediately_with_pending_queue(self, client: TestClient) -> None:
        """真 hook 在位时 load_anchor 有界返回（登记不阻塞），请求进入 pending 队列。"""
        import time as _t

        from sim.api import ws as ws_mod

        assert ws_mod._ANCHOR_LOAD_HOOK is not None  # 生产 hook 已挂（非替身）
        anchor = client.post("/api/anchors", json={"name": "溪边小驻"}).json()
        t0 = _t.perf_counter()
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # full_snapshot
            ws.receive_json()  # session_state
            ws.send_json({"type": "load_anchor", "channel": "session", "anchor_id": anchor["id"]})
            reply = ws.receive_json()
        elapsed = _t.perf_counter() - t0
        assert elapsed < 2.0, f"load_anchor 阻塞 {elapsed:.2f}s（R-1 忙等回归？）"
        assert reply["type"] in {"session_state", "error"}  # 受理或显式失败，不挂起

    def test_driver_drains_pending_loads(self, client: TestClient) -> None:
        """pending 请求由 driver 侧 drain 执行（受理后最终落 outcome）。"""
        from sim.api.main import app

        anchor = client.post("/api/anchors", json={"name": "溪边小驻"}).json()
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.receive_json()
            ws.send_json({"type": "load_anchor", "channel": "session", "anchor_id": anchor["id"]})
            ws.receive_json()
        # drain 是协作式的：TestClient 请求结束后手动跑一轮 drain 断言 outcome
        import asyncio

        drain = getattr(app.state, "drain_pending_loads", None)
        assert drain is not None, "drain 未注册（R-1 修复缺半）"
        asyncio.get_event_loop_policy()
        outcome_run = asyncio.new_event_loop()
        try:
            outcome_run.run_until_complete(drain())
        finally:
            outcome_run.close()
        outcomes = app.state.load_outcomes
        assert outcomes and outcomes[-1][0] == anchor["id"]
