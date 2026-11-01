"""启动时读取当前分支的检查点墙钟水位；这些控制元数据不进世界状态/事件。"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from sqlalchemy import select

from sim.core.persistence.models import Branch, Snapshot
from sim.core.persistence.store import SqlEventStore


def checkpoint_epoch(value: object) -> float:
    """兼容历史 ISO 时间与现行 epoch；无时区的旧 ISO 按 UTC 解释。"""
    if isinstance(value, bool):
        raise ValueError("invalid checkpoint wall time")
    if isinstance(value, (int, float)):
        epoch = float(value)
    elif isinstance(value, str):
        try:
            epoch = float(value)
        except ValueError:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            epoch = parsed.timestamp()
    else:
        raise ValueError("invalid checkpoint wall time")
    if not math.isfinite(epoch) or epoch < 0:
        raise ValueError("invalid checkpoint wall time")
    return epoch


async def last_recorded_at(store: SqlEventStore, branch_id: str) -> float:
    async with store.session_factory() as session:
        branch = await session.get(Branch, branch_id)
        if branch is None or branch.status != "active" or not branch.is_current:
            raise ValueError("offline progression requires the current active branch")
        value = await session.scalar(
            select(Snapshot.created_at)
            .where(Snapshot.branch_id == branch_id)
            .order_by(Snapshot.tick.desc(), Snapshot.seq.desc())
            .limit(1)
        )
        return checkpoint_epoch(branch.created_at if value is None else value)
