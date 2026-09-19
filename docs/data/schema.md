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

**约束**：
- `source` IN ('witnessed', 'told', 'inferred')
- `confidence` 范围 0.0–1.0

**索引**：
- `idx_knowledge_holder` ON `(branch_id, holder_id)` — 按角色查询知识
- `idx_knowledge_source` ON `(branch_id, source)` — 按来源筛选

---

## 9. structures（建筑/结构物）

§6 Structure：可建造/可破坏的物理结构。

| 字段 | 类型 | 约束 | 说明 | 对齐 |
|------|------|------|------|------|
| `id` | TEXT | PRIMARY KEY | 结构物 UUID | — |
| `branch_id` | TEXT | NOT NULL | 所属分支 | — |
| `tiles` | TEXT | NOT NULL | JSON 数组：占据的 tile 坐标 [(x,y), ...] | §6 |
| `kind` | TEXT | NOT NULL | 结构类型（木棚/石墙/...） | §6 |
| `material` | TEXT | NOT NULL | 材料 | §6 |
| `integrity` | REAL | NOT NULL DEFAULT 1.0 | 完整度 0.0–1.0，归零变 rubble | §6/§14 |
| `quality` | REAL | NOT NULL DEFAULT 0.5 | 质量 0.0–1.0，影响衰减速度 | §6 |
| `load_bearing` | INTEGER | NOT NULL DEFAULT 0 | 是否承重 | §6 |
| `supported_by` | TEXT | NOT NULL DEFAULT '[]' | JSON 数组：支撑结构 id 列表 | §6 |
| `owner_id` | TEXT | NULL | 所有者 | §6 |
| `built_by` | TEXT | NULL | 建造者 | §6 |
| `built_at` | INTEGER | NULL | 建造 tick | §6 |

**索引**：
- `idx_struct_branch` ON `(branch_id)` — 按分支查询
- `idx_struct_owner` ON `(branch_id, owner_id)` — 按所有者查询

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

## ER 关系图

```
branches ──1:N── events
branches ──1:N── snapshots
branches ──1:N── player_anchors
branches ──1:N── npc_memories
branches ──1:N── relationships
branches ──1:N── knowledge
branches ──1:N── structures

events ──1:1── entropy_log（通过 entropy_ref）

npc_memories ──1:1── npc_memory_vec（通过 rowid）

player_anchors ──N:1── branches（通过 branch_id）
```

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

---

## 与 §19 禁止事项的对齐

| 禁止事项 | Schema 对策 |
|----------|------------|
| 不要为世界状态直接赋值，必须走 `apply(event)` | events 表唯一写路径，ORM 不暴露 UPDATE/DELETE |
| 不要让读档删除或回退世界档历史 | events append-only，读档只创建新分支 |
| 不要在 LOD 降格时丢失 LLM 产生的结论 | npc_memories 持久化所有 LLM 输出的结论 |
| 不要直接渲染 LLM 原始输出 | schema 不含渲染字段，只存原始数据 |
