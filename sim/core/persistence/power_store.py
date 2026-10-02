"""权力状态数据访问层 — `PowerStore`（批次 C 数据面，M5-A7 / 0013）

设计稿：`docs/data/m5-power-data-preplan.md`；判据：`docs/security/m5-authority-criteria-preplan.md`
（D-10 权力不可见、红线 A 不新增事件 kind、红线 B 禁键集）。

**为什么不是事件投影**（与 `npc_store.py` 的 M2/M3/M4 投影相反）：codex 已用
`test_event_kinds_closed` 把事件 kind 集合钉死，而既有 payload 是闭合集
（``extra="forbid"``）⇒ 权力的增量**无处可挂**。故本表走**显式增量写**：

- ``materialize(npc_ids=None)``：**一次 SELECT** 物化本分支（或给定 id 集合）→
  ``{npc_id: PowerState}``；**纯读**（不写、不衰减、不投影）；未知 id 不在结果
  （调用方兜底，同 ``NpcStore.materialize``）。禁止逐 NPC 查询。
- ``apply_batch(deltas, *, tick)``：一个 tick 的批量增量 = **一次事务**（分支闸门校验
  一次 + N 行读改写）。**非幂等**（增量语义）——机制若需幂等必须自带去重。
- ``apply(npc_id, delta, *, tick)``：单行薄封装。

**fail-closed 四条**（非法输入一律抛 :class:`PowerWriteError`，**零写**）：

1. ``delta`` 为 NaN/Inf（``float('nan')`` 能通过 ``>``/``<=`` 比较，**必须显式查**）；
2. ``tick`` 非 int / 负数 / **早于该行已有 ``updated_at_tick``**（时间倒流 = 调用方 bug，
   静默接受会让衰减算错且不可复现）；
3. ``npc_id`` 为空串或非 str；
4. 目标分支不是 ``active``（复用 :class:`~sim.core.persistence.store.InactiveBranchError`
   ——分叉后父分支封存，往被弃时间线追加权力同样是污染，C6）。

**越界夹取如实上报**：累加结果超出 ``[POWER_MIN, POWER_MAX]`` 时**夹取**（不抛，避免
一次数值溢出打断整个 tick），并在返回的 :class:`PowerState` 里把 ``clamped=True`` 如实
带回——调用方**必须**检查该事实，别当无事发生（DB CHECK 是第二道防线，直接 ORM 写也会被拒）。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select

from sim.core.persistence.models import POWER_MAX, POWER_MIN, Branch, NpcPower
from sim.core.persistence.store import InactiveBranchError, SqlEventStore


class PowerWriteError(RuntimeError):
    """权力写面非法调用（NaN/Inf、tick 倒流、非法 id）——一律 fail-closed、零写。"""


@dataclass(frozen=True)
class PowerState:
    """一个 NPC 在本分支的权力态（frozen：读面产物不可被就地改写）。

    ``clamped``：**本次写入**是否发生了越界夹取。``materialize`` 读回的既有行恒为
    ``False``（库里不可能有越界值——DB CHECK 挡着），故该事实只对写面有意义。
    """

    npc_id: str
    power_level: float
    updated_at_tick: int
    clamped: bool = False


def _check_delta(delta: object) -> float:
    """NaN/Inf 显式拒（**不可**用比较判：NaN 与任何值比较都返回 False）。"""
    if isinstance(delta, bool) or not isinstance(delta, int | float):
        raise PowerWriteError(f"delta 必须是数值: {delta!r}")
    value = float(delta)
    if math.isnan(value) or math.isinf(value):
        raise PowerWriteError(f"delta 不得为 NaN/Inf: {delta!r}")
    return value


def _check_tick(tick: object) -> int:
    if isinstance(tick, bool) or not isinstance(tick, int):
        raise PowerWriteError(f"tick 必须是 int: {tick!r}")
    if tick < 0:
        raise PowerWriteError(f"tick 不得为负: {tick!r}")
    return tick


def _check_npc_id(npc_id: object) -> str:
    if not isinstance(npc_id, str) or not npc_id:
        raise PowerWriteError(f"npc_id 必须是非空 str: {npc_id!r}")
    return npc_id


def _clamp(value: float) -> tuple[float, bool]:
    """夹取到量纲内，返回 `(值, 是否发生夹取)`。"""
    if value < POWER_MIN:
        return POWER_MIN, True
    if value > POWER_MAX:
        return POWER_MAX, True
    return value, False


class PowerStore:
    """权力状态数据访问层（async SQLAlchemy，复用事件库 session_factory）。

    与 :class:`~sim.core.persistence.npc_store.NpcStore` 同款构造：拿事件库 + 分支 id，
    分支 id 落在实例上（**每实例只服务一条世界线**，不跨分支读写）。
    """

    def __init__(self, event_store: SqlEventStore, *, branch_id: str = "main") -> None:
        self._events = event_store
        self._branch_id = branch_id

    @property
    def branch_id(self) -> str:
        return self._branch_id

    # ------------------------------------------------------------------
    # 读面（纯读）
    # ------------------------------------------------------------------

    async def materialize(self, npc_ids: Sequence[str] | None = None) -> dict[str, PowerState]:
        """一次 SELECT 物化权力态 → ``{npc_id: PowerState}``（无行 = 未表态，调用方兜底 0）。

        - ``npc_ids=None`` → 本分支全部；显式给 id → ``IN (...)``，**未知 id 不在结果中**。
        - **纯读**：不写、不衰减（衰减是调用方按 ``tick - updated_at_tick`` 算完再 ``apply``，
          读面永不产生副作用）。
        """
        stmt = select(NpcPower).where(NpcPower.branch_id == self._branch_id)
        if npc_ids is not None:
            ids = list(npc_ids)
            if not ids:
                return {}
            stmt = stmt.where(NpcPower.npc_id.in_(ids))
        async with self._events.session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return {
            row.npc_id: PowerState(
                npc_id=row.npc_id,
                power_level=float(row.power_level),
                updated_at_tick=int(row.updated_at_tick),
            )
            for row in rows
        }

    # ------------------------------------------------------------------
    # 写面（显式增量；一次事务；fail-closed）
    # ------------------------------------------------------------------

    async def apply_batch(self, deltas: Mapping[str, float], *, tick: int) -> dict[str, PowerState]:
        """批量增量写（一个 tick 一次事务）→ ``{npc_id: PowerState}``。

        - 空 ``deltas`` → no-op（**不**开事务、**不**校验分支：没有写入就没有副作用）；
        - **全批原子**：批内任一条非法 ⇒ 整批抛 :class:`PowerWriteError`，**零写**；
        - 分支闸门只查**一次**（N 行读改写在同一事务里）。
        """
        if not deltas:
            return {}
        checked = {
            _check_npc_id(npc_id): (_check_delta(delta), tick) for npc_id, delta in deltas.items()
        }
        checked_tick = _check_tick(tick)

        results: dict[str, PowerState] = {}
        async with self._events.session_factory() as session:
            status = (
                await session.execute(select(Branch.status).where(Branch.id == self._branch_id))
            ).scalar_one_or_none()
            if status is None:
                raise InactiveBranchError(
                    f"分支 {self._branch_id!r} 不存在，不可写权力态（开线请走事件库闸门）"
                )
            if status != "active":
                raise InactiveBranchError(
                    f"分支 {self._branch_id!r} 状态为 {status!r}，不可写权力态"
                    "（分叉后父分支封存，往被弃时间线写 = 污染）"
                )
            for npc_id, (delta, _tick) in checked.items():
                row = await session.get(NpcPower, (self._branch_id, npc_id))
                prior = float(row.power_level) if row is not None else 0.0
                prior_tick = int(row.updated_at_tick) if row is not None else 0
                if checked_tick < prior_tick:
                    raise PowerWriteError(
                        f"tick 倒流: tick={checked_tick} < 该行已有 updated_at_tick="
                        f"{prior_tick}（npc_id={npc_id!r}）——静默接受会让衰减算错且不可复现"
                    )
                level, clamped = _clamp(prior + delta)
                if row is None:
                    session.add(
                        NpcPower(
                            branch_id=self._branch_id,
                            npc_id=npc_id,
                            power_level=level,
                            updated_at_tick=checked_tick,
                        )
                    )
                else:
                    row.power_level = level
                    row.updated_at_tick = checked_tick
                results[npc_id] = PowerState(
                    npc_id=npc_id,
                    power_level=level,
                    updated_at_tick=checked_tick,
                    clamped=clamped,
                )
            await session.commit()
        return results

    async def apply(self, npc_id: str, delta: float, *, tick: int) -> PowerState:
        """单行增量写（薄封装 :meth:`apply_batch`）→ 写入后的 :class:`PowerState`。

        行不存在 ⇒ 以 ``power_level=0`` 为基线建行（**未表态 ≡ 0** 与 ``materialize``
        的「无行 = 未表态，调用方兜底 0」同一口径，不存在「有行/无行」两套语义）。
        """
        results = await self.apply_batch({npc_id: delta}, tick=tick)
        return results[_check_npc_id(npc_id)]
