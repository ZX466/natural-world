# M6 内容面性能预算案（生态 / 动物 / 语言阶层 / 迷雾）
> 性能域（pi），2026-10-04。任务：M6-P4（**零代码**；thresholds 零改动；所有权=`docs/perf/m6-content-budget.md`+自树 memory）。
> 基线：main `3f321b4`（= 本树 HEAD，开工同头确认；2362 passed / 121 skipped）。
> 输入：P13 红线建议（动物 ∝ 半径² 并入 PERCEPTION 行、**零新通道**）；P9/P10/P11 三案教训；`m5-batch-a-chaos-budget.md` / `m5-fire-budget.md` / `m5-power-budget.md` 的实测口径。
> **本档产物性质**：给四个**即将施工**模块的（a）每 tick 成本量级、（b）间接账与红线归属、（c）**换机/降频解除后的最短定标单**。**所有数字为模拟量级**（模块未落），但**每个数字都锚在一个本机实测口径上**。

## 0. 结论速览
| 模块 | 每 tick 成本量级（模拟） | 最大风险（间接账） | 红线归属（**零新行**） |
|---|---|---|---|
| **生态** | **≤7µs/tick**（到期桶 + 每 60 tick 窗）⇒ 若写成「每 tick 全量扫」= **~400µs/tick 顶穿 0.10 行** | 窗口化被实现成"每 tick 全量扫"（最可能的回归形态） | `CHUNK_EVENT_SCAN_LIMIT_MS=0.10`（若走 chunk 扫）+ `APPLY_P99_LIMIT_MS=0.04`（事件边际） |
| **动物**（三只） | L1 **+3 行 ≈ +9µs**（并入 6.0 行）；嗅觉 **+3 源 ≈ +6%**（并入 1.0 行）；LOS 配对 **+18–31%** of human50（P13 实测口径） | 半径 16–24 ⇒ 配对 ∝ 半径² 的膨胀（P13 几何：1.78–4.0×），**不是**多加 3 个 NPC | `PERCEPTION_TICK_LIMIT_MS=3.6`（半径² 并入）+ `SMELL_WIRED_TICK_LIMIT_MS=1.0`（源）+ `L1_UTILITY_TICK_LIMIT_MS=6.0`（行） |
| **语言阶层** | **本地算力 ≈ 0**（O(1) 文本拼接；`norms.MAX_NORMS=5` ⇒ 现 119 字符 ≈ **119 token 上界**） | **token 增量不在 tick 面**；风险是**误挂 `messages[0]` 破坏前缀缓存**⇒ 增量被 LLM 侧放大成假账 | **不进 tick 红线**；token 账归 LLM 远程延迟档（P5，advisory）；本地只钉「禁破 messages[0] 前缀缓存」 |
| **迷雾** | **~0**（`reveal` 0.53µs/次 cap ≤16 chunk；`is_revealed` 0.07µs） | 揭示 → 寻路缓存失效？**v0 无钩子**；若耦合 ⇒ 满表扫 103.3µs × 16 chunk = **1.65ms**（正好在既有 2.0 行内、但离穿一步） | `CHUNK_INVALIDATION_TICK_LIMIT_MS=2.0`（**已存在**）+ 契约常量（若需按帧摊还）；`find` **不在 tick 路径**（`ws.py:569` 玩家指令）⇒ **不进 tick 行** |

**机器门结论**：本机当前 `throttle_ratio` **1.547 ≤ 2.0**（本单现测）⇒ 门 2 **暂达**；但因跨轮在 1.547–2.657 间波动（P6 判例），**派标定轮前必须现测**；最短执行单见 §4（**换机/降频解除即跑**）。

---

## 1. 既有实测锚点（本单全部推导的地基）
| 锚点 | 数值 | 出处 |
|---|---|---|
| `chaotic()` 纯函数重建 | **9.3µs/次**（缓存 `gen.random()` 为 0.30µs ⇒ 31x） | `m5-batch-a-chaos-budget.md` §2.1 |
| `matter.damage` 边际 | **~4.9µs/条**（construct+observe+chunk-invalidate 暖态中位） | `m5-fire-budget.md` §1 |
| 格驱动全烧上界（1024 格） | **8.23ms/tick**（"直接成本从不破线，破线的是间接账"） | 同上 |
| 冷 A\*（全图对角 64×64） | **559.7µs**（本机复测；P11 账一-b 带 494–647µs ✓ 一致） | 本单 + `m5-batch-a-chaos-budget.md` |
| `PathCache.invalidate` 满表扫 | **103.3µs 中位 / 177.9µs 最大**（4096 条，按 chunk 遍历全表） | 本单实测 |
| `PathCache` 容量 | `max_entries=4096` + FIFO 淘汰 | `sim/world/pathfinding.py` |
| 感知逐人基准 | needs 推进 3.2µs/人 ⇒ 175µs/50 人；`PERCEPTION_TICK_LIMIT_MS=3.6` | `m5-power-budget.md` §1 + thresholds |
| 嗅觉（源=全体实体） | 50 源 0.116ms / 100 → 0.135 / 200 → 0.151 / 500 → 0.335；**`SMELL_WIRED_TICK_LIMIT_MS=1.0`** | thresholds:62-88 注 |
| L1 效用矩阵 | 50 人 **211.75µs**（= `L1_UTILITY_TICK_LIMIT_MS=6.0` 的 3.5%，余量 ~0.29ms） | 本单 M6-P2 实测 |
| 混沌入 prompt 的既有口 | `norms.MAX_NORMS=5` ⇒ top-5 知识 fact 直用 ⇒ **119 字符 ≈ 119 tok（CJK 1:1 上界）**；**挂 `messages[1]`、禁破 `messages[0]` 前缀缓存** | 本单实测 + `sim/npc/norms.py` |

---

## 2. 逐模块预算账

### 2.0 公共成本模型（本档统一口径）
**每 tick 成本 =（窗口化摊销 or 全量扫）×（单次纯函数成本）+ 事件边际。**
- **单次纯函数成本档位**：查表/算术 **0.3–2µs**（缓存随机 0.30µs 为下限锚，`chaotic()` 重建 9.3µs 为「别这么写」上限锚）；
- **事件边际**：**4.9µs/条**（`matter.damage` 口径；新模块若新增 kind，按 `gen-protocol`+`PAYLOAD_MODELS` 闭合集纪律走，成本同族）；
- **窗口化判据**：凡是"周期性"语义（生态再生、天气、情绪回落）一律 **到期桶 + 区间常量**（体例 `FIRE_SPREAD_INTERVAL_TICKS=60` / `CHAOS_EMOTION_REGRESS_INTERVAL_TICKS=60`），**禁每 tick 全量扫**。

### 2.1 生态（再生/生长节律）
| 项 | 账 |
|---|---|
| **直接（推荐形态）** | 到期桶：每 60 tick 窗处理到期项 ⇒ `N_patch × 2µs / 60`。取 `N_patch ≤ 200`（对齐 fire 的物质规模量级）⇒ **≤6.7µs/tick** |
| **直接（坏形态）** | 每 tick 全量扫 200 项 ×2µs = **400µs/tick** ⇒ 顶穿 `CHUNK_EVENT_SCAN_LIMIT_MS=0.10` **4x** ⇒ 必红（这是本模块**最可能**的回归形态，写进实现说明） |
| **事件** | 仅"过阈值"才产事件（对齐 fire 的 ignite 语义）⇒ 边际 4.9µs/条，**条数由区间常量封顶** ⇒ 不进 tick 常态 |
| **间接** | 再生 → 资源被采 → 触发下游（采集/存量计算）？**若存量查询走 SQL** ⇒ 同 P3/P5 的一次性档（`SNAPSHOT_LIMIT_MS=500` 族），**不进 tick** |
| **归属** | `CHUNK_EVENT_SCAN_LIMIT_MS=0.10` + `APPLY_P99_LIMIT_MS=0.04`；**零新行** |
| **约束** | 生态须声明 N_patch 上界（同 fire 的 F≤50 反解手法：**由区间常量反解允许规模**，勿拍数） |

### 2.2 动物（三只）
| 项 | 账 |
|---|---|
| **直接-L1** | +3 行 ⇒ 矩阵 `(53, n_actions)`，按实测斜率（50:211.75 / 49:214.40 / 40:182.15）⇒ **≈+9µs/tick**（并入 6.0 行，占 0.15%） |
| **直接-嗅觉（源）** | 源 = 全体实体 ⇒ **53/50 = +6%** ⇒ 0.116ms → **~0.123ms**（并入 `SMELL_WIRED_TICK_LIMIT_MS=1.0`，余量 8x） |
| **直接-LOS 配对** | P13 口径：**+18–31% of human50 基线**（几何：半径 16/18/20/24 ⇒ 面积 1.78/2.25/2.78/4.0×，受 `PERCEPTION_TICK_LIMIT_MS=3.6` 覆盖；P13 判定"并入 PERCEPTION 行"仍成立） |
| **间接（本模块真风险）** | 半径² 膨胀 ⇒ 若实现**新增**一条"动物专用配对"通道 ⇒ **违反 P13「零新通道」** ⇒ 双通道各自设行 = 双真相源。**判据：动物必须复用既有感知/L1/嗅觉三条面** |
| **归属** | `PERCEPTION_TICK_LIMIT_MS` + `SMELL_WIRED_TICK_LIMIT_MS` + `L1_UTILITY_TICK_LIMIT_MS`；**零新行** |
| **契约常量** | 动物数上界（3）与半径上界（24）**由机制面给**（体例 `FIRE_AGGREGATE_EVENT_N_PER_10TICK`）；**不进 thresholds** |
| ⚠ 交叉提示 | 三只 = **3 个新 entity id** ⇒ 命中我 M6-P2 记的 `rtoken ≤ N_NPC` 钉（53 > 50）⇒ **同 CR 处理**（见 `m6-mortality-perf-input.md` §2.3-1） |

### 2.3 语言阶层（识字率 → 措辞分层）
| 项 | 账 |
|---|---|
| **直接（本地）** | **≈0**：文本拼接 O(1)（对齐 `norms_text_of` 的 `"\n".join(facts)` 形态）；现有 top-5 = **119 字符** |
| **token 增量** | 按 MAX_NORMS=5 现状，识字率分层若只增"措辞档位"一段 ⇒ 上界 ≈ **+119 tok/NPC/次**（**CJK 1:1 上界口径；真实值取 0.6–1.0 系数须 LLM 侧实测**）|
| **间接（本模块真风险）** | ①**禁挂 `messages[0]`**：识字率进系统前缀 ⇒ **前缀缓存全失效** ⇒ 每次调用从"0 缓存"计费 ⇒ token 增量被放大（`norms.py` 已守此界，新模块必须沿用）；②禁把"识字率"当数值写进 prompt（`confidence 是戏外数值绝不进文本` 同族铁律，`norms.py:12`） |
| **归属** | **不进 tick 红线**（本地无算力）；token/延迟账归 **P5 措辞/LLM 档**（advisory，须 LLM 侧实测建基线）；本地只保留一条**规约**：挂 `messages[1]`、禁破 `messages[0]` |
| ⚠ 与卡给的 145–171 tok 基线的关系 | 卡给的「M4 prompt 145–171 tok 基线」**在 `docs/perf/*` 未复核到出处**（本单 `grep` 全仓 docs 无命中）⇒ 本档**不引用为实测锚**，只以本机实测的 `norms` 119 字符作为可比量级；**该基线若存在，应在定标轮由 LLM 侧补测确认**（登记不猜） |

### 2.4 迷雾（区块迷雾 v0 → 观察面接线）
| 项 | 账 |
|---|---|
| **直接** | `FogOfWar.reveal` **0.53µs/次**（含 frozenset 重建；64×64 地图 = 4×4 = **16 chunk 上限**）⇒ 全图揭满 **≤8.5µs 全程**；`is_revealed` **0.07µs/次** ⇒ 每 tick ≈ 0（**O(chunks)** 状态量，DESIGN §14 基线成立） |
| **间接（本模块真风险）** | **「迷雾揭示触发寻路缓存失效？」——v0 无此钩子**（fog 纯内存、不进事件流/存档 ⇒ 无人调 `invalidate`）。**若 M6 把 fog 接到寻路目标（"未揭示=不可达"）** ⇒ 每次揭示走 `PathCache.invalidate(chunk)` = **满表扫 103.3µs（4096 条）**；全图 16 chunk = **1.65ms** ⇒ **落在既有 `CHUNK_INVALIDATION_TICK_LIMIT_MS=2.0` 内但仅剩 0.35ms 余量**（17%）⇒ 结论：**耦合必须走 `invalidate_dirty()` 的"脏 chunk 批处理"形态**（该 API 已在 `pathfinding.py:116` 存在），**禁"揭示即全扫"** |
| **关键事实（降风险）** | `Pathfinder.find` 在仓内**只有一个调用方** = `sim/api/ws.py:569`（**玩家指令**）⇒ **寻路不在 tick 热路径** ⇒ 即便耦合，成本落在**指令面**而非每 tick ⇒ **不进 tick 行**（这是本模块最大的降险事实，建议写进实现说明） |
| **归属** | `CHUNK_INVALIDATION_TICK_LIMIT_MS=2.0`（已存在）+ 契约常量（若需按帧摊还，体例 `CASCADE_EVENT_BUDGET_PER_FRAME` / `FIRE_REPATH_BUDGET_PER_FRAME=100`）；**零新行** |

---

## 3. 红线归属总表（**零新行**验收）
| 模块 | 走的既有行（`sim/tests/bench/thresholds.py`） | 新行 |
|---|---|---|
| 生态 | `CHUNK_EVENT_SCAN_LIMIT_MS=0.10`、`APPLY_P99_LIMIT_MS=0.04`、`SNAPSHOT_LIMIT_MS=500`（存量查询族） | **0** |
| 动物 | `PERCEPTION_TICK_LIMIT_MS=3.6`、`SMELL_WIRED_TICK_LIMIT_MS=1.0`、`L1_UTILITY_TICK_LIMIT_MS=6.0` | **0** |
| 语言阶层 | 无（本地 ≈0；token 归 P5 LLM 档 advisory） | **0** |
| 迷雾 | `CHUNK_INVALIDATION_TICK_LIMIT_MS=2.0` | **0** |
| **合计** | — | **0** |
> **验收口径**：四模块施工 CR **不得**向 `thresholds.py` 追加任何新行；若实现形态要求新行（如"动物专用配对通道"），那是**实现违规**（违反 P13 零新通道），**不是预算不足**。

---

## 4. 机器门最短执行单（**换机/降频解除即跑**）
> 承接 `m6-calibration-order.md` §3（本单只补「最短路径」，不重复其全量五步）。
**前置判定（每次必做，一步不猜）**：
```bash
# 步骤 0：探针（判定门 2）。比值 <=2.0 才继续；>2.0 停止并记录（跑了不算数）
uv run python -m sim.tests.bench.throttle_probe
```
**最短三跑**（内容门 1 已由 main `3f321b4` 满足：inject/fire*/power 消费 三件齐；四模块**另属内容门 1 的下一波**——若四模块已在 main，按 §2 逐模块跑；否则本单只给"四模块落 main 后"的执行路径）：
```bash
# ① 只跑会受四模块影响的三行对应 bench（零新行 ⇒ 用例已存在）
uv run pytest -q -m "not bench" -k "perception"      # PERCEPTION 行（动物 LOS）
uv run pytest -q -m "not bench" -k "smell"           # SMELL_WIRED 行（动物源）
uv run pytest -q -m "not bench" -k "utility"         # L1_UTILITY 行（动物行数）
# ② 若四模块各自带 bench（生态/迷雾），跑其新档并核对 §2 的量级（不是红线值）：
uv run pytest -q sim/tests/bench/
# ③ 收口仍走 calibration-order §3.4 五步（实测中位 ×1.7 => 阈值；提案值 ≠ 实测值要报裁）
```
**纪律重申**：`PI_THROTTLE_SELFCHECK=0` 只用于「验证 CI 断言面」；**定标/收口一律带探针跑**（否则 soak 三测 skip 会伪装成通过）。

---

## 5. 留痕（2026-10-04，本机）
| 动作 | 结果 |
|---|---|
| `throttle_probe`（门 2） | **1.547 ≤ 2.0**（跨轮：P6-P1 1.629 / kilo 2.657 ⇒ 瞬态） |
| `grep` 既有锚点 | chaotic 9.3µs（A案 §2.1）、matter.damage ~4.9µs/条（fire §1）、感知 3.2µs/人（power §1） |
| `PathCache.invalidate` 满表实测 | **103.30µs 中位 / 177.90µs max**（4096 条） |
| 冷 A\*（64×64 全图对角） | **559.7µs 中位**（对照 P11 494–647µs ✓） |
| `FogOfWar.reveal` / `is_revealed` | **0.530µs/次** / **0.0705µs/次**（16 chunk 上界 ⇒ 全程 ≤8.5µs） |
| `norms.MAX_NORMS` + `norms_text_of` | **5**；top-5 文本 **119 字符**（≈119 tok 上界） |
| `grep -rn "145\|171" docs/perf/*.md` | **零命中** ⇒ 卡的 M4 基线本档不引用为锚（登记） |
| `sim/api/ws.py:569` | `Pathfinder.find` **唯一调用方=玩家指令** ⇒ 寻路不在 tick 路径 |
| `thresholds.py` 行盘点 | `CHUNK_EVENT_SCAN_LIMIT_MS=0.10` / `CHUNK_INVALIDATION_TICK_LIMIT_MS=2.0` / `SMELL_WIRED_TICK_LIMIT_MS=1.0` / `PERCEPTION_TICK_LIMIT_MS=3.6` / `L1_UTILITY_TICK_LIMIT_MS` ⇒ 四模块**全部有归属** |
| `--collect-only` + not-bench | 全量 **2421** = not-bench `2351 + 70`（恒等式）；M6-P4 **零代码** ⇒ not-bench **2293 passed / 120 skipped / 70 deselected / 0 failed**；与卡「main `3f321b4` = 2362/121」对账：2293+**69**=2362 ✓、120+**1**=121 ⇒ **bench 组 70 全选、无一 skip ⇒ 零改动绿闭合**（M6-P1 口径 2231/120 系旧 main `48c9944`，不可混用） |
| `ruff` / `pyright` | All checks passed / 0 errors |
