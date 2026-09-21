# L1 效用算法规格（docs/perf/l1-spec.md）

> M2-P3 第 1 项：把 `sim/tests/bench/test_bench_l1_utility.py` 原型的算法规格落盘，
> 与 M2-A2 第二批落地（main `59ffd86`）的真实实现**逐项对账**，并回填红线实测。
> 依据：`DESIGN.md` §5（NPC）/ §13（LOD、NPC 完整属性）、`docs/arch/m2-npc-cognition.md` §2、
> `docs/perf/budget.md` §2.4（L1 预算）、`sim/tests/bench/thresholds.py`（红线唯一真相源）。
> 边界：本文只描述**算法与量纲**，不改 `sim/npc/` 代码（架构域）。

---

## 0. 口径与三份「规格」的关系

性能域手里有**三份 L1 规格**，必须分清，否则会拿错数当红线：

| # | 名称 | 是什么 | 用途 |
|---|---|---|---|
| S1 | **原型规格**（`test_bench_l1_utility._L1Load`） | M2-P1 按 DESIGN §13「NPC 完整属性」造的**代表性满属性载荷**，纯 numpy 同构数组 | 定预算**上界**（红线 6.0ms） |
| S2 | **实现规格**（`sim/npc/utility.py`） | M2-A2 第二批落地的真实 M2 实现，**精简形** | 复测回填实测值 |
| S3 | **验收口径**（`docs/perf/m2-acceptance.md`） | 长跑分层断言 | 7 日自转无崩溃 |

**红线归属 S1**：6.0ms/单 NPC 0.12ms 是「M2 满属性 + 未向量化写法」的**回归天花板**，
不是「当前实现的期望值」。实现比原型简单 ⇒ 实测远低于红线 ⇒ **红线不放宽**（放窄 = 自缩防线，
下次真加 PAD/关系/记忆项时会被自己挡）。本文 §4 给出「若补齐 S2 缺失项」的推算。

---

## 1. 规格 S1：原型（预算上界）

### 1.1 numpy 数据布局

| 数组 | 形状 | dtype | 语义 |
|---|---|---|---|
| `needs` | `(50, 6)` | float32 | 需求值（6 项带权重，DESIGN §13） |
| `weights` | `(50, 6)` | float32 | 需求权重（效用加权用） |
| `ocean` | `(50, 5)` | float32 | OCEAN 0-100 |
| `pad` | `(50, 3)` | float32 | PAD −1..1 |
| `rel` | `(50, 50)` | float32 | 关系矩阵（有向、不对称：我对他 ≠ 他对我） |
| `mem_salience` | `(50, 32)` | float32 | 记忆显著性窗口 |
| `mem_emotion` | `(50, 32)` | float32 | 记忆情绪强度（与显著性逐元素相乘） |
| `u_needs` | `(13, 6)` | float32 | 动作×需求 效用系数 |
| `u_ocean` | `(13, 5)` | float32 | 动作×OCEAN 效用系数 |
| `u_pad` | `(13, 3)` | float32 | 动作×PAD 效用系数 |

常量：`N_NPC=50`、`N_NEEDS=6`、`N_OCEAN=5`、`N_PAD=3`、`N_REL=50`、`N_MEM=32`、
`N_ACTIONS=13`（= `sim/agent/intent.py` 的 IntentAction 种类数）、`SEED=7`（C5：禁 stdlib random）。

### 1.2 打分公式（每 tick）

```
# 1) 需求衰减（紧迫度上升方向用 clip 保 [0,1]）
needs = clip(needs - 1e-4, 0, 1)

# 2) 三项矩阵乘积 + 两项聚合标量
scores  = needs @ u_needs.T          # (50,6)@(6,13) -> (50,13)
scores += ocean @ u_ocean.T          # (50,5)@(5,13)
scores += pad   @ u_pad.T            # (50,3)@(3,13)
scores += rel.mean(axis=1, keepdims=True)              # 关系均值标量广播
scores += 0.1 * (mem_salience * mem_emotion).sum(1)    # 记忆项

# 3) argmax 决策 + 记忆衰减（每 tick 乘一次）
best = scores.argmax(axis=1)
mem_salience *= 0.999
```

**矩阵法要点**（budget §2.4「同构数据向量化」= H-2 下限）：三个 `(n,k)@(k,a)` 一次算完，
禁逐 NPC Python 循环。`tick_scalar` 是 H-2 同款反模式哨兵（只证明向量化必要，不卡预算）。

### 1.3 断线兜底（同一份预算）

LLM 断线时 L2 位 NPC 降级执行**计划队列**（LLM 上次规划的行动序列）：每股 `pop(0)` 一步 +
常数校验，`L1_OFFLINE_FALLBACK_LIMIT_MS = 0.20ms`。该路径断线期每 tick 都跑。

---

## 2. 规格 S2：真实实现（main `59ffd86`）

### 2.1 常量与列序（确定性契约）

```python
NEED_ORDER   = ("hunger", "energy", "social")            # n_needs = 3
ACTION_ORDER = ("move", "work", "eat", "rest", "wander", "request_chat")  # n_actions = 6
N_ACTIONS    = 6
```

`ACTION_ORDER` 由 `ACTION_WHITELIST` 过滤生成，**固定序**（不随 set 迭代序漂移，C5）；
列序同时决定 `_GAIN` 的列与 `UtilityModel.action_index`。

### 2.2 增益矩阵 `_GAIN`（行 = NEED_ORDER，列 = ACTION_ORDER）

| 需求 \ 动作 | move | work | eat | rest | wander | request_chat |
|---|---|---|---|---|---|---|
| **hunger** | 0.0 | 0.0 | **0.9** | 0.1 | 0.0 | 0.0 |
| **energy** | 0.0 | 0.0 | 0.1 | **0.9** | 0.2 | 0.0 |
| **social** | 0.0 | 0.2 | 0.0 | 0.0 | 0.3 | **0.8** |

dtype `float32`，形状 `(3, 6)`。内容常量·占位值（eat 治饥饿 / rest 恢复精力 / chat 补社交）。

### 2.3 打分公式（每 tick）

```
# 1) needs 元组 -> (n,3) 矩阵（missing 项权重默认 1、值默认 0）
needs    = model._needs_matrix(profiles)      # (n,3) value 列
weights  = model._weights_matrix(profiles)    # (n,3) weight 列
urgency  = needs * weights                    # (n,3) 元素积

# 2) 矩阵法主项
scores   = urgency @ _GAIN                    # (n,3)@(3,6) -> (n,n_actions)

# 3) 外向偏置（OCEAN 第 3 维 /100 ∈[0,1]）只加到 request_chat 列
scores[:, chat_col] += 0.3 * ocean[:, 2] / 100.0

# 4) 习惯加成（M4 前均匀常数列，避免全零打分并列）
scores += 0.05

# 5) argmax
best = scores.argmax(axis=1)
```

常量：`HABIT_BONUS = 0.05`（六偏差之一占位，M4 意愿系统接管）、
`_EXTRAVERSION_CHAT_BIAS = 0.3`。

### 2.4 需求推进与候选集

- `needs.advance_needs(needs, DEFAULT_DECAYS, ticks=1)`：`DEFAULT_DECAYS` =
  hunger `1/86400`（一天饿满）/ energy `1/57600`（16h 耗尽）/ social `1/172800`（2 天）；
  阈值 0.7/0.7/0.8 → 补救动作 eat/rest/request_chat。`Need.advanced` clip 到 `[0,1]`。
- `schedule.current_slot(tick)`：昼夜相位 → 缺省动作档（DAWN/DUSK→wander、DAY→work、NIGHT→rest），
  由 `sim/core/calendar.py` 的 `phase_of_day` 派生（纯函数可重放）。
- **候选集**：架构稿 §2 定义为「日程档 + needs 阈值补救 + 计划队列剩余」，由 runtime 注入；
  **当前 `NpcRuntime.tick` 只跑全动作打分**（候选集未进 utility 入参）——见 §5 未落地项。

### 2.5 `NpcRuntime.tick(tick)` 职责链（固定序，C5）

```
1. needs 推进：profiles -> replace(p, needs=advance_needs(p.needs))   # frozen，不原地改
2. L0 过滤：lod == 0 不参与决策（统计档，不建对象语义）        # NPC_LOD_CHANGE 事件驱动
3. 效用：evaluate_batch(active_profiles, utility) -> UtilityDecision[]
4. 事件产出：npc_act_event(tick, npc_id, action, target, params)
             params 只带 ACTION_PAYLOAD_KEYS[action] 白名单键（当前 scores 键与
             白名单键不相交 ⇒ params 恒空，见 §5）
```

`NpcRuntime.__post_init__` 把 `profiles` 键排序固化（`_order`），并对 `utility.n_npc`
做一致性校验；`tick` 末尾 `self.profiles = advanced`（自身状态推进，不进 WorldState）。

---

## 3. 对账表：S1 原型 ↔ S2 实现

| 维度 | S1 原型 | S2 实现 | 差异影响 |
|---|---|---|---|
| needs 维数 | 6 | **3**（hunger/energy/social） | 主项乘积 `(n,3)@(3,6)` 比原型小 4× |
| actions 维数 | 13 | **6** | 输出列少一半以上 |
| 主项 | 3 个矩阵积（needs/ocean/pad） | **1 个**矩阵积（needs×weights → _GAIN） | 原型是「身份全属性」最坏载荷 |
| 需求权重 | 单独 `weights` 数组参与 | 与 value **元素积**成 urgency 后进主项 | 等价的信息量，少一次矩阵乘 |
| OCEAN | 全 5 维矩阵积 | 仅 `ocean[2]`（外向）一个**标量偏置**加 chat 列 | 原型上界的 1/5 |
| PAD | 3 维矩阵积 | **未实现** | 欠项（§5） |
| 关系矩阵 | `(50,50)` 均值广播 | **未实现** | 欠项（§5，也是最贵的一项：O(n²)） |
| 记忆项 | `0.1 * Σ(salience*emotion)` 每 tick 衰减 0.999 | **未实现** | 欠项（§5） |
| 需求衰减 | `clip(needs - 1e-4)` 常量 | `advance_needs` 按 `DEFAULT_DECAYS` 分项速率 | 实现更细（含阈值补救） |
| 日程候选集 | 无（全 13 动作打分） | **未注入** utility（runtime 未传候选） | 欠项（§5） |
| 习惯加成 | 无 | `+0.05` 常数列 | 新增项，成本 O(n·a) 一次广播 |
| 决策 | `argmax(axis=1)` | `argmax(axis=1)` + 每 NPC scores dict 审计 | dict 构造是主要 Python 开销 |
| 实现语言/容器 | 纯 numpy 同构数组 | pydantic/dataclass `NpcProfileData` + Python 循环建矩阵 | **实现侧反而慢于原型**，见 §4 |

**结论**：S2 的**算法规模远小于** S1（3 vs 6 needs、6 vs 13 actions、缺 3 项），
S1 的红线仍是有效上界。但 S2 的**实现开销大头在 Python 侧**（`_needs_matrix` /
`_weights_matrix` 的逐 profile 循环、`evaluate_batch` 的 dict 构造、`npc_act_event` 的
pydantic 校验），不是 numpy 算术——这解释了 §4 的实测反差。

---

## 4. 实测回填（2026-09-21，本机，暖态中位）

| 被测 | 实测（中位） | 红线 | 余量 |
|---|---|---|---|
| S1 原型 `tick_vectorized` 50 NPC | **0.018ms** | `L1_UTILITY_TICK_LIMIT_MS=6.0` | ~330× |
| S1 原型 单 NPC | **0.00036ms** | `L1_UTILITY_PER_NPC_LIMIT_MS=0.12` | ~330× |
| S1 断线兜底计划队列 | ~0.01ms | `L1_OFFLINE_FALLBACK_LIMIT_MS=0.20` | ~20× |
| **S2** `utility_scores_matrix` 50 NPC | **0.206ms** | 6.0 | ~29× |
| **S2** `evaluate_batch` 50 NPC（含 scores dict） | **0.273ms** | 6.0 | ~22× |
| **S2** `NpcRuntime.tick` 50 NPC（needs+效用+事件） | **0.747ms** | 6.0 | ~8× |
| **S2** 单 NPC（1-NPC 批次） | **0.0124ms** | 0.12 | ~10× |

用例：`test_bench_l1_utility.py::test_l1_real_*`（`@pytest.mark.bench`，nightly 跑）。
口径：`warmup_rounds=1` + `assert_median_threshold`（抗首轮缓存/GC 离群），与感知红线同源。

**读数要点**：S2 比 S1 **慢一个数量级**（0.75 vs 0.018ms）——不是算法退化，而是
S1 是裸 numpy 同构数组，S2 要建 `NpcProfileData` 矩阵 + 出 `WorldEvent`。
即便如此仍远低于 6.0ms 红线（预算 §1 每 tick 16.6ms 的 4.5%）。

**若补齐 §5 欠项**（+PAD 3 列、+关系 `(50,50)`、+记忆 `(50,32)`）：
按 S1 原型比例外推 ≈ 原型量级 + S2 固定开销 ≈ 1ms 级，仍 < 6.0ms。**红线维持不变**。

---

## 5. 未落地项 / 边界（架构域，非性能域补齐）

| 欠项 | 现状 | 影响性能域口径 |
|---|---|---|
| PAD 三维效用 | 未实现 | 补齐后按 §4 推算，红线仍够 |
| 关系矩阵 `(50,50)` | 未实现 | **最贵欠项**（O(n²)/tick）；补齐时必须向量化，否则 S1 的 `tick_scalar` 哨兵会红 |
| 记忆显著性×情绪 | 未实现 | 含每 tick 0.999 衰减，注意衰减要就地/向量化 |
| 候选集注入 utility | runtime 未传（日程档+阈值补救+计划队列） | 候选集会**缩小** argmax 范围（提速），不增负担 |
| `scores` 审计 params | `ACTION_PAYLOAD_KEYS[action]` 与 scores 的动作名键不相交 ⇒ params 恒空 | 若后续要审计进 payload，需把 scores 键映射到白名单键（架构与 codex 白名单域定） |
| `NPC_ACT` handler | `build_default_bus()` 未注册（架构第三批接 tick 固定序） | 决定 soak 长跑 L1 feeder 的阶段 2 接线，见 `m2-acceptance.md` §3.1 |
| 单 NPC 计的坑 | pytest-benchmark 计**调用墙钟**，不吃返回值 | 单 NPC 用例必须用 1-NPC 批次，别除以 n（M2-P3 踩过，已修） |

---

## 6. 红线与修订纪律

- 红线集中在 `sim/tests/bench/thresholds.py`（唯一真相源），本文只引用不复制。
- **不放窄**：实测远低于红线不改红线（红线是上界，放窄 = 自缩防线）。
- **不放宽**：机器档位差异按 `docs/perf/bench-plan.md` §3 缩放口径处理，不直接改数。
- 实测值更新只改本文 §4 表与 `thresholds.py` 注释，不动常量。
