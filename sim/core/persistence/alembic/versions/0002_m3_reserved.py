"""0002 — M3 预留表 + entropy_log.event_seq

Revision ID: 0002_m3_reserved
Revises: 0001_m0_initial
Create Date: 2026-09-19

内容：
- 预先创建 M3 空表：npc_memories / relationships / knowledge（schema.md §5/§7/§8）
- entropy_log 增 event_seq 列（codex 终审记账项；M1 EntropyMixer 接线回填）

注意：npc_memory_vec 是 sqlite-vec 虚拟表，维度未定且需 LOAD EXTENSION，
不在 Alembic 范围内（见 docs/data/migration.md + sim/core/persistence/vector.py）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_m3_reserved"
down_revision: str | None = "0001_m0_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --------------------------------------------------------- npc_memories (§5)
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
    op.create_index("idx_memories_event", "npc_memories", ["branch_id", "event_seq"])

    # --------------------------------------------------------- relationships (§7)
    op.create_table(
        "relationships",
        sa.Column("owner_id", sa.String, nullable=False),
        sa.Column("other_id", sa.String, nullable=False),
        sa.Column("trust", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("affection", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("fear", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("debt", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("face", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("last_interaction", sa.Integer, nullable=False, server_default="0"),
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint("branch_id", "owner_id", "other_id"),
    )
    op.create_index("idx_rel_owner", "relationships", ["branch_id", "owner_id"])
    op.create_index("idx_rel_other", "relationships", ["branch_id", "other_id"])

    # ------------------------------------------------------------ knowledge (§8)
    op.create_table(
        "knowledge",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("holder_id", sa.String, nullable=False),
        sa.Column("fact", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("source", sa.String, nullable=False),  # witnessed/told/inferred
        sa.Column("learned_at", sa.Integer, nullable=False),
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("idx_knowledge_holder", "knowledge", ["branch_id", "holder_id"])
    op.create_index("idx_knowledge_source", "knowledge", ["branch_id", "source"])

    # --------------------------------------- entropy_log.event_seq（codex 记账）
    with op.batch_alter_table("entropy_log") as batch_op:
        batch_op.add_column(sa.Column("event_seq", sa.Integer, nullable=True))
        batch_op.create_index("idx_entropy_event", ["branch_id", "event_seq"])


def downgrade() -> None:
    with op.batch_alter_table("entropy_log") as batch_op:
        batch_op.drop_index("idx_entropy_event")
        batch_op.drop_column("event_seq")

    op.drop_index("idx_knowledge_source", table_name="knowledge")
    op.drop_index("idx_knowledge_holder", table_name="knowledge")
    op.drop_table("knowledge")

    op.drop_index("idx_rel_other", table_name="relationships")
    op.drop_index("idx_rel_owner", table_name="relationships")
    op.drop_table("relationships")

    op.drop_index("idx_memories_event", table_name="npc_memories")
    op.drop_index("idx_memories_importance", table_name="npc_memories")
    op.drop_index("idx_memories_npc", table_name="npc_memories")
    op.drop_table("npc_memories")
