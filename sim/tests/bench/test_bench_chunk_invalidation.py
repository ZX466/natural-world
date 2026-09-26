"""C3 chunk 失效通路基准（性能域，pi）— M3-P3 bench 收口（C3 通路纳入观察）。
背景：C3 chunk 失效通路已收编 main `5724aa7`（`sim/world/pathfinding.py`
`Pathfinder.observe_events` / `invalidate_dirty` / `observe_map` + `TileMap` 脏集）。
此前**无 perf 预算覆盖** —— 按惯例新热路径要有数（M3-P3 任务书）。
口径：与 `test_bench_retrieval.py` 同源 —— 暖态中位（`warmup_rounds=1` + median）、
固定 seed、开阔图（无遮挡 → 路径/失效成本取同条件最坏）。
两段成本拆开测：
  ① `event_tile_position` 纯函数本身 —— 每 tick 对**全事件流**遍历一遍的开销上界；
  ② `observe_events` 失效本体 —— 标脏 → `drain_dirty` → 逐 chunk `PathCache.invalidate`
     （「剔 N 留 M」：只删途经脏 chunk 的条目）。
**状态：裁 13 已裁（2026-09-25 全采）**，bench 侧维持 `_record_proposal` 观察态——
本文件常量 `CHUNK_EVENT_SCAN_LIMIT_MS` /
`CHUNK_INVALIDATION_TICK_LIMIT_MS` 是 pi 实测后的**提案值**（见 docs/perf/
m3-retrieval-budget.md 附录 M3-P3），Claude 裁前**不卡 CI 红**：用 `_record_proposal`
只记录「实测中位 vs 提案阈值」，裁后按 M3-P2 先例转 `harness.assert_median_threshold`。
失效本体是**消费式**的（标脏即 drain、剔除即删），故每轮前用 `setup` 复原缓存快照，
计时窗口只含失效通路（不含 A* 回填；A* 单条 ~0.65ms，属寻路本身、不在本通路内）。
"""
from __future__ import annotations

import pytest
import structlog

from sim.core.events import EventKind, matter_event, move_event
from sim.world.map import CHUNK_SIZE, Chunk, TileMap
from sim.world.pathfinding import Pathfinder, event_tile_position

from .thresholds import CHUNK_EVENT_SCAN_LIMIT_MS, CHUNK_INVALIDATION_TICK_LIMIT_MS

logger = structlog.get_logger(__name__)

# 48×48 图 = 3×3 = 9 chunk（任务书指定尺幅；与 test_m3_chunk_invalidation.py 同尺）
_MAP_W = 48
_MAP_H = 48
#: 失效成本的主尺度：一批定位事件数（= tick p99 事件量级，budget.md §2.3）
_BATCH = 50
#: 每 tick 全事件流代表量：150 MOVE（无关 kind）+ 50 定位 matter
_TICK_IRRELEVANT = 150
#: 缓存规模档位（条路径）
_PATHS_100 = 100
_PATHS_1000 = 1000
#: 上界档位：`PathCache.max_entries`（合成条目打满，真实键空间在 48×48 上到不了 4096）
_CACHE_MAX = 4096


def _open_map() -> TileMap:
    """全通行 48×48 图（基准用理想图：无遮挡，路径长度/失效扫描取同条件最坏）。"""
    chunks: dict[tuple[int, int], Chunk] = {}
    for cy in range((_MAP_H + CHUNK_SIZE - 1) // CHUNK_SIZE):
        for cx in range((_MAP_W + CHUNK_SIZE - 1) // CHUNK_SIZE):
            chunks[(cx, cy)] = Chunk(
                cx=cx,
                cy=cy,
                ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
    return TileMap(width=_MAP_W, height=_MAP_H, chunks=chunks)


def _unique_pairs(n: int) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """确定性生成 n 个唯一 (start, goal) 对（stride 洗牌；无 RNG，天然可复现）。"""
    out: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for r in range(_MAP_H - 2):
        for c in range(_MAP_W - 2):
            g = (max(c + 1, (c + 17) % _MAP_W), max(r + 1, (r + 23) % _MAP_H))
            if (r, c) != g:
                out.append(((r, c), g))
    stride = 97
    out = [out[(i * stride) % len(out)] for i in range(len(out))]
    return out[:n]


def _located_batch(n: int = _BATCH) -> list:
    """n 条定位 MATTER_BUILD 事件（x/y≥0 → 标脏所在 chunk）。"""
    return [
        matter_event(0, EventKind.MATTER_BUILD, f"m{i}", x=(i * 5) % _MAP_W, y=(i * 3) % _MAP_H)
        for i in range(n)
    ]


def _mixed_batch(n: int = _BATCH) -> list:
    """n 条半定位事件：偶 BUILD（定位）+ 奇 DECAY（x/y=-1 未定位，不标脏）。"""
    evs = []
    for i in range(n):
        if i % 2 == 0:
            evs.append(
                matter_event(
                    0, EventKind.MATTER_BUILD, f"m{i}", x=(i * 5) % _MAP_W, y=(i * 3) % _MAP_H
                )
            )
        else:
            evs.append(matter_event(0, EventKind.MATTER_DECAY, f"m{i}", x=-1, y=-1))
    return evs


def _tick_event_batch(n_located: int = _BATCH, n_irrelevant: int = _TICK_IRRELEVANT) -> list:
    """典型 tick 全事件流：n_irrelevant 条无关 MOVE + n_located 条定位 matter。"""
    evs = [
        move_event(0, f"e{i}", (0, 0), (1, 1), ((0, 0), (1, 1))) for i in range(n_irrelevant)
    ]
    evs.extend(_located_batch(n_located))
    return evs


def _record_proposal(
    meta: object, limit_ms: float, label: str, extra: dict[str, float | int] | None = None
) -> None:
    """提案待裁口径（M3-P3）：只记录「实测中位 vs 提案阈值」，**不断言**。

    Claude 裁后按 M3-P2 先例换成 `harness.assert_median_threshold`（定标机硬断言 /
    `PI_BENCH_ADVISORY=1` 只记录）。测量口径与其它 bench 完全一致（暖态中位）。
    """
    stats = meta.stats  # type: ignore[attr-defined]
    median_ms = stats.median * 1000.0
    mean_ms = stats.mean * 1000.0
    exceeded = median_ms > limit_ms
    logger.info(
        "bench.chunk_invalidation.proposal",
        label=label,
        median_ms=round(median_ms, 4),
        mean_ms=round(mean_ms, 4),
        limit_ms=limit_ms,
        exceeded=exceeded,
        delta_ms=round(median_ms - limit_ms, 4),
        **(extra or {}),
    )


class _InvalidationBenchWorld:
    """失效通路基准世界：48×48 开阔图 + Pathfinder + 预填缓存快照。

    失效本体是消费式的（标脏即 drain、剔除即删），故构造时把缓存字典**快照**一份，
    每轮 `restore()` 复原 —— 计时窗口只含失效通路。
    """

    def __init__(self, n_paths: int) -> None:
        self.pf = Pathfinder(_open_map())
        for s, g in _unique_pairs(n_paths):
            try:
                self.pf.find(s, g)
            except ValueError:  # pragma: no cover — 开阔图不会不可达
                continue
        self.snapshot = dict(self.pf.cache.entries)
        self.n_entries = len(self.snapshot)

    def restore(self) -> None:
        self.pf.cache.entries.clear()
        self.pf.cache.entries.update(self.snapshot)

    def synthetic_fill(self, n_entries: int, n_chunks: int) -> None:
        """合成 n_entries 条条目（路径空、途经 chunk 轮流落在 n_chunks 个 chunk 上）。

        真实键空间在 48×48 上最多 2116 个唯一 (start, goal)，够不到
        `PathCache.max_entries=4096` —— 上界档位用合成条目打满缓存。
        """
        entries: dict[tuple[tuple[int, int], tuple[int, int]], tuple] = {}
        for i in range(n_entries):
            key = ((i % 4096, (i // 4096) % 4096), (i % 4096 + 1, (i // 4096) % 4096 + 1))
            entries[key] = ((), frozenset({(i % n_chunks, (i // n_chunks) % 16)}))
        self.pf.cache.entries = entries
        self.snapshot = dict(entries)
        self.n_entries = n_entries


# ---------------------------------------------------------------------------
# ① event_tile_position 纯函数（每 tick 全事件遍历的开销上界）
# ---------------------------------------------------------------------------
@pytest.mark.bench
def test_event_tile_position_full_tick_scan(benchmark) -> None:
    """`event_tile_position` 遍历典型 tick 全事件流（150 无关 + 50 定位）的上界。

    实测（48×48，暖态中位）：50 定位 0.007ms / 200 混合 0.036ms / 1000 无关 0.054ms
    / 5000 无关 0.267ms → 约 0.06ms/千事件。提案 0.10ms 覆盖 ~1800 事件/tick
    （稳态 ~20/tick 与 p99 50 均在其内，budget.md §2.3）。破限 = 事件流异常暴涨，
    查事件来源（非本通路退化）。
    """
    events = _tick_event_batch()

    def _run() -> int:
        return sum(1 for ev in events if event_tile_position(ev) is not None)

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=1)
    _record_proposal(
        benchmark.stats,
        CHUNK_EVENT_SCAN_LIMIT_MS,
        "event_tile_position 全 tick 事件遍历（150 无关+50 定位）",
        {"events": len(events), "located": sum(1 for ev in events if event_tile_position(ev))},
    )


# ---------------------------------------------------------------------------
# ② observe_events 失效本体（剔 N 留 M）
# ---------------------------------------------------------------------------
@pytest.mark.bench
def test_chunk_invalidation_50_events_100_paths(benchmark) -> None:
    """失效通路主口径：100 条真实缓存路径 + 50 定位事件（≈9 脏 chunk）。

    实测暖态中位 ~0.076ms（100 条）。提案红线按上界档（cache 打满 max_entries）给，
    见下一条；本用例给常态规模的数量级参照。
    """
    world = _InvalidationBenchWorld(_PATHS_100)
    events = _located_batch()
    benchmark.pedantic(
        lambda: world.pf.observe_events(events),
        rounds=9,
        warmup_rounds=1,
        iterations=1,
        setup=world.restore,
    )
    _record_proposal(
        benchmark.stats,
        CHUNK_INVALIDATION_TICK_LIMIT_MS,
        "observe_events 失效本体（100 路径 / 50 定位事件）",
        {"cache": world.n_entries, "events": len(events)},
    )


@pytest.mark.bench
def test_chunk_invalidation_50_events_1000_paths(benchmark) -> None:
    """失效通路 ∝ 缓存规模：1000 条缓存路径 + 50 定位事件（实测暖态中位 ~0.32ms）。"""
    world = _InvalidationBenchWorld(_PATHS_1000)
    events = _located_batch()
    benchmark.pedantic(
        lambda: world.pf.observe_events(events),
        rounds=9,
        warmup_rounds=1,
        iterations=1,
        setup=world.restore,
    )
    _record_proposal(
        benchmark.stats,
        CHUNK_INVALIDATION_TICK_LIMIT_MS,
        "observe_events 失效本体（1000 路径 / 50 定位事件）",
        {"cache": world.n_entries, "events": len(events)},
    )


@pytest.mark.bench
def test_chunk_invalidation_50_events_cache_ceiling(benchmark) -> None:
    """失效通路上界口径：缓存打满 `PathCache.max_entries=4096` + 50 定位事件（≈9 脏 chunk）。

    实测暖态中位 ~1.18ms。这是提案红线 `CHUNK_INVALIDATION_TICK_LIMIT_MS=2.0` 的定标依据
    （1.18 + 慢机余量 ~1.7x）。成本 ∝ 缓存条数 × 脏 chunk 数（`invalidate` 逐 chunk
    全表扫一遍）：若 M4 起缓存上界调大或图尺扩大，按此档位重新对账。
    """
    world = _InvalidationBenchWorld(_PATHS_100)
    world.synthetic_fill(_CACHE_MAX, n_chunks=9)
    events = _located_batch()
    benchmark.pedantic(
        lambda: world.pf.observe_events(events),
        rounds=9,
        warmup_rounds=1,
        iterations=1,
        setup=world.restore,
    )
    _record_proposal(
        benchmark.stats,
        CHUNK_INVALIDATION_TICK_LIMIT_MS,
        "observe_events 失效本体（4096 缓存打满 / 50 定位事件）",
        {"cache": world.n_entries, "events": len(events)},
    )


@pytest.mark.bench
def test_chunk_invalidation_full_dirty_degraded_probe(benchmark) -> None:
    """退化哨兵（观察项、无红线）：缓存打满 + **全 chunk 脏**（每 chunk 一条定位事件）。

    实测（48×48，9 chunk）暖态中位 ~1.1ms，与常态同量级（脏集合上限 = chunk 数）；
    但 128×128=64 chunk 全脏实测 ~10ms = tick 预算 16.6ms 的 **60%** —— 这是
    「一张大图全图同时变脏」的上界。当前无形态触发（定位事件每 tick ~p99 50 条，
    且 48×48 只有 9 chunk），故不设红线；若 M4 起出现「全图重绘 / 批量建造」形态，
    按此档位复核（失效是逐 chunk 全表扫，非全清）。
    """
    world = _InvalidationBenchWorld(_PATHS_100)
    world.synthetic_fill(_CACHE_MAX, n_chunks=9)
    # 每 chunk 一条定位事件 → 全图脏
    events = [
        matter_event(0, EventKind.MATTER_BUILD, f"m{cy * 3 + cx}", x=cx * 16, y=cy * 16)
        for cy in range(3)
        for cx in range(3)
    ]
    benchmark.pedantic(
        lambda: world.pf.observe_events(events),
        rounds=9,
        warmup_rounds=1,
        iterations=1,
        setup=world.restore,
    )
    _record_proposal(
        benchmark.stats,
        CHUNK_INVALIDATION_TICK_LIMIT_MS,
        "observe_events 退化哨兵（4096 缓存 / 全 9 chunk 脏）",
        {"cache": world.n_entries, "events": len(events)},
    )


@pytest.mark.bench
def test_chunk_invalidation_mixed_batch_half_unlocated(benchmark) -> None:
    """半定位事件批（50 条：25 定位 + 25 x/y=-1）对照实测（暖态中位 ~0.056ms）。

    未定位哨兵不标脏（C4 域约束）→ 脏 chunk 数减半、失效成本随之减半。
    测的是「事件里混多少未定位」对失效通路的敏感度。
    """
    world = _InvalidationBenchWorld(_PATHS_100)
    events = _mixed_batch()
    benchmark.pedantic(
        lambda: world.pf.observe_events(events),
        rounds=9,
        warmup_rounds=1,
        iterations=1,
        setup=world.restore,
    )
    _record_proposal(
        benchmark.stats,
        CHUNK_INVALIDATION_TICK_LIMIT_MS,
        "observe_events 失效本体（100 路径 / 25 定位+25 未定位）",
        {"cache": world.n_entries, "events": len(events)},
    )


def test_probe_world_shape_contract() -> None:
    """基准世界形状契约（非 bench）：避免测量口径悄悄漂移。"""
    world = _InvalidationBenchWorld(_PATHS_100)
    assert world.n_entries == _PATHS_100
    # 48×48 = 3×3 chunk；50 定位事件铺满全部 9 个
    assert _open_map().chunks_x == 3 and _open_map().chunks_y == 3
    located = _located_batch()
    chunks_hit = {
        _open_map().chunk_of(int(ev.payload["x"]), int(ev.payload["y"])) for ev in located
    }
    assert len(chunks_hit) == 9
    # 未定位事件确实不产出坐标（哨兵语义）
    assert all(event_tile_position(ev) is None for ev in _mixed_batch()[1::2])
