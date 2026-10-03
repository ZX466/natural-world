"""火场生命周期数据访问层 — `FireStore`（批次 D 数据面，M5-A9 / 0014）

设计稿 `docs/data/m5-fire-data-preplan.md`（A8）；接口约束 `docs/api/m5-fire-api-prestudy.md`
§4 **F1-F5**；安规钉 `docs/security/m5-fire-threatmodel.md` **D-1..D-7**。

**只存生命周期，不存火势中间态**（A8 §1.2 已裁，裁 33 沿用）：一行 = 一场火
（``fire_id`` 分支内唯一），字段只有坐标 + 起火 tick + 熄灭 tick + 物理终止态。
蔓延强度 / 燃料剩余 / 蔓延半径**不入库**——它们是**纯运行态**（每 tick 由混沌流现抽），
入库就得新建第 5 张不可重建表 + 扩物化包 + 扩克隆清单（四处成本换「读档后续烧」）。

**F1（签名）**：`upsert_fire` / `set_fire_end` / `active_fires` 三方法；返回的
:class:`FireRow` **禁含归因键**（无 actor/igniter/culprit/authority_*，K12 §3 + D-10）。

**F2（禁内存态火势 / 变更必产事件，W-D1）**：本模块**不提供**任何不经事件直接改
``fires`` 表的入口——两次写都经 :meth:`SqlEventStore.append` 产 ``fire.*`` 事件，投影
（:func:`project_fire`）在**同一事务内**落行。传播步进（蔓延/烧毁）由机制面另产既有族
事件（``matter.damage`` / ``matter.collapse`` / ``structure.collapsed`` /
``material.moved``），**本模块零涉及**——烧毁的材料去向必须带 ``to_ref``
（如 ``world:burned``）⇒ T1 材料守恒逐位相等（F4）。

**W-D3（事件预算）**：一个 tick 的蔓延事件 **≤1 条**（状态跃迁/按场聚合），传播步进零事件；
N 值由 pi 定标机定（advisory），本层只立口径「无状态变更零事件」。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sim.core.events import EventKind, FireEnd, fire_extinguished_event, fire_ignited_event
from sim.core.persistence.models import Fire
from sim.core.persistence.store import SqlEventStore

#: 坐标域（与 `events.py::_FIRE_COORD`、`MatterPayload` 同哨兵语义：-1 = 未定位）。
COORD_MIN, COORD_LIMIT = -1, 4096

#: 本层产出的 kind 集合（写面只许产这两个 ⇒ 「写火灾后 events 行集只增 fire 族」可钉）。
FIRE_KINDS: frozenset[EventKind] = frozenset({EventKind.FIRE_IGNITED, EventKind.FIRE_EXTINGUISHED})


class FireWriteError(RuntimeError):
    """火场写面非法调用（空 fire_id / 坐标越界 / tick 非法 / 重复熄灭）——fail-closed、零写。"""


@dataclass(frozen=True)
class FireRow:
    """一场火在某分支的当前态（frozen；**零归因键**，K12 §3）。

    ``ended_tick is None`` ⇔ 仍在燃烧（与库内 ``ck_fires_end_pair`` 同一条不变式）。
    """

    fire_id: str
    x: int
    y: int
    ignited_tick: int
    ended_tick: int | None = None
    end: FireEnd | Literal[""] = ""

    @property
    def active(self) -> bool:
        return self.ended_tick is None


# ---------------------------------------------------------------------------
# 校验（fail-closed；非法一律零写）
# ---------------------------------------------------------------------------


def _check_fire_id(fire_id: object) -> str:
    if not isinstance(fire_id, str) or not fire_id or len(fire_id) > 64:
        raise FireWriteError(f"fire_id 必须是 1..64 字符的非空 str: {fire_id!r}")
    return fire_id


def _check_coord(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FireWriteError(f"{name} 必须是 int（-1 = 未定位）: {value!r}")
    if not (COORD_MIN <= value < COORD_LIMIT):
        raise FireWriteError(f"{name} 越界 [{COORD_MIN}, {COORD_LIMIT}): {value!r}")
    return value


def _check_tick(tick: object) -> int:
    if isinstance(tick, bool) or not isinstance(tick, int):
        raise FireWriteError(f"tick 必须是 int: {tick!r}")
    if tick < 0:
        raise FireWriteError(f"tick 不得为负: {tick!r}")
    return tick


def _check_end(end: object) -> FireEnd:
    if end not in ("out", "fuel_out", "doused"):
        raise FireWriteError(f"end 必须是物理终止态（out/fuel_out/doused）: {end!r}")
    return cast(FireEnd, end)


def _cast_end(raw: str) -> FireEnd | Literal[""]:
    """库内 ``end`` 列 → frozen 行的类型（空串 = 活跃中；其余值由 CHECK 兜住域）。"""
    if raw == "":
        return ""
    return _check_end(raw)


# ---------------------------------------------------------------------------
# 折叠规则（投影与重放**同源**，schema §19.3 铁律：两路径不得各写一套）
# ---------------------------------------------------------------------------


def fold_fire(
    prev: FireRow | None,
    *,
    fire_id: str,
    x: int,
    y: int,
    tick: int,
    end: FireEnd | None,
) -> FireRow:
    """``fire.*`` 单折叠（投影与重放共用）。

    - ``fire.ignited``（``end is None``）：**重复起火 fail-closed**（同一 fire_id 二次点火
      是调用方 bug——静默覆盖会丢历史）。
    - ``fire.extinguished``：行不存在 ⇒ fail-closed（没起过火就灭 = 状态机不合法）；
      已熄灭 ⇒ fail-closed（重复熄灭）。
    """
    if end is None:
        if prev is not None:
            raise FireWriteError(f"fire_id={fire_id!r} 已存在，重复起火")
        return FireRow(fire_id=fire_id, x=x, y=y, ignited_tick=tick)
    if prev is None:
        raise FireWriteError(f"fire_id={fire_id!r} 未起火却收到熄灭事件")
    if prev.ended_tick is not None:
        raise FireWriteError(f"fire_id={fire_id!r} 已于 tick={prev.ended_tick} 熄灭，重复熄灭")
    if tick < prev.ignited_tick:
        raise FireWriteError(
            f"tick 倒流: 熄灭 tick={tick} < 起火 tick={prev.ignited_tick}（fire_id={fire_id!r}）"
        )
    return replace(prev, ended_tick=tick, end=end)


def _row_to_fire(row: Fire) -> FireRow:
    return FireRow(
        fire_id=row.fire_id,
        x=int(row.x),
        y=int(row.y),
        ignited_tick=int(row.ignited_tick),
        ended_tick=None if row.ended_tick is None else int(row.ended_tick),
        end=_cast_end(row.end),
    )


async def project_fire(session: AsyncSession, branch_id: str, event: object) -> None:
    """``fire.*`` → ``fires`` 行投影（**同一事务内**；事件流唯一写路径 W-D1 的落点）。

    与 :func:`fold_fire` 同源（不另写一套折叠逻辑，schema §19.3）。
    """
    kind = str(getattr(event, "event_type", ""))
    payload = getattr(event, "payload", None) or {}
    tick = int(getattr(event, "tick", 0))
    if kind not in {EventKind.FIRE_IGNITED.value, EventKind.FIRE_EXTINGUISHED.value}:
        return
    fire_id = str(payload.get("fire_id", ""))
    if not fire_id:
        raise FireWriteError(f"fire.* payload 缺 fire_id: {payload!r}")
    x = _check_coord(int(payload.get("x", -1)), "x")
    y = _check_coord(int(payload.get("y", -1)), "y")
    end = str(payload.get("end")) if kind == EventKind.FIRE_EXTINGUISHED.value else None

    existing = await session.get(Fire, (branch_id, fire_id))
    folded = fold_fire(
        None if existing is None else _row_to_fire(existing),
        fire_id=fire_id,
        x=x,
        y=y,
        tick=tick,
        end=None if end is None else _check_end(end),
    )
    if existing is None:
        session.add(
            Fire(
                branch_id=branch_id,
                fire_id=folded.fire_id,
                x=folded.x,
                y=folded.y,
                ignited_tick=folded.ignited_tick,
                ended_tick=folded.ended_tick,
                end=folded.end,
            )
        )
        return
    existing.x = folded.x
    existing.y = folded.y
    existing.ended_tick = folded.ended_tick
    existing.end = folded.end


class FireStore:
    """火场生命周期数据访问层（async SQLAlchemy，复用事件库 session_factory）。

    与 :class:`~sim.core.persistence.power_store.PowerStore` /
    :class:`~sim.core.persistence.npc_store.NpcStore` 同款构造：拿事件库 + 分支 id，
    分支 id 落在实例上（**每实例只服务一条世界线**）。
    """

    def __init__(self, event_store: SqlEventStore, *, branch_id: str = "main") -> None:
        self._events = event_store
        self._branch_id = branch_id

    @property
    def branch_id(self) -> str:
        return self._branch_id

    # ------------------------------------------------------------------
    # 写面（两次写都产事件；F2：零「不经 append 直改表」的入口）
    # ------------------------------------------------------------------

    async def upsert_fire(self, *, fire_id: str, x: int, y: int, tick: int) -> FireRow:
        """起火：产 ``fire.ignited`` 事件 → 同事务投影落行 → 返回落库后的行。

        - **产事件是义务**（F2/W-D1）：本方法没有「只落表」的旁路。
        - ``fire_id`` 已存在 ⇒ :class:`FireWriteError`（重复点火 = 调用方 bug）。
        - 事件预算（W-D3）：一次调用 = **一条**事件（无 per-tick 增量面）。
        """
        checked_id = _check_fire_id(fire_id)
        checked_x = _check_coord(x, "x")
        checked_y = _check_coord(y, "y")
        checked_tick = _check_tick(tick)
        event = fire_ignited_event(
            checked_tick, fire_id=checked_id, x=checked_x, y=checked_y, branch_id=self._branch_id
        )

        async def _project(session: AsyncSession, _seq_by_index: dict[int, int]) -> None:
            await project_fire(session, self._branch_id, event)

        await self._events.append(
            self._branch_id,
            [event.to_store_dict()],
            projection=_project,
        )
        async with self._events.session_factory() as session:
            row = await session.get(Fire, (self._branch_id, checked_id))
        if row is None:  # pragma: no cover - 投影必落行；防御性：宁可不返回半值
            raise FireWriteError(f"起火后未读到 fires 行（投影缺失）: {checked_id!r}")
        return _row_to_fire(row)

    async def set_fire_end(self, fire_id: str, *, end: FireEnd, tick: int) -> FireRow:
        """熄灭：产 ``fire.extinguished`` 事件 → 同事务更新行（``ended_tick`` + ``end``）。"""
        checked_id = _check_fire_id(fire_id)
        checked_end, checked_tick = _check_end(end), _check_tick(tick)
        async with self._events.session_factory() as session:
            current = await session.get(Fire, (self._branch_id, checked_id))
        if current is None:
            raise FireWriteError(f"fire_id={checked_id!r} 不存在，无从熄灭（状态机不合法）")
        row = _row_to_fire(current)
        event = fire_extinguished_event(
            checked_tick,
            fire_id=checked_id,
            end=checked_end,
            x=row.x,
            y=row.y,
            branch_id=self._branch_id,
        )

        async def _project(session: AsyncSession, _seq_by_index: dict[int, int]) -> None:
            await project_fire(session, self._branch_id, event)

        await self._events.append(
            self._branch_id,
            [event.to_store_dict()],
            projection=_project,
        )
        async with self._events.session_factory() as session:
            updated = await session.get(Fire, (self._branch_id, checked_id))
        if updated is None:  # pragma: no cover - 投影必在；防御性
            raise FireWriteError(f"熄灭后未读到 fires 行（投影缺失）: {checked_id!r}")
        return _row_to_fire(updated)

    # ------------------------------------------------------------------
    # 读面（纯读）
    # ------------------------------------------------------------------

    async def active_fires(self, fire_ids: Sequence[str] | None = None) -> list[FireRow]:
        """当前仍在燃烧的火场（一次 SELECT；**纯读**：不写、不推进、不衰减）。

        ``fire_ids`` 给定时只取命中行（未知 id 不在结果）。行按 ``fire_id`` 升序，
        结果确定可复现。
        """
        stmt = (
            select(Fire).where(Fire.branch_id == self._branch_id).where(Fire.ended_tick.is_(None))
        )
        if fire_ids is not None:
            ids = list(fire_ids)
            if not ids:
                return []
            stmt = stmt.where(Fire.fire_id.in_(ids))
        async with self._events.session_factory() as session:
            rows = (await session.execute(stmt.order_by(Fire.fire_id))).scalars().all()
        return [_row_to_fire(row) for row in rows]

    async def materialize_fires_replay(self, upto_seq: int | None = None) -> dict[str, FireRow]:
        """**重放路径**：折叠 ``fire.*`` 事件重建火场（与投影共用 :func:`fold_fire`）。

        - ``upto_seq`` 给定 ⇒ 只折叠 ``seq <= upto_seq`` 的事件（**读档窗口**语义：
          anchor 点之后的火灾事件对本结果**零影响**，A8 §4 照妖镜钉的判据）；
          ``None`` ⇒ 全量折叠（冷启动）。
        - **纯读**：只读 ``events``，不落库、不投影。
        - 一致性判据：与快照路径 ``active_fires`` / 读表在窗口内**逐位相等**。
        """
        limit = 2**62 - 1 if upto_seq is None else upto_seq
        raw = await self._events.read_range(self._branch_id, 0, limit)
        states: dict[str, FireRow] = {}
        for event in sorted(raw, key=lambda e: int(e.get("seq", 0))):
            kind = str(event.get("event_type", ""))
            if kind not in {k.value for k in FIRE_KINDS}:
                continue
            payload = event.get("payload") or {}
            fire_id = str(payload.get("fire_id", ""))
            if not fire_id:
                raise FireWriteError(f"fire.* payload 缺 fire_id: {payload!r}")
            end = str(payload.get("end")) if kind == EventKind.FIRE_EXTINGUISHED.value else None
            states[fire_id] = fold_fire(
                states.get(fire_id),
                fire_id=fire_id,
                x=int(payload.get("x", -1)),
                y=int(payload.get("y", -1)),
                tick=int(event.get("tick", 0)),
                end=None if end is None else _check_end(end),
            )
        return states
