"""无孤儿变更断言组最小单元测试（M4-C4）——假事件/假投影，不跑满日。"""

from __future__ import annotations

import pytest

from sim.core.events import (
    EventKind,
    entropy_event,
    material_moved_event,
    matter_event,
    structure_removed_event,
    structure_started_event,
)
from sim.tests.golden.assertions import assert_no_orphans, find_orphans

_MATTER_EVENTS = [
    matter_event(tick=1, kind=EventKind.MATTER_BUILD, matter_id="wall-1", durability=1.0)
]
_STRUCTURE_EVENTS = [
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
    )
]
_MATERIAL_EVENTS = [
    material_moved_event(
        tick=1,
        transfer_id="t1",
        material_id="wood",
        quantity=5.0,
        from_ref="world:stock",
        to_ref="site:s1",
        reason="build_reserved",
    )
]


def test_clean_run_has_no_orphans() -> None:
    report = assert_no_orphans(
        [*_MATTER_EVENTS, *_STRUCTURE_EVENTS, *_MATERIAL_EVENTS],
        projected_matter={"wall-1": object()},
        projected_structures={"s1": "building"},
        projected_materials=[("world:stock", "wood"), ("site:s1", "wood")],
    )
    assert report.ok()


def test_entropy_inject_is_not_orphan_event() -> None:
    """**写死的坑**：熵只进事件流（裁 14-5）→ 熵事件不算孤儿事件。"""
    events = [*_STRUCTURE_EVENTS, entropy_event(tick=2, stream="weather", payload_hex="00ff")]
    report = assert_no_orphans(events, projected_structures={"s1": "building"})
    assert report.ok(), "entropy_inject 被误判为孤儿事件——违反裁 14-5 排除口径"


def test_structure_removed_is_not_orphan_event() -> None:
    """REMOVED 的投影语义是删行 → 拆除对象不在投影不算孤儿。"""
    events = [
        *_STRUCTURE_EVENTS,
        structure_removed_event(tick=9, structure_id="s1", reason="demolished"),
    ]
    assert find_orphans(events, projected_structures=()).ok()


def test_projection_without_event_is_orphan() -> None:
    with pytest.raises(AssertionError, match="孤儿投影"):
        assert_no_orphans(_STRUCTURE_EVENTS, projected_structures={"ghost": "building"})


def test_event_without_projection_is_orphan() -> None:
    with pytest.raises(AssertionError, match="孤儿事件"):
        assert_no_orphans(_MATTER_EVENTS, projected_matter={})
    with pytest.raises(AssertionError, match="孤儿事件"):
        assert_no_orphans(_MATERIAL_EVENTS, projected_materials=[])


def test_orphan_message_lists_exclusions() -> None:
    """红时报错里带合法排除说明（便于 D 批接线时自查口径）。"""
    with pytest.raises(AssertionError, match="entropy_inject"):
        assert_no_orphans(_MATTER_EVENTS, projected_matter={})
