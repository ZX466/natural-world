"""NPC runtime 数据访问层 — NpcStore（M2-D2，m2-npc-cognition §1.2/§1.3/§4.1）。

数据域职责（opencode）：把 M2 runtime 需要的三类持久化动作收在一处，runtime 本体
（`sim/npc/runtime.py`，架构域 M2-A2）只调本模块，不直接碰 SQL：

1. **50 NPC 批量物化（L0→L1）**：`materialize()` 一次 SELECT 取 50 行 `npc_profiles`
   → frozen `NpcProfileData` 字典（model.py 的内存态）；避免逐 NPC 查询。
2. **tick 批次 flush**：`flush_tick()` 把本 tick 事件批次落 `events`/`entropy_log`，
   并在**同一事务内**投影 M2 事件（`NPC_LOD_CHANGE`→`npc_profiles.lod`、
   `MATTER_*`→`matter_state`）——C4 唯一写路径，事件驱动不直改列（§1.2）。
3. **降格记忆压缩写回调用点**：`writeback_downgrade_memory()` 在 L2→L1 降格时把
   LLM 结论经 `MemoryWritePipeline.write(source="reason")` 压缩写回记忆
   （§1.2 关键缝：降格不丢人格 / 断线恢复）；不在本模块做叙事压缩（上游产物）。

投影与事件写入同事务：`SqlEventStore.append(..., projection=...)` 的投影回调在
commit 前于同一 session 执行，回调抛异常则整批回滚（无半写）。

依赖表：npc_profiles / npc_health / matter_state（0004）、events / entropy_log（0001/0002）。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sim.core.events import EventKind, WorldEvent
from sim.core.flush import flush_rows
from sim.core.persistence.models import MatterState, NpcHealth, NpcProfile
from sim.core.persistence.store import SqlEventStore
from sim.llm.memory_scan import (
    MemoryWritePipeline,
    WriteResult,
)
from sim.npc.contract import HiddenState
from sim.npc.hidden import HiddenAttribute, HiddenProfile
from sim.npc.model import NpcProfileData, needs_from_json
from sim.world.matter import MatterLedger, MatterSnapshot

#: LOD↔运行时物化范围（m2-npc-cognition §1.2）：L0=统计/1=效用/2=LLM。
LOD_STATISTICAL = 0
LOD_UTILITY = 1
LOD_LLM = 2


#: 扩展投影回调（runtime 追加；同事务执行，签名见 flush_tick）。
ProjectionLike = Callable[[AsyncSession, dict[int, int], Sequence[WorldEvent]], Awaitable[None]]


class NpcStoreError(RuntimeError):
    """数据访问层非法调用（对象不存在/投影缺键等）。"""


# ---------------------------------------------------------------------------
# 1. 批量物化（L0→L1）
# ---------------------------------------------------------------------------


def _row_to_profile_data(row: NpcProfile) -> NpcProfileData:
    """npc_profiles ORM 行 → frozen NpcProfileData（model.py）。

    OCEAN 五维 / PAD 三维按 §13 列序聚合为元组；needs JSON 走 needs_from_json
    做边界校验（非法 JSON → NeedsError，属数据损坏，向上抛）。
    """
    return NpcProfileData(
        npc_id=row.id,
        name=row.name,
        species=row.species,
        occupation=row.occupation,
        ocean=(
            float(row.ocean_openness),
            float(row.ocean_conscientiousness),
            float(row.ocean_extraversion),
            float(row.ocean_agreeableness),
            float(row.ocean_neuroticism),
        ),
        pad=(row.pad_pleasure, row.pad_arousal, row.pad_dominance),
        needs=needs_from_json(row.needs),
        skills=_skills_from_json(row.skills),
        lod=row.lod,
    )


def _skills_from_json(raw: str) -> dict[str, int]:
    """skills JSON 文本 → {技能: 等级}。空/非法按空表（技能非关键路径，宽容）。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): int(v) for k, v in data.items()}


def _load_str_list(raw: str | None) -> list[str]:
    """JSON 文本 → list[str]（descriptors/trigger_conditions）。非法按空表。"""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


class NpcStore:
    """NPC runtime 数据访问层（async SQLAlchemy，复用事件库 session_factory）。"""

    def __init__(
        self,
        event_store: SqlEventStore,
        *,
        branch_id: str = "main",
        memory_pipeline: MemoryWritePipeline | None = None,
    ) -> None:
        self._events = event_store
        self._branch_id = branch_id
        self._memory_pipeline = memory_pipeline or MemoryWritePipeline()

    @property
    def branch_id(self) -> str:
        return self._branch_id

    async def materialize(self, npc_ids: Sequence[str] | None = None) -> dict[str, NpcProfileData]:
        """批量物化 NPC（L0→L1）：一次 SELECT → {npc_id: NpcProfileData}。

        npc_ids 为 None 时物化本分支全部（MVP=50）；显式给 id 时只取命中行
        （未知 id 不在结果中，由调用方按需处理）。禁止逐 NPC 查询（§1.3）。
        """
        stmt = select(NpcProfile).where(NpcProfile.branch_id == self._branch_id)
        if npc_ids is not None:
            ids = list(npc_ids)
            if not ids:
                return {}
            stmt = stmt.where(NpcProfile.id.in_(ids))
        async with self._events.session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return {row.id: _row_to_profile_data(row) for row in rows}

    async def materialize_hidden(
        self, npc_ids: Sequence[str] | None = None
    ) -> dict[str, HiddenState]:
        """批量装配隐藏属性状态（M2-D3，codex MEDIUM ②；升格缺半边的补齐）。

        `materialize()` 只取 `npc_profiles`，不含 `npc_health` 的隐藏行 →
        升格时 HiddenState 装配缺半边。本方法一次性取全部相关 `npc_health` 行
        （hidden=True 且 active=True = 自我未知属性），按 npc_id 聚合为
        `{npc_id: HiddenState}`（codex `sim/npc/contract.py`）。

        - attributes 的 `id` = ``f"{npc_id}.health_{row.id}"``（DB 主键派生，
          稳定且不撞车；不直接暴露 label 作 id）；
        - `descriptors` ← 行 descriptors JSON（直陈词面，供泄漏扫描）；
        - `triggers` ← 行 trigger_conditions JSON（情境触发关键词）；
        - triggered 从空集起（升格后按 tick 用 `HiddenState.evaluate` 重估）；
        - 无隐藏行的 NPC 不出现在结果中（调用方用 `HiddenState.empty()` 兜底）。
        """
        stmt = (
            select(NpcHealth)
            .where(NpcHealth.branch_id == self._branch_id)
            .where(NpcHealth.hidden.is_(True))
            .where(NpcHealth.active.is_(True))
        )
        if npc_ids is not None:
            ids = list(npc_ids)
            if not ids:
                return {}
            stmt = stmt.where(NpcHealth.npc_id.in_(ids))
        async with self._events.session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()

        grouped: dict[str, list[HiddenAttribute]] = {}
        for row in rows:
            attr = HiddenAttribute(
                id=f"{row.npc_id}.health_{row.id}",
                category=row.category,  # type: ignore[arg-type]  # DB 值受 D1 约束
                label=row.label,
                descriptors=tuple(_load_str_list(row.descriptors)),
                triggers=tuple(_load_str_list(row.trigger_conditions)),
            )
            grouped.setdefault(row.npc_id, []).append(attr)

        return {
            npc_id: HiddenState(
                profile=HiddenProfile(npc_id=npc_id, attributes=tuple(attrs)),
                triggered=frozenset(),
            )
            for npc_id, attrs in grouped.items()
        }

    async def materialize_matter(self, matter_ids: Sequence[str] | None = None) -> MatterLedger:
        """批量物化物质账本（M3-C1，§19 快照路径契约照抄）。

        从 ``matter_state``（事件流的持久化投影，§17 方案 A 起列保真）**一次 SELECT**
        重建内存 ``MatterLedger``，对镜 ``materialize``；禁止逐对象查询（§1.3 纪律）。

        - ``matter_ids=None`` → 本分支全部（``WHERE branch_id=?``）；显式给 id →
          ``IN (...)``，**未知 id 不在结果中**（调用方兜底，同 ``materialize``）。
        - 列 → 字段映射（§19.2）：``subject_id``→``matter_id``、``integrity``/``decay_rate``/
          ``is_rubble`` 直通；其余列（``subject_kind/material/quality/load_bearing/
          supported_by``）不映射（``MatterSnapshot`` 无此概念，归 M4/M5）。
        - **纯读**：不触发写路径、不投影、不 flush（C4 唯一写路径不变）。
        - **注册≠落库**：仅回「已投影对象」；未产事件的注册对象不在 ``matter_state``。
        - 零 schema 改动、零迁移（纯读 + 已有列）。
        """
        stmt = select(MatterState).where(MatterState.branch_id == self._branch_id)
        if matter_ids is not None:
            ids = list(matter_ids)
            if not ids:
                return MatterLedger()
            stmt = stmt.where(MatterState.subject_id.in_(ids))
        async with self._events.session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()

        # 逐位列直通（§19.2）：库内 integrity 已 clip、decay_rate 非负（_project_matter
        # 保证），故直接构造 MatterSnapshot 与「register+mark_rubble」逐位等价。
        # 与**重放路径**共用 `MatterLedger.from_snapshots` 构造点（§19.3 逐位相等判据）。
        return MatterLedger.from_snapshots(
            MatterSnapshot(
                matter_id=row.subject_id,
                integrity=row.integrity,
                decay_rate=row.decay_rate,
                is_rubble=row.is_rubble,
            )
            for row in rows
        )

    async def materialize_matter_replay(
        self, matter_ids: Sequence[str] | None = None
    ) -> MatterLedger:
        """物质账本**重放路径**（M3-C2，§19.3）：从事件流重放 ``matter.*`` 重建。

        与**快照路径** ``materialize_matter`` **同产物、不同机制**（§19.3）：

        - 快照路径：直接 SELECT ``matter_state``（当前值，O(n)）；
        - 重放路径：读 ``events`` 表内 ``matter.*`` 事件（按 seq 升序）→ 逐事件
          **复用同一折叠规则**（``fold_matter_snapshot``，与 ``_project_matter``
          同源）→ UPSERT 内存账本。

        冷启动（无封存快照）时即「从空账本 + 全部事件」重放；若调用方持有快照点
        的账本（M3 世界循环封存），可先 ``from_snapshots(基线)`` 再喂后续事件——
        本方法当前实现「全量重放」形态（快照封存接线后扩展为「快照 + seq 之后」）。

        - ``matter_ids`` 过滤同 ``materialize_matter``（未知 id 不在结果）：
          仅当**最后一次折叠仍存在**的 id 才在结果中；未产事件的对象不在。
        - **纯读**：只读 ``events``、不落库、不投影。
        - 一致性判据：两入口产出**逐位相等**（§19.3；见 C2 校验测试）。
        """
        raw = await self._events.read_range(self._branch_id, 0, 2**62 - 1)

        # 按 seq 升序折叠所有 matter.* 事件（read_range 已升序；显式排序防御）。
        states: dict[str, MatterSnapshot] = {}
        for ev in sorted(raw, key=lambda e: int(e.get("seq", 0))):
            kind = str(ev.get("event_type", ""))
            if not kind.startswith("matter."):
                continue
            payload = ev.get("payload") or {}
            matter_id = str(payload.get("matter_id", ""))
            if not matter_id:
                raise NpcStoreError(f"MATTER_* payload 缺 matter_id: {payload!r}")
            states[matter_id] = fold_matter_snapshot(
                states.get(matter_id),
                matter_id=matter_id,
                durability=float(payload.get("durability", -1.0)),
                decay_rate=float(payload.get("decay_rate", -1.0)),
                is_collapse=kind == EventKind.MATTER_COLLAPSE.value,
            )

        if matter_ids is not None:
            wanted = set(matter_ids)
            states = {k: v for k, v in states.items() if k in wanted}
        return MatterLedger.from_snapshots(states.values())

    # -----------------------------------------------------------------------
    # 2. tick 批次 flush（事件 + 投影，同事务）
    # -----------------------------------------------------------------------

    async def flush_tick(
        self,
        events: Sequence[WorldEvent],
        *,
        extra_projection: ProjectionLike | None = None,
    ) -> None:
        """本 tick 事件批次落库 + M2 事件投影（同一事务；无则 no-op）。

        - events 经 `flush_rows` 得 store 行与 entropy 行（entropy_inject 派生）；
        - 投影：NPC_LOD_CHANGE → UPDATE npc_profiles.lod；
                MATTER_* → UPSERT matter_state；
        - extra_projection：给上层（M2-A2 runtime）追加投影的扩展缝，签名
          `async (session, seq_by_index, events) -> None`，同事务执行。
        """
        event_list = list(events)
        if not event_list and extra_projection is None:
            return
        rows, entropy_rows = flush_rows(event_list)

        async def _project(session: AsyncSession, seq_by_index: dict[int, int]) -> None:
            await _project_m2_events(session, self._branch_id, event_list)
            if extra_projection is not None:
                await extra_projection(session, seq_by_index, event_list)

        await self._events.append(
            self._branch_id,
            rows,
            entropy_rows=entropy_rows or None,
            projection=_project,
        )

    # -----------------------------------------------------------------------
    # 3. 降格记忆压缩写回（L2→L1）
    # -----------------------------------------------------------------------

    def writeback_downgrade_memory(
        self,
        npc_id: str,
        compressed: str,
        *,
        event_seq: int | None = None,
        importance: float = 0.5,
        emotion_tag: str | None = None,
        hidden: HiddenProfile | None = None,
        triggered: frozenset[str] = frozenset(),
    ) -> WriteResult:
        """L2→L1 降格：LLM 结论压缩后经唯一写入入口落记忆（source=reason）。

        压缩/叙事化是上游（agent 域）产物，本层只负责调用唯一入口
        `MemoryWritePipeline.write()`（S1 守卫不变：拒写不落库）。
        event_seq 缺省 None=推理转述（非事件绑定），见 memory-scan.md §4。
        """
        return self._memory_pipeline.write(
            npc_id,
            compressed,
            source="reason",
            event_seq=event_seq,
            importance=importance,
            emotion_tag=emotion_tag,
            hidden=hidden,
            triggered=triggered,
        )


# ---------------------------------------------------------------------------
# 投影实现
# ---------------------------------------------------------------------------


async def _project_m2_events(
    session: AsyncSession, branch_id: str, events: Sequence[WorldEvent]
) -> None:
    """M2 事件 → 派生表投影（同一事务）。仅处理 LOD 与物质熵增两类。"""
    for event in events:
        if event.event_type is EventKind.NPC_LOD_CHANGE:
            await _project_lod_change(session, branch_id, event)
        elif event.event_type in _MATTER_KINDS:
            await _project_matter(session, branch_id, event)


async def _project_lod_change(session: AsyncSession, branch_id: str, event: WorldEvent) -> None:
    """NPC_LOD_CHANGE → npc_profiles.lod（C4：LOD 只走事件，不直改列）。"""
    payload = event.payload
    npc_id = str(payload.get("npc_id", ""))
    to_lod = int(payload.get("to_lod", -1))  # type: ignore[arg-type]
    if not npc_id or to_lod not in (LOD_STATISTICAL, LOD_UTILITY, LOD_LLM):
        raise NpcStoreError(f"NPC_LOD_CHANGE payload 非法: {payload!r}")
    row = await session.get(NpcProfile, npc_id)
    if row is None:
        raise NpcStoreError(f"NPC_LOD_CHANGE 指向未知 NPC: {npc_id}")
    row.lod = to_lod
    row.updated_at_tick = event.tick


_MATTER_KINDS = frozenset(
    {
        EventKind.MATTER_DECAY,
        EventKind.MATTER_DAMAGE,
        EventKind.MATTER_BUILD,
        EventKind.MATTER_COLLAPSE,
    }
)


def fold_matter_snapshot(
    state: MatterSnapshot | None,
    *,
    matter_id: str,
    durability: float,
    decay_rate: float,
    is_collapse: bool,
) -> MatterSnapshot:
    """**单一折叠规则**：MATTER_* payload → 新 ``MatterSnapshot``（§19.3 防分叉）。

    投影路径（``_project_matter``，落 ``matter_state``）与重放路径
    （``materialize_matter_replay``，建内存账本）**共用本函数**——两入口逐位相等
    的前提（无第二套语义）。

    - ``durability < 0``：本次事件不携带耐久（如纯衰减携带账本率的 BUY 类），
      新态沿用旧 integrity；新对象无旧值 → 取 1.0（§17.2：新建硬编码满耐久）；
    - ``durability >= 0``：结算后耐久（clamp 0..1）；
    - ``decay_rate >= 0``：携带账本静态率（§17.2 方案 A 写率）；``< 0`` = 不动
      （沿用旧率；新对象取 0.0）；
    - ``is_rubble``：终态不可逆（``COLLAPSE`` 或 integrity 归零即置位，只增不减）；
    - 新对象的 ``decay_rate<0`` 归一为 0.0（旧对象沿用），对齐 ``_project_matter`` 原行为。
    """
    if state is None:
        integrity = 1.0 if durability < 0.0 else max(0.0, min(1.0, durability))
        rate = max(0.0, decay_rate) if decay_rate >= 0.0 else 0.0
        return MatterSnapshot(
            matter_id=matter_id,
            integrity=integrity,
            decay_rate=rate,
            is_rubble=is_collapse or integrity <= 0.0,
        )

    base = state.integrity if durability < 0.0 else durability
    integrity = max(0.0, min(1.0, base))
    rate = decay_rate if decay_rate >= 0.0 else state.decay_rate
    return MatterSnapshot(
        matter_id=matter_id,
        integrity=integrity,
        decay_rate=rate,
        is_rubble=state.is_rubble or is_collapse or integrity <= 0.0,
    )


async def _project_matter(session: AsyncSession, branch_id: str, event: WorldEvent) -> None:
    """MATTER_* → matter_state UPSERT（matter_state = 事件流的持久化投影）。

    payload（MatterPayload）：matter_id/amount/durability/decay_rate/note。
    amount<0 为损耗，durability>=0 为结算后耐久（折算 integrity）；COLLAPSE 置
    is_rubble；decay_rate>=0 携带账本静态率写列（§17.2 方案 A，重放保真），-1=不动。
    折叠规则见 ``fold_matter_snapshot``（与重放路径同源）。
    """
    payload = event.payload
    matter_id = str(payload.get("matter_id", ""))
    if not matter_id:
        raise NpcStoreError(f"MATTER_* payload 缺 matter_id: {payload!r}")
    amount = float(payload.get("amount", 0.0))  # type: ignore[arg-type]
    durability = float(payload.get("durability", -1.0))  # type: ignore[arg-type]
    decay_rate = float(payload.get("decay_rate", -1.0))  # type: ignore[arg-type]
    is_collapse = event.event_type is EventKind.MATTER_COLLAPSE

    existing = await session.get(MatterState, (branch_id, matter_id))
    if existing is None:
        folded = fold_matter_snapshot(
            None,
            matter_id=matter_id,
            durability=durability,
            decay_rate=decay_rate,
            is_collapse=is_collapse,
        )
        session.add(
            MatterState(
                subject_id=matter_id,
                branch_id=branch_id,
                subject_kind="structure",
                material="",  # MatterPayload 暂无 material 字段（材料归 M4 结构域）
                integrity=folded.integrity,
                quality=0.5,
                decay_rate=folded.decay_rate,
                load_bearing=False,
                supported_by="[]",
                is_rubble=folded.is_rubble,
                last_decay_tick=event.tick,
                updated_at_tick=event.tick,
            )
        )
        return

    prior = MatterSnapshot(
        matter_id=matter_id,
        integrity=existing.integrity,
        decay_rate=existing.decay_rate,
        is_rubble=existing.is_rubble,
    )
    folded = fold_matter_snapshot(
        prior,
        matter_id=matter_id,
        durability=durability,
        decay_rate=decay_rate,
        is_collapse=is_collapse,
    )
    existing.integrity = folded.integrity
    existing.decay_rate = folded.decay_rate
    existing.is_rubble = folded.is_rubble
    existing.last_decay_tick = event.tick
    _ = amount  # amount 已折算进 durability/integrity；保留字段供审计
