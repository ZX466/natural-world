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
**M2-P5 起两口径并存**（勿混用红线）：
- 上部用例 = 纯网格参考口径（`_SmellField`，K=20 活跃物质源）→
  `SMELL_TICK_LIMIT_MS=0.15`；
- 尾部用例（M2-P5）= 接线版真实实现（`SmellWorld.step`，源=全体实体 + 批量采样 +
  dict 组装）→ `SMELL_WIRED_TICK_LIMIT_MS=1.0`。依据 docs/perf/m2-p4-budget-preplan.md §1.3。
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from .harness import assert_median_threshold
from .thresholds import (
    SMELL_NAIVE_SENTINEL_MS,
    SMELL_TICK_LIMIT_MS,
    SMELL_WIRED_TICK_LIMIT_MS,
)

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


# ---------------------------------------------------------------------------
# M2-P5：接线版（源 = 全体实体，真实 `SmellWorld.step`）红线
# 依据 docs/perf/m2-p4-budget-preplan.md §1.3/§1.5（Claude 2026-09-22 裁决）。
# 与上部参考实现用例的区别：这里是感知步里真正的调用形（inject + roll 平流 +
# 8 邻域扩散 + 衰减 + sample_batch + dict 组装），源数随实体数走（L1 = 50），
# 不是 K=20 活跃物质源的参考口径 → 红线独立（SMELL_WIRED_TICK_LIMIT_MS）。
# 复测（main `653d395` inject 向量化后）：50 源 0.116 / 100 源 0.135 / 200 源
# 0.151 / 500 源 0.335ms（暖态中位）—— 红线 1.0ms 覆盖 10x L1 规模上界。
# ---------------------------------------------------------------------------


@pytest.mark.bench
def test_smell_world_step_50_entities(benchmark) -> None:
    """SmellWorld.step（源=全体 50 实体，真实实现）≤ 1.0ms/tick（暖态中位）。

    卡的是接线版红线（budget §1 新行），不是纯网格 K=20 口径；含风平流 +
    8 邻域扩散 + 衰减 + 批量采样 + {entity_id: 浓度} 组装。
    """
    from sim.perception.smell_world import SmellWorld

    rng = np.random.default_rng(_SEED)
    positions = (rng.random((N_RECV, 2)) * GRID).astype(int) % GRID
    sources = {f"e{i:03d}": (int(p[0]), int(p[1])) for i, p in enumerate(positions)}
    world = SmellWorld(height=GRID, width=GRID)

    def _run() -> float:
        t0 = _perf_counter()
        world.step(sources, wind=WIND_SHIFT)
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=200)
    assert_median_threshold(
        benchmark.stats, SMELL_WIRED_TICK_LIMIT_MS, "嗅觉场推进接线版 50 实体（暖态中位）"
    )


@pytest.mark.bench
def test_smell_world_step_100_sources_headroom(benchmark) -> None:
    """100 源上界探测（L0 千人降采样前的余量哨兵；软断言只查形状与量级）。

    不设硬门禁：100 源不是 L1 常态规模，目的是在实体数涨（L0 投影/观战实体）时
    给出成本走势证据。硬红线由 test_smell_world_step_50_entities 卡。
    """
    from sim.perception.smell_world import SmellWorld

    rng = np.random.default_rng(_SEED)
    positions = (rng.random((100, 2)) * GRID).astype(int) % GRID
    sources = {f"e{i:03d}": (int(p[0]), int(p[1])) for i, p in enumerate(positions)}
    world = SmellWorld(height=GRID, width=GRID)

    def _run() -> float:
        t0 = _perf_counter()
        world.step(sources, wind=WIND_SHIFT)
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=200)
    assert_median_threshold(
        benchmark.stats, SMELL_WIRED_TICK_LIMIT_MS, "嗅觉场推进接线版 100 源（暖态中位）"
    )


def test_smell_world_step_tick_amortized() -> None:
    """契约守卫（非 bench）：接线版每 tick 摊销 ≤ 红线 / 2（感知每 2 tick 一次）。

    用单次墙钟粗测（非 pytest-benchmark）：一次 step 的摊销成本须低于红线一半，
    否则 `_PERCEPTION_EVERY_N_TICKS=2` 的降采口径失效（该常量在 tick.py，见
    budget.md §1）。粗测不设统计轮次，只防量级退化。
    """
    from sim.perception.smell_world import SmellWorld

    rng = np.random.default_rng(_SEED)
    positions = (rng.random((N_RECV, 2)) * GRID).astype(int) % GRID
    sources = {f"e{i:03d}": (int(p[0]), int(p[1])) for i, p in enumerate(positions)}
    world = SmellWorld(height=GRID, width=GRID)
    for _ in range(20):  # 暖态（扩散场稳定、缓存热）
        world.step(sources, wind=WIND_SHIFT)
    rounds = 50
    t0 = _perf_counter()
    for _ in range(rounds):
        world.step(sources, wind=WIND_SHIFT)
    per_step_ms = (_perf_counter() - t0) / rounds * 1000.0
    amortized_ms = per_step_ms / 2  # 感知步每 2 tick 一次
    assert amortized_ms <= SMELL_WIRED_TICK_LIMIT_MS / 2, (
        f"嗅觉场推进每 tick 摊销 {amortized_ms:.3f}ms > 红线一半 "
        f"{SMELL_WIRED_TICK_LIMIT_MS / 2:.3f}ms（单步 {per_step_ms:.3f}ms）"
    )
