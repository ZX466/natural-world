"""稳定健康属性标识；历史十进制 id 保留原 attr_id，分支克隆复制 code。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_health_code"
down_revision: str | None = "0014_fires"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("npc_health", sa.Column("code", sa.Text(), nullable=True))
    op.execute("UPDATE npc_health SET code = CAST(id AS TEXT)")
    with op.batch_alter_table("npc_health") as batch:
        batch.alter_column("code", existing_type=sa.Text(), nullable=False)
        batch.create_index("uq_health_code", ["branch_id", "npc_id", "code"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("npc_health") as batch:
        batch.drop_index("uq_health_code")
        batch.drop_column("code")
