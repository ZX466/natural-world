"""0013 — M5-A7：`npc_power` 建表（批次 C 权力机制数据面）

Revision ID: 0013_power_state
Revises: 0012_branches_current
Create Date: 2026-10-02

设计稿：`docs/data/m5-power-data-preplan.md`（裁 31-1 授权：预研稿推荐案 = 施工案）。
判据：`docs/security/m5-authority-criteria-preplan.md`（D-10 权力不可见 + 红线 A
「事件 kind 不得新增」+ 红线 B 禁键集）。

要点：

- **纯 ``create_table``** ⇒ 不需要 ``batch_alter_table``（0008 因 CHECK 才需要 batch，
  0009/0012 是纯 ``add_column``；新建表直接带 CHECK，0011 同款）。
- **复合主键** ``(branch_id, npc_id)``（0008 ``npc_profiles`` 同款）：分叉后同 id 跨分支共存。
- **量纲归一到 [-1, 1]**：``0`` = 与玩家平权。两条 CHECK 把「越界值」在**数据库层**挡住
  （写面另有夹取 + ``clamped`` 事实上报，双保险；机制若要原始分 = 改这两条 CHECK）。
- **列名故意落在 codex 红线 B 的禁键集里**（``power_level``）：本表**永不出站**
  （D-10），而禁键扫描按**键名**精确匹配 ⇒ 将来任何意外序列化会被当场扫红，而不是靠
  review 记忆。改名必须先改 codex 稿禁键集（变更纪律），不许悄悄换中性名。
- **零索引**：主键前导列就是 ``branch_id`` ⇒ 分支查询走 PK 前缀，再加索引是纯冗余。
- **无事件源**（红线 A：不新增 kind）⇒ 本表属 A3「不可重建」族**第 4 张**
  （登记见 ``m5-anchor-materialization-preplan.md``）⇒ 历史点读档拿不到本表的值，
  由批次 E 物化单收口。本迁移**不**扩 ``anchor_packages.corpus_blob`` 格式。
- **零回填**：既有库无本表 ⇒ 无行可填（表是新的）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_power_state"
down_revision: str | None = "0012_branches_current"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 量纲边界（与 `models.py::NpcPower` / `power_store.py::POWER_MIN/POWER_MAX` 同源）。
POWER_MIN = -1.0
POWER_MAX = 1.0


def upgrade() -> None:
    op.create_table(
        "npc_power",
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("npc_id", sa.String(), nullable=False),
        sa.Column("power_level", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at_tick", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("branch_id", "npc_id"),
        sa.CheckConstraint(
            f"power_level >= {POWER_MIN} AND power_level <= {POWER_MAX}",
            name="ck_npc_power_level_range",
        ),
        sa.CheckConstraint("updated_at_tick >= 0", name="ck_npc_power_tick_nonneg"),
    )


def downgrade() -> None:
    """结构性回退：drop 表（无数据语句 ⇒ 无回填可撤销；降 0013 = 放弃权力历史）。"""
    op.drop_table("npc_power")
