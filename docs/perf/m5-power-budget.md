# M5-P10：批次 C 权力牙齿·性能预算案（权力状态更新成本 + 决策层间接传导推演 + 红线建议）
> 性能域（pi），2026-10-02。任务：M5-P10（**提案制零代码**——不碰 `sim/`、不碰 `thresholds.py`，红线只是提案，待裁后施工）。
> 承接：`docs/arch/m5-plan.md` 批次 C（权力牙齿＝§13 加内容六 / §18 可砍序 5；机制本体「本骨架不发明」，随时间累积/衰减＝批次 A 依赖）；
> 裁 26-169（**D-10 权力完全不可见**：纯 Agent 内部，协议面零改动）；`docs/security/m5-authority-criteria-preplan.md`（codex 判据：A 协议零新增/B 出站递归禁键/C 行为差异只在叙事面）；
> `docs/api/m5-batch-c-prestudy-authority.md`（kilo K4：perception/monologue/plan 三面现成，D-11~D-13 随之闭合）；
> 前单 `docs/perf/m5-batch-a-chaos-budget.md`（P9 教训：**间接成本比直接成本大一个量级**——抽样 9.3µs vs 冷 A* 494–647µs＝~53–70x）。
> 实测环境：本机 Win11，Python 3.12，2026-10-02，多轮取中位（与既有 bench 同源口径，warm median）。**这是 kilo/opencode 本轮并行施工的接法约束输入。**

## 0. 结论速览
| # | 问题 | 结论 |
|---|---|---|
| 1 | 权力状态更新本身的每 tick 成本？ | **可忽略**——向量化「衰减+增益+夹紧」50 NPC **2.8µs/tick**，对比 L1 满属性向量化决策全推 `tick_vectorized(50)` **18.1µs** ⇒ ≈**+15% 决策行增量**（它本质上就是效用矩阵多一列）。§1 |
| 2 | 陷阱在哪（对照 P8/P9 教训）？ | ①**逐 NPC `dataclasses.replace` 50 人 = 81µs、逐 NPC `chaotic_at` 抖动 = 521µs**（后者正是 P9 纯函数重建 31x 陷阱的翻版）；②**聚合口径用中位不用均值**（P8：willingness 中位 0.21ms、均值被 9.6ms 离群拖到 0.47ms）。§1 |
| 3 | 间接传导（本单核心）？ | 权力 → 改 utility 权重 → **改动作选择分布**（实测：+10/50 NPC 由 eat 翻到 request_chat，flip_rate 随偏置幅度 0.1→0.46、动作熵 2.52→1.80）→ **改哪些冷子系统被触发**（不是改事件数）。权力的等效「冷路径」＝**寻路冷 A*（0.53ms@64×64）＋检索触发（0.05–0.30ms）＋每事件 apply/fold（~20µs + 0.74µs）**。§2 |
| 4 | P=5/P=50 档位推演？ | **P=5**（少数掌权者翻进冷路径）：混合 3 move+2 chat ≈ **1.7ms/tick**，全 move 上界 2.64ms。 **P=50**（全体翻 move）：**26.4ms/tick → 破整 tick 预算 16.6ms**；全体翻 chat 走全量扫描哨兵 → M3 存照 43.1ms/tick。**权力不得把整体动作分布推向冷路径**——这是 P9「接法红线」的同一课。§2.4 |
| 5 | 红线：进 thresholds vs 并入既有行？ | ①**直接成本并入 L1_UTILITY 决策行**（`L1_UTILITY_TICK_LIMIT_MS=6.0`），**不新建 `POWER_TICK_LIMIT_MS`**（一句裁定，理由见 §3.1：避免与决策行双算，同 M4-P1 坍塌不新增行先例）；②权力若用 `chaotic()` 抖动 → 走 RNG/熵行（P9 已占 `CHAOS_TICK_LIMIT_MS=0.05`）；③**间接成本不设独立 tick 红线**，改设**偏置幅度契约上限 + flip 守卫**，由寻路/检索既有行自然吸收。§3 |
| 6 | 契约常量复用？ | 权力＝慢变量（§13/§18「随时间累积/衰减」）→ 沿用 P9 `CHAOS_EMOTION_REGRESS_INTERVAL_TICKS=60` 同族 → **`POWER_REGRESS_INTERVAL_TICKS=60`**（区间推进，禁每 tick 每 NPC）。§3.3 |
| 7 | P6 纪律 | 一切数值红线**未定标前 advisory**；绝对阈值降频机必假红（先 `throttle_probe` 后定标）。§3.4 |

---

## 1. 直接账：权力状态更新的每 tick 成本模型

成本 = **更新频率 × 单次成本**。权力被 DESIGN/批次 A 定义为**慢变量**（随时间累积/衰减），不是 per-tick 高频量——这决定了它应走「区间推进」而非每 tick。

### 1.1 单次成本（四形态，实测本机暖态中位）
| 形态 | 50 NPC/tick | 说明 |
|---|---|---|
| **向量化**（`multiply`+`add`+`clip`，= 效用矩阵多一列） | **2.8µs** | ✅ 推荐。L1 满属性向量化全推 `tick_vectorized(50)` 实测 **18.1µs**，权力多一列≈**+15% 决策行增量** |
| **逐 NPC Python 更新**（既有 `advance_needs` 风格，50 次调用） | **175µs**（3.2µs/人） | ⚠ 这就是**现状 needs 推进的写法**——权力若照抄此形即同量级；比向量化 **63x** |
| **逐 NPC `dataclasses.replace`**（冻结实体每 tick 重建） | **81µs** | ⚠ 反模式（H-2 逐对象热循环）；比向量化 **29x** |
| **逐 NPC `chaotic_at` 抖动**（纯函数重建 Generator 抽权力噪声） | **521µs** | ⚠ **P9 陷阱翻版**：单 draw 9.5µs × 50＝重建代价 31x，一次就顶穿 RNG/熵行余量（P9 `CHAOS_TICK_LIMIT_MS=0.05`）的 10 倍 |

**直接账结论**：权力更新本体是噪声级（≤2.8µs），**但会变成 81µs / 175µs / 521µs，完全取决于接法**——这正是 P9 的结构性教训（同一个 50 人每 tick 更新，接法差 **186x**）。

### 1.2 频率模型（对照契约常量族）
- 权力累积/衰减是**低频**：`POWER_REGRESS_INTERVAL_TICKS=60`（复用 P9 情绪回落同族常量，§3.3）。
- 摊到每 tick：`2.8µs / 60 ≈ 0.047µs/tick`（向量化）——纯噪声，**不进任何红线**。
- 真随机注入（权力走 `EntropyMixer`？）：与 P9 inject 同口径（mix 6.6µs × ≤150 次/游戏日 ⇒ ≤0.011µs/tick），已证可忽略。

### 1.3 聚合口径（P8 纪律直接适用）
测「权力更新的每 tick 成本」时**取中位、不取均值**：单 tick 的 GC/上下文切换离群（P8 实测 max ~9.6ms）会把均值拖离真值。护栏若将来上 CI，按 `statistics.median` 判（同 willingness Δ 护栏 M5-P8 订正）。

---

## 2. 间接账（本单核心）：权力进决策层的传导链

> **传导链**：权力值 → 改 utility 打分权重 → **改动作选择分布** → 改「哪些冷子系统被触发 / 事件构成」 → 传导到 检索 / 折叠 / 存储 / 感知。
> **关键**：`runtime.tick` 每活跃 NPC 恒产 **1 条 NPC_ACT**（实测 50 人 tick=691µs、events=50）——**权力不改事件条数，改的是每条事件下游触发什么**。这与 P9「抽样本身轻、触发重算才是大头」完全同构。

### 2.1 放大器实测：动作分布随权力偏置漂移
在打分矩阵上加一列 `power[:,None] × action_bias`（唯一合理的向量化接缝）。
**灵敏度曲线用合成 score 面**（`rng.random((50,6))×0.3` + 随机 per-action bias）以隔离「偏置幅度→漂移」关系，不掺真实增益矩阵的量纲：

| 偏置幅度 amp | flip_rate（动作被改判的 NPC 占比） | 动作熵（分布集中度，↓＝坍缩） |
|---|---|---|
| 0（基线） | — | 2.52 |
| 0.1 | 0.18 | 2.48 |
| 0.2 | 0.24 | 2.41 |
| 0.5 | 0.38 | 2.13 |
| 1.0 | **0.46** | **1.80**（6 动作坍到 5） |

- **真实精简形**（3 needs/6 actions、真 `_GAIN`、`action_bias=[0,.25,0,0,-.2,.4]`）实测：
  **request_chat 16→26（+10/50 NPC 翻判）、eat 34→24**——即真实模型上中等偏置就能改判 20% 的 NPC。
- 直连决策成本**几乎免费**：打分矩阵路径（`(needs×weights) @ _GAIN`）基线 **211.7µs**，加权力广播列 `+ power[:,None]×action_bias` 后 **214.8µs** ⇒ **仅 +3.05µs/50 人（+1.4%）**；
  含 `UtilityDecision` 组装的真实 `evaluate_batch(50)` 为 **270µs**。**成本不在这一步，在它触发的下一步。**

### 2.2 权力的等效「冷路径」（对照 P9 的 A* 教训）
动作分布一旦翻向某类，就点亮对应冷子系统，单价：

| 翻向的动作 | 点亮的冷子系统 | 单次成本（实测/M3-M5-P9 存照） |
|---|---|---|
| `move`（走路） | **冷 A* 寻路**（新目的地＝缓存 miss） | **0.53ms**@64×64（`Pathfinder.find` 新目标；P9 账一-b 同源） |
| `request_chat`（对话） | **检索链**（决策/prompt 驱动，M3） | 常态 **0.05ms**/NPC；退化全量扫描 **0.30–2.0ms**/NPC（`RETRIEVAL_*` 行） |
| 任意动作事件 | `apply` + `fold` + 落库 | apply ~0.02ms 名义（`APPLY_P99=0.04`）+ fold `0.74µs`/事件 |

> **这就是权力的「账一-b」**：权力列**自付 3.05µs**（§2.1），却能让一个 NPC 从 `eat`（零下游）翻到 `move`（+0.53ms）或 `chat`（+0.05–0.30ms）——
> **间接成本比直接成本高近两个数量级（3µs 触发 530µs ≈ 174x）**，比 P9 抽样 vs 冷 A* 的 ~53–70x 还极端（因为权力的直接成本几乎为零）。

### 2.3 传导的存储/折叠尾账
动作分布漂移 → 事件构成变化 → 事件条数**不变**（恒 50/tick）但**类型**变（move 事件带 x/y 坐标→触发 chunk 失效→寻路缓存失效churn；chat 触发 prompt 装配）。折叠/存储侧增量 = `Δ事件类型 × fold 单价`，沿 M5-P1（fold 0.74µs/事件）与 P9（存储噪声级）口径，**不构成新风险**，除非整体事件密度被推高（权力不推密度，只推类型——已由 `runtime.tick` 恒定 1 事件/NPC 保证）。

### 2.4 P=5 / P=50 档位推演
P ＝ 每 tick 被权力改判、且翻进冷路径的 NPC 数（少数掌权者 vs 全体动员）：

| 档位 | 全翻 `move`（冷 A* 0.53ms/次） | 全翻 `chat`（检索常态 0.05 / 红线退化 0.30 / 全量扫描哨兵 0.86，单位 ms·NPC⁻¹） | 现实混合（3 move + 2 chat） |
|---|---|---|---|
| **P=5**（精英少数） | **2.64ms** | 0.25 / 1.5 / **4.3ms** | **~1.7ms/tick** |
| **P=50**（全体） | **26.4ms → 破 16.6ms 整 tick 预算** | 2.5 / 15 / **43.1ms**（M3 存照「每 tick 全量 50 NPC」= 破线 2.6x） | 线性放大 10x，move 主导必破线 |

**红线推论**：P=5 混合档可被 L1_UTILITY 行（6.0ms）吸收；但**权力偏置绝不允许把分布整体推向 `move`/冷路径**（P=50 全 move＝结构性爆预算，等价 P9 的账一-b 反模式）。**约束点在偏置幅度（flip 率），不在更新耗时本身。**

---

## 3. 红线建议

### 3.0 最紧要红线（接法，非数字阈值）
- **权力只作 utility 矩阵的额外列**（向量化 `scores += power[:,None] * action_bias`），**不得**逐 NPC `dataclasses.replace`（81µs）或逐 NPC `chaotic_at`（521µs）把慢变量做成热循环——这是 P9 §3.0 的同一课。
- **偏置幅度设上限**：`power` 对 `action_bias` 的乘子须有界（如 `|power_bias_effect| ≤ 0.2`），使 flip_rate 停在 ~0.24/熵 ≥2.4（分布不坍缩），既守住性能也守住 §4 的「叙事多样/不操纵感」。
- **不可见即不可测进戏内**（D-10）：权力值不进任何出站面/感知/prompt（codex 红线 B），本预算只测内核侧。

### 3.1 一句裁定：直接成本**并入决策行**，不新建 `POWER_TICK_LIMIT_MS`
- **裁定建议**：权力更新的每 tick 成本**并入 `L1_UTILITY_TICK_LIMIT_MS=6.0`（决策行）**，与 P9 把抽签并入 RNG/熵行**同理**——**不另起炉灶**。理由：①权力列就是效用矩阵的一列，属同一操作类；②新建 `POWER_TICK_LIMIT_MS` 会与决策行**双算**（同 M4-P1 §4.2 坍塌「并入既有红线、不加新行」先例，thresholds 注释已记「避免与 L1 行叠加双算」）；③真风险在间接（§2），数字阈值卡不住接法。
- **例外**：若权力的**抖动**用 `chaotic()` 实现 → 那笔走 **RNG/熵行**（P9 已占 `CHAOS_TICK_LIMIT_MS=0.05`，50 NPC 每 tick 抖＝521µs 直接顶穿），**不重复计入决策行**。

### 3.2 间接成本不设独立 tick 红线（用守卫拦）
- 冷路径成本（寻路/检索）**已由既有行覆盖**：`RETRIEVAL_TICK_LIMIT_MS=12.0`、chunk 失效行、`L1_UTILITY` 行。再设 `POWER_INDIRECT_LIMIT_MS` 只会双算且测不准（取决于内容偏置，非稳定量）。
- **改设两条可证伪守卫**（供施工单/CI）：①**flip 守卫**——权力接入前后，50 NPC 动作分布 flip_rate ≤ 阈值（建议 ≤0.25，留 §2.1 数据支撑），破限＝偏置过强；②**冷路径计数守卫**——权力触发的新增 `move`/`chat` 事件/tick ≤ 预算（对齐 P9「理想 P≤5/tick」）。

### 3.3 契约常量复用（非红线，随施工对齐）
```
# 权力＝慢变量（§13/§18 随时间累积/衰减）→ 复用 P9 CHAOS_EMOTION_REGRESS_INTERVAL_TICKS 同族
POWER_REGRESS_INTERVAL_TICKS   = 60    # 权力推进区间（慢变量，禁每 tick 每 NPC）
POWER_MAX_BIAS                 = 0.2   # 权力对 utility 的最大乘子（守 flip≤0.25 + §4 叙事多样）
```
- 与 `_PERCEPTION_EVERY_N_TICKS` / `FAST_FORWARD_TICKS_PER_FRAME` / `CHAOS_EMOTION_REGRESS_INTERVAL_TICKS` 同族（代码契约常量，非 bench 红线）。

### 3.4 P6 纪律（承 P8/P9）
`POWER_MAX_BIAS` / 各计数阈值为**提案值**，**不进 thresholds.py**（本单零代码）。**未定标前一律 advisory**；绝对阈值降频机必假红，落地前在定标机（`throttle_probe` 比值 ~1.0）暖态中位实测再收口。

---

## 4. 守卫点 / 语义约束（防「达标但语义错」）
- **T2 回放逐位一致（C5）**：权力值须由 `(world_seed, 事件流, tick)` 确定性派生，禁 `import random`、禁墙钟；抖动（若有）走 `chaotic_at(stream, rng, tick)`（同刻恒同值）。
- **D-10 不可见（codex 红线 A/B）**：权力不进 WS 帧/openapi/事件 kind/prompt 递归体——`sim/tests/test_m5_authority_surface.py` 8 钉锁现状，机制施工任何新面即红。预算侧不测这些面，只在 §3.0 重申。
- **出戏最高风险（m5-plan 批次 C 行 + §10）**：权力带来的差异**只能是叙事面**（monologue/perception/plan），抱怨须**自我怀疑**不得**被操纵感**（codex 红线 C，`manipulation` 码零豁免）。**性能侧的对应约束**：`POWER_MAX_BIAS` 设上限既为守性能（flip≤0.25），也为**防动作分布坍缩**（§2.1 熵 2.52→1.80）——分布坍缩＝「所有人被权力操纵成同一种行为」＝出戏风险的机器可测前兆。这是一举两得点，值得 codex/cline 交叉。
- **§16 补充断言**：权力（同 luck）不出现在感知帧字段。

## 5. 待裁 / 交叉
1. **机制形态待 Claude**：权力值定义（位阶/威信/支配度）、进 utility 的具体列/系数、是否含 `chaotic()` 抖动——本单只给「任何接法的成本边界」。
2. **`POWER_MAX_BIAS` 与 flip 阈值**待施工对齐（数值为提案）。
3. **红线落点**待裁：决策行并入（建议）vs 新行（不建议，双算）。
4. **交叉 codex**：`POWER_MAX_BIAS`/分布坍缩守卫 ↔ 「被操纵感」安规判据（§4）可共用一条 flip/熵断言。
5. **交叉 opencode**：权力落库/重放若新增列，沿用 P9 结论——确定性派生不落事件、材料键控缓存、抽样子不落 kind。
6. **对 P9 RNG/熵行的协调**：权力抖动走 chaotic → 计入 P9 的 `CHAOS_TICK_LIMIT_MS`，与抽签余量共享同一 0.05ms 额度，**不叠加**。

## 6. 零改动留痕（2026-10-02，本机）
本单**只新增本文档**，`sim/`、`thresholds.py`、既有 bench 文件零改动（`git status` 仅一个 `?? docs/perf/m5-power-budget.md`；`git diff --stat e17944a..HEAD -- sim/tests/` 仅一个**非 bench**新文件，无阈值/接线改动）。

| 命令 | 结果 |
|---|---|
| `uv run pytest -q -m "not bench"` | **1950 passed / 125 skipped / 70 deselected**，4 warnings，122.1s |
| `uv run pytest -q -m bench` | **68 passed / 2 skipped**（268.3s）——两个 skip 均为环境门：7 日完整 soak（`PI_M2_FULL_SOAK` 默认关）+ **soak 自检因本机跑时降频探针比值 2.055>2.0 自行 skip**（P6 降频门正常生效，非回归；上一基线为 69 passed/1 skipped） |
| `uv run ruff check .` | All checks passed |
| `uv run pyright .` | 0 errors |

**实测探针（临时脚本，已删）**：权力向量化更新 x50 **2.8µs** / `dataclasses.replace` x50 **81µs** / `chaotic_at` x50 **521µs**（单 9.5µs） / `advance_needs` 单 NPC 3.2µs、**50 NPC 逐人循环 175µs（现状是逐对象 Python 写法）** / L1 满属性向量化 `tick_vectorized(50)` **18.1µs** / 打分矩阵路径 base **211.7µs**→加权力列 **214.8µs**（+3.05µs）；含决策组装的 `evaluate_batch(50)` **270µs** / 动作 flip_rate 0.18–0.46（偏置 0.1–1.0）、动作熵 2.52→1.80 / 真实精简形 request_chat 16→26 / `runtime.tick(50)` 691µs、events=50/tick / 冷 A* 64×64 新目标 **0.53ms**（corner-corner 0.65ms） / apply 名义 0.02ms·fold 0.74µs（M5-P1 存照） / 检索常态 0.05·退化 0.30–2.0ms/NPC（M3 存照）。
