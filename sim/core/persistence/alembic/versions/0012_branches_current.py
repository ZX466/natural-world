"""0012 — M5-A5：`branches.is_current`（当前活跃分支真源载体）+ 回填

Revision ID: 0012_branches_current
Revises: 0011_anchor_packages
Create Date: 2026-10-01

条款：`docs/data/m5-r4-active-branch-contract.md` R-4.1/R-4.3（codex S4 缺陷 R-4：
分支硬编码 `'main'` ⇒ 分叉后记档指错世界线）。本迁移只落**数据面**：

1. **列**：`branches.is_current BOOLEAN NOT NULL DEFAULT 0`。「当前」从「靠 recency /
   ``status='active'`` 猜」变成**可判定、可索引的显式载体**。纯 ``add_column``
   （无 CHECK）⇒ **不需要** ``batch_alter_table``（0008 加 CHECK 才需要，0009 同款）。
2. **部分唯一索引** ``ux_branches_current ON branches(is_current) WHERE is_current = 1``：
   索引值恒为 1 ⇒ 第二个 ``is_current=1`` 的行**撞唯一索引** ⇒ 「至多一个当前」这条
   不变量由**数据库层**保证，失败面落在写入层（``IntegrityError`` ⇒ fail-closed）。
   应用层检查会被并发绕过，索引不会。
3. **回填**（0010 同款判据：只做必要的、幂等、零行合法）：把**唯一** ``status='active'``
   的那一行置 1。**≥2 个 active ⇒ 一行都不置**（世界线状态歧义，报给运维重开世界，
   **不按 recency 兜底**——recency 选法会把「玩家在跑的线」换成「最近被分叉出去的线」，
   正是 R-4 要根治的病）；0 个 active ⇒ 零行更新（合法态）。

**不否决的部分**：R-4.5「读档子线可以多条并存」与本索引**不矛盾**——读档子线
（anchor-fork 的历史点分叉产物）按 R-4.4 是 ``is_current=0`` 的普通行。

⚠️ **本迁移不移动当前行**。head-fork 的「当前行移交子分支」与 anchor-fork 的「父分支保持
当前」写在 ``fork.py``（R-4 **施工单**，架构域）：分叉事务里必须**同一事务**清父置子，
否则第二个 ``is_current=1`` 直接 IntegrityError（这正是本索引要它必须同事务的原因）。
在施工单落地前，head-fork 后当前行仍停在**已被封存的父分支**上（读档侧因此报
「无当前分支」，属已知缺口，见回执）。

> **钉已预置**（M5-A10 / G3 小单，2026-10-03）：交接归属的**双态钉**已落在
> ``sim/tests/test_m5_anchors_branch_source.py::TestForkHandoverForm`` —— 交接未落 ⇒
> 「父仍持当前位 + 子非当前」（今日）；交接已落 ⇒「子当前 + 父 ``abandoned``」；锁信号 =
> ``fork.py`` 的**代码**里出现 ``is_current``。该小单**零生产码**（只改钉 + 本行指针），
> 故 0012 依旧只提供载体与索引，交接写入仍等 R-4 施工单。
>
> **✅ 交接已落**（M5-R4 施工，2026-10-03，Claude 域）：``fork.py`` 已实现同事务交接——
> head-fork 先清父（``UPDATE is_current = 0``）再插子（``is_current = 1``，次序铁律：
> 部分唯一索引是**语句级**校验，反序必撞 UNIQUE）；anchor-fork 子线 ``is_current = 0``
> 父线保持当前。上述「已知缺口」（head-fork 后读档侧报无当前分支）**就此关闭**；
> 双态钉此后恒走「已落」分支。

**downgrade**：回填**不撤销**（同 0010 的理由：撤销反而制造「列与在役派生式互相矛盾」的
状态），只做结构性回退——drop 索引 + drop 列；重复 upgrade 幂等。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_branches_current"
down_revision: str | None = "0011_anchor_packages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 「至多一个当前」的部分唯一索引：索引列值恒为 1 ⇒ 第二行撞唯一约束。
CURRENT_INDEX_NAME = "ux_branches_current"
CURRENT_INDEX_WHERE = "is_current = 1"

#: 当前行回填：**唯一** active 的那一行置 1；≥2 个 active ⇒ 子查询匹配零行
#: （**不按 recency 兜底**，理由见模块 docstring）；0 个 active 同样零行（合法态）。
#: 幂等：重复执行结果不变（已是 1 的行重写为 1）。
BACKFILL_SQL = (
    "UPDATE branches SET is_current = 1 WHERE id = ("
    " SELECT id FROM branches WHERE status = 'active'"
    " AND (SELECT COUNT(*) FROM branches WHERE status = 'active') = 1)"
)


def upgrade() -> None:
    op.add_column(
        "branches",
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.execute(BACKFILL_SQL)
    op.create_index(
        CURRENT_INDEX_NAME,
        "branches",
        ["is_current"],
        unique=True,
        sqlite_where=sa.text(CURRENT_INDEX_WHERE),
    )


def downgrade() -> None:
    """结构性回退：drop 索引 + drop 列。回填**不撤销**（理由见模块 docstring）。"""
    op.drop_index(CURRENT_INDEX_NAME, table_name="branches")
    op.drop_column("branches", "is_current")
