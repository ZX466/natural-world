"""human 物种 profile — 视觉主导 + 语言（语言判定本身 M2）。

半径取值依据：临河镇 32×32 起步图，视觉 12 tile ≈ 半个街区；
听觉地板 0.04 配 FOOTSTEP_BASE=1.0 → 空地有效听距 ~25 tile（被半径 14 截断），
一堵墙衰减 0.5 → 隔墙有效听距 ~12 tile（「街对面只闻闷响」）。
"""

from __future__ import annotations

from sim.perception.profiles.base import PerceptionProfile

HUMAN = PerceptionProfile(
    species="human",
    vision_radius=12.0,
    hearing_radius=14.0,
)
