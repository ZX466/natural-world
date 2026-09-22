"""sim.perception.smell — 嗅觉通道：Eulerian 网格增量扩散（M2-A1 §5.1）。

算法采纳 pi 对账提示 #2（网格增量扩散，禁逐对 O(N²)——naive 哨兵实测 ~4.6ms，
网格红线 0.15ms/tick，thresholds.py）。三要素映射（与视觉/听觉同构）：
衰减=全图系数；阻断=不阻断（绕障是平流的自然结果）；修正=风场（weather.wind_at）。

纯函数：smell_propagate 返回新 SmellField，不原地改（项目 immutability 规约）；
接收端 O(1) 采样（批量版 smell_sample_batch 向量化）。不进 prompt/协议（铁律 1）。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SmellField:
    """Eulerian 嗅觉浓度场（64×64 float32；M2 单物质通道，多物质 M3+ 扩维）。"""

    grid: np.ndarray

    @staticmethod
    def zeros(grid: int = 64) -> SmellField:
        return SmellField(grid=np.zeros((grid, grid), dtype=np.float32))

    def sample(self, pos: tuple[int, int]) -> float:
        """O(1) 采样（所在格浓度；1/r² 已由扩散场隐式承载）。越界 clamp 防御。"""
        h, w = self.grid.shape
        y = int(np.clip(pos[1], 0, h - 1))
        x = int(np.clip(pos[0], 0, w - 1))
        return float(self.grid[y, x])

    def inject(self, sources: list[tuple[int, int]], strength: float) -> SmellField:
        """源发射：向各源所在格加注（返回新场；多源同格自然累加）。"""
        out = self.grid.copy()
        h, w = out.shape
        for sx, sy in sources:
            y = int(np.clip(sy, 0, h - 1))
            x = int(np.clip(sx, 0, w - 1))
            out[y, x] += np.float32(strength)
        return SmellField(grid=out)

    def decayed(self, decay: np.float32 | float) -> SmellField:
        """全图衰减（乘系数；返回新场）。"""
        return SmellField(grid=self.grid * np.float32(decay))


def smell_propagate(
    field: SmellField,
    *,
    sources: list[tuple[int, int]],
    wind: tuple[float, float],
    strength: float,
    decay: np.float32 | float,
    diffuse_rate: float = 0.0,
) -> SmellField:
    """一 tick 嗅觉推进：发射 → 平流（风） → 扩散 → 衰减（§5.1 纯函数，可重放）。

    wind = weather.WindVector.vector()（每 tick 位移，格/tick）。
    平流用 np.roll 取整格位移（半格亚像素精度 M3+ 再加密；pi bench 同口径）。
    静风 (0,0)：np.roll(0) 为 no-op，只剩发射+扩散+衰减。
    diffuse_rate：8 防域扩散份额（0..1；0=关，既有调用方行为不变）——
    每 tick 每格按比例把浓度向 4 直邻 + 4 斜邻（斜邻减半）让渡（arch §5.1 第 2 步），
    向量化 done via np.roll 叠加，无逐格 Python 循环。
    """
    # 1. 发射（在平流前注入：源是世界的固定位置，随场一起被风带走）
    emitted = field.inject(sources, strength)
    # 2. 平流：roll 轴序 (y, x)；dy 位移 y 轴、dx 位移 x 轴
    dx, dy = wind
    shift_y = round(dy)
    shift_x = round(dx)
    advected = SmellField(grid=np.roll(emitted.grid, shift=(shift_y, shift_x), axis=(0, 1)))
    # 3. 8 邻域扩散（arch §5.1 算法第 2 步；0 = 既有口径不变）
    g = advected.grid
    if diffuse_rate > 0.0:
        rate = np.float32(diffuse_rate)
        diag = np.float32(diffuse_rate / 2.0)
        share = g * rate  # 每格向 4 直邻各让渡的量
        dshare = g * diag  # 向 4 斜邻各让渡的量（减半）
        acc = (
            np.roll(share, shift=(1, 0), axis=(0, 1))
            + np.roll(share, shift=(-1, 0), axis=(0, 1))
            + np.roll(share, shift=(0, 1), axis=(0, 1))
            + np.roll(share, shift=(0, -1), axis=(0, 1))
            + np.roll(dshare, shift=(1, 1), axis=(0, 1))
            + np.roll(dshare, shift=(1, -1), axis=(0, 1))
            + np.roll(dshare, shift=(-1, 1), axis=(0, 1))
            + np.roll(dshare, shift=(-1, -1), axis=(0, 1))
        )
        outflow = 4 * share + 4 * dshare
        g = g - outflow + acc
    # 4. 衰减
    return SmellField(grid=g * np.float32(decay))


def smell_sample_batch(field: SmellField, positions: list[tuple[int, int]]) -> np.ndarray:
    """批量采样（50 NPC 一次 fancy indexing；禁逐 NPC 循环）。"""
    if not positions:
        return np.zeros(0, dtype=np.float32)
    h, w = field.grid.shape
    ys = np.clip([p[1] for p in positions], 0, h - 1)
    xs = np.clip([p[0] for p in positions], 0, w - 1)
    return field.grid[ys, xs]
