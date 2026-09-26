"""0006 — M4-D2：structures 拓扑投影 + matter 分支复合身份（裁 14-2）

Revision ID: 0006_m4_structures
Revises: 0005_m3_knowledge_governance
Create Date: 2026-09-26

内容：
- 新建 ``structures``：只存拓扑与生命周期（tiles/kind/material/phase/
  load_bearing/supported_by/owner/built_by/built_at），不复制 matter 熵态列；
- 主键 ``(branch_id, structure_id)``，允许同 id 在不同分支共存；
- ``matter_state`` 主键由 ``subject_id`` 改为 ``(branch_id, subject_id)``，
  关闭跨分支投影串写；既有列与索引保持不变。

SQLite 注意：改主键需重建表，故用 ``op.batch_alter_table``；0004 建的旧 PK
未命名，``naming_convention`` 把它规范成 ``pk_matter_state_subject_id`` 后再删。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_m4_structures"
down_revision: str | None = "0005_m3_knowledge_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMING_CONVENTION = {"pk": "pk_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    with op.batch_alter_table("matter_state", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("pk_matter_state_subject_id", type_="primary")
        batch_op.create_primary_key("pk_matter_state_branch_subject", ["branch_id", "subject_id"])

    op.create_table(
        "structures",
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("structure_id", sa.String, nullable=False),
        sa.Column("tiles", sa.Text, nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("material", sa.String, nullable=False),
        sa.Column("phase", sa.String, nullable=False, server_default="building"),
        sa.Column("load_bearing", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("supported_by", sa.Text, nullable=False, server_default="[]"),
        sa.Column("owner_id", sa.String, nullable=True),
        sa.Column("built_by", sa.String, nullable=True),
        sa.Column("built_at", sa.Integer, nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint("branch_id", "structure_id", name="pk_structures_branch_id"),
    )
    op.create_index("idx_struct_branch", "structures", ["branch_id"])
    op.create_index("idx_struct_owner", "structures", ["branch_id", "owner_id"])
    op.create_index("idx_struct_phase", "structures", ["branch_id", "phase"])


def downgrade() -> None:
    op.drop_index("idx_struct_phase", table_name="structures")
    op.drop_index("idx_struct_owner", table_name="structures")
    op.drop_index("idx_struct_branch", table_name="structures")
    op.drop_table("structures")

    with op.batch_alter_table("matter_state", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("pk_matter_state_branch_subject", type_="primary")
        batch_op.create_primary_key("pk_matter_state_subject_id", ["subject_id"])
