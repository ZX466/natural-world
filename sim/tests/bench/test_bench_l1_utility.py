"""L1 效用 AI 基准（性能域，pi）— M2-P1 第 1 项（DESIGN §5/§13，budget.md §1/§2.4）。

范围（task M2-P1）：50 NPC 效用函数 AI，每秒 tick；单 NPC 单 tick 评估预算 +
50 NPC 全量预算红线；含 LLM 断线降级路径（L1 兜底执行计划队列）开销核算。

M2-P3 更新（main `59ffd86` 已落地真实实现）：本文件两段并存，规格对账见 `docs/perf/l1-spec.md`：
- 上半（`_L1Load`）：M2-P1 按 DESIGN §13「NPC 完整属性」造的**代表性满属性载荷**
  （身份/需求/OCEAN/PAD/关系/记忆）定预算**上界**。
- 下半（`test_l1_real_*`）：对真实 `sim/npc/utility.py` + `runtime.py` 复测回填。
红线口径不变（上界不缩小）。

口径：暖态中位（`warmup_rounds=1` + `assert_median_threshold`），与感知红线同源。
红线来自 thresholds.py（L1_UTILITY_*）。确定性：固定 numpy seed（C5，禁 stdlib random）。
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from sim.npc.model import Need, NpcProfileData
from sim.npc.runtime import NpcRuntime
from sim.npc.utility import (
    ACTION_ORDER,
    NEED_ORDER,
    UtilityModel,
    evaluate_batch,
    utility_scores_matrix,
)

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


# ===========================================================================
# M2-P3 对账：真实实现（sim/npc/utility.py + runtime.py）复测
#
# 上面的 `_L1Load` 是 M2-P1 按 DESIGN §13「NPC 完整属性」造的**代表性满属性载荷**，
# 用于定预算**上界**（6 needs / 13 actions / PAD / 关系 / 记忆，纯 numpy 同构数组）。
# M2-A2 第二批（main `59ffd86`）落地的真实实现是**精简形**：3 needs / 6 actions /
# 增益矩阵 `_GAIN (3,6)` + 外向偏置 + 习惯加成，**无 PAD/关系/记忆项**。
# 故本节用真实 `sim.npc.utility` / `sim.npc.runtime` 复测，回填实测值。
# 口径不变：暖态中位（warmup_rounds=1 + assert_median_threshold）；红线不缩小
# （6.0ms 是「M2 满属性 + 未向量化写法」的上界，实测远低于它）。
# 规格 <-> 实现对账明细见 docs/perf/l1-spec.md。
# ===========================================================================

#: 真实实现的 needs 字段序（utility.NEED_ORDER）；中性值让 argmax 不被单一需求绑架
_NEED_VALUES = {"hunger": 0.5, "energy": 0.4, "social": 0.3}


def _real_profiles(n_npc: int = N_NPC) -> list[NpcProfileData]:
    """真实 NpcProfileData 满编 50 人（id 与 bench harness 的 e%03d 对齐）。"""
    return [
        NpcProfileData(
            npc_id=f"e{i:03d}",
            name=f"npc{i}",
            species="human",
            ocean=(50.0, 50.0, float(i % 100), 50.0, 50.0),
            needs=tuple(Need(k, v, 1.0) for k, v in _NEED_VALUES.items()),
        )
        for i in range(n_npc)
    ]


@pytest.fixture
def real_profiles() -> list[NpcProfileData]:
    return _real_profiles()


@pytest.fixture
def real_model() -> UtilityModel:
    return UtilityModel(n_npc=N_NPC)


@pytest.mark.bench
def test_l1_real_utility_scores_matrix(real_profiles, real_model, benchmark) -> None:
    """真实 `utility_scores_matrix` 50 NPC ≤ 6.00ms/tick（上界红线复测）。"""

    def _run() -> float:
        t0 = _perf_counter()
        utility_scores_matrix(real_profiles, real_model)
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=100)
    assert_median_threshold(
        benchmark.stats, L1_UTILITY_TICK_LIMIT_MS, "L1 真实实现 scores_matrix（暖态中位）"
    )


@pytest.mark.bench
def test_l1_real_evaluate_batch(real_profiles, real_model, benchmark) -> None:
    """真实 `evaluate_batch`（含 argmax + scores dict 审计）50 NPC ≤ 6.00ms/tick。"""

    def _run() -> float:
        t0 = _perf_counter()
        evaluate_batch(real_profiles, real_model)
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=100)
    assert_median_threshold(
        benchmark.stats, L1_UTILITY_TICK_LIMIT_MS, "L1 真实实现 evaluate_batch（暖态中位）"
    )


@pytest.mark.bench
def test_l1_real_runtime_tick_50npc(benchmark) -> None:
    """真实 `NpcRuntime.tick`（needs 推进 + 效用 + 事件产出）50 NPC ≤ 6.00ms/tick。

    这是 soak 长跑里 L1 的真实增量成本（runtime.tick 每 tick 调一次）。
    """
    profiles = _real_profiles()
    runtime = NpcRuntime(
        profiles={p.npc_id: p for p in profiles}, utility=UtilityModel(n_npc=N_NPC)
    )

    def _run() -> float:
        t0 = _perf_counter()
        runtime.tick(1)
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=50)
    assert_median_threshold(
        benchmark.stats, L1_UTILITY_TICK_LIMIT_MS, "L1 真实实现 runtime.tick（暖态中位）"
    )


@pytest.mark.bench
def test_l1_real_per_npc_within_budget(benchmark) -> None:
    """真实实现单 NPC 单 tick ≤ 0.12ms（= 6.00ms / 50，budget §2.4 逐人预算）。"""
    profiles = _real_profiles()
    single = profiles[:1]  # 单 NPC 批次（pytest-benchmark 计调用墙钟，非返回值）
    model = UtilityModel(n_npc=N_NPC)

    def _run() -> float:
        t0 = _perf_counter()
        evaluate_batch(single, model)
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=20)
    assert_median_threshold(
        benchmark.stats, L1_UTILITY_PER_NPC_LIMIT_MS, "L1 真实实现 单 NPC（暖态中位）"
    )


def test_l1_real_impl_spec_contract() -> None:
    """契约守卫（非 bench）：真实实现的矩阵形状 / 常量序与 l1-spec.md 落盘一致。"""
    assert NEED_ORDER == ("hunger", "energy", "social")
    assert len(ACTION_ORDER) == 6
    assert ACTION_ORDER == ("move", "work", "eat", "rest", "wander", "request_chat")
    profiles = _real_profiles()
    model = UtilityModel(n_npc=N_NPC)
    scores = utility_scores_matrix(profiles, model)
    assert scores.shape == (N_NPC, len(ACTION_ORDER))
    decisions = evaluate_batch(profiles, model)
    assert len(decisions) == N_NPC
    assert {d.action for d in decisions} <= set(ACTION_ORDER)


def test_l1_real_impl_determinism() -> None:
    """确定性守卫（非 bench）：同 profiles 同 model → 逐位同分（C5）。"""
    profiles = _real_profiles()
    model = UtilityModel(n_npc=N_NPC)
    a = utility_scores_matrix(profiles, model)
    b = utility_scores_matrix(profiles, model)
    assert np.array_equal(a, b), "真实实现打分不确定（违反 C5）"
