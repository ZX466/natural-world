"""0009 — M5-A-DATA：branches.rng_state（裁 27-B b2，随机连续性承接）

Revision ID: 0009_branches_rng_state
Revises: 0008_m5_fork_identity
Create Date: 2026-09-28

读档 = 分叉时，随机流必须**承接抽签进度**，否则接缝处行为跳变（T2 破）。实测
（`docs/data/m5-fork-archive-preplan.md` §6.3）：``RngRegistry`` 只记 ``world_seed``
与熵材料，抽签进度活在调用方持有的 PCG64 生成器里 ⇒ **存一个 seed 不足**（只承接
registry 时后续抽签必然不同），必须承接可序列化状态包（≈198 B/流）。

落 `branches.rng_state`（b2）而非子分支快照（b1）：分支自带状态 ⇒ **可连续分叉链**；
且由 fork 事务**原子**写入（与克隆同生共死，无半写）。`NULL` = 该分支未承接过状态
（根分支 / 调用方未提供）。

SQLite 注意：纯 ``add_column``（可空、无 CHECK、无 server_default）——**不需要
``batch_alter_table``**（0008 的 CHECK 才需要）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_branches_rng_state"
down_revision: str | None = "0008_m5_fork_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("branches", sa.Column("rng_state", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("branches", "rng_state")
