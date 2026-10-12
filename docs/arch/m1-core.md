# M1 认知内核（m1-core）

> 状态：**收官后补记**（M1 于 2026-09 收官，本文 2026-10-12 补写）。
> 职责范围：DESIGN §4/§6/§7/§8/§15 —— LLM 客户端、Profile、Intent 闸门、
> 感知引擎、身份锚、独白叙事化、社会未知、20 差事指标。
> 归属：架构（Claude）。登记于 docs/README.md §2 文档地图与 §4 M1 区块。

---

## 1. 定位与范围

M1 在 M0 确定性内核之上立起「认知闭环」：世界照常 tick（C1 内核零认知依赖），
认知域全部**异步挂在内核旁**——LLM 永不阻塞世界，LLM 永不直接改世界。

```
内核（tick loop，同步确定性）
  │ 事件流（C4 唯一写路径）
  ├─→ 感知引擎（每 tick 装配 PerceptionFrame）
  │       ↓
  │   prompt 装配器（六段结构）
  │       ↓
  │   LLM 客户端（异步，永不进 tick）
  │       ↓
  │   Intent schema（LLM 唯一输出）
  │       ↓
  │   意图闸门（两道校验）
  │       ↓
  └──事件入队（回到 C4 唯一写路径）
```

### 不做（边界即设计）

- 内核零依赖认知域：`sim.core` 不 import `sim.llm` / `sim.perception` / `sim.agent`
  （内核替换不回改，钩子注入制——`attach_perception` / `attach_npc_runtime`）。
- LLM 失败零阻断：调用超时/断网/坏 JSON 全部降级（闸门结构化拒绝 → 重规划
  或队列排队），世界 tick 照常。
- 感知帧零出戏字段：tick 之外的 entity_id/seed/内部枚举不进帧（帧是 debug
  坐标外的玩家视角产物）。

## 2. 模块与职责（源码落点速查）

| 模块 | 行数 | 职责一句话 | 关键纪律 |
|---|---|---|---|
| `sim/llm/client.py` | 252 | OpenAI 协议通吃客户端；api_key 用完即丢（K3/K4）；structlog 监控事件族 | 单次决策最多重试 1 次（§15 成本治理）；监控字段对齐 `docs/perf/llm-monitoring.md` |
| `sim/llm/prompts/identity.py` | ~40 | 身份锚：自述+人格摘要+长期目标，frozen | 锚定不可变；prompt 第一段 = 前缀缓存分界（messages[0]） |
| `sim/llm/prompts/assembler.py` | ~200 | 六段 prompt 装配：[身份锚][记忆][处境][计划][输入][要求] | 装配产物全文过 `banned_words.scan()`，命中即装配失败（出口唯一闸） |
| `sim/llm/prompts/banned_words.py` | ~200 | 禁词单一数据源（prompt/记忆/出站共用） | S6 起 META_SHELL 空表并入 `scan_meta_shell`；REWRITE_MAP 改写梯 |
| `sim/agent/intent.py` | 84 | Intent schema：Literal 枚举 + extra="forbid" | LLM 原始 JSON 严格校验后才能进闸门；解析失败=结构化拒绝 |
| `sim/agent/gate.py` | 159 | 意图闸门两道校验：规划预检 + 执行时二次校验 | 拒绝=结构化原因（不静默丢弃，§19）；过期 Intent 执行时丢弃 |
| `sim/agent/impulse_gate.py` | 132 | 玩家念头注入闸门（player_impulse） | 念头只通主角；词面+边界双校验 |
| `sim/perception/senses.py` | 426 | 感知引擎：视觉（Bresenham 遮挡）/听觉（衰减不阻断）/触/内感受 | 半径预过滤 → 候选对打射线；显著性截断 ≤ max_observations |
| `sim/perception/propagation.py` | 250 | 感知传播三要素（光/声/嗅源强度距离） | 视觉每 2 tick 降采样（H-1 方案 3）；引擎纯读幂等 |
| `sim/perception/narrate.py` | 99 | 世界状态 → 世界内语言（数值/动机/时间零元信息） | 纯函数模板；hp:30 →「左肋疼得厉害」 |
| `sim/perception/salience.py` | 66 | 显著性截断（prompt 体积治理） | 单帧 ≤ profile.max_observations 条 |
| `sim/perception/frame.py` | 100 | PerceptionFrame 数据形状 | 零出戏字段（帧=玩家视角产物） |
| `sim/perception/smell.py` + `smell_world.py` | 172 | 嗅觉通道 + 风场耦合（M2 前置预埋） | 基半径 × 风向修正式 |
| `sim/npc/hidden.py` | ~200 | 自我未知：隐藏属性标注/情境触发/泄漏扫描 | 同一工具三处共用（闸门/记忆/扫描），禁两处维护 |

## 2.1 后续批次的接线点（M1 地基上的扩建，不在本文范围）

- **批次 E（对话/经济/战斗）**：`sim/agent/driver.py`（ChenmoDriver 执行面）、
  `sim/agent/dialogue.py`（模板池+LLM 线）、`sim/agent/combat_exec.py`、
  `sim/agent/build_exec.py`——执行面翻译器体例，见
  `docs/superpowers/plans/2026-10-09-batch-e-gameplay-wiring.md`。
- **认知偏差**：`sim/agent/cognition.py`（M2-A2 第三批）。
- **LLM 断线兜底**：L1 效用（`sim/npc/utility.py`，M2 交付）。

## 3. 六段 prompt 结构（DESIGN §8）

段序固定，前段可命中供应商前缀缓存：

1. **[身份锚]** —— IdentityAnchor（frozen），messages[0] 缓存分界。
2. **[记忆]** —— 检索缝召回（M3 向量化前为余弦打分），过 memory_scan。
3. **[处境]** —— 感知帧叙事化文本 + 地标（批次 E 增 landmarks_text）。
4. **[计划]** —— PlanDelta 渲染；空计划=空段（非占位文本）。
5. **[输入]** —— 本 tick 触发（差事/对话/遭遇）。
6. **[要求]** —— 固定文本：Intent JSON 输出契约 + reason 第一人称世界内语言。

出戏边界防线（装配层强制）：装配产物全文过 `banned_words.scan()`，命中即
装配失败——装配产物是 LLM 出口，等同记忆出口的 S1 唯一入口原则。

## 4. 闸门两道校验（C1 的牙齿）

1. **规划时预检**（`gate.validate`）：动作枚举已由 schema 保证，语义查
   （目标存在/距离可达/reason 非空）；拒绝=结构化原因反馈重规划。
2. **执行时二次校验**（`gate.revalidate_at_execution`）：Intent 入队后在
   执行 tick 再校验——世界已变化导致过期 Intent 丢弃并触发重规划；
   LLM 异步延迟天然无害（§8）。M2-S1 扩展：未触发隐藏属性被直陈即拒绝。

> 批次 E 补线（2026-10-11 评审）：买/卖/建造/攻击四动作经**同一闸门白名单**
> （买/卖 target_id 是货物名，豁免实体存在检查）——闸门白名单是唯一执行
> 许可源，测试不得绕闸直 append `_pending`。

## 4.1 念头注入（玩家=直觉）

`impulse_gate.py`：玩家文本 → 词面+边界双校验 → 陈默下一决策的输入段。
与世界真实性不冲突：念头是陈默的直觉，不是上帝指令（对照 GOD /intervene
的拒绝理由，见 `docs/data/god-reuse-final.md` §2）。

## 5. 感知引擎（信息边界 C2 的产出物）

- **输入**：WorldState + TileMap（静态遮挡）+ 本 tick 事件流。
- **输出**：每 observer 一帧 PerceptionFrame（显著性截断后 ≤ max_observations）。
- **性能体**：视觉半径预过滤 → 候选对 Bresenham 射线；听觉 base/r 衰减不
  阻断；视觉每 2 tick 降采样（H-1 方案 3），听觉每 tick 全速。
- **叙事化**：`narrate.py` 纯函数模板——数值永不出（hp:30 →「左肋疼得
  厉害」）、动机永不出（trust:-20 →「他看我的眼神不太对」）、时间零元信息
  （tick →「天色暗下来了」）。
- **嗅觉**：`smell.py` 基半径 × 风向修正（`smell_world.py` 风场耦合，M2
  weather 前置预埋）。

## 6. 量化验收（DESIGN §17 M1 行，实测记录于 docs/README.md §4）

| 指标 | 门槛 | 实测 | 结论 |
|---|---|---|---|
| 脚本差事完成率 | ≥80% | 20/20（假 LLM 下界） | ✅ |
| 决策延迟 P95 | <8s | ≈0.25ms（链路计算耗时下界） | ✅ |
| 单决策 prompt | <2k tok | 232–274 字符 ≈145–171 tok | ✅ |
| T3 出戏对抗 | 100% 安全 | 69 条语料 78 断言全绿 | ✅ |

> 口径：延迟与完成率是假 LLM（脚本应答、零网络）下的下界；真实墙钟延迟由
> `docs/perf/llm-monitoring.md` 日汇总看板监控。两者量纲不同，不可互替。

## 7. 测试落点速查

| 测试 | 覆盖 |
|---|---|
| `sim/tests/test_m1_metrics.py` | 四指标跑分（CI 按文件路径跑） |
| `sim/tests/test_t3_gate.py` | 69 条对抗语料 78 断言（CI 按文件路径跑） |
| `sim/tests/test_banned_words.py` / `test_memory_scan.py` | 禁词表 / 记忆写入管线 |
| `sim/tests/test_t1_self_unknown.py` | 自我未知双路径 28 例 |
| `sim/tests/test_m2_t1_sampling_10k.py` | T1 信息边界 10k 采样 |
| `sim/tests/test_m1_intent_gate.py` | Intent schema + 闸门两道校验 |

## 8. 已知演进记录（历史不改，现状为准）

- **W6 鉴权**：token + hello 握手 hmac + Origin 白名单（codex S04，main
  `66f3f18`）；前端 token 接入归 kilo 后续对接。
- **P3 加固 3 项**：bool 穿透 / rtoken 注释 / 键白名单断言——S04 全收口。
- **M2 扩展**：认知偏差六偏差、L1 断线兜底、smell/weather 接感知步——
  见 `docs/arch/m2-npc-cognition.md`。
- **批次 E 扩展**：对话/经济/战斗/建造执行面、对话模板池+LLM 线、
  landmarks_text——见 `docs/superpowers/plans/2026-10-09-batch-e-gameplay-wiring.md`。
- **T4 泄漏修**（2026-10-12）：LLM 线回声泄漏 → `sanitize_provider_line`
  改写梯 + REWRITE_MAP 扩表（`sim/agent/dialogue.py`）。
