# M3 规划：记忆·传播·可变世界（架构域整合稿）

> 维护：Claude（主导/架构域）· 2026-09-23
> **本文是三份 M3 预研的整合骨架**：安规缝（codex m3-preplan.md）、数据契约（opencode
> schema.md §19 + vec-preplan.md）、接口契约（kilo K3 复验 + ws-message-diff.md）。
> 职责：把预研结论映射到模块施工点，切分 M3 分批派单。实现细节以各域预研稿为准，
> 本文不重复其表格——只做**排序、归属、依赖**三件事。
> 基线：DESIGN.md §17 M3 = 记忆/向量检索/反思+关系+知识传播+不成文规矩+可变地图底座+空间迷雾。
> 量化验收：**NPC 记得且会转述；chunk 失效正确**。

---

## 0. M3 范围四句话

1. **记忆长出向量检索**（vec-preplan）：候选生成器换源，打分链一字不动。
2. **记忆长出传播**（m3-preplan R 面）：转述/反思/知识表，全部走写入门，治理列闭环。
3. **地图长出可变性**（schema §19 + M4 前置）：matter 读路径 + chunk 失效。
4. **安规缝全部钉住**（R1-R7/C1-C13/X1-X8）：两枚 T1 RED 钉子已派（codex M3-S1）。

---

## 1. 预研结论速览（→ 详细出处）

| 预研稿 | 核心结论 | M3 施工点 |
|---|---|---|
| `m3-preplan.md`（codex） | R1-R7 传播缝 4 条真实（knowledge 无治理列/vec 无治理/双列口径/分支混入）；C1-C13 建造输入面（M4 用，C2 提前）；X1-X8 扫描面（breakdown 构造隔离） | §2 批次内的 T1 钉子 |
| `vec-preplan.md`（opencode） | sqlite-vec 主 + numpy 降级（裁 3）；5 万条量级两法均亚毫秒=**非瓶颈，成本在 embedding 生成**；`LlmClient.embed` 独立缝；候选源替换不触打分链（§18 硬边界） | 批次 A 全部 |
| `schema.md §19`（opencode） | `materialize_matter(ids=None) -> MatterLedger` 快照路径；重放路径同折叠规则；注册由 `MATTER_BUILD` 立账事件持久化 | 批次 C |
| K3 复验（kilo） | 接口契约 0 差异；M5 anchors 契约稿与 404 handler 提案是切源解禁实现侧（不阻塞 M3） | M5 批次（本文不展开） |

## 2. 依赖与排序总纲

```
批次A 向量检索（数据+性能）
   │ embedding 缝（LlmClient.embed ← V3 提案先行）
   ▼
批次B 传播（安全+架构）──依赖 A 的候选源接口稳定（R2 治理过滤挂在候选生成处）
   │ 反思批处理（§15）依赖 B 的写入闭环
   ▼
批次C 可变地图底座（数据）──独立于 A/B，可并行
   │
   ▼
批次D 社会面（架构）──依赖 B（传播通路）+ R5 证据链规则
```

- **A 与 C 可并行**（无共享文件）；B 等 A 的接口冻结；D 最后。
- codex M3-S1 的两枚 RED 钉子（R2 vec 治理缝 / C2 MatterPayload 域约束）**先于一切实现**。

## 3. 批次切分（派单粒度）

### 批次 A — 向量检索（opencode 主 + pi 辅 + Claude 裁 V3）

| # | 工作项 | 域 | 前置 |
|---|---|---|---|
| A1 | V3 提案定稿（embedding profile 缝三选一）→ 全员裁决 | opencode 提案 | — |
| A2 | `MemoryEntry.embedding` 字段 + 写路径挂 embedding 生成（V7 提案过 codex 后） | opencode | A1 |
| A3 | `VectorIndex` 接口 + sqlite-vec 主实现 + numpy 降级实现（裁 3 V1） | opencode | A2 |
| A4 | 候选源替换：`retrieve` 前置向量候选 + 治理过滤 JOIN（裁 3 V6，R2 落点） | opencode | A3 + S1 钉子 |
| A5 | bench：检索缝预算（防每 tick 全量检索红线——防呆约定期延续） | pi | A4 |
| A6 | 监控：`llm.embed_*` 事件族 | pi | A1 |

### 批次 B — 记忆传播与反思（codex 验收 + opencode 存储 + Claude 行为链）

| # | 工作项 | 域 | 前置 |
|---|---|---|---|
| B1 | R3 双列口径裁决（iter_visible 过滤条件写死） | Claude 裁 | — |
| B2 | R4 分支隔离：读 API 带 branch_id | opencode | B1 |
| B3 | R1 knowledge 治理列 + 级联失效 + `source_memory` 派生列 | opencode | B2 |
| B4 | R5 证据链规则（witnessed@triggered-tick / told 衰减 / inferred 禁他人属性） | codex 契约 + Claude 实现 | B3 |
| B5 | R6 传播=复制写（A 告诉 B = B 走 write()）；R7 反思走 write(source="reason") + S1 守卫扩展 | Claude | B4 |
| B6 | 反思批处理（DESIGN §15：每游戏日 1 次） | Claude | B5 |
| B7 | 关系图激活：`society.py` 传播逻辑（trust/affection 随转述互动演化） | Claude | B5 |

#### B 批次架构细化（A2 第五批，2026-09-23——模块/文件级施工图）

**现状锚点（M2 已备）**：写侧唯一入口 `MemoryWritePipeline.write`（`sim/llm/memory_scan.py`，
banned+hidden 双扫，S1 守卫 CI 锁构造点）；读侧唯一入口 `memory.py::retrieve`（候选源
`iter_visible` → 批次 A 换向量候选）；治理列 `superseded_by/invalid_reason`（0003 迁移）；
`Knowledge`/`Relationship` 表已在 models.py（M3 解锁）；`HiddenState.evaluate → evaluate_triggers`
已产 triggered 集合（隐藏属性浮现窗）；每游戏日切点 `divmod(tick, TICKS_PER_GAME_DAY)`
（calendar.py:41，weather 已用同款判日切）。

**B-B1 传播 = 复制写（R6 落地，模块级）**
- 新模块 `sim/npc/propagation.py`（唯一新文件，行为链域）：
  `retell(from_npc, to_npc, hit: MemoryHit, *, tick, channel) -> MemoryEntry | None`。
- **实现即「读 A 可见 → 按证据链判定（B4）→ 在 B 侧走一次 write()」**：
  `MemoryWritePipeline.write(make_entry(npc_id=to_npc, source="dialogue", ...))`——
  B 的写入门（banned+hidden 扫描按 B 的 profile）自动生效，禁任何绕行构造。
- told 衰减在 `retell` 内计算 confidence/importance（codex 契约系数），**不改**
  `MemoryWritePipeline` 本体（扫描面零扩）。
- 挂载点：M3 对话/转述行为产生时（NPC_ACT 白名单扩「转述」动作时接）；本批先立模块+契约测试。
- R7 前置：S1 守卫测试扩一行——`grep` 断言仓内 MemoryEntry 构造只经 make_entry/Pipeline。

**B-B2 反思批处理（DESIGN §15「每游戏日 1 次」，挂载点）**
- **每日注入点**：新 `sim/npc/reflection.py::reflection_due(tick) -> bool`
  （`tick % TICKS_PER_GAME_DAY == 0` 判日切，与 weather 同款纯函数；由世界循环在固定执行序
  「事件结算后」调用——**不进每 tick 路径**，防呆红线同源）。
- 流水线：`gather(当日 source="event" 的可见记忆) → LLM 摘要（复用 reason 通道，零额外调用型）
  → write(source="reason")`。摘要产物是普通记忆条目，治理/检索/向量全链复用，无特例。
- LLM 缺位降级：无 profile/网络时跳过（与决策降级同口径，世界照转）。
- C5 确定性：反思走「事件驱动」而非墙钟——同事件流重放同反思（RNG 分桶：反思专用 stream key）。

**B-B3 society 激活顺序（`society.py` 新建，M2 只留了规划位）**
- 数据层：Relationship 表直用（`models.py:194`，双向两行，branch_id 主键列已有——B2 分支隔离自动覆盖）；
  新 `sim/core/persistence/relationship_store.py`（照 memory_store.py 惯例：纯 SQL、
  upsert 单行、无缓存层）。
- 演化规则（M3 最小集，防过度设计）：
  1. **转述互动**：retell 成功 → to_npc 对 from_npc 的 trust +δ（δ 常量起步，M4 再调）；
  2. **目击隐藏属性**：witnessed 判定成立 → fear +δ（trauma 关联）；
  3. **日常互动**：NPC_ACT 对话类动作 → affection 小幅漂移 + last_interaction 刷新。
- 激活顺序 = 依赖序：relationship_store（数据）→ retell 挂演化钩子（B-B1 完成后）→
  L1 效用读关系面（现 cognition.py 效用缝**不读关系**，M3 批次 D 才接入——**本批不碰效用链**）。
- 边界：不做关系推理（M2 架构稿 §3 原约束延续）；trust/affection/fear 不出感知帧（社会未知轴）。

**B 批次文件清单（预估）**
| 文件 | 动作 | 域 |
|---|---|---|
| `sim/npc/propagation.py` | 新建 | Claude |
| `sim/npc/reflection.py` | 新建 | Claude |
| `sim/npc/society.py` | 新建 | Claude |
| `sim/core/persistence/relationship_store.py` | 新建 | opencode |
| `sim/core/persistence/memory_store.py` | 扩（B1 双列口径 + B2 branch 过滤） | opencode |
| `sim/core/persistence/models.py` | 扩（B3 knowledge 治理列，schema 提案制） | opencode |
| `sim/npc/memory.py` | 扩（候选源换向量，A4 联动） | opencode |
| `sim/tests/test_m3_propagation.py` 等 | 新建（含 codex §8 七钉子） | 共建 |

**B 批次前置裁决**：B1 双列口径（Claude 裁，取「任一非空即不可见」——检索端收紧优先）；
E1 事件（npc.hidden_emerge）与 knowledge 五列扩展（codex M3-S2 提案，opencode B3 合并评审）。

### 批次 C — 可变地图底座（opencode）

| # | 工作项 | 域 |
|---|---|---|
| C1 | `materialize_matter()` 快照路径实现（§19 契约照抄） | opencode |
| C2 | 重放路径 + 两入口逐位相等校验测试（§19.3） | opencode |
| C3 | chunk 失效正确性（24 钉子）+ §19.4 注册持久化（`MATTER_BUILD` 立账事件 + 9 钉子） | opencode |
| C4 | MatterPayload 域约束实现（codex C2 钉子转绿：Field(ge/le) + allow_inf_nan=False） | opencode |

### 批次 D — 社会面收束（Claude）

| # | 工作项 | 域 |
|---|---|---|
| D1 | 不成文规矩 v0（知识表 → 行为约束的最小通路） | Claude |
| D2 | 空间迷雾（区块迷雾最廉价未知，DESIGN §14 未知四轴） | Claude |
| D3 | 「NPC 记得且会转述」端到端验收场景（T5 golden 雏形） | Claude + codex 出探针 |

## 4. 安规钉子清单（横切，随批次转绿）

| 钉子 | 来源 | 随批次 | 状态 |
|---|---|---|---|
| R2 vec 治理过滤 | codex M3-S1 ① | A4 | 🟢 `test_t1_m3_vec_governance.py` |
| C2 MatterPayload 域约束 | codex M3-S1 ② | C4 | 🟢 `test_t1_m3_matter_bounds.py` |
| R1 knowledge 级联 | m3-preplan §4.1 | B3 | 🟢 `test_t1_m3_knowledge_cascade.py` |
| R4 分支隔离 | §4.1 | B2 | 🟢 knowledge 侧 `test_t1_m3_knowledge_cascade.py`；记忆侧 `test_memory_store.py::TestBranchIsolationMemorySide`（S6 F-b 补） |
| X2/X3 breakdown 死路 | §4.1 | B5 | 🟢 `test_t1_m3_breakdown_deadend.py`（S6 F-a 补） |
| R3 双列口径 | §4.1 | B1 裁决后 | 🟢 `test_memory_store.py`（双列任一非空即不可见） |

X5 触发词面扩面走 CR（新叙事文本与 trigger 词面交叉审查，词面变更纪律同 self-unknown §7）。

## 5. M3 验收对照（DESIGN §17 逐条）

| 量化验收 | 落点 |
|---|---|
| **NPC 记得且会转述** | 批次 A（记得=向量检索）+ 批次 B（转述=R6 复制写）+ D3 端到端场景 |
| **chunk 失效正确** | 批次 C3 |
| T1 六类不变量扩展 | 钉子清单全绿 + S4 10k harness 零回归（m3-preplan §4） |

## 6. 待裁决队列（本文维护，裁决后移入各域预稿）

| # | 项 | 提案域 | 状态 |
|---|---|---|---|
| V2 | embedding 维度 384/768 | opencode | 挂 M3（随 A1 定） |
| V3 | embedding profile 缝 | opencode | **M3 首批提案**（A1） |
| V5 | 召回时机（每 tick/按需/批量窗口） | opencode + pi | 挂 M3（A5 bench 数据后裁） |
| V7 | embedding 挂写路径（S1 边界） | opencode | **M3 首批提案**（codex 复核前置） |
| R3 | invalid_reason 双列口径 | codex 建议 | **M3 首批提案**（B1） |
| §19.4 | 注册持久化（register 事件 vs structures 表） | opencode | **已裁决（§6 全采主张）**：采 A（register 返回 MATTER_BUILD 立账事件）、structures M3 不建、x/y 默认 -1；实施放行 opencode（C3 后续件） |

## 7. 与第六轮任务单的衔接

- codex M3-S1（两枚 RED 钉子）= 本文 §4 前两行，**M3 第一个 PR 之前的门**。
- opencode M2-D6（裁决栏落档）= 裁 3 的文档化，先于批次 A。
- kilo M5-K1（anchors 预研）独立并行，产出进 M5 不进 M3。
