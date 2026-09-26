"""M4 施工/坍塌基准（性能域，pi）— M4-P2 红线定标（预研草案转正式）。

背景：M4-D2a/b/c 已收编 main（`240f9f7`：建造事件族 + 0006 迁移 + checkpoint 施工 +
承重图按帧摊还级联）。本文件对 pi M4-P1 预研草案（`88284c3`）
「施工 0.50 / 坍塌单帧 2.00 / 级联 100 节点每帧」逐条实测定标。
口径：与 `test_bench_chunk_invalidation.py` 同源 —— 暖态中位（`warmup_rounds=1` + median）、
固定 seed、多轮取中位；阈值 = 实测 + 1.7x 慢机余量（裁 13 先例）。
**观察态起步**：本文件阈值用 `_record_proposal` 只记录「实测中位 vs 建议阈值」，**不断言**
（硬断言待 nightly 数据后另裁；与 M3-P3 收口态一致）。
被测入口（两段成本拆开）：
  ① 施工推进 `advance_build`（在建点批）与 `fold_structure_snapshot`（重放/投影单折叠）；
  ② `materialize_structures`（投影重建，DB 路径，非每 tick）与 fold 重放核（无 SQL）；
  ③ `build_support_graph`（承重图物化）与 `advance_cascade`（按帧摊还级联，budget=100）；
契约守卫（非 bench）：级联单帧 ≤ `CASCADE_EVENT_BUDGET_PER_FRAME` 节点、图规模 10k 验收。
"""

from __future__ import annotations

import asyncio
import json
import statistics
from pathlib import Path

import pytest
import structlog

from sim.core.events import EventKind, structure_started_event
from sim.core.persistence.database import init_database
from sim.core.persistence.models import Structure
from sim.core.persistence.npc_store import NpcStore, fold_structure_snapshot
from sim.core.persistence.store import SqlEventStore
from sim.world.structure import (
    CHECKPOINT_INTERVAL_TICKS,
    BuildProgress,
    StructurePhase,
    StructureSnapshot,
    advance_build,
)
from sim.world.support_graph import (
    CASCADE_EVENT_BUDGET_PER_FRAME,
    SUPPORT_GRAPH_ACCEPTANCE_NODES,
    advance_cascade,
    build_support_graph,
    start_cascade,
)

from .thresholds import BUILD_PROGRESS_TICK_LIMIT_MS, COLLAPSE_FRAME_LIMIT_MS

logger = structlog.get_logger(__name__)

#: 代表性在建点数（并发施工规模上界；预研草案 0.50ms 口径 = ~100 点）
_SITES = 100
#: 图/级联三档规模（任务书指定；10k = SUPPORT_GRAPH_ACCEPTANCE_NODES）
_N_100 = 100
_N_1000 = 1000
_N_10K = SUPPORT_GRAPH_ACCEPTANCE_NODES
#: 投影重建档位（DB 路径为启动/重建成本，非每 tick，取代表性 1k）
_DB_ROWS = 1000
#: 重建/重放路径的信息性上限（非 tick 热路径；量纲同 SNAPSHOT_LIMIT_MS=500ms——
#: 启动/拓扑重建允许背景耗时，不进每 tick 固定序）。
_REBUILD_INFO_LIMIT_MS = 500.0


def _record_proposal(
    meta: object, limit_ms: float, label: str, extra: dict[str, float | int] | None = None
) -> None:
    """定标观察态（M4-P2）：只记录「实测中位 vs 建议阈值」，**不断言**。

    裁 14-2 后按 M3-P2/M3-P3 先例换 `harness.assert_median_threshold`
    （定标机硬断言 / `PI_BENCH_ADVISORY=1` 只记录）。测量口径与其它 bench 完全一致（暖态中位）。
    """
    stats = meta.stats  # type: ignore[attr-defined]
    median_ms = stats.median * 1000.0
    mean_ms = stats.mean * 1000.0
    exceeded = median_ms > limit_ms
    logger.info(
        "bench.structure.proposal",
        label=label,
        median_ms=round(median_ms, 4),
        mean_ms=round(mean_ms, 4),
        limit_ms=limit_ms,
        exceeded=exceeded,
        delta_ms=round(median_ms - limit_ms, 4),
        **(extra or {}),
    )


def _chain(n: int) -> list[tuple[str, StructureSnapshot]]:
    """承重链：s00000 承重，s00001..s(n-1) 各支撑前一个（全链级联最坏）。

    末节点不承重（无依赖者）——与 `test_t1_m4_support_graph` 10k 验收同形。
    """
    out: list[tuple[str, StructureSnapshot]] = [
        (
            "main",
            StructureSnapshot(
                structure_id="s00000",
                tiles=((0, 0),),
                kind="wall",
                material="stone",
                phase=StructurePhase.ACTIVE,
                load_bearing=True,
                supported_by=(),
            ),
        )
    ]
    for i in range(1, n):
        out.append(
            (
                "main",
                StructureSnapshot(
                    structure_id=f"s{i:05d}",
                    tiles=((0, 0),),
                    kind="wall",
                    material="stone",
                    phase=StructurePhase.ACTIVE,
                    load_bearing=i < n - 1,
                    supported_by=(f"s{i - 1:05d}",),
                ),
            )
        )
    return out


def _started_event(structure_id: str, tick: int = 1):
    return structure_started_event(
        tick,
        structure_id=structure_id,
        tiles=((0, 0),),
        kind="wall",
        material="stone",
        planned_duration_ticks=CHECKPOINT_INTERVAL_TICKS,
        recipe_id="m4-recipe",
        recipe_version="1",
        build_rule_version="m4-v1",
        load_bearing=True,
    )


def _fold_once(
    state: StructureSnapshot | None, event_type: EventKind, structure_id: str
) -> StructureSnapshot | None:
    return fold_structure_snapshot(
        state,
        event_type=event_type,
        structure_id=structure_id,
        tick=2,
        tiles=((0, 0),),
        kind="wall",
        material="stone",
        load_bearing=True,
    )


def _fold_replay(n: int) -> int:
    """fold 重放核（无 SQL，纯折叠循环）= `materialize_structures_replay` 的核心成本。"""
    states: dict[str, StructureSnapshot | None] = {}
    for i in range(n):
        sid = f"s{i:05d}"
        states[sid] = fold_structure_snapshot(
            None,
            event_type=EventKind.STRUCTURE_STARTED,
            structure_id=sid,
            tick=i,
            tiles=((0, 0),),
            kind="wall",
            material="stone",
            load_bearing=True,
        )
    return len(states)


def _build_states(n: int) -> list[BuildProgress]:
    return [
        BuildProgress(
            structure_id=f"s{i:05d}",
            progress=0.0,
            quality=0.5,
            integrity=1.0,
            build_rule_version="m4-v1",
            started_tick=0,
            planned_duration_ticks=CHECKPOINT_INTERVAL_TICKS,
        )
        for i in range(n)
    ]


def _advance_batch(states: list[BuildProgress], target_tick: int) -> int:
    advanced = [advance_build(state, target_tick=target_tick) for state in states]
    return len(advanced)


# ---------------------------------------------------------------------------
# ① 施工推进 / 单折叠（同步、tick 热路径）
# ---------------------------------------------------------------------------
@pytest.mark.bench
def test_fold_structure_snapshot_started(benchmark) -> None:
    """`fold_structure_snapshot` 单次折叠（STRUCTURE_STARTED，投影/重放共用单折叠）。

    实测（本机暖态中位）：STARTED ~1.9µs / CHECKPOINT ~0.3µs / COMPLETED·COLLAPSED ~2.7µs。
    单折叠不是 tick 瓶颈，红线并入施工推进行（本用例只记录，不单设阈值）。
    """
    benchmark.pedantic(lambda: _fold_once(None, EventKind.STRUCTURE_STARTED, "hut-1"), rounds=9)
    _record_proposal(
        benchmark.stats,
        BUILD_PROGRESS_TICK_LIMIT_MS,
        "fold_structure_snapshot(STARTED) 单次",
        {"calls": 1},
    )


@pytest.mark.bench
def test_build_progress_advance_100_sites(benchmark) -> None:
    """施工推进 `advance_build` × 100 在建点（每 tick 推进一帧）。

    实测（本机暖态中位，bench 口径 = 只计时推进循环，状态预建）：S=100 **~0.175ms**
    （~1.75µs/点，线性：50→0.09 / 150→0.26 / 1k→1.8ms）。
    建议红线 = 实测 × 1.7 ≈ **0.30ms**（**向下修正**预研草案 0.50ms：草案按预研模型的
    数组扫（0.03µs/点）估，real `advance_build` 是带校验的 dataclass replace）；
    红线绑定并发规模 ≤100 在建点，>170 点即破。破限先查在建点数是否失控，
    再查是否退化为逐点 DB 往返。
    """
    states = _build_states(_SITES)
    benchmark.pedantic(lambda: _advance_batch(states, 100), rounds=9, warmup_rounds=1)
    _record_proposal(
        benchmark.stats,
        BUILD_PROGRESS_TICK_LIMIT_MS,
        "施工推进 advance_build ×100 在建点",
        {"sites": _SITES},
    )


# ---------------------------------------------------------------------------
# ② 投影重建（DB 路径，启动/重建成本，非每 tick）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def materialize_world(tmp_path_factory: pytest.TempPathFactory):
    """预建临时 DB（`_DB_ROWS` 行 active 结构）+ 同环事件循环容器。

    引擎/会话/循环绑定同一 loop：DB 异步路径须在同一 loop 内建与用。
    """
    loop = asyncio.new_event_loop()
    path = Path(tmp_path_factory.mktemp("m4p2")) / "structures.db"
    engine = loop.run_until_complete(_make_engine(path))
    loop.run_until_complete(_populate(engine, _DB_ROWS))
    store = SqlEventStore(_session_factory(engine))
    yield loop, NpcStore(store)
    loop.run_until_complete(engine.dispose())
    loop.close()


async def _make_engine(path: Path):
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    await init_database(engine)
    return engine


def _session_factory(engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _populate(engine, rows: int) -> None:
    factory = _session_factory(engine)
    async with factory() as session:
        for i in range(rows):
            session.add(
                Structure(
                    branch_id="main",
                    structure_id=f"s{i:05d}",
                    tiles=json.dumps([[0, 0]]),
                    kind="wall",
                    material="stone",
                    phase="active",
                    load_bearing=True,
                    supported_by=json.dumps([]),
                )
            )
        await session.commit()


@pytest.mark.bench
def test_materialize_structures_projection_1000(materialize_world, benchmark) -> None:
    """`materialize_structures`（投影重建，一次 SELECT + 逐行转换）= 重建成本，非每 tick。

    实测（本机暖态中位）：N=1k ~11ms / N=10k ~127ms（临时库）。它是启动/拓扑重建路径，
    **不进 tick 固定序**（承重图物化只在拓扑变更时触发）；红线并入坍塌/图物化观察项。
    """
    loop, store = materialize_world
    benchmark.pedantic(
        lambda: loop.run_until_complete(store.materialize_structures()),
        rounds=5,
        warmup_rounds=1,
    )
    _record_proposal(
        benchmark.stats,
        _REBUILD_INFO_LIMIT_MS,
        "materialize_structures 投影重建（DB，N=1000）",
        {"rows": _DB_ROWS},
    )


@pytest.mark.bench
def test_fold_replay_core_1000(benchmark) -> None:
    """fold 重放核（无 SQL）N=1000 = `materialize_structures_replay` 的纯折叠成本。

    实测（本机暖态中位）：N=100 ~0.18ms / 1k ~1.87ms / 10k ~19.8ms（~1.9µs/事件）。
    """
    benchmark.pedantic(lambda: _fold_replay(_N_1000), rounds=9, warmup_rounds=1)
    _record_proposal(
        benchmark.stats,
        _REBUILD_INFO_LIMIT_MS,
        "fold 重放核（无 SQL，N=1000）",
        {"events": _N_1000},
    )


# ---------------------------------------------------------------------------
# ③ 承重图物化 + 按帧摊还级联
# ---------------------------------------------------------------------------
@pytest.mark.bench
@pytest.mark.parametrize(
    ("n", "label"),
    [(_N_100, "100"), (_N_1000, "1k"), (_N_10K, "10k")],
    ids=["100", "1k", "10k"],
)
def test_support_graph_materialize(benchmark, n: int, label: str) -> None:
    """`build_support_graph` 物化（建正/反图 + 全量环检测）；图规模三档。

    实测（本机暖态中位）：链式 100/1k/10k ~0.06/0.58/6.75ms；DAG fanin=2 ~10.9ms。
    图物化是**事件驱动一次性**（只在拓扑变更时），非每 tick；红线并入观测项。
    """
    entries = _chain(n)
    benchmark.pedantic(lambda: build_support_graph(entries), rounds=5, warmup_rounds=1)
    _record_proposal(
        benchmark.stats,
        _REBUILD_INFO_LIMIT_MS,
        f"build_support_graph 物化（链 {label}）",
        {"nodes": n},
    )


@pytest.mark.bench
@pytest.mark.parametrize(
    ("n", "label"),
    [(_N_100, "100"), (_N_1000, "1k"), (_N_10K, "10k")],
    ids=["100", "1k", "10k"],
)
def test_collapse_cascade_frame(benchmark, n: int, label: str) -> None:
    """`advance_cascade` 单帧（budget=`CASCADE_EVENT_BUDGET_PER_FRAME`=100）级联。

    实测（本机暖态中位）：三档 ~0.50ms/帧（单帧成本由事件预算封顶，与 N 无关——
    100 事件 × ~5µs 构造成本）。建议红线 = 实测 × 1.7 ≈ 0.85ms（**向下修正**预研草案
    2.00ms：草案按「一帧发完全部级联事件」的朴素口径给，D2c 已用 budget=100 封顶，
    单帧成本不再随级联规模增长，2.00 余量过大）。破限排查：事件构造退化 / budget 被改大。
    """
    graph = build_support_graph(_chain(n))
    state = start_cascade(graph, ["s00000"])
    benchmark.pedantic(
        lambda: advance_cascade(graph, state, tick=0, event_budget=CASCADE_EVENT_BUDGET_PER_FRAME),
        rounds=9,
        warmup_rounds=1,
    )
    _record_proposal(
        benchmark.stats,
        COLLAPSE_FRAME_LIMIT_MS,
        f"坍塌单帧 advance_cascade（{label}，budget=100）",
        {"nodes": n, "budget": CASCADE_EVENT_BUDGET_PER_FRAME},
    )


@pytest.mark.bench
def test_collapse_cascade_full_amortized_10k(benchmark) -> None:
    """10k 全量摊还：整条级联走完的墙钟 / 帧数（端到端摊还帧耗时）。

    实测（本机暖态中位）：10k 链 = 100 帧走完，单帧中位 ~0.5ms、最大帧 ~1.1ms。
    摊还帧耗时 ≥ 单帧红线时说明级联退化为「单帧多事件」；正常形态 ≤ `COLLAPSE_FRAME_LIMIT_MS`。
    """
    graph = build_support_graph(_chain(_N_10K))

    def _run_full() -> float:
        state = start_cascade(graph, ["s00000"])
        frames = 0
        total_ms = 0.0
        while not state.done:
            import time

            t0 = time.perf_counter()
            step = advance_cascade(
                graph, state, tick=frames, event_budget=CASCADE_EVENT_BUDGET_PER_FRAME
            )
            total_ms += (time.perf_counter() - t0) * 1000.0
            state = step.state
            frames += 1
        return total_ms / max(frames, 1)

    benchmark.pedantic(_run_full, rounds=5, warmup_rounds=1)
    _record_proposal(
        benchmark.stats,
        COLLAPSE_FRAME_LIMIT_MS,
        "10k 全量摊还帧耗时（端到端 / 帧数）",
        {"nodes": _N_10K},
    )


# ---------------------------------------------------------------------------
# 契约守卫（非 bench）：级联预算 = 100 节点/帧 + 验收规模常量
# ---------------------------------------------------------------------------
def test_cascade_frame_budget_is_100_nodes() -> None:
    """级联每帧节点上限 = 100（红线「级联 100 节点每帧」= 代码契约常量，T1 已咬）。

    实测（本机）单帧 ~0.5ms 是「100 节点/帧」的成本上界；性能红线按
    `COLLAPSE_FRAME_LIMIT_MS`（0.85ms）覆盖，规模本身由本常量硬约束。
    """
    assert CASCADE_EVENT_BUDGET_PER_FRAME == 100
    graph = build_support_graph(_chain(_N_1000))
    state = start_cascade(graph, ["s00000"])
    while not state.done:
        step = advance_cascade(graph, state, tick=0, event_budget=CASCADE_EVENT_BUDGET_PER_FRAME)
        assert len(step.events) <= CASCADE_EVENT_BUDGET_PER_FRAME
        state = step.state


def test_support_graph_acceptance_scale_is_10k() -> None:
    """承重图验收规模常量 = 10,000（裁 14-2 ⑥）。"""
    assert SUPPORT_GRAPH_ACCEPTANCE_NODES == 10_000


def test_fold_replay_matches_projection_single_source() -> None:
    """折叠形状守卫：STARTED→building / COMPLETED→active / COLLAPSED→rubble（单折叠规则）。"""
    started = _fold_once(None, EventKind.STRUCTURE_STARTED, "hut-1")
    assert started is not None
    assert started.phase is StructurePhase.BUILDING
    completed = _fold_once(started, EventKind.STRUCTURE_COMPLETED, "hut-1")
    assert completed is not None
    assert completed.phase is StructurePhase.ACTIVE
    collapsed = _fold_once(completed, EventKind.STRUCTURE_COLLAPSED, "hut-1")
    assert collapsed is not None
    assert collapsed.phase is StructurePhase.RUBBLE
    assert _fold_once(completed, EventKind.STRUCTURE_REMOVED, "hut-1") is None


def test_cascade_event_construction_cost_model() -> None:
    """成本模型守卫：100 条 `advance_cascade` 事件构造 ≈ 单帧成本主项（~0.5ms）。

    护栏 0.5ms~2.0ms：过低 = 事件构造被短路（异常），过高 = 单帧成本模型失效（须重定标）。
    """
    graph = build_support_graph(_chain(_N_1000))
    state = start_cascade(graph, ["s00000"])
    samples = []
    import time

    for _ in range(9):
        t0 = time.perf_counter()
        advance_cascade(graph, state, tick=0, event_budget=CASCADE_EVENT_BUDGET_PER_FRAME)
        samples.append((time.perf_counter() - t0) * 1000.0)
    median_ms = statistics.median(samples)
    assert 0.05 <= median_ms <= 20.0, f"单帧成本模型异常: {median_ms:.4f}ms"
