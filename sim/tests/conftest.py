"""启动真实 API 的测试也必须使用各自临时库，不能读写开发存档。

共享夹具（2026-10-26 去重）：`engine` / `store` / `session` 三件套原在各测试文件
逐字重复（24 / 16 / 20 份），统一上移到本文件。带差异的变体（`engine(tmp_path)`、
`store() -> InMemoryStore` 等）仍留在各自文件里本地覆盖。
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.store import SqlEventStore


@pytest.fixture(autouse=True)
def isolated_world_database(tmp_path, monkeypatch):
    from sim.api import main

    monkeypatch.setattr(main, "WORLD_DB_PATH", tmp_path / "world.db")
    monkeypatch.setattr(main, "_active_profile_snapshot_provider", lambda: lambda: None)


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def store(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return SqlEventStore(sf)


@pytest.fixture
async def session(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        yield s
