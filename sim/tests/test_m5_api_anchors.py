"""M5-K7 anchors 最小实现（kilo 部署债 #1：_ANCHOR_IDS 替身 → 落库路径）。

契约（anchors-api.md §4/§5 清单 #2 子集）：
- `GET /api/anchors` 读 `player_anchors` 表 → `AnchorListItem` 五键白名单
  列表（**空库回 200 + `[]`，非 404**——协议 §5 #6 最易写错一条）。
- 每条落库后调 `register_anchor_id()` 把 id 注进 WS 分发块的同步查表集
  （ws.py:410 `_ANCHOR_IDS`）；`load_anchor` 的 `load_failed` 判定转由它供数。
- `GET /api/anchors/{anchor_id}` 按 id 查单项（§4「按 id 查」）；不存在回 404。

**不在本批次**（§5 清单余项，Claude 域）：POST/PATCH/DELETE 三路由、
`sim/api/errors.py` ProblemDetail handler、`protected` 新列迁移、
`AnchorCreate`/`AnchorRename` 请求模型。因此本文件的 404 断言只锁
status 与 body 不含内部字段，不锁 ProblemDetail 四键形（那归 #3/#4）。
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sim.api import anchors as anchors_mod
from sim.api.ws import _ANCHOR_IDS, reset_anchor_registry
from sim.core.persistence.models import PlayerAnchor
from sim.core.tick import TickLoop


@pytest.fixture(autouse=True)
def _clean_anchor_registry() -> Iterator[None]:
    reset_anchor_registry()
    yield
    reset_anchor_registry()


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    """临时 sqlite + master key（沿用 test_m2_openapi_rework.py fixture 写法）。"""
    from sim.api.settings import get_profile_store

    monkeypatch.setenv("LZ_MASTER_KEY", "t" * 44)
    store = get_profile_store()
    store.__init__(f"sqlite:///{tmp_path}/world.db")
    anchors_mod.get_anchor_store().__init__(f"sqlite:///{tmp_path}/world.db")
    from sim.api.main import app

    return TestClient(app)


def _seed(store: Any, n: int = 2) -> list[str]:
    """直插 n 行 anchor（POST 路由未实现；本批次只测读路径）。

    返回按插入顺序的 id 列表；时间戳用 sleep 拉开，保证 updated_at 可比。
    """
    ids: list[str] = []
    for i in range(n):
        with store.session() as s:
            s.add(
                PlayerAnchor(
                    id=f"anchor{i:03d}",
                    name=f"第 {i} 档",
                    branch_id="b-root",
                    tick=10 * i,
                    seq=5 * i,
                )
            )
            s.commit()
        ids.append(f"anchor{i:03d}")
        time.sleep(0.01)
    return ids


class TestListAnchors:
    def test_empty_db_returns_empty_list_not_404(self, client: TestClient) -> None:
        """§5 #6 最易写错条：空库 → 200 + []（非 404）。"""
        resp = client.get("/api/anchors")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_five_keys(self, client: TestClient) -> None:
        _seed(anchors_mod.get_anchor_store(), 1)
        body = client.get("/api/anchors").json()
        assert len(body) == 1
        assert set(body[0]) == {"id", "name", "story_label", "created_at", "protected"}

    def test_list_excludes_internal_fields(self, client: TestClient) -> None:
        """出戏边界：禁 tick/seq/branch_id/agent_override 出载荷。"""
        _seed(anchors_mod.get_anchor_store(), 1)
        body = client.get("/api/anchors").json()
        for banned in ("tick", "seq", "branch_id", "agent_override", "updated_at"):
            assert banned not in body[0]

    def test_name_matches_seed(self, client: TestClient) -> None:
        _seed(anchors_mod.get_anchor_store(), 1)
        assert client.get("/api/anchors").json()[0]["name"] == "第 0 档"

    def test_story_label_is_string(self, client: TestClient) -> None:
        """构造期 calendar 未就绪 → 空串（非 null，§6.7）。"""
        _seed(anchors_mod.get_anchor_store(), 1)
        item = client.get("/api/anchors").json()[0]
        assert isinstance(item["story_label"], str)

    def test_created_at_is_iso_string(self, client: TestClient) -> None:
        """schema 声明 date-time 串（非 epoch float）。"""
        _seed(anchors_mod.get_anchor_store(), 1)
        item = client.get("/api/anchors").json()[0]
        assert isinstance(item["created_at"], str)
        assert item["created_at"].endswith("Z")

    def test_protected_is_derived_newest(self, client: TestClient) -> None:
        """§1.4 派生只读：末梢=updated_at 最大者；其余 false。"""
        ids = _seed(anchors_mod.get_anchor_store(), 3)
        body = client.get("/api/anchors").json()
        by_id = {i["id"]: i for i in body}
        assert by_id[ids[-1]]["protected"] is True
        assert by_id[ids[0]]["protected"] is False
        assert by_id[ids[1]]["protected"] is False

    def test_single_row_is_protected(self, client: TestClient) -> None:
        _seed(anchors_mod.get_anchor_store(), 1)
        assert client.get("/api/anchors").json()[0]["protected"] is True

    def test_list_ordering_by_created_at(self, client: TestClient) -> None:
        ids = _seed(anchors_mod.get_anchor_store(), 3)
        assert [i["id"] for i in client.get("/api/anchors").json()] == ids

    def test_list_registers_ids_into_ws_registry(self, client: TestClient) -> None:
        """部署债 #1 核心：列表路由把 id 注进 WS 同步查表集。"""
        _seed(anchors_mod.get_anchor_store(), 2)
        client.get("/api/anchors")
        assert "anchor000" in _ANCHOR_IDS
        assert "anchor001" in _ANCHOR_IDS

    def test_registry_starts_empty(self, client: TestClient) -> None:
        _seed(anchors_mod.get_anchor_store(), 2)
        assert len(_ANCHOR_IDS) == 0

    def test_reload_does_not_duplicate(self, client: TestClient) -> None:
        _seed(anchors_mod.get_anchor_store(), 2)
        client.get("/api/anchors")
        client.get("/api/anchors")
        assert len(_ANCHOR_IDS) == 2
        assert {"anchor000", "anchor001"}.issubset(_ANCHOR_IDS)


class TestGetAnchor:
    def test_existing_anchor_returns_item(self, client: TestClient) -> None:
        _seed(anchors_mod.get_anchor_store(), 1)
        resp = client.get("/api/anchors/anchor000")
        assert resp.status_code == 200
        assert set(resp.json()) == {"id", "name", "story_label", "created_at", "protected"}
        assert resp.json()["id"] == "anchor000"

    def test_missing_anchor_404(self, client: TestClient) -> None:
        assert client.get("/api/anchors/nope").status_code == 404

    def test_404_body_has_no_internal_fields(self, client: TestClient) -> None:
        raw = client.get("/api/anchors/nope").text
        for banned in ("branch_id", "agent_override", "sqlite", "Traceback"):
            assert banned not in raw

    def test_get_registers_id(self, client: TestClient) -> None:
        """§4「按 id 查」同样供数给 WS 查表集。"""
        _seed(anchors_mod.get_anchor_store(), 1)
        client.get("/api/anchors/anchor000")
        assert "anchor000" in _ANCHOR_IDS

    def test_path_param_name_is_anchor_id(self) -> None:
        """§5 #7：形参名逐字 anchor_id，否则 FastAPI 生成 {id} 造成快照漂移。"""
        assert next(iter(inspect.signature(anchors_mod.get_anchor).parameters)) == "anchor_id"

    def test_empty_table_get_404(self, client: TestClient) -> None:
        assert client.get("/api/anchors/anything").status_code == 404


class TestLoadAnchorUsesRegistry:
    """部署债闭环：WS load_anchor 的成功/失败由落库注册集供数。"""

    def _loop_and_pf(self):
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.world import WorldState, build_default_bus
        from sim.world.map import CHUNK_SIZE, Chunk, TileMap
        from sim.world.pathfinding import Pathfinder

        loop = TickLoop(
            clock=GameClock(speed=1.0),
            bus=build_default_bus(),
            state=WorldState(world_seed=1),
        )
        loop.enqueue(world_create_event(tick=0, seed=1, entity_ids=("chenmo",)))
        loop.drain_events()
        chunks = {
            (cx, cy): Chunk(
                cx=cx,
                cy=cy,
                ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
            for cy in range(2)
            for cx in range(2)
        }
        return loop, Pathfinder(TileMap(width=32, height=32, chunks=chunks))

    def test_registered_id_returns_snapshot(self, client: TestClient) -> None:
        from sim.api.ws import _handle_load_anchor

        _seed(anchors_mod.get_anchor_store(), 1)
        client.get("/api/anchors")

        loop, pf = self._loop_and_pf()
        reply = _handle_load_anchor({"anchor_id": "anchor000"}, loop, pf)
        assert reply is not None
        assert reply["type"] == "full_snapshot"

    def test_unregistered_id_load_failed(self, client: TestClient) -> None:
        from sim.api.ws import _handle_load_anchor

        loop, pf = self._loop_and_pf()
        reply = _handle_load_anchor({"anchor_id": "ghost"}, loop, pf)
        assert reply is not None
        assert reply["type"] == "error"
        assert reply["code"] == "load_failed"


def test_anchor_store_uses_player_anchors_table() -> None:
    """落库路径：读的是 player_anchors 表，不是内存替身。"""
    assert PlayerAnchor.__tablename__ == "player_anchors"


class TestSchemaMatchesSnapshot:
    """实发 schema ≡ shared/openapi.json 快照（K7 最小实现的 schema 真源对齐）。

    pydantic 自动装饰（title/description/format）是历史漂移源——K3 靠 K3 同款
    开关 + openapi_ext 后处理归零；本类把 anchors 这一项钉住，#4 注入 responses
    时不必重踩。
    """

    def test_anchor_list_item_matches_snapshot(self, client: TestClient) -> None:
        import json
        from pathlib import Path

        live = client.get("/openapi.json").json()["components"]["schemas"]["AnchorListItem"]
        snap = json.loads(
            (Path(__file__).parents[1].parent / "shared" / "openapi.json").read_text(
                encoding="utf-8"
            )
        )["components"]["schemas"]["AnchorListItem"]
        assert live == snap

    def test_path_param_name_is_anchor_id_in_live_spec(self, client: TestClient) -> None:
        """§5 #7：实发 spec 的形参名也是 anchor_id（gen-protocol.ts 头注点名）。"""
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/anchors/{anchor_id}" in paths
        assert "/api/anchors/{id}" not in paths

    def test_get_routes_live(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert "get" in paths["/api/anchors"]
        assert "get" in paths["/api/anchors/{anchor_id}"]

    def test_mutation_routes_absent_this_batch(self, client: TestClient) -> None:
        """本批次范围外：POST/PATCH/DELETE 仍归 Claude 域（§5 清单 #2/#5）。

        断言它们缺席，避免未来有人误以为读写路径已齐。
        """
        paths = client.get("/openapi.json").json()["paths"]
        assert set(paths["/api/anchors"]) == {"get"}
        assert {k for k in paths["/api/anchors/{anchor_id}"] if k != "parameters"} == {"get"}
