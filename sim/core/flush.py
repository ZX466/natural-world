"""sim/api 之外的 flush 适配层 — TickLoop 事件 → EventStore（C05）。

把 loop.pending_events 转成 store.append 形状；entropy_inject 事件同步派生
entropy_log 行，与事件同事务落库（codex 复审硬约束：entropy_log 与 events
原子，失败无半写状态）。
"""

from __future__ import annotations

from typing import Any, Protocol

from sim.core.events import EventKind, WorldEvent


class EventStoreLike(Protocol):
    async def append(
        self,
        branch_id: str,
        events: list[dict[str, Any]],
        entropy_rows: list[dict[str, Any]] | None = None,
    ) -> None: ...


def flush_rows(events: list[WorldEvent]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """事件 → (store 行, entropy 行)。熵行与事件行同 tick 同源，append 同事务写入。

    每条 entropy 行带 ``event_index``（= 派生它的 ``entropy_inject`` 事件在 events
    列表中的下标）；``store.append`` 分配 seq 后据此把 ``event_seq`` 回填到
    entropy_log（D04 记账项），事件与熵行同事务，无半写。
    """
    store_rows: list[dict[str, Any]] = []
    entropy_rows: list[dict[str, Any]] = []
    for i, e in enumerate(events):
        store_rows.append(e.to_store_dict())
        if e.event_type is EventKind.ENTROPY_INJECT:
            payload = e.payload
            entropy_rows.append(
                {
                    "stream": str(payload.get("stream", "")),
                    "reason": "entropy_inject",
                    "tick": e.tick,
                    "value": str(payload.get("material", "")),
                    "event_index": i,
                }
            )
    return store_rows, entropy_rows


async def flush_events(
    store: EventStoreLike, events: list[WorldEvent], branch_id: str = "main"
) -> None:
    """外层驱动每帧调用：事件与熵行同事务落库。"""
    if not events:
        return
    rows, entropy_rows = flush_rows(events)
    await store.append(branch_id, rows, entropy_rows=entropy_rows or None)
