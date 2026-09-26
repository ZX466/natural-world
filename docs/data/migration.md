# Alembic 迁移策略

> 技术栈：Alembic + SQLAlchemy 2.0 async + aiosqlite。
> 对齐 DESIGN.md §4（技术栈锁定）+ docs/data/schema.md（完整表设计）。

---

## 1. 迁移策略原则

- **版本化**：每个 schema 变更对应一个迁移脚本，可追溯、可回滚。
- **幂等**：迁移脚本可在任意顺序执行后达到一致状态（Alembic 管理顺序）。
- **前向兼容**：新表/新列用 `nullable=True` 或 `server_default` 渐进引入。
- **零停机**：SQLite 单文件数据库，迁移期间世界暂停（tick 暂停）。

---

## 2. 项目结构

```
sim/
├─ core/
│  └─ persistence/
│     ├─ __init__.py
│     ├─ models.py          # SQLAlchemy ORM 模型
│     ├─ database.py        # async engine + session factory
│     └─ migrations/
│        ├─ alembic.ini
│        ├─ env.py           # Alembic env（async 配置）
│        └─ versions/
│           ├─ 001_initial_schema.py
│           ├─ 002_add_npc_memories.py
│           └─ ...
```

---

## 3. Alembic 异步配置

### 3.1 env.py 核心配置

```python
# sim/core/persistence/migrations/env.py
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from sim.core.persistence.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """异步在线模式"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### 3.2 alembic.ini

```ini
[alembic]
script_location = sim/core/persistence/migrations
sqlalchemy.url = sqlite+aiosqlite:///world.db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

---

## 4. SQLAlchemy ORM 模型

### 4.1 基础模型

```python
# sim/core/persistence/models.py
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean, LargeBinary,
    ForeignKey, Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at = Column(Float, nullable=False, default=lambda: datetime.utcnow().timestamp())
```

### 4.2 events 表

```python
class Event(TimestampMixin, Base):
    __tablename__ = "events"

    branch_id = Column(String, nullable=False, primary_key=True)
    seq = Column(Integer, nullable=False, primary_key=True)
    tick = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)
    actor_id = Column(String, nullable=False)
    target_id = Column(String, nullable=True)
    parent_seq = Column(Integer, nullable=True)
    payload = Column(Text, nullable=False)  # JSON
    witnesses = Column(Text, nullable=False)  # JSON array
    entropy_ref = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_events_branch_tick", "branch_id", "tick"),
        Index("idx_events_actor", "branch_id", "actor_id"),
        Index("idx_events_type", "branch_id", "event_type"),
    )
```

### 4.3 branches 表

```python
class Branch(TimestampMixin, Base):
    __tablename__ = "branches"

    id = Column(String, primary_key=True)
    forked_from_branch = Column(String, nullable=True)
    forked_from_seq = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="active")
    abandoned_at = Column(Float, nullable=True)

    __table_args__ = (
        Index("idx_branches_status", "status"),
    )
```

### 4.4 snapshots 表

```python
class Snapshot(TimestampMixin, Base):
    __tablename__ = "snapshots"

    branch_id = Column(String, nullable=False, primary_key=True)
    seq = Column(Integer, nullable=False, primary_key=True)
    tick = Column(Integer, nullable=False)
    snapshot_data = Column(LargeBinary, nullable=False)  # gzip compressed
    is_cold = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("idx_snapshots_branch_tick", "branch_id", "tick"),
        Index("idx_snapshots_cold", "is_cold"),
    )
```

### 4.5 player_anchors 表

```python
class PlayerAnchor(TimestampMixin, Base):
    __tablename__ = "player_anchors"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    branch_id = Column(String, nullable=False)
    tick = Column(Integer, nullable=False)
    seq = Column(Integer, nullable=False)
    agent_override = Column(Text, nullable=False, default="{}")
    updated_at = Column(Float, nullable=False, default=lambda: datetime.utcnow().timestamp())

    __table_args__ = (
        Index("idx_anchors_branch", "branch_id"),
    )
```

### 4.6 npc_memories 表

```python
class NPCMemory(TimestampMixin, Base):
    __tablename__ = "npc_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    npc_id = Column(String, nullable=False)
    event_seq = Column(Integer, nullable=True)
    branch_id = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    importance = Column(Float, nullable=False)
    emotion_tag = Column(String, nullable=True)
    distortion = Column(Float, nullable=False, default=0.0)
    embedding = Column(LargeBinary, nullable=True)
    created_at_tick = Column(Integer, nullable=False)
    last_accessed_tick = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_memories_npc", "npc_id", "branch_id"),
        Index("idx_memories_importance", "npc_id", importance DESC),
        Index("idx_memories_event", "branch_id", "event_seq"),
        CheckConstraint("importance >= 0.0 AND importance <= 1.0"),
        CheckConstraint("distortion >= 0.0 AND distortion <= 1.0"),
    )
```

### 4.7 relationships 表

```python
class Relationship(Base):
    __tablename__ = "relationships"

    branch_id = Column(String, nullable=False, primary_key=True)
    owner_id = Column(String, nullable=False, primary_key=True)
    other_id = Column(String, nullable=False, primary_key=True)
    trust = Column(Float, nullable=False, default=0.0)
    affection = Column(Float, nullable=False, default=0.0)
    fear = Column(Float, nullable=False, default=0.0)
    debt = Column(Float, nullable=False, default=0.0)
    face = Column(Float, nullable=False, default=0.0)
    last_interaction = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_rel_owner", "branch_id", "owner_id"),
        Index("idx_rel_other", "branch_id", "other_id"),
    )
```

### 4.8 knowledge 表

```python
class Knowledge(TimestampMixin, Base):
    __tablename__ = "knowledge"

    id = Column(Integer, primary_key=True, autoincrement=True)
    holder_id = Column(String, nullable=False)
    fact = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    source = Column(String, nullable=False)
    learned_at = Column(Integer, nullable=False)
    branch_id = Column(String, nullable=False)

    __table_args__ = (
        Index("idx_knowledge_holder", "branch_id", "holder_id"),
        Index("idx_knowledge_source", "branch_id", "source"),
        CheckConstraint("source IN ('witnessed', 'told', 'inferred')"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0"),
    )
```

### 4.9 structures 表（0006 已落地）

```python
class Structure(TimestampMixin, Base):
    __tablename__ = "structures"

    branch_id = Column(String, nullable=False)
    structure_id = Column(String, nullable=False)
    tiles = Column(Text, nullable=False)
    kind = Column(String, nullable=False)
    material = Column(String, nullable=False)
    phase = Column(String, nullable=False, default="building")
    load_bearing = Column(Boolean, nullable=False, default=False)
    supported_by = Column(Text, nullable=False, default="[]")
    owner_id = Column(String, nullable=True)
    built_by = Column(String, nullable=True)
    built_at = Column(Integer, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("branch_id", "structure_id"),
        Index("idx_struct_branch", "branch_id"),
        Index("idx_struct_owner", "branch_id", "owner_id"),
        Index("idx_struct_phase", "branch_id", "phase"),
    )
```

熵态列 `integrity/quality/decay_rate/is_rubble` 留在 `matter_state`，本表不复制。

### 4.10 llm_profiles 表

```python
class LLMProfile(TimestampMixin, Base):
    __tablename__ = "llm_profiles"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    api_key_enc = Column(LargeBinary, nullable=False)  # Fernet encrypted
    model = Column(String, nullable=False)
    temperature = Column(Float, nullable=False, default=0.7)
    max_tokens = Column(Integer, nullable=False, default=2048)
    is_active = Column(Boolean, nullable=False, default=False)
```

### 4.11 entropy_log 表

```python
class EntropyLog(TimestampMixin, Base):
    __tablename__ = "entropy_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stream = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    tick = Column(Integer, nullable=False)
    value = Column(String, nullable=False)  # hex
    branch_id = Column(String, nullable=False)

    __table_args__ = (
        Index("idx_entropy_branch_tick", "branch_id", "tick"),
    )
```

---

## 5. 初始迁移脚本

### 5.1 001_initial_schema.py

```python
"""initial schema — M0 基础表

Revision ID: 001
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # branches
    op.create_table(
        "branches",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("forked_from_branch", sa.String, nullable=True),
        sa.Column("forked_from_seq", sa.Integer, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="active"),
        sa.Column("abandoned_at", sa.Float, nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("idx_branches_status", "branches", ["status"])

    # events
    op.create_table(
        "events",
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("tick", sa.Integer, nullable=False),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("actor_id", sa.String, nullable=False),
        sa.Column("target_id", sa.String, nullable=True),
        sa.Column("parent_seq", sa.Integer, nullable=True),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("witnesses", sa.Text, nullable=False),
        sa.Column("entropy_ref", sa.String, nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint("branch_id", "seq"),
    )
    op.create_index("idx_events_branch_tick", "events", ["branch_id", "tick"])
    op.create_index("idx_events_actor", "events", ["branch_id", "actor_id"])
    op.create_index("idx_events_type", "events", ["branch_id", "event_type"])

    # snapshots
    op.create_table(
        "snapshots",
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("tick", sa.Integer, nullable=False),
        sa.Column("snapshot_data", sa.LargeBinary, nullable=False),
        sa.Column("is_cold", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint("branch_id", "seq"),
    )
    op.create_index("idx_snapshots_branch_tick", "snapshots", ["branch_id", "tick"])
    op.create_index("idx_snapshots_cold", "snapshots", ["is_cold"])

    # player_anchors
    op.create_table(
        "player_anchors",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("tick", sa.Integer, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("agent_override", sa.Text, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
    )
    op.create_index("idx_anchors_branch", "player_anchors", ["branch_id"])

    # llm_profiles
    op.create_table(
        "llm_profiles",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("base_url", sa.String, nullable=False),
        sa.Column("api_key_enc", sa.LargeBinary, nullable=False),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("temperature", sa.Float, nullable=False, server_default="0.7"),
        sa.Column("max_tokens", sa.Integer, nullable=False, server_default="2048"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.Float, nullable=False),
    )

    # entropy_log
    op.create_table(
        "entropy_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("stream", sa.String, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("tick", sa.Integer, nullable=False),
        sa.Column("value", sa.String, nullable=False),
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("idx_entropy_branch_tick", "entropy_log", ["branch_id", "tick"])


def downgrade() -> None:
    op.drop_table("entropy_log")
    op.drop_table("llm_profiles")
    op.drop_table("player_anchors")
    op.drop_table("snapshots")
    op.drop_table("events")
    op.drop_table("branches")
```

---

## 6. 后续迁移脚本骨架

### 6.1 002_add_npc_memories.py（M3 阶段）

```python
"""add npc_memories and relationships — M3

Revision ID: 002
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"


def upgrade() -> None:
    op.create_table(
        "npc_memories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("npc_id", sa.String, nullable=False),
        sa.Column("event_seq", sa.Integer, nullable=True),
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("importance", sa.Float, nullable=False),
        sa.Column("emotion_tag", sa.String, nullable=True),
        sa.Column("distortion", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("embedding", sa.LargeBinary, nullable=True),
        sa.Column("created_at_tick", sa.Integer, nullable=False),
        sa.Column("last_accessed_tick", sa.Integer, nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("idx_memories_npc", "npc_memories", ["npc_id", "branch_id"])
    op.create_index("idx_memories_importance", "npc_memories", ["npc_id", "importance"])

    op.create_table(
        "relationships",
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("owner_id", sa.String, nullable=False),
        sa.Column("other_id", sa.String, nullable=False),
        sa.Column("trust", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("affection", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("fear", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("debt", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("face", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("last_interaction", sa.Integer, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("branch_id", "owner_id", "other_id"),
    )
    op.create_index("idx_rel_owner", "relationships", ["branch_id", "owner_id"])

    op.create_table(
        "knowledge",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("holder_id", sa.String, nullable=False),
        sa.Column("fact", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("learned_at", sa.Integer, nullable=False),
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("idx_knowledge_holder", "knowledge", ["branch_id", "holder_id"])


def downgrade() -> None:
    op.drop_table("knowledge")
    op.drop_table("relationships")
    op.drop_table("npc_memories")
```

### 6.2 0006_m4_structures.py（M4-D2a 已落地）

实际迁移：`sim/core/persistence/alembic/versions/0006_m4_structures.py`。

- 新建 `structures`（§4.9 瘦身形状），主键 `(branch_id, structure_id)`；
- `op.batch_alter_table("matter_state")` 将主键由 `subject_id` 改为
  `(branch_id, subject_id)`，关闭跨分支投影串写；
- 0004 旧 PK 未命名，迁移用 `naming_convention` 规范成
  `pk_matter_state_subject_id` 后删除；索引在 batch 外维护；
- downgrade 逆序：删 structures 索引/表，再把 matter PK 还原为单列。

---

### 6.3 0007_m4_material_balances.py（M4-D2d 已落地）

- 新建 `material_balances`：复合主键 `(branch_id, ref, material_id)`；
- 索引 `(branch_id, material_id)`；
- 纯 `create_table`，无需 batch；downgrade 先删索引再删表。

---

## 7. 迁移执行命令

```bash
# 生成新迁移（自动检测模型变更）
alembic revision --autogenerate -m "description"

# 执行迁移到最新版本
alembic upgrade head

# 回滚到上一个版本
alembic downgrade -1

# 查看当前版本
alembic current

# 查看迁移历史
alembic history

# 生成离线 SQL 脚本
alembic upgrade head --sql > migration.sql
```

---

## 8. 数据库初始化流程

```python
# sim/core/persistence/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///world.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """首次启动：创建表 + 初始分支"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 创建初始分支
    async with async_session() as session:
        root_branch = Branch(
            id="main",
            status="active",
            created_at=datetime.utcnow().timestamp(),
        )
        session.add(root_branch)
        await session.commit()
```

---

## 9. 迁移注意事项

| 事项 | 说明 |
|------|------|
| **tick 暂停** | 迁移期间世界暂停（tick 不推进），避免迁移中产生新事件 |
| **备份** | 迁移前自动备份 world.db → world.db.bak |
| **回滚** | 每个迁移必须有 downgrade()，支持回滚 |
| **版本锁** | Alembic 版本表 `alembic_version` 记录当前版本，多进程安全 |
| **大表迁移** | events 表可能很大，ALTER TABLE 需要谨慎（SQLite 重建表机制） |
| **sqlite-vec** | 虚拟表（npc_memory_vec）不在 Alembic 管理范围内，手动创建 |
