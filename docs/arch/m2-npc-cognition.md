# M2 架构设计 — NPC 底座 / L1 效用 / 非理性框架 / 物质熵增 / 嗅觉风向 / 语言判定（M2-A1）

> 依据 DESIGN.md（v2.1 冻结基线）§5 目录、§7 感知、§10 时间锁定、§13 LOD、§16 未知四轴、§17 里程碑；M2-P1 性能预算（pi，main `e42b979`）、M2-D1 数据层（opencode，`4934ec1`）、M2-S1 自我未知安全边界（codex，`8d254cb`）的交付物。
> 范围：M2 的 `sim/npc/`（底座 + utility + body + needs + cognition）+ `sim/world/matter/` + `sim/perception/`（smell + language）接口契约与模块边界。
> 不涉及：数据表结构（见 `docs/data/schema.md` §12-14）、性能红线数值（见 `docs/perf/budget.md` §1.2）、闸门实现（见 `docs/security/self-unknown.md`）——本文只定架构切面与对接缝。

---

## 0. M2 的架构目标

M2 让世界从「一个主角 + 脚本差事」变成「50 个自转的 NPC」。MVP 收官线 = 50 NPC × 7 游戏日（604,800 tick）自转无崩溃 + T1 信息边界 10k 采样通过。

架构上只有三件事必须定型（DESIGN §18「永不砍」）：

1. **NPC 底座**：属性、需求、身体、日程的统一数据模型 + LOD 升降格。
2. **非理性框架**：六偏差挂进决策链的固定缝——M3+ 所有行为能力都要过这道缝。
3. **感知传播的第三通道**：嗅觉 ∝1/r² 与风向——引擎三要素（衰减/阻断/修正）同构，只换参数与扩展算法。

---

## 1. sim/npc/ — NPC 底座

### 1.1 模块切分（对齐 `sim/npc/__init__.py` 既有声明）

| 模块 | 职责 | 不做 |
|---|---|---|
| `model.py` | NPC 聚合根：从 `npc_profiles`/`npc_health` ORM 行构造 frozen 数据类；`apply_*` 返回新实例 | 不碰 SQL（持久层在 `sim/core/persistence/`） |
| `needs.py` | 需求系统：饥饿/精力/社交等带权重需求，tick 推进 + 效用输入 | 不做决策（决策在 utility/agent） |
| `body.py` | 身体状态：hp/hunger 叙事化数据源（内感受），接 M1 narrate | 不做健康事件判定（归 events 流） |
| `schedule.py` | 日程/作息：按 tick 派生当前应做的事（作息表 + 集市日例外） | 不做计划重排（M4 意愿系统） |
| `utility.py` | L1 效用 AI：效用函数选行为 + LLM 断线兜底计划队列执行 | 不做 LLM 调用（L2 在 `sim/agent/`） |
| `society.py` | 社会关系有向图（M2 只建数据结构，传播 M3） | 不做关系推理 |
| `hidden.py` | ✅ 已交付（codex M2-S1）：隐藏属性 + 触发评估 + 直陈泄露扫描 | — |

### 1.2 LOD 与升降格（DESIGN §5/§13）

- `npc_profiles.lod` 列已就位（0=统计/1=效用/2=LLM）。M2 落地 0↔1↔2 三档：
  - **L0→L1**：进入玩家可能感知范围（8 格）或被事件波及 → 物化完整 profile。
  - **L1→L2**：进入 8 格 / 发起对话 / 被卷入事件 → 升格，LLM 接管规划。
  - **L2→L1**：离开范围且对话结束 30 游戏秒 → 降格，**LLM 结论必须压缩写回记忆**（`MemoryWritePipeline.write()`，source=`reason`）——这是断线恢复与降格不丢人格的关键缝。
- 升降格由 **tick 驱动的事件**表达（`EventKind.NPC_LOD_CHANGE`，M2-A2 实现），禁止直接改列——C4 唯一写路径。

### 1.3 50 NPC 装配

- NPC 实例按需物化（L0 只存行，不建对象）；tick 内同时活跃对象 ≤ 50（MVP 地图规模）。
- 装配入口 `sim/npc/runtime.py`（M2-A2）：`NpcRuntime.tick(tick, rng, events)` → 返回本 tick 事件批次；世界循环每 tick 调一次。

---

## 2. sim/npc/utility.py — L1 效用 AI（兼断线兜底）

### 2.1 决策模型

```
效用(action | npc, t) = Σ_i w_i · satisfaction_i(action 改变量)   # needs 加权和
                      + habit_bonus(action)                        # 习惯路径依赖（§3 非理性）
                      + sunk_cost_penalty(abandon)                 # 沉没成本
候选集 = schedule 当前档 ∪ needs 触发的补救动作 ∪ 计划队列剩余项
```

- **向量化**（pi 实测 ~0.02ms/tick @50NPC）：全 NPC 需求矩阵 `(50, n_needs)` numpy 一次算完，禁止逐 NPC Python 循环。
- **断线兜底**：`llm_available=False` 时 L2 位 NPC 降级执行**计划队列**（LLM 上次规划的行动序列）；队列空则落到 L1 效用选择。重连后断线期记忆按「低保真」补写（DESIGN §6）。
- **输出**：`UtilityDecision(action_id, target, scores)` → 生成 `EventKind.NPC_ACT`（白名单动作集，M2 只需：移动/工作/进食/休息/闲逛/交谈请求）。

### 2.2 与闸门的关系

L1 决策**不走 IntentGate**（闸门审 LLM 输出；效用函数是确定性代码，无可注入面）。但 L1 产出的对话请求升格 L2 后，其 LLM 输出照常过闸门——边界见 `docs/security/self-unknown.md` §4。

---

## 3. sim/agent/cognition.py — 非理性框架（M2 默认开启）

### 3.1 六偏差的挂载缝（DESIGN §7 表格逐条落地）

| 偏差 | 挂载点 | 实现缝 |
|---|---|---|
| 确认偏误 | 记忆检索 | `MemoryWritePipeline`/检索侧：与既有信念一致的条目权重上浮（检索打分乘系数，不改存储） |
| 沉没成本 | utility 效用函数 | `sunk_cost_penalty`：已投入时间/资源计入继续意愿（上表） |
| 习惯 | utility 候选集 | 重复行为 → `habit_bonus`；改变需意愿冲突（M4 will 接管，M2 先记档） |
| 创伤应激 | hidden.py 触发 | `evaluate_triggers` 命中 → 回避动作直接进候选集，绕过效用比较（已有接口） |
| 情绪一致性 | 记忆检索 | PAD 当前情绪 → 检索偏向同价情绪记忆（同确认偏误的检索缝） |
| 醉酒 | 感知 + 意愿 | 感知层噪声上升（propagation 修正系数）；意愿抑制 M2 只留接口（`inhibition: float`），M4 生效 |

### 3.2 架构约束

- cognition 是**纯函数层**：输入（profile, needs, mood, memory_scores, context）→ 输出（修正后的分数/候选集）。无 IO、无状态、可重放。
- 默认开启**不可配置关闭**（DESIGN §7「不是可选」）——不留 feature flag，防止测试与真实行为分叉。
- LLM prompt 不感知偏差参数：偏差只作用于**检索打分与效用计算**，不进 prompt 文本——保持 prompt 装配纯净，偏差由代码层施加。

---

## 4. sim/world/matter/ — 物质熵增

### 4.1 事件类型（扩展 `EventKind`，M2-A2 实现）

对齐 opencode `docs/data/schema.md` §14 的事件形状（`matter.decay|damage|build|collapse` + witnesses + entropy_ref）：

- `MATTER_DECAY`：自然衰减（食物腐坏/建筑风化），按 tick 批量结算（RNG 分桶：每 tick 一次批量 draw，不用逐实体 draw——C5 预算内）。
- `MATTER_DAMAGE` / `MATTER_BUILD` / `MATTER_COLLAPSE`：交互产生；`COLLAPSE` 在 M4 承重系统接入前只做「耐久归零 → 塌」的简化版。
- `matter_state` 表 = 事件流的**持久化投影**（opencode 已建）；`apply(MATTER_*)` 是唯一写路径，表由 flush 同步——与 entropy_log 同构。

### 4.2 tick 内时序

感知 → L1 效用/计划执行 → **matter 结算**（固定序末尾，pi 对账提示 #2：嗅觉与物质都要 tick 固定序，C5 确定性）→ flush。

---

## 5. sim/perception/ — 嗅觉通道 + 语言判定

### 5.1 smell.py — 嗅觉传播（pi 红线 0.15ms/tick）

**算法采纳 pi 对账提示 #2：Eulerian 网格增量扩散**，不做逐对：

```
SmellField（64×64 网格 × 物质种类数）
  1. 源发射：持续源（食物堆/尸体/作坊）按强度向所在 cell 加注
  2. 平流：沿风场（tick 变化的风向向量）位移半格 + 8 邻域扩散（∝1/r² 由网格衰减系数近似）
  3. 衰减：全图乘衰减系数
  4. 接收：NPC 所在 cell O(1) 采样 → Observation(channel=SMELL, ...)
```

- 三要素映射：衰减=全图系数；阻断=**不阻断**（绕障是平流的自然结果）；修正=风场。与视觉/听觉同构。
- **API**：`smell_propagate(field, sources, wind, tick) -> SmellField`（纯函数，可重放）；`SmellField.sample(pos) -> float`。
- 风场：`sim/world/weather.py`（M2-A2）按日/时段从 RNG 派生风向风速——事件流记录 seed，重放一致。
- 挂载点：`run_perception_step` 内、视觉/听觉之后（pi 提示：感知之后、tick 固定序末尾）。

### 5.2 language.py — 语言判定

- `LanguageProfile(literacy, jargon: Sequence[str], class_register)`：**按角色**构造（数据层既定 `npc_profiles.knowledge_boundary` JSON = 每角色一份，opencode 0004 迁移夹具为准）；`species_language` 才是物种级枚举位（human 共用一套感知参数，DESIGN §7——勿与语言能力混淆，kilo M2-K1 澄清）。命名以数据层夹具为准：`class_register`（非 `register`）、`jargon: Sequence[str]`（JSON list）。
- 判定规则（纯函数，零 LLM）：
  - 识字类观察（布告/书籍）：`literacy` 不足 → 「有音无义」变体（「画着些看不懂的符号」）。
  - 行话/阶层用语：词表命中 → 按听者 class_register 输出「几个词你没听明白」。
  - 物种语言档：cat 无语言（人声=纯音）、dog 40-60 词、raven 伪语言——M2 只留 `species_language` 枚举位，M6 动物接入。
- 出戏三红线（kilo 实测 `banned_words.scan()` 0 命中的口径延续）：降质文案零数值零系统词；`literacy` 只做阈值判据、绝不进文本；降质只动叙事层文本。
- 挂载点（M2-K1 意见④采纳，2026-09-21）：`PerceptionFrame.narrated()` 装配内的**通道分组输出前**——听不懂的话在叙事层降质，`Observation`/`PerceptionFrame` 的原始数据保持完整（供 debug 与 M3 知识传播复用；若挂在 Observation 构造处，观测对象本身被裁剪，此保证即失效）。接口面不变：降质文本走现有 perception 消息 `content`（string），判据字段不出 WS。

---

## 6. 与已收编交付物的接缝

| 交付物 | 本文接缝 |
|---|---|
| codex `hidden.py` | cognition 创伤应激直接调 `evaluate_triggers`；闸门/记忆写入的 `hidden/triggered` 参数由 NPC runtime 每 tick 传入 |
| opencode 三表 | `model.py` 从 ORM 行构造 frozen 聚合；LOD 变更走事件流（不直改 `lod` 列） |
| pi 5 阈值常量 | utility/smell 实现的性能护栏；向量化与网格方案为达标前提（实测余量 300×/15×） |
| kilo 跨域发现 | `openapi_ext.py` 的 wsMessages 注入改写进 `components.schemas`（M2-A2，kilo 复核）；`error` 消息 sim 侧补发 `ref` 或快照去 required |
| cline CI 占位 | 架构域 CI 级测试命名 `sim/tests/test_m2_*.py`（如 `test_m2_smell_field.py`）；604,800 tick 完整跑接 nightly（待裁接法） |

---

## 7. 实施顺序（M2-A2 起，按依赖）

1. **NPC model + needs + body + runtime 骨架**（无行为，先立数据流）→ 2. **utility 向量化**（对齐 pi bench）→ 3. **matter 事件 +结算** → 4. **smell.py + weather 风场** → 5. **language.py + narrate 接线** → 6. **cognition 六偏差**（依赖记忆检索打分缝）→ 7. **LOD 升降格 + 断线兜底** → 8. **7 日自转验收脚本**（接 nightly）。

分工建议：1-3 归我（架构域主战场），4 的 smell.py 归我、weather 归 cline（配置域 RNG 派生），5 归 kilo（接口/叙事边界复核）+ 我，6 归我，7 归我 + opencode（LOD 事件持久化），8 归 pi（验收口径）+ cline（CI 接法）。
