# M5-P2：fast_forward 预算红线提案（承接裁 21-D-2）+ RETRIEVAL_* before 存照
> 性能域（pi），2026-09-27。任务：M5-P2（**提案制零代码**）。
> 承接：`docs/arch/m5-rulings.md` §A D-2（「不扩 speed 枚举 + 新 action `fast_forward`，长跨度
> 推进、批处理语义，pi 预算红线随附」）；M5-P1 预研 `docs/perf/m5-time-scale-fork-budget.md`（60x/300x 外推 + 降级策略）。
> 接口面输入：`docs/api/m5-prestudy-timescale-and-fork.md` §2.3（高倍速量化边界表，kilo D-2）。
> 交叉：`docs/arch/m5-plan.md` 批次 A（时间刻度）/批次 E（离线推进 tick 成本 = pi）。
> **零代码**——不碰 `sim/`、不碰 `thresholds.py`（红线只是提案，待裁后施工）。实测环境同 M5-P1
> （本机 Win11 + WSL2，Python 3.12.13，2026-09-27，多轮取中位）。

## 0. 结论速览
| # | 问题 | 结论 |
|---|---|---|
| 1 | fast_forward 的形态 | **长跨度推进 = 一次请求推进 N tick（批处理语义）**，不是「持续倍率」。它是**离散事件**（一次推进一天/一段），不是稳态节拍 → 预算口径按「**单次推进的批处理成本 + 单帧 tick 上限**」两段给，**不按倍率反比收缩**。§1 |
| 2 | 单帧 tick 上限 | 现有 `_MAX_TICKS_PER_FRAME=240`（16x catch-up 封顶）。fast_forward 若一次推进一天（86,400 tick）**不能塞进单帧** → 必须**分帧摊还**（对齐 collapse `CASCADE_EVENT_BUDGET_PER_FRAME=100` 先例）。提案：`FAST_FORWARD_TICKS_PER_FRAME`（草案 **240**，与 `_MAX_TICKS_PER_FRAME` 同值起步）。§2 |
| 3 | 批量 fold 摊还 | 快进期间 fold **不逐 tick 触发**，走**批处理窗口**（每 N tick 或每上下文切换一次），均摊 = `0.74µs × 窗内事件数 / 窗口 tick`。**禁每 tick 全量重放**（10 日 1.728M 事件 × 0.74µs = 1.28s/帧级 → 破线 23x）。§3 |
| 4 | 单帧墙钟预算 | 单帧做 240 tick × 实测 mean_tick：**10 实体 0.059ms/tick → 14ms/帧**（< `FRAME_BUDGET_SECONDS=16.6ms` ✅）；**50 实体 1.796ms/tick → 431ms/帧**（**26x 破**）→ 50 实体快进必须降采样节拍。§2.2 |
| 5 | 降采样节拍命名 | 沿用 `_PERCEPTION_EVERY_N_TICKS` 先例，新增常量族（**代码契约常量，非 bench 红线**）：`FAST_FORWARD_TICKS_PER_FRAME` / `_FOLD_WINDOW_TICKS` / `_PERCEPTION_STRIDE_FAST`。§4 |
| 6 | 「只改节拍不改折叠规则」守卫点 | 批处理窗口的 fold **必须调同一批 `fold_*` 函数**（D1-C2/R2-B「单一折叠来源」）；等价性由「同 seed 同事件流 → 逐位一致」（T2）保证。§5 |
| 7 | RETRIEVAL_* before | 存照**本机实测**（`baseline.json` **不含** retrieval 行——bench 用例 2026-09-23 才加，baseline 是 2026-09-23 首绿 run 的 21 项）。候选 0.198 / 打分 0.063 / 哨兵 1.145 / tick 总量 2.93ms（决策驱动 10 次，线 12.0）。§6 |

## 1. fast_forward 语义定位（为何口径与倍率档不同）
- **裁 21-D-2 原文**：`speed` 枚举锁 `{0,1,4,16}`（`clock.ALLOWED_SPEEDS` 硬校验）；
  快进走**新 action `fast_forward`**（长跨度推进、批处理语义）。
- **与「稳态倍率」的区别**：
  | 维度 | 稳态倍率（1x/4x/16x） | fast_forward（本单） |
  |---|---|---|
  | 时间形态 | 持续、每帧固定 tick | **一次请求推进 N tick**（离散） |
  | 预算口径 | 每 tick `16.6ms/R` 反比收缩 | **单帧批处理成本 ≤ 帧预算**（15 乘子不适用） |
  | 落库/广播 | 每帧 drain 一次 | 大跨度 → **分帧 drain**（否则单帧事件积压爆内存） |
  | 降级 | 降采样节拍 | **分帧摊还 + 窗口 fold** |
- **结论**：fast_forward 是**泊松式稀发长任务**，不是稳态负载 → 不套用 M5-P1 的 `16.6/R` 派生红线；
  而是给「**单帧能做多少 tick**」与「**整段推进的均摊成本**」两条红线。

## 2. 单帧 tick 上限与墙钟预算
### 2.1 现有约束（铁证行号）
- `sim/core/tick.py:17`：`_MAX_TICKS_PER_FRAME = 240`（16x = 960 tick/s × 4s catch-up 封顶）。
- `sim/core/clock.py:19`：`MAX_CATCHUP_REAL_SECONDS = 4.0`（`clock.advance` 只截断 dt，**不限 tick 数**——
  kilo §2.3 已标此风险）。
- `sim/api/ws.py:45`：`FRAME_BUDGET_SECONDS = 1/60`（驱动节拍）；`run_world_driver` 每帧
  `advance_frame(real_dt)` → `drain_delta/drain_events` → `on_flush` → 广播（`ws.py:614-637`）。
- `sim/api/ws.py:589` `run_world_driver` 一帧推进 0..N tick（16x 下 ~16，catch-up 上限 240）。

### 2.2 单帧墙钟（实测外推）
口径：单帧 = `FAST_FORWARD_TICKS_PER_FRAME`（草案 240）tick × 本机 mean_tick（M5-P1 driver 口径）。
| 实体数 | mean_tick（本机） | 240 tick/帧 | 对照 `FRAME_BUDGET_SECONDS`=16.6ms | 判定 |
|---|---|---|---|---|
| 10 | 0.059ms | **14.2ms** | 0.86x | ✅ 单帧可承载 |
| 50 | 1.796ms | **431ms** | **26x** | ❌ 必须降采样节拍（§4） |
> 读法：fast_forward 的单帧上限**不是**由 `FRAME_BUDGET_SECONDS` 直接算，而是「240 tick × mean_tick」。
> 10 实体可单帧跑满 240；50 实体单帧只能跑 `16.6ms / 1.796 = 9 tick` → 必须降采样。
> 注：`FRAME_BUDGET_SECONDS` 是**稳态 1x 驱动节拍**（`asyncio.sleep`），fast_forward 的一次推进
> 是**主动批处理**——其单帧成本可短时超 16.6ms **若**该帧不阻塞其它连接广播（归架构域裁定）。
> 本域给判据：**单帧推进不得让「下一帧广播间隔」超 `FRAME_BUDGET_SECONDS` 的 k 倍**（k 待裁）。

### 2.3 整段推进的均摊成本
- 推进 N tick 的**净计算成本** = `N × mean_tick`（与倍率无关）。
- 例：推进 1 游戏日 86,400 tick @10 实体 = 86400 × 0.059ms = **5.1s**；@50 实体 = **155s**。
- 摊销到帧：`N / FAST_FORWARD_TICKS_PER_FRAME` 帧，每帧 §2.2 的成本。
- **落库叠加**：`N × e × 78.7µs`（M5-P1 §4.3，`SqlEventStore.append` 单价）→ 日推进 20 事件/tick
  = 86400 × 20 × 78.7µs = **136s**（**远超 10 实体的 5.1s 计算成本**；对 50 实体的 155s 也同量级）→ 快进必须
  **批量事务 flush**（多帧事件合并一次 `store.append`，摊销 `select max(seq)` + 事务开销），这是 D1 §7-7「clone
  事务内不逐行 Python 循环」的同一诉求。

## 3. 批量 fold 摊还（对齐 collapse 先例）
### 3.1 摊还模型（复用 M5-P1 §3.2）
- fold 单价（M5-P1 实测）：`fold_matter` **0.74µs/事件**、单折叠 0.674µs、`fold_structure` STARTED 1.48µs / CHECKPOINT 0.147µs。
- **禁反例**：fast_forward 推进一天若**每 tick 全量重放当日累计事件** → `86400 × 20 × 0.74µs = 1.28s/帧级` = 破线 23x。
- **摊还策略**：fold 只在**批处理窗口边界**触发（窗口 = `_FOLD_WINDOW_TICKS`，或推进段结束）；
  均摊 = `窗内事件数 × 0.74µs / 窗口 tick`。
- **collapse 先例对照**：`CASCADE_EVENT_BUDGET_PER_FRAME=100` 用「每帧事件预算」封顶，
  单帧成本与级联总规模**解耦**（实测三档均 ~0.50ms/帧）。fold 摊还**同一手法**——窗口内事件数
  封顶（`_FOLD_WINDOW_EVENTS` 草案与 `CASCADE_EVENT_BUDGET_PER_FRAME` 同值 100 起步）。

### 3.2 观测项（不设红线）
- **窗口 fold 与事件落库的顺序**：`on_flush` 先落库（真相先于投递，`ws.py` 已定），fold 窗口
  必须在落库后（否则折的是未持久化态）——归架构域编排，本域只标依赖。
- **多分支 fold × fast_forward**：若快进期间跨分支（读档=分叉，D1），fold 窗口必须**分支内**（D1-C1）。

## 4. 降采样节拍常量命名（代码契约常量，非 bench 红线）
> 先例：`sim/core/tick.py:18` `_PERCEPTION_EVERY_N_TICKS=2`（H-1 方案 3，视觉传播降采样）。
> 纪律：**节拍是代码契约常量**（同 `CASCADE_EVENT_BUDGET_PER_FRAME`），由 T1 契约测试守卫，**不设 bench 数值红线**；
> bench 只测「降采样后的每 tick 有效成本」。
| 常量（草案命名） | 草案值 | 落点 | 依据 |
|---|---|---|---|
| `FAST_FORWARD_TICKS_PER_FRAME` | **240** | `sim/core/tick.py`（或 clock） | 与 `_MAX_TICKS_PER_FRAME` 同值起步；10 实体单帧 14.2ms 可承载 |
| `_FOLD_WINDOW_TICKS` | 待定（如 60/日切） | fold 调用侧 | 窗口 fold，对齐 collapse 事件预算 |
| `_FOLD_WINDOW_EVENTS` | **100** | fold 调用侧 | 与 `CASCADE_EVENT_BUDGET_PER_FRAME` 同值起步 |
| `_PERCEPTION_STRIDE_FAST` | 待定（如 `ceil(3.6/单帧预算)`） | `sim/core/tick.py` | 感知在快进档的降采样步长（M5-P1 §3.3） |
> 命名对齐接口面：kilo §2.6/S4 的 `SetControlMessage.action` 枚举将含 `fast_forward`；本处处只定**内核侧**常量名，协议面归 kilo。

## 5. 「只改节拍不改折叠规则」守卫点（D1-C2/R2-B）
> 这是 fast_forward 红线里**唯一必须硬保证的语义约束**（性能可降、语义不可破）。
| 守卫点 | 规则 | 落地形态 |
|---|---|---|
| G1 | 批处理窗口的 fold **必须调同一批 `fold_*` 函数** | `fold_matter_snapshot` / `fold_structure_snapshot` / `fold_material_balance` 三处（D1-C2 引用）；禁「快进专用折叠」 |
| G2 | 同 seed 同事件流 → **逐位一致**（T2） | fast_forward 的批处理**不得引入跨 tick 状态**（否则 T2 逐位一致破） |
| G3 | 折叠窗口**分支内**（D1-C1） | 窗口只读本 `branch_id` 事件 |
| G4 | 降采样**不改事件流结构** | 只改「何时 fold/感知」，事件产生与 seq 分配不变（C4/C5） |
| **验证口径** | bench 侧可加**契约守卫**：批处理窗口化的 fold 输出 ≡ 逐事件 fold 输出（M5 实现后，零代码本件不写） | `test_bench_*`（契约守卫，非数值红线） |

## 6. RETRIEVAL_* before 存照（裁 21-B-11 / opencode F3 前置）
> 背景：opencode 施工 F3（`vec_candidate_ids` 补 `branch_id` 过滤，裁 11 M5 硬前置）；
> pi 跑 before（F3 落地前）→ after（F3 落地后），漂移超 advisory 门则报数。
> **重要**：`docs/perf/baseline.json`（CI 首绿 run `35918283944`，2026-09-23）**不含 retrieval 行**——
> 检索 bench（`test_bench_retrieval.py`）2026-09-23 22:11 才入库，晚于 baseline commit。故 **before = 本机实测**（下）。
### 6.1 before 实测（本机暖态中位，2026-09-27，`test_bench_retrieval.py -m bench`，3 次独立跑取代表值）
| 用例 | 红线（thresholds.py） | 实测中位 | 余量 | 对照 M3-P2 记录 |
|---|---|---|---|---|
| `test_vec_candidate_generation_per_npc`（①） | `VEC_CANDIDATE_PER_NPC_LIMIT_MS=0.30` | **0.198ms** | 1.52x | M3-P2 记 0.233（本机同口径，档位抖动） |
| `test_retrieval_scoring_20_candidates`（②） | `RETRIEVAL_SCORE_PER_NPC_LIMIT_MS=0.30` | **0.063ms** | 4.8x | M3-P2 记 0.057 |
| `test_retrieval_full_scan_degraded_sentinel`（③） | `RETRIEVAL_FULL_SCAN_PER_NPC_LIMIT_MS=2.00` | **1.145ms** | 1.75x | M3-P2 记 0.970 |
| `test_retrieval_tick_total_decision_driven`（④） | `RETRIEVAL_TICK_LIMIT_MS=12.0` | **2.93ms**（决策驱动 10 次） | 4.1x | M3-P2 记 2.9 |
| `test_retrieval_broadcast_anti_pattern_probe`（反模式） | **无硬断言**（探测量） | 106.9ms（50 NPC 广播） | — | M3-P2 记 16.8ms（本机档位/参考实现差异，仍 6x 破 tick 预算） |
> **①/③ 偏紧记录**：候选 0.198/0.30=**1.52x**、哨兵 1.145/2.00=**1.75x**——与 M3-P2「偏紧」结论一致
> （① M3-P2 1.29x）。after 实测见 §6.2：① 未漂移（F3 未直接进参考实现 bench，见 §6.2 先决口径）。
> **反模式 106.9ms vs M3-P2 16.8ms 的差**：本机档位 + 参考实现（80 参 IN-JOIN vs 4 倍过取）差异；
> 该用例**无硬断言**，仅作防呆论据，不影响 before/after 对账口径。
### 6.2 after 实测（F3 已落 main `5bd8d1f`；本机暖态中位，2026-09-28，多跑取代表值）
**先决口径（重要）**：`test_bench_retrieval.py` 的四红线用例用**独立参考实现**（`_VecBenchWorld`
的 numpy 余弦 + IN-JOIN，`48db6cf` 起**未改动**），**不 import** `vector.py` 的 `vec_candidate_ids`——
故 F3 改 SQL **不直接进这四条 bench**。四红线 after 的意义是「**确认 F3 未波及打分链/候选形状**
（vec-preplan §18 硬边界）」；F3 的 SQL 增量由**独立探针**（真 sqlite-vec）实测（见下）。
| 用例 | 红线 | before（M5-P2） | **after（F3 后）** | 漂移 | 判定 |
|---|---|---|---|---|---|
| ① `test_vec_candidate_generation_per_npc` | 0.30 | 0.198ms | **0.198ms** | ~0% | ✅ 无漂移 |
| ② `test_retrieval_scoring_20_candidates` | 0.30 | 0.063ms | **0.062ms** | −1.6% | ✅ 无漂移 |
| ③ `test_retrieval_full_scan_degraded_sentinel` | 2.00 | 1.145ms | **1.12ms** | −2.2% | ✅ 无漂移 |
| ④ `test_retrieval_tick_total_decision_driven` | 12.0 | 2.93ms | **3.05ms** | +4.1% | ✅ 无漂移（<advisory） |
| 反模式 `test_retrieval_broadcast_anti_pattern_probe` | 无硬断言 | 106.9ms* | **16.1ms** | — | 与 M3-P2 记 16.8 一致 |
> *before 的 106.9ms 是**系统负载下的离群**（当时多 agent 并行）；无硬断言、不进对账口径。
> 结论：**四红线 after ≈ before（均 <5% 抖动，无 advisory 破线）**——F3 未触及打分链/候选形状（预期内）。

#### 6.2.1 F3 SQL 增量（独立探针：真 sqlite-vec `vec_candidate_ids`，N=600、top_k=20、forks=4、dim=384）
> opencode 明确请测「**over-fetch** 的距离计算增量」（`k` 由 `top_k` → `top_k × RECALL_OVERFETCH_FACTOR(4)`）。
> 探针建 4 分叉语料（本分支占 1/4），直调 `vec_candidate_ids`，暖态中位 300 iter × 9 round。
| 形态 | dim=384（真实） | dim=4（bench 档） |
|---|---|---|
| pre-F3：无分支谓词、k=top_k | 0.495ms | 0.036ms |
| F3：`branch_id` 谓词、k=top_k | **0.474ms**（Δ=**−0.021ms**，≈0） | 0.027ms（Δ≈0） |
| F3：`branch_id` + over-fetch k=top_k×4 | **0.532ms**（Δ_overfetch=**+0.057ms**） | 0.076ms（Δ=+0.049ms） |
| **F3 全量 vs pre-F3** | **+0.037ms（1.07x）** | +0.040ms（2.09x，基数极小） |
- **分支谓词本身 ≈ 0**（+3 参 push-down，同句内，与 R2 纪律一致）——与 opencode「预期≈0」相符。
- **over-fetch 的增量 +0.057ms**（k 20→80）：vec0 扫描 4x 候选但 ANN 亚线性，只 +14%；仍是**真 SQL 增量主项**。
- **F3 全量 +0.037ms（1.07x）≪ 0.30ms 红线**（余量 8x）→ **不破线、无需放宽**；探针验证「过滤进召回句、禁 Python 侧后过滤」的性能代价可忽略。
- 破例前置：若 `RECALL_OVERFETCH_FACTOR` 再上抬（F>4 需 per-branch 向量分区，D1 §5-C5 已列后续件）→ 该增量会随系数线性放大，须届时复测。

#### 6.2.2 对账点 5 收口
- D1 §7 对账点 5「F3 加分支过滤的检索成本」→ **关闭**：分叉谓词 ≈0 + over-fetch +0.057ms，全量 1.07x，不破线；
- `pi ↔ opencode` 交叉对账（D1 §7 全 9 点）至此**全部收口**（5 由本单关闭，1–4/6–9 M5-P1 已回填）。
- **baseline 建议**：`docs/perf/baseline.json` 应随下次 nightly 重生成时补入 retrieval/structure/willingness 行（现 21 项为 2026-09-23 旧集，缺 M3-P2/M4 新增 bench）——属 CI 域，本单只登记。

## 7. 边界与门禁
- **零代码**：不动 `sim/`、`thresholds.py`、迁移；只新增本文件 + memory ⑤节。
- **红线只是提案**：fast_forward 两红线（单帧 tick 上限 / 批量 fold 摊还）与四个常量命名待 Claude 裁后施工。
- **越界声明**：`run_world_driver` 分帧编排 / 单帧超时 k 倍判据 → 架构域；`SetControlMessage.action` 枚举面 → kilo；F3 SQL → opencode。
- **验证**：纯文档 + 本机实测存照；内容可追到代码行号/实测（每表标注来源）。
