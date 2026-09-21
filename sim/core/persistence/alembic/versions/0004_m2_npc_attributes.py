"""0004 — M2：NPC 完整属性 + 物质熵增状态

Revision ID: 0004_m2_npc_attributes
Revises: 0003_memory_write
Create Date: 2026-09-20

对齐 DESIGN.md §13（NPC 完整属性：身份/需求/OCEAN/PAD/技能/目标/物品/健康）
+ §11（物质熵增）+ §14（结构 integrity/quality，归零变 rubble）
+ docs/data/schema.md（本迁移后新增 §12/§13）
+ codex docs/security/self-unknown.md §6（隐藏属性标注字段映射）。

内容：
- npc_profiles：健康档以外的完整属性宽表（身份 + OCEAN + PAD + 需求/技能/
  目标/物品/知识边界 JSON + LOD）；
- npc_health：健康档（疾病/旧伤/成瘾/残疾 + 创伤应激=trauma），一行一条，
  含隐藏标注三列 hidden / descriptors / trigger_conditions（自我未知）；
- matter_state：物质熵增状态（integrity/quality/decay/rubble），熵增过程
  仍由 events 流的 tile_changed / matter.* 事件驱动（事件模型见 schema.md §13）。

注意：npc_memory_vec 是 sqlite-vec 虚拟表，维度未锁定且需 LOAD EXTENSION，
不在 Alembic 范围内（见 docs/data/migration.md + sim/core/persistence/vector.py），
仍锁 M3。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_m2_npc_attributes"
down_revision: str | None = "0003_memory_write"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------------- npc_profiles (§12)
    op.create_table(
        "npc_profiles",
        sa.Column("id", sa.String, primary_key=True),  # NPC entity_id
        sa.Column("branch_id", sa.String, nullable=False),
        # 身份
        sa.Column("name", sa.String, nullable=False),
        sa.Column("species", sa.String, nullable=False, server_default="human"),
        sa.Column("gender", sa.String, nullable=False, server_default="unknown"),
        sa.Column("age", sa.Integer, nullable=False, server_default="0"),
        sa.Column("occupation", sa.String, nullable=False, server_default=""),
        sa.Column("identity_anchor", sa.Text, nullable=False, server_default=""),
        # OCEAN 人格（0-100）
        sa.Column("ocean_openness", sa.Integer, nullable=False, server_default="50"),
        sa.Column("ocean_conscientiousness", sa.Integer, nullable=False, server_default="50"),
        sa.Column("ocean_extraversion", sa.Integer, nullable=False, server_default="50"),
        sa.Column("ocean_agreeableness", sa.Integer, nullable=False, server_default="50"),
        sa.Column("ocean_neuroticism", sa.Integer, nullable=False, server_default="50"),
        # PAD 情绪（-1..1）
        sa.Column("pad_pleasure", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("pad_arousal", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("pad_dominance", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("emotion_updated_tick", sa.Integer, nullable=False, server_default="0"),
        # 集合型属性（JSON 文本）
        sa.Column("needs", sa.Text, nullable=False, server_default="[]"),
        sa.Column("skills", sa.Text, nullable=False, server_default="{}"),
        sa.Column("goals", sa.Text, nullable=False, server_default="{}"),
        sa.Column("inventory", sa.Text, nullable=False, server_default="[]"),
        sa.Column("knowledge_boundary", sa.Text, nullable=False, server_default="{}"),
        # LOD 与游标
        sa.Column("lod", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at_tick", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at_tick", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("idx_profiles_branch", "npc_profiles", ["branch_id"])
    op.create_index("idx_profiles_branch_lod", "npc_profiles", ["branch_id", "lod"])

    # ------------------------------------------------------------ npc_health (§13)
    op.create_table(
        "npc_health",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("npc_id", sa.String, nullable=False),
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("category", sa.String, nullable=False),  # codex HiddenCategory
        sa.Column("label", sa.String, nullable=False),
        sa.Column("severity", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("hidden", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("descriptors", sa.Text, nullable=False, server_default="[]"),
        sa.Column("trigger_conditions", sa.Text, nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at_tick", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("idx_health_npc", "npc_health", ["branch_id", "npc_id"])
    op.create_index("idx_health_hidden", "npc_health", ["branch_id", "hidden"])
    op.create_index("idx_health_category", "npc_health", ["branch_id", "category"])

    # ----------------------------------------------------------- matter_state (§13)
    op.create_table(
        "matter_state",
        sa.Column("subject_id", sa.String, nullable=False),
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("subject_kind", sa.String, nullable=False, server_default="structure"),
        sa.Column("material", sa.String, nullable=False, server_default=""),
        sa.Column("integrity", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("quality", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("decay_rate", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("load_bearing", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("supported_by", sa.Text, nullable=False, server_default="[]"),
        sa.Column("is_rubble", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("last_decay_tick", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at_tick", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint("subject_id"),
    )
    op.create_index("idx_matter_branch", "matter_state", ["branch_id"])
    op.create_index("idx_matter_branch_kind", "matter_state", ["branch_id", "subject_kind"])


def downgrade() -> None:
    op.drop_index("idx_matter_branch_kind", table_name="matter_state")
    op.drop_index("idx_matter_branch", table_name="matter_state")
    op.drop_table("matter_state")

    op.drop_index("idx_health_category", table_name="npc_health")
    op.drop_index("idx_health_hidden", table_name="npc_health")
    op.drop_index("idx_health_npc", table_name="npc_health")
    op.drop_table("npc_health")

    op.drop_index("idx_profiles_branch_lod", table_name="npc_profiles")
    op.drop_index("idx_profiles_branch", table_name="npc_profiles")
    op.drop_table("npc_profiles")
