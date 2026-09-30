"""0011 — M5-A4：`anchor_packages` 建表（anchor 世界态物化包，A3 §1.1）

Revision ID: 0011_anchor_packages
Revises: 0010_protected_backfill
Create Date: 2026-09-30

设计稿：`docs/data/m5-anchor-materialization-preplan.md` §1.1（批次 E 前置）。本迁移
**只建表、不回填**（老档无包且 anchor 时刻 `rng_state` 不可得 ⇒ 不可物化，见 A3 §2）⇒
纯 ``create_table``，无 batch、无数据语句。

要点：

- ``anchor_id`` 1:1 于 ``player_anchors.id``（不建 FK：``player_anchors`` 是「档面」，
  删除语义归 kilo 的 CRUD 面；此处只保证 1:1 语义，不越域设约束）。
- ``rng_state`` **可空**：NULL ⇒ 该档不可物化（``AnchorMaterializationError``），
  **禁止**用 ``Branch.seed`` 派生兜底（seed 不含 PCG64 进度 ⇒ 抽签跳变，A2 已实测）。
- ``snapshot_seq``/``snapshot_tick`` 是**引用**（(branch_id, seq) 指 ``snapshots`` 行），
  不复制 blob ⇒ 快照被 GC 时退化为「全前缀重放」，语料/rng 仍在包内。
- ``corpus_blob`` 是 gzip JSON 的 3 张不可重建表行值（``npc_memories``/``knowledge``/
  ``relationships``），格式契约归物化实现单（A3 §1.4）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_anchor_packages"
down_revision: str | None = "0010_protected_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anchor_packages",
        sa.Column("anchor_id", sa.String(), nullable=False),
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("snapshot_seq", sa.Integer(), nullable=True),
        sa.Column("snapshot_tick", sa.Integer(), nullable=True),
        sa.Column("rng_state", sa.Text(), nullable=True),
        sa.Column("agent_override", sa.Text(), nullable=False),
        sa.Column("corpus_blob", sa.LargeBinary(), nullable=True),
        sa.Column("state_hash", sa.String(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("anchor_id"),
        sa.CheckConstraint(
            "(snapshot_seq IS NULL AND snapshot_tick IS NULL)"
            " OR (snapshot_seq IS NOT NULL AND snapshot_tick IS NOT NULL)",
            name="ck_anchor_packages_snapshot_pair",
        ),
    )
    op.create_index("idx_anchor_packages_branch", "anchor_packages", ["branch_id"])


def downgrade() -> None:
    op.drop_index("idx_anchor_packages_branch", table_name="anchor_packages")
    op.drop_table("anchor_packages")
