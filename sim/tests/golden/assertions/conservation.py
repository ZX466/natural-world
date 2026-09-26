"""物质/材料/结构守恒断言（裁 17-1：逐位相等，不给浮差）。

三个面（对齐 `docs/arch/t5-golden-scaffold.md` §3.1）：

- **matter 存量**：事件流折叠终态 == 投影终态（`integrity` / `decay_rate` / `is_rubble` 逐位相等）；
  折叠复用 `npc_store.fold_matter_snapshot`（与 `_project_matter` 投影路径、
  `materialize_matter_replay` 重放路径**同一函数**，§19.3）。
- **材料转移**：`MATERIAL_MOVED` 折叠余额 == `material_balances` 投影行（0007 表）逐位相等，
  且**总量守恒**（转移只搬运不增减：Σ 余额与基线一致）。
- **结构本体**：投影 `structure_id` **⊆** 事件（每个 id 有来源事件），且 `phase` 与事件折叠
  逐位相等（复用 `fold_structure_snapshot`；`STRUCTURE_REMOVED` 折叠返回 None = 删行，
  故从 phase 视图消失，与投影一致）。

熵态列（`integrity`/`quality`/`decay_rate`/`is_rubble`）按裁 14-② 已移出 structures 表，
故结构面只对账 `phase`；物质面只对账 matter 三列。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sim.core.events import EventKind, WorldEvent
from sim.core.persistence.npc_store import (
    fold_material_balance,
    fold_matter_snapshot,
    fold_structure_snapshot,
)
from sim.world.matter import MatterSnapshot
from sim.world.structure import StructureSnapshot

MATTER_KINDS: frozenset[EventKind] = frozenset(
    {
        EventKind.MATTER_BUILD,
        EventKind.MATTER_DECAY,
        EventKind.MATTER_DAMAGE,
        EventKind.MATTER_COLLAPSE,
    }
)

STRUCTURE_KINDS: frozenset[EventKind] = frozenset(
    {
        EventKind.STRUCTURE_STARTED,
        EventKind.STRUCTURE_CHECKPOINT,
        EventKind.STRUCTURE_COMPLETED,
        EventKind.STRUCTURE_COLLAPSED,
        EventKind.STRUCTURE_REMOVED,
    }
)


def _payload(ev: WorldEvent) -> Mapping[str, Any]:
    return ev.payload


def _required_str(ev: WorldEvent, field: str) -> str:
    raw = str(_payload(ev).get(field, ""))
    if not raw:
        raise ValueError(f"{ev.event_type.value} payload 缺 {field}: {_payload(ev)!r}")
    return raw


# ---------------------------------------------------------------------------
# 面 1：matter 存量（逐位相等）
# ---------------------------------------------------------------------------


def fold_matter_states(events: Sequence[WorldEvent]) -> dict[str, MatterSnapshot]:
    """事件流 → matter 终态（**复用数据域单一折叠规则**，语义同 `materialize_matter_replay`）。"""
    states: dict[str, MatterSnapshot] = {}
    for ev in events:
        if ev.event_type not in MATTER_KINDS:
            continue
        matter_id = _required_str(ev, "matter_id")
        states[matter_id] = fold_matter_snapshot(
            states.get(matter_id),
            matter_id=matter_id,
            durability=float(_payload(ev).get("durability", -1.0)),
            decay_rate=float(_payload(ev).get("decay_rate", -1.0)),
            is_collapse=ev.event_type is EventKind.MATTER_COLLAPSE,
        )
    return states


def _matter_map(
    projected: Mapping[str, MatterSnapshot] | Sequence[MatterSnapshot],
) -> dict[str, MatterSnapshot]:
    if isinstance(projected, Mapping):
        return dict(projected)
    out: dict[str, MatterSnapshot] = {}
    for snapshot in projected:
        out[snapshot.matter_id] = snapshot
    return out


def diff_matter_states(
    folded: Mapping[str, MatterSnapshot],
    projected: Mapping[str, MatterSnapshot] | Sequence[MatterSnapshot],
) -> tuple[str, ...]:
    """逐位比较（`integrity`/`decay_rate`/`is_rubble`），返回可读差异（空 = 一致）。"""
    proj = _matter_map(projected)
    diffs: list[str] = []
    for matter_id in sorted(set(folded) | set(proj)):
        f = folded.get(matter_id)
        p = proj.get(matter_id)
        if f is None:
            diffs.append(f"{matter_id}: 事件流无此物质（投影有）")
            continue
        if p is None:
            diffs.append(f"{matter_id}: 投影无此物质（事件流有）")
            continue
        if (f.integrity, f.decay_rate, f.is_rubble) != (p.integrity, p.decay_rate, p.is_rubble):
            diffs.append(
                f"{matter_id}: 事件流(integrity={f.integrity!r}, decay_rate={f.decay_rate!r}, "
                f"is_rubble={f.is_rubble}) != 投影(integrity={p.integrity!r}, "
                f"decay_rate={p.decay_rate!r}, is_rubble={p.is_rubble})"
            )
    return tuple(diffs)


def assert_matter_conserved(
    events: Sequence[WorldEvent],
    projected: Mapping[str, MatterSnapshot] | Sequence[MatterSnapshot],
) -> None:
    """裁 17-1 硬判：matter 存量事件流折叠 == 投影（逐位相等，不给浮差）。"""
    diffs = diff_matter_states(fold_matter_states(events), projected)
    assert not diffs, "matter 守恒失败（逐位相等，不给浮差）:\n  " + "\n  ".join(diffs)


# ---------------------------------------------------------------------------
# 面 2：材料转移（`material_balances`，0007 表）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaterialBalanceRow:
    """`material_balances` 一行（0007：ref / material_id / quantity / updated_at_tick）。"""

    ref: str
    material_id: str
    quantity: float


def fold_material_balances(
    events: Sequence[WorldEvent],
    *,
    initial: Mapping[tuple[str, str], float] | None = None,
) -> dict[tuple[str, str], float]:
    """事件流 → `(ref, material_id)` 余额（复用 `fold_material_balance`：from 减 / to 加）。

    `initial` = 跑段起点的基线余额（冷启动一般为空；`world:*` 是外部供给基准、净负合法，
    非 world ref 余额不足由折叠函数 fail-closed 抛错 → 守恒红）。
    """
    balances: dict[tuple[str, str], float] = dict(initial or {})
    for ev in events:
        if ev.event_type is not EventKind.MATERIAL_MOVED:
            continue
        material_id = _required_str(ev, "material_id")
        from_ref = _required_str(ev, "from_ref")
        to_ref = _required_str(ev, "to_ref")
        quantity = float(_payload(ev).get("quantity", 0.0))
        key_from = (from_ref, material_id)
        key_to = (to_ref, material_id)
        balances[key_from], balances[key_to] = fold_material_balance(
            balances.get(key_from, 0.0),
            balances.get(key_to, 0.0),
            quantity=quantity,
            from_ref=from_ref,
        )
    return balances


def assert_material_balances_conserved(
    events: Sequence[WorldEvent],
    rows: Sequence[MaterialBalanceRow],
    *,
    initial: Mapping[tuple[str, str], float] | None = None,
) -> None:
    """裁 17-1 硬判：转移折叠余额 == `material_balances` 投影（逐位相等）**且**总量守恒。

    总量守恒 = Σ 所有 `(ref, material_id)` 余额与基线一致——转移只搬运不增减（材料不凭空生灭）。
    """
    folded = fold_material_balances(events, initial=initial)
    projected = {(r.ref, r.material_id): r.quantity for r in rows}
    diffs: list[str] = []
    for key in sorted(set(folded) | set(projected)):
        f = folded.get(key)
        p = projected.get(key)
        if f is None:
            diffs.append(f"{key}: 事件流无此余额（投影有 {p!r}）")
        elif p is None:
            diffs.append(f"{key}: 投影无此余额（事件流有 {f!r}）")
        elif f != p:
            diffs.append(f"{key}: 事件流 {f!r} != 投影 {p!r}")
    total_folded = sum(folded.values())
    total_base = sum(dict(initial or {}).values())
    if total_folded != total_base:
        diffs.append(f"材料总量不守恒：事件流折叠 Σ={total_folded!r} != 基线 Σ={total_base!r}")
    assert not diffs, "材料转移守恒失败（逐位相等 + 总量守恒）:\n  " + "\n  ".join(diffs)


# ---------------------------------------------------------------------------
# 面 3：结构本体 ⊆ 事件（phase 逐位相等）
# ---------------------------------------------------------------------------


def _structure_fields(ev: WorldEvent) -> dict[str, Any]:
    """STRUCTURE_* payload → 折叠入参（对齐 `npc_store._structure_event_fields` 的字段映射）。

    域折叠 `fold_structure_snapshot` 构造 `StructureSnapshot` 时校验 `tiles` 非空，故 phase 折叠
    也必须把拓扑字段喂进去——否则 STARTED 会被判「tiles 不得为空」误红。
    """
    p = _payload(ev)
    raw_tiles = p.get("tiles") or ()
    tiles: tuple[tuple[int, int], ...] = tuple((int(item[0]), int(item[1])) for item in raw_tiles)
    raw_supports = p.get("supported_by") or ()
    return {
        "tiles": tiles,
        "kind": str(p.get("kind", "")),
        "material": str(p.get("material", "")),
        "load_bearing": bool(p.get("load_bearing", False)),
        "supported_by": tuple(str(s) for s in raw_supports),
        "owner_id": str(p.get("owner_id", "")),
        "built_by": str(p.get("built_by", "")),
    }


def fold_structure_phases(events: Sequence[WorldEvent]) -> dict[str, StructureSnapshot]:
    """事件流 → structure 终态（复用 `fold_structure_snapshot`；REMOVED → None = 删行）。"""
    states: dict[str, StructureSnapshot] = {}
    for ev in events:
        if ev.event_type not in STRUCTURE_KINDS:
            continue
        structure_id = _required_str(ev, "structure_id")
        fields = _structure_fields(ev)
        nxt = fold_structure_snapshot(
            states.get(structure_id),
            event_type=ev.event_type,
            structure_id=structure_id,
            tick=ev.tick,
            tiles=fields["tiles"],
            kind=str(fields["kind"]),
            material=str(fields["material"]),
            load_bearing=bool(fields["load_bearing"]),
            supported_by=fields["supported_by"],
            owner_id=str(fields["owner_id"]),
            built_by=str(fields["built_by"]),
        )
        if nxt is None:
            states.pop(structure_id, None)
        else:
            states[structure_id] = nxt
    return states


def assert_structures_projected_from_events(
    events: Sequence[WorldEvent],
    projected_phases: Mapping[str, str] | Iterable[str],
) -> None:
    """裁 17-1 硬判：投影 structure_id **⊆** 事件（每个 id 有来源事件）且 phase 逐位相等。

    熵态列不在本面（裁 14-② 已移出 structures 表，熵态真相在事件流）→ 只对账 `phase`；
    事件有结构但投影无 = 孤儿事件方向，归 `orphan_changes`（此处仅提示，不重复判红）。
    """
    folded = {sid: s.phase.value for sid, s in fold_structure_phases(events).items()}
    projected = (
        dict(projected_phases)
        if isinstance(projected_phases, Mapping)
        else dict.fromkeys(projected_phases, "")
    )
    diffs: list[str] = []
    for structure_id in sorted(projected):
        if structure_id not in folded:
            diffs.append(f"{structure_id}: 投影有结构但事件流无来源事件")
            continue
        want = projected[structure_id]
        if want and want != folded[structure_id]:
            diffs.append(
                f"{structure_id}: 投影 phase={want!r} != 事件折叠 {folded[structure_id]!r}"
            )
    assert not diffs, "结构本体未由事件投影（⊆ 判定 + phase 逐位相等）:\n  " + "\n  ".join(diffs)
