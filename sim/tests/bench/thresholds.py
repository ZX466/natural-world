"""基准回归阈值 — 集中一处（性能域，pi）。

依据：docs/perf/budget.md §1 预算表、docs/perf/bench-plan.md §3 回归阈值。
口径：pytest-benchmark 的 mean 为「被测函数单轮耗时」；本文件常量是回归红线，
bench 用例失败时会输出「实测值与阈值的差值」。
注意：机器档位不同阈值要按 bench-plan §3 口径缩放，不要照搬换机器。

修订记录（TASK-002 先行实测，2026-09-19）：
- RNG 1M 逐调用聚合量纲实测 219ms，原 100ms 阈值与「每 tick 预算」脱节 ——
  RNG 每 tick 成本按「draw 数 × 单 draw 耗时」计，聚合 1M 只是警戒线，非 tick 硬预算。
  已将 `RNG_1M_DRAWS_LIMIT_MS` 调为 300（实测 219 + 慢机余量），
  M2-P6（Claude 2026-09-22 裁决 2）再调 330：定标机全量 bench 首跑中位 300.084ms
  （贴边，单跑复绿 = 抖动）—— 加 10% 余量消刀尖红。仅聚合警戒线，非 tick 硬预算。
  并新增 `RNG_TICK_LIMIT_MS`（= budget §1 上限 0.10ms）直接卡每 tick 场景。
"""

# --- 每 tick 预算（budget.md §1，1x = 60 tick/s → 16.6ms）---
TICK_BUDGET_MS = 16.6  # 每 tick 硬预算上限

# --- 回归阈值（bench-plan.md §3）---
# tick p99 ≤ 预算 50%
TICK_P99_LIMIT_MS = 8.3
# apply(event) 单事件 p99 ≤ 0.04ms
APPLY_P99_LIMIT_MS = 0.04
# RNG 1M draws 警戒线（聚合量纲；先行实测逐调用 219ms @本机）。
# 330 = 实测 + 慢机余量（M2-P6：300→330，定标机全量跑中位 300.084ms 贴边）
RNG_1M_DRAWS_LIMIT_MS = 330.0
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
# **M2-P4 起本常量 = 纯网格参考口径**（K=20 活跃物质源，不接入知步的参考实现
# `_SmellField`，见 test_bench_smell.py 上部用例）。接线版（源=全体实体、真正的
# `SmellWorld.step`，含 dict 组装与批量采样）红线下行 `SMELL_WIRED_TICK_LIMIT_MS`——
# 两口径并存，勿用本常量卡接线版（源数差 2.5x 且多采样/组装成本）。
SMELL_TICK_LIMIT_MS = 0.15
# 嗅觉 naive O(N²) ∝1/r² 哨兵下界：断言其明显慢于网格版（H-1 动机证据，不卡预算）。
SMELL_NAIVE_SENTINEL_MS = 3.0
# --- M2-P5：嗅觉场推进接线版红线（源 = 全体实体，SmellWorld.step 真实实现） ---
# 依据 docs/perf/m2-p4-budget-preplan.md §1.3（Claude 2026-09-22 裁决采纳补行）。
# 口径：`SmellWorld.step`（inject + roll 平流 + 8 邻域扩散 + 衰减 + sample_batch + dict 组装），
# 源 = 全体实体（50 NPC 场景；100 源上界哨兵用同一红线做软断言）。
# M2-P5 复测（inject 已向量化 main `653d395`，np.add.at）：
#   50 源 0.116ms / 100 源 0.135ms / 200 源 0.151ms / 500 源 0.335ms（暖态中位）。
# 1.0ms = 500 源（≈10x L1 规模）之上 + 慢机余量；P4 原提案值不变，实测余量 ~8x。
SMELL_WIRED_TICK_LIMIT_MS = 1.0

# --- M3-P1/P2：检索缝预算红线（裁 7 采，2026-09-23；A4 收口后落地）---
# 依据 docs/perf/m3-retrieval-budget.md §1.3（V5 裁决输入）+ §2 防呆母本
# （m2-p4-budget-preplan §3.3）。口径：单次检索 = vec 候选生成（k=20）+ 打分链
# （20 候选 × 2 钩子）两段拆开给红线；**不进 tick 常态**（触发决策/prompt 驱动，§2）。
# 红线值 = pi 提案原值（Claude 裁 7 采，不变）：A4 接线后按实测对账（M3-P2 已对账，
# 见 test_bench_retrieval.py 头注：候选 0.233 / 打分 0.057 / 哨兵 0.970 / tick 总量 ~0.29ms）。
# 候选生成（Vec）单次上限。numpy 余弦实测 0.019ms/NPC + 15x 余量（sqlite-vec 同量级；
# dim 768 翻倍仍余 7x）。破限 = 候选缝退化，查 VectorIndex 接线而非放宽。
VEC_CANDIDATE_PER_NPC_LIMIT_MS = 0.30
# 打分链（20 候选 × 2 钩子）上限。外推 0.029ms/NPC + 10x 余量；M3-P2 实测 0.057ms。
RETRIEVAL_SCORE_PER_NPC_LIMIT_MS = 0.30
# 退化哨兵：候选未收缩（600 全量 × 2 钩子）上限。实测 0.862ms(A2) / 0.970ms(A4 口径) + ~2x；
# 破限 = 向量缝断链（召回端治理 JOIN 失败 / 候选生成器没接上）→ 查 A4 接线，非放宽。
RETRIEVAL_FULL_SCAN_PER_NPC_LIMIT_MS = 2.00
# 单 tick 检索总量（50 NPC 各一次）上限 = 50×0.05 正常 + 余量。
# 破限先查**触发频次退化**（§2 防呆：禁每 tick 全量检索），不是查单次成本。
RETRIEVAL_TICK_LIMIT_MS = 12.0
# 注：单次检索（候选+打分）合计 ≤ 0.60ms/NPC = 0.30+0.30（不新增行，与上两行同源）。

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

# --- M3-P3：C3 chunk 失效通路红线（2026-09-25 Claude 裁决：全采）---
# 依据 docs/perf/m3-retrieval-budget.md 附录「M3-P3 chunk 失效实测」（2026-09-25）。
# 口径与既有红线同源：暖态中位（warmup_rounds=1 + median）、固定seed、48×48=9 chunk 开阔图。
# **裁决（裁 13）**：两行全采——实测充分（多轮中位+成本模型 缓存条数×脏chunk 数），
# 独立行不占 RETRIEVAL_TICK 预算的论证成立。**既有四行检索红线不动**。
# 后续（M4 或定标机接入时）：bench 侧由 _record_proposal 切 harness.assert_median_threshold
# 硬断言 + nightly advisory 门（M3-P2 先例）；当前观察态维持。
# ① `event_tile_position` 纯函数每 tick 全事件遍历上限 = 0.10ms。
#    实测 0.06ms/千事件（50 定位 0.007 / 200 混合 0.036 / 1000 0.054 / 5000 0.267ms）→ 1.7x 余量
#    覆盖 ~1800 事件/tick（稳态 ~20 与 p99 50 均远在其内，budget.md §2.3）。
#    破限 = 事件流异常暴涨，查事件产生侧（非本通路退化）。
CHUNK_EVENT_SCAN_LIMIT_MS = 0.10
# ② `observe_events` 失效本体（标脏 → drain → 逐 chunk 精确剔除）单 tick 上限 = 2.0ms
#    （tick 预算 RETRIEVAL_TICK_LIMIT_MS=12.0 之外**独立行**：失效是寻路缓存的维护成本，
#    与检索链零耦合；且必须留在 16.6ms tick 预算内 → 取 12% 作上界占位）。
#    实测（暖态中位）：
#      100 路径 / 50 定位事件  ~0.076ms
#      1000 路径 / 50 定位事件 ~0.320ms
#      **4096 缓存打满 / 50 定位事件 ~1.18ms**（= PathCache.max_entries 上界档，定标据此）
#      100 路径 / 25 定位+25 未定位 ~0.056ms（脏 chunk 减半 → 成本减半，验证 ∝ 脏chunk 数）
#    成本模型：缓存条数 × 脏 chunk 数（`PathCache.invalidate` 逐 chunk 全表扫一遍）。
#    2.0 = 1.18 实测 + ~1.7x 慢机余量。破限先查缓存规模/脏 chunk 数来源，
#    再考虑「按 chunk 倒排索引」形态（当前 4096 条 × 9 chunk 下限规模无需索引）。
CHUNK_INVALIDATION_TICK_LIMIT_MS = 2.0
