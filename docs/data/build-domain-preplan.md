# M4-D1 建造域数据面预研（提案制）

> 数据域（opencode），M4-D1，2026-09-25。**本文只出提案，不写 `models.py`、不出迁移、不改事件实现。**
> 依据：`DESIGN.md` §6/§14/§16、`docs/data/schema.md` §9/§14/§17/§19、
> `docs/data/migration.md` §4.9/§6.2、`docs/security/m3-preplan.md` §2 C1–C13、
> `docs/data/matter-register-proposal.md` §3/§6、`sim/core/events.py`、
> `sim/world/matter.py`、`sim/core/persistence/{models,npc_store,store}.py`。
> 既有裁决作为输入：**事件是熵态真相，structures 只做拓扑投影，不作注册直写路径。**

## 0. 结论摘要

1. **structures**：保留 `tiles/kind/material/owner_id/built_by/built_at/load_bearing/supported_by`；
   新增拓扑生命周期投影（如 `phase`）。移除 `integrity/quality/decay_rate/is_rubble` 等熵态列，
   避免与 `matter_state` 形成双真相。`material` 是结构组成元数据，不是库存数量。
2. **建造事件**：`TILE_CHANGED` 只做地图瓦片派生变化；`MATTER_*` 只做物质熵态变化；
   建造/拆除/坍塌新增小型类型化 structure 事件族，避免把施工进度塞进 `MATTER_BUILD.amount`。
3. **推进粒度**：不采用每 tick 事件。采用「开始事件 + 有界阶段 checkpoint + 终态事件」；
   tick 间由确定性纯函数推进，checkpoint 携带累计状态和规则版本，支持无 checkpoint 尾部重算。
4. **承重图**：M4 不建 SQL 边表；从 structures 投影物化内存正向/反向图，按稳定排序遍历。
   环、悬空引用、重复边、跨分支支撑在领域校验层拒绝。
5. **材料守恒**：新增结构化 `MATERIAL_MOVED`（来源→去向、数量、原因）事件；
   库存扣减、结构落成、拓扑投影同事务/同事件批次。不得复用 `MATTER_BUILD.amount` 表示材料数量。
6. **必须先裁**：事件族形状、checkpoint 频率/尾部重算、结构 id 分支作用域、
   topology phase 与 rubble 保留方式、材料事件与库存投影、支撑变化规则。

## 1. 现状与问题边界

### 1.1 已有 structures 草案

`docs/data/schema.md:239-261` 与 `docs/data/migration.md:313-336,563-599` 的草案包含：

- `id/branch_id/tiles/kind/material`；
- `integrity/quality/load_bearing/supported_by`；
- `owner_id/built_by/built_at`；
- branch 与 owner 索引。

现实是：仓库没有 `Structure` ORM、structures 实际迁移、投影、读路径或重放器；
当前迁移头是 `0005_m3_knowledge_governance`。`matter_state` 已有
`material/quality/load_bearing/supported_by` 等占位列，但当前 matter 物化不读取它们。

### 1.2 事件与投影现实

- `MATTER_BUILD/DAMAGE/DECAY/COLLAPSE` 共用 `MatterPayload`；`amount` 不是材料数量，
  `_project_matter` 以 `durability` 折叠 integrity。
- `TILE_CHANGED` 只有 `x/y/tile_id`，不能表达结构身份、tiles、承重、材料或进度。
- 生产 `flush_events` 只落 events，不投影 `matter_state`；快照路径需要 `NpcStore.flush_tick`。
- `structures` 草案复制 matter 熵态列，与「事件=熵态真相、structures=拓扑投影」的裁决倾向冲突。
- 事件枚举是冻结基线，只能追加；新增 kind 必须同步 `PAYLOAD_MODELS` 与校验测试。

**待裁点**：structures 是纯当前拓扑，还是保留历史 tombstone；`quality` 是否仍由 matter 投影承载。

## 2. structures 表结构提案

### 2.1 角色边界

| 数据 | 真相源 | structures 角色 |
|---|---|---|
| integrity / decay_rate / is_rubble | `MATTER_*` 事件 → `matter_state` | 不存、不更新 |
| quality / 建构期衰减影响 | 结构事件 + matter 投影（若纳入熵态） | 不作第二份质量真相 |
| tiles / kind / material / owner | structure 事件 | 当前拓扑投影 |
| load_bearing / supported_by | structure 事件 | 当前承重拓扑投影 |
| phase / built_by / built_at | structure 事件 | 生命周期/来源投影 |
| 资源数量与库存余额 | `MATERIAL_MOVED` 事件 → 资源投影 | 不存 recipe 数量 |

### 2.2 建议列

| 列 | 类型/约束 | 语义 | 备注 |
|---|---|---|---|
| `branch_id` | TEXT NOT NULL | 分支隔离 | 所有读写必带 |
| `structure_id` | TEXT NOT NULL | 稳定结构 id | 草案 `id` 建议改名，避免与 `matter_state.subject_id` 混淆；建议与 `(branch_id, structure_id)` 复合主键 |
| `tiles` | TEXT NOT NULL | JSON `[[x,y], ...]` | 事件校验形状；非 SQL JSON 查询索引 |
| `kind` | TEXT NOT NULL | 结构类型 | 受控枚举/注册表，不接收任意词面 |
| `material` | TEXT NOT NULL | 组成材料 | 静态拓扑，不是数量 |
| `phase` | TEXT NOT NULL | `planned/building/active/collapsing` | rubble 终态由 matter 承载；渲染层再映射协议 phase |
| `load_bearing` | BOOLEAN NOT NULL | 是否承重 | 拓扑标记 |
| `supported_by` | TEXT NOT NULL DEFAULT `'[]'` | 支撑 id JSON 数组 | 同 branch、无环由领域校验 |
| `owner_id` | TEXT NULL | 所有者 | 拓扑/权限元数据 |
| `built_by` | TEXT NULL | 建造者 | 服务端生成的 provenance |
| `built_at` | INTEGER NULL | 建成 tick | 非墙钟时间 |
| `created_at` / `updated_at` | REAL | 投影维护时间 | 辅助字段，不参与游戏重放 |

**移出 structures**：`integrity`、`quality`、`decay_rate`、`is_rubble`。
这些值必须从 `matter_state` 物化；若 quality 影响衰减，应在事件与 matter 投影中明确承载，
不能靠 structures 旁路更新。

### 2.3 主键、索引与完整性

- 建议主键：`(branch_id, structure_id)`，与事件 `(branch_id, seq)` 的隔离纪律一致。
- 建议索引：`(branch_id, owner_id)`；`(branch_id, phase)` 可在有施工看板查询后增加。
- 不建 `supported_by` JSON 索引、tile JSON 索引、外键级联删除；M4 查询规模不足，且会引入
  SQLite JSON/跨分支外键复杂度。
- JSON 形状、同分支存在性、无环、无重复支撑、tile 不重叠属于事件/领域校验，不伪装成普通 CHECK。
- 当前 `matter_state` 仍以全局 `subject_id` 为主键；若 structures 改为复合主键，必须在同一轮
  身份迁移中解决两表映射，不能只改 structures 假装分支安全。

**待裁点**：
1. 是否接受 `(branch_id, structure_id)` 复合主键并同步修正 matter identity；
2. rubble 是删除 structures 活跃行，还是保留 `phase=rubble` tombstone；
3. `phase` 是否进入表，还是完全由事件重放计算；
4. `material` 是否允许多材料数组（当前草案是单字符串）。

## 3. 建造事件流取舍

### 3.1 三类现有事件的职责

| 事件 | M4 职责 | 不负责 |
|---|---|---|
| `TILE_CHANGED` | 地图/碰撞瓦片的派生变化；驱动 chunk 失效 | 结构身份、进度、质量、材料、承重 |
| `MATTER_BUILD/DAMAGE/DECAY/COLLAPSE` | 物质熵态 delta；更新 matter_state | 施工计划、tiles、资源转移 |
| 新 structure kind | 建造/拆除/坍塌领域真相与投影输入 | 直接写表、直接改地图 |

`TILE_CHANGED` 可由结构事件在同一事务后派生；不能只靠它重建 structures，因为它没有
`structure_id` 与拓扑元数据。反过来，结构事件也不能替代 tile delta，因为寻路缓存需要坐标。

### 3.2 推荐事件族

建议追加小型、类型化事件（名称可在裁决时调整）：

| kind | 必需 payload 语义 | 投影 |
|---|---|---|
| `STRUCTURE_BUILD_STARTED` | structure_id、tiles、kind、material、owner/built_by、recipe_id/version、planned_duration、load_bearing、supported_by、build_rule_version、rng/外部输入引用 | 建 structures `planned/building` 行；预留 tiles；校验拓扑 |
| `STRUCTURE_BUILD_CHECKPOINT` | structure_id、progress、quality、integrity、phase、累计材料消耗、累计 RNG/规则版本 | 更新当前结构投影与 matter 投影；不写 tile 占用（除明确规则） |
| `STRUCTURE_BUILD_COMPLETED` | structure_id、最终 progress/quality/integrity、最终材料消耗、built_at、支撑快照 | structures 转 active；matter 转终态；派生 TILE_CHANGED |
| `STRUCTURE_DEMOLISHED` | structure_id、原因、回收材料转移引用、终态 tick | 删除/标记拓扑；派生 tile 恢复；关联资源回收 |
| `STRUCTURE_COLLAPSED` | structure_id、cause（decay/damage/support_lost）、support path/parent、终态 integrity | 删除/标记拓扑；matter rubble；逐对象派生坍塌事件 |
| `MATERIAL_MOVED` | transfer_id、material_id、quantity>0、from/to ref、reason、structure_id | 资源账本/库存余额投影；与结构事件同批 |

`STRUCTURE_COLLAPSED` 与现有 `MATTER_COLLAPSE` 的最终取舍待裁：推荐保留结构领域事件，
由投影同时写 matter rubble，避免把 `cause/support path` 塞进 `note`；若裁决要求少 kind，
则必须给 `MATTER_COLLAPSE` 增加结构化 cause 字段并同步所有消费者。

### 3.3 施工/拆除/坍塌的映射

- **施工**：`BUILD_STARTED` → 若干 `BUILD_CHECKPOINT` → `BUILD_COMPLETED`。
- **拆除**：`DEMOLISHED` 是显式终态；若拆除也需要多 tick，使用同构 checkpoint 或复用 started/checkpoint。
- **坍塌**：图遍历产生每个受影响结构的 `STRUCTURE_COLLAPSED`，不能只发一个全图事件。
- **地图变化**：完成/拆除/坍塌按 tile 派生 `TILE_CHANGED`；施工中的预留是否阻断寻路另裁。
- **matter delta**：物理完整度变化可伴随 `MATTER_BUILD/DAMAGE`，但不承担施工计划字段。

**待裁点**：新 kind 数量是否过多；`STRUCTURE_COLLAPSED` 是否替代/包裹 `MATTER_COLLAPSE`；
`note` 是否完全从建造事件删除；结构事件是否允许一个 payload 多 tiles（建议允许）。

## 4. 施工推进语义：每 tick 事件 vs 阶段快照

### 4.1 方案比较

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A 每 tick delta 事件 | 最直观；任意 tick 可直接重放 | 一木棚一游戏日约 86,400 tick，事件量、flush、索引成本极高 | 不推荐 |
| B 只发阶段完成事件 | 事件少、审计清晰 | 中途进度丢失；质量/技能/天气/疲劳的中间结果无法恢复 | 不可单独采用 |
| C 确定性推进 + 有界 checkpoint + 终态 | 兼顾可恢复性、事件量、终态清晰 | 需固定 build rule version 与尾部重算契约 | **推荐** |

### 4.2 推荐语义

1. `BUILD_STARTED` 固化 recipe、计划时长、规则版本与所有影响推进的输入/RNG 引用。
2. tick 间推进是纯函数：`advance(state, target_tick) -> state`，禁止读墙上时间、容器 hash 序或未记录 RNG。
3. 按固定 cadence（建议每游戏日或显式 stage boundary，不按每 tick）写 `BUILD_CHECKPOINT`；
   checkpoint 必须携带累计 progress/quality/integrity/材料消耗，而非 delta。
4. 读档时取最近 checkpoint；若目标 tick 在 checkpoint 之后，用同一 `build_rule_version` 的纯函数
   重算尾部；重算结果必须与下一个 checkpoint 逐位相等。
5. 完成/失败/取消写终态事件；rubble 不可逆。
6. 预留 tiles 是否在 `building` 阶段阻断新建或寻路，需单独裁决；不能从 `phase` 隐式猜。

### 4.3 checkpoint 频率

- 不按现实帧或 WebSocket flush 次数定义；按游戏 tick 的固定边界定义。
- cadence 需进入 recipe/build rule version；改 cadence 必须产生新规则版本或迁移策略。
- 若性能实测显示 checkpoint 仍过大，可改为 stage boundary，但仍不得退回“只终态”。
- progress/quality 不是 `structures` 的第二真相：结构事件是真相，表只投影当前值。

**待裁点**：cadence（日/阶段/固定 tick）；失败是低 quality 还是独立 `BUILD_FAILED`；
取消/退款事件形状；无 checkpoint 尾部的重算上限与版本淘汰策略。

## 5. 承重依赖图

### 5.1 M4 表示：拓扑 JSON + 内存图

`structures.supported_by` 保留 JSON 数组；从当前分支 structures 投影一次批量物化：

```text
nodes: structure_id -> {phase, load_bearing, supported_by}
dependents: support_id -> sorted[dependent_id]
```

坍塌时在内存图上按 `(structure_id, tile, kind)` 稳定排序遍历；每个实际受影响对象产生一次
collapse 事件。`visited` 集合防重复；环在建造/支撑变更时被拒绝，不依赖 visited 兜底成为常态。

### 5.2 为什么暂不建 SQL 边表

- 当前单地图、MVP 结构规模与 MatterLedger 物化模式相容；
- 草案已经选择 `supported_by` JSON，M4 暂无跨结构图查询或 SQL 级反向依赖需求；
- 内存图可在一个事务投影批次后构建，遍历顺序可控，避免 SQLite JSON 递归查询；
- 事件重放仍能从 support edge 事件恢复图，表只是当前投影。

### 5.3 图不变量

1. edge 两端必须同 branch；support id 必须存在。
2. 禁止 self-edge、重复 edge、环；支撑对象必须满足 `load_bearing=true`（待裁）。
3. 只有 active/collapsing 结构可作为当前承重节点；planned/building 是否可支撑待裁。
4. 失去支撑时，级联顺序固定；一个对象在同一坍塌因果链最多一个终态事件。
5. topology 变化若不改变 tile 占用，不自动触发 chunk 失效；若改变占用，必须派生 TILE_CHANGED。
6. `structures` 行的删除/tombstone 与 matter rubble 语义必须固定，不能一域删一域留。

**待裁点**：支撑边是否可修改；planned 是否可承重；失去全部支撑是立即坍塌还是 quality 降级；
环/悬空边是 reject 整次事件还是跳过坏边；何时升级独立 `structure_edges` 表
（建议触发器：需要 SQL 反向依赖查询、规模压测超预算、或频繁图更新无法批量物化）。

## 6. 材料守恒与资源事件

### 6.1 不变量

对每种 material：

```text
after_total = before_total + known_sources - known_sinks
```

建造完成的专用断言：

```text
after_total = before_total - recipe.cost
```

拒绝、取消、拆除回收也必须各自产生可审计的相反方向转移；失败事务不得留下半扣或半建。

### 6.2 推荐 `MATERIAL_MOVED`

不复用 `MATTER_BUILD.amount`、自由文本 `note` 或 `npc_profiles.inventory` JSON 旁路。
事件至少表达：

- `transfer_id`、`material_id`、`quantity>0`；
- `from_ref/from_kind`、`to_ref/to_kind`；
- `reason`：`build_reserved/build_consumed/build_refunded/demolish_yield/...`；
- `structure_id`、`recipe_id/recipe_version`（若与建造关联）。

库存/世界物资/结构组成之间用显式来源和去向表达转移，避免“只扣库存”无法证明材料去了哪里。
资源余额可由事件重放；若需要快速查询，另建 `material_balances`/`material_ledger` 投影，
不能把它塞进 structures。

### 6.3 原子批次

`MATERIAL_MOVED`、结构 started/completed/collapsed、structures 投影、matter 投影、
资源投影必须在同一 `NpcStore.flush_tick` 事务批次；任一校验失败整批回滚。
当前生产 `flush_events` 无投影，M4 接线必须显式选择投影 flush 路径。

**待裁点**：材料 reservation 时机（命令接受/开始/阶段完成）；库存真相表；
拆除回收比例；quantity 单位与小数精度；同一 transfer 的幂等/重试策略。

## 7. C1–C13 输入面映射

| 清单 | M4 落点 | 施工 | 拆除 | 坍塌 |
|---|---|---|---|---|
| C1 kind 登记 | 每类新 kind 同步 `PAYLOAD_MODELS`、工厂、校验 | started/checkpoint/completed | demolished | collapsed |
| C2 数值域 | progress/quality/integrity/quantity 有限且有界；坐标 strict int | payload + store | payload + store | cause/path 校验 |
| C3 bool 冒充 int | `tiles` 坐标、tick、quantity 禁 bool | server gate | server gate | server gate |
| C4 服务端裁决 | 配方、地块、权限、材料、支撑由服务端判 | validate before emit | validate before emit | graph/domain rule |
| C5 标识符 | structure/material/recipe/transfer id 限长与字符集 | factory | factory | factory |
| C6 主体权限 | actor/owner 服务端生成；客户端不可伪造 | WS control | WS control | NPC/system event |
| C7 note 字面 | 建造域不接自由 note；原因用枚举 cause | reject raw note | reject raw note | cause enum |
| C8 频控 | build 控制消息、事件批量与 tick cadence 均限频 | control | control | cascade budget |
| C9 结构化错误 | code/ref/message 返回，不静默丢 | WS error | WS error | event/replay error |
| C10 坏帧 | JSON/字段解析失败安全 error，不打断接收循环 | WS | WS | N/A |
| C11 重放一致 | 事件唯一写路；两投影同源折叠 | checkpoint replay | event replay | graph replay |
| C12 材料守恒 | transfer + structure 同批事务 | consumed/refund | yield | rubble material sink |
| C13 通道纪律 | build 只走 control；render/narrative 只读投影 | input→event | input→event | output event |

## 8. 建议实施顺序（裁决后）

1. 先裁事件族与 payload；追加 C1/C2/C3/C5/C7 单元钉子。
2. 再裁 structures 身份/phase/rubble；出 migration 草案与 branch identity 对账。
3. 实现 build checkpoint 纯函数与 replay 逐位相等测试；不先接 UI。
4. 实现内存承重图、无环/同分支/确定性级联测试。
5. 实现 `MATERIAL_MOVED` 与同事务回滚/守恒测试。
6. 最后接 `TILE_CHANGED` 派生、chunk 失效、WS control；render/narrative 仍只读投影。

## 9. 待裁点汇总

1. 新 structure kind 的最小集合与 `STRUCTURE_COLLAPSED`/`MATTER_COLLAPSE` 关系。
2. checkpoint cadence、build rule version、尾部重算和规则淘汰。
3. structures 复合主键与 matter_state 分支身份是否同轮修正。
4. `phase` 是否入表；rubble 删除/tombstone；planned 是否占用/承重。
5. `quality` 的事件承载与 matter 投影；多材料结构形状。
6. 内存承重图验收规模与升级 `structure_edges` 的触发器。
7. `MATERIAL_MOVED` 的 reservation 时机、库存投影与幂等键。

**本提案提交后不改代码；待 Claude 裁决上述 7 点，再进入 M4-D2 施工。**
