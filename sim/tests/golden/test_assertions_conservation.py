"""守恒断言组最小单元测试（M4-C4）——真实账本驱动 + 假投影，**不跑满日**。

C5：全部显式 seed / 常量，不用 `random.*` / `time`。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from sim.core.events import (
    EventKind,
    WorldEvent,
    material_moved_event,
    structure_completed_event,
    structure_removed_event,
    structure_started_event,
)
from sim.core.persistence.npc_store import NpcStoreError
from sim.tests.golden.assertions import (
    MaterialBalanceRow,
    assert_material_balances_conserved,
    assert_matter_conserved,
    assert_structures_projected_from_events,
    diff_matter_states,
    fold_matter_states,
    fold_structure_phases,
)
from sim.world.matter import MatterLedger, settle_decay
from sim.world.structure import StructurePhase


def _drive_ledger() -> tuple[list[WorldEvent], MatterLedger]:
    """真实账本跑一段：立账 → 损伤 → 建造 → 自然衰减 → 归零坍塌（事件全部由内核产出）。"""
    ledger = MatterLedger()
    events: list[WorldEvent] = [
        ledger.register("wall-1", integrity=1.0, decay_rate=0.0, tick=1, x=3, y=4),
        ledger.register("crate-1", integrity=1.0, decay_rate=0.01, tick=1, x=5, y=6),
    ]
    events.append(ledger.damage("wall-1", amount=-0.25, tick=2))
    events.append(ledger.build("wall-1", amount=0.10, tick=3))
    events.extend(settle_decay(ledger, tick=4, seed=7))  # 显式 seed → 确定性（C5）
    events.append(ledger.damage("wall-1", amount=-1.0, tick=5))
    return events, ledger


def _projection(ledger: MatterLedger) -> dict[str, object]:
    """投影侧 = 账本两个物质对象的终态（逐位对账的对照组）。"""
    return {mid: ledger.state(mid) for mid in ("wall-1", "crate-1")}


def test_matter_fold_matches_kernel_ledger() -> None:
    """折叠 == 内核账本终态（逐位）：证明断言折叠与投影/重放同源。"""
    events, ledger = _drive_ledger()
    assert_matter_conserved(events, _projection(ledger))  # type: ignore[arg-type]
    assert fold_matter_states(events)["wall-1"].is_rubble is True


def test_matter_mismatch_is_bitwise_red() -> None:
    """投影被改一位即红（不给浮差：0.0 + 1e-12 也放过不了）。"""
    events, ledger = _drive_ledger()
    proj = dict(_projection(ledger))
    wall = proj["wall-1"]
    assert hasattr(wall, "integrity")
    proj["wall-1"] = replace(wall, integrity=wall.integrity + 1e-12)  # type: ignore[attr-defined]
    diffs = diff_matter_states(fold_matter_states(events), proj)  # type: ignore[arg-type]
    assert diffs and "wall-1" in diffs[0]
    with pytest.raises(AssertionError, match="逐位相等"):
        assert_matter_conserved(events, proj)  # type: ignore[arg-type]


def test_material_balances_roundtrip() -> None:
    """转移折叠 == material_balances 投影；总量守恒（只搬运不增减）。"""
    events = [
        material_moved_event(
            tick=1,
            transfer_id="t1",
            material_id="wood",
            quantity=5.0,
            from_ref="world:stock",
            to_ref="site:s1",
            reason="build_reserved",
        ),
        material_moved_event(
            tick=2,
            transfer_id="t2",
            material_id="wood",
            quantity=2.0,
            from_ref="site:s1",
            to_ref="site:s2",
            reason="build_reserved",
        ),
    ]
    rows = [
        MaterialBalanceRow(ref="world:stock", material_id="wood", quantity=-5.0),
        MaterialBalanceRow(ref="site:s1", material_id="wood", quantity=3.0),
        MaterialBalanceRow(ref="site:s2", material_id="wood", quantity=2.0),
    ]
    assert_material_balances_conserved(events, rows)
    bad = [replace(rows[0], quantity=-4.0), *rows[1:]]
    with pytest.raises(AssertionError, match="材料转移守恒失败"):
        assert_material_balances_conserved(events, bad)


def test_material_overdraft_is_fail_closed() -> None:
    """非 world ref 余额不足 → 折叠函数 fail-closed（守恒红，域规则由数据域定义）。"""
    events = [
        material_moved_event(
            tick=1,
            transfer_id="t1",
            material_id="wood",
            quantity=5.0,
            from_ref="site:s1",
            to_ref="site:s2",
            reason="build_reserved",
        )
    ]
    with pytest.raises(NpcStoreError):
        assert_material_balances_conserved(events, [])


def test_structure_phase_fold_and_projection_subset() -> None:
    """结构 phase 逐位相等 + 投影 ⊆ 事件；REMOVED 删行后不应再出现在投影。"""
    events = [
        structure_started_event(
            tick=1,
            structure_id="s1",
            tiles=((0, 0), (1, 1)),
            kind="shelter",
            material="wood",
            planned_duration_ticks=100,
            recipe_id="r1",
            recipe_version="1",
            build_rule_version="v1",
        ),
        structure_completed_event(tick=50, structure_id="s1", quality=0.9, integrity=1.0),
    ]
    folded = {sid: s.phase for sid, s in fold_structure_phases(events).items()}
    assert folded["s1"] is StructurePhase.ACTIVE
    assert_structures_projected_from_events(events, {"s1": "active"})
    with pytest.raises(AssertionError, match="结构本体未由事件投影"):
        assert_structures_projected_from_events(events, {"ghost": "active"})

    removed = [*events, structure_removed_event(tick=60, structure_id="s1", reason="demolished")]
    assert fold_structure_phases(removed) == {}  # REMOVED = 删行
    with pytest.raises(AssertionError, match="无来源事件"):
        assert_structures_projected_from_events(removed, {"s1": "active"})


def test_matter_payload_missing_id_is_rejected() -> None:
    """payload 缺 matter_id → 显式报错（不静默跳过）。"""
    broken = WorldEvent(branch_id="main", tick=1, event_type=EventKind.MATTER_BUILD, payload={})
    with pytest.raises(ValueError, match="matter_id"):
        fold_matter_states([broken])
