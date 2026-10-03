# M5-P11：批次 D 火灾蔓延/生态·性能预算案 + CHAOS/POWER 定标准备清单（零代码）
> 性能域（pi），2026-10-03。任务：M5-P11（**重派，二次超期致歉**——预算案+定标清单照给，N 值必须落）。
> **零代码**：不碰 `sim/`、不碰 `thresholds.py`（红线只是提案，待裁后施工）。实测环境：本机 Win11，Python 3.12，
> 2026-10-03，多轮取中位；**本轮 `throttle_probe` 比值 1.492 < 2.0（未降频，定标可用）**。
> 三条已收敛输入（预研三单互锁，直接采纳不重判）：
> ① **W-D3 N 值是唯一开放项**——聚合口径已由 A8/S9 裁「**火势状态变更驱动**（无变更零事件）+ 按场聚合」，只差数值；
> ② 火灾只动**可重放表**（S9/A8「火场中间态不入库 ⇒ 物化包不为火扩格式」）⇒ 间接账聚焦「一次烧毁→结构消失→冷 A* 重算→搬家/重建（检索+折叠）」；O(N²) 邻居查询风险判定；
> ③ **守恒约束**：烧毁必产 `to_ref="world:burned"`（T1 守恒钉已锁）⇒ 事件条数账按「每次燃烧=1 damage 事件+聚合 spread 信号」口径。
> 依据链：`docs/security/m5-fire-threatmodel.md`（codex S9 红线 A/B/C + D-14 预算判据）、`docs/data/m5-fire-data-preplan.md`（opencode A8 聚合口径）、`docs/api/m5-fire-api-prestudy.md`（kilo K12 §1.2 代价 3「N 由 pi 定标机定」+ A9 advisory N=2）；前单 P9（`m5-batch-a-chaos-budget.md` 抽样 vs 冷 A* 账一-b 教训）、P10（`m5-power-budget.md` 权力间接传导）。

## 0. 结论速览
| # | 问题 | 结论 |
|---|---|---|
| 1 | **W-D3 聚合阈值 N（本单必交付项）** | **采认 opencode A9 的 advisory N=2，并给出定标机依据**。判据：一场火「同因（`parent_seq` 指向同一 `fire.ignited`）」在连续 10 tick 内聚合 damage 事件 **>2 即实现偏差**（= 退化为格驱动 per-tick）。**交叉校验**：反解 `2F ≤ 100 ⇒ F ≤ 50`（F=同时活动火场数，机制面参数）——**在 F≤50 假设下** N=2 恰好等于既有 `CASCADE_EVENT_BUDGET_PER_FRAME=100` 上限，**不新造预算轴**（F>50 见行 4b / §6-1）；per-tick 合规上界 ≤1 条/火 ⇒ 10 tick 最多 10，取 2 给「一场火 10 tick 内跨过 2 个损伤阈值」留余量，同时任何真·格驱动（每格每 tick 一条）在 10 tick 内产 ≥10×格数 ≫2，**稳定判红**。§2 |
| 2 | 火灾蔓延的**直接**每 tick 成本？ | 聚合 damage 事件边际 **~4.9µs/条**（construct+observe+chunk-invalidate，暖态中位）；即便**格驱动全烧**（1024 格铺满 32×32）也只有 **8.23ms/tick**（construct+observe+invalidate on 1024-entry cache）——**直接成本从不破线，破线的是间接账**。§1 |
| 3 | **间接账（本单核心，= 火灾的「账一-b」）** | 一次烧毁（`structure.collapsed`+`matter.collapse`+`material_moved→world:burned` 3 事件=**14µs**）→ chunk 失效 → **K 个 NPC 冷 A* 重算**：实测 K=1 **0.63ms**、K=5 **6.6ms**、K=20 **17.2ms（破 16.6ms 整 tick 预算）**、K=50 **35.1ms**。烧毁的自成本 14µs 却触发 K×~0.7ms 重算（K=50 摊算；K=5 档含长路线偏高至 ~1.3ms/人）——**与 P9 抽样→冷 A* 的账一-b 同构**，只是这次的「抽样」是「烧毁 3 事件」。§3 |
| 4 | **O(N²) 邻居查询风险（判红）** | 蔓延引擎若用**成对扫描**（每火格 × 全火格判相邻）算前沿扩张：实测 G=16 pair 13µs、G=256 **3012µs**、G=1024 **39100µs（39ms，一次蔓延即破线）**；O(G) 形态（膨胀四邻，`np.roll`/set 邻接，M2 嗅觉/坍塌图同款）G=1024 仅 **174µs**（**224x 差**）。⇒ **红线：蔓延必须是 O(格数) 邻域膨胀/网格平流，禁 O(格数²) 成对扫描**。§3.2 |
| 4b | **N 与 F 的耦合** | `2F ≤ 100 ⇒ F ≤ 50`（F=同时活动火场数，机制面参数）。N=2 只在 F≤50 下嵌进既有坍塌摊还；**F 若更大 ⇒ 火灾与坍塌共用一条按帧摊还队列，不得调大 N**。§2.2 |
| 5 | 红线建议 | ①直接账**并入既有 apply 行**（`APPLY_P99=0.04` + `test_apply_50_events_batch`），**不新建火灾每 tick 数字行**；②**新造两条可证伪语义红线**（非数字阈值）：W-D3 聚合 N=2 钉 + O(G) 蔓延形态钉；③间接账用**烧毁邻域重算限流**守（复用坍塌 `CASCADE_EVENT_BUDGET_PER_FRAME=100` 按帧摊还先例，把「一次烧毁 → 全城重算」摊成「每帧 ≤M 条重算」），由寻路/检索既有行（`CHUNK_INVALIDATION=2.0`/`RETRIEVAL=12.0`）自然吸收。§4 |
| 6 | 定标准备（§D，另单执行） | CHAOS/POWER/火 三案的**数值红线全部待批次 C/D 接线合入后跑定标轮**（本机降频门 1.492 已验可用）。本单把清单**备好即用**（§5）：定标机命令、断言映射、advisory→硬断言的翻转条件、skip-locked 钉解锁位。 |

---

## 1. 直接账：蔓延/烧毁事件的每 tick 成本（实测）

**事件族**（A8/K12 已裁）：蔓延→`matter.damage`（走既有族，聚合）、烧毁→`matter.collapse`+`structure.collapsed{cause:"fire"}`+`material_moved{to_ref:"world:burned"}`、边界→`fire.ignited`/`fire.extinguished`。

| 测项（暖态中位，1024-entry 热缓存） | N=1 | N=2 | N=3 | N=5 | N=20 | N=100 | N=1024（全烧） |
|---|---|---|---|---|---|---|---|
| `matter.damage` 聚合事件 construct+observe+invalidate | 9.4µs | 14.3µs | 20.8µs | 32.7µs | 105.7µs | 510.2µs | **8.23ms** |
| 边际 µs/事件 | — | ~4.9 | ~5.1 | ~5.0 | ~4.8 | ~5.1 | ~8.0（含全表扫） |

- **单条聚合蔓延事件 ~4.9µs**（construct 4.6µs 主导：pydantic `MatterPayload` 校验 + `to_store_dict` 0.3µs）；store 行 **293B**（`to_store_dict` 实测）⇒ 100 游戏日单场火存储 ~KB 级，噪声。
- **直接成本从不破线**：格驱动最坏（1024 格全烧铺满）也仅 8.23ms/tick（< 16.6ms tick 预算，= `TICK_P99_LIMIT_MS` 边界）。**⇒ 火灾的直接账不是风险点，§3 的间接账才是。** 这与 P9「inject 摊摊可忽略，真成本在抽签」结构一致，也与 opencode A8「零新增预算行」结论吻合。

---

## 2. W-D3 聚合阈值 N 值（本单必交付）：**N=2**

### 2.1 定义（沿用 codex S9 D-14 判据，非新造）
> 「连续 10 tick **同因**蔓延事件 > N 即实现偏差」，同因 = `parent_seq` 指向同一 `fire.ignited`；口径 = **火势状态变更驱动**（无变更零事件），每 tick 每场火蔓延事件 ≤1 条聚合。

### 2.2 三条推导依据（定标机实测 + 既有常量交叉，不给凭感觉的数）
1. **不新造预算轴（最强约束）**：opencode A8「阈值与 K 由 pi 定标」+ 既有坍塌摊还 `CASCADE_EVENT_BUDGET_PER_FRAME=100`。
   取 **N=2** ⇒ 每 tick 火灾族事件上界 = **2 × F**（F = 同时活动火场数）。
   **F 是机制面参数（未施工，本域不发明），但反解可得红线**：`2F ≤ 100 ⇒ F ≤ 50`——
   即 **N=2 在「同时 ≤50 场火」的假设下恰好嵌进坍塌已有的按帧封顶，零新增预算轴**（M4-P1 先例：能并入既有轴就不另起炉灶）。
   ⇒ **若 Claude 定的 F > 50，则须改走「火灾并入坍塌同一条按帧摊还队列」（共用 100 上限）而不是调大 N**；
   这一点列为 §6 待裁第 1 项（F 的上界归属机制面裁，本域只给「N 与 F 不得同时放大」的约束式）。
2. **A2 混沌量级口径对照**（重派卡点名）——注意**「常态速率」与「判红天花板」是两个量纲，不可直接比**：
   - **常态速率**：A2 混沌注入 20–150 条/游戏日 = **0.0002–0.0017 条/tick**。火灾按场聚合后同量纲对照——
     一场火从点燃到熄灭跨过的**「可讲述」状态跃迁**（点火 / 量级跃迁 / 烧毁 / 扑灭）typical **1–4 条/场**，
     与混沌注入「一个事件才一条」同源（DESIGN §11「可讲述才注入」判据，codex W-D3 §④ 明写「沿用混沌判据，不是新标准」）。
   - **判红天花板**：N=2/10tick = **每场火 0.2 条/tick** 上界，× F=50 ⇒ **≤10 条/tick**，
     恰为既有稳态事件量（`budget.md` §1 稳态 ~20 事件/tick）的 **50%**——即「天花板用掉一半预算」的松紧度，
     既不至于让合规实现（1–4 条/场全程）偶发误红，又离格驱动（10×前沿格条）差 1–3 个数量级，判红灵敏。
   ⇒ 换句话说：**N 定的是「异常检测的门」，不是「常态成本的上限」**；常态成本由 §1 直接账（4.9µs/条）与 §3 间接账担保。
3. **判红灵敏度（实测反证）**：真·格驱动（每格每 tick 一条）在 10 tick 窗口内产 `10 × 前沿格数` 条 ⇒ 即便前沿只有 1 格也 = 10 条 ≫ N=2，**稳定判红**；合规「状态变更驱动」在 10 tick 窗口内的条数 = 该窗口内的状态跃迁数（一场火全程 typical 1–4 条，分摊到任一 10-tick 窗口绝大多数 ≤2），**不误红**。N=1 会因「同一 tick 边界跨两阈值」偶发误红，N=2 给 1 条抖动余量。

### 2.3 与 A9 advisory 的关系
opencode A9 在 P11 缺席期代给 **N=2 advisory**——**本单定标机复核后采认同值**，非另裁。施工时落钉：`sim/tests/bench/test_bench_fire.py::test_fire_tick_event_budget`（codex S9 D-14 建议落点）+ `docs/perf/budget.md` D 批行。**未定标前 advisory**（P6）。

---

## 3. 间接账（本单核心）：烧毁的传导链 = 火灾的「账一-b」

> 传导链（重派卡点名）：**一次烧毁 → 结构消失（`structure.collapsed`）→ 该格变阻 → 途经此格的寻路缓存失效 → NPC 冷 A* 重算 → 搬家/重建决策再触检索+折叠。**
> 与 P9 同构：烧毁自付 14µs（3 边界事件 construct），但**触发一次全城级重算 = K×0.85ms**。

### 3.1 烧毁 → 冷 A* 重算（实测，K=受影响 NPC 数）
64×64 图，预热 `PathCache`（64 条途经烧毁格的路径），单点烧毁 → `observe_events` 精确失效 → K 个 NPC 各自重算新路线（冷路径）：

| K（烧毁触发的重算 NPC 数） | 每 tick 成本（实测中位） | 判定 |
|---|---|---|
| 1 | **0.63ms** | 单 NPC，吸收进 L1 决策行 |
| 5 | **6.6ms** | 贴 `L1_UTILITY_TICK_LIMIT_MS=6.0` 上沿 |
| 20 | **17.2ms** | **破 16.6ms 整 tick 预算** ✗ |
| 50（全员） | **35.1ms** | 结构性爆预算 ✗✗ |

**这就是火灾的账一-b**：`structure.collapsed` 是缓存失效**触发器**——火场蔓延到热门走廊（多人通勤路径），一次烧毁即引发 K 个 NPC 冷 A* 重算。**P=K=20 即破线**。约束点不在烧毁事件本身（14µs），在「烧毁是否落在共享路径 + 有多少 NPC 依赖该路径」。

### 3.2 O(N²) 邻居查询风险判定（重派卡点名，**判红**）
蔓延引擎算「下一 tick 前沿扩张」：合规 = O(格数) 邻域膨胀；反模式 = 成对扫描每火格×全火格判相邻。实测（前沿 G 格）：

| G（火场格数） | O(G²) 成对扫描 | O(G) 四邻膨胀 | 差 |
|---|---|---|---|
| 16 | 13.0µs | 2.3µs | 5.7x |
| 64 | 188.5µs | 9.7µs | 19x |
| 256 | 3012µs | 41.1µs | 73x |
| 1024（32×32 铺满） | **39.1ms** | 174.5µs | **224x（O(G²) 一次蔓延即破线）** |

⇒ **红线（语义，非数字）：蔓延必须用 O(格数) 邻域膨胀/网格平流（M2 嗅觉 `np.roll` Eulerian、M4 坍塌承重图 BFS 同族），禁 O(格数²) 成对相邻扫描**。32×32 铺满场用成对扫描，一次蔓延步就 39ms = 破线 2.4x。这是 P9「抽样 9.3µs vs 冷 A* 494–647µs」教训在**蔓延本体**上的复现——算法形态选错直接爆一个量级。

### 3.3 存储/折叠尾账（守恒约束下）
「每次燃烧=1 damage 事件+聚合 spread 信号」⇒ 烧毁 burst = 3 事件（14µs）+ 1 聚合 spread；fire 只动可重放表（`matter_state`/`structures`/`material_balances`，S9/A8 裁火场中间态不入库），fold 单价 0.74µs/事件（M5-P1）⇒ 存储/折叠侧**噪声级，不构成新风险**，与 P9 inject 同口径。`to_ref="world:burned"` 已锁 T1 守恒 ⇒ 事件条数账不含额外守恒开销。

---

## 4. 红线建议

### 4.0 两条最紧要的**语义**红线（接法/形态，非数字阈值）——承 P9/P10 课
- **火灾账一-b 红线**：烧毁落共享路径时，**禁止一次烧毁触发无上限全量 NPC 重算**。复用坍塌 `CASCADE_EVENT_BUDGET_PER_FRAME=100` 摊还先例——把「烧毁→重算」纳入**按帧限流**（每帧 ≤M 条受影响 NPC 重算路径，其余排队到后续帧），使 K=20/50 档摊成每帧常数，**不随火场规模增长**。由寻路既有行 `CHUNK_INVALIDATION_TICK_LIMIT_MS=2.0` 自然吸收。
- **O(G²) 红线**：蔓延形态必须 O(格数)，见 §3.2。

### 4.1 直接账：**并入既有 apply 行，不新建火灾每 tick 数字行**
一句裁定（同 P9 并入 RNG/熵行、P10 并入 L1 决策行的同一逻辑）：蔓延/烧毁事件的每 tick 成本**走既有 `APPLY_P99_LIMIT_MS=0.04` + `test_apply_50_events_batch`**（thresholds.py:175 已注明「走既有 apply 通路」）——**不新增 `FIRE_TICK_LIMIT_MS`**。理由：直接账边际 4.9µs/事件从不破线（§1），新建行只会与 apply 行双算且测不准（取决于火场规模）。

### 4.2 W-D3 聚合钉 N=2（新造，进 thresholds 待施工裁）
```
# --- M5-P11：批次 D 火灾蔓延事件预算（W-D3 判据；N 值 pi 定标机复核 A9 advisory）---
# 依据 docs/perf/m5-fire-budget.md §2 + codex S9 D-14 + opencode A8 聚合口径。
# 一场火（同 parent_seq）连续 10 tick 聚合 damage 事件 > N 即实现偏差（= 退化格驱动 per-tick）。
# N=2 依据：①N×同时火场上界50=100=既有 CASCADE_EVENT_BUDGET_PER_FRAME（不新造预算轴）
#          ②0.2 条/tick 上界已是 A2 混沌密度 100–1000x（不误红合规）；③真格驱动 10×前沿格 ≫2（稳判红）。
# 未定标前 advisory（P6）；落钉 test_bench_fire.py::test_fire_tick_event_budget。
FIRE_AGGREGATE_EVENT_N_PER_10TICK = 2
# 烧毁→重算按帧限流（复用坍塌摊还先例；提案值，定标机实测×1.7 慢机余量后收口）
FIRE_REPATH_BUDGET_PER_FRAME = 100
```
### 4.3 契约常量复用（非红线，随施工对齐）
```
FIRE_SPREAD_INTERVAL_TICKS = 60   # 火场强度逐格推进区间（慢变量，复用 P9/P10 regress 同族）
```
- 与 `_PERCEPTION_EVERY_N_TICKS` / `CHAOS_EMOTION_REGRESS_INTERVAL_TICKS=60` / `POWER_REGRESS_INTERVAL_TICKS=60` 同族 ⇒ **火灾本体是低频 pass，非每 tick**（budget §2.9 嗅觉「每 N tick 更新一次」先例）。

### 4.4 P6 纪律（承 P8/P9/P10）
`FIRE_AGGREGATE_EVENT_N_PER_10TICK=2`（语义钉，不依赖机器）可先落；其余数字（重算摊还帧预算、`FIRE_SPREAD_INTERVAL_TICKS`）为提案值，**未定标前 advisory**。绝对阈值降频机必假红，落地前在定标机（`throttle_probe` 比值 ~1.0）暖态中位实测再收口。

---

## 5. CHAOS/POWER/火 定标准备清单（§D，另单执行；本单备好即用）

> **触发条件**：Claude 批次 C 权力核心接线 + 批次 D 火灾机制合入后，各派一张**定标执行单**。以下为备好即用清单，无需再推导。

### 5.1 定标机口径（全案统一）
- 机器：`throttle_probe.py` 比值 ≤ 2.0（本机 1.492 可用；>2.0 则 soak 自检自 skip，见 P10 坑）。
- 断言：暖态中位（`warmup_rounds=1` + `assert_median_threshold`），固定 seed，多轮取中位（P8：均值离群教训）。
- 阈值：`实测中位 × 1.7` 慢机余量（裁 13 先例）。

### 5.2 三案红线映射（advisory → 硬断言翻转条件）
| 案 | 待定标红线 | 现状 | 翻转硬断言的条件 |
|---|---|---|---|
| CHAOS（P9） | `CHAOS_TICK_LIMIT_MS=0.05` | advisory | 混沌接线（inject+消费点）合入 → 定标机实测聚合抽签 ≤0.05 → 转硬 |
| POWER（P10） | `POWER_MAX_BIAS≤0.2`、flip≤0.25 | advisory | 权力核心接线合入 → 实测分布漂移在阈内 → 转硬 |
| FIRE（P11） | 重算摊还帧预算、`FIRE_SPREAD_INTERVAL_TICKS=60` | advisory | 火灾机制合入 → 定标机测 K 档重算摊平 → 收口 `FIRE_REPATH_BUDGET_PER_FRAME` |
| W-D3 钉 | `FIRE_AGGREGATE_EVENT_N_PER_10TICK=2` | **语义钉可先落** | 不依赖机器，落 test_bench_fire 即生效 |

### 5.3 skip-locked 钉解锁位（施工即解锁，别漏）
- codex S9 **D-1**（机制面白盒扫）：因 `sim/world/fire*.py` 未落盘而 skip ⇒ 火灾机制落盘即自动生效（A9 已述）。
- P9 §5：`rng_state_persisted=False` 混沌接线后建议从 warning 升硬错误（opencode A2 修正 1）——定标轮一并裁。

### 5.4 执行单模板（我备好，Claude 派单时直接引）
```
定标执行单 M5-P11b（示例，接线合入后派）：
1. 落 sim/tests/bench/test_bench_fire.py：test_fire_tick_event_budget（N=2 钉）
   + test_fire_spread_is_linear（O(G) 形态钉：G=256 蔓延步 ≤ O(G) 上界）
   + test_fire_burnout_repath_amortized（重算按帧摊还 ≤ 收口值）
2. thresholds.py 追加 FIRE_* 常量（本单只给提案值，定标实测 ×1.7 收口）
3. budget.md 补批次 D 火灾行（名义/上限，并入 apply 行口径）
4. 跑 not-bench + bench 全量留痕；ruff/pyright 0；双推。
```

---

## 6. 待裁 / 交叉
1. **F（同时活动火场数）上界**归机制面（Claude）裁——本域只给约束式 **`N × F ≤ CASCADE_EVENT_BUDGET_PER_FRAME = 100`**：
   N=2 与 F≤50 必须**至少满足其一**；若机制要 F>50，采「火灾与坍塌**共用同一条按帧摊还队列**」（共用 100 上限），
   **不得**用调大 N 来放宽（调大 N 即失去 W-D3 卡格驱动的判别力，§2.2 依据 3）。
2. **K（烧毁影响的重算 NPC 数）是否需要独立摊还**待施工裁——建议**复用坍塌 `advance_cascade` 的按帧 budget 手法**
   （M4-D2c 已证「单帧成本与级联总规模解耦」，实测三档均 ~0.50ms/帧），把重算排进队列而非同 tick 全量重算。
3. **`FIRE_REPATH_BUDGET_PER_FRAME=100` 与 `FIRE_SPREAD_INTERVAL_TICKS=60` 均为提案值**，待批次 D 机制合入后
   定标机实测 ×1.7 收口（§5）；未定标前 advisory。
4. **交叉 codex S9**：W-D3 N=2 钉落 `test_bench_fire.py::test_fire_tick_event_budget`（S9 D-14 建议落点）；
   O(G²) 形态红线（§4.0）宜同钉一条「蔓延步成本 ≤ O(G) 上界」断言（防实现漂移成对扫描）。
5. **交叉 opencode A8/A9**：火灾走既有 `matter.*` 族 ⇒ 直接账并入 apply 行（§4.1）零新增预算轴；
   火场中间态不入库（A8）⇒ 本单存储尾账为噪声级（§3.3），与 A8「物化包不为火扩格式」结论一致。
6. **T3 实弹（`sim/tests/test_t3_live_fire.py`）**：当前全 skip（需 `T3_RUN`+模型 key）——
   火灾机制施工后，W-D3 N 钉宜进 T3 语料面（纵火题面）联动复验。

---

## 7. 零改动留痕（2026-10-03，本机）
本单**只新增本文档**，`sim/`、`thresholds.py`、既有 bench 文件零改动（`git status` 仅 `?? docs/perf/m5-fire-budget.md`）。

| 命令 | 结果 |
|---|---|
| `throttle_probe` | 比值 **1.492 < 2.0**（burst 16.449 / sustained worst 24.543ms）——未降频，定标可用 |
| `uv run pytest -q -m "not bench"` | **2013 passed / 125 skipped / 70 deselected**，4 warnings，135.6s |
| `uv run pytest -q -m bench` | **69 passed / 1 skipped**（2138 deselected）——稳定复跑 3 次同值；skip = 7 日完整 soak（`PI_M2_FULL_SOAK` 默认关） |
| `uv run ruff check .` | All checks passed |
| `uv run pyright .` | 0 errors, 0 warnings, 0 informations |

**两处计数对账（免得下轮误读）**：
1. **派单板写「main `76dd14a` = 2081 passed / 127 skipped」**（全量含 bench），本单 `-m "not bench"` 实测
   **2013 passed / 125 skipped / 70 deselected** ⇒ 两侧**用例总数都是 2208**（2013+125+70 = 2081+127 = 2208 ✓
   同 HEAD 无增删）。差异只在 bench 组：本单 bench 跑 **69 passed / 1 skipped** ⇒ 合并 = 2082 passed / 126 skipped，
   与卡面 2081/127 **恰好差 1 个用例在 passed↔skipped 间翻转**——那正是 soak 降频自检门（见下条），
   **非回归、非用例增删**。
2. **本轮首跑 bench 曾报 66 passed / 4 skipped**，随后三次稳定 69 / 1——
   那 4 个 skip 是 `test_bench_soak.py` 的**降频自检门**（`_skip_if_throttled`，共 4 个 soak 测试挂此门）
   在那一次运行中判定降频而级联自 skip（P6 门按设计工作，非回归）；`throttle_probe` 随后读数 1.492（未降频）。
   ⇒ **P10 记过的坑再次复现并扩写：bench 的 passed 数会随环境降频门浮动，留痕必须同轮跑 `throttle_probe`
   并记比值；若 passed 数比基线少，先查是不是 soak 门级联 skip，再怀疑代码。**

**实测探针（临时脚本，已删）**：`matter.damage` 聚合事件 construct 4.6µs（边际 ~4.9µs）/ store 行 293B / 格驱动全烧 1024 格 construct+observe+invalidate **8.23ms**（直接账不破线）/ 烧毁→冷 A* 重算 K=1 **0.63ms**、K=5 **6.6ms**、K=20 **17.2ms（破 16.6ms）**、K=50 **35.1ms** / O(G²) 成对扫描 G=16 13µs、G=256 **3012µs**、G=1024 **39.1ms** vs O(G) 四邻膨胀 G=1024 **174.5µs**（224x）/ 烧毁 burst 3 事件 14µs / fold 0.74µs（M5-P1）/ 对照 P9 冷 A* 494–647µs、A2 混沌 20–150 条/游戏日、CASCADE_EVENT_BUDGET_PER_FRAME=100。
