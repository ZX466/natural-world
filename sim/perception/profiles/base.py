"""感知 profile 基模型 — 物种级（不是角色级）感知参数（DESIGN §7）。

半径/地板/截断集中于此：引擎只读 profile，不做隐式常量。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PerceptionProfile(BaseModel):
    """一个物种的感知参数集。人类角色共用 human 一套（DESIGN §7）。"""

    model_config = ConfigDict(frozen=True)

    species: str
    vision_radius: float  # 白天视觉半径（tile）；夜间再乘光照修正
    hearing_radius: float  # 听觉硬上限半径（tile），内部按强度地板再截
    touch_radius: float = 1.5  # 触觉：相邻（8 邻域 √2 ≈ 1.41 < 1.5）
    vision_floor: float = 0.02  # 显著性地板（视觉：夜间低强度不抹掉人影）
    hearing_floor: float = 0.04  # 显著性地板（听觉：低于则「没注意到」）
    max_observations: int = 12  # 单帧单者观测数上限（prompt 体积治理）


class PerceptionEngineLike:  # pragma: no cover — 仅文档化协议，见 senses.PerceptionEngine
    pass
