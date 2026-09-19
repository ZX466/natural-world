"""历法派生 — 纯函数，不落状态（m0-core.md §1）。

所有戏内时间表达由 tick 单向派生：减少快照体积，且重放天然一致。
界面（C3）只能消费这里的输出，绝不接触原始 tick。
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple

TICKS_PER_GAME_DAY = 86_400  # 1 tick = 1 游戏秒（DESIGN §10 锁定）
TICKS_PER_GAME_HOUR = 3_600

MARKET_DAY_INTERVAL = 5  # 集市日间隔（内容常量，占位值）


class DayPhase(Enum):
    """昼夜相位 — M0 仅用于前端昼夜调色。"""

    DAWN = "dawn"
    DAY = "day"
    DUSK = "dusk"
    NIGHT = "night"


class GameTime(NamedTuple):
    """戏内时间（day 从 1 起，时分秒 24h 制）。"""

    day: int
    hour: int
    minute: int
    second: int


def game_time(tick: int) -> GameTime:
    """tick → 戏内时间。tick 0 = 第 1 天 00:00:00。"""
    if tick < 0:
        msg = f"tick 非负约束被违反: {tick}"
        raise ValueError(msg)
    day, rem = divmod(tick, TICKS_PER_GAME_DAY)
    hour, rem = divmod(rem, TICKS_PER_GAME_HOUR)
    minute, second = divmod(rem, 60)
    return GameTime(day=day + 1, hour=hour, minute=minute, second=second)


def phase_of_day(tick: int) -> DayPhase:
    """昼夜相位：黎明 5-7 / 白天 7-17 / 黄昏 17-19 / 夜晚其余。"""
    hour = game_time(tick).hour
    if 5 <= hour < 7:
        return DayPhase.DAWN
    if 7 <= hour < 17:
        return DayPhase.DAY
    if 17 <= hour < 19:
        return DayPhase.DUSK
    return DayPhase.NIGHT


def is_market_day(tick: int) -> bool:
    """集市日：每 MARKET_DAY_INTERVAL 天一次（第 1、6、11…天）。"""
    return (game_time(tick).day - 1) % MARKET_DAY_INTERVAL == 0
