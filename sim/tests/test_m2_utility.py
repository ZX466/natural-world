"""M2-A2 第二批：schedule 日程档 + utility 向量化 + runtime 装配（m2-npc-cognition §1/§2）。

T1 断言：秒级，无 LLM，随 `-m "not bench"` 全量跑。
pi 红线（thresholds.py）：50 NPC 效用推进 ≤ 6.0ms/tick、单 NPC ≤ 0.12ms——
utility 用与 bench 原型同构的 numpy 矩阵（确定性同 seed 同结果，C5）。
"""

from __future__ import annotations

import numpy as np
import pytest

from sim.core.calendar import phase_of_day
from sim.core.events import EventKind
from sim.npc.actions import ACTION_WHITELIST
from sim.npc.model import Need, NpcProfileData
from sim.npc.runtime import NpcRuntime
from sim.npc.schedule import current_slot
from sim.npc.utility import (
    UtilityDecision,
    UtilityModel,
    evaluate_batch,
    utility_scores_matrix,
)

# ---------------------------------------------------------------------------
# schedule.py — 日程档（§1.1：按 tick 派生当前应做的事，不做计划重排）
# ---------------------------------------------------------------------------


class TestSchedule:
    def test_slot_pure_by_tick(self) -> None:
        # 同 tick 同档（纯函数，可重放）
        assert current_slot(100) == current_slot(100)

    def test_night_is_rest(self) -> None:
        # 深夜档 → rest（作息：夜里休息）
        tick = 23 * 3_600  # 23:00
        assert current_slot(tick).action == "rest"

    def test_day_is_work(self) -> None:
        tick = 10 * 3_600  # 10:00 白天
        assert current_slot(tick).action == "work"

    def test_slot_is_frozen(self) -> None:
        s = current_slot(0)
        with pytest.raises((AttributeError, TypeError)):
            s.action = "eat"  # type: ignore[misc]

    def test_phase_of_day_consistent(self) -> None:
        # schedule 与历法同源：档位映射覆盖全相位
        for tick in (0, 6 * 3_600, 12 * 3_600, 18 * 3_600):
            slot = current_slot(tick)
            assert slot.action in ACTION_WHITELIST
            assert phase_of_day(tick) is not None


# ---------------------------------------------------------------------------
# utility.py — 向量化打分（§2.1；对齐 pi bench 原型 _L1Load.tick_vectorized）
# ---------------------------------------------------------------------------


def _profile(i: int, needs: tuple[Need, ...]) -> NpcProfileData:
    return NpcProfileData(
        npc_id=f"npc_{i:02d}",
        name=f"张三{i}",
        needs=needs,
        ocean=(55.0, 60.0, 45.0, 50.0, 40.0),
        pad=(0.1, 0.2, 0.0),
    )


class TestUtilityScoring:
    def test_matrix_shape_50x_actions(self) -> None:
        # Arrange: 50 NPC，每 NPC 3 需求
        profiles = [
            _profile(i, (Need("hunger", 0.5, 2.0), Need("energy", 0.3, 1.0))) for i in range(50)
        ]
        model = UtilityModel(n_npc=50)

        # Act
        scores = utility_scores_matrix(profiles, model)

        # Assert: (50, n_actions) 矩阵，n_actions = 白名单动作数
        assert scores.shape == (50, len(ACTION_WHITELIST))

    def test_hungry_npc_prefers_eat(self) -> None:
        # Arrange: 高饥饿 NPC 的 eat 得分应显著高于 rest
        hungry = _profile(0, (Need("hunger", 0.9, 2.0), Need("energy", 0.1, 1.0)))
        model = UtilityModel(n_npc=1)

        # Act
        scores = utility_scores_matrix([hungry], model)

        # Assert
        eat_i = model.action_index["eat"]
        rest_i = model.action_index["rest"]
        assert scores[0, eat_i] > scores[0, rest_i]

    def test_deterministic_same_seed(self) -> None:
        # C5：同 seed 两次评估逐位一致
        profiles = [_profile(i, (Need("hunger", 0.6, 1.5),)) for i in range(10)]
        m1, m2 = UtilityModel(n_npc=10, seed=7), UtilityModel(n_npc=10, seed=7)
        assert np.array_equal(
            utility_scores_matrix(profiles, m1), utility_scores_matrix(profiles, m2)
        )

    def test_weighted_needs_dominates(self) -> None:
        # 权重放大紧迫度：weight=2 的饥饿 vs weight=1 的饥饿，eat 得分更高
        low = _profile(0, (Need("hunger", 0.9, 1.0),))
        high = _profile(1, (Need("hunger", 0.9, 3.0),))
        model = UtilityModel(n_npc=2)
        scores = utility_scores_matrix([low, high], model)
        assert scores[1, model.action_index["eat"]] > scores[0, model.action_index["eat"]]


class TestEvaluateBatch:
    def test_decision_whitelisted(self) -> None:
        profiles = [_profile(i, (Need("hunger", 0.8, 2.0),)) for i in range(5)]
        decisions = evaluate_batch(profiles, UtilityModel(n_npc=5, seed=3))
        assert len(decisions) == 5
        for d in decisions:
            assert isinstance(d, UtilityDecision)
            assert d.action in ACTION_WHITELIST

    def test_scores_carried_for_audit(self) -> None:
        # scores 进 NPC_ACT payload params（审计）；action_id 是白名单动作
        profiles = [_profile(0, (Need("hunger", 0.95, 2.0),))]
        d = evaluate_batch(profiles, UtilityModel(n_npc=1, seed=3))[0]
        assert set(d.scores.keys()) == set(ACTION_WHITELIST)
        assert d.target == "" or isinstance(d.target, str)


class TestUtilityPerf:
    def test_50npc_batch_under_budget(self) -> None:
        """非 bench 的护栏实测（bench 文件另有暖态中位口径）：50 NPC 一次打分
        不应超过逐对象预算的量级（红线 6.0ms/tick 来自 pi thresholds）。"""
        import time

        profiles = [
            _profile(
                i, (Need("hunger", 0.4, 2.0), Need("energy", 0.6, 1.0), Need("social", 0.2, 1.0))
            )
            for i in range(50)
        ]
        model = UtilityModel(n_npc=50, seed=7)
        t0 = time.perf_counter()
        evaluate_batch(profiles, model)
        ms = (time.perf_counter() - t0) * 1000.0
        # 红线 6.0ms 是暖态中位（含 JIT 预热后的稳态）；本护栏给 3× 冷启动余量
        assert ms < 18.0, f"50 NPC 效用打分 {ms:.2f}ms 超冷启动护栏 18ms"


# ---------------------------------------------------------------------------
# runtime.py — 装配入口（§1.3：NpcRuntime.tick → 本 tick 事件批次）
# ---------------------------------------------------------------------------


class TestNpcRuntime:
    def _runtime(self, profiles: list[NpcProfileData]) -> NpcRuntime:
        return NpcRuntime(
            profiles={p.npc_id: p for p in profiles},
            utility=UtilityModel(n_npc=len(profiles), seed=7),
        )

    def test_tick_returns_act_events(self) -> None:
        profiles = [_profile(i, (Need("hunger", 0.8, 2.0),)) for i in range(5)]
        rt = self._runtime(profiles)
        events = rt.tick(tick=100)
        assert len(events) == 5
        for e in events:
            assert e.event_type == EventKind.NPC_ACT
            assert e.payload["action"] in ACTION_WHITELIST

    def test_tick_pure_events_do_not_mutate(self) -> None:
        # 纯函数性：同一 tick 两次调用产出等价事件批次（可重放，C5）
        profiles = [_profile(i, (Need("hunger", 0.7, 1.5),)) for i in range(3)]
        rt = self._runtime(profiles)
        e1 = rt.tick(tick=50)
        e2 = rt.tick(tick=50)
        assert [(x.payload["action"], x.payload["npc_id"]) for x in e1] == [
            (x.payload["action"], x.payload["npc_id"]) for x in e2
        ]

    def test_needs_advanced_after_tick(self) -> None:
        # tick 推进需求（needs.py DEFAULT_DECAYS）：返回事件后内存态已更新
        profiles = [_profile(0, (Need("hunger", 0.0, 1.0),))]
        rt = self._runtime(profiles)
        rt.tick(tick=1)
        assert rt.profiles["npc_00"].needs[0].value > 0.0

    def test_threshold_remedy_injected(self) -> None:
        # needs 阈值触发 → 补救动作进候选集（§2.1 候选集公式第 2 项）
        profiles = [_profile(0, (Need("hunger", 0.99, 5.0),))]
        rt = self._runtime(profiles)
        events = rt.tick(tick=10)
        # 阈值命中时 eat 必然胜出（remedy 注入候选集 + 高权重紧迫度）
        assert events[0].payload["action"] == "eat"

    def test_lod_zero_skipped(self) -> None:
        # L0 统计档不产生决策（不建对象语义：无 NPC_ACT 事件）
        p = _profile(0, (Need("hunger", 0.9, 2.0),)).with_lod(0)
        rt = self._runtime([p])
        assert rt.tick(tick=1) == []

    def test_event_tick_matches(self) -> None:
        profiles = [_profile(0, (Need("hunger", 0.5, 1.0),))]
        rt = self._runtime(profiles)
        events = rt.tick(tick=777)
        assert events[0].tick == 777

    def test_params_whitelisted_keys(self) -> None:
        # NPC_ACT payload params 只允许 ACTION_PAYLOAD_KEYS 白名单键
        from sim.npc.actions import ACTION_PAYLOAD_KEYS

        profiles = [_profile(i, (Need("hunger", 0.5, 1.0),)) for i in range(3)]
        rt = self._runtime(profiles)
        for e in rt.tick(tick=1):
            allowed = ACTION_PAYLOAD_KEYS[str(e.payload["action"])]
            params = e.payload["params"]
            assert isinstance(params, dict)
            assert set(params.keys()) <= set(allowed)
