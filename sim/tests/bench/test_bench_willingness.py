"""意愿/独白热路径基准（性能域，pi）— M4-P3（B3 接线补数）。

背景：M4-B3 已收编 main（`24eadb2`）：`NpcRuntime.tick` 意愿注入缝——
`willingness` 非空时每 NPC 每动作多一次 `willingness_expression` 纯函数调用，
band≥1 时每 NPC 一条 `npc_monologue_event`（K8 通路）。按惯例新热路径补数。

口径：与既有红线同源 —— 暖态中位（`warmup_rounds=1` + median）、固定 seed、
50 NPC/tick 量级（DESIGN §13 L1 规模）。
**观察态起步**：阈值用 `_record_proposal` 只记录「实测中位 vs 建议阈值」，**不断言**
（硬断言待 nightly 数据后另裁；与 M3-P3 / M4-P2 收口一致）。

三段成本（本机暖态中位，2026-09-26）：
  ① `willingness_expression` 单函数：band=0 早退 **~0.04µs/调用**（50 NPC = 2.2µs/tick）；
     band≥1 走模板选取 **~0.4µs/调用**（50 NPC ≈ 20µs/tick）；`willingness_conflict`
     合成 ~0.9µs/调用（50 NPC ≈ 46µs/tick）。
  ② **B3 热路径本体**（expression + band≥1 的 monologue 事件构造，50 NPC）：
     band=0 **2.1µs/tick**（全早退）/ band≥1 **~165-176µs/tick**（~3.4µs/NPC，事件构造主导）。
  ③ **`runtime.tick` 端到端对照**（None vs 注入，50 NPC 同 seed）：
     None **0.720ms/tick**；band=0 +0.004ms（~4µs）；band≥1 **+0.20ms/tick**（~200µs）。
     → 增量 = 表现面成本（每 NPC 一条独白事件），与 §② 一致。
"""

from __future__ import annotations

import time

import pytest
import structlog

from sim.agent.will import (
    WillingnessVerdict,
    willingness_conflict,
    willingness_expression,
)
from sim.core.events import npc_monologue_event
from sim.npc.model import Need, NpcProfileData
from sim.npc.runtime import NpcRuntime
from sim.npc.utility import UtilityModel

from .thresholds import WILLINGNESS_TICK_LIMIT_MS

logger = structlog.get_logger(__name__)

N_NPC = 50  # DESIGN §13 L1 规模（与 test_bench_l1_utility / soak 同）
#: 三档代表 verdict（band 0 无表现 / band 1 微词 / band 3 强烈抵触 + defers）
_BANDS: tuple[tuple[int, float], ...] = ((0, 0.1), (1, 0.45), (2, 0.7), (3, 0.9))
_NEED_VALUES = {"hunger": 0.5, "energy": 0.4, "social": 0.3}


def _verdict(band: int) -> WillingnessVerdict:
    score = next(s for b, s in _BANDS if b == band)
    return WillingnessVerdict(score=score, band=band)


def _profiles() -> list[NpcProfileData]:
    """真实 NpcProfileData 满编 50 人（id 与 bench harness 的 e%03d 对齐）。"""
    return [
        NpcProfileData(
            npc_id=f"e{i:03d}",
            name=f"npc{i}",
            species="human",
            ocean=(50.0, 50.0, float(i % 100), 50.0, 50.0),
            needs=tuple(Need(k, v, 1.0) for k, v in _NEED_VALUES.items()),
        )
        for i in range(N_NPC)
    ]


def _make_runtime(verdict: WillingnessVerdict | None) -> NpcRuntime:
    """50 NPC runtime（同 seed 局部确定性；willingness 注入缝）。"""
    return NpcRuntime(
        profiles={p.npc_id: p for p in _profiles()},
        utility=UtilityModel(n_npc=N_NPC),
        willingness=verdict,
    )


def _record_proposal(
    meta: object, limit_ms: float, label: str, extra: dict[str, float | int] | None = None
) -> None:
    """定标观察态（M4-P3）：只记录「实测中位 vs 建议阈值」，**不断言**。

    裁后按 M3-P2/M3-P3/M4-P2 先例换 `harness.assert_median_threshold`
    （定标机硬断言 / `PI_BENCH_ADVISORY=1` 只记录）。口径与其它 bench 完全一致（暖态中位）。
    """
    stats = meta.stats  # type: ignore[attr-defined]
    median_ms = stats.median * 1000.0
    mean_ms = stats.mean * 1000.0
    exceeded = median_ms > limit_ms
    logger.info(
        "bench.willingness.proposal",
        label=label,
        median_ms=round(median_ms, 4),
        mean_ms=round(mean_ms, 4),
        limit_ms=limit_ms,
        exceeded=exceeded,
        delta_ms=round(median_ms - limit_ms, 4),
        **(extra or {}),
    )


# ---------------------------------------------------------------------------
# ① 意愿纯函数（单函数成本，50 NPC/tick 量级）
# ---------------------------------------------------------------------------
@pytest.mark.bench
@pytest.mark.parametrize("band", [0, 1, 2, 3], ids=["band0", "band1", "band2", "band3"])
def test_willingness_expression_50npc(benchmark, band: int) -> None:
    """`willingness_expression` × 50 NPC/tick（band 0 早退 / band≥1 模板选取）。

    实测（本机暖态中位）：band=0 ~0.04µs/调用（早退返回 None）；band≥1 ~0.4µs/调用。
    """
    verdict = _verdict(band)
    ids = [f"e{i:03d}" for i in range(N_NPC)]
    benchmark.pedantic(
        lambda: [willingness_expression(verdict, npc_name=nid) for nid in ids],
        rounds=9,
        warmup_rounds=1,
    )
    _record_proposal(
        benchmark.stats,
        WILLINGNESS_TICK_LIMIT_MS,
        f"willingness_expression ×{N_NPC}（band={band}）",
        {"npc": N_NPC, "band": band},
    )


@pytest.mark.bench
def test_willingness_conflict_synthesis_50npc(benchmark) -> None:
    """`willingness_conflict` w₁-w₄ 合成 × 50 NPC/tick（决策侧调用点）。

    实测（本机暖态中位）：~0.9µs/调用（50 NPC ≈ 46µs/tick）。
    """
    args = (0.3, 0.4, 0.5, 0.6)
    benchmark.pedantic(
        lambda: [willingness_conflict(*args) for _ in range(N_NPC)],
        rounds=9,
        warmup_rounds=1,
    )
    _record_proposal(
        benchmark.stats,
        WILLINGNESS_TICK_LIMIT_MS,
        f"willingness_conflict ×{N_NPC}",
        {"npc": N_NPC},
    )


# ---------------------------------------------------------------------------
# ② B3 热路径本体（expression + band≥1 monologue 事件构造）
# ---------------------------------------------------------------------------
@pytest.mark.bench
@pytest.mark.parametrize("band", [0, 1, 2, 3], ids=["band0", "band1", "band2", "band3"])
def test_willingness_hotpath_50npc(benchmark, band: int) -> None:
    """B3 注入缝本体：每 NPC 一次 `willingness_expression` + band≥1 一条独白事件。

    这是 `NpcRuntime.tick` 注入分支的**增量成本**（与 runtime 其余部分解耦）。
    实测（本机暖态中位）：band=0 ~2.1µs/tick（全早退）；band≥1 ~165-176µs/tick
    （~3.4µs/NPC，独白事件 pydantic 构造主导）。
    """
    verdict = _verdict(band)
    ids = [f"e{i:03d}" for i in range(N_NPC)]

    def _hotpath() -> list[object]:
        events: list[object] = []
        for nid in ids:
            expr = willingness_expression(verdict, npc_name=nid)
            if expr is not None:
                events.append(
                    npc_monologue_event(
                        tick=1, npc_id=nid, form="thought", content=expr.monologue
                    )
                )
        return events

    benchmark.pedantic(_hotpath, rounds=9, warmup_rounds=1)
    _record_proposal(
        benchmark.stats,
        WILLINGNESS_TICK_LIMIT_MS,
        f"B3 热路径（expression+monologue ×{N_NPC}，band={band}）",
        {"npc": N_NPC, "band": band},
    )


# ---------------------------------------------------------------------------
# ③ runtime.tick 端到端对照（None vs 注入，50 NPC 同 seed）
# ---------------------------------------------------------------------------
@pytest.mark.bench
def test_tick_baseline_none_50npc(benchmark) -> None:
    """`NpcRuntime.tick` 50 NPC，`willingness=None`（M2 基线，意愿缝零成本）。

    实测（本机暖态中位）：~0.720ms/tick —— 与 `test_l1_real_runtime_tick_50npc`
    （0.74ms）一致（红线 `L1_UTILITY_TICK_LIMIT_MS=6.0` 口径）。
    """
    runtime = _make_runtime(None)
    benchmark.pedantic(lambda: runtime.tick(1), rounds=9, warmup_rounds=1)
    _record_proposal(
        benchmark.stats,
        WILLINGNESS_TICK_LIMIT_MS,
        "runtime.tick None（50 NPC 基线）",
        {"npc": N_NPC},
    )


@pytest.mark.bench
@pytest.mark.parametrize("band", [0, 1, 3], ids=["band0", "band1", "band3"])
def test_tick_overhead_injected_50npc(benchmark, band: int) -> None:
    """`NpcRuntime.tick` 50 NPC，注入 `willingness`（band 0/1/3）——表现面增量实测。

    实测（本机暖态中位）：None 基线 0.720ms/tick；band=0 +0.004ms（~4µs，全早退）；
    band≥1 **+0.20ms/tick**（~200µs）= 每 NPC 一条独白事件的构造成本（§②同源）。
    红线按注入态（最坏）取值。
    """
    runtime = _make_runtime(_verdict(band))
    benchmark.pedantic(lambda: runtime.tick(1), rounds=9, warmup_rounds=1)
    _record_proposal(
        benchmark.stats,
        WILLINGNESS_TICK_LIMIT_MS,
        f"runtime.tick 注入（50 NPC，band={band}）",
        {"npc": N_NPC, "band": band},
    )


# ---------------------------------------------------------------------------
# 契约/成本模型守卫（非 bench）
# ---------------------------------------------------------------------------
def test_expression_band0_is_none_contract() -> None:
    """band=0 无表现 = `None`（§10 四档表：0.0-0.3 自然接受，零戏内产物）。"""
    assert willingness_expression(_verdict(0), npc_name="e000") is None


def test_expression_band_mapping_contract() -> None:
    """四档映射：band≥1 有独白；band=3 才 `defers`（§10：先做别的再绕回来）。"""
    for band in (1, 2, 3):
        expr = willingness_expression(_verdict(band), npc_name="e000")
        assert expr is not None
        assert expr.band == band
        assert expr.monologue
        assert expr.defers is (band >= 3)


def test_tick_overhead_delta_sanity() -> None:
    """端到端增量合理性护栏（非红线）：注入 band≥1 的 Δ 应落在 µs~亚 ms 量级。

    护栏 0.02ms~2.0ms：过低 = 独白分支被短路（异常）；过高 = 事件构造退化（须重定标）。
    """
    baseline = _make_runtime(None)
    injected = _make_runtime(_verdict(1))
    _warm(injected)
    _warm(baseline)
    delta_ms = _paired_delta(baseline, injected, iters=40) * 1000.0
    assert 0.02 <= delta_ms <= 2.0, f"注入增量异常: {delta_ms:.4f}ms/tick"


def test_monologue_event_payload_has_no_band_metadata() -> None:
    """T1 守卫复核：独白事件 payload 只含 npc_id/form/content（档位号永不进文本）。"""
    event = npc_monologue_event(tick=1, npc_id="e000", form="thought", content="嗯，我有点犯难。")
    assert set(event.payload) == {"npc_id", "form", "content"}


def _warm(runtime: NpcRuntime, iters: int = 5) -> None:
    for _ in range(iters):
        runtime.tick(1)


def _paired_delta(baseline: NpcRuntime, injected: NpcRuntime, *, iters: int) -> float:
    """交替 tick 相减的配对增量（秒/tick）；交替消除墙钟漂移。"""
    total = 0.0
    for _ in range(iters):
        t0 = time.perf_counter()
        baseline.tick(1)
        total -= time.perf_counter() - t0
        t0 = time.perf_counter()
        injected.tick(1)
        total += time.perf_counter() - t0
    return total / iters
