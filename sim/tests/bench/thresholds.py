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
# LLM 预取调度（M1）：tick 内确定性部分（触发门控+Intent 入队+二次校验），
# = budget.md §1/§2.8 上限 0.20ms；异步推理墙钟量纲不进 tick（见 llm-monitoring.md）
LLM_SCHED_TICK_LIMIT_MS = 0.20
# 感知传播每 tick 红线。预算目标值 3.00ms（budget.md §1/§2.5）；红线 3.6 = +20% 慢机余量。
# F06 复核（真实引擎，2026-09-20）：暖态 mean 实测 3.0-3.3ms（在 3.6 内，余量 8-17%），
# 首轮 LOS 对称缓存冷启动 7.6-8.2ms（一次性）；bench 已 `warmup_rounds=1` 剔除冷启动，
# 否则 mean 会被拉到 3.8-4.4ms 越过红线假红。暖态口径下红线成立。
PERCEPTION_TICK_LIMIT_MS = 3.6

# --- M2-P1：L1 效用 AI（50 NPC）与嗅觉传播（∝1/r² 风向）预算红线 ---
# 依据：budget.md §1 表 + §2.4/§2.9，M2-P1 定案（2026-09-20，本机暖态中位实测）。
# 口径统一「暖态中位」（warmup_rounds=1 + assert_median_threshold），与感知红线同源。

# L1 效用 50 NPC 全量每 tick 上限。budget.md §1 上限 6.00ms（名义 4.00ms）。
# 实测（代表性满属性载荷：needs6+OCEAN5+PAD3+关系+R32 记忆显著性，向量化）
# 暖态中位 ~0.02ms —— 6.00 为「M2 满属性 + 未向量化写法」的回归天花板，
# 破限先砍 memory 衰减节拍（budget §2.4），再优化，不得放宽红线。
# M2-P3 对账（main `59ffd86` 已落地真实实现，规格见 docs/perf/l1-spec.md）：真实实现是精简形
# （3 needs / 6 actions / `_GAIN (3,6)`，无 PAD/关系/记忆），但开销大头在 Python 侧
# （建矩阵逐 profile 循环 + scores dict + pydantic 事件），实测慢于原型一个数量级：
#   utility_scores_matrix 50 NPC ~0.206ms / evaluate_batch ~0.273ms / NpcRuntime.tick ~0.747ms
#   单 NPC（1-NPC 批次）~0.0124ms —— 全部远低本红线（~29x / ~22x / ~8x / ~10x）。
# 红线不缩小（上界放羄 = 自缩防线）。单 NPC 测量坑：pytest-benchmark 计调用墙钟、
# 不吃返回值，故必须用 1-NPC 批次（别除 n）。
L1_UTILITY_TICK_LIMIT_MS = 6.0
# 单 NPC 单 tick 效用评估上限 = 6.00ms / 50 npc（budget §2.4 逐人预算口径）。
# 真实实现实测 ~0.0124ms（余量 ~10x）。
L1_UTILITY_PER_NPC_LIMIT_MS = 0.12
# LLM 断线降级路径（L1 兜底执行计划队列：每股 pop 一步 + 常数校验）上限。
# 量级校验项：实测 ~0.001ms；0.20 = O(N) 上界，防降级路径写回热循环。
L1_OFFLINE_FALLBACK_LIMIT_MS = 0.20

# 嗅觉传播（M2 新通道）每 tick 扩散上限。budget.md §2.9：名义 0.05ms / 上限 0.15ms。
# 口径：Eulerian 网格半拉格朗日平流 + 衰减 + 持续源发射（64×64，K≈20 活跃源），
# 一次 np.roll 全图 —— 不逐对计算（逐对 O(N²)·1/r² 是 naive 哨兵，见下）。
# 暖态中位实测 ~0.01ms；0.15 留「风场非恒定→需双线性插值平移」的余量。
SMELL_TICK_LIMIT_MS = 0.15
# 嗅觉 naive O(N²) ∝1/r² 哨兵下界：断言其明显慢于网格版（H-1 动机证据，不卡预算）。
SMELL_NAIVE_SENTINEL_MS = 3.0

# --- M2-P2：7 日自转长跑（604,800 tick）验收红线 ---
# 依据：DESIGN §17 M2 验收「50 NPC × 7 游戏日自转无崩溃」。
# 口径：**分窗稳定性**，而非单轮 p99 —— 长跑里单窗口离群（GC/OS 抖动）不应误红；
# 判据 = 末窗均值相对首稳态窗的漂移有界 + 内存/句柄/缓存不无界增长。
# 实测（本机 50 NPC×64×64，含感知挂载，两种 feeder 见 soak.py）：
#   make_mock_feeder（50 全走，内核负载上界）稳态 mean ~1.9ms
#   make_l1_feeder（真实 NpcRuntime.tick，L1 计算 ~0.75ms/tick）稳态 mean ~0.9ms
# （早期错峰空转原型为 4.5ms —— 负载保真差异见 soak.py make_mock_feeder 注释。）
# L1 feeder 不取代 mock feeder 当上界：当前内容常量下 hunger 主导 → eat 占多数
# → move/wander 少 → 内核负载反而低于 mock。两者测不同的事（见 m2-acceptance.md §3.1）。
# 604,800 tick 完整跑不进每提交 CI，接 nightly（接法已裁方案 A）。
#
# 稳态均值上限：含感知的全内核长跑须远低于 16.6ms 预算；取 6.2ms（约为 tick p99 红线 8.3 的 75%）。
SOAK_STEADY_MEAN_LIMIT_MS = 6.2
# 末窗均值相对首稳态窗（第 2 窗，剔除首窗冷启动）的漂移比上限（1.5x）。
# 单机 GC/缓存预热有界上升容许；所谓 O(n) 累积会远超此值。
SOAK_MEAN_DRIFT_RATIO_LIMIT = 1.5
# 内存增长上限（MB）：末窗 RSS - 首窗 RSS。50 NPC 稳态不应有 MB 级线性累积。
# 探测不可用（返回 -1）时本项自动跳过（不误红）。
SOAK_RSS_GROWTH_LIMIT_MB = 128.0
# GC 对象数增长上限（末窗 - 首窗）。LOS 缓存最多数千项；对象数不应线性膨胀。
SOAK_GC_OBJECT_GROWTH_LIMIT = 20_000
# 句柄数增长上限（Windows 有效；其他平台 handle_count()==-1 自动跳过）。
SOAK_HANDLE_GROWTH_LIMIT = 64
