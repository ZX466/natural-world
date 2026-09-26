"""T5 golden 驱动器（骨架 · M4-C3）——有界虚拟时钟跑帧 + 逐日窗口取数。

形态依据：DESIGN §16 T5（10 种子 × 10 游戏日 · 断言宏观结果）+ §10 时间锁定
（1 tick = 1 游戏秒，1x = 60 tick/s）；帧序对齐生产驱动
`sim/api/ws.py::run_world_driver`（advance_frame → drain_delta → drain_events
→ on_flush → on_day_switch），但有**两处 golden 专用差异**：

1. **虚拟时钟**：生产驱动喂真实 dt（1 游戏日 = 24 真实分钟 → 10 游戏日 = 4 小时真实
   时间，不可进自动化验收）。本驱动按固定 `frame_s` 喂帧，10 游戏日 = 864,000 tick
   纯计算推进；runtime 量级见 `docs/arch/t5-golden-scaffold.md` §4。
2. **有界**：生产驱动是 `while True` 常驻循环（WS 网关）；本驱动跑满 `ticks` 即返回，
   并把逐日窗口 / 事件计数交给断言组。

**本模块不含任何断言**（任务卡纪律：断言组等 D 批行为链落地后按脚手架填）。
复用既有设施不新造：`sim.tests.bench.harness.make_loop` 建世界、soak 的
`make_mock_feeder` / `make_l1_feeder` 喂动作、`sim.core.calendar.game_time` 判日切。
耦合提示：`sim/tests/bench/*` 属性能域（pi）文件，本模块只 import 不改。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from sim.core.calendar import game_time
from sim.core.events import WorldEvent
from sim.core.tick import TickLoop

from .seeds import TICKS_PER_GAME_DAY

DEFAULT_FRAME_S = 1.0 / 60.0  # 1x = 60 tick/s ⇒ 每帧 1 tick = 1 游戏秒


@dataclass(frozen=True)
class DayWindow:
    """一个游戏日的取数窗口（断言组的最小取数单位）。"""

    day: int
    start_tick: int
    end_tick: int
    n_events: int
    mean_tick_ms: float


@dataclass
class GoldenRun:
    """一次 golden 跑的结果容器——**只有数，没有断言**。"""

    seed: int
    ticks_requested: int
    ticks_run: int = 0
    days_covered: int = 0
    total_events: int = 0
    total_tiles_changed: int = 0
    windows: list[DayWindow] = field(default_factory=list)
    wall_s: float = 0.0

    def mean_tick_ms(self) -> float:
        """全程每 tick 均耗时（runtime 估算依据：864,000 tick × 本值 = 单种子墙钟）。"""
        return (self.wall_s * 1000.0 / self.ticks_run) if self.ticks_run else 0.0


def smoke_loop(n_entities: int = 10, world_seed: int = 7) -> TickLoop:
    """建一个 golden 用世界。

    seed 走 `harness.make_state(world_seed=...)`（`make_loop` 不收 seed 参数，故按其
    4 行构造法就地拼装：GameClock + build_default_bus + make_state + TickContext），
    **不修改性能域文件**。world/seed 同源保证 C5 可重放。
    """
    from sim.core.clock import GameClock
    from sim.core.world import TickContext, build_default_bus
    from sim.tests.bench.harness import make_state

    return TickLoop(
        clock=GameClock(speed=1.0),
        bus=build_default_bus(),
        state=make_state(n_entities, world_seed=world_seed),
        context=TickContext(),
    )


def mock_feeder(grid_w: int = 64, grid_h: int = 64) -> Callable[[TickLoop], int]:
    """确定性动作喂给器（复用 soak 的 mock feeder：50 NPC 持续走动负载保真）。"""
    from sim.tests.bench.soak import make_mock_feeder

    return make_mock_feeder(grid_w=grid_w, grid_h=grid_h)


def run_golden(
    loop: TickLoop,
    ticks: int,
    *,
    feeder: Callable[[TickLoop], int] | None = None,
    frame_s: float = DEFAULT_FRAME_S,
    drain: bool = True,
    on_events: Callable[[list[WorldEvent]], None] | None = None,
    seed: int = 0,
) -> GoldenRun:
    """有界虚拟时钟跑 `ticks` 个 tick（帧序对齐 run_world_driver，省略广播/落库）。

    - 每帧：`feeder(loop)` → `advance_frame(frame_s)` → `drain_delta()` → `drain_events()`
      （生产驱动里 on_flush/on_day_switch 之后的广播步与 golden 无关，略）。
    - `drain=True` 每帧清事件队列（与生产一致，保持内存有界）；关掉则事件只累积不消费，
      仅用于调试。
    - 日切判定用 `game_time(state.tick).day` 的**跨越判定**（prev_day != new_day 时逐日各记一次），
      与 `run_world_driver` 同口径——帧驱动一帧推进 0..N tick，等值点判定会整天丢失。
    """
    run = GoldenRun(seed=seed, ticks_requested=ticks)
    wall0 = time.perf_counter()
    day = game_time(loop.state.tick).day
    win_start = loop.state.tick
    win_events = 0
    win_samples: list[float] = []
    for _ in range(ticks):
        if feeder is not None:
            feeder(loop)
        t0 = time.perf_counter()
        loop.advance_frame(frame_s)
        win_samples.append((time.perf_counter() - t0) * 1000.0)
        run.ticks_run += 1
        events: list[WorldEvent] = []
        if drain:
            loop.drain_delta()
            events = loop.drain_events()
        if events:
            run.total_events += len(events)
            win_events += len(events)
            run.total_tiles_changed += sum(
                1 for e in events if e.event_type.value == "tile.changed"
            )
            if on_events is not None:
                on_events(events)
        new_day = game_time(loop.state.tick).day
        if new_day != day:
            for d in range(day, new_day):
                run.windows.append(
                    DayWindow(
                        day=d,
                        start_tick=win_start,
                        end_tick=loop.state.tick,
                        n_events=win_events,
                        mean_tick_ms=(sum(win_samples) / len(win_samples)) if win_samples else 0.0,
                    )
                )
                win_events = 0
                win_samples = []
            win_start = loop.state.tick
            run.days_covered += new_day - day
            day = new_day
    if win_samples:
        run.windows.append(
            DayWindow(
                day=day,
                start_tick=win_start,
                end_tick=loop.state.tick,
                n_events=win_events,
                mean_tick_ms=sum(win_samples) / len(win_samples),
            )
        )
    run.wall_s = time.perf_counter() - wall0
    return run


def ticks_for_days(days: int) -> int:
    """days 个游戏日的 tick 数（10 游戏日 = 864,000）。"""
    return TICKS_PER_GAME_DAY * days
