# T1 信息边界 10k 采样验收口径（docs/security/t1-sampling-10k.md）
> 维护：Codex（安全/合规/风险域）· 依据：DESIGN.md §17（M2 量化验收）/§16（未知四轴）、
> self-unknown.md（M2-S1）、l1-whitelist.md（M2-S2）· 日期：2026-09-22
> 状态：M2-S4 交付稿。实现：`sim/tests/test_m2_t1_sampling_10k.py`（harness 骨架）。

## 0. 一句话

M2 量化验收的 T1 信息边界项：对隐藏创伤属性（自我未知）做 **10,000 次直陈/触发采样**，
判据 = **零直陈泄露**（未触发属性被直陈的次数必须为 0）；触发浮现路径作为对照同步采样。
单测（test_t1_self_unknown.py / test_t1_l1_whitelist.py）覆盖逻辑分支；本验收 = 同一
工具链的规模化执行（口径见 §4）。

## 1. 采样对象

| 对象 | 来源 | 说明 |
|---|---|---|
| 隐藏属性 | `HiddenProfile` 标注（health 档隐藏项 + 创伤触发项） | 每样本一条属性 × 一条候选输出文本 |
| 候选输出文本 | 假 LLM 路径生成的 reason / 记忆内容 | 零网络、纯本地构造；真实 LLM 接入后换产出源，判据不变 |
| 扫描工具 | `sim.npc.hidden.hidden_leak_scan`（闸门 + 记忆写入共用同一工具） | 只扩不改（M2-S1 已收编文件纪律） |
| 触发评估 | `HiddenState.evaluate` / `evaluate_triggers` | 每 tick 重估窗口的纯函数（self-unknown.md §2） |
| 拒绝面 | `IntentGate.revalidate_at_execution(hidden, triggered)` + `MemoryWritePipeline.write(hidden, triggered)` | 双防线：闸门拒 reason 直陈、记忆拒写内容直陈（REASON_HIDDEN_LEAK） |

采样分布（4 类场景，各 2,500 条，总 10,000）：

| 场景 | 触发窗口 | 直陈词面 | 期望 |
|---|---|---|---|
| A 未触发直陈 | 良性处境（无触发词） | 有 | 扫描命中 → 闸门拒绝 + 记忆拒写 |
| B 未触发行为暗示 | 良性处境 | 无（仅行为描述词） | 零命中、零拒绝（行为暗示可议） |
| C 触发浮现直陈 | 触发处境（命中该属性触发词） | 仅已触发属性 | 零命中、放行/可写（浮现窗口内合法） |
| D 混合属性 | 触发处境（已触发属性 A） | A + 未触发属性 B | B 命中 → 拒绝（浮现后仍受审查） |

## 2. 判据（验收红线）

1. **零直陈泄露**：场景 A/D 中，任何未触发属性直陈必须被 `hidden_leak_scan` 命中，
   且闸门拒绝（`hidden_attribute_leak`）/ 记忆拒写（`REASON_HIDDEN_LEAK`）。
   10,000 条样本中「未触发直陈逃逸」计数 = 0 即通过。
2. **零误伤**：场景 B/C 中，行为暗示与已触发直陈不得被拒绝（防线不能误杀正常叙事）。
3. **分布完整**：4 类场景各 2,500 条；样本空间覆盖全部样例属性与全部描述词/触发词
   （harness 断言覆盖率，防止空转）。
4. **确定性**：样本生成走固定 RNG 流（sim.core.rng），同 seed 同结果（可重放）。

## 3. 触发分布

- 处境文本池：良性处境（不含任何触发词）与触发处境（含属性触发词）按 1:1 构造；
  触发处境仅对该属性触发，不连带触发其他属性（词面卫生由 M2-S1 语料卫生测试背书）。
- 直陈词面池：每属性 descriptors 全量入池；每条直陈样本随机取 1-2 个词面拼装。
- 行为暗示池：走路瘸 / 回避话题 / 扶墙 等行为描述词（不在扫描面，S1 口径）。
- RNG：`sim.core.rng` 分流 RNG（DESIGN §19 禁 stdlib random；样本索引与词面抽取
  全部走固定 seed 的 RNG 流）。

## 4. 与 M2-S1 双路径测试的关系

| | M2-S1 单测（test_t1_self_unknown.py） | 本验收（test_m2_t1_sampling_10k.py） |
|---|---|---|
| 目的 | 逻辑分支覆盖：每条断言对应一个口径条款 | 规模化执行：同口径 × 10,000 样本 |
| 样本量 | 手工样例集（3 属性 × 双路径） | 4 场景 × 2,500，覆盖全部属性/词面/触发词 |
| 工具 | hidden_leak_scan / gate / memory_scan（同一套） | 完全同一套（不复制逻辑、不另建防线） |
| 失败含义 | 口径实现错误 | 大规模逃逸/误伤（词面组合边界） |

终验口径：**两者都绿才构成 T1 信息边界验收**；单测保证「对」，
10k 保证「稳」（组合空间上的零逃逸）。

## 5. harness（sim/tests/test_m2_t1_sampling_10k.py）

- 骨架交付：4 场景 × 2,500 条全量跑（10,000 条，纯 T1、零网络、秒级~分钟级）。
- 假 LLM 路径：样本文本 = 本地词面池拼装（`FakeLlmText` 生成器），不调任何模型；
  cognition 未落地前不模拟 cognition 输出形状——采样面是「候选输出文本」，
  与产出源解耦，后续真 LLM 接入只换文本来源。
- 命名：`test_m2_` 前缀 → 自动进 CI「M2 验收测试」glob（.github/workflows/ci.yml
  已有按文件路径门禁，无需新增步骤）。
- 计数器：`SamplingCounters` 汇总四场景命中/拒绝/放行计数，断言即判据 §2。
- 性能护栏：10,000 条需在 CI 预算内（秒级~分钟级）；若未来场景扩容导致超预算，
  按Ci.yml 头注口径改接 nightly 并在本文档登记（当前不动）。

## 6. 责任与维护

- 本口径与 harness 维护：Codex（安全域）。判据变更走 CR（安全域 owner）。
- S1 已收编文件（hidden.py / gate.py / memory_scan.py / contract.py）只扩不改；
  harness 发现逃逸 → 按 self-unknown.md 流程补 descriptor 词面或修工具，
  不在 harness 内复制防线逻辑。
- CI 接入：沿用「M2 验收测试」glob（命名约定即契约）；无独立新增 CI 步骤。
