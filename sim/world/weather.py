"""风场派生 — 嗅觉通道的风向/风速来源（M2-C2；m2-npc-cognition §5.1）。

职责边界（最小面）：
- 本模块只回答「此刻的风是什么」——供 `sim/perception/smell.py` 的 Eulerian 网格
  平流（`np.roll` 位移 + 风向投影）消费；**不做**扩散、不做感知、不做叙事。
- 纯函数 + 无状态：同 (rng 材料, tick) 必得同风（C5 可重放、bench/回放友好）。

规则（DESIGN §7「嗅觉 ∝1/r²，风向主导」；§11「每日天气 = 注入真随机」）：
- **粒度**：一日四档，与 `sim.core.calendar.DayPhase` 对齐（黎明/白天/黄昏/夜晚）。
  档内恒定、档间跳变 —— 满足 budget §2.9「非恒定风 → 每 N tick 更新一次风场（低频 pass）」；
  帧内平滑（双线性插值）属消费方选择，此处不引入插值成本。
- **派生**：`(流材料指纹, day, phase)` 的 sha256 → PCG64 抽「方向 + 风速」。
  与 `RngRegistry.generator()` 的区别：**不推进抽签状态**（每次调用新建 Generator），
  故任意 tick 可独立重算、调用顺序不影响结果 —— 这是本模块「纯函数」的实现方式。
- **真随机**：每日天气属 DESIGN §11 注入点。世界循环在 `daily_reseed_due(tick)` 为真的 tick
  调 `EntropyMixer.mix(WEATHER_STREAM, tick)`，熵事件（`ENTROPY_INJECT`）落事件流；
  重放路径 `replay_mix(WEATHER_STREAM, payload_hex)` 用同一材料重建注册表 → 风逐位一致。
  未注入时风由 `world_seed` 纯函数派生（同样可重放，只是完全可预测）。
- **跨机一致性**：抽签用 numpy `Generator`，其流在锁定同一 numpy 版本时一致
  （`uv.lock` 钉版本 ⇒ CI 与本机同解）；换 numpy 大版本需重跑回放基线（C5 口径）。
- **出戏边界**：风向/风速是世界内部物理量 —— 不进 prompt、不进感知帧数值、不进对外协议
  （铁律 1 零元信息）；戏内只能以叙事表达（「风是从河那边吹过来的」）。
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Final

import numpy as np

from sim.core.calendar import TICKS_PER_GAME_DAY, DayPhase, game_time, phase_of_day
from sim.core.rng import RngRegistry

#: 天气流名（与内核既有保留名一致：`sim/tests/test_core_m0.py` 用 "world.weather"）
WEATHER_STREAM: Final[str] = "world.weather"

#: 风速上限（格/游戏秒，即 格/tick）——内容常量·占位值。
#: 依据 arch §5.1「沿风场位移半格」量级：上限取 0.6 保证平流位移 <1 格，
#: 避免 `np.roll` 整格跳变越过衰减尺度把浓度场撕裂。性能域若给量纲口径再改此值。
MAX_WIND_SPEED: Final[float] = 0.6

_SLOT_SEED_BYTES: Final[int] = 16  # PCG64 用 128bit 种子（与 sim/core/rng.py 一致）


class WeatherError(ValueError):
    """风场取值/参数非法。"""


@dataclass(frozen=True)
class WindVector:
    """风矢量：单位方向 (dx, dy) + 风速（格/游戏秒）。

    - `dx`/`dy` 是**单位向量**分量（模 1，y 轴向下为正，与瓦片坐标同向）；
    - `speed` = 平流速率（格/tick）；`vector` = (dx·speed, dy·speed) 即每 tick 位移。
    - 静风（speed = 0）合法：方向仍在，但无平流（nose 只靠扩散）。
    """

    dx: float
    dy: float
    speed: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.dx, self.dy, self.speed)):
            raise WeatherError(f"风矢量必须是有限数: {(self.dx, self.dy, self.speed)}")
        if not 0.0 <= self.speed <= MAX_WIND_SPEED:
            raise WeatherError(f"风速越界: {self.speed}（合法 0..{MAX_WIND_SPEED} 格/tick）")
        norm = math.hypot(self.dx, self.dy)
        if abs(norm - 1.0) > 1e-9:
            raise WeatherError(f"风向必须是单位向量（模 1），实得模 {norm}: {(self.dx, self.dy)}")

    @classmethod
    def from_direction(cls, direction_rad: float, speed: float) -> WindVector:
        """由「方向角（弧度，标准数学正向）+ 风速」构造（方向自动取单位向量）。"""
        if not math.isfinite(direction_rad):
            raise WeatherError(f"风向角必须是有限数: {direction_rad}")
        return cls(dx=math.cos(direction_rad), dy=math.sin(direction_rad), speed=speed)

    @property
    def direction_rad(self) -> float:
        """方向角（弧度，atan2 口径，[-π, π]）。静风时方向仍有意义（惯性方向）。"""
        return math.atan2(self.dy, self.dx)

    @property
    def vector(self) -> tuple[float, float]:
        """每 tick 的平流位移（格）= 单位方向 × 风速。"""
        return (self.dx * self.speed, self.dy * self.speed)

    def as_array(self) -> np.ndarray:
        """单位方向数组（供投影/点乘，如「顺风为正、逆风为负」判定）。"""
        return np.array([self.dx, self.dy], dtype=np.float64)

    def project(self, delta: tuple[float, float]) -> float:
        """把位移向量投影到风向（>0 顺风、<0 逆风、=0 侧风）——纯几何，无副作用。"""
        return self.dx * delta[0] + self.dy * delta[1]


def wind_slot(tick: int) -> tuple[int, DayPhase]:
    """tick → (戏内日, 昼夜档)。风在档内恒定（低频更新口径）。"""
    return game_time(tick).day, phase_of_day(tick)


def _slot_seed(rng: RngRegistry, day: int, phase: DayPhase) -> int:
    """档位种子 = f(流材料指纹, day, phase)。

    用 `draw_key`（公开 API，含熵注入后的材料）而非 `generator`：不推进抽签状态，
    故同一 (rng, tick) 任意次调用结果一致（纯函数语义，见模块 docstring）。
    """
    material = f"{rng.draw_key(WEATHER_STREAM)}:{day}:{phase.value}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:_SLOT_SEED_BYTES], "big")


def wind_at(tick: int, rng: RngRegistry) -> WindVector:
    """此刻（tick 所在档）的风 —— 纯函数，无状态、无 IO、可重放。

    Args:
        tick: 世界 tick（非负；戏内时间由 `sim.core.calendar` 派生）。
        rng: 分流 RNG 注册表（`world.weather` 流的材料指纹决定本日风场；
             `EntropyMixer.mix` 注入后材料变 → 风变，重放用同一材料 → 风一致）。

    Returns:
        该档位的 `WindVector`（档内恒定）。
    """
    day, phase = wind_slot(tick)
    gen = np.random.Generator(np.random.PCG64(_slot_seed(rng, day, phase)))
    direction = float(gen.random()) * math.tau
    speed = float(gen.random()) * MAX_WIND_SPEED
    return WindVector.from_direction(direction, speed)


def daily_reseed_due(tick: int) -> bool:
    """是否处于「每日天气」熵注入点（DESIGN §11：每日天气 = 注入真随机）。

    世界循环在此为真时调 `EntropyMixer.mix(WEATHER_STREAM, tick)` 并把返回的熵事件
    交给 `EventBus.apply`（C4 唯一写路径）；重放时用事件里的材料 `replay_mix`。
    第 1 天（tick 0）也算一次 —— 让首日天气同样走注入路径，避免「首日永远可预测」。
    """
    return tick % TICKS_PER_GAME_DAY == 0
