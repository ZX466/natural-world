"""7 日自转长跑预压测（性能域，pi）— M2-P2。

范围（task M2-P2 第 3 项）：现 bench 脚手架模拟 50 NPC × 万级 tick 采样段，
暴露 O(n) 累积 / 内存泄漏。实现未落地 → 用 mock 动作集（`soak.make_mock_feeder`
的确定性错峰 MOVE 喂给，等价 npc.actions 的 `move`）。

量纲：DESIGN §10「1 tick = 1 游戏秒」⇒ 7 游戏日 = 604,800 tick（`M2_ACCEPTANCE_TICKS`）。
分级（对齐 docs/perf/m2-acceptance.md §3 降采样断言策略）：
- **每提交 CI**（未标 `bench` 的用例）：1,200 tick 缩样冒烟 + 探针/量纲契约。
- **nightly**（标 `@pytest.mark.bench`）：30,000 tick 长跑稳定性 + 稳态 p99 + 缓存有界 + 确定性。
- **里程碑/手动**：604,800 tick 完整跑（nightly 新 job，接法提案见 docs/perf/m2-acceptance.md §4）。

红线来自 thresholds.py（SOAK_*）。口径：**分窗稳定性**而非单轮 p99——
长跑单窗口离群（GC/OS 抖动）不误红，只看末窗相对首稳态窗的漂移与内存/句柄/缓存增长。
"""

from __future__ import annotations

import os

import pytest

from sim.core.clock import GameClock
from sim.core.tick import TickLoop
from sim.core.world import TickContext, build_default_bus
from sim.world.map import Chunk, TileMap
from sim.world.pathfinding import Pathfinder

from .harness import make_state
from .soak import (
    M2_ACCEPTANCE_TICKS,
    TICKS_PER_GAME_DAY,
    make_mock_feeder,
    perception_cache_sizes,
    run_soak,
    sample_proc,
)
from .thresholds import (
    SOAK_GC_OBJECT_GROWTH_LIMIT,
    SOAK_HANDLE_GROWTH_LIMIT,
    SOAK_MEAN_DRIFT_RATIO_LIMIT,
    SOAK_RSS_GROWTH_LIMIT_MB,
    SOAK_STEADY_MEAN_LIMIT_MS,
    TICK_P99_LIMIT_MS,
)

_MAP_W = 64
_MAP_H = 64
N_NPC = 50
# CI 冒烟：1,200 tick 分 3 窗（本机 ~2s），只验证「框架可跑 + 契约成立」。
_CI_SOAK_TICKS = 1_200
_CI_WINDOW_TICKS = 400
# nightly 长跑：30,000 tick 分 5 窗（本机 ~1 min），验稳态漂移/p99/缓存。
_NIGHTLY_SOAK_TICKS = 30_000
_NIGHTLY_WINDOW_TICKS = 6_000


def _open_map() -> TileMap:
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


def _build_loop_with_perception() -> TickLoop:
    """50 NPC + 感知挂载（真实引擎）+ 寻路器——最接近 M2 验收内核形态。"""
    from sim.perception.senses import run_perception_step

    tile_map = _open_map()
    loop = TickLoop(
        clock=GameClock(speed=1.0),
        bus=build_default_bus(),
        state=make_state(N_NPC, grid_w=_MAP_W, grid_h=_MAP_H),
        context=TickContext(),
        pathfinder=Pathfinder(tile_map),
    )
    loop.attach_perception(
        lambda state, tick_events: run_perception_step(state, tile_map, tick_events)
    )
    return loop


def _assert_no_runaway(result, *, label: str) -> None:
    """长跑稳定性断言（分窗口径，抗单窗离群）。"""
    windows = result.windows
    assert len(windows) >= 2, f"{label}: 窗口数不足（{len(windows)}），无法判漂移"
    # 单窗均值不超过长跑稳态上限（含感知的全内核）
    for w in windows:
        assert w.mean_ms <= SOAK_STEADY_MEAN_LIMIT_MS, (
            f"{label}: 窗口 @{w.start_tick} 均值 {w.mean_ms:.3f}ms "
            f"> 上限 {SOAK_STEADY_MEAN_LIMIT_MS}ms"
        )
    # 漂移：末窗均值 / 首稳态窗均值（首窗含冷启动，用第 2 窗作基线）
    base = windows[1].mean_ms
    last = windows[-1].mean_ms
    if base > 0:
        ratio = last / base
        assert ratio <= SOAK_MEAN_DRIFT_RATIO_LIMIT, (
            f"{label}: 均值漂移 {ratio:.2f}x > {SOAK_MEAN_DRIFT_RATIO_LIMIT}x"
            f"（末窗 {last:.3f}ms / 基线 {base:.3f}ms）——疑似 O(n) 累积"
        )
    # 内存 / GC 对象 / 句柄增长（探测不可用返回 -1 时跳过）
    first, final = windows[0], windows[-1]
    if first.end_rss_mb >= 0 and final.end_rss_mb >= 0:
        growth = final.end_rss_mb - first.end_rss_mb
        assert growth <= SOAK_RSS_GROWTH_LIMIT_MB, (
            f"{label}: RSS 增长 {growth:.1f}MB > {SOAK_RSS_GROWTH_LIMIT_MB}MB（疑似泄漏）"
        )
    gc_growth = final.end_gc_objects - first.end_gc_objects
    assert gc_growth <= SOAK_GC_OBJECT_GROWTH_LIMIT, (
        f"{label}: GC 对象增长 {gc_growth} > {SOAK_GC_OBJECT_GROWTH_LIMIT}（疑似泄漏）"
    )
    if first.end_handles >= 0 and final.end_handles >= 0:
        h_growth = final.end_handles - first.end_handles
        assert h_growth <= SOAK_HANDLE_GROWTH_LIMIT, (
            f"{label}: 句柄增长 {h_growth} > {SOAK_HANDLE_GROWTH_LIMIT}（疑似句柄泄漏）"
        )
    # 实体数不漂移（长跑中 NPC 集合应稳定）
    assert result.entity_count_end == result.entity_count_start, (
        f"{label}: 实体数漂移 {result.entity_count_start} → {result.entity_count_end}"
    )


def test_soak_ci_smoke_stability() -> None:
    """CI 冒烟：50 NPC × 1,200 tick 分窗稳定性（框架可跑 + 无界增长契约成立）。"""
    loop = _build_loop_with_perception()
    result = run_soak(
        loop,
        ticks=_CI_SOAK_TICKS,
        window_ticks=_CI_WINDOW_TICKS,
        feeder=make_mock_feeder(_MAP_W, _MAP_H),
    )
    _assert_no_runaway(result, label="M2 长跑 CI 冒烟")


@pytest.mark.bench
def test_soak_nightly_determinism_seeded() -> None:
    """nightly：同 seed 两轮长跑的状态指纹逐位一致（C5 对长跑同样适用）。"""
    a = _build_loop_with_perception()
    b = _build_loop_with_perception()
    run_soak(a, ticks=3_000, window_ticks=3_000, feeder=make_mock_feeder(_MAP_W, _MAP_H))
    run_soak(b, ticks=3_000, window_ticks=3_000, feeder=make_mock_feeder(_MAP_W, _MAP_H))
    assert a.state.state_hash() == b.state.state_hash()


def test_soak_probe_is_available_or_gracefully_unknown() -> None:
    """进程探针契约：可用则给出有效值，不可用返回 -1（不误红）。"""
    p = sample_proc()
    assert p.gc_objects > 0
    assert p.rss_mb == -1.0 or p.rss_mb > 0.0
    assert p.handles == -1 or p.handles > 0


def test_m2_acceptance_tick_constant_is_7_days() -> None:
    """量纲守卫：M2 验收 = 7 游戏日 = 604,800 tick（DESIGN §10/§17）。"""
    assert M2_ACCEPTANCE_TICKS == 604_800


@pytest.fixture(scope="module")
def nightly_soak_result():
    """模块级缓存：nightly 30,000 tick 长跑只跑一次，多个断言共享（省 2× 墙钟）。"""
    loop = _build_loop_with_perception()
    result = run_soak(
        loop,
        ticks=_NIGHTLY_SOAK_TICKS,
        window_ticks=_NIGHTLY_WINDOW_TICKS,
        feeder=make_mock_feeder(_MAP_W, _MAP_H),
    )
    return loop, result


@pytest.mark.bench
def test_soak_nightly_longrun_stability(nightly_soak_result) -> None:
    """nightly：50 NPC × 30,000 tick 分窗稳定性（无 O(n) 累积/内存/句柄泄漏）。"""
    _loop, result = nightly_soak_result
    _assert_no_runaway(result, label="M2 长跑 nightly 30k")


@pytest.mark.bench
def test_soak_nightly_steady_p99_below_tick_line(nightly_soak_result) -> None:
    """nightly：稳态每窗 p99 ≤ tick p99 红线 8.3ms。"""
    _loop, result = nightly_soak_result
    # 首窗含冷启动，从第 2 窗起判
    for w in result.windows[1:]:
        assert w.p99_ms <= TICK_P99_LIMIT_MS, (
            f"长跑稳态窗口 @{w.start_tick} p99 {w.p99_ms:.3f}ms > {TICK_P99_LIMIT_MS}ms"
        )


@pytest.mark.bench
def test_soak_nightly_caches_bounded(nightly_soak_result) -> None:
    """nightly：长跑后感知实例缓存有界（LOS 对称缓存封顶 _LOS_CACHE_MAX=65536）。"""
    _loop, _result = nightly_soak_result
    sizes = perception_cache_sizes()
    for name, size in sizes.items():
        assert size <= 65_536, f"缓存 {name} 无界增长: {size}"
    assert sizes.get("rtoken", 0) <= N_NPC


@pytest.mark.bench
@pytest.mark.skipif(
    os.environ.get("PI_M2_FULL_SOAK") != "1",
    reason=(
        "完整 7 日跑（604,800 tick，~min 级）默认跳过；置 PI_M2_FULL_SOAK=1 触发"
        "（见 docs/perf/m2-acceptance.md §4）"
    ),
)
def test_m2_full_7day_acceptance() -> None:
    """里程碑：604,800 tick（50 NPC × 7 游戏日）完整跑无崩溃 + 资源有界。

    不经每提交 CI（超 timeout-minutes: 15 护栏）；nightly 接法由 cline 裁决
    （docs/perf/m2-acceptance.md §4）。环境门避免 nightly 默认就烧分钟级。
    """
    loop = _build_loop_with_perception()
    result = run_soak(
        loop,
        ticks=M2_ACCEPTANCE_TICKS,
        window_ticks=TICKS_PER_GAME_DAY,  # 每游戏日一窗（7 窗）
        feeder=make_mock_feeder(_MAP_W, _MAP_H),
    )
    _assert_no_runaway(result, label="M2 7 日自转完整跑")
    assert result.total_ticks == M2_ACCEPTANCE_TICKS
