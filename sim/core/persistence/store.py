"""EventStore 实现 — m0-core.md §8 Protocol

唯一写路径：append → 分配 seq → INSERT INTO events。
读取路径：read_range → SELECT ... ORDER BY seq。
快照路径：write_snapshot / latest_snapshot。
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sqlalchemy import func, select

from sim.core.persistence.models import Event, Snapshot

# ---------------------------------------------------------------------------
# Protocol 定义（m0-core.md §8）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SnapshotData:
    """快照的数据表示。"""
    branch_id: str
    seq: int
    tick: int
    data: bytes  # gzip 压缩的 JSON


@runtime_checkable
class EventStore(Protocol):
    """持久化接口 — m0-core.md §8。"""

    async def append(self, branch_id: str, events: list[dict]) -> None:
        """分配分支内 seq，append-only 写入。events 为 WorldEvent 字典列表。"""
        ...

    async def read_range(
        self, branch_id: str, frm: int, to: int
    ) -> list[dict]:
        """读取 [frm, to] 闭区间内的事件，按 seq 升序。"""
        ...

    async def write_snapshot(
        self, branch_id: str, tick: int, blob: bytes
    ) -> None:
        """写入快照（gzip 压缩的全量状态）。"""
        ...

    async def latest_snapshot(
        self, branch_id: str, before_tick: int
    ) -> SnapshotData | None:
        """获取 before_tick 之前（含）的最新快照。"""
        ...


# ---------------------------------------------------------------------------
# SQLAlchemy 实现
# ---------------------------------------------------------------------------

class SqlEventStore:
    """基于 SQLAlchemy 2.0 async + aiosqlite 的 EventStore 实现。"""

    def __init__(self, session_factory) -> None:
        """
        Args:
            session_factory: async session 工厂（async_sessionmaker）。
        """
        self._session_factory = session_factory

    async def append(self, branch_id: str, events: list[dict]) -> None:
        """分配分支内 seq，批量写入 events 表。"""
        if not events:
            return

        async with self._session_factory() as session:
            # 获取当前最大 seq
            result = await session.execute(
                select(func.coalesce(func.max(Event.seq), 0)).where(
                    Event.branch_id == branch_id
                )
            )
            max_seq: int = result.scalar() or 0

            for i, event in enumerate(events):
                ev = Event(
                    branch_id=branch_id,
                    seq=max_seq + i + 1,
                    tick=event["tick"],
                    event_type=event["event_type"],
                    actor_id=event.get("actor_id", ""),
                    target_id=event.get("target_id"),
                    parent_seq=event.get("parent_seq"),
                    payload=json.dumps(event.get("payload", {}), ensure_ascii=False),
                    witnesses=json.dumps(event.get("witnesses", []), ensure_ascii=False),
                    entropy_ref=event.get("entropy_ref"),
                )
                session.add(ev)

            await session.commit()

    async def read_range(
        self, branch_id: str, frm: int, to: int
    ) -> list[dict]:
        """读取 [frm, to] 闭区间内的事件，按 seq 升序。"""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Event)
                .where(Event.branch_id == branch_id)
                .where(Event.seq >= frm)
                .where(Event.seq <= to)
                .order_by(Event.seq)
            )
            rows = result.scalars().all()
            return [_event_to_dict(r) for r in rows]

    async def write_snapshot(
        self, branch_id: str, tick: int, blob: bytes
    ) -> None:
        """写入快照。seq 由当前最大 seq + 1 分配。"""
        compressed = gzip.compress(blob, compresslevel=6)

        async with self._session_factory() as session:
            result = await session.execute(
                select(func.coalesce(func.max(Snapshot.seq), 0)).where(
                    Snapshot.branch_id == branch_id
                )
            )
            max_seq: int = result.scalar() or 0

            snap = Snapshot(
                branch_id=branch_id,
                seq=max_seq + 1,
                tick=tick,
                snapshot_data=compressed,
                is_cold=False,
            )
            session.add(snap)
            await session.commit()

    async def latest_snapshot(
        self, branch_id: str, before_tick: int
    ) -> SnapshotData | None:
        """获取 before_tick 之前（含）的最新快照。"""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Snapshot)
                .where(Snapshot.branch_id == branch_id)
                .where(Snapshot.tick <= before_tick)
                .order_by(Snapshot.tick.desc(), Snapshot.seq.desc())
                .limit(1)
            )
            snap = result.scalar_one_or_none()
            if snap is None:
                return None
            return SnapshotData(
                branch_id=snap.branch_id,
                seq=snap.seq,
                tick=snap.tick,
                data=snap.snapshot_data,
            )


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _event_to_dict(event: Event) -> dict:
    """将 ORM Event 对象转为字典。"""
    return {
        "branch_id": event.branch_id,
        "seq": event.seq,
        "tick": event.tick,
        "event_type": event.event_type,
        "actor_id": event.actor_id,
        "target_id": event.target_id,
        "parent_seq": event.parent_seq,
        "payload": json.loads(event.payload),
        "witnesses": json.loads(event.witnesses),
        "entropy_ref": event.entropy_ref,
    }


def decompress_snapshot(snap: SnapshotData) -> dict:
    """解压快照数据为字典。"""
    return json.loads(gzip.decompress(snap.data))
