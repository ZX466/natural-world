"""数据库初始化与 session 工厂。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sim.core.persistence.models import Base


def create_engine(database_url: str = "sqlite+aiosqlite:///:memory:") -> AsyncEngine:
    """创建异步引擎。默认使用内存数据库（测试用）。"""
    return create_async_engine(database_url, echo=False)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """创建 async session 工厂。"""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_database(engine: AsyncEngine) -> None:
    """创建所有 M0 表（Alembic 就位后改用迁移）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
