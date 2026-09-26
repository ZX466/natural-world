"""建造域纯状态与施工推进（M4-D2b；事件为真相，本模块零 SQL/零 IO）。

- ``StructureSnapshot`` 只含拓扑与生命周期；熵态在 ``matter_state``；
- ``advance_build`` 按 ``build_rule_version`` 选规则，未知版本 fail-closed；
- checkpoint cadence = 每游戏日一次，相对 ``started_tick`` 分桶；
- 尾部重算以最近 checkpoint 自带版本为准，逐位相等可复演。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.core.events import WorldEvent, structure_checkpoint_event

BUILD_RULE_VERSION: Final[str] = "m4-v1"
CHECKPOINT_INTERVAL_TICKS: Final[int] = TICKS_PER_GAME_DAY


class UnknownBuildRuleError(ValueError):
    """未知/已淘汰 build rule version；禁止静默回落到当前版本。"""


class StructurePhase(StrEnum):
    PLANNED = "planned"
    BUILDING = "building"
    ACTIVE = "active"
    COLLAPSING = "collapsing"
    RUBBLE = "rubble"


@dataclass(frozen=True)
class StructureSnapshot:
    """结构当前拓扑与生命周期投影（不含熵态列）。"""

    structure_id: str
    tiles: tuple[tuple[int, int], ...]
    kind: str
    material: str
    phase: StructurePhase
    load_bearing: bool
    supported_by: tuple[str, ...]
    owner_id: str = ""
    built_by: str = ""
    built_at: int | None = None

    def __post_init__(self) -> None:
        if not self.structure_id:
            msg = "structure_id 不得为空"
            raise ValueError(msg)
        if not self.tiles:
            msg = "tiles 不得为空"
            raise ValueError(msg)
        if tuple(sorted(self.tiles)) != self.tiles or len(set(self.tiles)) != len(self.tiles):
            msg = "tiles 必须已排序且不重复"
            raise ValueError(msg)
        if tuple(sorted(self.supported_by)) != self.supported_by:
            msg = "supported_by 必须已排序"
            raise ValueError(msg)
        if len(set(self.supported_by)) != len(self.supported_by):
            msg = "supported_by 不得重复"
            raise ValueError(msg)
        if self.built_at is not None and self.built_at < 0:
            msg = "built_at 不得为负"
            raise ValueError(msg)


@dataclass(frozen=True)
class BuildProgress:
    """施工检查点状态；推进规则只读该快照。"""

    structure_id: str
    progress: float
    quality: float
    integrity: float
    build_rule_version: str
    started_tick: int
    planned_duration_ticks: int
    last_checkpoint_tick: int | None = None

    def __post_init__(self) -> None:
        for name in ("progress", "quality", "integrity"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                msg = f"{name} 必须在 0..1：{value!r}"
                raise ValueError(msg)
        if not self.build_rule_version:
            msg = "build_rule_version 不得为空"
            raise ValueError(msg)
        if self.started_tick < 0 or self.planned_duration_ticks <= 0:
            msg = "施工 tick/duration 非法"
            raise ValueError(msg)
        if self.last_checkpoint_tick is not None and self.last_checkpoint_tick < self.started_tick:
            msg = "last_checkpoint_tick 不得早于 started_tick"
            raise ValueError(msg)


_RuleFn = Callable[[BuildProgress, int], BuildProgress]


def _advance_v1(state: BuildProgress, target_tick: int) -> BuildProgress:
    elapsed = target_tick - state.started_tick
    progress = max(0.0, min(1.0, elapsed / state.planned_duration_ticks))
    return replace(state, progress=progress)


_BUILD_RULES: Final[dict[str, _RuleFn]] = {BUILD_RULE_VERSION: _advance_v1}


def advance_build(state: BuildProgress, *, target_tick: int) -> BuildProgress:
    """按 state 自带规则版本推进；未知版本抛错，不回落。"""
    rule = _BUILD_RULES.get(state.build_rule_version)
    if rule is None:
        msg = f"未知 build_rule_version: {state.build_rule_version!r}"
        raise UnknownBuildRuleError(msg)
    return rule(state, target_tick)


def next_checkpoint_tick(state: BuildProgress) -> int:
    """下一个游戏日边界（相对上次 checkpoint；未发过则相对 started_tick）。"""
    anchor = (
        state.last_checkpoint_tick if state.last_checkpoint_tick is not None else state.started_tick
    )
    return (anchor // CHECKPOINT_INTERVAL_TICKS + 1) * CHECKPOINT_INTERVAL_TICKS


def checkpoint_due(state: BuildProgress, *, tick: int) -> bool:
    return tick >= next_checkpoint_tick(state)


def mark_checkpoint(state: BuildProgress, *, tick: int) -> BuildProgress:
    """标记 checkpoint 已发；同游戏日不再重复发。"""
    if not checkpoint_due(state, tick=tick):
        msg = f"tick {tick} 尚未到 checkpoint 边界"
        raise ValueError(msg)
    return replace(state, last_checkpoint_tick=tick)


def build_checkpoint_event(state: BuildProgress, *, tick: int) -> WorldEvent | None:
    """cadence 到点才产 STRUCTURE_CHECKPOINT；tick 由事件单一承载。"""
    if not checkpoint_due(state, tick=tick):
        return None
    return structure_checkpoint_event(
        tick,
        structure_id=state.structure_id,
        progress=state.progress,
        quality=state.quality,
        integrity=state.integrity,
        build_rule_version=state.build_rule_version,
    )


def recompute_tail(checkpoint: BuildProgress, *, target_tick: int) -> BuildProgress:
    """以最近 checkpoint 自带版本确定性重算尾部。"""
    return advance_build(checkpoint, target_tick=target_tick)
