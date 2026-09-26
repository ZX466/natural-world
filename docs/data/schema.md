# SQLite Schema 设计

> 对齐 DESIGN.md §6 核心数据契约 + §12 双轨存档 + §19 禁止事项（`apply(event)` 为唯一写路径）。
> 技术栈：SQLAlchemy 2.0 async + aiosqlite + sqlite-vec。

---

## 1. events（事件日志 — append-only 世界档）

唯一写路径：`apply(event)` → INSERT INTO events。禁止 UPDATE/DELETE。

| 字段 | 类型 | 约束 | 说明 | 对齐 |
|------|------|------|------|------|
| `branch_id` | TEXT | NOT NULL | 所属世界线分支 | §6 WorldEvent.branch_id |
| `seq` | INTEGER | NOT NULL | 分支内单调递增序列号 | §6 WorldEvent.seq |
| `tick` | INTEGER | NOT NULL | 事件发生的游戏 tick | §6 WorldEvent.tick |
| `event_type` | TEXT | NOT NULL | 事件类型（move_to / talk_to / take / ...） | §6 WorldEvent.kind |
| `actor_id` | TEXT | NOT NULL | 事件发起者 entity_id | §6 WorldEvent.actor_id |
| `target_id` | TEXT | NULL | 事件目标 entity_id | §6 WorldEvent.target_id |
| `parent_seq` | INTEGER | NULL | 父事件 seq（因果链） | §6 WorldEvent.parent_seq |
| `payload` | TEXT | NOT NULL | JSON 序列化的事件参数 | §6 WorldEvent.payload |
| `witnesses` | TEXT | NOT NULL | JSON 数组：见证者 entity_id 列表 | §6 WorldEvent.witnesses |
| `entropy_ref` | TEXT | NULL | 熵注入记录引用（inject 时写入） | §11 混合熵 |
| `created_at` | REAL | NOT NULL DEFAULT (unixepoch('now','subsec')) | 客观时间戳（调试用，不进入游戏） | — |

**主键**：`(branch_id, seq)` — 复合主键，分支内唯一。

**索引**：
- `idx_events_branch_tick` ON `(branch_id, tick)` — 按 tick 范围查询（快照后重放）
- `idx_events_actor` ON `(branch_id, actor_id)` — 按角色查询事件
- `idx_events_type` ON `(branch_id, event_type)` — 按类型筛选

**约束**：
- `seq` 在分支内单调递增（应用层保证，SQLite 无 rowid 冲突）
- `payload` 必须为合法 JSON（CHECK 约束或应用层校验）
- 禁止 UPDATE/DELETE（ORM 层不暴露更新接口，只 append）

---

## 2. branches（世界线分支）

| 字段 | 类型 | 约束 | 说明 | 对齐 |
|------|------|------|------|------|
| `id` | TEXT | PRIMARY KEY | 分支 UUID | §6 Branch.id |
| `forked_from_branch` | TEXT | NULL | 父分支 id | §6 Branch.forked_from |
| `forked_from_seq` | INTEGER | NULL | 分叉点 seq | §6 Branch.forked_from |
| `status` | TEXT | NOT NULL DEFAULT 'active' | active / abandoned | §6 Branch.status |
| `created_at` | REAL | NOT NULL DEFAULT (unixepoch('now','subsec')) | 创建时间 | — |
| `abandoned_at` | REAL | NULL | 废弃时间（status=abandoned 时填充） | §12 双轨存档 |

**索引**：
- `idx_branches_status` ON `(status)` — 查询活跃分支

**约束**：
- `forked_from_seq` 为 NULL 当且仅当 `forked_from_branch` 为 NULL（根分支）
- 废弃分支不可重新激活（应用层保证）

---

## 3. snapshots（快照 — 冷热分层）

§12 v2.1：每 1000 tick 全量快照，gzip 压缩。同分支仅保留最近 8 份热快照 + 每日首快照；abandoned 分支整体冷归档。

| 字段 | 类型 | 约束 | 说明 | 对齐 |
|------|------|------|------|------|
| `branch_id` | TEXT | NOT NULL | 所属分支 | §12 快照 |
| `seq` | INTEGER | NOT NULL | 快照点的事件序列号 | §12 快照 |
| `tick` | INTEGER | NOT NULL | 快照点的游戏 tick | §12 快照 |
| `snapshot_data` | BLOB | NOT NULL | gzip 压缩的全量状态 JSON | §12 体积治理 |
| `is_cold` | INTEGER | NOT NULL DEFAULT 0 | 0=热存储 1=冷归档 | §12 冷热分层 |
| `created_at` | REAL | NOT NULL DEFAULT (unixepoch('now','subsec')) | — | — |

**主键**：`(branch_id, seq)` — 每个快照点唯一。

**索引**：
- `idx_snapshots_branch_tick` ON `(branch_id, tick)` — 读档时定位最近快照
- `idx_snapshots_cold` ON `(is_cold)` — 冷归档查询

**快照内容结构**（snapshot_data 解压后）：
```json
{
  "tick": 1000,
  "entities": { "<entity_id>": { ... 全量状态 ... } },
  "map_version": 0,
  "relationships": [ ... ],
  "knowledge": [ ... ],
  "structures": [ ... ]
}
```

**体积预估**（§12）：单份 ≤5MB（gzip 后），每 1000 tick → 每游戏日 86 份 → 约 430MB。治理后稳态 <2GB。

---

## 4. player_anchors（玩家档 — 游标）

§12：玩家档只是游标 + agent_override，不是世界状态副本。读档 = 分叉。

| 字段 | 类型 | 约束 | 说明 | 对齐 |
|------|------|------|------|------|
| `id` | TEXT | PRIMARY KEY | anchor UUID | §6 PlayerAnchor.id |
| `name` | TEXT | NOT NULL | 玩家命名的存档名 | §6 PlayerAnchor.name |
| `branch_id` | TEXT | NOT NULL | 当前所在分支 | §6 PlayerAnchor.branch_id |
| `tick` | INTEGER | NOT NULL | 游标 tick | §6 PlayerAnchor.tick |
| `seq` | INTEGER | NOT NULL | 游标 seq | §6 PlayerAnchor.seq |
| `agent_override` | TEXT | NOT NULL DEFAULT '{}' | JSON：Agent 身体/物品/位置覆盖 | §6 PlayerAnchor.agent_override |
| `created_at` | REAL | NOT NULL DEFAULT (unixepoch('now','subsec')) | — | — |
| `updated_at` | REAL | NOT NULL DEFAULT (unixepoch('now','subsec')) | — | — |

**索引**：
- `idx_anchors_branch` ON `(branch_id)` — 按分支查询 anchors

**读档流程**（§12）：
1. 定位 anchor → (branch_id, seq)
2. 找最近快照（tick ≤ anchor.tick）
3. 从快照重放事件到 anchor.tick
4. 应用 agent_override
5. 创建新分支（forked_from = 当前分支+seq）
6. 旧分支标记 abandoned

---

## 5. npc_memories（NPC 记忆表）

§6 MemoryEntry：第一人称叙事记忆，带重要性、情绪标签、扭曲度。M3 启用。

| 字段 | 类型 | 约束 | 说明 | 对齐 |
|------|------|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增 ID | — |
| `npc_id` | TEXT | NOT NULL | 记忆持有者 | §6 MemoryEntry.npc_id |
| `event_seq` | INTEGER | NULL | 关联事件 seq（NULL = 推理/转述） | §6 MemoryEntry.event_seq |
| `branch_id` | TEXT | NOT NULL | 所属分支 | — |
| `content` | TEXT | NOT NULL | 第一人称叙事内容 | §6 MemoryEntry.content |
| `importance` | REAL | NOT NULL | 0.0–1.0，决定衰减速率与检索权重 | §6 MemoryEntry.importance |
| `emotion_tag` | TEXT | NULL | 情绪标签（用于一致性检索） | §6 MemoryEntry.emotion_tag |
| `distortion` | REAL | NOT NULL DEFAULT 0.0 | 被情绪扭曲程度 | §6 MemoryEntry.distortion |
| `embedding` | BLOB | NULL | sqlite-vec 向量（M3 时填充） | §6 MemoryEntry.embedding |
| `created_at_tick` | INTEGER | NOT NULL | 创建时的游戏 tick | — |
| `last_accessed_tick` | INTEGER | NULL | 最后访问 tick（衰减计算用） | — |

**索引**：
- `idx_memories_npc` ON `(npc_id, branch_id)` — 按角色查询记忆
- `idx_memories_importance` ON `(npc_id, importance DESC)` — 重要性排序检索
- `idx_memories_event` ON `(branch_id, event_seq)` — 按事件关联查询

**约束**：
- `importance` 范围 0.0–1.0（应用层校验）
- `distortion` 范围 0.0–1.0（应用层校验）

---

## 6. npc_memory_vec（sqlite-vec 向量索引）

§6 MemoryEntry.embedding：向量检索用，M3 启用。独立表以支持 sqlite-vec 扩展。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `rowid` | INTEGER | PRIMARY KEY | 对应 npc_memories.id |
| `embedding` | FLOAT32[N] | NOT NULL | 向量（维度由 embedding model 决定） |

**使用方式**：
```sql
-- sqlite-vec 虚拟表
CREATE VIRTUAL TABLE npc_memory_vec USING vec0(
  embedding FLOAT32[N]
);
```

**注意**：sqlite-vec 要求固定维度。embedding model 选定后锁定维度（如 384 或 768）。

---

## 7. relationships（NPC 关系）

§6 Relationship：有向不对称关系。双向存储（A→B 和 B→A 各一行）。

| 字段 | 类型 | 约束 | 说明 | 对齐 |
|------|------|------|------|------|
| `owner_id` | TEXT | NOT NULL | 关系持有者 | §6 Relationship.owner_id |
| `other_id` | TEXT | NOT NULL | 关系对象 | §6 Relationship.other_id |
| `trust` | REAL | NOT NULL DEFAULT 0.0 | 信任度 | §6 |
| `affection` | REAL | NOT NULL DEFAULT 0.0 | 好感度 | §6 |
| `fear` | REAL | NOT NULL DEFAULT 0.0 | 恐惧度 | §6 |
| `debt` | REAL | NOT NULL DEFAULT 0.0 | 人情债（正值=他欠我） | §6 |
| `face` | REAL | NOT NULL DEFAULT 0.0 | 面子往来 | §6 |
| `last_interaction` | INTEGER | NOT NULL DEFAULT 0 | 最后交互 tick | §6 |
| `branch_id` | TEXT | NOT NULL | 所属分支 | — |

**主键**：`(branch_id, owner_id, other_id)` — 分支内有向唯一。

**索引**：
- `idx_rel_owner` ON `(branch_id, owner_id)` — 查询某角色的所有关系
- `idx_rel_other` ON `(branch_id, other_id)` — 反向查询

---

## 8. knowledge（NPC 知识）

§6 KnowledgeItem：NPC 持有的事实性知识，带可信度和来源。

| 字段 | 类型 | 约束 | 说明 | 对齐 |
|------|------|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | — | — |
| `holder_id` | TEXT | NOT NULL | 知识持有者 | §6 KnowledgeItem.holder_id |
| `fact` | TEXT | NOT NULL | 知识内容 | §6 |
| `confidence` | REAL | NOT NULL | 0.0–1.0 可信度 | §6 |
| `source` | TEXT | NOT NULL | witnessed / told / inferred | §6 |
| `learned_at` | INTEGER | NOT NULL | 学习时的 tick | §6 |
| `branch_id` | TEXT | NOT NULL | 所属分支 | — |
| `subject_npc_id` | TEXT | NULL | 他人属性知识的主体 npc_id；自身事实知识为 NULL | evidence-chain §5 |
| `subject_attr_id` | TEXT | NULL | 属性主键（戏外）；自身事实知识为 NULL | evidence-chain §5 |
| `evidence_seq` | INTEGER | NULL | witnessed：锚定的 `npc.hidden_emerge` 事件 seq（持久层分配后经 `seq_by_index` 投影缝回填） | evidence-chain §5 |
| `source_knowledge_id` | INTEGER | NULL | told：teller 的 knowledge 行 id（told 链回溯键 = 级联递归索引起点） | evidence-chain §5 |
| `source_memory` | TEXT | NULL | 派生源记忆 `npc_memories.entry_id`（R1 级联起点） | m3-preplan §1 R1 |
| `invalidated` | BOOLEAN | NOT NULL DEFAULT 0 | 失效位（0=有效）；**独立位而非 `superseded_by`**——knowledge 无「替代行」语义 | evidence-chain §6 |
| `invalid_reason` | TEXT | NULL | 失效原因（结构化串，不含 LLM 原文/词面） | 同 `npc_memories` |

**约束**（CHECK，`0005_m3_knowledge_governance`）：
- `ck_knowledge_source`：`source` IN ('witnessed', 'told', 'inferred')
- `ck_knowledge_confidence`：`confidence` 范围 0.0–1.0
- `ck_knowledge_subject_pair`：`(subject_npc_id IS NULL) = (subject_attr_id IS NULL)`（成对）

**应用层形态约束**（proposal §2.2「软约束」，由 `KnowledgeStore.write_fact` 把关，DB CHECK 表达力不及）：
- `witnessed` ⇒ `evidence_seq IS NOT NULL` 且 `subject_npc_id IS NOT NULL`；
- `told` ⇒ `source_knowledge_id IS NOT NULL`（自我披露链根 `subject_npc_id == holder_id` 例外）；
- `fact` 必过写入门（`MemoryWritePipeline.scan_fact`，X7：banned 词面 + 未触发隐藏属性直陈 → 拒收不落库；可映射命中落改写后文本）。

**索引**：
- `idx_knowledge_holder` ON `(branch_id, holder_id)` — 按角色查询知识
- `idx_knowledge_source` ON `(branch_id, source)` — 按来源筛选
- `idx_knowledge_source_memory` ON `(branch_id, source_memory)` — 源记忆 supersede → 反查派生知识（R1 级联起点）
- `idx_knowledge_source_kid` ON `(branch_id, source_knowledge_id)` — told 链向下递归（级联传播）
- `idx_knowledge_subject` ON `(branch_id, subject_npc_id, subject_attr_id)` — 按主体+属性查有效知识（evidence 判定 teller 行一致性）

**治理语义**（evidence-chain §6 终裁）：**继承失效、不继承替代**——源记忆 supersede → 派生 knowledge 行置 `invalidated=1` + `invalid_reason`，沿 `source_knowledge_id` 递归向下，无替代行（codex 预审①）。接口见 `sim/core/persistence/knowledge_store.py`：`invalidate_by_source(entry_id)` / `invalidate_by_row(row_id)`，分支隔离（R4）+ 幂等 + 可与源记忆 supersede 同事务。

---

## 9. structures（建筑/结构物 — M4-D2 已落地）

**当前拓扑与生命周期投影**；熵态真相仍在 §14 `matter_state`。迁移：
`0006_m4_structures`。复合主键允许同 `structure_id` 在不同分支共存。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `structure_id` | TEXT | PRIMARY KEY | 结构稳定 id（分支内唯一） |
| `branch_id` | TEXT | PRIMARY KEY, NOT NULL | 所属分支 |
| `tiles` | TEXT | NOT NULL | JSON 数组 `[[x,y], ...]` |
| `kind` | TEXT | NOT NULL | 结构类型 slug（木棚/石墙…） |
| `material` | TEXT | NOT NULL | 单材料 slug（M5 再议多材料） |
| `phase` | TEXT | NOT NULL DEFAULT 'building' | planned/building/active/collapsing/rubble |
| `load_bearing` | INTEGER | NOT NULL DEFAULT 0 | 是否承重；planned 不承重 |
| `supported_by` | TEXT | NOT NULL DEFAULT '[]' | JSON 支撑 id 数组（无环/同分支由领域校验） |
| `owner_id` | TEXT | NULL | 所有者 |
| `built_by` | TEXT | NULL | 建造者 |
| `built_at` | INTEGER | NULL | 建成 tick |
| `created_at` | REAL | NOT NULL | 投影维护时间 |

**不存**：`integrity/quality/decay_rate/is_rubble`（避免与 `matter_state` 双真相）。
坍塌保留 `phase=rubble` tombstone，不删行。

**索引**：
- `idx_struct_branch` ON `(branch_id)` — 按分支查询
- `idx_struct_owner` ON `(branch_id, owner_id)` — 按所有者查询
- `idx_struct_phase` ON `(branch_id, phase)` — 施工看板/生命周期筛选

**投影/重放（M4-D2b 已落地）**：
- `STRUCTURE_STARTED/CHECKPOINT/COMPLETED/COLLAPSED/REMOVED` 经
  `fold_structure_snapshot` 单折叠；投影与 `materialize_structures_replay` 共用，
  两入口逐位相等；
- phase 由事件种类推导：STARTED→building、COMPLETED→active、
  COLLAPSED→rubble（保留 tombstone）、REMOVED→删行；
- `NpcStore.materialize_structures` 为快照路径（一次 SELECT、分支隔离），
  `materialize_structures_replay` 为纯读重放路径；
- 施工推进纯函数在 `sim/world/structure.py`：每游戏日 checkpoint、
  `build_rule_version` 选规则，未知版本 fail-closed，尾部确定性重算。

**承重图与级联（M4-D2c 已落地）**：`sim/world/support_graph.py` 从本分支
`materialize_structures()` 结果一次物化内存正/反向图；同分支、悬空/自环/重复边、
环、planned/building 承重一律拒绝。级联游标按 id 稳定排序，每帧最多
`CASCADE_EVENT_BUDGET_PER_FRAME=100` 条 `STRUCTURE_COLLAPSED`，10k 节点验收规模
`SUPPORT_GRAPH_ACCEPTANCE_NODES=10000`；support_path 只记直接失去的支撑。

---

## 10. llm_profiles（LLM 配置档案）

§15 成本治理：api_key 用 Fernet 加密落库。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | TEXT | PRIMARY KEY | profile UUID |
| `name` | TEXT | NOT NULL | 显示名称 |
| `base_url` | TEXT | NOT NULL | API 端点 |
| `api_key_enc` | BLOB | NOT NULL | Fernet 加密的 API key |
| `model` | TEXT | NOT NULL | 模型名称 |
| `temperature` | REAL | NOT NULL DEFAULT 0.7 | — |
| `max_tokens` | INTEGER | NOT NULL DEFAULT 2048 | — |
| `is_active` | INTEGER | NOT NULL DEFAULT 0 | 当前活跃 profile |
| `created_at` | REAL | NOT NULL DEFAULT (unixepoch('now','subsec')) | — |

**约束**：
- 同一时间只有一个 `is_active = 1`（应用层保证）

---

## 11. entropy_log（熵日志 — 开发模式）

§11 混合熵：inject 时记录真随机值。仅开发模式存在。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | — |
| `stream` | TEXT | NOT NULL | 熵流名称 |
| `reason` | TEXT | NOT NULL | 注入原因 |
| `tick` | INTEGER | NOT NULL | 注入时 tick |
| `value` | TEXT | NOT NULL | 真随机值（十六进制） |
| `branch_id` | TEXT | NOT NULL | 所属分支 |

**注意**：生产环境可选保留或清空，不影响回放（回放用 events 中的 entropy_ref）。

---

## 12. npc_profiles（NPC 完整属性宽表 — M2）

§13 NPC 完整属性（身份 / 需求带权重 / OCEAN 人格 / PAD 情绪 / 技能树 / 目标 /
物品 / 知识边界）+ LOD。健康档单独见 §13 npc_health；关系/记忆/知识分别落
relationships / npc_memories / knowledge。迁移：`0004_m2_npc_attributes`。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | TEXT | PRIMARY KEY | NPC entity_id（稳定戏外主键） |
| `branch_id` | TEXT | NOT NULL | 所属分支 |
| `name` | TEXT | NOT NULL | 姓名 |
| `species` | TEXT | NOT NULL DEFAULT 'human' | human/cat/dog/raven（§7 物种级 profile） |
| `gender` | TEXT | NOT NULL DEFAULT 'unknown' | — |
| `age` | INTEGER | NOT NULL DEFAULT 0 | 年龄 |
| `occupation` | TEXT | NOT NULL DEFAULT '' | 身份/营生 |
| `identity_anchor` | TEXT | NOT NULL DEFAULT '' | 自述锚（prompt [身份锚]） |
| `ocean_openness` | INTEGER | NOT NULL DEFAULT 50 | OCEAN 开放性 0–100 |
| `ocean_conscientiousness` | INTEGER | NOT NULL DEFAULT 50 | 尽责性 |
| `ocean_extraversion` | INTEGER | NOT NULL DEFAULT 50 | 外向性 |
| `ocean_agreeableness` | INTEGER | NOT NULL DEFAULT 50 | 宜人性 |
| `ocean_neuroticism` | INTEGER | NOT NULL DEFAULT 50 | 神经质（陈默=75） |
| `pad_pleasure` | REAL | NOT NULL DEFAULT 0.0 | PAD 愉悦 −1..1 |
| `pad_arousal` | REAL | NOT NULL DEFAULT 0.0 | PAD 唤醒 |
| `pad_dominance` | REAL | NOT NULL DEFAULT 0.0 | PAD 支配 |
| `emotion_updated_tick` | INTEGER | NOT NULL DEFAULT 0 | 情绪最后更新 tick |
| `needs` | TEXT | NOT NULL DEFAULT '[]' | JSON：[{name,value,weight}] 需求带权重 |
| `skills` | TEXT | NOT NULL DEFAULT '{}' | JSON：{技能: 等级} |
| `goals` | TEXT | NOT NULL DEFAULT '{}' | JSON：{short,long} 目标 |
| `inventory` | TEXT | NOT NULL DEFAULT '[]' | JSON 物品列表 |
| `knowledge_boundary` | TEXT | NOT NULL DEFAULT '{}' | JSON：识字率/行话/阶层用语（§7 语言判定） |
| `lod` | INTEGER | NOT NULL DEFAULT 1 | LOD：0/1/2（§13 升降格） |
| `created_at_tick` | INTEGER | NOT NULL DEFAULT 0 | 出生 tick |
| `updated_at_tick` | INTEGER | NOT NULL DEFAULT 0 | 最后更新 tick |
| `created_at` | REAL | NOT NULL | 客观时间戳 |

**索引**：
- `idx_profiles_branch` ON `(branch_id)` — 按分支取全部 NPC
- `idx_profiles_branch_lod` ON `(branch_id, lod)` — L1 全量自转（50 NPC）按 LOD 取

**约束**：
- OCEAN 各维 0–100、PAD 各维 −1..1（应用层校验）
- JSON 列必须为合法 JSON（应用层校验，同 payload §1 纪律）

---

## 13. npc_health（NPC 健康档 + 隐藏标注 — M2）

§13 健康（疾病、旧伤、成瘾、残疾）+ §8 创伤应激。一行 = 一条健康属性。
隐藏属性为「自我未知」：默认不进任何 LLM/戏内输出面，仅情境触发命中才浮现。
字段与语义对齐 codex `sim/npc/hidden.py` 的 `HiddenAttribute` 与
`docs/security/self-unknown.md` §1/§6（方式 A：隐藏标注落在健康档）。
迁移：`0004_m2_npc_attributes`。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | — |
| `npc_id` | TEXT | NOT NULL | 持有者 entity_id |
| `branch_id` | TEXT | NOT NULL | 所属分支 |
| `category` | TEXT | NOT NULL | `disease`/`old_injury`/`addiction`/`disability`/`trauma` |
| `label` | TEXT | NOT NULL | 世界内指称（文档/调试用，本身也是直陈词面） |
| `severity` | REAL | NOT NULL DEFAULT 0.0 | 严重度 0.0–1.0（应用层校验） |
| `active` | INTEGER | NOT NULL DEFAULT 1 | 是否仍在作用 |
| `hidden` | INTEGER | NOT NULL DEFAULT 0 | 1=隐藏属性（自我未知），0=常显 |
| `descriptors` | TEXT | NOT NULL DEFAULT '[]' | JSON 数组：直陈词面（泄漏扫描面） |
| `trigger_conditions` | TEXT | NOT NULL DEFAULT '[]' | JSON 数组：情境触发关键词（命中→本 tick 浮现） |
| `notes` | TEXT | NULL | 备注 |
| `created_at_tick` | INTEGER | NOT NULL DEFAULT 0 | 形成 tick |
| `created_at` | REAL | NOT NULL | 客观时间戳 |

**索引**：
- `idx_health_npc` ON `(branch_id, npc_id)` — 取某 NPC 健康档
- `idx_health_hidden` ON `(branch_id, hidden)` — 区分常显/隐藏（装配默认过滤）
- `idx_health_category` ON `(branch_id, category)` — 按健康类别查询

**约束**：
- `category` IN 上述五值（应用层校验）
- `hidden = 1` 且未触发时：感知帧/独白/记忆检索默认结果均不得含其直陈词面（§16 自我未知）

---

## 14. matter_state（物质熵增状态 — M2）

§11 物质熵增 + §14 结构 integrity/quality（归零变 rubble 永不恢复）。
物质熵增是慢变量：可损耗对象随 tick 自发衰减（`integrity`↓、`decay_rate`），
施工/破坏/火灾改变其数值。本表只持久化「当前物质熵状态」，**每次变更仍由
events 流的 `tile_changed` / `matter.*` 事件驱动**（§19 禁止直接赋值；
§11 熵材料随事件落库）——快照 + 事件重放可逐位重建。

迁移：`0004_m2_npc_attributes` 建表；`0006_m4_structures` 将主键改为分支复合键。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `branch_id` | TEXT | PRIMARY KEY, NOT NULL | 所属分支 |
| `subject_id` | TEXT | PRIMARY KEY, NOT NULL | 对象稳定 id（分支内唯一） |
| `subject_kind` | TEXT | NOT NULL DEFAULT 'structure' | structure/item/terrain/natural |
| `material` | TEXT | NOT NULL DEFAULT '' | 材料（木/石/...） |
| `integrity` | REAL | NOT NULL DEFAULT 1.0 | 完整度 0.0–1.0，归零变 rubble |
| `quality` | REAL | NOT NULL DEFAULT 0.5 | 手艺 0.0–1.0，影响衰减速度 |
| `decay_rate` | REAL | NOT NULL DEFAULT 0.0 | 每 tick 衰减速率 |
| `load_bearing` | INTEGER | NOT NULL DEFAULT 0 | 是否承重（级联坍塌用，M5） |
| `supported_by` | TEXT | NOT NULL DEFAULT '[]' | JSON 支撑结构 id 列表 |
| `is_rubble` | INTEGER | NOT NULL DEFAULT 0 | 1=已成瓦砾（终态，永不恢复） |
| `last_decay_tick` | INTEGER | NOT NULL DEFAULT 0 | 上次衰减 tick |
| `updated_at_tick` | INTEGER | NOT NULL DEFAULT 0 | 最后更新 tick |
| `created_at` | REAL | NOT NULL | 客观时间戳 |

**索引**：
- `idx_matter_branch` ON `(branch_id)` — 按分支取全部物质状态
- `idx_matter_branch_kind` ON `(branch_id, subject_kind)` — 按对象类别查询

**matter 熵增事件模型**（与 events 表配合；本表不含事件语义）：

物质熵增的**唯一写路径**是事件流（§19），事件形状：

```
event_type = "matter.decay" | "matter.damage" | "matter.build" | "matter.collapse"
actor_id   = 触发者（自然衰减为空串 / 系统）
target_id  = subject_id
payload    = { "subject_id", "delta_integrity", "cause", "material"? }
witnesses  = 目击者（坍塌/火灾进记忆，§14）
entropy_ref= 关键分叉（坍塌伤人/火灾蔓延）走熵注入时指向 entropy_log.id（§11）
```

- `matter.decay`：确定性混沌（§11），随 tick 按 `decay_rate` 衰减，可重放；
- `matter.damage` / `matter.collapse`：破坏与级联坍塌（§14，M5）；
- `matter.build`：施工推进（§14，M4）；
- 回放：从最近快照的 matter 状态出发，按 `events.seq` 重放上述事件 → `matter_state`
  逐位重建（与 §12 双轨存档天然兼容）。
- EventKind 与 payload schema 的落地归架构域（`sim/core/events.py`，Claude M2-A1）；
  本表为其持久化投影，字段与上述事件 payload 对齐。

**投影实现（M2-D2，`sim/core/persistence/npc_store.py`）**：

- `NpcStore.flush_tick(events)` = 本 tick 事件批次落 `events`/`entropy_log` +
  **同一事务内**投影：`MATTER_*` → `matter_state` UPSERT（`durability` 折算 `integrity`，
  `MATTER_COLLAPSE`/integrity≤0 → `is_rubble=1` 终态）。
- 投影经 `SqlEventStore.append(..., projection=<callback>)` 在 commit 前同一 session 执行；
  回调抛异常则整批回滚（无半写）。
- `NpcStore.materialize(ids)`：一次 SELECT 批量物化（L0→L1）→ frozen `NpcProfileData`（§12）。

---

## 15. NPC_LOD_CHANGE 持久化投影（M2-D2）

LOD 升降格是**事件驱动的列投影**（m2-npc-cognition §1.2：禁止直接改列，C4）：

```
event_type = "npc.lod_change"
payload    = { "npc_id", "from_lod", "to_lod"∈{0,1,2}, "reason" }
```

- 事件落 `events` 表（`witnesses`/`entropy_ref` 为通用列，与非 LOD 事件同构）；
- `NpcStore.flush_tick` 在**同一事务内**把 `to_lod` 投影回 `npc_profiles.lod`
  （§12 列，D1 已建），并刷新 `updated_at_tick`；
- 回放：重放 `events` 即重建各 NPC 的 lod 序列（同 matter_state 结构）；
- **无新增表/列**（LOD 状态本就属 `npc_profiles`），故 M2-D2 不产生 0005 迁移。

**降格记忆压缩写回（L2→L1，§1.2 关键缝）**：降格时 LLM 结论经唯一写入入口
`MemoryWritePipeline.write(source="reason")` 压缩落 `npc_memories`（§5）——
`NpcStore.writeback_downgrade_memory()` 为调用点；S1 守卫不变（隐藏属性直陈 → 拒写不落库）。

---

## 16. 记忆检索打分缝（读侧，M2-D3）+ 隐藏属性物化

### 16.1 检索打分（`sim/npc/memory.py`，读侧 only）

m2-npc-cognition §3.1 的「确认偏误 / 情绪一致性 → 记忆检索」挂载点落地为**读侧
检索打分 API**；本层**不写死偏差逻辑**，偏差由 `sim/agent/cognition.py` 后期以钩子注册。

```
MemoryQuery = { npc_id, context, mood=(p,r,d)|None, now_tick|None, top_k=DEFAULT }
retrieve(store|iterable, query, scorers=()) -> [MemoryHit(entry, score, breakdown)]
score = base_score(entry, query) × Π(mul 系数) + Σ(add 项)
base_score = importance × recency_factor   # 纯函数，不含偏差
```

- 候选来自 `MemoryStore.iter_visible(npc_id)`（§5/S5：**过滤 `superseded_by` 条目**）；
- **标量检索**（M2）；向量检索走 `npc_memory_vec`（§6）仍锁 M3；
- 钩子 `Scorer(name, RetrieveFn, mode∈{mul,add})`：`RetrieveFn = (entry, query) -> float`；
  `RetrievalScorers` 为不可变注册表（默认空 = 无偏差）；
- 确定性（C5）：同分按 `entry.id` 稳定排序；
- **读侧 only**：`retrieve` 不写库、不改存储，绝不碰 `MemoryWritePipeline` 写路径与守卫。

### 16.2 隐藏属性物化（`NpcStore.materialize_hidden`，codex MEDIUM ②）

`materialize()` 只取 `npc_profiles`（§12），升格装配 `HiddenState` 时缺隐藏半边。
`materialize_hidden() -> {npc_id: HiddenState}` 一次 SELECT 取 `npc_health` 中
`hidden=1 AND active=1`（§13）的行，按 npc_id 聚合：

- `HiddenAttribute.id` = `f"{npc_id}.health_{row.id}"`（DB 主键派生，稳定唯一）；
- `descriptors` ← 行 `descriptors` JSON（直陈词面，泄漏扫描面）；
- `triggers` ← 行 `trigger_conditions` JSON（情境触发关键词）；
- 返回类型 `sim/npc/contract.py::HiddenState`（M2-S2）；无隐藏行者不在结果中。

### 16.3 写入前置校验（`sim/core/persistence/event_validation.py`，codex MEDIUM ①）

`SqlEventStore.append()` 默认 `validate=True`：落库前逐行过
`validate_store_row`——按 `event_type` 查 `PAYLOAD_MODELS` 走 `extra="forbid"`
模型校验 payload；`NPC_ACT` 追加动作/`params` 键白名单（`sim/npc/actions.py`）；
`witnesses` 必须 `list[str]`。拒绝夹带字段/伪造见证人/未知 kind（防「smuggled params」）。
低层存储机制测试可 `validate=False` 传合成 payload（**生产禁用**）。此校验**不新增表/列**。

---

## ER 关系图

```
branches ──1:N── events
branches ──1:N── snapshots
branches ──1:N── player_anchors
branches ──1:N── npc_memories
branches ──1:N── relationships
branches ──1:N── knowledge
branches ──1:N── structures
branches ──1:N── npc_profiles
branches ──1:N── npc_health
branches ──1:N── matter_state

npc_profiles ──1:N── npc_health（通过 npc_id）
npc_profiles ──1:N── relationships / npc_memories / knowledge（通过 owner/holder/npc_id）

events ──1:1── entropy_log（通过 entropy_ref）
events ──N:1── matter_state（matter.* 事件驱动物质熵增，target_id=subject_id）

npc_memories ──1:1── npc_memory_vec（通过 rowid）

player_anchors ──N:1── branches（通过 branch_id）
```

---

## 17. Matter 三方投影对账（M2-D4）

MatterLedger（内存账本）→ MATTER_* 事件（`MatterPayload`）→ `matter_state`（持久化投影）
三方的字段一致性对账。判据 = §14「快照 + 事件重放可**逐位重建**」；任一列若无法从
事件流重建，即破坏回放保真，属对账缺口。

### 17.1 三方字段一致性表

| MatterSnapshot 字段 | MatterPayload 字段 | matter_state 列 | 现状 | 判据 |
|---|---|---|---|---|
| `matter_id` | `matter_id` / `target_id` | `subject_id`（PK） | ✅ 一致 | 主键直通 |
| `integrity` | `durability`（结算后耐久） | `integrity` | ✅ 一致 | 投影 `clip(0,1)`；`durability<0`=不变更 |
| `is_rubble` | —（无字段，**由 kind/值推导**） | `is_rubble` | ⚠️ 推导一致 | `COLLAPSE ∨ integrity≤0`；当前与账本等价，但非显式承载 |
| `decay_rate` | **无字段** | `decay_rate` | ❌ **缺口** | 投影硬编码 `0.0` 且 update 路径从不动它 → 重放后衰减对象永不衰减 |

**投影无源、按占位落库的列**（账本无对应概念，非缺口，归 M4/M5）：
`subject_kind`（`"structure"`）、`material`（`""`）、`quality`（`0.5`）、
`load_bearing`（`False`）、`supported_by`（`"[]"`）。`last_decay_tick`/`updated_at_tick`
取事件 `tick`；`branch_id` 取 flush 分支；`created_at` 为落库时钟。

### 17.2 缺口：`decay_rate` 无事件承载

- **现象**：`MatterLedger.register(decay_rate=...)` 是对象静态衰减系数（石墙=0），
  但 `settle_decay` 只用它算内部 `drop = decay_rate × jitter`，事件只记 `amount=-drop`；
  投影 `_project_matter` 新建行时 `decay_rate=0.0` 硬编码、更新路径不写该列。
- **后果**：§14 声明的「事件重放逐位重建」不成立——从快照/事件重载后，衰减对象的
  `decay_rate` 归零 → 永不衰减。当前无 `MatterState` 读路径（materialize 未接），
  故尚未暴露，但第三批接入世界循环 + 读档恢复即触发。
- **无法纯事件推导**：`decay_rate` 未进任何 `MatterPayload`；`jitter` 是 RNG 分桶 draw，
  未落 payload，从 `amount` 反解需按 tick 序重放 RNG（脆且违背「payload 自描述审计」）。
  `decay_rate=0` 的对象根本不产事件 → 该值永不可观测。

### 17.3 方案（待裁决）

| 方案 | 动作 | 迁移 | 评价 |
|---|---|---|---|
| **A（推荐）事件承载** | `MatterPayload` 增可选 `decay_rate`（默认 `-1`=不变更）；`matter_event`/`settle_decay` 携带账本静态率；投影写 `matter_state.decay_rate` | **无**（列已存在） | 恢复回放保真；但改 `sim/core/events.py` **冻结事件基线**，须 Claude 裁决 |
| B 只 build/register 事件承载 | 仅建造/注册事件带率，衰减/损伤不带 | 无 | 事件更少，但注册无专属 kind，需借 `MATTER_BUILD` 语义 |
| C 暂缓 | 保持 `decay_rate=0.0` 占位，文档标注已知缺口 | 无 | 零风险，但 §14 回放保真带洞直至 M4 |

- 最小变更不动 schema（`matter_state.decay_rate` §14 已建）；**无 0005 迁移**。
- 变更面：`events.py`（payload 字段 + factory 默认）→ `matter.py`（settle/damage/build 传率）
  → `npc_store.py::_project_matter`（写列）；配套 `test_m2_matter_projection.py` 对账。
- 约束「schema 变更先提案后动」：本表为提案，**报 Claude 裁决后再动**代码。

---

## 18. memory.py 检索打分契约（M2-D4 文档化）

`sim/npc/memory.py` 的完整契约（输入输出/注入点/M3 边界）以**模块 docstring 为权威**
（§16.1 为摘要）。要点：

| 契约面 | 内容 |
|---|---|
| 输入 | `MemoryQuery(npc_id 必填, context="", mood=None, now_tick=None, top_k=8)` |
| 输出 | `[MemoryHit(entry, score, breakdown)]`，score 降序 + 同分 `entry.id` 升序稳定 + top_k 截断 |
| 公式 | `score = (importance × recency) × Π(mul) + Σ(add)`；`scorers=()` 即纯基础分 |
| 注入点 | `Scorer(name, RetrieveFn(entry,query)->float, mode∈{mul,add})`；`RetrievalScorers` frozen；**偏差逻辑归 cognition**（确认偏误/情绪一致性，mode=mul） |
| M3 边界 | M2 标量：候选 = `iter_visible`（S5）；`npc_memory_vec`（§6）**仍锁 M3**，届时仅作候选生成器替换/前置，打分 API 形状不变 |
| Guardrail | 读侧 only：不写库、不碰 `MemoryWritePipeline`/S1 守卫 |

`scores_of(hits) -> {entry_id: score}` = §3.2 cognition 的 `memory_scores` 输入形。

---

## 19. matter 读路径设计（M3 预研，M2-D4 后继）

§17 方案 A 落地后 `matter_state` 已是**完整**的写入投影（含 `decay_rate`，事件可逐位重建）。
M3 世界循环需要**读路径**：从库/事件重建内存 `MatterLedger`。本节为**设计契约草案**
（零代码，行为以落地版为准）。

### 19.1 目标与模式

- **对镜 `NpcStore.materialize`**（§12 L0→L1）：一次 SELECT 批量取本分支 `matter_state`
  → 内存态；禁止逐对象查询（§1.3 同款纪律）。
- **产物**：`MatterLedger`（`{matter_id: MatterSnapshot}`，含 `integrity/decay_rate/is_rubble`）。
- 契约名：`NpcStore.materialize_matter(subject_ids: Sequence[str] | None = None) -> MatterLedger`。

### 19.2 草案签名与映射

```
async def materialize_matter(
    self, matter_ids: Sequence[str] | None = None
) -> MatterLedger: ...
```

| matter_state 列 | MatterSnapshot 字段 | 映射 |
|---|---|---|
| `subject_id` | `matter_id` | 直通 |
| `integrity` | `integrity` | 直通（库内已 clip 0..1） |
| `decay_rate` | `decay_rate` | 直通（方案 A 起列保真） |
| `is_rubble` | `is_rubble` | 直通（终态） |

- `matter_ids=None` → 本分支全部（`WHERE branch_id=?`）；显式给 id → `IN (...)`，
  未知 id 不在结果中（调用方兜底，同 `materialize`）。
- 其余列（`subject_kind/material/quality/load_bearing/supported_by`）**不映射**：
  MatterSnapshot 无此概念（§17.1 占位列，归 M4/M5）。
- **不落库、不改写**：读路径只重建内存账本（与 `materialize` 同为纯读）。

### 19.3 两种入口的缝（重放路径 vs 快照路径）

§14 声明「快照 + 事件重放可逐位重建」。两入口**同产物、不同代价/精度**：

| 入口 | 机制 | 代价 | 用途 |
|---|---|---|---|
| **快照路径** `materialize_matter()` | 直接 SELECT `matter_state`（当前值） | 1 次查询 O(n) | 常规启动/恢复；n = 存活对象数 |
| **重放路径**（预留） | 从最近 `snapshots` + 重放 `matter.*` 事件 → UPSERT 重建 | 与事件数成正比 | 快照损坏/审计核对；方案 A 已保证 `decay_rate` 可重建 |

- **缝的位置**：两入口都归数据域（本模块），产出 same `MatterLedger`；调用方
  （M3 世界循环）按场景选入口，**不感知**内部差异。
- **一致性判据**：两入口产出应**逐位相等**（`integrity/decay_rate/is_rubble`）；
  可作 M3 校验测试（对账 §17 三方表的运行时延伸）。
- **重放路径本批不实现**：M2 只备「快照路径」入口草案；重放器（读 events 表按 seq
  重放 → 投影回内存）是 M3 工作项，届时复用 `_project_matter` 的**同一折叠规则**
  （`durability`→integrity、`COLLAPSE∨≤0`→rubble、`decay_rate≥0`→写率），避免两套语义分叉。

### 19.4 边界与约束

- **注册=立账事件**：`MatterLedger.register` 返回 `MATTER_BUILD` 事件
  （`amount=0`、`durability=integrity`、`note="register"`，x/y 默认 -1），
  走 C4 唯一写路径。`NpcStore.flush_tick` 同事务投影 `matter_state`；
  `flush_events` 只落事件、由 `materialize_matter_replay` 冷启重建。
  structures 表 M3 不建；M4 建造时再裁拓扑投影（见 §9 与
  `docs/data/matter-register-proposal.md`）。
  *（M2-D6 核对：本条与 V 系裁决 3 的 V6「记忆召回端治理过滤」无交集——V6 作用于
  `npc_memories`/`npc_memory_vec`（记忆域），本条为 matter 域注册语义，二者互不影响。）*
- **分支隔离**：`WHERE branch_id = self._branch_id`，同 `materialize`。
- **只读**：不触发写路径、不投影、不 flush（C4 唯一写路径不变）。
- 零 schema 改动、零迁移（纯读 + 已有列）。

---

## 索引策略总结

| 表 | 索引 | 用途 |
|----|------|------|
| events | (branch_id, tick) | 快照后重放定位 |
| events | (branch_id, actor_id) | 角色事件查询 |
| events | (branch_id, event_type) | 类型筛选 |
| branches | (status) | 活跃分支查询 |
| snapshots | (branch_id, tick) | 读档定位最近快照 |
| snapshots | (is_cold) | 冷归档管理 |
| npc_memories | (npc_id, branch_id) | 角色记忆查询 |
| npc_memories | (npc_id, importance DESC) | 重要性检索 |
| relationships | (branch_id, owner_id) | 关系查询 |
| knowledge | (branch_id, holder_id) | 知识查询 |
| structures | (branch_id) | 分支结构物查询 |
| npc_profiles | (branch_id, lod) | L1 全量自转（50 NPC）按 LOD 取 |
| npc_health | (branch_id, hidden) | 常显/隐藏健康档过滤（自我未知） |
| matter_state | (branch_id, subject_kind) | 物质熵增状态按类别查询 |

---

## 与 §19 禁止事项的对齐

| 禁止事项 | Schema 对策 |
|----------|------------|
| 不要为世界状态直接赋值，必须走 `apply(event)` | events 表唯一写路径，ORM 不暴露 UPDATE/DELETE；matter_state（§14）与 npc_profiles.lod（§15）均为事件的持久化投影 |
| 不要让读档删除或回退世界档历史 | events append-only，读档只创建新分支 |
| 不要在 LOD 降格时丢失 LLM 产生的结论 | npc_memories 持久化所有 LLM 输出的结论；降格压缩写回 source=reason（§15） |
| 不要直接渲染 LLM 原始输出 | schema 不含渲染字段，只存原始数据 |
| 自我未知：隐藏属性不得默认进入 LLM/戏内输出面 | npc_health.hidden + descriptors/trigger_conditions 标注（§13，触发才浮现） |
