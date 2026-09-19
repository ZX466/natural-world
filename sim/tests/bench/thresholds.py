"""基准回归阈值 — 集中一处（性能域，pi）。

依据：docs/perf/budget.md §1 预算表、docs/perf/bench-plan.md §3 回归阈值。
口径：pytest-benchmark 的 mean 为「被测函数单轮耗时」；本文件常量是回归红线，
bench 用例失败时会输出「实测值与阈值的差值」。
注意：机器档位不同阈值要按 bench-plan §3 口径缩放，不要照搬换机器。

修订记录（TASK-002 先行实测，2026-09-19）：
- RNG 1M 逐调用聚合量纲实测 219ms，原 100ms 阈值与「每 tick 预算」脱节 ——
  RNG 每 tick 成本按「draw 数 × 单 draw 耗时」计，聚合 1M 只是警戒线，非 tick 硬预算。
  已将 `RNG_1M_DRAWS_LIMIT_MS` 调为 300（实测 219 + 慢机余量），
  并新增 `RNG_TICK_LIMIT_MS`（= budget §1 上限 0.10ms）直接卡每 tick 场景。
"""

# --- 每 tick 预算（budget.md §1，1x = 60 tick/s → 16.6ms）---
TICK_BUDGET_MS = 16.6  # 每 tick 硬预算上限

# --- 回归阈值（bench-plan.md §3）---
# tick p99 ≤ 预算 50%
TICK_P99_LIMIT_MS = 8.3
# apply(event) 单事件 p99 ≤ 0.04ms
APPLY_P99_LIMIT_MS = 0.04
# RNG 1M draws 警戒线（聚合量纲；先行实测逐调用 219ms @本机）。300 = 实测 + 慢机余量
RNG_1M_DRAWS_LIMIT_MS = 300.0
# RNG 每 tick 成本上限 = budget §1/§2.2 上限 0.10ms（50 NPC × draws/tick 场景）
RNG_TICK_LIMIT_MS = 0.10
# 快照单次 ≤ 500ms（后台可见，不进 tick 临界区）
SNAPSHOT_LIMIT_MS = 500.0
