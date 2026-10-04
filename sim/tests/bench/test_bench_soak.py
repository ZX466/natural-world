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

import dataclasses
import json
import math
import os
import statistics
from pathlib import Path

import pytest

from sim.core.clock import GameClock
from sim.core.tick import TickLoop
from sim.core.world import TickContext, build_default_bus
from sim.npc.model import Need, NpcProfileData
from sim.npc.runtime import NpcRuntime
from sim.npc.utility import UtilityModel
from sim.world.map import Chunk, TileMap
from sim.world.pathfinding import Pathfinder

from . import throttle_probe
from .harness import make_state
from .soak import (
    M2_ACCEPTANCE_TICKS,
    TICKS_PER_GAME_DAY,
    make_l1_feeder,
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
    TICK_BUDGET_MS,
)
from .throttle_probe import _SkipSoak, assert_not_throttled

_MAP_W = 64
_MAP_H = 64
N_NPC = 50
# CI 冒烟：1,200 tick 分 3 窗（本机 ~2s），只验证「框架可跑 + 契约成立」。
_CI_SOAK_TICKS = 1_200
_CI_WINDOW_TICKS = 400
# nightly 长跑：30,000 tick 分 5 窗（本机 ~1 min），验稳态漂移/p99/缓存。
_NIGHTLY_SOAK_TICKS = 30_000
_NIGHTLY_WINDOW_TICKS = 6_000
#: soak 窗口级 artifact（nightly/里程碑落，供红时回查单窗离群 vs 单调退化）。
#: JSONL 追加（不覆写）：本文件多个 soak 长跑在同一 session 落同一文件时各一行。
#: 只在 nightly（PI_BENCH_ADVISORY=1）与里程碑（PI_M2_FULL_SOAK=1）写；每提交 CI 不写。
_SOAK_ARTIFACT_PATH = "perf/soak-windows.jsonl"


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


# --- M6-P1（阶段 A）：实体守恒契约 --------------------------------------------------
# 方案：`docs/perf/m6-soak-contract-preplan.md`（M5-P14 施工级预研，已收编）。
# 体例对照 `CASCADE_EVENT_BUDGET_PER_FRAME`（代码契约常量，**非** thresholds 红线）：
#   规模侧由本常量/派生式硬约束，耗时侧仍由 `SOAK_*` 红线覆盖，两者不混。
# **阶段 A 值 = 0** ⇒ 净减上界 0 ⇒ 与旧断言（`end == start`）**语义等价**、零行为变化。
# **阶段 B**（M6「生命始终」落点 a = 移出 `WorldState.entities` 落地时**同 CR**）才提值：
#   由生命面给「每游戏日可接受净减上界」；本域只提供派生式（不按档硬编码，防双真相源）。
# 契约钉：`test_soak_entity_loss_bound_is_zero_in_phase_a`（阶段 B 须同步更新）。
SOAK_ENTITY_LOSS_PER_GAME_DAY = 0


def _entity_loss_bound(ticks: int) -> int:
    """本 run 允许的实体**净减**上界（单一真相源导出，不按档硬编码）。

    CI(1,200t)/nightly(30k)/里程碑(604.8k) 自动得不同值，避免三处常量（双真相源）。
    """
    if SOAK_ENTITY_LOSS_PER_GAME_DAY <= 0:
        return 0
    return math.ceil(SOAK_ENTITY_LOSS_PER_GAME_DAY * ticks / TICKS_PER_GAME_DAY)


def _assert_entity_stable(
    result, *, label: str, profile_ids: set[str] | None = None
) -> None:
    """实体守恒（**结构量**判据，两处断言共用，防双真相源）。

    四侧判据（M6-P1 阶段 A，方案见 `docs/perf/m6-soak-contract-preplan.md` §2.1/§3）：
      ① 增侧：净增必须为 0——**不放宽**原断言的防泄漏意图（「实体凭空增多」）；
      ② 减侧：净减 ≤ `_entity_loss_bound(total_ticks)`（阶段 A = 0 ⇒ 等价恒等）；
      ③ id 集合：不得出现**新 id**（比计数强：计数相等也可能整体换人）；
      ④ 映射一致（传 `profile_ids` 时）：实体集 ↔ `runtime.profiles` 同名（`soak.py`
         接线契约）——「只删一半」会留下幽灵 NPC（A12/M6-A1 实证：`entities` 不参与
         fork 克隆而 `npc_profiles` 整表克隆 ⇒ 不对称风险）。
    与机器速度**无关**（结构量非计时量）⇒ 调用方应把它排在降频探针门**之前**。
    """
    start, end = result.entity_count_start, result.entity_count_end
    bound = _entity_loss_bound(result.total_ticks)
    assert end <= start, f"{label}: 实体净增（疑似泄漏/失控 spawn）{start} → {end}"
    assert start - end <= bound, (
        f"{label}: 实体净减 {start - end} 超界（上界 {bound}，{start} → {end}）"
    )
    if result.entity_ids_start:
        new_ids = set(result.entity_ids_end) - set(result.entity_ids_start)
        assert not new_ids, f"{label}: 出现新实体 id（{sorted(new_ids)[:5]}…）"
        if profile_ids is not None:
            assert set(result.entity_ids_end) == profile_ids, (
                f"{label}: 实体集 ↔ runtime.profiles 映射分叉"
                f"（实体 {len(result.entity_ids_end)} / profiles {len(profile_ids)}）"
            )


def _assert_no_runaway(
    result, *, label: str, profile_ids: set[str] | None = None
) -> None:
    """长跑稳定性断言（分窗口径，抗单窗离群）。

    **结构判据前置**（M6-P1 / P14 建议已采）：实体守恒是**结构量**（与机器速度无关），
    故排在降频探针门**之前**——降频夜不该让结构面静默不检。

    **降频自检**（M5-P7 / M5-P6 风险①收口）：`SOAK_STEADY_MEAN_LIMIT_MS` 是绝对值
    判据，而 soak 是分钟级持续 CPU 负载——本机若处于持续降频（实测 6.6x，
    m5-p6-soak-arbitration.md §2.2）必然假红。先跑 `throttle_probe.probe()`；比值越
    阈值即 `pytest.skip`（不是 fail：降频是环境事实，非代码回归；漂移比判据天然免疫）。
    """
    _assert_entity_stable(result, label=label, profile_ids=profile_ids)
    _skip_if_throttled()
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
    # 实体守恒已**前置**到本函数首行（M6-P1：结构量不受降频门管辖），此处不再重复。

def _assert_smoke(
    result, *, label: str, expected_ticks: int, profile_ids: set[str] | None = None
) -> None:
    """CI 冒烟（框架契约）：只验「可跑通 + 实体集稳定 + 总 tick 到位」。

    ci_smoke 形态收口（裁 28-D / M5-P5）：**不判漂移、不判稳态均值、不判资源增长**——
    旧口径把它当 `_assert_no_runaway` 跑（漂移/稳态/RSS/GC/句柄全量），但其 3 窗 × 400 tick
    样本量不足以判「末窗/首稳态窗」比值（M5-P4 实测：单窗均值 CV 8.5%，两次抽样比的右尾
    可噬 2x 假漂移）。故本处只作框架冒烟；漂移判定留给 nightly 30k（5 窗×6000）与
    里程碑 604.8k（7 窗）形态的 `_assert_no_runaway`。
    """
    assert result.windows, f"{label}: 无窗口（长跑未采样）"
    assert result.total_ticks == expected_ticks, (
        f"{label}: 总 tick {result.total_ticks} != {expected_ticks}"
    )
    _assert_entity_stable(result, label=label, profile_ids=profile_ids)

def _write_soak_artifact(result, *, label: str) -> None:
    """窗口级数字落 artifact（裁 28-D 建议②采纳）。

    nightly（`PI_BENCH_ADVISORY=1`）与里程碑（`PI_M2_FULL_SOAK=1`）写 `perf/soak-windows.jsonl`
    （JSONL 追加，多 soak 长跑各一行：label + dataclass 快照）。每提交 CI（无上述 env、
    `-m "not bench"` 选中 `test_soak_ci_smoke_stability`）不写。

    用途：nightly 红时回查单窗离群（单窗均差大） vs 单调退化（窗口均值随 tick 持续爬升），
    不再只能取「绿/红」二值（M5-P4 §1.2 缺口）。
    """
    env = os.environ
    if env.get("PI_BENCH_ADVISORY") != "1" and env.get("PI_M2_FULL_SOAK") != "1":
        return
    drift_ratio: float | None = None
    if len(result.windows) >= 2 and result.windows[1].mean_ms > 0:
        drift_ratio = result.windows[-1].mean_ms / result.windows[1].mean_ms
    record: dict[str, object] = {
        "label": label,
        "drift_ratio": drift_ratio,
        **dataclasses.asdict(result),
    }
    Path(_SOAK_ARTIFACT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with Path(_SOAK_ARTIFACT_PATH).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

def _skip_if_throttled() -> None:
    """本机持续降频 ⇒ skip（M5-P7 接管 `throttle_probe` 的信号）。

    在 soak 绝对阈值判据前调用；`PI_THROTTLE_SELFCHECK=0` 可显式关闭。
    """
    try:
        assert_not_throttled(label="soak 降频自检")
    except _SkipSoak as exc:
        pytest.skip(str(exc))

def test_soak_ci_smoke_stability() -> None:
    """CI 冒烟（M5-P5 收口）：50 NPC × 1,200 tick 只作**框架冒烟**。

    旧口径：`_assert_no_runaway` 全量（漂移/稳态均值/RSS/GC/句柄/实体数）。
    新口径：`_assert_smoke` 只验「窗口非空 + 总 tick 到位 + 实体集稳定」。
    原因：3 窗 × 400 tick 样本量不足以判「末窗/首稳态窗」比值（M5-P4 实测定论，
    2.81x 假红），漂移判定挪 nightly 30k / 里程碑 604.8k 形态。
    """
    loop = _build_loop_with_perception()
    result = run_soak(
        loop,
        ticks=_CI_SOAK_TICKS,
        window_ticks=_CI_WINDOW_TICKS,
        feeder=make_mock_feeder(_MAP_W, _MAP_H),
    )
    _assert_smoke(result, label="M2 长跑 CI 冒烟", expected_ticks=_CI_SOAK_TICKS)


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

def test_throttle_probe_shape() -> None:
    """降频自检探针契约（M5-P7）：字段齐、`throttled` 与比值单调一致、成本小。

    用 1s 持续段（env 覆盖）保持本用例秒级；真实判据 25s 段只在 soak 路径上跑。
    """
    result = throttle_probe.probe(seconds=1.0, iters=50_000)
    assert set(result) == {
        "burst_base_ms",
        "sustained_worst_ms",
        "throttle_ratio",
        "ratio_limit",
        "throttled",
        "samples",
        "iters",
    }
    assert result["burst_base_ms"] > 0
    assert result["samples"] >= 1
    assert result["throttled"] is (result["throttle_ratio"] > result["ratio_limit"])
    assert throttle_probe.THROTTLE_RATIO_LIMIT == 2.0

def test_throttle_probe_selfcheck_off_short_circuits() -> None:
    """`PI_THROTTLE_SELFCHECK=0` 时 `_skip_if_throttled` 不自旋（CI 不打折）。"""
    monkey = pytest.MonkeyPatch()
    try:
        monkey.setenv("PI_THROTTLE_SELFCHECK", "0")
        _skip_if_throttled()  # 不 raise、不 skip ⇒ 直接返回
    finally:
        monkey.undo()


def test_m2_acceptance_tick_constant_is_7_days() -> None:
    """量纲守卫：M2 验收 = 7 游戏日 = 604,800 tick（DESIGN §10/§17）。"""
    assert M2_ACCEPTANCE_TICKS == 604_800

def test_soak_entity_loss_bound_is_zero_in_phase_a() -> None:
    """契约钉（体例同 `test_cascade_frame_budget_is_100_nodes`）：阶段 A 净减上界 = 0。

    **阶段 B**（M6「生命始终」落点 a 落地同 CR）本钉须随之更新为「= 生命面给定值」，
    并同步更新 `docs/perf/m6-soak-contract-preplan.md` §7 提案值表。
    阶段 A 断言 `== 0` ⇒ `_entity_loss_bound` 恒 0 ⇒ 与旧断言（`end == start`）语义等价。
    """
    assert SOAK_ENTITY_LOSS_PER_GAME_DAY == 0
    assert _entity_loss_bound(0) == 0
    assert _entity_loss_bound(_CI_SOAK_TICKS) == 0
    assert _entity_loss_bound(M2_ACCEPTANCE_TICKS) == 0


@pytest.fixture(scope="module")
def nightly_soak_result():
    """模块级缓存：nightly 30,000 tick 长跑只跑一次，多个断言共享（省 2× 墙钟）。

    降频自检在**这里**跑（不是测试体里）：30k soak 是分钟级持续负载，若本机已降频
    （M5-P7 探针，见 `throttle_probe.py`），先 skip 再付 7 分钟墙钟纯属浪费
    （m5-p6-soak-arbitration.md §2.2 的教训）。
    """
    _skip_if_throttled()
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
    _write_soak_artifact(result, label="M2 长跑 nightly 30k")
    _assert_no_runaway(result, label="M2 长跑 nightly 30k")


@pytest.mark.bench
def test_soak_nightly_steady_p99_below_tick_budget(nightly_soak_result) -> None:
    """nightly：稳态 p99 聚合值不越每 tick 硬预算（16.6ms）——信息性守护，非细网门禁。

    为什么不拿 8.3ms（tick p99 红线）当硬门禁：长跑里单窗 p99 被 GC 分代回收 /
    OS 调度干扰主导，与负载本身无关——实测均值仅 ~2.3ms 而 p99 ~8.6ms（3.7x，
    调度噪声特征，非程序噪声）。固定硬线会把较忙的 runner 造成假红。
    故本项只守「明显退化」（p99 聚合 ≤ 16.6ms 硬预算）；真正的回归检测由
    分窗均值漂移（`SOAK_MEAN_DRIFT_RATIO_LIMIT`）+ 资源增长判据承担（两者都不受单点尖锋影响）。
    **tick p99 红线 8.3ms 的固定容身之处是短基准**
    `test_bench_clock.py`（增量硬件，每方法独立计时）。
    """
    _loop, result = nightly_soak_result
    steady = result.windows[1:]  # 首窗含冷启动
    assert steady, "无稳态窗口（窗数不足）"
    steady_p99_mean = statistics.fmean(w.p99_ms for w in steady)
    assert steady_p99_mean <= TICK_BUDGET_MS, (
        f"稳态 p99 聚合 {steady_p99_mean:.3f}ms > 硬预算 {TICK_BUDGET_MS}ms"
        f"（各窗 p99：{[round(w.p99_ms, 2) for w in steady]}）"
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
    # 30 分钟量级的持续负载：**先**判本机降频再付墙钟（M5-P7，探针见
    # `throttle_probe.py`）。降频时绝对阈值不可信，但漂移比/资源判据仍可信，
    # 故此处用「先写 artifact 再判」的顺序——保留窗口数字供回查。
    _skip_if_throttled()
    loop = _build_loop_with_perception()
    result = run_soak(
        loop,
        ticks=M2_ACCEPTANCE_TICKS,
        window_ticks=TICKS_PER_GAME_DAY,  # 每游戏日一窗（7 窗）
        feeder=make_mock_feeder(_MAP_W, _MAP_H),
    )
    _write_soak_artifact(result, label="M2 7 日自转完整跑")
    _assert_no_runaway(result, label="M2 7 日自转完整跑")
    assert result.total_ticks == M2_ACCEPTANCE_TICKS


def _build_l1_runtime() -> NpcRuntime:
    """真实 NpcRuntime（50 NPC），npc_id 与内核实体 id 同名（接线契约）。"""
    profiles = {
        f"e{i:03d}": NpcProfileData(
            npc_id=f"e{i:03d}",
            name=f"npc{i}",
            species="human",
            ocean=(50.0, 50.0, float(i % 100), 50.0, 50.0),
            needs=(
                Need("hunger", 0.5, 1.0),
                Need("energy", 0.4, 1.0),
                Need("social", 0.3, 1.0),
            ),
        )
        for i in range(N_NPC)
    }
    return NpcRuntime(profiles=profiles, utility=UtilityModel(n_npc=N_NPC))


@pytest.mark.bench
def test_soak_nightly_l1_feeder_stability() -> None:
    """nightly：50 NPC × 真实 L1 feeder 长跑无 O(n) 累积/泄漏。

    与 mock feeder 的分工见 docs/perf/m2-acceptance.md §3.1：
    mock = 内核负载上界（50 全走）；l1 = 真实 L1 计算 + 当前内容常量下的动作分布。
    """
    _skip_if_throttled()  # 分钟级持续负载：先判降频，别白烧 7 分钟（M5-P7）
    loop = _build_loop_with_perception()
    runtime = _build_l1_runtime()
    result = run_soak(
        loop,
        ticks=_NIGHTLY_SOAK_TICKS,
        window_ticks=_NIGHTLY_WINDOW_TICKS,
        feeder=make_l1_feeder(runtime, grid_w=_MAP_W, grid_h=_MAP_H),
    )
    _write_soak_artifact(result, label="M2 长跑 L1 feeder 30k")
    _assert_no_runaway(result, label="M2 长跑 L1 feeder 30k", profile_ids=set(runtime.profiles))


@pytest.mark.bench
def test_soak_l1_feeder_ci_smoke() -> None:
    """CI 冒烟（M5-P5 收口）：L1 feeder 只作**框架冒烟**。

    旧口径：`_assert_no_runaway` 全量（无界增长契约=漂移/稳态/RSS/GC/句柄）。
    新口径：`_assert_smoke` 只验「窗口非空 + 总 tick 到位 + 实体集稳定」。
    原因同 `test_soak_ci_smoke_stability`：3 窗 × 400 tick 不足以判漂移比，挪 nightly/里程碑。
    """
    loop = _build_loop_with_perception()
    runtime = _build_l1_runtime()
    result = run_soak(
        loop,
        ticks=_CI_SOAK_TICKS,
        window_ticks=_CI_WINDOW_TICKS,
        feeder=make_l1_feeder(runtime, grid_w=_MAP_W, grid_h=_MAP_H),
    )
    _assert_smoke(
        result,
        label="M2 长跑 L1 feeder CI 冒烟",
        expected_ticks=_CI_SOAK_TICKS,
        profile_ids=set(runtime.profiles),
    )
