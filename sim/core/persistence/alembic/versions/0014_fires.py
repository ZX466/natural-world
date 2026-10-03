"""0014 — M5-A9：`fires` 建表（批次 D 火灾生态数据面 · 裁 33）

Revision ID: 0014_fires
Revises: 0013_power_state
Create Date: 2026-10-03

设计稿 `docs/data/m5-fire-data-preplan.md`（A8 预研，裁 31-1 授权预研案即施工案）；
事件面判定 `docs/api/m5-fire-api-prestudy.md`（K12，假设 **F1-F5**）；
安规钉 `docs/security/m5-fire-threatmodel.md`（S9，**D-1..D-7**）。

要点：

- **纯 ``create_table``** ⇒ 不需要 ``batch_alter_table``（0011/0013 同款判据：新建表直接
  带 CHECK；只有 ALTER 才需要 batch）。
- **复合主键** ``(branch_id, fire_id)``：一场火一行、分支内唯一（0008 ``npc_profiles`` 同款）。
- **只存生命周期**（起火 tick / 熄灭 tick / 物理终止态），**不存火势中间态**（强度/燃料/
  蔓延半径）：A8 §1.2 已裁「火场中间态不入库」⇒ 本表**不是** A3 的第 5 张不可重建表，
  物化包**不为火扩格式**（它有事件源 + fold 器 ⇒ 属可重放那一族）。
- **三条 CHECK**（0008 四件 CHECK 先例 + S9 **D-4**「成对不变式进 DB，不靠 Python if」）：
  坐标域（-1 哨兵 / 4096 寻路界，与 ``MatterPayload`` 同口径）、tick 非负、
  **``ended_tick`` 与 ``end`` 同有同无**（空串 = 仍在燃烧）。
- **零索引**：主键前导列即 ``branch_id`` ⇒ 分支查询走 PK 前缀（0013 同款判据）。
- **零归因**：无 actor/igniter/culprit 键（D-10 + K12 §3）。

⚠️ **与派单的一处偏差（已回执说明）**：派单写「快照双列 CHECK」。本表**没有**
``snapshot_seq``/``snapshot_tick``——火场是**事件纯函数投影**（有 fold 器）⇒ 与
``matter_state`` 同族，重建靠「快照 + 事件窗口重放」，**不需要快照指针**；加了就是
无人写入的**死列**（未来谎言）。批次 E 真要给火势物化基准点时，随那一单加列 + 同款
成对 CHECK（体例不变）。本表真正的成对不变式是 ``(ended_tick, end)``，已落 CHECK。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_fires"
down_revision: str | None = "0013_power_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 物理终止态值域（与 `events.py::FireEnd` 同源）。
FIRE_ENDS: tuple[str, ...] = ("out", "fuel_out", "doused")

#: 坐标域（与 `MatterPayload` 同哨兵语义：-1 = 未定位，4096 = 寻路界）。
COORD_MIN, COORD_LIMIT = -1, 4096


def _end_pair_clause() -> str:
    values = ", ".join(f"'{value}'" for value in FIRE_ENDS)
    return f"(ended_tick IS NULL AND end = '') OR (ended_tick IS NOT NULL AND end IN ({values}))"


def upgrade() -> None:
    op.create_table(
        "fires",
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("fire_id", sa.String(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False, server_default=sa.text("-1")),
        sa.Column("y", sa.Integer(), nullable=False, server_default=sa.text("-1")),
        sa.Column("ignited_tick", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ended_tick", sa.Integer(), nullable=True),
        sa.Column("end", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("branch_id", "fire_id"),
        sa.CheckConstraint(
            f"x >= {COORD_MIN} AND x < {COORD_LIMIT} AND y >= {COORD_MIN} AND y < {COORD_LIMIT}",
            name="ck_fires_xy_domain",
        ),
        sa.CheckConstraint(
            "ignited_tick >= 0 AND (ended_tick IS NULL OR ended_tick >= 0)",
            name="ck_fires_tick_nonneg",
        ),
        sa.CheckConstraint(_end_pair_clause(), name="ck_fires_end_pair"),
    )


def downgrade() -> None:
    """结构性回退：drop 表（火场生命周期是运行期事实，降级即放弃这段火灾历史）。"""
    op.drop_table("fires")
