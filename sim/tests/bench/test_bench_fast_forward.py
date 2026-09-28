"""fast_forward 帧成本基准（性能域，pi）— M5-P3 红线配套（裁 21-A D-2 / M5-K3 已落）。

背景：M5-K3（批次 B，main `848ee18` 起）把 fast_forward 新 action 落码——
`sim/api/ws.py::step_fast_forward` 按 `FAST_FORWARD_TICKS_PER_FRAME`(=240) 预算
摊还推进（跨连接共享），`run_world_driver` 每帧调它并**抑制逐帧 state_delta 广播**。
`TestFastForwardDriverStep`（`test_m5_batch_b_control.py`）已把「恒 ≤ 预算 / 跨连接
共享预算」钉成**代码契约基线**；本文件补**性能侧数值度量**。

两条待裁红线（M5-P2 提案 §2/§4 的落地形态，本文件按 M3-P3/M4-P2 先例**观察态起步**）：
  ① `FAST_FORWARD_FRAME_LIMIT_MS` —— **单帧快进 tick 预算的墙钟上限**：一帧推进
     `FAST_FORWARD_TICKS_PER_FRAME`(240) tick 的 step+drain 成本。破限 = 单帧占用帧预算，
     会挤掉同帧的正常 tick/广播（`run_world_driver` 先 `advance_frame(real_dt)` 再叠加快进）。
  ② `FAST_FORWARD_REQUEST_DURATION_LIMIT_S` —— **单次请求上限时长**（墙钟）：满上限请求
     `FAST_FORWARD_MAX_HOURS`(168 游戏小时 = 604 800 tick) 的**推导**墙钟 = 帧数 / 驱动帧率。
     这是**派生量**（帧数 = 604800/240 = 2520；驱动 `FRAME_BUDGET_SECONDS=1/60` ⇒ 2520/60
     = **42.0 s**），破限 = 帧预算被调大 / tick 预算被调大 / 驱动帧率被改（非本表能放宽）。
     **形态 = 契约守卫，非 bench 数值行**（42s 里绝大部分是 `asyncio.sleep` 等待位，非计算；
     长跑墙钟还会被本机热/功耗降频污染——实测同进程重负载后纯 CPU 自旋 6.7x 变慢，非代码）。

口径：与既有红线同源——定标机暖态中位（`warmup_rounds` + median）、固定 seed、
世界形态对齐生产（`run_world_driver` 的 fast_forward 分支：每帧 `step_fast_forward` +
`drain_delta/drain_events`，**不调 L1 feeder**——当前 `NPC_ACT` 无内核 handler，
`NpcRuntime` 未接进 tick 固定序，故快进帧的真实负载 = 既有路径推进，非满 L1）。
**观察态起步**：`_record_proposal` 只记录「实测中位 vs 建议阈值」，**不断言**
（硬断言待 nightly 数据后另裁；与 M3-P3 / M4-P2 / M4-P3 收口一致）。

实测（本机暖态中位，2026-09-28；两工作负载锚点）：
  单帧 240 tick（生产口径，无 L1 feeder）：
    0 实体 **0.29ms** / 10 实体 **0.35ms** / 50 实体 **0.53ms**；
  （对照：若快进帧**也跑** mock feeder 满负载，plain-50 单帧 ~2.9ms、perc-50 单帧 ~1.5s
   ——后者是「L1/感知已接进 tick」后的未来负载，非当前生产口径，只作上界参考。）
⚠ 本机噪声提示：同进程重负载后纯 CPU 自旋会 6.7x 变慢（热/功耗降频，非代码退化）——
   故 ① 用 `iterations=200` 的 pedantic（单帧微基准，受降频影响小）。
"""
from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
import structlog

from sim.api.ws import (
    FAST_FORWARD_MAX_HOURS,
    FAST_FORWARD_TICKS_PER_FRAME,
    ControlState,
    step_fast_forward,
)
from sim.core.tick import TickLoop

from .harness import make_loop
from .thresholds import (
    FAST_FORWARD_FRAME_LIMIT_MS,
    FAST_FORWARD_REQUEST_DURATION_LIMIT_S,
)

logger = structlog.get_logger(__name__)

#: 帧成本的代表实体数（0=纯内核；50=DESIGN §13 L1 规模）。
_N_ENTITIES = (0, 10, 50)


def _perf_counter() -> float:
    return time.perf_counter()


@pytest.fixture(params=_N_ENTITIES, ids=lambda n: f"{n}npc")
def ff_loop(request: pytest.FixtureRequest) -> Iterator[TickLoop]:
    """生产口径快进世界：`make_loop(n)`（真实内核，无 L1/感知挂载）。"""
    yield make_loop(request.param)


def _record_proposal(
    meta: object, limit_ms: float, label: str, extra: dict[str, float | int] | None = None
) -> None:
    """定标观察态（M5-P3）：只记录「实测中位 vs 建议阈值」，**不断言**。

    裁后按 M3-P2/M3-P3/M4-P2 先例换 `harness.assert_median_threshold`
    （定标机硬断言 / `PI_BENCH_ADVISORY=1` 只记录）。口径与其它 bench 完全一致（暖态中位）。
    """
    stats = meta.stats  # type: ignore[attr-defined]
    median_ms = stats.median * 1000.0
    mean_ms = stats.mean * 1000.0
    logger.info(
        "bench.fast_forward.proposal",
        label=label,
        median_ms=round(median_ms, 4),
        mean_ms=round(mean_ms, 4),
        limit_ms=limit_ms,
        exceeded=median_ms > limit_ms,
        delta_ms=round(median_ms - limit_ms, 4),
        **(extra or {}),
    )


# ---------------------------------------------------------------------------
# ① 单帧快进 tick 预算的墙钟上限（FAST_FORWARD_FRAME_LIMIT_MS）
# ---------------------------------------------------------------------------
@pytest.mark.bench
def test_fast_forward_frame_cost(ff_loop: TickLoop, benchmark) -> None:
    """一帧 `step_fast_forward` 满预算（240 tick）+ drain ≤ 0.90ms（暖态中位）。

    形态对齐 `run_world_driver` 的 fast_forward 分支：`step_fast_forward(loop, controls, budget)`
    后每帧 `drain_events/drain_delta`。破限 = 单帧快进挤占同帧正常 tick/广播预算
    （240 tick × 单 tick 成本的直接体现）；**先查内核单 tick 成本**（`test_bench_clock`），
    不是放宽本行。
    """

    def _run() -> float:
        # 每帧恒满预算推进：预登记足量在途（单帧成本只量一帧）。
        control = ControlState()
        control.request_fast_forward(FAST_FORWARD_TICKS_PER_FRAME + 1)
        loop = ff_loop
        t0 = _perf_counter()
        step_fast_forward(loop, [control], budget=FAST_FORWARD_TICKS_PER_FRAME)
        loop.drain_events()
        loop.drain_delta()
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=200)
    _record_proposal(
        benchmark.stats,
        FAST_FORWARD_FRAME_LIMIT_MS,
        "fast_forward 单帧（240 tick · step+drain）",
        {"ticks_per_frame": FAST_FORWARD_TICKS_PER_FRAME},
    )


# ---------------------------------------------------------------------------
# 契约守卫（T1 级，不设数值红线）
# ---------------------------------------------------------------------------
def test_fast_forward_frame_budget_contract() -> None:
    """单帧预算常量不超内核封顶（`FAST_FORWARD_TICKS_PER_FRAME` ≤ `_MAX_TICKS_PER_FRAME`）。

    与 `TestFastForwardDriverStep`（`test_m5_batch_b_control.py`）互补：那条钉「恒 ≤ 预算」，
    本条钉「预算本身 ≤ 内核单帧封顶」——否则 `clock` 二次截断，快进达不到预算（静默变慢）。
    """
    from sim.core.tick import _MAX_TICKS_PER_FRAME

    assert FAST_FORWARD_TICKS_PER_FRAME <= _MAX_TICKS_PER_FRAME
    assert FAST_FORWARD_MAX_HOURS > 0


def test_fast_forward_request_duration_is_derived() -> None:
    """上限时长是**派生量**：`MAX_HOURS × 3600 / TICKS_PER_FRAME / 60` = 42.0 s（契约）。"""
    derived = (FAST_FORWARD_MAX_HOURS * 3_600) / FAST_FORWARD_TICKS_PER_FRAME / 60.0
    assert abs(derived - FAST_FORWARD_REQUEST_DURATION_LIMIT_S) < 1e-9
