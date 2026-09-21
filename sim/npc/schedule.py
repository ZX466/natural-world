"""sim.npc.schedule — 日程/作息（M2-A1 §1.1；DESIGN §5）。

按 tick 单向派生当前应做的事（与历法同源，纯函数可重放）；集市日例外
（MARKET_DAY_INTERVAL）在 M2 只留计算位。不做计划重排（M4 意愿系统）。
"""

from __future__ import annotations

from dataclasses import dataclass

from sim.core.calendar import MARKET_DAY_INTERVAL, TICKS_PER_GAME_DAY, DayPhase, phase_of_day


@dataclass(frozen=True)
class ScheduleSlot:
    """日程档：当前相位下 NPC 应做的事（候选集输入之一，非强制）。"""

    phase: DayPhase
    action: str  # 白名单动作（sim/npc/actions.py）


#: 昼夜相位 → 缺省动作档（内容常量：白天劳作、夜里休息、晨昏闲逛）
_PHASE_ACTION: dict[DayPhase, str] = {
    DayPhase.DAWN: "wander",
    DayPhase.DAY: "work",
    DayPhase.DUSK: "wander",
    DayPhase.NIGHT: "rest",
}


def current_slot(tick: int) -> ScheduleSlot:
    """tick → 当前日程档（纯函数；同 tick 恒同档）。"""
    return ScheduleSlot(phase=phase_of_day(tick), action=_PHASE_ACTION[phase_of_day(tick)])


def is_market_day(tick: int) -> bool:
    """集市日判定（M4 前只留计算位：间隔取整日）。"""
    return (tick // TICKS_PER_GAME_DAY) % MARKET_DAY_INTERVAL == 0
