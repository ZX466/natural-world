"""基准 harness（性能域，pi）— 钟表/世界/tick 装配与计时辅助。

与 conftest.py 区分：这里是纯辅助函数（可被用例直接 import），
conftest.py 只暴露 pytest fixture。
"""

from __future__ import annotations

import time

from sim.core.clock import GameClock
from sim.core.tick import TickLoop
from sim.core.world import EntityState, EventBus, TickContext, WorldState, build_default_bus

# 默认帧长：1x = 60 tick/s → 每帧喂 1/60 真实秒 = 1 tick
DEFAULT_FRAME_S = 1.0 / 60.0


def make_state(
    n_entities: int = 50,
    world_seed: int = 7,
    grid_w: int = 64,
    grid_h: int = 64,
) -> WorldState:
    """构造 M0 世界状态：n_entities 个静止实体（M2 前以位置为主）。"""
    entities: dict[str, EntityState] = {}
    for i in range(n_entities):
        entities[f"e{i:03d}"] = EntityState(
            entity_id=f"e{i:03d}",
            pos=(i % grid_w, (i // grid_w) % grid_h),
        )
    return WorldState(world_seed=world_seed, tick=0, entities=entities)


def make_loop(n_entities: int = 50, bus: EventBus | None = None) -> TickLoop:
    """构造可跑的内核 loop：真实 GameClock + 默认事件总线 + N 实体世界。"""
    return TickLoop(
        clock=GameClock(speed=1.0),
        bus=bus if bus is not None else build_default_bus(),
        state=make_state(n_entities),
        context=TickContext(),
    )


def run_frames(loop: TickLoop, frames: int, dt: float = DEFAULT_FRAME_S) -> tuple[int, float]:
    """累计推进 frames 帧，返回 (推进总 tick 数, 总耗时秒)。"""
    t0 = time.perf_counter()
    total = 0
    for _ in range(frames):
        total += loop.advance_frame(dt)
    elapsed = time.perf_counter() - t0
    return total, elapsed


def ms_per_tick(loop: TickLoop, frames: int = 600, dt: float = DEFAULT_FRAME_S) -> float:
    """跑 frames 帧，返回每 tick 平均毫秒。600 帧 = 600 tick = 10 真实秒 @1x。"""
    ticks, elapsed = run_frames(loop, frames, dt)
    if ticks == 0:
        return float("inf")
    return (elapsed / ticks) * 1000.0


def assert_threshold(measured_ms: float, limit_ms: float, label: str) -> None:
    """阈值断言：失败时输出实测值与阈值的差值。"""
    assert measured_ms <= limit_ms, (
        f"{label} 超阈值: 实测 {measured_ms:.3f}ms > 上限 {limit_ms:.3f}ms"
        f"（差值 {(measured_ms - limit_ms):.3f}ms）"
    )
