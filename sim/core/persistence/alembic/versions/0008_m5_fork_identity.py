"""0008 — M5-D3-a：分叉身份四件（裁 1 / 3 / 4 / 9）

Revision ID: 0008_m5_fork_identity
Revises: 0007_m4_material_balances
Create Date: 2026-09-28

读档 = 分叉（DESIGN §12）要能承载「同一业务 id 在不同分支各自存在」与「跨分支
引用」。本迁移落四件：

- **a** ``npc_profiles`` 主键 ``id`` → ``(branch_id, id)``（裁 1 = F1 硬前置）：
  本表曾是 13 张表里唯一主键不带分支的例外，同 npc_id 跨分支物理不可能共存 →
  分叉克隆必撞主键。改后克隆只需 ``INSERT … SELECT`` 换 ``branch_id`` 值；
- **3** ``events.parent_branch_id``：``parent_seq`` 是分支内引用，跨分支谱系引用
  需要指名父事件住在哪个分支（``NULL`` = 本分支，既有行零回填）；
- **4** ``knowledge.evidence_branch_id``：同上，封 C4「证据跨分支悬空」；
- **9** ``player_anchors.protected``：与 kilo 锚点 CRUD 面合并（DELETE protected → 409）。

两条成对不变式落 DB CHECK（可表达约束进 DB，沿 0005 先例）：
``ck_events_parent_branch_pair`` / ``ck_knowledge_evidence_pair``——**单向**：
「指名分支必给 seq」，而 ``(NULL, seq)``（引用在本分支）合法且是既有行的常态。

**SQLite 注意**：改主键需重建表，用 ``op.batch_alter_table``；0004 建的旧 PK 未命名，
``naming_convention`` 先把它规范成 ``pk_npc_profiles_id`` 再删（0006 同款手法）。

**downgrade 的前置条件**：还原 ``npc_profiles`` 单列主键要求**库内不存在同 id 跨分支
共存行**（否则重建表时主键冲突）。本仓开发库一直是单分支，0008 之后产生的分叉数据
不可降级到 0007（正常路径不需要回退，downgrade 只服务迁移往返验证）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_m5_fork_identity"
down_revision: str | None = "0007_m4_material_balances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMING_CONVENTION = {"pk": "pk_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    # --- a：npc_profiles 分支复合身份（裁 1）---
    with op.batch_alter_table("npc_profiles", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("pk_npc_profiles_id", type_="primary")
        batch_op.create_primary_key("pk_npc_profiles_branch_id", ["branch_id", "id"])

    # --- 3：events.parent_branch_id（谱系引用的另一半）---
    # CHECK 属表级约束，ADD COLUMN 表达不了 → batch（建新表→拷数据→换名），0005 同款。
    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(sa.Column("parent_branch_id", sa.String, nullable=True))
        batch_op.create_check_constraint(
            "ck_events_parent_branch_pair",
            "parent_branch_id IS NULL OR parent_seq IS NOT NULL",
        )
    op.create_index(
        "idx_events_parent_branch",
        "events",
        ["parent_branch_id", "parent_seq"],
    )

    # --- 4：knowledge.evidence_branch_id（封 C4 跨分支悬空）---
    with op.batch_alter_table("knowledge") as batch_op:
        batch_op.add_column(sa.Column("evidence_branch_id", sa.String, nullable=True))
        batch_op.create_check_constraint(
            "ck_knowledge_evidence_pair",
            "evidence_branch_id IS NULL OR evidence_seq IS NOT NULL",
        )
    op.create_index(
        "idx_knowledge_evidence",
        "knowledge",
        ["branch_id", "evidence_branch_id", "evidence_seq"],
    )

    # --- 9：player_anchors.protected（与 kilo 锚点面合并）---
    op.add_column(
        "player_anchors",
        sa.Column("protected", sa.Boolean, nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("player_anchors", "protected")

    op.drop_index("idx_knowledge_evidence", table_name="knowledge")
    with op.batch_alter_table("knowledge") as batch_op:
        batch_op.drop_constraint("ck_knowledge_evidence_pair", type_="check")
        batch_op.drop_column("evidence_branch_id")

    op.drop_index("idx_events_parent_branch", table_name="events")
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_constraint("ck_events_parent_branch_pair", type_="check")
        batch_op.drop_column("parent_branch_id")

    # 需库内无同 id 跨分支共存行（见模块 docstring）。
    with op.batch_alter_table("npc_profiles", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("pk_npc_profiles_branch_id", type_="primary")
        batch_op.create_primary_key("pk_npc_profiles_id", ["id"])
