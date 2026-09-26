"""0007 — M4-D2d：材料余额投影（裁 14-2 ⑦）

Revision ID: 0007_m4_material_balances
Revises: 0006_m4_structures
Create Date: 2026-09-26

MATERIAL_MOVED 是材料转移真相；本表只存 `(branch, ref, material)` 当前净余额，
供同批事务内扣减/入账与守恒断言。`world:*` 允许净负（外部供给基准），
`npc/structure` 非负由投影 fail-closed。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_m4_material_balances"
down_revision: str | None = "0006_m4_structures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material_balances",
        sa.Column("branch_id", sa.String, nullable=False),
        sa.Column("ref", sa.String, nullable=False),
        sa.Column("material_id", sa.String, nullable=False),
        sa.Column("quantity", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("updated_at_tick", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint(
            "branch_id",
            "ref",
            "material_id",
            name="pk_material_balances_branch_id",
        ),
    )
    op.create_index(
        "idx_material_branch_material",
        "material_balances",
        ["branch_id", "material_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_material_branch_material", table_name="material_balances")
    op.drop_table("material_balances")
