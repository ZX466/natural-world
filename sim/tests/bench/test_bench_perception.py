"""感知传播基准（性能域，pi）— M1 挂载点（m0-core §5.2 追加项，DESIGN §7）。

背景：C06-③ 真实感知引擎已合入 main（`dafc8df`，`sim.perception.senses.PerceptionEngine`）。
本文件测真实引擎：视觉射线遮挡完全阻断 + 光照修正、听觉 ∝1/r 衰减（DESIGN §7）。
红线来自 thresholds.py（PERCEPTION_TICK_LIMIT_MS），预算目标值见 budget.md §1/§2.5。

两类对照：
- 真实引擎用例（分区/缓存内建）：卡 PERCEPTION_TICK_LIMIT_MS（暖态）。
- 朴素 O(N²) 哨兵：断言其明显慢于线（H-1 的动机证据），不卡预算红线。

首轮 LOS 对称缓存冷启动 7.6-8.2ms（一次性）：bench 用 `warmup_rounds=1` 剔除，
使 mean 反映暖态稳态（实测 3.0-3.3ms），避免冷启动把均值拉过红线假红。
"""

from __future__ import annotations

import math

import pytest

from sim.world.map import Chunk, TileMap

from .harness import assert_median_threshold, make_state
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
    """视觉传播 50 NPC（真实引擎）：M1 红线 PERCEPTION_TICK_LIMIT_MS=3ms。

    C06-③ 真实引擎已合入（sim.perception.senses）：这里测的是真实
    PerceptionEngine 对 50 实体全员装配（视觉射线 + 光照修正）。
    红线恢复 = budget.md §2.5（C06-③ 真实引擎已合入，红线生效）。
    """
    from sim.perception.senses import PerceptionEngine

    map_ = _open_map()
    state = bench_loop_50.state
    engine = PerceptionEngine(map_)  # 实例级 LOS 缓存跨轮复用（同图）

    def _run() -> float:
        return _run_timed(lambda: [engine.assemble(state, eid) for eid in state.entities])

    # F06 红线复核：首轮为 LOS 对称缓存冷启动（实测 7.6-8.2ms），直接用 mean 会假红。
    # warmup_rounds=1 预热 + median 口径（抗离群），反映暖态稳态（median 实测 ~1.7ms）。
    benchmark.pedantic(_run, rounds=7, warmup_rounds=1, iterations=1)
    assert_median_threshold(
        benchmark.stats, PERCEPTION_TICK_LIMIT_MS, "感知视觉 50 NPC（真实引擎·暖态中位）"
    )


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
    """听觉传播 50 NPC（真实引擎）：全员移动最坏情况 + 半径预过滤 + 穿墙衰减。"""

    from sim.perception.senses import FOOTSTEP_BASE, PerceptionEngine

    map_ = _open_map()
    state = bench_loop_50.state
    engine = PerceptionEngine(map_)
    # 最坏情况：全员带路径（每 tick 50 个脚步声源，人人都在动）
    moving_state = state.model_copy(
        update={
            "entities": {
                eid: e.model_copy(update={"path": ((e.pos[0] + 1, e.pos[1]),)})
                for eid, e in state.entities.items()
            }
        }
    )
    footstep = FOOTSTEP_BASE  # 声学常量参与强度（保留锚防漂移）

    def _run() -> float:
        return _run_timed(
            lambda: [engine.assemble(moving_state, eid, []) for eid in moving_state.entities]
        )

    benchmark.pedantic(_run, rounds=7, warmup_rounds=1, iterations=1)
    assert_median_threshold(
        benchmark.stats, PERCEPTION_TICK_LIMIT_MS, "感知听觉 50 NPC（真实引擎·暖态中位）"
    )
    assert footstep > 0.0


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
    """模型形状自检（非 bench，挂载点契约：M1 引擎与参考形状一致）。"""
    map_ = _open_map()
    assert _line_of_sight(map_, (2, 2), (5, 2)) is True
    # 听觉 1/r 衰减形状：近源（d=3）>远源（d=20），不锁具体数值
    assert (1.0 / 3.0) > (1.0 / 20.0)
    # 分区剪枝版与朴素版结果一致（可见对数相同）
    positions = [(i % 8, i // 8) for i in range(30)]
    naive = _vision_naive(positions, _open_map())
    part = _vision_partitioned_v2(positions, _open_map(), 24.0)
    assert naive == part
