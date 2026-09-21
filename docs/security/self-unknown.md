# 自我未知安全边界（docs/security/self-unknown.md）

> 维护：Codex（安全/合规/风险域）· 依据：DESIGN.md v2.1 §8/§13/§16 · 日期：2026-09-20
> 状态：M2-S1 交付稿。实现：`sim/npc/hidden.py`（标注+触发+泄漏扫描）、
> `sim/agent/gate.py`（执行时二次校验扩展）、`sim/llm/memory_scan.py`（写入拒写扩展）、
> `sim/tests/test_t1_self_unknown.py`（T1 双路径采样）。
> 评审：cline（依赖/配置/文档域）。数据表协调：opencode（M2-D1，0004 起号）。
> 关联：`m1-checklist.md`（M1-A~I 出戏防护基线）、`memory-scan.md`（记忆写入唯一入口 S1）、
> `t3-corpus.md`（出戏对抗语料）。

## 0. 一句话

「自我未知」= Agent 可能不知道自己某一面（DESIGN §16 未知四轴）：健康档里的隐藏创伤属性
（疾病/旧伤/成瘾/残疾 + 创伤应激触发条件）默认**不进入任何 LLM/戏内输出面**；只有情境触发
命中的那一刻才浮现给 Agent 自身；浮现后仍受闸门审查。**直陈未触发属性 = 拒绝；行为暗示可议
（不阻断）。**

## 1. 数据标注规范（NPC profile 隐藏属性标记）

在 NPC 健康档（DESIGN §13 健康：疾病、旧伤、成瘾、残疾）+ 创伤应激（§8 非理性框架）之上，
加一层「隐藏」标注。每个隐藏属性一条记录（`HiddenAttribute`）：

| 字段 | 说明 | 示例 |
|---|---|---|
| `id` | 稳定戏外主键（不进任何戏内/prompt 面） | `chenmo.leg_old_injury` |
| `category` | 隐藏类别：`disease`/`old_injury`/`addiction`/`disability`/`trauma` | `old_injury` |
| `label` | 世界内指称（文档/调试用，本身也是直陈词面之一） | 右腿旧伤 |
| `descriptors` | 直陈词面——独白/记忆里「直接说出该属性」会用到的话（泄漏扫描面） | `旧伤`、`右腿旧伤` |
| `triggers` | 情境触发关键词——对当前处境文本（感知帧叙事+内感受）子串匹配，命中任一 → 本 tick 浮现 | `阴雨天`、`右腿` |

铁律：

1. **隐藏属性永不进入**：感知帧（含内感受叙事）、独白 prompt（[身份锚]/[记忆]/[处境]/[计划]/[输入]
   六段）、记忆检索默认结果。分工：感知引擎/装配器接入本规范的可见性契约归 Claude 架构域
   （M2-A1）；安全侧闸门（reason 直陈）与记忆写入扫描（内容直陈）本树落地。
2. **直陈 vs 行为暗示**：`descriptors` 是「直陈面」，说了就是泄露；行为描述词（走路瘸、回避话题）
   不在扫描面——行为暗示可议，不做闸门拒绝。
3. **浮现窗口**：触发按 tick 重估（`evaluate_triggers` 纯函数，调用方每 tick 对当前处境文本求值）；
   触发消退 → 回归隐藏。浮现后仍受闸门审查（其他未触发属性照样拒绝）。

## 2. 情境触发浮现机制

- 入口：`sim.npc.hidden.evaluate_triggers(profile, context_text) -> frozenset[str]`。
- `context_text` = 该 tick 的感知帧叙事 + 内感受文本（Agent 自己的处境，不是他人处境）。
- 语义：属性 A 的任一 `triggers` 关键词在 `context_text` 中出现 → A 本 tick 可见。
- 消费契约（给 Claude 架构域）：感知引擎/行为循环每 tick 调用 `evaluate_triggers`，把返回的
  `triggered` 集合传给 (a) 独白/行为链装配（仅 triggered 属性可进处境/内感受叙事）、
  (b) 闸门执行时二次校验 `revalidate_at_execution(hidden=profile, triggered=...)`、
  (c) 记忆写入管线 `write(..., hidden=profile, triggered=...)`。
- 未接入前（M2-S1 本树交付）：`hidden` 参数缺省为 None → 行为与 M1 完全一致
  （无隐藏属性即无检查），零回归。

## 3. 闸门扩展（执行时二次校验）

`IntentGate.revalidate_at_execution(..., hidden, triggered)` 在原有目标存在/距离检查之外新增
「自我未知」维度：

- 对 `intent.reason`（独白唯一来源）跑 `hidden_leak_scan(reason, profile, triggered)`；
- 命中 → `GateVerdict(False, hidden_attribute_leak)`（结构化原因供重规划，不含 LLM 原文）；
- 口径：未触发属性被直陈 → 拒绝；触发中属性被直陈 → 放行；同一 reason 混入其他未触发属性 →
  拒绝（浮现后仍受审查）。

## 4. 记忆写入扫描（记忆检索默认结果防线）

`MemoryWritePipeline.write(..., hidden, triggered)` 在禁词扫描之前先跑隐藏属性直陈扫描：

- 命中 → 拒写（`reason=hidden_attribute_leak`），不进 store → 记忆检索默认结果天然无
  未触发隐藏属性内容；
- 不改写：直陈面不是机械词（与 S3 词面改写不同类），拒写保底——记忆缺失比记忆污染安全
  （同 S4 底线判断）；
- 检索侧默认过滤由写入防线兜底；M3 向量检索接入后若出现「触发时写入、触发消退后检索」的场景，
  由检索端按当前 `triggered` 集合过滤（本树只留接口契约，不越界到 M3 实现）。

## 5. T1 双路径采样（test_t1_self_unknown.py）

| 路径 | 断言 |
|---|---|
| 未触发零泄露 | `evaluate_triggers(良性处境)`=∅；直陈文本 `leak_scan` 命中；闸门拒绝 `hidden_attribute_leak`；记忆写入拒写；感知帧叙事/装配 prompt 面零描述词 |
| 触发正常浮现 | `evaluate_triggers(触发处境)`={id}；直陈已触发属性闸门放行、记忆写入通过；同一文本混入未触发属性仍拒绝（浮现后仍受审查） |
| 附加口径 | 行为暗示（走路瘸）不命中；descriptors/triggers 语料卫生（不含 M1 禁词）；ASCII 描述词大小写不敏感 |

CI：按文件路径独立红灯信号（沿用 `test_t3_gate.py` 做法），见 `.github/workflows/ci.yml`。

## 6. 数据表协调（opencode M2-D1）

NPC 完整属性 0004 迁移（opencode 域）建议为健康档隐藏标注预留：

- 方式 A（推荐）：`npc_health` 表加 `hidden INTEGER NOT NULL DEFAULT 0` +
  `trigger_conditions TEXT NOT NULL DEFAULT '[]'`（JSON 数组，元素与本规范 `triggers` 一致）；
- 方式 B：独立 `npc_hidden_attributes` 表（npc_id, category, label, descriptors, triggers）
  与健康表 1:N。

本树 `sim/npc/hidden.py` 的 `HiddenAttribute` 即 0004 的字段映射参照；持久化实现归 opencode，
本树只持内存态模型与规则。

## 7. 责任与维护

- 词面（descriptors/triggers）变更走 CR（安全域 owner：Codex）——同 banned_words 维护纪律；
- 感知引擎接入（把 `evaluate_triggers` 接进处境/内感受叙事）归 Claude 架构域（M2-A1 架构稿）；
- 持久化（0004 表）归 opencode（M2-D1）。
