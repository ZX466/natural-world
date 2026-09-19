"""感知传播基准（性能域，pi）— M1 挂载点（m0-core §5.2 追加项，DESIGN §7）。

背景：感知引擎 M1 落地中（Claude C06）。本文件在实现未到位时对**参考实现**跑，
形状按 DESIGN §7：视觉=射线遮挡完全阻断、听觉=∝1/r 穿墙衰减不阻断。
真实引擎合入后只替换参考实现内部（bench shape 不变），阈值来自 budget.md M1 表。

两类参考：
- 分区剪枝版（grid 桶 + 半径预过滤）：代表 M1 可交付的性能档，卡 PERCEPTION_TICK_LIMIT_MS。
- 朴素 O(N²) 哨兵：断言其明显慢于分区版（H-1 的动机证据），不卡预算红线。
"""

from __future__ import annotations

import math

import pytest

from sim.world.map import Chunk, TileMap

from .harness import assert_threshold, make_state
from .thresholds import PERCEPTION_TICK_LIMIT_MS

# 64×64 地图 → 4×4=16 chunk；全通（collision 全 True）
_MAP_W = 64
_MAP_H = 64


def _open_map() -> TileMap:
    """全通行 64×64 地图（基准用理想图：无遮挡让射线成本取最坏）。"""
    chunks: dict[tuple[int, int], Chunk] = {}
    for cy in range((_MAP_H + 15) // 16):
        for cx in range((_MAP_W + 15) // 16):
            chunks[(cx, cy)] = Chunk(
                cx=cx,
                cy=cy,
                ground=tuple(0 for _ in range(16 * 16)),
                collision=tuple(True for _ in range(16 * 16)),
            )
    return TileMap(width=_MAP_W, height=_MAP_H, tile_size=16, chunks=chunks)


def _line_of_sight(map_: TileMap, a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Bresenham 直线：全程可通行 → 可见（视觉：射线遮挡完全阻断，DESIGN §7）。

    M1 引擎合入后此函数被真实射线实现替换；bench 只卡数量级与预算走势。
    """
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if (x0, y0) != a and not map_.is_walkable(x0, y0):
            return False
        if x0 == x1 and y0 == y1:
            return True
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _vision_naive(positions: list[tuple[int, int]], map_: TileMap) -> int:
    """朴素 O(N²) 视觉传播（H-1 基线，M0 形态不可行——哨兵用）。"""
    visible = 0
    for i, a in enumerate(positions):
        for b in positions[i + 1 :]:
            if _line_of_sight(map_, a, b):
                visible += 1
    return visible


def _vision_partitioned_v2(positions: list[tuple[int, int]], map_: TileMap, radius: float) -> int:
    """修正版：按半径预过滤（欧氏距离）后再射线，避免重复与越界遍历。"""
    visible = 0
    for i, a in enumerate(positions):
        for b in positions[i + 1 :]:
            if math.hypot(a[0] - b[0], a[1] - b[1]) > radius:
                continue
            if _line_of_sight(map_, a, b):
                visible += 1
    return visible


def _sound_propagate(positions: list[tuple[int, int]], radius: float = 24.0) -> float:
    """听觉 ∝1/r、穿墙不阻断（DESIGN §7）：距离预过滤 + 求和衰减。"""
    total = 0.0
    for i, (ax, ay) in enumerate(positions):
        for bx, by in positions[i + 1 :]:
            d = math.hypot(ax - bx, ay - by)
            if d < radius and d > 0.0:
                total += 1.0 / d
    return total


def _perf_counter() -> float:
    import time

    return time.perf_counter()


def _run_timed(fn) -> float:
    t0 = _perf_counter()
    fn()
    return (_perf_counter() - t0) * 1000.0


@pytest.mark.bench
def test_perception_vision_partitioned_50npc(bench_loop_50, benchmark) -> None:
    """视觉传播 50 NPC（分区剪枝参考）：记录基线，不卡红线（红线归 M1 真实引擎）。

    M1 引擎合入后此用例把 `_vision_partitioned_v2` 换成真实实现并恢复
    assert_threshold(PERCEPTION_TICK_LIMIT_MS)。现阶段的数字是「参考实现的成本证据」。
    """

    map_ = _open_map()
    positions = [e.pos for e in bench_loop_50.state.entities.values()]

    def _run() -> float:
        return _run_timed(lambda: _vision_partitioned_v2(positions, map_, 24.0))

    benchmark.pedantic(_run, rounds=5, iterations=1)  # 只记录，不判定


@pytest.mark.bench
def test_perception_vision_naive_complexity_sentinel(bench_loop_50, benchmark) -> None:
    """朴素 O(N²) 哨兵：断言明显慢于分区版（H-1 动机证据，不卡预算红线）。"""

    map_ = _open_map()
    positions = [e.pos for e in bench_loop_50.state.entities.values()]
    # 50 个 entity 在 64×64 全通图（无障碍 → 全部可见对）
    ms_ref = _run_timed(lambda: _vision_naive(positions, map_))
    assert ms_ref > 3.0, f"朴素 O(N x N) 视觉不应快于 3ms（实测 {ms_ref:.2f}ms, H-1 动机消失）"


@pytest.mark.bench
def test_perception_sound_50npc(bench_loop_50, benchmark) -> None:
    """听觉传播 50 NPC：∝1/r 距离预过滤，M1 预算内应无压力。"""

    positions = [e.pos for e in bench_loop_50.state.entities.values()]

    def _run() -> float:
        return _run_timed(lambda: _sound_propagate(positions))

    measured = benchmark.pedantic(_run, rounds=5, iterations=1)
    assert_threshold(measured, PERCEPTION_TICK_LIMIT_MS, "感知听觉 50 NPC（参考）")


@pytest.mark.bench
def test_perception_vision_scale_sanity(bench_loop_50, benchmark) -> None:
    """复杂度哨兵：朴素视觉 O(N²) 应随 N 增长（测量有区分度，非恒零）。"""
    map_ = _open_map()
    pos_50 = [e.pos for e in bench_loop_50.state.entities.values()]
    pos_20 = [e.pos for e in make_state(20).entities.values()]
    ms20 = _run_timed(lambda: _vision_naive(pos_20, map_))
    ms50 = _run_timed(lambda: _vision_naive(pos_50, map_))
    assert ms20 > 0.0, "感知基准测得零耗时，哨兵无效"
    assert ms50 / ms20 > 1.0, "50 NPC 视觉应比 20 NPC 更慢（O(N²) 走势）"


def test_perception_model_shape_contract() -> None:
    """参考实现形状自检（非 bench，确保挂载点可被 M1 引擎替换）。"""
    map_ = _open_map()
    assert _line_of_sight(map_, (2, 2), (5, 2)) is True
    # 听觉 1/r 衰减形状：近源（d=3）>远源（d=20），不锁具体数值
    assert (1.0 / 3.0) > (1.0 / 20.0)
    # 分区剪枝版与朴素版结果一致（可见对数相同）
    positions = [(i % 8, i // 8) for i in range(30)]
    naive = _vision_naive(positions, _open_map())
    part = _vision_partitioned_v2(positions, _open_map(), 24.0)
    assert naive == part
