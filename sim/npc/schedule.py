"""sim.npc.schedule — 日程/作息（M2-A1 §1.1；DESIGN §5）。

按 tick 与角色画像派生日程候选；职业、个人作息和集市日只给有限效用偏置。
"""

from __future__ import annotations

from dataclasses import dataclass
from zlib import crc32

from sim.core.calendar import TICKS_PER_GAME_HOUR, DayPhase, is_market_day, phase_of_day
from sim.npc.model import NpcProfileData

MARKET_SITE = (72, 52)


@dataclass(frozen=True)
class ScheduleSlot:
    """日程档：当前相位下 NPC 应做的事（候选集输入之一，非强制）。"""

    phase: DayPhase
    action: str  # 白名单动作（sim/npc/actions.py）
    target: str = ""


#: 昼夜相位 → 缺省动作档（内容常量：白天劳作、夜里休息、晨昏闲逛）
_PHASE_ACTION: dict[DayPhase, str] = {
    DayPhase.DAWN: "wander",
    DayPhase.DAY: "work",
    DayPhase.DUSK: "wander",
    DayPhase.NIGHT: "rest",
}


def current_slot(tick: int, profile: NpcProfileData | None = None) -> ScheduleSlot:
    """(tick, profile) → 日程候选（纯函数；同输入恒同档，省略画像保留缺省档）。"""
    phase = phase_of_day(tick)
    if profile is None:
        return ScheduleSlot(phase, _PHASE_ACTION[phase])
    if phase is DayPhase.DAY and is_market_day(tick) and profile.species == "human":
        return ScheduleSlot(phase, "work" if profile.occupation == "商贩" else "move", "market")
    offset = (crc32(profile.npc_id.encode()) % 3 - 1) * TICKS_PER_GAME_HOUR
    personal_phase = phase_of_day(max(0, tick + offset))
    action = _PHASE_ACTION[personal_phase]
    if personal_phase is DayPhase.DAY and profile.occupation == "艺人":
        action = "request_chat"
    return ScheduleSlot(phase, action)
