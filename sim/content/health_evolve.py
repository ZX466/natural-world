"""每日健康内容演进；同步适配器只消费快照并沿既有事件写路径入队。

下表是纯游戏平衡值，单位为严重度/游戏日，不是医学判断或建议：

=================  ==========  =========================================
category           每日变化    游戏内容取舍
=================  ==========  =========================================
old_injury         -0.05       普通旧伤缓慢愈合；归零后 inactive
disease            +0.10       未处理的疾病逐日恶化；到 1 后保持 active
addiction          +0.02       持续的习惯小幅加重；到 1 后保持 active
disability          0.00       稳定残疾不随日历自行改变
trauma             -0.02       创伤缓慢缓解；归零后 inactive
=================  ==========  =========================================

先 round 到 12 位小数，再裁到 [0, 1]；只为 severity/active 的实际变更产事件。
inactive 行不自动复发；恶化饱和也不重复产事件。1 表示持续重症，本适配器只产
NPC_HEALTH_CHANGED，不产 AGENT_INCAPACITATED：普通 NPC 没有生产恢复入口，
不能借此引入永久失能。健康变更保持 category/code/hidden/notes，不改 LOD、不调模型。

day 是 calendar 的 1-based 游戏天号。日界 tick 为
``(day - 1) * TICKS_PER_GAME_DAY``，只演进在该日界已经存在的健康行：
``created_at_tick <= 日界 tick``。一帧跨多日时不能把帧末新伤倒推到更早的日界；
既有 code 当帧被更新则按快照里的最新已提交值演进，创建时刻仍沿用原行。

load_health_snapshot 在钩子外异步批读；__call__ 是无数据库/网络 IO 的同步回调。
回调内每次成功 enqueue 后更新缓存，多日未落库时仍能顺序推演；重复/过去 day
无操作。事件 tick 恒取当前 loop.state.tick，payload 仅七个既有健康键。生产日切
在本帧 flush 之后，因此这些事件由下一帧 drain+flush 落库，正常存在一帧延迟。
refresh 只能在成功投影后换快照，不消费日号；读档用 reset 重建分支和基线。

离线选 (b)：advance_offline 不演进健康。生产组合层应在启动补跑结束后初始化
当前日基线，并在成功读档时重设；不会在首次在线回调追补已经跳过的离线日。
规则不采样墙钟或 RNG；同一初值与调用序列产生逐字段一致的事件。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sim.core.calendar import TICKS_PER_GAME_DAY, game_time
from sim.core.events import NpcHealthChangedPayload, WorldEvent, npc_health_changed_event
from sim.core.persistence.models import NpcHealth, NpcProfile
from sim.core.tick import TickLoop
from sim.npc.hidden import HiddenCategory

logger = structlog.get_logger(__name__)

_DELTA_PER_DAY = MappingProxyType[HiddenCategory, float](
    {
        "old_injury": -0.05,
        "disease": 0.10,
        "addiction": 0.02,
        "disability": 0.0,
        "trauma": -0.02,
    }
)


@dataclass(frozen=True)
class HealthRow:
    npc_id: str
    category: HiddenCategory
    code: str
    severity: float
    active: bool
    hidden: bool
    notes: str | None = None
    created_at_tick: int = 0


@dataclass(frozen=True)
class HealthSnapshot:
    branch_id: str
    rows: tuple[HealthRow, ...]
    profile_ids: frozenset[str]


async def load_health_snapshot(
    session_factory: async_sessionmaker[AsyncSession], *, branch_id: str
) -> HealthSnapshot:
    """两次批读本分支档案与全部健康行；不保留 ORM 对象或活动 session。"""
    async with session_factory() as session:
        profile_ids = frozenset(
            await session.scalars(select(NpcProfile.id).where(NpcProfile.branch_id == branch_id))
        )
        result = await session.execute(
            select(
                NpcHealth.npc_id,
                NpcHealth.category,
                NpcHealth.code,
                NpcHealth.severity,
                NpcHealth.active,
                NpcHealth.hidden,
                NpcHealth.notes,
                NpcHealth.created_at_tick,
            )
            .join(
                NpcProfile,
                and_(
                    NpcProfile.branch_id == NpcHealth.branch_id,
                    NpcProfile.id == NpcHealth.npc_id,
                ),
            )
            .where(NpcHealth.branch_id == branch_id)
            .order_by(NpcHealth.npc_id, NpcHealth.code)
        )
        rows = tuple(
            HealthRow(
                npc_id=row.npc_id,
                category=cast(HiddenCategory, row.category),
                code=row.code,
                severity=row.severity,
                active=row.active,
                hidden=row.hidden,
                notes=row.notes,
                created_at_tick=row.created_at_tick,
            )
            for row in result
        )
    return HealthSnapshot(branch_id, rows, profile_ids)


class DailyHealthEvolution:
    """保存当前有效快照；每 NPC 计算隔离，入队故障仍向世界驱动抛出。"""

    def __init__(
        self, loop: TickLoop, snapshot: HealthSnapshot, *, baseline_day: int | None = None
    ) -> None:
        self._loop = loop
        self.reset(
            snapshot,
            baseline_day=game_time(loop.state.tick).day if baseline_day is None else baseline_day,
        )

    @property
    def branch_id(self) -> str:
        return self._branch_id

    @property
    def last_day(self) -> int:
        return self._last_day

    def refresh(self, snapshot: HealthSnapshot) -> None:
        """同分支成功投影后替换快照；未处理的新日仍须留给同步钩子。"""
        if snapshot.branch_id != self._branch_id:
            raise ValueError("health snapshot belongs to another branch; use reset")
        self._replace_snapshot(snapshot)

    def reset(self, snapshot: HealthSnapshot, *, baseline_day: int) -> None:
        """启动/读档重建快照与基线，允许切换分支或向过去重设。"""
        self._validate_day(baseline_day)
        self._replace_snapshot(snapshot)
        self._last_day = baseline_day

    def _replace_snapshot(self, snapshot: HealthSnapshot) -> None:
        self._branch_id = snapshot.branch_id
        self._profile_ids = snapshot.profile_ids
        self._rows = {(row.npc_id, row.code): row for row in snapshot.rows}

    @staticmethod
    def _validate_day(day: int) -> None:
        if type(day) is not int or day < 1:
            raise ValueError("health day must be a positive integer")

    def __call__(self, day: int) -> None:
        self._validate_day(day)
        if day <= self._last_day:
            return
        if day > game_time(self._loop.state.tick).day:
            raise ValueError("health day is ahead of the current game day")
        for current_day in range(self._last_day + 1, day + 1):
            self._evolve_day(current_day)
            self._last_day = current_day

    def _evolve_day(self, day: int) -> None:
        by_npc: dict[str, list[HealthRow]] = {}
        for row in self._rows.values():
            # profile 抵挡孤儿旧行；实体检查抵挡尚未投影的 NPC_DEATH。
            if row.npc_id not in self._profile_ids or row.npc_id not in self._loop.state.entities:
                continue
            by_npc.setdefault(row.npc_id, []).append(row)
        for npc_id in sorted(by_npc):
            try:
                rows = sorted(by_npc[npc_id], key=lambda row: row.code)
                changes = self._changes_for_npc(rows, day)
            except (ValueError, TypeError) as exc:
                # 不输出健康内容或异常消息；单个坏 NPC 不阻断其余 NPC。
                logger.warning(
                    "health.evolution_invalid_npc", npc_id=npc_id, reason=type(exc).__name__
                )
                continue
            for row, event in changes:
                # 基础设施/入队异常不属于坏 NPC，必须在隔离块外抛出。
                self._loop.enqueue(event)
                self._rows[(row.npc_id, row.code)] = row

    def _changes_for_npc(
        self, rows: list[HealthRow], day: int
    ) -> list[tuple[HealthRow, WorldEvent]]:
        changes: list[tuple[HealthRow, WorldEvent]] = []
        boundary_tick = (day - 1) * TICKS_PER_GAME_DAY
        for row in rows:
            if type(row.created_at_tick) is not int or row.created_at_tick < 0:
                raise ValueError("health creation tick must be a nonnegative integer")
            if isinstance(row.severity, bool) or not isinstance(row.severity, (int, float)):
                raise TypeError("health severity must be numeric")
            value = NpcHealthChangedPayload(
                npc_id=row.npc_id,
                category=row.category,
                code=row.code,
                severity=row.severity,
                active=row.active,
                hidden=row.hidden,
                notes=row.notes,
            )
            if not value.active or row.created_at_tick > boundary_tick:
                continue
            delta = _DELTA_PER_DAY[value.category]
            if delta == 0:
                continue
            severity = min(1.0, max(0.0, round(value.severity + delta, 12)))
            active = severity > 0 if delta < 0 else True
            if (severity, active) == (value.severity, value.active):
                continue
            changed = replace(row, severity=severity, active=active)
            event = npc_health_changed_event(
                self._loop.state.tick,
                npc_id=value.npc_id,
                category=value.category,
                code=value.code,
                severity=severity,
                active=active,
                hidden=value.hidden,
                notes=value.notes,
                branch_id=self._branch_id,
            )
            changes.append((changed, event))
        return changes
