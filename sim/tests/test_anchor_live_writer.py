"""S2: 真实驱动持写锁时，HTTP 存档不能阻塞其提交。"""

import asyncio
import threading
import time

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from sim.api import anchors
from sim.api.main import app
from sim.api.settings import get_profile_store


def test_repeated_saves_while_driver_commits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    get_profile_store().__init__(f"sqlite:///{tmp_path / 'settings.db'}")
    anchor_store = anchors.get_anchor_store()
    anchor_store.__init__(f"sqlite:///{tmp_path / 'world.db'}")
    with anchor_store._engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA busy_timeout=200")

    writer_ready = threading.Event()
    real_commit = AsyncSession.commit

    async def delayed_commit(session):
        if asyncio.current_task() is app.state.driver:
            # 真实 SQL 取得写锁后，让提交挂起一小段（模拟慢磁盘）。
            await session.flush()
            writer_ready.set()
            await asyncio.sleep(0.04)
        await real_commit(session)

    with TestClient(app) as client:
        async def world_ready():
            for _ in range(500):
                if await app.state.store.current_branch_id_or_none() is not None:
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("世界没有建立当前分支")

        assert client.portal is not None
        client.portal.call(asyncio.wait_for, world_ready(), 5)
        monkeypatch.setattr(AsyncSession, "commit", delayed_commit)
        for index in range(5):
            writer_ready.clear()
            assert writer_ready.wait(timeout=5), "驱动没有进入写事务"
            response = client.post("/api/anchors", json={"name": f"河边歇脚{index}"})
            assert response.status_code == 201, response.text
            assert not app.state.driver.done()
        assert len(client.get("/api/anchors").json()) == 5

    # 生命周期退出后，第三连接仍应立即取得写锁（没有遗留事务）。
    with anchor_store._engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        connection.rollback()


def test_save_package_keeps_world_cursor_stable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    get_profile_store().__init__(f"sqlite:///{tmp_path / 'settings.db'}")
    anchor_store = anchors.get_anchor_store()
    anchor_store.__init__(f"sqlite:///{tmp_path / 'world.db'}")
    observed = []
    real_create = anchor_store.create_item

    def slow_create(*args, **kwargs):
        before = app.state.loop.state.tick
        time.sleep(0.1)
        observed.append((before, app.state.loop.state.tick))
        return real_create(*args, **kwargs)

    with TestClient(app) as client:
        # 第一条请求允许世界尚未提交创世；第二条必须在已开线后运行。
        for _ in range(100):
            if client.post("/api/anchors", json={"name": "开线"}).status_code == 201:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("世界未开线")
        monkeypatch.setattr(anchor_store, "create_item", slow_create)
        assert client.post("/api/anchors", json={"name": "驻足"}).status_code == 201
        assert observed and all(before == after for before, after in observed)
