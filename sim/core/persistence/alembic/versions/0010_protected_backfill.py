"""0010 — M5-A2：player_anchors 末梢档强制保护回填（GAP-B）

Revision ID: 0010_protected_backfill
Revises: 0009_branches_rng_state
Create Date: 2026-09-29

`player_anchors.protected` 列在 0008 已随裁 9 落地，但**既有行全是 0**——
「最新档必须受保护」这条产品语义（kilo M5-K5 的 GAP-B）没有落进数据。0010 做
**只回填、不切列**的数据迁移：把末梢那一档置 ``protected=1``。

判据与 K3 ``GET /api/anchors/current`` 同口径（``anchors.py::current_item``）：
``ORDER BY updated_at DESC, id DESC LIMIT 1``——同刻多行按 id 降序兜底，保证结果
确定可复现。**全表无行时零行更新是合法态**（子查询返回 NULL → ``WHERE id = NULL``
匹配零行），不报错。

**只回填、不切读路径**（裁 26-C④）：读路径仍是派生式
（``anchors.py::list_items`` 的 ``row.updated_at >= max(updated_at)``），CRUD 单才切成
读列。⚠️ 两口径在**同刻多行**时不一致（派生式标 N 行、回填标 1 行）——已上报 kilo，
`list_items` 需补 id 兜底或于 CRUD 落地后让派生式退休。

**downgrade 不撤销回填**（有意决定）：0010 的效果是让「列」与「仍在役的派生式」一致；
撤销它反而制造矛盾（派生式仍会把末梢算成 protected=True，而列变成 0）。downgrade
只做结构性回退——本迁移无 schema 变化，故为 no-op（重复 upgrade 幂等）。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_protected_backfill"
down_revision: str | None = "0009_branches_rng_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 末档保护回填（与 K3 `/current` 同口径；测试按源码逐字比对，防两处漂移）。
BACKFILL_SQL = (
    "UPDATE player_anchors SET protected = 1 WHERE id = ("
    " SELECT id FROM player_anchors ORDER BY updated_at DESC, id DESC LIMIT 1)"
)


def upgrade() -> None:
    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    """无 schema 变化 ⇒ no-op；回填**不撤销**（理由见模块 docstring）。"""
