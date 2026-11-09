"""受控启动补跑：只消费显式时长，确定性引擎事件仍经普通 tick 和 flush。"""

from __future__ import annotations

import asyncio
import math
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog

from sim.core.calendar import TICKS_PER_GAME_DAY, TICKS_PER_GAME_HOUR
from sim.core.clock import MAX_CATCHUP_REAL_SECONDS
from sim.core.events import WorldEvent
from sim.core.tick import _MAX_TICKS_PER_FRAME, TickLoop

logger = structlog.get_logger(__name__)
OfflineFlush = Callable[[list[WorldEvent], float, bool], Awaitable[None]]

#: 停机补跑的默认上限：**一个游戏小时**，不是一整个游戏日。
#:
#: 每 tick 都要跑满 L1 效用决策（实测 ~4ms，与
#: `docs/perf/budget.md` 的 `L1_UTILITY_TICK_LIMIT_MS=6.0` 同量级），所以上限
#: 直接换算成启动时长：一天 = 86400 tick ≈ 250s，一小时 = 3600 tick ≈ 15s。
#: 停服超过 24 真实分钟就必然撞满旧上限，重启一次要等五分钟——对单人开发循环
#: 不可接受，故默认收敛到一小时；想要更长的补跑用环境变量调回去。
DEFAULT_MAX_CATCHUP_TICKS = TICKS_PER_GAME_HOUR
#: 上限可调：`LZ_OFFLINE_CATCHUP_MAX_TICKS=86400` 即恢复旧行为，`=0` 关闭补跑。
CATCHUP_MAX_TICKS_ENV = "LZ_OFFLINE_CATCHUP_MAX_TICKS"


def configured_max_ticks() -> int:
    """读环境变量得到补跑上限；缺省用 :data:`DEFAULT_MAX_CATCHUP_TICKS`。

    非法值直接拒绝启动而不是静默取默认——上限配错只会表现为「启动很慢」或
    「世界不演进」，两种都很难在事后归因。
    """
    raw = os.environ.get(CATCHUP_MAX_TICKS_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_MAX_CATCHUP_TICKS
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{CATCHUP_MAX_TICKS_ENV} must be an integer tick count") from exc
    if not 0 < value <= TICKS_PER_GAME_DAY:
        raise ValueError(
            f"{CATCHUP_MAX_TICKS_ENV} must be within (0, {TICKS_PER_GAME_DAY}]: {value}"
        )
    return value


@dataclass(frozen=True)
class OfflineResult:
    advanced_ticks: int
    consumed_seconds: float
    discarded_seconds: float


async def advance_offline(
    loop: TickLoop,
    *,
    offline_seconds: float,
    flush: OfflineFlush,
    max_ticks: int | None = None,
) -> OfflineResult:
    """固定 1x、沿当前时间尺补跑；回调保存每批事件与进度水位。

    小数不足一个 tick 的尾部向下取整；不恢复模型计划、不调用网络/墙钟。
    每批最多 4 实秒与 240 tick，避免时钟先前进而世界被单帧上限截断。
    不调用在线日切内容钩子：离线跨日不做每日健康演进；启动后以补跑结束日
    建立健康基线，不在首次上线日切追补离线天数（第二十轮选项 b）。

    ``max_ticks`` 缺省取 :func:`configured_max_ticks`（环境变量可调，默认
    一个游戏小时，理由见该常量）。
    """
    if isinstance(offline_seconds, bool) or not isinstance(offline_seconds, (int, float)):
        raise TypeError("offline_seconds must be a finite nonnegative number")
    if not math.isfinite(offline_seconds) or offline_seconds < 0:
        raise ValueError("offline_seconds must be a finite nonnegative number")
    if max_ticks is None:
        max_ticks = configured_max_ticks()
    if (
        isinstance(max_ticks, bool)
        or not isinstance(max_ticks, int)
        or not 0 < max_ticks <= TICKS_PER_GAME_DAY
    ):
        raise ValueError("max_ticks must be within one game day")
    if offline_seconds == 0:
        return OfflineResult(0, 0.0, 0.0)
    start_tick = loop.state.tick
    previous_speed = loop.clock.speed
    consumed = 0.0
    loop.clock.set_speed(1.0)
    try:
        while consumed < offline_seconds and loop.state.tick - start_tick < max_ticks:
            remaining_ticks = max_ticks - (loop.state.tick - start_tick)
            rate = loop.clock.ticks_per_real_second()
            dt = min(
                offline_seconds - consumed,
                MAX_CATCHUP_REAL_SECONDS,
                min(_MAX_TICKS_PER_FRAME, remaining_ticks) / rate,
            )
            if dt <= 0:
                break
            loop.advance_frame(dt)
            consumed = min(offline_seconds, consumed + dt)
            capped = loop.state.tick - start_tick >= max_ticks and consumed < offline_seconds
            final = consumed >= offline_seconds or capped
            await flush(loop.drain_events(), consumed, final)
            await asyncio.sleep(0)
    finally:
        loop.clock.set_speed(previous_speed)
    discarded = max(0.0, offline_seconds - consumed)
    if discarded:
        logger.warning(
            "offline.capped",
            requested_seconds=offline_seconds,
            consumed_seconds=consumed,
            discarded_seconds=discarded,
            advanced_ticks=loop.state.tick - start_tick,
            max_ticks=max_ticks,
        )
    return OfflineResult(loop.state.tick - start_tick, consumed, discarded)
