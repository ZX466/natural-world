"""游戏时钟 — 时间唯一权威（m0-core.md §1）。

clock 不推进世界，只回答「现在是什么时间、该走几个 tick」。
时间尺切换只改「真实秒 → tick」换算率，不改事件流结构（回放对时间尺无感）。
"""

from __future__ import annotations

import enum

import structlog

from sim.core.calendar import DayPhase, GameTime, game_time, is_market_day, phase_of_day

logger = structlog.get_logger(__name__)

TICKS_PER_REAL_SECOND_NORMAL = 60.0  # 1x = 60 tick/s 实机（DESIGN §10 v2.1）
TICKS_PER_REAL_SECOND_COMBAT = 1.0  # 战斗时间尺：1 tick = 1 真实秒（§9 v2.1）
MAX_CATCHUP_REAL_SECONDS = 4.0  # 单帧补 tick 上限（防死亡螺旋）
ALLOWED_SPEEDS = frozenset({0.0, 1.0, 4.0, 16.0})


class TimeScale(enum.Enum):
    """时间尺：普通实机 / 战斗慢镜（进入战斗自动切换，§9 v2.1）。"""

    NORMAL = "normal"
    COMBAT = "combat"


class GameClock:
    """tick 唯一权威。累加器模式：advance(real_dt) → 本帧应推进的 tick 数。"""

    def __init__(self, speed: float = 1.0) -> None:
        if speed not in ALLOWED_SPEEDS:
            msg = f"非法倍速: {speed}，允许 {sorted(ALLOWED_SPEEDS)}"
            raise ValueError(msg)
        self._tick = 0
        self._speed = speed
        self._timescale = TimeScale.NORMAL
        self._accumulator = 0.0

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def timescale(self) -> TimeScale:
        return self._timescale

    def set_speed(self, speed: float) -> None:
        if speed not in ALLOWED_SPEEDS:
            msg = f"非法倍速: {speed}，允许 {sorted(ALLOWED_SPEEDS)}"
            raise ValueError(msg)
        self._speed = speed

    def ticks_per_real_second(self) -> float:
        base = (
            TICKS_PER_REAL_SECOND_COMBAT
            if self._timescale is TimeScale.COMBAT
            else (TICKS_PER_REAL_SECOND_NORMAL)
        )
        return base * self._speed

    def advance(self, real_dt: float) -> int:
        """喂入真实流逝秒数，返回本帧应推进的 tick 数（累加器模式）。

        real_dt 超过 MAX_CATCHUP_REAL_SECONDS 时截断并记日志（丢弃超时部分）。
        """
        if real_dt < 0:
            msg = f"real_dt 非负约束被违反: {real_dt}"
            raise ValueError(msg)
        dt = min(real_dt, MAX_CATCHUP_REAL_SECONDS)
        if real_dt > MAX_CATCHUP_REAL_SECONDS:
            logger.warning("clock.catchup_capped", requested=real_dt, used=dt)
        self._accumulator += dt * self.ticks_per_real_second()
        n_ticks = int(self._accumulator)
        self._accumulator -= n_ticks
        self._tick += n_ticks
        return n_ticks

    def enter_combat(self) -> None:
        """切换战斗时间尺；累加器清零防突跳。世界照常运转，只是战斗局部放慢。"""
        self._timescale = TimeScale.COMBAT
        self._accumulator = 0.0

    def exit_combat(self) -> None:
        self._timescale = TimeScale.NORMAL
        self._accumulator = 0.0

    # --- 戏内时间派生（纯函数委托，clock 不存派生状态） ---

    def game_time(self) -> GameTime:
        return game_time(self._tick)

    def phase_of_day(self) -> DayPhase:
        return phase_of_day(self._tick)

    def is_market_day(self) -> bool:
        return is_market_day(self._tick)
