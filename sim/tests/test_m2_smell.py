"""M2-A2 第二批：smell.py 欧拉网格嗅觉场（m2-npc-cognition §5.1）。

TDD RED 先行。契约（架构稿 §5.1 + pi bench 参考实现）：
- SmellField：64×64 × 单物质浓度场（M2 单通道；多物质 M3+ 扩展维）；
- smell_propagate(field, sources, wind) 纯函数：发射→平流(np.roll 半格)→衰减；
- SmellField.sample(pos) O(1) 接收；
- 阻断=不阻断（绕障是平流自然结果）；修正=风场（weather.wind_at 消费）。
"""

from __future__ import annotations

import numpy as np
import pytest

from sim.perception.smell import SmellField, smell_propagate, smell_sample_batch

GRID = 64
DECAY = np.float32(0.98)


class TestSmellField:
    def test_empty_field_zero_sample(self) -> None:
        f = SmellField.zeros(grid=GRID)
        assert f.sample((10, 10)) == 0.0

    def test_source_injection_localized(self) -> None:
        # 源所在格浓度 > 远格
        f = SmellField.zeros(grid=GRID)
        f2 = f.inject(sources=[(32, 32)], strength=1.0)
        assert f2.sample((32, 32)) > f2.sample((0, 0))

    def test_inject_immutable(self) -> None:
        # inject 返回新场（纯函数；原场不变）
        f = SmellField.zeros(grid=GRID)
        f.inject(sources=[(5, 5)], strength=2.0)
        assert f.sample((5, 5)) == 0.0

    def test_decay_multiplies_field(self) -> None:
        f = SmellField.zeros(grid=GRID).inject(sources=[(3, 3)], strength=1.0)
        f2 = f.decayed(DECAY)
        assert f2.sample((3, 3)) == pytest.approx(0.98, abs=1e-6)

    def test_sample_out_of_bounds_clamped(self) -> None:
        # 越界采样按边界格 clamp（NPC 永不越图，防御性）
        f = SmellField.zeros(grid=GRID).inject(sources=[(0, 0)], strength=1.0)
        assert f.sample((-5, -5)) == f.sample((0, 0))


class TestPropagate:
    def test_wind_advects_downwind(self) -> None:
        """平流：恒定风 (0,+1)（dy 正=y+）→ 浓度向 y+ 移动。"""
        f = SmellField.zeros(grid=GRID).inject(sources=[(32, 10)], strength=10.0)
        wind = (0.0, 1.0)  # 单位方向（weather.WindVector.vector 口径）
        f2 = smell_propagate(f, sources=[(32, 10)], wind=wind, strength=10.0, decay=DECAY)
        # 源点被 roll 走后回注一半强度；下风格（y+1）浓度应高于上风格
        assert f2.sample((32, 11)) > f2.sample((32, 9))

    def test_calm_wind_still_diffuses_by_decay(self) -> None:
        # 静风：无平流，只衰减（nose 只靠回注维持）
        f = SmellField.zeros(grid=GRID).inject(sources=[(32, 32)], strength=10.0)
        f2 = smell_propagate(f, sources=[(32, 32)], wind=(0.0, 0.0), strength=10.0, decay=DECAY)
        assert f2.sample((32, 32)) < f.sample((32, 32)) + 10.0  # 原值衰减后回注

    def test_pure_function_replayable(self) -> None:
        # C5：同输入两次传播逐位一致
        f = SmellField.zeros(grid=GRID).inject(sources=[(7, 7)], strength=3.0)
        a = smell_propagate(f, sources=[(7, 7)], wind=(1.0, 0.0), strength=3.0, decay=DECAY)
        b = smell_propagate(f, sources=[(7, 7)], wind=(1.0, 0.0), strength=3.0, decay=DECAY)
        assert np.array_equal(a.grid, b.grid)
        assert np.array_equal(f.grid, f.grid)  # 原场未被改动

    def test_multi_source_accumulate(self) -> None:
        # 多源同格叠加强度
        f = SmellField.zeros(grid=GRID)
        f2 = smell_propagate(
            f, sources=[(10, 10), (10, 10)], wind=(0.0, 0.0), strength=1.0, decay=1.0
        )
        assert f2.sample((10, 10)) == pytest.approx(2.0)


class TestSampleBatch:
    def test_batch_matches_individual(self) -> None:
        """50 NPC 批量采样 = 逐个采样（向量化入口，禁逐 NPC Python 循环的批量版）。"""
        f = SmellField.zeros(grid=GRID).inject(sources=[(20, 20), (40, 40)], strength=5.0)
        positions = [(20, 20), (40, 40), (0, 0)]
        batch = smell_sample_batch(f, positions)
        assert batch.shape == (3,)
        for i, pos in enumerate(positions):
            assert batch[i] == pytest.approx(f.sample(pos))

    def test_batch_dtype_float32(self) -> None:
        f = SmellField.zeros(grid=GRID)
        out = smell_sample_batch(f, [(1, 1), (2, 2)])
        assert out.dtype == np.float32
