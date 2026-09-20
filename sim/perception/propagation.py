"""传播引擎 — 通道无关三要素：衰减 + 阻断 + 修正（DESIGN §7，C06-③）。

这是信息边界 C2 的物理实现核心：一个事件能否进入某个 Agent 的感知，
由传播模型决定，不由规则白名单决定。通道模型差异全部收敛为
「衰减函数 + 阻断函数 + 修正系数」的组合：

- 视觉：衰减 ∝1/max(r,1)，遮挡完全阻断（射线），光照/雾为修正
- 听觉：衰减 ∝1/r，墙体穿墙衰减不阻断（每穿一格 ×0.5）
- 嗅觉(M2)：∝1/r²，风向主导 —— 三要素同构，换参数即可

性能契约（docs/perf/hotspots.md H-1 取舍：方案 1 分区剪枝 + 方案 3 降采样）：
- 距离半径预过滤（候选 cull，O(N·k)）
- 射线只在候选对上打
- 昼夜光照修正低频：调用方每 PERCEPTION_LIGHT_INTERVAL tick 算一次传入

纯函数、无全局态：同输入必同输出（C5，bench/回放友好）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sim.world.map import CHUNK_SIZE, TileMap

# --- 传播模型常量（DESIGN §7 + profiles 注释的取值依据）---

WALL_DECAY = 0.5  # 听觉每穿一格墙的衰减因子（不阻断，穿墙衰减）
LIGHT_NIGHT = 0.4  # 夜间光照修正系数（视觉强度乘子；白天 1.0）
LIGHT_INTERVAL = 10  # 光照修正低频节拍：每 N tick 算一次（H-1 方案 3）


def line_blocked(tile_map: TileMap, a: tuple[int, int], b: tuple[int, int]) -> bool:
    """a→b 视线是否被阻断（Bresenham 射线，两端点不算障碍）。

    纯几何：只查 tile 碰撞，与实体无关。视觉「完全阻断」的唯一判据。
    无缓存——调用方高频复用同一图时应持有 PerceptionEngine（其内部
    带实例级 LOS 缓存；模块级缓存会跨 TileMap 串味，此处不做）。
    """
    return _line_blocked_uncached(tile_map, a, b)


def _line_blocked_uncached(tile_map: TileMap, a: tuple[int, int], b: tuple[int, int]) -> bool:
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if (x0, y0) != a and (x0, y0) != b and not tile_map.is_walkable(x0, y0):
            return True  # 途经不可通行 tile → 遮挡
        if x0 == x1 and y0 == y1:
            return False
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


# --- 扁平碰撞网格（H-1 性能底座）---
# pydantic Chunk 属性链（bounds→chunk_of→get→collision 索引）在热循环里太慢；
# TileMap frozen → 一次性展开成 bytes，Bresenham 里只剩一次 bytearray 索引。


def collision_grid(tile_map: TileMap) -> bytes:
    """整图碰撞展开：row-major bytes，1=可通行 0=障碍。长度 = width×height。"""
    w, h = tile_map.width, tile_map.height
    grid = bytearray(w * h)
    for cy in range(tile_map.chunks_y):
        for cx in range(tile_map.chunks_x):
            chunk = tile_map.chunks.get((cx, cy))
            if chunk is None:
                continue
            for ly in range(CHUNK_SIZE):
                gy = cy * CHUNK_SIZE + ly
                if gy >= h:
                    break
                base = gy * w + cx * CHUNK_SIZE
                row = chunk.collision[ly * CHUNK_SIZE : (ly + 1) * CHUNK_SIZE]
                for lx, walkable in enumerate(row):
                    gx = cx * CHUNK_SIZE + lx
                    if gx < w:
                        grid[base + lx] = 1 if walkable else 0
    return bytes(grid)


def line_blocked_grid(
    grid: bytes, width: int, height: int, a: tuple[int, int], b: tuple[int, int]
) -> bool:
    """网格版射线遮挡（两端点不算障碍）。语义与 line_blocked 完全一致。"""
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if (
            (x0, y0) != a
            and (x0, y0) != b
            and not (0 <= x0 < width and 0 <= y0 < height and grid[y0 * width + x0])
        ):
            return True
        if x0 == x1 and y0 == y1:
            return False
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def walls_crossed_grid(
    grid: bytes, width: int, height: int, a: tuple[int, int], b: tuple[int, int]
) -> int:
    """网格版穿墙计数（两端点不算）。语义与 walls_crossed 完全一致。"""
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    crossed = 0
    while True:
        if (
            (x0, y0) != a
            and (x0, y0) != b
            and not (0 <= x0 < width and 0 <= y0 < height and grid[y0 * width + x0])
        ):
            crossed += 1
        if x0 == x1 and y0 == y1:
            return crossed
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def walls_crossed(tile_map: TileMap, a: tuple[int, int], b: tuple[int, int]) -> int:
    """a→b 途经的不可通行 tile 数（听觉穿墙衰减计数，两端点不算）。"""
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    crossed = 0
    while True:
        if (x0, y0) != a and (x0, y0) != b and not tile_map.is_walkable(x0, y0):
            crossed += 1
        if x0 == x1 and y0 == y1:
            return crossed
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


@dataclass(frozen=True)
class Propagation:
    """传播结果：0.0 = 感知不到；>0 = 显著性强度（供显著性与帧装配排序）。"""

    strength: float


def vision_propagate(
    dist: float, light: float = 1.0, *, radius: float, floor: float
) -> Propagation:
    """视觉三要素组合：1/r 衰减 × 光照修正 × 遮挡阻断（遮挡由调用方射线判定）。

    floor 是显著性 HARD floor：低于它整条观测丢弃（夜间远处草动不值得报）。
    """
    if dist > radius:
        return Propagation(0.0)
    strength = (1.0 / max(dist, 1.0)) * light
    return Propagation(strength if strength >= floor else 0.0)


def hearing_propagate(
    dist: float,
    walls: int,
    *,
    radius: float,
    floor: float,
    base: float = 1.0,
) -> Propagation:
    """听觉三要素组合：base/r 衰减 × 穿墙衰减（WALL_DECAY^walls，不阻断）。

    无 HARD floor 丢弃——低于 floor 交给显著性（低强度仍可产出
    「有音无义」类弱感知；M1 由装配端决定是否呈现）。
    """
    if dist > radius:
        return Propagation(0.0)
    strength = base / max(dist, 1.0) * (WALL_DECAY**walls)
    return Propagation(min(strength, 1.0))


def light_factor(tick: int) -> float:
    """昼夜光照修正（视觉乘子）。白天 1.0；夜间/黄昏打折。

    低频调用契约：调用方每 LIGHT_INTERVAL tick 算一次传入引擎（H-1 方案 3），
    本函数自身只做纯查表。
    """
    from sim.core.calendar import DayPhase, phase_of_day

    phase = phase_of_day(tick)
    if phase in (DayPhase.NIGHT, DayPhase.DUSK):
        return LIGHT_NIGHT
    if phase == DayPhase.DAWN:
        return (1.0 + LIGHT_NIGHT) / 2.0  # 黎明折半过渡
    return 1.0


def candidates_in_radius(
    origin: tuple[int, int],
    positions: dict[str, tuple[int, int]],
    radius: float,
    *,
    exclude: str,
) -> list[str]:
    """半径内候选 id（欧氏距离预过滤）。O(N) 顺序稳定（dict 序 + 距离排序）。

    顺序确定性：先按 dict 插入序过滤，再按 (dist, id) 排序 —— 同输入同输出。
    """
    ox, oy = origin
    out: list[tuple[float, str]] = []
    for eid, (x, y) in positions.items():
        if eid == exclude:
            continue
        d = math.hypot(x - ox, y - oy)
        if d <= radius:
            out.append((d, eid))
    out.sort()
    return [eid for _, eid in out]
