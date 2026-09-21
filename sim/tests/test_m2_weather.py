"""M2-C2：风场派生（`sim/world/weather.py`；m2-npc-cognition §5.1）。

T1 断言：纯函数可重放 + 通道语义（顺风/逆风）+ 每日天气注入点。秒级、无 LLM，
随 `-m "not bench"` 全量跑；也被 ci.yml 的 M2 命名步骤按文件路径接住。
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from sim.core.calendar import TICKS_PER_GAME_DAY, DayPhase
from sim.core.entropy import EntropyMixer
from sim.core.rng import RngRegistry
from sim.world.weather import (
    MAX_WIND_SPEED,
    WEATHER_STREAM,
    WeatherError,
    WindVector,
    daily_reseed_due,
    wind_at,
    wind_slot,
)

_SEED = 42
_HOUR = 3_600


def _registry(world_seed: int = _SEED) -> RngRegistry:
    return RngRegistry(world_seed=world_seed)


# ---------------------------------------------------------------------------
# WindVector — 取值契约
# ---------------------------------------------------------------------------


class TestWindVector:
    def test_from_direction_is_unit_vector(self) -> None:
        # Arrange / Act
        w = WindVector.from_direction(math.pi / 3, 0.2)

        # Assert
        assert math.hypot(w.dx, w.dy) == pytest.approx(1.0, abs=1e-12)
        assert w.speed == pytest.approx(0.2)
        assert w.direction_rad == pytest.approx(math.pi / 3)

    def test_calm_wind_is_valid(self) -> None:
        # 静风：方向仍在、无平流（嗅觉只靠扩散）——不是非法值
        w = WindVector.from_direction(0.0, 0.0)
        assert w.vector == (0.0, 0.0)

    def test_speed_over_max_rejected(self) -> None:
        with pytest.raises(WeatherError, match="风速越界"):
            WindVector.from_direction(0.0, MAX_WIND_SPEED + 0.01)

    def test_negative_speed_rejected(self) -> None:
        with pytest.raises(WeatherError, match="风速越界"):
            WindVector.from_direction(0.0, -0.1)

    def test_non_finite_rejected(self) -> None:
        with pytest.raises(WeatherError, match="有限数"):
            WindVector(dx=0.0, dy=1.0, speed=float("nan"))

    def test_non_unit_direction_rejected(self) -> None:
        with pytest.raises(WeatherError, match="单位向量"):
            WindVector(dx=0.6, dy=0.6, speed=0.1)

    def test_frozen_replace_revalidates_and_returns_new(self) -> None:
        # Arrange
        w = WindVector.from_direction(0.0, 0.2)

        # Act
        w2 = dataclasses.replace(w, speed=0.3)

        # Assert
        assert w2.speed == pytest.approx(0.3)
        assert w.speed == pytest.approx(0.2)  # 原实例不变
        with pytest.raises(WeatherError, match="风速越界"):
            dataclasses.replace(w, speed=MAX_WIND_SPEED * 2)

    def test_vector_is_direction_times_speed(self) -> None:
        w = WindVector.from_direction(0.0, 0.5)
        assert w.vector == pytest.approx((0.5, 0.0))

    def test_as_array_is_unit_direction(self) -> None:
        # 供 smell 的投影/点乘消费（naive 哨兵同款写法）
        w = wind_at(0, _registry())
        arr = w.as_array()
        assert arr.shape == (2,)
        assert float((arr**2).sum()) == pytest.approx(1.0, abs=1e-12)

    def test_project_marks_upwind_negative(self) -> None:
        # 顺风为正、逆风为负（DESIGN §7「下风处闻到血腥」的几何前提）
        w = WindVector.from_direction(0.0, 0.4)  # 正 x 方向
        assert w.project((1.0, 0.0)) > 0.0
        assert w.project((-1.0, 0.0)) < 0.0
        assert w.project((0.0, 1.0)) == pytest.approx(0.0)

    def test_max_speed_keeps_advection_under_one_cell(self) -> None:
        # 网格平流契约：单 tick 位移 <1 格，避免整格跳变越过衰减尺度（weather.py 常量依据）
        assert 0.0 < MAX_WIND_SPEED < 1.0


# ---------------------------------------------------------------------------
# wind_slot / daily_reseed_due — 时间派生
# ---------------------------------------------------------------------------


class TestWindSlot:
    def test_tick_zero_is_day_one_night(self) -> None:
        assert wind_slot(0) == (1, DayPhase.NIGHT)

    @pytest.mark.parametrize(
        ("hour", "phase"),
        [(6, DayPhase.DAWN), (8, DayPhase.DAY), (18, DayPhase.DUSK), (23, DayPhase.NIGHT)],
    )
    def test_phase_mapping(self, hour: int, phase: DayPhase) -> None:
        assert wind_slot(hour * _HOUR)[1] is phase

    def test_day_advances_with_tick(self) -> None:
        assert wind_slot(0)[0] == 1
        assert wind_slot(TICKS_PER_GAME_DAY)[0] == 2
        assert wind_slot(TICKS_PER_GAME_DAY * 7 - 1)[0] == 7

    def test_wind_constant_within_slot(self) -> None:
        # 档内恒定（低频更新口径）：同一档任意两 tick 同风
        rng = _registry()
        assert wind_at(8 * _HOUR, rng) == wind_at(8 * _HOUR + 100, rng)

    def test_wind_changes_across_phase_boundary(self) -> None:
        rng = _registry()
        assert wind_at(7 * _HOUR - 1, rng) != wind_at(7 * _HOUR, rng)


class TestDailyReseedDue:
    def test_due_at_day_boundaries(self) -> None:
        assert daily_reseed_due(0) is True
        assert daily_reseed_due(TICKS_PER_GAME_DAY) is True
        assert daily_reseed_due(TICKS_PER_GAME_DAY * 5) is True

    def test_not_due_mid_day(self) -> None:
        assert daily_reseed_due(1) is False
        assert daily_reseed_due(TICKS_PER_GAME_DAY - 1) is False
        assert daily_reseed_due(TICKS_PER_GAME_DAY + 1) is False


# ---------------------------------------------------------------------------
# wind_at — 纯函数 / 可重放（C5）
# ---------------------------------------------------------------------------


class TestWindAtDeterminism:
    def test_same_args_same_wind(self) -> None:
        rng = _registry()
        assert wind_at(12_345, rng) == wind_at(12_345, rng)

    def test_order_independent(self) -> None:
        # 纯函数：结果不受调用顺序影响（不推进抽签状态）
        rng = _registry()
        first = wind_at(9 * _HOUR, rng)
        for t in range(0, 24 * _HOUR, 600):
            wind_at(t, rng)
        assert wind_at(9 * _HOUR, rng) == first

    def test_fresh_registry_same_seed_same_wind(self) -> None:
        assert wind_at(0, _registry(_SEED)) == wind_at(0, _registry(_SEED))

    def test_world_seed_changes_wind_somewhere(self) -> None:
        a, b = _registry(_SEED), _registry(_SEED + 1)
        ticks = range(0, 4 * TICKS_PER_GAME_DAY, _HOUR)
        assert any(wind_at(t, a) != wind_at(t, b) for t in ticks)

    def test_unrelated_stream_does_not_affect_wind(self) -> None:
        # 分流 RNG 的意义：别的子系统抽签不改变风（m0-core §2）
        rng = _registry()
        before = wind_at(0, rng)
        rng.generator("npc.utility", {}).random()
        assert wind_at(0, rng) == before

    def test_speed_within_bounds_over_seven_days(self) -> None:
        rng = _registry()
        winds = [wind_at(t, rng) for t in range(0, 7 * TICKS_PER_GAME_DAY, _HOUR)]
        assert all(0.0 <= w.speed <= MAX_WIND_SPEED for w in winds)

    def test_slots_are_distinct_not_one_static_wind(self) -> None:
        # 7 日 × 4 档 = 168 小时采样，方向组合应远多于 1 种（防「恒定风」退化）
        rng = _registry()
        combos = {
            (round(wind_at(t, rng).dx, 9), round(wind_at(t, rng).dy, 9))
            for t in range(0, 7 * TICKS_PER_GAME_DAY, _HOUR)
        }
        assert len(combos) >= 8


# ---------------------------------------------------------------------------
# 每日天气 = 注入真随机（DESIGN §11）——注入可重放
# ---------------------------------------------------------------------------


class TestWeatherEntropyInjection:
    def test_daily_injection_changes_wind(self) -> None:
        # Arrange
        mixer = EntropyMixer(rng=_registry())

        # Act
        injected, event = mixer.mix(WEATHER_STREAM, tick=0)

        # Assert
        assert wind_at(0, injected.rng) != wind_at(0, mixer.rng)
        assert event.tick == 0
        assert event.payload["stream"] == WEATHER_STREAM
        assert len(str(event.payload["material"])) == 32  # 16 bytes hex

    def test_replay_mix_reproduces_same_wind(self) -> None:
        # 重放路径：从**注入前**的注册表 + 事件里的材料 → 同一风（C5 逐位一致）
        # 口径与 test_core_m0.py::test_entropy_roundtrip_replay 一致
        mixer = EntropyMixer(rng=_registry())
        injected, event = mixer.mix(WEATHER_STREAM, tick=0)
        replayed = mixer.replay_mix(
            stream=str(event.payload["stream"]),
            material_hex=str(event.payload["material"]),
        )

        assert wind_at(0, replayed.rng) == wind_at(0, injected.rng)
        assert replayed.rng.draw_key(WEATHER_STREAM) == injected.rng.draw_key(WEATHER_STREAM)

    def test_injection_only_affects_weather_stream(self) -> None:
        # 注入只推进 weather 流材料：NPC 流不受影响（分流隔离）
        mixer = EntropyMixer(rng=_registry())
        injected, _ = mixer.mix(WEATHER_STREAM, tick=0)

        assert injected.rng.draw_key("npc.utility") == mixer.rng.draw_key("npc.utility")
        assert injected.rng.draw_key(WEATHER_STREAM) != mixer.rng.draw_key(WEATHER_STREAM)
