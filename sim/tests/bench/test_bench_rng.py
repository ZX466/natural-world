"""RNG 基准（性能域，pi）— sim.core.rng.RngRegistry 分流 RNG。

回归阈值：RNG_1M_DRAWS_LIMIT_MS = 300ms 警戒线（bench-plan.md §3；budget.md §2.2）；
真预算口径为「每 tick RNG 成本（L1 规模 200 draws）≤ 0.10ms」（RNG_TICK_LIMIT_MS）。
口径：经 RngRegistry.generator(stream, cache) 取 numpy Generator（PCG64），
在单一 stream 上抽 1M 个 float，测耗时。cache 由调用方持有并跨 tick 复用
（m0-core §2：抽签进度保存在 Generator 内，不落快照）。
"""

from __future__ import annotations

import numpy as np
import pytest

from sim.core.rng import RngRegistry

from .harness import assert_median_threshold, assert_threshold
from .thresholds import RNG_1M_DRAWS_LIMIT_MS, RNG_TICK_LIMIT_MS

STREAM = "bench.draw"
WORLD_SEED = 7
DRAWS = 1_000_000


def _draw_1m() -> float:
    """抽 1M 个 float，返回耗时毫秒。模拟业务经分流 RNG 连续抽签。"""
    reg = RngRegistry(world_seed=WORLD_SEED)
    cache: dict[str, np.random.Generator] = {}
    gen = reg.generator(STREAM, cache)

    start = _perf_counter()
    for _ in range(DRAWS):
        gen.random()
    return (_perf_counter() - start) * 1000.0


def _draw_1m_vectorized() -> float:
    """向量化对比（L0 千人级批量推进场景）：一次性 random(size=1M)。"""
    reg = RngRegistry(world_seed=WORLD_SEED)
    cache: dict[str, np.random.Generator] = {}
    gen = reg.generator(STREAM, cache)

    start = _perf_counter()
    gen.random(size=DRAWS)
    return (_perf_counter() - start) * 1000.0


def _perf_counter() -> float:
    import time

    return time.perf_counter()


@pytest.mark.bench
def test_rng_per_tick_cost_l1_scale(benchmark) -> None:
    """每 tick RNG 成本（L1 规模：50 NPC × 4 draws/tick = 200 draws）≤ 0.10ms。

    —— 这是 RNG 预算（budget §1/§2.2 上限 0.10ms）的真正语义口径，
    聚合 1M draws 只是警戒线。若超限，回退到向量化批量抽取（budget §2.2）。
    """
    reg = RngRegistry(world_seed=WORLD_SEED)
    cache: dict[str, np.random.Generator] = {}
    gen = reg.generator(STREAM, cache)

    def _run() -> float:
        start = _perf_counter()
        for _ in range(200):  # 50 NPC × 4 draws
            gen.random()
        return (_perf_counter() - start) * 1000.0

    benchmark.pedantic(_run, rounds=10, iterations=1)
    assert_median_threshold(
        benchmark.stats, RNG_TICK_LIMIT_MS, "RNG 每 tick（L1 规模 200 draws·中位）"
    )


@pytest.mark.bench
def test_rng_1m_draws_per_call(benchmark) -> None:
    """逐调用抽 1M 次（模拟 50 NPC × 多次抽签的 L1 场景）。

    聚合量纲警戒线 ≤300ms（实测逐调用 219ms）；真预算见 RNG_TICK_LIMIT_MS。
    """
    benchmark.pedantic(_draw_1m, rounds=7, iterations=1)
    assert_median_threshold(benchmark.stats, RNG_1M_DRAWS_LIMIT_MS, "RNG 1M draws（逐调用·中位）")


@pytest.mark.bench
def test_rng_1m_draws_vectorized(benchmark) -> None:
    """向量化对比（L0 批量推进）：1M draws 应 ≤300ms（实测 2.4ms）。"""
    measured = benchmark.pedantic(_draw_1m_vectorized, rounds=5, iterations=1)
    assert_threshold(measured, RNG_1M_DRAWS_LIMIT_MS, "RNG 1M draws（向量化）")


def test_rng_deterministic_stream_contract() -> None:
    """契约守卫（T1 级）：同 seed 同 stream → 同序列；cache 跨调用复用保抽签进度。"""
    reg = RngRegistry(world_seed=WORLD_SEED)
    # 同 seed、同 stream、全新 cache → 新 generator，首抽必同（确定性）
    g_fresh1 = reg.generator("a", {})
    g_fresh2 = reg.generator("a", {})
    assert g_fresh1.random() == g_fresh2.random()
    # 复用同一 cache → 同一 Generator 实例（抽签进度在实例内推进，m0-core §2）
    cache: dict[str, np.random.Generator] = {}
    g1 = reg.generator("a", cache)
    d1 = g1.random()
    d2 = g1.random()
    g1b = reg.generator("a", cache)  # 同一 cache → 同一实例
    assert g1b is g1  # 身份同一：进度连续，不重抽、不回退
    assert g1b.random() != d2  # 第 3 抽 ≠ 第 2 抽（序列在推进）
    # 全新 cache → 新实例，但同 seed 同 stream 首抽确定（重放一致）
    g_fresh = reg.generator("a", {})
    assert g_fresh.random() == d1


def test_rng_reseed_changes_stream() -> None:
    """熵注入：reseed 后重新生成，同 ent 材料 → 同结果（C5 可重放）。"""
    reg = RngRegistry(world_seed=WORLD_SEED)
    reg2 = reg.reseed("a", b"\x00" * 16)
    g_old = reg.generator("a", {})
    g_new = reg2.generator("a", {})
    d_old = g_old.random()
    d_new = g_new.random()
    assert d_old != d_new  # 熵注入改变了抽签序列
    # 重放同一材料 → 一致的抽签序列（首抽必同）
    reg2b = reg.reseed("a", b"\x00" * 16)
    g_new2 = reg2b.generator("a", {})
    assert g_new2.random() == d_new
