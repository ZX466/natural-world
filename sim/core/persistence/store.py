"""EventStore 实现 — m0-core.md §8 Protocol

唯一写路径：append → 分配 seq → INSERT INTO events。
读取路径：read_range → SELECT ... ORDER BY seq。
快照路径：write_snapshot / latest_snapshot。
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sim.core.persistence.models import EntropyLog, Event, Snapshot

# 快照 payload 结构版本（codex 建议项：schema_version，M5 前必须）
SNAPSHOT_SCHEMA_VERSION = 1

#: M2-D2 投影回调：在 append 的同一事务内被调用（session + event_index→seq 映射）。
ProjectionFn = Callable[[AsyncSession, dict[int, int]], Awaitable[None]]

# ---------------------------------------------------------------------------
# Protocol 定义（m0-core.md §8）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotData:
    """快照的数据表示。

    seq 语义：等于快照点的事件流最大 events.seq（codex 必须项 #3）。
    """

    branch_id: str
    seq: int  # = 快照点 events 最大 seq
    tick: int
    data: bytes  # gzip 压缩的 JSON
    schema_version: int = 1


@runtime_checkable
class EventStore(Protocol):
    """持久化接口 — m0-core.md §8。"""

    async def append(
        self,
        branch_id: str,
        events: list[dict],
        entropy_rows: list[dict] | None = None,
        projection: ProjectionFn | None = None,
    ) -> None:
        """分配分支内 seq，append-only 写入。

        events 为 WorldEvent 字典列表。
        entropy_rows（codex 必须项 #2 预留）：可选的熵日志行，与事件在同一事务内
        原子写入；None 时仅写 events（当前内核把熵材料存于 event payload，无需双写）。
        """
        ...

    async def read_range(self, branch_id: str, frm: int, to: int) -> list[dict]:
        """读取 [frm, to] 闭区间内的事件，按 seq 升序。"""
        ...

    async def write_snapshot(self, branch_id: str, tick: int, event_seq: int, blob: bytes) -> None:
        """写入快照（gzip 压缩的全量状态）。

        event_seq：快照点当前事件流的最大 events.seq，落库为 snapshots.seq，
        读档时 `start_seq = snapshot.seq` 直接衔接 `events.seq > start_seq`。
        """
        ...

    async def latest_snapshot(self, branch_id: str, before_tick: int) -> SnapshotData | None:
        """获取 before_tick 之前（含）的最新快照。"""
        ...


# ---------------------------------------------------------------------------
# SQLAlchemy 实现
# ---------------------------------------------------------------------------


class SqlEventStore:
    """基于 SQLAlchemy 2.0 async + aiosqlite 的 EventStore 实现。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """
        Args:
            session_factory: async session 工厂（async_sessionmaker）。
        """
        self._session_factory = session_factory

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """暴露 session 工厂（M2-D2：NpcStore 批量物化需只读查询）。"""
        return self._session_factory

    async def append(
        self,
        branch_id: str,
        events: list[dict],
        entropy_rows: list[dict] | None = None,
        projection: ProjectionFn | None = None,
    ) -> None:
        """分配分支内 seq，批量写入 events 表。

        entropy_rows（codex 必须项 #2 预留）：与事件同事务原子写入 entropy_log。
        当前内核把熵材料存于 event payload（entropy_inject 事件自带 material），
        故通常传 None；保留该参数以支持后续「显式熵日志表」的原子落库。

        D04 记账项：entropy 行可通过 ``event_index`` 关联到 events 列表下标，
        本方法分配 seq 后把对应 ``event_seq`` 回填（同一事务）。

        projection（M2-D2）：可选投影回调，在**同一事务内**、events/entropy 落库后
        被调用（收到 session 与 event_index→seq 映射），用于把 M2 事件投影到
        派生表（NPC_LOD_CHANGE→npc_profiles.lod、MATTER_*→matter_state）。
        回调改动随本次 commit 原子提交；抛异常则整批回滚（无半写）。
        """
        if not events and not entropy_rows:
            return

        async with self._session_factory() as session:
            # 获取当前最大 seq
            result = await session.execute(
                select(func.coalesce(func.max(Event.seq), 0)).where(Event.branch_id == branch_id)
            )
            max_seq: int = result.scalar() or 0

            # event_index → 分配到的 seq（供 entropy 行回填 event_seq）
            seq_by_index: dict[int, int] = {}
            for i, event in enumerate(events):
                assigned_seq = max_seq + i + 1
                seq_by_index[i] = assigned_seq
                ev = Event(
                    branch_id=branch_id,
                    seq=assigned_seq,
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

            # 熵日志行：与事件同事务提交（原子性），event_seq 回填（D04）
            for row in entropy_rows or []:
                idx = row.get("event_index")
                backfilled = seq_by_index.get(idx) if idx is not None else row.get("event_seq")
                session.add(
                    EntropyLog(
                        branch_id=branch_id,
                        stream=row["stream"],
                        reason=row.get("reason", ""),
                        tick=row["tick"],
                        value=row["value"],
                        event_seq=backfilled,
                    )
                )

            # M2-D2：派生表投影（NPC_LOD_CHANGE→npc_profiles.lod、
            # MATTER_*→matter_state）在**同一事务内**完成，随本次 commit 原子提交。
            if projection is not None:
                await projection(session, seq_by_index)

            await session.commit()

    async def read_range(self, branch_id: str, frm: int, to: int) -> list[dict]:
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

    async def write_snapshot(self, branch_id: str, tick: int, event_seq: int, blob: bytes) -> None:
        """写入快照。seq = event_seq（快照点事件流最大 seq），与 events.seq 语义对齐。

        codex 必须项 #3：读档伪代码 `start_seq = snapshot.seq` 衔接
        `events.seq > start_seq`；若用表内自增会错位。
        """
        compressed = gzip.compress(blob, compresslevel=6)

        async with self._session_factory() as session:
            snap = Snapshot(
                branch_id=branch_id,
                seq=event_seq,
                tick=tick,
                snapshot_data=compressed,
                is_cold=False,
                schema_version=SNAPSHOT_SCHEMA_VERSION,
            )
            session.add(snap)
            await session.commit()

    async def latest_snapshot(self, branch_id: str, before_tick: int) -> SnapshotData | None:
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
                schema_version=snap.schema_version,
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
