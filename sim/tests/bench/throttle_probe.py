"""本机降频自检探针（性能域，pi）— M5-P6 风险①收口 / M5-P7。

背景（m5-p6-soak-arbitration.md §2.2）：soak 判据 `SOAK_STEADY_MEAN_LIMIT_MS` 是
**绝对值**（6.2ms），而 soak 是分钟~十分钟级持续 CPU 负载。若本机处于**持续负载
降频**状态（热/功耗），绝对值必然假红——M5-P6 实测同一份代码在本机 7.04ms（应为
~2.8ms），且**漂移比判据（比值）免疫降频**（本机 drift 1.017 ≤ 1.5）。

本模块给一个便宜、可复现的「降频」度量：短冲程自旋建立本机基线，再持续自旋并取
**最坏单样本 / 基线** 比值。**比值 > 阈值 ⇒ 本机不可信于绝对阈值**。

用法（两处，任选）：
  1) 直接跑 CLI：`python -m sim.tests.bench.throttle_probe`（或
     `uv run python -m sim.tests.bench.throttle_probe`）→ 打印一行 JSON 摘要；
  2) soak 用例调 `assert_not_throttled(label=...)`：比值越阈值时**跳过本窗**（不是红）。

口径与阈值（均记录于下，**不动 thresholds.py** —— 本探针是判据的**信任前置**，
不是新红线；m5-p6 建议①登记待裁，本文件是其落地实现）：
  - 短冲程：`BURST_ITERS=500_000` 次整数自旋，取 5 次**最小**值为 burst 基线
    （短负载能让 CPU 短暂冲高频，正是「本机最佳表现」的代理）。
  - 持续段：同一 workload 反复跑满 `SUSTAIN_SECONDS=25`，取 `max(dt/burst_base)`。
  - 阈值 `THROTTLE_RATIO_LIMIT = 2.0`：>2x 视为「本机处于持续降频」。
    依据 M5-P6 实测定标：健康本机同口径比值 **1.2~1.5**，降频本机 **6.6~7.9**
    （`test_bench_fast_forward.py` docstring 的 6.7x 先例一致）；2.0 落在两簇之间。

成本：25s 左右（可调 env `PI_THROTTLE_SUSTAIN_SECONDS`）。只在显式调用时发生，
**不自动进任何 bench/soak**（soak 侧由 `_assert_no_runaway` 调用，见同目录
`test_bench_soak.py`；CI 不跑本探针——`-m "not bench"` 与 nightly 均不触发）。
"""

from __future__ import annotations

import json
import os
import time
from typing import TypedDict

#: 单次短冲程迭代数（整数自旋，与感知/内核负载同为纯 CPU 解释器内循环）。
BURST_ITERS = 500_000
#: 短冲程重复次数（取 min 作基线）。
BURST_ROUNDS = 5
#: 持续段总时长（秒）。env `PI_THROTTLE_SUSTAIN_SECONDS` 可覆盖（测试里设为小值）。
SUSTAIN_SECONDS = 25.0
#: 比值上限：`sustained_max / burst_base` > 此值 ⇒ 判本机处于持续降频，绝对阈值不可信。
THROTTLE_RATIO_LIMIT = 2.0


class ProbeResult(TypedDict):
    """`probe()` 返回结构（TypedDict 让调用侧的比较有类型）。"""

    burst_base_ms: float
    sustained_worst_ms: float
    throttle_ratio: float
    ratio_limit: float
    throttled: bool
    samples: int
    iters: int


def _spin(iters: int) -> int:
    """纯 CPU 自旋负载（无 I/O、无分配，避免 GC 节奏干扰）。"""
    acc = 0
    for i in range(iters):
        acc += i * i
    return acc


def burst_baseline(rounds: int = BURST_ROUNDS, iters: int = BURST_ITERS) -> float:
    """短冲程基线：同一 workload 跑若干次，取**最小**耗时（本机最佳表现的代理）。"""
    best = float("inf")
    for _ in range(max(1, rounds)):
        t0 = time.perf_counter()
        _spin(iters)
        best = min(best, time.perf_counter() - t0)
    return best


def sustained_ratio(
    seconds: float | None = None, *, base_s: float | None = None, iters: int = BURST_ITERS
) -> tuple[float, float, int]:
    """持续段度量。

    Returns:
        (ratio, worst_s, samples)：`worst_s / base_s`、最坏单次耗时、样本数。
    """
    if seconds is None:
        seconds = float(os.environ.get("PI_THROTTLE_SUSTAIN_SECONDS", SUSTAIN_SECONDS))
    base = burst_baseline(iters=iters) if base_s is None else base_s
    worst = 0.0
    samples = 0
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        t0 = time.perf_counter()
        _spin(iters)
        worst = max(worst, time.perf_counter() - t0)
        samples += 1
    return (worst / base if base > 0 else float("inf")), worst, samples


def probe(seconds: float | None = None, *, iters: int = BURST_ITERS) -> ProbeResult:
    """跑完整探针，返回可序列化结果（CLI 与测试共用同一口径）。"""
    base = burst_baseline(iters=iters)
    ratio, worst, samples = sustained_ratio(seconds=seconds, base_s=base, iters=iters)
    return {
        "burst_base_ms": round(base * 1000.0, 3),
        "sustained_worst_ms": round(worst * 1000.0, 3),
        "throttle_ratio": round(ratio, 3),
        "ratio_limit": THROTTLE_RATIO_LIMIT,
        "throttled": ratio > THROTTLE_RATIO_LIMIT,
        "samples": samples,
        "iters": iters,
    }


def assert_not_throttled(*, label: str = "本机降频自检", seconds: float | None = None) -> None:
    """若本机处于持续降频 → **跳过**调用方用例（不是失败）。

    语义（m5-p6 §5-1 建议①）：绝对阈值判据（`SOAK_STEADY_MEAN_LIMIT_MS`）在降频
    本机必然假红；漂移比判据天然免疫。故此处 skip 而非 fail——降频是**环境事实**，
    不是被测代码的回归。用法：`test_bench_soak.py` 的 soak 用例在
    `_assert_no_runaway` 前调用；env `PI_THROTTLE_SELFCHECK=0` 可显式关掉本自检。
    """
    if os.environ.get("PI_THROTTLE_SELFCHECK") == "0":
        return
    result = probe(seconds)
    if result["throttled"]:
        msg = (
            f"{label}: 本机持续负载降频（自旋比值 {result['throttle_ratio']} > "
            f"{result['ratio_limit']}；短冲程 {result['burst_base_ms']}ms → "
            f"持续段最坏 {result['sustained_worst_ms']}ms，{result['samples']} 样本）。"
            "soak 绝对阈值（SOAK_STEADY_MEAN_LIMIT_MS）在本机不可信，漂移比判据不受影响。"
            "处置：稍候重跑，或直看 CI（docs/perf/m5-p6-soak-arbitration.md §2.2）。"
        )
        raise _SkipSoak(msg)
    return


class _SkipSoak(Exception):
    """内部信号：soak 用例因本机降频而跳过（由 soak 模块接住转 pytest.skip）。"""


def main() -> None:
    """CLI：输出一行 JSON（`python -m sim.tests.bench.throttle_probe`）。"""
    print(json.dumps(probe(), ensure_ascii=False))


if __name__ == "__main__":
    main()
