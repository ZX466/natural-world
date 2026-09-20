"""0003 — npc_memories 写入/治理列

Revision ID: 0003_memory_write
Revises: 0002_m3_reserved
Create Date: 2026-09-20

对齐 docs/security/memory-scan.md §4（append-only 补救）+ §1（写入来源）：
- entry_id：MemoryEntry.id 稳定句柄（uuid hex），supersede 关联键；唯一索引
- source：写入来源 reason/dialogue/event/interoception
- superseded_by / invalid_reason：治理列，supersede 只更新这两列
- idx_memories_visible：检索视图过滤 superseded_by IS NOT NULL

向量列预留不返工：npc_memories.embedding + entry_id 已就位，M3 直接落 vec0 关联。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_memory_write"
down_revision: str | None = "0002_m3_reserved"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("npc_memories") as batch_op:
        batch_op.add_column(sa.Column("entry_id", sa.String, nullable=False, server_default=""))
        batch_op.add_column(sa.Column("source", sa.String, nullable=False, server_default="event"))
        batch_op.add_column(sa.Column("superseded_by", sa.String, nullable=True))
        batch_op.add_column(sa.Column("invalid_reason", sa.String, nullable=True))
        batch_op.create_index("idx_memories_entry", ["entry_id"], unique=True)
        batch_op.create_index("idx_memories_visible", ["npc_id", "branch_id", "superseded_by"])


def downgrade() -> None:
    with op.batch_alter_table("npc_memories") as batch_op:
        batch_op.drop_index("idx_memories_visible")
        batch_op.drop_index("idx_memories_entry")
        batch_op.drop_column("invalid_reason")
        batch_op.drop_column("superseded_by")
        batch_op.drop_column("source")
        batch_op.drop_column("entry_id")
