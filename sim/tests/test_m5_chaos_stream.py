"""M5-A 批次：混沌流钉子（DESIGN §11 + opencode 预研 §a 结论）。

口径：
- chaotic 纯函数可重放（同材料恒同值、无调用序依赖）——T2 逐位一致前提；
- chaotic_at 同刻恒同值/异刻独立——日常演化语义载体；
- inject 重播种后序列整体切换——DESIGN「注入后重新播种」；
- T1 出戏边界：返回值不携带熵材料/seed 面（float 标量）。
"""

from __future__ import annotations

import numpy as np

from sim.core.entropy import EntropyMixer
from sim.core.rng import RngRegistry
from sim.world.chaos import CHAOS_STREAM, chaotic, chaotic_at


def _rng(seed: int = 42) -> RngRegistry:
    return RngRegistry(world_seed=seed)


class TestChaoticDeterminism:
    def test_same_material_same_value(self) -> None:
        """同 (seed, materials) 恒同值——纯函数可重放（T2 前提）。"""
        assert chaotic("chaos", _rng()) == chaotic("chaos", _rng())

    def test_no_call_order_dependency(self) -> None:
        """无调用序依赖：连抽 N 次后重算，值不变（区别于 generator 进度语义）。"""
        rng = _rng()
        for _ in range(10):
            chaotic("chaos", rng)
        assert chaotic("chaos", rng) == chaotic("chaos", _rng())

    def test_value_in_unit_interval(self) -> None:
        v = chaotic("chaos", _rng())
        assert 0.0 <= v < 1.0

    def test_different_streams_independent(self) -> None:
        """流隔离：不同流材料不同 ⇒ 值不同（分流语义）。"""
        rng = _rng()
        assert chaotic("chaos", rng) != chaotic("chaos.weather", rng)

    def test_returns_plain_float_scalar(self) -> None:
        """T1 边界：返回普通 float 标量（不携带材料/seed 面，可安全进内核）。"""
        v = chaotic("chaos", _rng())
        assert type(v) is float
        assert not isinstance(v, np.generic)


class TestChaoticAtTickVariance:
    def test_same_tick_same_value(self) -> None:
        assert chaotic_at("chaos", _rng(), 100) == chaotic_at("chaos", _rng(), 100)

    def test_different_ticks_independent_samples(self) -> None:
        """异刻独立样本（重合概率 ~2^-53，实践恒异）。"""
        vals = {chaotic_at("chaos", _rng(), t) for t in range(50)}
        assert len(vals) == 50

    def test_tick_zero_equals_chaotic(self) -> None:
        assert chaotic_at("chaos", _rng(), 0) == chaotic("chaos", _rng())


class TestInjectReswitch:
    def test_inject_switches_chaotic_sequence(self) -> None:
        """DESIGN §11：注入真随机后重新播种 ⇒ chaotic 序列整体切换。"""
        rng = _rng()
        before = chaotic("chaos", rng)
        mixer, event = EntropyMixer(rng=rng).mix("chaos", tick=1)
        after = chaotic("chaos", mixer.rng)
        assert before != after
        assert event.event_type.value == "entropy_inject"

    def test_replay_rebuilds_same_sequence(self) -> None:
        """重放路径：用事件材料 replay_mix ⇒ chaotic 逐位一致（C5）。"""
        mixer, event = EntropyMixer(rng=_rng()).mix("chaos", tick=1)
        material_hex = str(event.payload["material"])
        replayed = EntropyMixer(rng=_rng()).replay_mix("chaos", material_hex)
        assert chaotic("chaos", mixer.rng) == chaotic("chaos", replayed.rng)

    def test_stream_constant(self) -> None:
        assert CHAOS_STREAM == "chaos"
