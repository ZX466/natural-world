"""sim.world.fauna — 动物三只节律派生（M6 内容面；DESIGN §7 动物；pi P13/P4 红线口径）。

**职责边界（最小面）**：
- 动物 = **计数面纯函数派生**（opencode A3 判定：纯运行态、确定性刷新、
  **不进 `entities`**——soak 契约「实体只减不增」的红线：动物进 entities 会让
  `entity_count` 随刷新波动 ⇒ 红的原因与性能无关、是契约口径）；无状态无 IO；
- **三只**：狼/鹿/鸟（DESIGN §7 占位物种）——各带**活跃节律**（昼夜档对齐
  `weather.wind_slot` 的日相口径），输出 = 每只的**可叙事活跃标签**（出没/
  蛰伏），**零数值出站**（不进帧、不进协议；K12 零归因+零分层数值纪律）；
- **K4 C1 判定兑现**：动物不出专用事件——可见面走既有 `state_delta.actors[]`
  （`Actor.sprite` 自由串，**零 schema**）；**不 per-tick 产事件**（位置未变
  零事件，W-D3 口径）——本模块只给派生函数，事件由渲染消费方按需产。

C5：同 (seed, tick) 必得同节律（无隐藏随机/时钟）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sim.core.calendar import phase_of_day

#: 三只占位物种（DESIGN §7；内容常量）。
FAUNA_SPECIES: Final[tuple[str, ...]] = ("狼", "鹿", "鸟")

#: 活跃节律（每物种的活跃日相集合；值=DayPhase.value（dawn/day/dusk/night）——
#: `phase_of_day(t)` 返回枚举，成员判定用 `.value`）。
#: 狼=夜行（黄昏/夜晚）、鹿=晨昏（黎明/黄昏）、鸟=昼行（黎明/白天）。
FAUNA_ACTIVE_PHASES: Final[dict[str, frozenset[str]]] = {
    "狼": frozenset({"dusk", "night"}),
    "鹿": frozenset({"dawn", "dusk"}),
    "鸟": frozenset({"dawn", "day"}),
}

#: 活跃标签（可叙事；零数值——进帧/独白的只有这几个词）。
FAUNA_ACTIVE: Final[str] = "出没"
FAUNA_RESTING: Final[str] = "蛰伏"


@dataclass(frozen=True)
class FaunaSighting:
    """一只动物在某 tick 的节律态（frozen；**零数值字段**、零坐标——

    计数/位置不进出站面；消费方只拿「哪只出没」做叙事/渲染占位。
    """

    tick: int
    species: str  # FAUNA_SPECIES 之一
    state: str  # FAUNA_ACTIVE / FAUNA_RESTING

    def __post_init__(self) -> None:
        if self.species not in FAUNA_SPECIES:
            raise ValueError(f"物种非法: {self.species!r}")
        if self.state not in (FAUNA_ACTIVE, FAUNA_RESTING):
            raise ValueError(f"节律态非法: {self.state!r}")


def fauna_sightings_at(tick: int) -> tuple[FaunaSighting, ...]:
    """某 tick 的三只动物节律态（**纯函数**；O(物种数)=O(1)）。

    节律 = 日相 ∈ 物种活跃相集合 ⇒ 出没，否则蛰伏。
    C5：同 tick 恒同输出；**不产生事件**（可见面由消费方按需走既有 actors[]）。
    """
    phase = phase_of_day(tick).value
    out: list[FaunaSighting] = []
    for species in FAUNA_SPECIES:
        active = phase in FAUNA_ACTIVE_PHASES[species]
        out.append(
            FaunaSighting(
                tick=tick, species=species, state=FAUNA_ACTIVE if active else FAUNA_RESTING
            )
        )
    return tuple(out)


def active_species_at(tick: int) -> tuple[str, ...]:
    """某 tick 处于「出没」态的物种名清单（渲染消费方的便捷口径）。"""
    return tuple(s.species for s in fauna_sightings_at(tick) if s.state == FAUNA_ACTIVE)
