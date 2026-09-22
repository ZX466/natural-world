"""sim.perception.smell_world — 嗅觉场跨 tick 持有者（M2-A2 接线；m2-npc-cognition §5.1）。

职责边界：
- 持有跨 tick 的 SmellField（随 TileMap 常驻，id(tile_map) 键控由调用方管理——
  本模块只管场本身），每 tick 推进一次（发射 → 平流 → 扩散 → 衰减）+ 批量采样；
- 源口径：实体=持续弱源（SMELL_SOURCE_STRENGTH 占位常量，沿 M1 FOOTSTEP_BASE
  先例）；matter 源（食物堆/尸体）M3 接 MatterLedger 扩展；
- 风：调用方每 tick 传 weather.wind_at(tick, rng).vector（纯函数派生，档内恒定，
  档间跳变由 wind_slot 对齐 DayPhase）；本模块不碰 RNG（保持纯推进，可重放）；
- 不进 prompt/协议（铁律 1）：采样浓度只在感知域内部消费，出帧的是叙事文本。
"""

from __future__ import annotations

import numpy as np

from sim.perception.smell import SmellField, smell_propagate, smell_sample_batch

#: 实体持续源发射强度（占位常量；matter 源 M3 接 MatterLedger 后分物质定标）。
SMELL_SOURCE_STRENGTH: float = 1.0

#: 每 tick 场衰减系数（与 pi bench 参考实现同口径 0.98）。
SMELL_DECAY: float = 0.98

#: 8 邻域扩散份额（arch §5.1 算法第 2 步；每 tick 每格向邻域让渡的浓度比例）。
SMELL_DIFFUSE_RATE: float = 0.10


class SmellWorld:
    """跨 tick 嗅觉场：step() = 一 tick 推进 + 一次批量采样（O(grid²) 无逐对）。"""

    def __init__(self, *, height: int = 64, width: int = 64) -> None:
        self._field = SmellField(grid=np.zeros((height, width), dtype=np.float32))

    @property
    def field(self) -> SmellField:
        """当前场（只读视图用途：测试断言；调用方不得改写）。"""
        return self._field

    def step(
        self,
        sources: dict[str, tuple[int, int]],
        *,
        wind: tuple[float, float],
        strength: float = SMELL_SOURCE_STRENGTH,
    ) -> dict[str, float]:
        """一 tick 推进 + 批量采样。sources = {entity_id: pos}（本 tick 实体位置）。

        返回 {entity_id: 浓度}（感知域内部量，不出协议）。
        """
        positions = list(sources.values())
        self._field = smell_propagate(
            self._field,
            sources=positions,
            wind=wind,
            strength=strength,
            decay=SMELL_DECAY,
            diffuse_rate=SMELL_DIFFUSE_RATE,
        )
        samples = smell_sample_batch(self._field, positions)
        return dict(zip(sources, samples.tolist(), strict=True))
