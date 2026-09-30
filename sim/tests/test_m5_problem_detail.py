"""M5-S1：ProblemDetail 全局错误形（anchors-api.md §2/§3.2，kilo S-1 施工项）。

契约：
- HTTPException/未匹配路由 404/422 校验失败 → 四键 ProblemDetail
  （type/title/status/detail；title+status 必填）；
- detail 以 `/errors/...` 开头时同时用作 type（路由传机器码）；
- 未匹配路由 404 也是 ProblemDetail 形（非 `{"detail":"Not Found"}`）。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from sim.api import anchors as anchors_mod


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LZ_MASTER_KEY", "t" * 44)
    from sim.api.settings import get_profile_store

    get_profile_store().__init__(f"sqlite:///{tmp_path}/settings.db")
    anchors_mod.get_anchor_store().__init__(f"sqlite:///{tmp_path}/anchors.db")
    from sim.api.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestProblemDetailShape:
    def test_unmatched_route_404_is_problem(self, client: TestClient) -> None:
        r = client.get("/api/definitely-not-here")
        assert r.status_code == 404
        body = r.json()
        assert set(body) == {"type", "title", "status", "detail"}
        assert body["type"] == "/errors/not-found"
        assert body["status"] == 404

    def test_anchor_404_uses_machine_code(self, client: TestClient) -> None:
        r = client.get("/api/anchors/ghost000000")
        assert r.status_code == 404
        body = r.json()
        assert body["type"] == "/errors/anchor-not-found"
        assert body["title"] == "玩家档不存在"
        assert body["status"] == 404

    def test_validation_422_is_problem(self, client: TestClient) -> None:
        r = client.post("/api/anchors", json={})
        assert r.status_code == 422
        body = r.json()
        assert body["type"] == "/errors/validation"
        assert body["status"] == 422
        assert "name" in body["detail"]
