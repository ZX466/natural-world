"""启动真实 API 的测试也必须使用各自临时库，不能读写开发存档。"""

import pytest


@pytest.fixture(autouse=True)
def isolated_world_database(tmp_path, monkeypatch):
    from sim.api import main

    monkeypatch.setattr(main, "WORLD_DB_PATH", tmp_path / "world.db")
    monkeypatch.setattr(main, "_active_profile_snapshot_provider", lambda: lambda: None)
