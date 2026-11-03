"""创世档案补种共用的死亡过滤；只读既有 SessionFactory，不另开驱动。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select

from sim.core.events import EventKind
from sim.core.persistence.models import Branch, Event
from sim.core.persistence.store import SqlEventStore


def death_ids_from_history(history: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    """从 store 已解码的有界分支历史提取死者；payload 的键是 entity_id。"""
    return frozenset(
        event["payload"]["entity_id"]
        for event in history
        if event["event_type"] == EventKind.NPC_DEATH.value
    )


async def read_branch_death_ids(store: SqlEventStore, *, branch_id: str = "main") -> frozenset[str]:
    """本线 + 祖先分叉点前缀的死者；祖先的未来死亡不属于本线。

    尚无 Branch 行且没有目标分支事件才视作创世，不创建分支、不猜当前线。
    已有目标行时不依赖 is_current；孤立事件、缺祖先/缺 cutoff/循环等谱系错误
    照常抛出，禁止盲补。
    """
    async with store.session_factory() as session:
        if await session.get(Branch, branch_id) is None:
            if (
                await session.scalar(select(Event.seq).where(Event.branch_id == branch_id).limit(1))
            ) is not None:
                raise ValueError("missing branch history")
            return frozenset()
    return death_ids_from_history(await store.read_branch_history(branch_id))
