"""基准 harness（性能域，pi）— 钟表/世界/tick 装配与计时辅助。

与 conftest.py 区分：这里是纯辅助函数（可被用例直接 import），
conftest.py 只暴露 pytest fixture。
M2-P6：`assert_*` 带 **advisory 门**（`PI_BENCH_ADVISORY=1` → 越线只记录不断断言），
见 `assert_threshold` docstring 与 test_bench_advisory_gate.py。
"""

from __future__ import annotations

import os
import time

import structlog

from sim.core.clock import GameClock
from sim.core.tick import TickLoop
from sim.core.world import EntityState, EventBus, TickContext, WorldState, build_default_bus

logger = structlog.get_logger(__name__)

#: advisory 门 env（M2-P6，Claude 裁决 1）：置 "1" 时 bench 越线只记录不失败。
#: nightly（共享 runner）传 "1"；定标机/本机缺省 = 硬断言。仅 "1" 视为开。
ADVISORY_ENV = "PI_BENCH_ADVISORY"

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


def advisory_mode() -> bool:
    """读取 advisory 门状态（调用时读 env，测试可 monkeypatch 切换）。"""
    return os.environ.get(ADVISORY_ENV) == "1"


def assert_threshold(measured_ms: float, limit_ms: float, label: str) -> bool:
    """阈值断言：失败时输出实测值与阈值的差值。

    M2-P6（Claude 裁决 1）：**advisory 门**——`PI_BENCH_ADVISORY=1` 时越线不失败，
    只 warning 记录并返回 True（= 越线且仅记录）。动因：共享 4 核 runner（nightly
    ubuntu-latest）微基准边缘越线 2-9% 属调度噪声；bench-plan §0 原意即「归档 +
    相对基线漂移」，硬断言只留定标机（本机）。采集逻辑零改动——门只决定断不断言。
    返回 True/False = 是否越线（advisory 时可供上层汇总；否则越线直接 AssertionError）。
    """
    if measured_ms <= limit_ms:
        return False
    if advisory_mode():
        logger.warning(
            "bench.advisory.threshold_exceeded",
            label=label,
            measured_ms=round(measured_ms, 3),
            limit_ms=limit_ms,
            delta_ms=round(measured_ms - limit_ms, 3),
        )
        return True
    raise AssertionError(
        f"{label} 超阈值: 实测 {measured_ms:.3f}ms > 上限 {limit_ms:.3f}ms"
        f"（差值 {(measured_ms - limit_ms):.3f}ms）"
    )


def assert_median_threshold(meta: object, limit_ms: float, label: str) -> bool:
    """中位口径阈值断言（抗单轮离群）。

    meta 为 pytest-benchmark 的 `benchmark.stats`（Metadata 对象）；
    真正统计量在其 `.stats` 属性（Stats：median/mean 单位为**秒**）。
    用于热敏感项：首轮/偶发离群会把 mean 拉过红线（感知 LOS 冷启动、RNG GC 抖动），
    稳态由 median 反映（bench-plan §2「至少 3 轮取中位」的落地）。仍打印 mean 作参考。
    advisory 门同 `assert_threshold`（M2-P6 裁决 1）：见其 docstring。
    """
    stats = meta.stats  # type: ignore[attr-defined]
    median_ms = stats.median * 1000.0
    mean_ms = stats.mean * 1000.0
    if median_ms <= limit_ms:
        return False
    if advisory_mode():
        logger.warning(
            "bench.advisory.median_exceeded",
            label=label,
            median_ms=round(median_ms, 3),
            mean_ms=round(mean_ms, 3),
            limit_ms=limit_ms,
            delta_ms=round(median_ms - limit_ms, 3),
        )
        return True
    raise AssertionError(
        f"{label} 中位超阈值: median {median_ms:.3f}ms > 上限 {limit_ms:.3f}ms"
        f"（差值 {(median_ms - limit_ms):.3f}ms；mean {mean_ms:.3f}ms 仅参考）"
    )
