"""承重依赖图与按帧摊还级联（M4-D2c；纯内存、零 SQL）。

- 图从当前分支 structures 投影一次物化；无环/同分支/承重资格在建图时拒绝；
- ``dependents`` 与级联队列均按 id 稳定排序，保证回放逐位确定；
- 级联游标按 ``event_budget`` 分帧推进，单帧不超全局事件预算；
- support_path 只记录**直接失去的支撑**，深链不复制 O(n²) 路径。
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from sim.core.events import StructureCollapseCause, WorldEvent, structure_collapsed_event
from sim.world.structure import StructurePhase, StructureSnapshot

SUPPORT_GRAPH_ACCEPTANCE_NODES: Final[int] = 10_000
CASCADE_EVENT_BUDGET_PER_FRAME: Final[int] = 100


class GraphError(ValueError):
    """承重图违反同分支/无环/承重资格等不变量。"""


@dataclass(frozen=True)
class SupportGraph:
    branch_id: str
    nodes: Mapping[str, StructureSnapshot]
    dependents: Mapping[str, tuple[str, ...]]

    def dependents_of(self, structure_id: str) -> tuple[str, ...]:
        return self.dependents.get(structure_id, ())


def build_support_graph(entries: Iterable[tuple[str, StructureSnapshot]]) -> SupportGraph:
    """物化并校验承重图；跨分支/悬空/自环/重复/环/非承重支撑一律拒绝。"""
    materialized = list(entries)
    if not materialized:
        msg = "承重图不得为空"
        raise GraphError(msg)
    branches = {branch_id for branch_id, _ in materialized}
    if len(branches) != 1:
        msg = f"承重图不得混合分支: {sorted(branches)}"
        raise GraphError(msg)
    branch_id = next(iter(branches))

    nodes: dict[str, StructureSnapshot] = {}
    for entry_branch, snapshot in materialized:
        if entry_branch != branch_id:
            msg = f"承重图分支不一致: {entry_branch!r} != {branch_id!r}"
            raise GraphError(msg)
        structure_id = snapshot.structure_id
        if structure_id in nodes:
            msg = f"结构重复: {structure_id}"
            raise GraphError(msg)
        nodes[structure_id] = snapshot

    reverse: dict[str, list[str]] = {structure_id: [] for structure_id in nodes}
    indegree: dict[str, int] = {}
    for structure_id, snapshot in nodes.items():
        supports = snapshot.supported_by
        indegree[structure_id] = len(supports)
        if len(set(supports)) != len(supports):
            msg = f"支撑边重复: {structure_id}"
            raise GraphError(msg)
        for support_id in supports:
            if support_id == structure_id:
                msg = f"结构不得支撑自身: {structure_id}"
                raise GraphError(msg)
            support = nodes.get(support_id)
            if support is None:
                msg = f"支撑结构不存在: {support_id}"
                raise GraphError(msg)
            if support.phase is not StructurePhase.ACTIVE or not support.load_bearing:
                msg = f"支撑结构不可承重: {support_id} ({support.phase.value})"
                raise GraphError(msg)
            reverse[support_id].append(structure_id)

    dependents: dict[str, tuple[str, ...]] = {}
    for structure_id, items in reverse.items():
        dependents[structure_id] = tuple(sorted(items))
    _reject_cycle(dependents, indegree)

    return SupportGraph(
        branch_id=branch_id,
        nodes=MappingProxyType(nodes),
        dependents=MappingProxyType(dependents),
    )


def _reject_cycle(dependents: Mapping[str, tuple[str, ...]], indegree: Mapping[str, int]) -> None:
    remaining = dict(indegree)
    ready = [structure_id for structure_id, degree in remaining.items() if degree == 0]
    heapq.heapify(ready)
    processed = 0
    while ready:
        structure_id = heapq.heappop(ready)
        processed += 1
        for dependent in dependents.get(structure_id, ()):
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                heapq.heappush(ready, dependent)
    if processed != len(indegree):
        msg = "承重依赖存在环"
        raise GraphError(msg)


@dataclass(frozen=True)
class CascadeState:
    pending: tuple[tuple[str, str | None], ...]
    emitted: frozenset[str]
    cause: StructureCollapseCause

    @property
    def done(self) -> bool:
        return not self.pending


@dataclass(frozen=True)
class CascadeStep:
    state: CascadeState
    events: tuple[WorldEvent, ...]


def start_cascade(
    graph: SupportGraph,
    seed_ids: Iterable[str],
    *,
    cause: StructureCollapseCause = "support_lost",
) -> CascadeState:
    seeds = set(seed_ids)
    unknown = seeds - set(graph.nodes)
    if unknown:
        msg = f"坍塌种子不存在: {sorted(unknown)}"
        raise GraphError(msg)
    pending = tuple(sorted((structure_id, None) for structure_id in seeds))
    return CascadeState(pending=pending, emitted=frozenset(), cause=cause)


def advance_cascade(
    graph: SupportGraph,
    state: CascadeState,
    *,
    tick: int,
    event_budget: int = CASCADE_EVENT_BUDGET_PER_FRAME,
) -> CascadeStep:
    """单帧推进至多 event_budget 条坍塌事件；返回新游标与事件。"""
    if event_budget <= 0:
        msg = "event_budget 必须为正"
        raise ValueError(msg)
    queue = dict(state.pending)
    emitted = set(state.emitted)
    events: list[WorldEvent] = []
    ready = sorted(queue)
    heapq.heapify(ready)

    while ready and len(events) < event_budget:
        structure_id = heapq.heappop(ready)
        lost_support = queue.pop(structure_id)
        if structure_id in emitted:
            continue
        snapshot = graph.nodes[structure_id]
        if snapshot.phase is not StructurePhase.ACTIVE:
            continue
        support_path = () if lost_support is None else (lost_support,)
        events.append(
            structure_collapsed_event(
                tick,
                structure_id=structure_id,
                cause=state.cause,
                support_path=support_path,
            )
        )
        emitted.add(structure_id)
        for dependent in graph.dependents_of(structure_id):
            if dependent in emitted:
                continue
            prior = queue.get(dependent)
            if prior is None or structure_id < prior:
                queue[dependent] = structure_id
                heapq.heappush(ready, dependent)

    pending = tuple(sorted(queue.items()))
    return CascadeStep(
        state=CascadeState(pending=pending, emitted=frozenset(emitted), cause=state.cause),
        events=tuple(events),
    )
