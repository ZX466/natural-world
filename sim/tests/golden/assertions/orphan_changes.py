"""无孤儿变更断言（裁 17-1：**硬红**，不降级告警）。

两个方向都查（对齐 `docs/arch/t5-golden-scaffold.md` §3.3）：

- **方向 A（孤儿投影）**：投影里有、事件流里找不到来源——matter id 无任何 `matter.*` 事件 /
  structure id 无任何 `STRUCTURE_*` 事件 / `(ref, material_id)` 无任何 `MATERIAL_MOVED` 事件。
- **方向 B（孤儿事件）**：事件流里有、投影里没有对应对象。

**方向 B 的两个合法排除（写死的坑，漏一个就必假红）**：

1. `entropy_inject`——熵注入**只进事件流**、world state 与 prompt 面永不留痕
   （§11 + 裁 14-5），故熵事件天然没有投影行；
2. `structure.removed`——投影**删行**（`npc_store.fold_structure_snapshot` 对 REMOVED
   返回 None），故拆除事件的对象理应不在投影。

两张 structures 表都**没有 `last_event_seq` 列**（0006 列集：branch_id/structure_id/tiles/
kind/material/phase/load_bearing/supported_by/owner_id/built_by/built_at/created_at），
故本断言走 **id/来源级**判定（不靠 seq join）——与 §3.3 提案的 SQL 骨架相比是更弱的判据，
但可在**无数据库**的纯内核 golden 跑里执行；DB 侧强判据留给 D 批接线。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from sim.core.events import EventKind, WorldEvent

from .conservation import _payload, fold_matter_states, fold_structure_phases

#: 方向 B 合法排除：熵只进事件流（裁 14-5）——熵事件不产对象 id，收集阶段即跳过
ORPHAN_EXCLUDED_EVENT_KINDS: frozenset[EventKind] = frozenset({EventKind.ENTROPY_INJECT})

#: 口径说明（非收集用）：REMOVED 的投影语义是删行（`fold_structure_snapshot` → None），
#: 方向 B 改用**折叠终态**消化它；本常量留给 D 批 DB 侧 SQL 判据复用。
PROJECTION_DELETING_KINDS: frozenset[EventKind] = frozenset({EventKind.STRUCTURE_REMOVED})

_MATTER_KINDS: frozenset[EventKind] = frozenset(
    {
        EventKind.MATTER_BUILD,
        EventKind.MATTER_DECAY,
        EventKind.MATTER_DAMAGE,
        EventKind.MATTER_COLLAPSE,
    }
)
_STRUCTURE_KINDS: frozenset[EventKind] = frozenset(
    {
        EventKind.STRUCTURE_STARTED,
        EventKind.STRUCTURE_CHECKPOINT,
        EventKind.STRUCTURE_COMPLETED,
        EventKind.STRUCTURE_COLLAPSED,
        EventKind.STRUCTURE_REMOVED,
    }
)


@dataclass(frozen=True)
class OrphanReport:
    """孤儿清单（两方向；空 = 干净）。"""

    orphan_projections: tuple[str, ...]
    orphan_events: tuple[str, ...]

    def ok(self) -> bool:
        return not (self.orphan_projections or self.orphan_events)


def _ids(values: Mapping[str, object] | Iterable[str]) -> set[str]:
    if isinstance(values, Mapping):
        return set(values)
    return set(values)


def find_orphans(
    events: Sequence[WorldEvent],
    *,
    projected_matter: Mapping[str, object] | Iterable[str] = (),
    projected_structures: Mapping[str, object] | Iterable[str] = (),
    projected_materials: Iterable[tuple[str, str]] = (),
) -> OrphanReport:
    """扫两个方向的孤儿（确定性：入参顺序无关，输出排序）。

    `projected_materials` 元素为 `(ref, material_id)`（`material_balances` 投影键）。
    """
    event_matter: set[str] = set()
    event_structure: set[str] = set()
    event_material: set[tuple[str, str]] = set()
    for ev in events:
        kind = ev.event_type
        payload = _payload(ev)
        if kind in ORPHAN_EXCLUDED_EVENT_KINDS:
            # 熵只进事件流、world state 永不留痕（裁 14-5）→ 既不产对象 id 也不该有投影行
            continue
        if kind in _MATTER_KINDS:
            mid = str(payload.get("matter_id", ""))
            if mid:
                event_matter.add(mid)
        elif kind in _STRUCTURE_KINDS:
            sid = str(payload.get("structure_id", ""))
            if sid:
                event_structure.add(sid)
        elif kind is EventKind.MATERIAL_MOVED:
            mid = str(payload.get("material_id", ""))
            for ref in (str(payload.get("from_ref", "")), str(payload.get("to_ref", ""))):
                if mid and ref:
                    event_material.add((ref, mid))

    proj_matter = _ids(projected_matter)
    proj_structure = _ids(projected_structures)
    proj_material = set(projected_materials)

    orphan_projections = tuple(
        [f"matter:{m}" for m in sorted(proj_matter - event_matter)]
        + [f"structure:{s}" for s in sorted(proj_structure - event_structure)]
        + [f"material:{r}/{m}" for r, m in sorted(proj_material - event_material)]
    )

    # 方向 B：事件有、投影无——但按**折叠终态**判，而不是「见过的事件 id 全集」：
    # `structure.removed` 的投影语义是删行（fold 返回 None），拆除后的 id 理应不在投影，
    # 用全集判会把合法拆除误报成孤儿。熵事件（ORPHAN_EXCLUDED_EVENT_KINDS）根本不产对象 id，
    # 收集阶段即跳过——漏这条就必假红（裁 14-5 + 脚手架 §3.3 写死的坑）。
    folded_matter = set(fold_matter_states(events))
    folded_structures = set(fold_structure_phases(events))
    orphan_events = (
        tuple(f"matter:{m}" for m in sorted(folded_matter - proj_matter))
        + tuple(f"structure:{s}" for s in sorted(folded_structures - proj_structure))
        + tuple(f"material:{r}/{m}" for r, m in sorted(event_material - proj_material))
    )
    return OrphanReport(orphan_projections=orphan_projections, orphan_events=orphan_events)


def assert_no_orphans(
    events: Sequence[WorldEvent],
    *,
    projected_matter: Mapping[str, object] | Iterable[str] = (),
    projected_structures: Mapping[str, object] | Iterable[str] = (),
    projected_materials: Iterable[tuple[str, str]] = (),
) -> OrphanReport:
    """裁 17-1 硬判：任一方向有孤儿即红（不降级告警）；返回报告便于调用方落快照。"""
    report = find_orphans(
        events,
        projected_matter=projected_matter,
        projected_structures=projected_structures,
        projected_materials=projected_materials,
    )
    assert report.ok(), (
        "无孤儿变更失败（裁 17-1 硬红）:\n  孤儿投影: "
        + (", ".join(report.orphan_projections) or "无")
        + "\n  孤儿事件: "
        + (", ".join(report.orphan_events) or "无")
        + "\n  合法排除: entropy_inject（熵只进事件流）+ structure.removed（投影删行）"
    )
    return report
