"""数据库初始化与 session 工厂。"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sim.core.persistence.models import Base

#: 迁移配置入口（绝对路径）。
_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"

#: 迁移脚本目录（绝对路径）。`alembic.ini` 的 `script_location` 是**相对 CWD** 的，
#: 而本仓库大量测试 `monkeypatch.chdir(tmp_path)`，故必须显式覆盖为绝对路径，
#: 否则 `ScriptDirectory` 会去 tmp_path 下找迁移目录并 `CommandError: Path doesn't exist`。
_ALEMBIC_SCRIPTS = Path(__file__).resolve().parent / "alembic"

#: 「create_all 建出的库」被视作此版本——它包含了 0004~0014 的全部结构，
#: 只是没有 alembic_version 行。补齐时先 stamp 到此，再逐级升级。
_CREATE_ALL_BASELINE = "0014_fires"


def create_engine(database_url: str = "sqlite+aiosqlite:///:memory:") -> AsyncEngine:
    """创建异步引擎。默认使用内存数据库（测试用）。"""
    return create_async_engine(database_url, echo=False)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """创建 async session 工厂。"""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_database(engine: AsyncEngine) -> None:
    """创建所有 M0 表。

    生产/持久库走 Alembic 迁移（`uv run alembic upgrade head`，见 alembic.ini）；
    本函数仅供测试内存库与开发快速起步使用（Base.metadata.create_all）。

    **`create_all` 只建缺失的表，不给已存在的表加列**——已有存档必须再走
    :func:`ensure_schema`，否则新迁移引入的列永远补不上（2026-10-31 实测：
    `npc_health.code` 缺失会让应用启动直接 OperationalError）。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _alembic_config() -> object:
    """构造 alembic `Config`，并把 `script_location` 固定为绝对路径。

    必须在构造后覆盖：`alembic.ini` 写的是相对路径，依赖 CWD；测试与运行时都可能
    不在仓库根，相对路径会解析到错误位置。
    """
    from alembic.config import Config

    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", _ALEMBIC_SCRIPTS.as_posix())
    return config


def _alembic_head() -> str:
    """迁移脚本的最新 revision（从 alembic 自身读，不手抄常量）。"""
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()  # type: ignore[arg-type]
    if head is None:  # 迁移目录为空时 alembic 返回 None
        raise RuntimeError(f"alembic 迁移目录没有可用 revision: {_ALEMBIC_SCRIPTS}")
    return head


def _models_match(sync_conn: object) -> bool:
    """库的实际结构是否已与 ORM 模型一致（表与列都齐）。

    `create_all` 建出的库有两种：**老代码建的**（缺新迁移的列）与**当前代码建的**
    （已含全部列）。版本号都无法区分（都没有 `alembic_version`），只能比结构。
    """
    inspector = inspect(sync_conn)
    if inspector is None:  # 类型上 inspect 可返回 None，实际传入 Connection 不会
        return False
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            return False
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        if {column.name for column in table.columns} - actual:
            return False
    return True


async def _schema_state(engine: AsyncEngine) -> tuple[bool, bool, bool]:
    """(有 alembic_version 表?, 已到 head?, 结构已与模型一致?)。"""
    async with engine.connect() as conn:
        has_table = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).has_table("alembic_version")
        )
        matches = await conn.run_sync(_models_match)
        if not has_table:
            return False, False, matches
        from sqlalchemy import text

        current = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
    return True, current == _alembic_head(), matches


def _run_alembic(database_url: str, action: Callable[[object], None]) -> None:
    """在线程内执行 alembic（`env.py` 用 `asyncio.run`，不能在运行中的循环里调）。

    `env.py` 从 `WORLD_DB_URL` 读库地址，故临时设置；**用完必须还原**，否则会把
    进程级环境变量永久改成当前引擎的 URL（后续别的库操作会被误导）。
    """
    previous = os.environ.get("WORLD_DB_URL")
    os.environ["WORLD_DB_URL"] = database_url
    try:
        action(_alembic_config())
    finally:
        if previous is None:
            os.environ.pop("WORLD_DB_URL", None)
        else:
            os.environ["WORLD_DB_URL"] = previous


def _database_url_of(engine: AsyncEngine) -> str:
    """引擎实际连接的 URL（自愈必须打到同一个库）。"""
    url = engine.url
    return url.render_as_string(hide_password=False)


async def ensure_schema(engine: AsyncEngine) -> None:
    """把已存在的库升级到最新迁移（幂等；已到 head 时零操作）。

    **为什么需要**：`init_database` 的 `create_all` 只建缺失的表、不加列。本项目
    的 `world.db` 历史上正是 `create_all` 建出来的（无 `alembic_version` 行），
    于是任何「新增列」的迁移都无法作用于它——`0015_health_code` 的 `npc_health.code`
    就是这样缺失的，应用启动会 `OperationalError: no such column`。

    两条自愈路径：

    1. **无 `alembic_version` 表**（`create_all` 建出的库）：
       - 结构已与当前模型一致（当前代码 `create_all` 建的新库）→ 只 `stamp` 到 head，
         不跑 DDL（否则 `duplicate column name`）；
       - 结构落后（老代码建的库，如缺 `npc_health.code`）→ 先 `stamp` 到
         `_CREATE_ALL_BASELINE`（该库结构等价于此版本），再 `upgrade head`。
    2. **有版本但落后** → 直接 `upgrade head`。

    已在 head → 直接返回（幂等；第二次调用不改版本）。

    只做 DDL，不碰 `events`（C6：事件行一行不动）。历史 `npc_health` 行的
    `code` 由 `0015` 回填为旧自增 id 的十进制文本。
    """
    has_version, at_head, models_match = await _schema_state(engine)
    if at_head:
        return

    database_url = _database_url_of(engine)
    head = _alembic_head()

    def upgrade(config: object) -> None:
        from alembic import command

        if not has_version and models_match:
            # 当前代码 create_all 建的新库：结构已是 head，只需补版本行。
            command.stamp(config, head)  # type: ignore[arg-type]
            return
        if not has_version:
            # 老 create_all 库：结构等价于 create_all 时代的 head，对齐后再升级。
            command.stamp(config, _CREATE_ALL_BASELINE)  # type: ignore[arg-type]
        command.upgrade(config, "head")  # type: ignore[arg-type]

    await asyncio.to_thread(_run_alembic, database_url, upgrade)
