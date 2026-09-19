"""M0 首版迁移 — 五表（events/branches/snapshots/player_anchors/entropy_log + llm_profiles）

Revision ID: 0001_m0_initial
Revises:
Create Date: 2026-09-19

对齐 docs/data/schema.md + sim/core/persistence/models.py。
codex 必须项 #3：snapshots.seq = 快照点事件流最大 events.seq（非表内自增）。
建议项：snapshots.schema_version 已落。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_m0_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ branches
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

    # -------------------------------------------------------------------- events
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

    # ----------------------------------------------------------------- snapshots
    # seq = 快照点事件流最大 events.seq（codex 必须项 #3）
    op.create_table(
        "snapshots",
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("tick", sa.Integer, nullable=False),
        sa.Column("snapshot_data", sa.LargeBinary, nullable=False),
        sa.Column("is_cold", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint("branch_id", "seq"),
    )
    op.create_index("idx_snapshots_branch_tick", "snapshots", ["branch_id", "tick"])
    op.create_index("idx_snapshots_cold", "snapshots", ["is_cold"])

    # ------------------------------------------------------------ player_anchors
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

    # ------------------------------------------------------------- entropy_log
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

    # ------------------------------------------------------------ llm_profiles
    op.create_table(
        "llm_profiles",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("base_url", sa.String, nullable=False),
        sa.Column("api_key_enc", sa.LargeBinary, nullable=False),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("temperature", sa.Float, nullable=False, server_default="0.7"),
        sa.Column("max_tokens", sa.Integer, nullable=False, server_default="2048"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.Float, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_profiles")
    op.drop_index("idx_entropy_branch_tick", table_name="entropy_log")
    op.drop_table("entropy_log")
    op.drop_index("idx_anchors_branch", table_name="player_anchors")
    op.drop_table("player_anchors")
    op.drop_index("idx_snapshots_cold", table_name="snapshots")
    op.drop_index("idx_snapshots_branch_tick", table_name="snapshots")
    op.drop_table("snapshots")
    op.drop_index("idx_events_type", table_name="events")
    op.drop_index("idx_events_actor", table_name="events")
    op.drop_index("idx_events_branch_tick", table_name="events")
    op.drop_table("events")
    op.drop_index("idx_branches_status", table_name="branches")
    op.drop_table("branches")
