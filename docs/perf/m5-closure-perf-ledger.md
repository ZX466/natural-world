# M5-P12：M5 性能收官台账（三案红线终局 + 定标 runbook 终版 + 机器观察汇总 + M6 预告）
> 性能域（pi），2026-10-03。任务：M5-P12（**零代码 + 只读汇总**——不重跑 bench，引用各单留痕；`sim/`、`thresholds.py`、既有 bench、`docs/README` 零改动）。
> 基线：main `d2d95c0`（= 本树 HEAD，开工前同头确认）。
> 依据：P9 `m5-batch-a-chaos-budget.md` / P10 `m5-power-budget.md` / P11 `m5-fire-budget.md`（三案预算案）+ P5/P6/P7/P8（soak 仲裁·探针·护栏·Xeon 台账）+ codex S9 §D-14 / opencode A8·A9 / kilo K12·K13（三案已收敛口径）。
> **本档是 M5 性能面的单一入口**：新对话读此一档即可接手三案定标，不必回读三案全文。

## 0. 结论速览
| # | 问题 | 结论 |
|---|---|---|
| 1 | 三案红线现在什么状态？ | **全部仍是 advisory，零条进 `thresholds.py`**（实测 grep：`CHAOS/POWER/FIRE/MAX_BIAS/REGRESS_INTERVAL` 在该文件**零命中**）。原因**不是遗漏，而是前置未满足**——三案各自依赖的接线**都还没落**（§1.2 逐项实证：混沌消费点未接、权力决策层未消费、火灾机制面未落盘）。 |
| 2 | 能定标吗？ | **现在不能。** 定标的前提是「被测量已进生产热路径」；三案接线未落 ⇒ 现在跑定标轮测的是我自己临时探针，**等于给不存在的代码定红线**。⇒ **定标轮必须排在批次 A 收口 / 批次 C 接线 / 批次 D 机制面之后**（§2 runbook 已备好，触发即跑）。 |
| 3 | 三案「并入既有行」的裁定都被采了吗？ | **裁决文本层面：三案一条都没有可核对的落库文字**（`docs/arch/m5-rulings.md` **正文止于裁 30**，31–34 只存于主树 memory 转述，实测 `grep 裁决 3[1-4] docs/arch/` 零命中）。可核实的只有两条**间接证据**：POWER 行归属——主树 memory 裁 32 待落项写「**采 pi 建议=并入 L1 行**」（**期望而非已落**）；FIRE 两枚举成员 + 2 新 kind **确已进 main**（`EventKind.FIRE_IGNITED/EXTINGUISHED`、`StructureCollapseCause` 含 `"fire"` ⇒ 裁 33 **已执行**，但其文字同样不在库内）。CHAOS 并入 RNG/熵行**无任何裁决记录**。⇒ **建议收官轮把裁 31–34 落进 `m5-rulings.md` 正文**（否则性能台账的「采况」栏只能标推断）。 |
| 4 | 机器观察能沉淀成什么？ | 一条硬纪律：**「性能留痕 = bench 结果 + 同轮 `throttle_probe` 比值」，缺一即不可比**。M5 外层探针时间线（时序，§3.1 全表）**09-29 机理 6.6x → 09-30 P7 8.393 → 10-01 P8 1.652 → 10-02 P10 2.055 → 10-03 P11 1.492**：两簇分明（健康 1.2–1.7 / 降频 6.6–8.4），门 2.0 落在空隙里 ⇒ **判据可靠**（无健康/降频误判记录；P10 读数 2.055 恰越门 ⇒ 该轮 soak 自 skip 属正确行为）。级联 skip 判例 + **计数恒等式（2208→2267）** 一并沉淀 §3。 |
| 5 | M6 需要什么？ | 批次 E 物化读档 ≈20–40ms ⇒ **建议新增 1 条「一次性操作档」红线 `MATERIALIZE_LIMIT_MS=50.0`，不进 tick 预算**（比照 `SNAPSHOT_LIMIT_MS=500.0` 先例，A3 自给 50ms 口径）；断线演练重放窗口唯一关注点 = **禁每 tick 全量重放**（10 日 1.728M 事件 × 0.74µs ≈ **1.28s**，P2 已钉）。§4 |
| 6 | Xeon 挂账？ | **未命中、未建基线，且本轮无法判机型**（如实登记：`gh`/token 皆无，jobs 端点 `runner=null`、check-runs `annotations=[]` ⇒ 读不到机型 notice；P8 当时能读到「机型一致：AMD EPYC 7763」的那条注释体本轮不可达）。最近两次 nightly（`37067388197` 10-02 / `36932896240` 10-01）均 **success/main**，机型**未知**。§5 |

---

## 1. 三案红线终局表

### 1.1 终局表（提案 → 裁采况 → 翻转条件 → 当前状态）
| 案 | 提案红线/常量 | 提案出处 | 裁采况（实测核对） | 进 `thresholds.py`？ | advisory→硬断言**翻转条件** | **当前状态** |
|---|---|---|---|---|---|---|
| **CHAOS** | `CHAOS_TICK_LIMIT_MS=0.05`（**并入 RNG/熵行**，兜底 `RNG_TICK_LIMIT_MS=0.10` 总行）；契约常量 `CHAOS_EMOTION_REGRESS_INTERVAL_TICKS=60`；接法红线「**禁扰动进 `PathCache` 键/喂 A\***，只作用于 `find()` 输出」 | P9 §3.1/§3.0 | **无裁决文字**（裁 32 只列 POWER 三项、裁 34 只列 N=2 采认）；但接法红线**已被 P10/P11 复用为通用课**（间接>直接） | ❌ 零命中（实测） | ①批次 A 收口 = `EntropyMixer.mix` 在生产世界循环被调（`daily_reseed_due` 为真）+ 消费点（情绪/寻路扰动）落地；②定标机实测聚合抽签 ≤0.05；③`RNG+混沌 ≤0.10` 总行断言成立 | **advisory，前置未满足**（§1.2-A） |
| **POWER** | `POWER_MAX_BIAS ≤ 0.2`（使 flip ≤0.25）；**并入 `L1_UTILITY_TICK_LIMIT_MS=6.0`，不新建 `POWER_TICK_LIMIT_MS`**；契约常量 `POWER_REGRESS_INTERVAL_TICKS=60`；接法红线「权力只作 utility 额外列，禁逐人 `replace`/`chaotic_at`」 | P10 §3.1/§3.0/§3.3 | **裁 32 状态：主树 memory 仍记「待落」**（其项内写「红线行归属=采 pi 建议并入 L1 行」=**倾向记录，非已落裁决**）；`POWER_MAX_BIAS` 数值 + 「权力→utility 系数」两项同属待落 ⇒ **本域按「并入 L1 行」施工，未新建行**（若裁 32 最终改判新行，只需追加常量，不改既有行） | ❌ 零命中（实测） | ①批次 C 核心接线（`PowerStore` → utility 权重传导）落地；②实测 flip ≤0.25 **且** 动作分布熵不塌（codex S10 §5.3 已把这条断言**从安规侧写死为共用判据**，一箭双雕：熵坍缩=「被操纵感」机器可测前兆）；③定标机 ×1.7 收口 | **advisory，前置未满足**（§1.2-B）；**但口径已被 codex 定稿**（不必再议） |
| **FIRE** | **`FIRE_AGGREGATE_EVENT_N_PER_10TICK=2`**（语义钉，不依赖机器）；`FIRE_REPATH_BUDGET_PER_FRAME=100`（复用坍塌摊还）；`FIRE_SPREAD_INTERVAL_TICKS=60`；**不新建 `FIRE_TICK_LIMIT_MS`，并入 `APPLY_P99_LIMIT_MS=0.04` + `test_apply_50_events_batch`**；接法红线「蔓延必须 O(格数)，禁 O(G²) 成对扫描」 | P11 §4.1/§4.2/§2.2 | **N=2 待裁 34 采认**（A9 已代给 advisory N=2、P11 定标机复核同值；cline C10 建议「直接接不必等定标」）；两枚举成员 + 2 新 kind **确已进 main（裁 33 已执行）**——实测 `sim/core/events.py:54/56/229`：`FIRE_IGNITED`/`FIRE_EXTINGUISHED` + `StructureCollapseCause` 含 `"fire"`；**但裁 33/34 的裁决文字均不在 `docs/arch/`**（同上） | ❌ 零命中（实测） | **N=2 语义钉可先落**（不需接线）；`FIRE_REPATH_BUDGET_PER_FRAME`/`FIRE_SPREAD_INTERVAL_TICKS` 需批次 D 机制面落盘 + 定标机实测收口 | **N=2 = 可落而未落**（等裁 34 采认，**唯一被前置卡住的可执行项**）；摊还/区间常量 **advisory，前置未满足**（§1.2-C） |

### 1.2 前置未满足的**实测**依据（不采信转述，逐项查 main）
| 案 | 查证命令 | 结果 | 结论 |
|---|---|---|---|
| **A 混沌** | `grep -rn "chaotic\|CHAOS_STREAM" sim/world/*.py sim/npc/*.py`（排除 `chaos.py`/测试） | **零命中**；`sim/world/chaos.py` **存在**（架构件已落），但 `sim/main.py`/`sim/core/tick.py` **不调 `EntropyMixer.mix`**（仅 `weather.py` docstring 描述接法） | **接线未落** ⇒ 无生产调用方可测。批次 A 收口 = Claude 域（`m5-rulings.md` 末行自陈「混沌是唯一未开工主体」） |
| **B 权力** | `grep -rn "power" sim/npc/*.py`（排除测试） | **零命中**；数据面（`0013_npc_power`+`PowerStore`）与 API 面（`outbound_guard` 禁键含 `power_level`）**均已在 main** | **决策层未消费权力档** ⇒ §1.1 的 flip/熵断言无对象。批次 C 核心接线 = Claude 域；codex S8 已裁「18 钉中 14 钉自动覆盖，接线只须既有钉仍绿」 |
| **C 火灾** | `ls sim/world/fire*.py` + `grep SKIPPED` 实跑 `test_m5_fire_state.py` | **无 `fire*.py`**；该钉**实测 skip**：`test_m5_fire_state.py:196 —「机制面文件尚未落盘（sim/world/fire*.py）——D-1 白盒扫随其落盘自动生效」` | **机制面未落、数据面已在**（A9 的 `fire_store.py` + `0014 fires` + 2 kind + 43 钉在 main）⇒ 摊还类红线无对象；**skip 是设计行为，非回归** |

> **一句话给收官轮**：三案红线**不是没做完，是排在接线后面**。当前唯一可立即执行的性能动作 = **裁 34 采认 N=2 → 落 `test_bench_fire.py::test_fire_tick_event_budget`**（不需要任何机制代码，纯判据钉）。

---

## 2. 定标执行单终版 runbook（M6 开工即派，备好即用）

### 2.1 统一前置门（不满足则**不开跑**，跑完也不算数）
```
步骤 0（必做，约 30s）：
  uv run python -m sim.tests.bench.throttle_probe
  # 期望 JSON：throttle_ratio ≤ 2.0 且 throttled=false
  # 本机历史区间：健康 1.2–1.7 / 降频 6.6–8.4 ⇒ 门 2.0 落在两簇空隙
  比值 > 2.0 ⇒ 【停止定标】，等散热/电源/负载恢复后重跑；
              硬跑的后果 = 绝对阈值假红（P6 已仲裁：本机 6.6x 持续降频，P7 起 soak 改为 skip 而非红）
步骤 0b：确认 HEAD = 当时 main（不同档位/不同代不混基线）；记录 HEAD hash 进留痕。
```

### 2.2 判定口径（全案统一，与既有红线同源）
| 项 | 口径 | 出处/理由 |
|---|---|---|
| 估计量 | **暖态中位**（`warmup_rounds=1` + `assert_median_threshold`），**禁均值** | P8：willingness 逐对增量中位 **0.21ms** vs 均值 **0.47ms**（被 ~9.6ms GC/上下文切换离群拖走，>2.0ms 离群可达 3/60） |
| 阈值推导 | **实测中位 × 1.7** 慢机余量 | 裁 13 先例（M3-P3/M4-P2 同口径） |
| seed | 固定 seed（`_SEED=7` 族）；C5：禁 `import random`/墙钟 | 确定性契约 |
| 起步形态 | `_record_proposal` **观察态**（只记录实测 vs 建议值，**不断言**） | P6 anchors 提案 + `test_bench_fast_forward.py` 先例；硬断言待数据后另裁 |
| 基线引用 | 相对漂移用 `docs/perf/baseline-epyc7763.json`（CI 档，`--benchmark-compare-fail=median:25%`）；**本机绝对阈值不用它**（档位差 20%+ 会吃掉 25% 窗口 ⇒ 漏报真回归，P7 §1） | 裁 4/裁 11；Xeon 档待 §5 命中后另建 |

### 2.3 三案定标断言映射（定标轮该测什么，逐条可执行）
| 案 | 待测项 | 定标动作 | 落点（施工单） |
|---|---|---|---|
| CHAOS | 每 tick 聚合抽签成本（`chaotic()`/`chaotic_at()` 9.3µs/次 × 实际次数） | 实测 → 校 `≤0.05ms`；若 RNG 常规 draws >0.045ms 则**收缩混沌份额**（总行 0.10 不放开） | `test_bench_rng.py` 扩一行混沌聚合断言（同文件既有 `RNG_TICK_LIMIT_MS=0.10`） |
| CHAOS | 情绪回落区间常量（提案 60） | 实测 N 档摊还：N=60 ⇒ 0.008ms/tick；N=1（每 tick 每 NPC）⇒ **0.465ms = RNG 上限 4.65x** ⇒ 若实测偏离则改契约常量而非红线 | 契约常量落 `sim/`（非 thresholds） |
| CHAOS | **接法红线**（扰动只作用于 `find()` 输出） | 白盒扫：禁 `PathCache` 键含扰动项；账一-a(9.3µs) vs 账一-b(494–647µs) = **53–70x** | 新钉：`test_..._perturbation_not_in_cache_key`（白盒） |
| POWER | `POWER_MAX_BIAS`（提案 0.2）/ flip ≤0.25 | 实测权力接入前后动作分布：flip 与**熵**（基线 2.52；0.2 档应停 ≥2.4；1.0 档越界样本 1.80）⇒ **与 codex 红线 C 共用同一条断言，不另立第二条** | `test_bench_l1_utility.py` 或决策层新钉；口径见 S10 §5.3（已定稿） |
| POWER | 权力列增量（实测 +3.05µs/50 人） | 并入 `L1_UTILITY_TICK_LIMIT_MS=6.0` 断言内（**不加新行**）；校 `tick_vectorized(50)` 18.1µs + 权力 2.8µs | 复用既有 L1 行，无新 code |
| FIRE | **N=2（语义钉，可先落，不等定标）** | 落「同因（`parent_seq` 指同一 `fire.ignited`）连续 10 tick >2 即红」；**测的是事件计数，与机器速度无关** | `test_bench_fire.py::test_fire_tick_event_budget`（S9 D-14 建议落点） |
| FIRE | O(G) 形态钉 | 实测蔓延步成本随 G **线性**（G=1024 合规 174.5µs vs 成对扫描 **39.1ms** = 224x）⇒ 断言「蔓延步 ≤ O(G) 上界」防实现漂移 | `test_bench_fire.py::test_fire_spread_is_linear` |
| FIRE | 烧毁→重算摊还 | 实测 K 档：K=1 0.63 / K=5 6.6 / **K=20 17.2ms（破 16.6ms）** / K=50 35.1ms ⇒ 定 `FIRE_REPATH_BUDGET_PER_FRAME`（提案 100，复用坍塌按帧手法） | `test_bench_fire.py::test_fire_burnout_repath_amortized` |

### 2.4 翻转操作（advisory → 硬断言，五步，顺序不可换）
```
1. 接线/机制面已进 main（§1.2 对应 skip 自动解除）；
2. 步骤 0 探针 ≤2.0；
3. 跑 -m bench 取实测中位，按 ×1.7 得收口值；若收口值 ≠ 提案值 ⇒ 报 Claude 裁（不自行放宽）；
4. thresholds.py 追加常量 + 注释（依据指针三件套：预算案 § + 裁决号 + 实测日期/比值）——
   体例照 M4-P2 段（thresholds.py:155-180）；同步 docs/perf/budget.md 对应批行；
5. `_record_proposal` → `assert_median_threshold`（观察态转硬断言），复跑 bench 全绿 + 双推。
```

### 2.5 skip-locked 钉解锁位（施工即自动生效，别漏查）
| 钉 | 现状（实测） | 解锁触发 |
|---|---|---|
| codex S9 **D-1** 机制面白盒扫 | `test_m5_fire_state.py:196` **skip** | `sim/world/fire*.py` 落盘（机制面施工）⇒ 自动生效 |
| kilo K13 出站零变更守卫 15 例 | **已全绿**（A9 收编后 15/15，第四十四轮记「skip-locked 全解锁」） | 已解除 |
| T3 实弹 `test_t3_live_fire.py` | **47 + 8 skip**（实跑：`无联网权限/无结果` + `语料无判定全应跳过`） | 需 `T3_RUN` + 模型 key（归 T4/夜跑面，非本域） |
| P9 遗留：`rng_state_persisted=False` 升硬错误 | 仍是 warning | **随定标轮一并裁**（opencode A2 修正 1） |

---

## 3. M5 机器观察汇总（**读性能留痕必读**）

### 3.1 `throttle_probe` 比值时间线（本机 i7-14650HX）
| 日期 | 轮次 | 比值 | 判定 | 后果/备注 |
|---|---|---|---|---|
| 2026-09-29 | M5-P6 仲裁 | **6.6x**（持续 90s 自旋：首个 100.4ms → 末个 661.5ms，max 689.7ms） | 降频（机理定位） | 本机 soak 红的**根因结案**：不是代码回归；短冲程基准不受影响 |
| 2026-09-30 | M5-P7 探针落地 | **8.393**（CLI：burst 16.434 / sustained worst 137.928ms）；25s 曲线 first3 **1.151/0.982/1.032** → last3 **7.316/7.877/7.345** | throttled=true | **接线生效**：soak 从 `1 failed in 433.20s` 变 `1 skipped in 25.70s`（省 7 分钟空烧） |
| 2026-10-01 | M5-P8 护栏评估 | **1.652** | 健康 | willingness Δ 改中位判据（护栏 10/10 干净、5/5 CPU 争用） |
| 2026-10-02 | M5-P10 权力预算 | **2.055** | **越门** | bench **68 passed/2 skipped**：soak 自检自 skip（**P6 门按设计工作**） |
| 2026-10-03 | M5-P11 火灾预算 | **1.492**（burst 16.449 / worst 24.543） | 健康 ⇒ **定标可用** | 首跑却报 66/4（§3.2 级联判例） |

**两簇结论**：健康 **1.2–1.7**、降频 **6.6–8.4** ⇒ 门 **2.0 落在两簇空隙内**（判据可靠，无误判记录）。
**唯一一次「健康读数 + 级联 skip」= P11** ⇒ 见 §3.2，门是**逐测试体内自测**的，与外层单次读数不是同一时刻。

### 3.2 soak 门级联 skip 判例（P11 实录，**别误读成回归**）
- 现象：同一天三次 bench 跑，读数 **66 passed / 4 skipped** → **69/1** → **69/1** → **69/1**；外层探针 1.492（健康）。
- 机理（实测 `grep _skip_if_throttled()`）：**4 个测试各挂一次体内探针**，体内探针独立于外层读数——
  `test_throttle_probe_selfcheck_off_short_circuits`(:262) / `test_m2_acceptance_tick_constant_is_7_days`(:280) /
  `test_m2_full_7day_acceptance`(:348) / `test_soak_nightly_l1_feeder_stability`(:387)。
  机器瞬时降频 ⇒ 这 4 个**同时**自 skip ⇒ passed 少 3、skipped 多 3（1 个本来就因 `PI_M2_FULL_SOAK` 默认关而 skip）。
- 处置口径：**先查 skip 明细（`-rs`），再怀疑代码**。`-rs` 显示是 `soak 降频自检` ⇒ 环境事实，重跑即可。
- 纪律（P10 首记、P11 扩写）：**性能留痕必须 = bench 结果 + 同轮 `throttle_probe` 比值 + skip 明细**；passed 数比基线少时**禁止**直接写「回归」。

### 3.3 计数对账手法（**恒等式**，三步可复算）
M5 期间派单板与本域留痕的用例数**看似冲突**，实为**同一 HEAD 的三种口径**；核对法 = **算总数，不比 passed**：
```
总数 = passed + skipped + deselected
-m "not bench" : 2013 + 125 + 70    = 2208   （P11 时点）
-m bench       :   69 +   1 + 2138  = 2208
派单板（全量）  : 2081 + 127         = 2208      ⇒ 三口径恒等 ⇒ 同 HEAD 零增删 ✓
```
- **本时点新基准（P12 实测 `--collect-only`）**：**2267 总数** = not-bench `2197 collected / 70 deselected` = bench `70 collected / 2197 deselected`。
- 差 **+59** 的来源（实测 `git diff --stat 76dd14a..d2d95c0 -- sim/tests/`）：仅两个**新增非 bench 测试文件**
  `test_m5_fire_state.py`(792 行) + `test_m5_fire_outbound.py`(343 行) = A9 的 43 钉 + K13/S9 D 系 ⇒ **口径变化，非回归**。
- **反例教训（M5 记过两次）**：①「2081 vs 2013」被当成用例丢失（实为含/不含 bench 组）；②C7/C9 的「双真相源」——**同一事实两处书写，改动不同步 ⇒ 必然打架**。
  ⇒ 本档即性能面的**单一入口**。
- ⚠ **同类风险仍开放（只报不改，归架构域 Claude）**：`docs/arch/m5-rulings.md` **正文止于裁 30**；
  裁 **31 / 32 / 33 / 34** 仅存于主树 `.orca/memory.md` 转述 + 各域文档抬头引用（实测 `grep "裁决 3[1-4]" docs/arch/` **零命中**）。
  ⇒ 本档 §1.1「裁采况」栏因此**只能引转述**；若收官轮要对外发布，需先把 31–34 落进 `m5-rulings.md` 正文。

---

## 4. M6 性能面预告（一条即可，不展开）

### 4.1 批次 E 物化读档 ≈20–40ms ⇒ **判定：需要红线，但走「一次性操作档」，不进 tick 预算**
- A3 预研实测拼装（`m5-anchor-materialization-preplan.md` §L181–195）：快照展开 ~0.1–0.4ms + 窗口重放 **≤14.8ms**（≤1000 tick × 20 事件/tick × 0.74µs）+ 语料行灌入 ~6.1ms/10k 行 + fork 克隆 ⇒ **≈20–40ms 一次性**，与现行 head-fork **同量级**（不新增量级）。A3 自给建议「≤50ms/次」。
- **裁定建议（本域）**：新增 **1 条 `MATERIALIZE_LIMIT_MS = 50.0`**，体例**比照 `SNAPSHOT_LIMIT_MS = 500.0`（单次）+ ≤0.5ms/tick 摊销**（`bench-plan.md`）——
  理由：①它是**读档/开线时的一次性开销，不在 `_tick_once` 热路径** ⇒ 与 16.6ms/8.3ms tick 红线**不同档不可混**（P6 anchors 提案同结论：「不进 tick ⇒ 不加 tick 行」）；
  ②但它**可被误用成每 tick 调用**（自动物化/后台重放）⇒ 需一条**绝对上限**拦量级，并配**「异步卸载不阻塞 tick」的接法红线**（这才是重点，同 P9/P10/P11 三课）。
  ③**不要**为它新建摊还轴：窗口重放已受 P2 快进摊还约束。
- 关注点（各一条，不展开）：**断线演练重放窗口**——10 日 = 1.728M 事件 × 0.74µs ≈ **1.28s** 一次性可接受，
  **禁每 tick 全量重放**（P2 `m5-fast-forward-budget.md` §3 已钉破线 23x 反例）；断线呈现语义归 codex S10
  （「**变的是过去，不是被跳过的未来**」——按墙钟补算 = 把未发生伪装成已发生 = 等价重掷混沌）。

---

## 5. Xeon 基线挂账（如实登记：**未命中、未建、本轮无法判机型**）
| 项 | 现状（2026-10-03 实测） |
|---|---|
| `docs/perf/baseline-xeon8573c.json` | **不存在**（`ls docs/perf/` 实测：仅 `baseline-epyc7763.json` + `runner.txt`） |
| Nightly Bench（workflow id `361944466`） | **21 个 run**；最近两次 `37067388197`(10-02) / `36932896240`(10-01) 均 `completed success` @ `main` |
| 机型判定 | **本轮读不到**：无 `gh`、无 token；REST 实测 jobs 端点 `runner=null`、`commits/{sha}/check-runs` 的 `pytest-benchmark` 条目 `output.annotations=[]`、`title/summary=null` ⇒ **机型 notice 不可达**（P8 于 10-01 曾读到「机型一致：AMD EPYC 7763」，本轮同一手法不可得 ⇒ 只能记**未知**，**不得**记「已命中/已排除」） |
| 策略（未变） | **被动为主**（裁 30-C）：nightly 自然轮询，**落 Xeon 且全绿即触发 P7 §4 八步预建**；**不再主动 dispatch**（P7 已实证 `36721350832` 落 EPYC ⇒ dispatch 不挑机位、命中率与被动相同，代价 3/4 轮白烧） |
| 触发时执行 | P7 §4 八步（`gh run list/download` → **五字段核对**（ubuntu-latest / nproc 4 / **INTEL XEON PLATINUM 8573C** / py3.12.3 / uv 同锁）→ 落 `baseline-xeon8573c.json` + `runner` 注释块 → 本地 sanity `--benchmark-compare-fail=median:25%` → **不改 `nightly-bench.yml`**） |
| 收益（若建成） | 恢复判别力：Xeon 快 20%+ 的档位差会吃掉 EPYC 基线的 25% 窗口 ⇒ 真回归在 Xeon 上表现为「恢复 EPYC 水平」、drift 为负**永不越线**（**漏报**，非假红） |
| 需要的能力 | **一次 `gh`/token 授权**（下载 artifact `bench-result`）——本域无凭据 ⇒ **列为 M6 开工前置的一个外部依赖**，与 T4 真跑等 key 同类 |

---

## 6. M5 性能域交付清单（P1–P11 对账，11 案）
| 单 | 产出（实测在库） | 性质 |
|---|---|---|
| P1 | `docs/perf/m5-time-scale-fork-budget.md` | 60×/300× 外推：每 tick 预算 `16.6/R`；降级只改节拍不改折叠 |
| P2 | `docs/perf/m5-fast-forward-budget.md` | 快进摊还；**禁每 tick 全量重放**（1.28s/23x 反例）；fold 0.74µs 窗口摊 |
| P3 | `fast_forward` 红线进 thresholds（`FAST_FORWARD_FRAME_LIMIT_MS=0.90` / `..._REQUEST_DURATION_LIMIT_S=42.0`；thresholds.py:197 行头署 **M5-P3/P5** 共担）+ soak 第 2 红观察项 | **定标**（`SOAK_*` 行属 M2-P2 ⇒ **M5 期间进 thresholds 的只有这一组两行**，其余三案全 advisory） |
| P4 | `docs/perf/m5-p4-soak-calibration.md` | 事件密度 e≈20/tick 定标；soak 观察口径 |
| P5 | `test_bench_soak.py`（ci_smoke 形态收口 + **窗口级 artifact** `perf/soak-windows.jsonl`）+ 0.90 硬断言方案 | 施工+方案 |
| P6 | `docs/perf/m5-p6-soak-arbitration.md`（**6.6x 持续降频结案，非回归**）+ `m5-p6-anchors-write-bench-proposal.md`（写路径**不进 tick ⇒ 不加行**） | 仲裁+提案 |
| P7 | `sim/tests/bench/throttle_probe.py`（新）+ `test_bench_soak.py` 接线（4 处体内自测）+ `m5-p7-xeon-baseline-and-throttle-probe.md`（Xeon 八步+被动策略） | **施工**（本机降频从「7 分钟假红」变「25.7s skip」） |
| P8 | `test_bench_willingness.py`（护栏**均值→中位**，窗口数值不动）+ `m5-p8-willingness-delta-guardrail.md` + `m5-p8-xeon-passive-monitoring.md` | 施工+台账 |
| P9 | `docs/perf/m5-batch-a-chaos-budget.md` | 混沌预算：**接法 > 数字**；账一-a/b = **53–70x** |
| P10 | `docs/perf/m5-power-budget.md` | 权力预算：**间接/直接 ≈174x**；并入 L1 行（已采）；MAX_BIAS↔熵坍缩与安规共用断言 |
| P11 | `docs/perf/m5-fire-budget.md` | 火灾预算：**N=2**（反解 `2F≤100⇒F≤50`）；**O(G²) 判红 224x**；并入 apply 行 |

**贯穿三案的一条课（性能域 M5 最大结论）**：**间接成本比直接成本高 1–2 个数量级，所以红线首先卡「接法/形态」而不是「数值」**——
P9 抽样 9.3µs vs 冷 A* 494–647µs（53–70x）→ P10 权力列 3.05µs 触发 530µs（≈174x）→ P11 烧毁 14µs 触发 K×0.7ms（K=20 破整 tick）+ 蔓延成对扫描 39.1ms vs 线性 174.5µs（**224x**）。
⇒ M6 任何新机制预算案，**第一段就该问「它的等效冷路径是什么」**。

---

## 7. 零改动留痕（2026-10-03，本机；**只读汇总，未重跑任何 bench**）
本单**只新增本文档**；`git status --short` = `?? docs/perf/m5-closure-perf-ledger.md`（另有 §3.3 清理掉的 curl 探针临时文件，**零 `sim/`/`thresholds.py`/bench 改动**）。

| 动作 | 结果 |
|---|---|
| `grep CHAOS/POWER/FIRE/MAX_BIAS/REGRESS sim/tests/bench/thresholds.py` | **零命中** ⇒ §1.1「全部 advisory 未进库」的实测依据 |
| `grep chaotic/CHAOS_STREAM sim/world/*.py sim/npc/*.py`（排除 chaos.py/测试） | 零命中 ⇒ 混沌接线未落 |
| `grep power sim/npc/*.py`（排除测试） | 零命中 ⇒ 权力决策层未消费 |
| `ls sim/world/fire*.py` + 实跑 `-k "fire or authority or chaos or power" -rs` | 无 `fire*.py`；**370 passed / 56 skipped**（skip 明细：`test_m5_fire_state.py:196` 机制面未落盘 1 例 + `test_t3_live_fire.py` 47+8 例「无联网权限/语料无判定」）⇒ 零 failed，**与三案「前置未满足」结论一致**（此跑为**只读现状取证**，非 bench 重跑） |
| `--collect-only`（两口径） | **2267 总数**（not-bench 2197+70 deselected / bench 70+2197 deselected）⇒ §3.3 新基准 |
| `git diff --stat 76dd14a..d2d95c0 -- sim/tests/` | 仅 2 个新增测试文件（+1135 行）⇒ +59 来源结案 |
| GitHub REST（无 token） | workflows 4 个；Nightly Bench 21 runs，最近 2 次 success/main；**机型 annotations 不可达**（§5） |
| `uv run ruff check .` | **All checks passed** |
| `uv run pyright .` | **0 errors, 0 warnings, 0 informations** |

**引用留痕（各单原文，非本单重跑）**：P9 1945/69、P10 1950/68、P11 2013/69（探针 1.492）、P4 soak 密度 e≈20、
P6 6.6x 机理、P7 8.393/skip 接线、P8 1.652 + 中位 0.21ms、M3 检索 0.019/0.05/0.86/43.1ms、M5-P1 fold 0.74µs / apply 78.7µs。
