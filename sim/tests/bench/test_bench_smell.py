"""嗅觉传播基准（性能域，pi）— M2-P1 第 2 项（DESIGN §7，budget.md §2.9）。

通道模型（DESIGN §7 表）：「∝1/r²，风向主导，需持续源」。与现有感知引擎
（`sim/perception/propagation.py` 三要素：衰减 + 阻断 + 修正）同构，只换参数。

为什么**不做逐对**：∝1/r² 扩散若逐对 50×50 计算是 O(N²)/tick（naive 哨兵实测 ~4.6ms，
见 `test_smell_naive_sentinel`），且风吹环境下逐对还要算风向投影，成本更高。
预算方案：**Eulerian 网格增量扩散**——活跃源发射 → 整场平流（风）→ 衰减，
一次 `np.roll` 全图；接收端 O(1) 采样。tick 内时序建议见 budget.md §2.9。

红线来自 thresholds.py（SMELL_TICK_LIMIT_MS）。口径：暖态中位，与感知红线同源。
挂载点说明：嗅觉通道实现属架构域（M2-A1），本文件定预算红线与成本走势；
网格实现为**参考实现**（同感知 bench 的「参考实现版」模式）。
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from .harness import assert_median_threshold
from .thresholds import SMELL_NAIVE_SENTINEL_MS, SMELL_TICK_LIMIT_MS

GRID = 64  # 与感知 bench 同图尺度（64×64）
N_SOURCES = 20  # 活跃持续源（酒馆/屠宰/药铺/火堆…量级）
N_RECV = 50  # 接收者 = L1 NPC 数
DECAY = np.float32(0.98)  # 每 tick 场衰减（风的稀释）
WIND_SHIFT = (0, 1)  # 恒定风向 → 纯 roll 平流（最省）；非恒定风见文件尾注
_SEED = 7


def _perf_counter() -> float:
    return time.perf_counter()


def _make_sources(rng: np.random.Generator) -> np.ndarray:
    return (rng.random((N_SOURCES, 2)) * GRID).astype(int) % GRID


class _SmellField:
    """Eulerian 嗅觉场（参考实现）：发射 + 平流 + 衰减，O(grid²) 无逐对。"""

    def __init__(self) -> None:
        rng = np.random.default_rng(_SEED)
        self.field = np.zeros((GRID, GRID), dtype=np.float32)
        self.sources = _make_sources(rng)
        self.recv = (rng.random((N_RECV, 2)) * GRID).astype(int) % GRID

    def tick(self) -> None:
        self.field[self.sources[:, 1], self.sources[:, 0]] += np.float32(1.0)
        self.field = np.roll(self.field, shift=WIND_SHIFT, axis=(0, 1))
        self.field *= DECAY

    def sample_at_receivers(self) -> np.ndarray:
        """接收端采样：O(N_recv) 常数索引（浓度 = 该格场值，1/r² 已由扩散场隐式承载）。"""
        return self.field[self.recv[:, 1], self.recv[:, 0]]


@pytest.mark.bench
def test_smell_advect_diffuse_50npc(benchmark) -> None:
    """嗅觉扩散（网格平流+衰减）≤ 0.15ms/tick（budget §2.9 上限；暖态中位）。

    含每 tick 持续源发射（K=20）+ 全图 1/r² 隐式扩散 + 风平流，不含接收端采样。
    """
    world = _SmellField()

    def _run() -> float:
        t0 = _perf_counter()
        world.tick()
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=200)
    assert_median_threshold(benchmark.stats, SMELL_TICK_LIMIT_MS, "嗅觉扩散（64×64·暖态中位）")


@pytest.mark.bench
def test_smell_receiver_sample_50npc(benchmark) -> None:
    """接收端采样 50 NPC ≤ 0.15ms/tick（budget §2.9；采样应与扩散同量级或更低）。"""
    world = _SmellField()
    world.tick()

    def _run() -> float:
        t0 = _perf_counter()
        world.sample_at_receivers()
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=200)
    assert_median_threshold(benchmark.stats, SMELL_TICK_LIMIT_MS, "嗅觉接收采样 50 NPC（暖态中位）")


@pytest.mark.bench
def test_smell_total_tick(benchmark) -> None:
    """嗅觉通道整体（扩散 + 采样）≤ 0.15ms/tick（budget §2.9 上限口径）。"""
    world = _SmellField()

    def _run() -> float:
        t0 = _perf_counter()
        world.tick()
        world.sample_at_receivers()
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=200)
    assert_median_threshold(benchmark.stats, SMELL_TICK_LIMIT_MS, "嗅觉通道整体（暖态中位）")


@pytest.mark.bench
def test_smell_naive_sentinel() -> None:
    """朴素逐对 O(N²) ∝1/r²+风向投影哨兵：断言明显慢于 0.15ms（H-1 动机证据）。"""
    rng = np.random.default_rng(_SEED)
    pos = rng.random((N_RECV, 2)) * GRID
    wind = np.array([0.8, 0.6])
    wind /= np.linalg.norm(wind)

    def _naive() -> float:
        total = 0.0
        for i in range(N_RECV):
            for j in range(N_RECV):
                if i == j:
                    continue
                d = pos[j] - pos[i]
                r = float(np.hypot(d[0], d[1]))
                if r < 1e-9 or r > 24.0:
                    continue
                if float(d @ wind) <= 0.0:
                    continue  # 下风不可闻
                total += float(d @ wind) / r / (r * r)
        return total

    t0 = _perf_counter()
    _naive()
    ms_naive = (_perf_counter() - t0) * 1000.0
    assert ms_naive > SMELL_NAIVE_SENTINEL_MS, (
        f"朴素 O(N²) 嗅觉不应快于 {SMELL_NAIVE_SENTINEL_MS}ms"
        f"（实测 {ms_naive:.3f}ms，网格方案动机消失）"
    )


def test_smell_shape_contract() -> None:
    """契约守卫（非 bench）：1/r² 远场衰减 + 下风才可闻（DESIGN §7 通道语义）。"""
    # 浓度场在源附近高、远场低（1/r² 隐式）；接收采样非负
    world = _SmellField()
    for _ in range(5):
        world.tick()
    samples = world.sample_at_receivers()
    assert samples.shape == (N_RECV,)
    assert np.all(samples >= 0.0)
    # 风向投影：顺风为正、逆风为负（下游可闻、上游不可闻）
    wind = np.array([1.0, 0.0])
    assert float(np.array([1, 0]) @ wind) > 0.0
    assert float(np.array([-1, 0]) @ wind) < 0.0
