"""M5-A2 · 混沌流数据面预研（批次 A 数据侧，零代码）

DESIGN §11「时间·混沌」在**存储面**的落点预研：混沌事件登记路径、抽样预算与存储成本、
分叉克隆时的归属、以及与 F2 论断的交叉。**本稿零代码**，只给结论与落点建议；
实现单由 Claude 另行派发（派单：M5-A2【2】）。

## 0. 范围与既有事实（引用仓库现状，非推测）

| 事实 | 出处 |
| --- | --- |
| 熵注入事件 `entropy.inject`，payload `{stream: str, material: str}`（材料 hex，**必须随事件落日志**） | `sim/core/events.py::EntropyInjectPayload`（C5） |
| 注入审计表 `entropy_log(id, branch_id, stream, reason, tick, value, event_seq, created_at)` | `sim/core/persistence/models.py::EntropyLog` |
| `EntropyMixer.inject(reason, tick, value, event)` 写事件 + 写 `entropy_log`，`event_seq` 指向该事件 | `sim/core/entropy.py` |
| 确定性混沌流 `chaotic(stream)`：**纯函数**，由流状态（材料 + PCG64 进度）算出 | `sim/core/entropy.py` |
| 流状态落库载体 = `branches.rng_state`（0009），fork 事务内原子落库 | `0010` 之前的 `0009_branches_rng_state`、M5-A-DATA |
| 分叉语义：事件**不克隆**、投影随克隆；R2 = 父分支前缀折叠 ∘ 子分支事件折叠 | M5-D3-b / M5-D3-c |
| 摊还封顶先例：坍塌 `CASCADE_EVENT_BUDGET_PER_FRAME = 100`（按帧封顶，与规模解耦） | `sim/world/support_graph.py`、M4-P1 |
| 快进摊还模型：1 游戏日 86,400 tick；60× 档 0.277ms/tick、300× 档 0.0556ms/tick；降级只改节拍不改折叠规则 | `docs/perf/m5-time-scale-fork-budget.md` §1/§2（pi） |
| 实测事件密度 e ≈ 20 事件/tick（@50 NPC） | pi M5-P4 基准 |

## 1. (a) EventKind 白名单登记路径：混沌走**既有** kind，抽样不落事件

| 混沌成分 | 登记路径 | 结论 |
| --- | --- | --- |
| 熵注入（DESIGN §11 注入点：NPC 重大决策 / 致命一击 / 偶遇 / 每日天气 / 玩家行为意外后果） | 既有 **`entropy.inject`**（`{stream, material}`） | **不加新 kind** |
| 确定性抽样（`chaotic()` 出值） | **不落事件**——纯函数，续接靠 `branches.rng_state` | 无需 kind |
| 时间刻度（倍速） | **不落事件**——见 §1.2 红线 | 无需 kind |
| 注入被拒 / 预算耗尽 / 抽签号（若将来要审计） | 需**新 kind**（裁 7/8 冻结基线 ⇒ 须追加白名单） | 建议名 `chaos.draw`，payload 纯审计（`stream/reason/tick/value/draw_no`），**不带语料** |

**建议：先不加 `chaos.draw`。** 理由：抽样可由 `(rng_state, reason, tick)` 从父前缀事件
完全复现（见 §3），落事件只增体积不增信息；真出现「注入被拒」这类**不可复现**的
外部输入时再申请白名单，代价只有一次裁 28 级追加。

### 1.1 为什么「抽样不落事件」是数据面的正解
R2 要求「同一事件前缀 ⇒ 同一世界态」。抽样若落事件，则子分支重建时既要父前缀又要子
事件两处采样（同 tick 同 stream 抽两次），反而制造 R2 对账歧义；不落事件则「抽签」是
状态的**纯函数**，R2 对账只需对 `rng_state`（一行）✔ 与 memories 那类「无事件源的
原地演进列」问题正好相反（见 §4）。

### 1.2 时间刻度不落事件的前提（红线）
倍速只改 **tick 推进节奏**，不改「一个 tick 推进哪些效应」⇒ 世界态是 **tick 的函数**、
与墙钟无关 ⇒ 无需事件。**红线：不得引入任何按墙钟/真实时间衰减的效应**（如「按现实
时间掉血」）；一旦引入，必须新增 `timescale.set` 类事件并把时间源纳入状态包，否则
T2 replay 立刻失配。此红线归实现单（driver/世界侧），本单不动手。

## 2. (b) 抽样预算与存储成本：事件量级 O(百/游戏日)，**零新增预算行**

**抽样次数 ≠ 事件数**：每次**注入** = 1 条 `entropy.inject` + 1 行 `entropy_log`；
注入点由事件驱动（见 §0），**不是 per-tick**。

量级估算（50 NPC × 40–60 决策/游戏日 = 2–3k 决策/日，注入率取 1–5%）：

| 口径 | 数值 | 对照 |
| --- | --- | --- |
| 混沌事件 | **20–150 条/游戏日**（+ 天气 1/日） | pi 实测 e ≈ 20 事件/tick ⇒ 混沌占 **<0.01%**，噪声级 |
| 事件密度 | 0.0002–0.002 条/tick | 坍塌先例：**≤100 条/帧**（按帧封顶）⇒ 混沌连摊还都不需要 |
| 存储 | ≈150 ×（事件 ~300B + `entropy_log` ~120B）≈ **60KB/游戏日** | 100 游戏日 ≈ 6MB/世界，可忽略 |
| 若 per-tick 化（**当前设计不采**） | 86,400 × ~420B ≈ **36MB/日** ⇒ 3.6GB/百日 | **必须封顶**：沿用 M4-P1 摊还口径（按帧/按 tick 预算抽签，不逐 tick 落事件） |

**真正成本在抽签热路径，不在存储**：每次注入一次 `chaotic()`（numpy 调用）⇒ 口径看
pi 的 rng bench；本预研不新增预算行、不新增表。

## 3. (c) 与 0008/0009 的交互：派单假设**成立**，附两点修正

派单假设：「D3-b 语义下混沌事件天然继承父分支封存语义」。**核验结果：成立**，
理由与两点补充：

1. **归属正确、无悬空**：事件不克隆 ⇒ 子分支事件日志不含父分支 `entropy.inject`；
   `entropy_log` 不在 6 张克隆表内 ⇒ 子分支从空开始。子分支的新注入写自己的行、
   自己的 `event_seq`（**分支内**引用）⇒ `Event.entropy_ref` ↔ `entropy_log.event_seq`
   双向引用都锚在本分支，**克隆不产生悬空引用**。
2. **连续性靠 0009 而非事件**：流的材料与 PCG64 进度随 fork 事务原子落库
   （`branches.rng_state`）⇒ 子分支从同一材料、同一进度继续抽，**逐位一致**
   （已由 `sim/tests/test_m5_branches_rng_state.py` 的「端到端接缝抽签逐位一致」钉验证）。
3. **R2 重建不依赖克隆事件**：熵流材料从**父分支前缀事件**里的 `entropy.inject` 恢复
   （R2 = 父前缀折叠 ∘ 子事件折叠，父前缀本来就直读父分支事件日志）⇒ 无需把父事件
   复制进子分支。✔ 封存语义自洽。

**修正 1（权重提示）**：`restore_rng_state(None)` 回落 `Branch.seed` 派生 ⇒ 漏传
`rng_state` 时接缝跳变（M5-A-DATA 已埋 warning + `rng_state_persisted` 翻转）。在混沌
面上，接缝跳变表现为「同一世界分叉后混沌流变了」= **玩家可感知的世界线分岔**，权重
高于普通数值。**建议（域外，不在本单动手）**：混沌接线后把
`rng_state_persisted=False` 从 warning 升级为硬错误。

**修正 2（历史点分叉的混沌缺口）**：若将来支持历史 anchor 分叉，父分支在 anchor 时刻
的 `rng_state` 不可得（只有 fork 时刻快照）⇒ **混沌流无法历史重建**。⇒
`m5-fork-archive-preplan.md` §3.7 推荐的 (c) anchor 世界态物化**必须把 `rng_state`
一起纳入 anchor 世界态包**，否则历史回退会重掷混沌（同一存档回退后世界线不同）。
这是对主树 §3.7 结论的一处**数据面补充**。

## 4. (d) 与 F2 论断交叉：混沌**不新增** F2 缺口，反倒是正面样板

F2 缺口 = 「有事件源、却不可重建的语料/投影表」（典型：relationships 的累计值原地演进）。
混沌是仓库里**唯一「状态 + 事件 + 查询面」三件齐备**的随机性设施：

| 面 | 载体 | 事件源 | 可重建性 |
| --- | --- | --- | --- |
| 流状态 | `branches.rng_state`（per-branch 列，**非投影表**） | `entropy.inject`（父前缀） | 0009 快照 ∪ 父前缀事件 ✔ |
| 审计 | `entropy_log` | `event_seq` → `entropy.inject` | 已有表，**即混沌查询面**（branch/stream/reason/tick/value） |
| 事件 | `events`（`entropy.inject`） | 自身 | ✔ |

⇒ **不需要新表**（`entropy_log` 已是查询面），**不新增 F2 缺口**；混沌可作 F2 修复的
正面样板（同随机性维度、状态与事件同源可对账）。

## 5. 落点建议（供后续单裁）

1. **接线时**：`chaotic()` 调用点必须紧邻 `inject()`，且分叉前保证 `rng_state` 快照
   新鲜（0009 路径已在 fork 事务内落库，实现单只需保证调用前捕获）。
2. **时间刻度**：不落事件，守 §1.2 红线（无按墙钟效应）。
3. **预算**：存储面零新增预算行；若将来要 per-tick 化，先出摊还预算设计（collapse 先例）。
4. **补钉（实现单）**：`inject()` 后 `entropy_log.event_seq` 指向**本分支同 seq** 的
   `entropy.inject`（跨分支不查）——本单未加，属实现单的域。
