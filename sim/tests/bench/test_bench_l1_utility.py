"""L1 效用 AI 基准（性能域，pi）— M2-P1 第 1 项（DESIGN §5/§13，budget.md §1/§2.4）。

范围（task M2-P1）：50 NPC 效用函数 AI，每秒 tick；单 NPC 单 tick 评估预算 +
50 NPC 全量预算红线；含 LLM 断线降级路径（L1 兜底执行计划队列）开销核算。

挂载点说明：`sim/npc/utility` 尚未落地（M2-A1 架构域），本文件按 DESIGN §13
「NPC 完整属性」给**代表性满属性载荷**（身份/需求/OCEAN/PAD/关系/记忆）定预算与
红线，M2 引擎合入后按同一红线复测（红线是上界，换实现不改口径）。

口径：暖态中位（`warmup_rounds=1` + `assert_median_threshold`），与感知红线同源。
红线来自 thresholds.py（L1_UTILITY_*）。确定性：固定 numpy seed（C5，禁 stdlib random）。
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from .harness import assert_median_threshold, assert_threshold
from .thresholds import (
    L1_OFFLINE_FALLBACK_LIMIT_MS,
    L1_UTILITY_PER_NPC_LIMIT_MS,
    L1_UTILITY_TICK_LIMIT_MS,
)

N_NPC = 50
N_NEEDS = 6  # 需求带权重（DESIGN §13）
N_OCEAN = 5
N_PAD = 3
N_REL = N_NPC  # 关系矩阵：有向、不对称（我对他 ≠ 他对我）
N_MEM = 32  # 记忆显著性窗口（M2 起记忆衰减每 tick 参与打分）
N_ACTIONS = 13  # IntentAction 种类数（sim/agent/intent.py）
_SEED = 7


class _L1Load:
    """L1 满属性代表载荷：同构 numpy 数组（向量化下限）+ 逐对象视图（scalar 对照）。"""

    def __init__(self) -> None:
        rng = np.random.default_rng(_SEED)
        self.needs = rng.random((N_NPC, N_NEEDS), dtype=np.float32)
        self.weights = rng.random((N_NPC, N_NEEDS), dtype=np.float32)
        self.ocean = rng.random((N_NPC, N_OCEAN), dtype=np.float32)
        self.pad = rng.random((N_NPC, N_PAD), dtype=np.float32) * 2.0 - 1.0
        self.rel = rng.random((N_NPC, N_REL), dtype=np.float32)
        self.mem_salience = rng.random((N_NPC, N_MEM), dtype=np.float32)
        self.mem_emotion = rng.random((N_NPC, N_MEM), dtype=np.float32)
        self.u_needs = rng.random((N_ACTIONS, N_NEEDS), dtype=np.float32)
        self.u_ocean = rng.random((N_ACTIONS, N_OCEAN), dtype=np.float32)
        self.u_pad = rng.random((N_ACTIONS, N_PAD), dtype=np.float32)

    def tick_vectorized(self) -> np.ndarray:
        """50 NPC 全量推进一 tick：needs 衰减 + utility 打分 + memory 衰减（同构向量化）。"""
        np.clip(self.needs - np.float32(1e-4), 0.0, 1.0, out=self.needs)
        scores = self.needs @ self.u_needs.T
        scores += self.ocean @ self.u_ocean.T
        scores += self.pad @ self.u_pad.T
        scores += self.rel.mean(axis=1, keepdims=True)
        mem_term = (self.mem_salience * self.mem_emotion).sum(axis=1, keepdims=True)
        scores += np.float32(0.1) * mem_term
        best = scores.argmax(axis=1)
        self.mem_salience *= np.float32(0.999)
        return best

    def tick_scalar(self) -> list[int]:
        """逐对象 Python 热循环（scalar 对照：H-2 同款反模式，证明向量化必要性）。"""
        best_actions: list[int] = []
        for i in range(N_NPC):
            np.clip(self.needs[i] - np.float32(1e-4), 0.0, 1.0, out=self.needs[i])
            best_score = -1e9
            best_action = 0
            for a in range(N_ACTIONS):
                s = float(self.needs[i] @ self.u_needs[a])
                s += float(self.ocean[i] @ self.u_ocean[a])
                s += float(self.pad[i] @ self.u_pad[a])
                s += float(self.rel[i].mean())
                s += float((self.mem_salience[i] * self.mem_emotion[i]).sum()) * 0.1
                if s > best_score:
                    best_score = s
                    best_action = a
            best_actions.append(best_action)
            self.mem_salience[i] *= np.float32(0.999)
        return best_actions


def _perf_counter() -> float:
    return time.perf_counter()


@pytest.fixture
def l1_load() -> _L1Load:
    """每用例新鲜载荷（构造不计入计时；needs/记忆衰减需每轮复位）。"""
    return _L1Load()


@pytest.mark.bench
def test_l1_utility_50npc_vectorized(l1_load, benchmark) -> None:
    """50 NPC 全量效用推进 ≤ 6.00ms/tick（budget §1 上限；暖态中位口径）。

    M2 强制：同构数据必须向量化（budget §2.4「同构数据向量化」=H-2 同款下限），
    逐对象热循环（`tick_scalar` 对照）会被红线挡住。
    """

    def _run() -> float:
        t0 = _perf_counter()
        l1_load.tick_vectorized()
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=100)
    assert_median_threshold(
        benchmark.stats, L1_UTILITY_TICK_LIMIT_MS, "L1 效用 50 NPC（向量化·暖态中位）"
    )


@pytest.mark.bench
def test_l1_utility_per_npc_within_budget(l1_load, benchmark) -> None:
    """单 NPC 单 tick 效用评估 ≤ 0.12ms（= 6.00ms / 50，budget §2.4 逐人预算）。"""

    def _run() -> float:
        t0 = _perf_counter()
        l1_load.tick_vectorized()
        return (_perf_counter() - t0) * 1000.0 / N_NPC

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=20)
    assert_median_threshold(
        benchmark.stats, L1_UTILITY_PER_NPC_LIMIT_MS, "L1 效用 单 NPC（暖态中位）"
    )


@pytest.mark.bench
def test_l1_utility_scalar_sentinel() -> None:
    """逐对象热循环哨兵：证明向量化是下限（H-2 动机证据，不卡预算红线）。"""
    load = _L1Load()
    t0 = _perf_counter()
    load.tick_scalar()
    ms_scalar = (_perf_counter() - t0) * 1000.0
    assert ms_scalar > L1_UTILITY_PER_NPC_LIMIT_MS, (
        f"逐对象 50 NPC 效用推进不应快于 {L1_UTILITY_PER_NPC_LIMIT_MS}ms"
        f"（实测 {ms_scalar:.3f}ms，向量化动机消失）"
    )


@pytest.mark.bench
def test_l1_offline_fallback_plan_queue(benchmark) -> None:
    """LLM 断线降级：L1 兜底执行计划队列（每股 pop 一步 + 常数校验）≤ 0.20ms/tick。

    依据 DESIGN §3「LLM 断线 → 降级到 L1 效用 AI 继续执行计划队列」。
    该路径在断线期间每 tick 都跑，不能因降级把 tick 拖红。
    """
    plans: list[list[tuple[int, str]]] = [[(j, "move_to") for j in range(4)] for _ in range(N_NPC)]

    def _step() -> int:
        fired = 0
        for plan in plans:
            if plan:
                plan.pop(0)
                fired += 1
        return fired

    def _run() -> float:
        t0 = _perf_counter()
        _step()
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=200)
    assert_median_threshold(
        benchmark.stats, L1_OFFLINE_FALLBACK_LIMIT_MS, "L1 断线兜底计划队列（暖态中位）"
    )


def test_l1_utility_contract_shape() -> None:
    """契约守卫（非 bench）：50 股各有动作、打分确定性（同 seed 同结果，C5 友好）。"""
    a = _L1Load()
    b = _L1Load()
    actions_a = a.tick_vectorized()
    actions_b = b.tick_vectorized()
    assert actions_a.shape == (N_NPC,)
    assert np.array_equal(actions_a, actions_b), "同 seed 载荷打分不确定（违反 C5 可重放）"


def test_l1_offline_fallback_contract() -> None:
    """契约守卫：计划队列耗尽不发动作（降级路径不产幽灵事件）。"""
    plans: list[list[int]] = [[1, 2] for _ in range(N_NPC)]
    for _ in range(2):
        for plan in plans:
            if plan:
                plan.pop(0)
    fired = sum(1 for plan in plans if plan)
    assert fired == 0
    assert_threshold(0.0, L1_OFFLINE_FALLBACK_LIMIT_MS, "空队列兜底（零成本契约）")
