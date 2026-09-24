"""0005 — M3：knowledge 治理列 + 证据链派生键（B3 实施，裁 10 全采）

Revision ID: 0005_m3_knowledge_governance
Revises: 0004_m2_npc_attributes
Create Date: 2026-09-24

对齐 codex docs/security/m3-evidence-chain.md §5（数据需求）+ §6（S5/R1 对表）
+ docs/data/knowledge-five-cols-proposal.md（opencode M3-D3 提案，裁 10 全采）
+ docs/data/schema.md §8。

内容（knowledge 表，0002 已建空表 → add_column 无需回填）：
- 证据链派生键四列：subject_npc_id / subject_attr_id / evidence_seq /
  source_knowledge_id（told 链回溯键 = 级联递归的索引起点）；
- 治理三列：source_memory（派生源记忆 entry_id，R1 级联起点）/ invalidated
  （独立失效位——knowledge 无「替代行」语义）/ invalid_reason（结构化原因串）；
- 索引三列：级联起点 (branch_id, source_memory)、told 链递归
  (branch_id, source_knowledge_id)、按主体+属性查 (branch_id, subject_npc_id,
  subject_attr_id)；
- CHECK 三条：source 取值域、confidence 值域、subject 两列成对（自身事实两列同 NULL）。

governance 语义（§6 终裁）：**继承失效、不继承替代**——源记忆 supersede →
派生 knowledge 行置 invalidated=1，沿 source_knowledge_id 向下递归，无替代行。

SQLite 注意：CHECK 属表级约束，ADD COLUMN 表达不了，故本迁移用
``op.batch_alter_table``（SQLite 走「建新表→拷数据→换名」），列与 CHECK 同批落。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_m3_knowledge_governance"
down_revision: str | None = "0004_m2_npc_attributes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge") as batch_op:
        # ---- 证据链派生键（evidence-chain §5）----
        batch_op.add_column(sa.Column("subject_npc_id", sa.String, nullable=True))
        batch_op.add_column(sa.Column("subject_attr_id", sa.String, nullable=True))
        batch_op.add_column(sa.Column("evidence_seq", sa.Integer, nullable=True))
        batch_op.add_column(sa.Column("source_knowledge_id", sa.Integer, nullable=True))
        # ---- 治理列（R1/S5：继承失效、不继承替代）----
        batch_op.add_column(sa.Column("source_memory", sa.String, nullable=True))
        batch_op.add_column(
            sa.Column("invalidated", sa.Boolean, nullable=False, server_default=sa.text("0"))
        )
        batch_op.add_column(sa.Column("invalid_reason", sa.String, nullable=True))
        # ---- CHECK（表级约束，ADD COLUMN 表达不了，与列同批落）----
        batch_op.create_check_constraint(
            "ck_knowledge_source",
            "source IN ('witnessed', 'told', 'inferred')",
        )
        batch_op.create_check_constraint(
            "ck_knowledge_confidence",
            "confidence >= 0.0 AND confidence <= 1.0",
        )
        batch_op.create_check_constraint(
            "ck_knowledge_subject_pair",
            "(subject_npc_id IS NULL) = (subject_attr_id IS NULL)",
        )

    op.create_index("idx_knowledge_source_memory", "knowledge", ["branch_id", "source_memory"])
    op.create_index("idx_knowledge_source_kid", "knowledge", ["branch_id", "source_knowledge_id"])
    op.create_index(
        "idx_knowledge_subject",
        "knowledge",
        ["branch_id", "subject_npc_id", "subject_attr_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_subject", table_name="knowledge")
    op.drop_index("idx_knowledge_source_kid", table_name="knowledge")
    op.drop_index("idx_knowledge_source_memory", table_name="knowledge")

    with op.batch_alter_table("knowledge") as batch_op:
        batch_op.drop_constraint("ck_knowledge_subject_pair", type_="check")
        batch_op.drop_constraint("ck_knowledge_confidence", type_="check")
        batch_op.drop_constraint("ck_knowledge_source", type_="check")
        batch_op.drop_column("invalid_reason")
        batch_op.drop_column("invalidated")
        batch_op.drop_column("source_memory")
        batch_op.drop_column("source_knowledge_id")
        batch_op.drop_column("evidence_seq")
        batch_op.drop_column("subject_attr_id")
        batch_op.drop_column("subject_npc_id")
