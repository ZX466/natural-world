# M5-D1 双轨存档存储面预研（读档 = 分叉；提案制零代码）

> 输入：Claude 主树派单 M5-D1（2026-09-27）｜能力域：数据/数据库｜评审配对：codex
> 基线：DESIGN.md §11 不可逆两层（分支间可回退 = 读档分叉）、§12 双轨存档、§16 T1/T2/T5、§17 M5 行
> 自有资产：`docs/data/schema.md`、`docs/data/event-sourcing.md`、`docs/data/vec-preplan.md`、
> `docs/data/build-domain-preplan.md`（同款提案体例）、`sim/core/persistence/{models,store,vector,memory_store}.py`
> 交叉对账：pi M5-P1（M5 perf 预研）= `docs/perf/m5-time-scale-fork-budget.md`；**§7 已回填**（2026-09-27）
> **本文档零代码、零 schema、零迁移**；所有迁移号（0008）只做预估，不动手。
>
> **施工进度（勿把提案当现状读）**：裁决见 `docs/arch/m5-rulings.md` §B（12 点全裁）。
> 已落：①§2.4 案 C（T1 断言 5 口径）+ ②§5-C5（F3 向量召回分支隔离，裁 11）——**M5-D2**。
> 未落：0008 迁移（裁 1/3/4/9）、fork 事务与克隆（裁 6/10）、R2 三断言。进度表见 §9。

---

## 0. 结论摘要

### 0.1 三条硬发现（先说结论，全部有仓内实证）

| 编号 | 发现 | 实证位置 | 后果 |
|---|---|---|---|
| **F1** | `npc_profiles` 主键是**单列 `id`**，`branch_id` 只是普通列——13 张表里唯一的例外 | `models.py:292-293`（`id = mapped_column(String, primary_key=True)`，`__table_args__` 只有两个 Index） | 读档克隆 `npc_profiles` 必撞主键；同 id 跨分支**物理不可能共存**。修复＝0008 batch 改复合主键（0006 对 `matter_state` 的同款手法，本树有先例） |
| **F2** | `npc_memories` / `knowledge` / `relationships` **没有事件源**——19 个 `EventKind` 里没有任何「记忆/知识/关系被写入」的事件，`NPC_ACT.params` 白名单只有 `path/site/food_id/hours/radius/to_npc` | `event_validation.py:53-72`（`PAYLOAD_MODELS` 全 19 kind）、`actions.py:22-29` | 这三张表**不可从事件流重建** → 「读档=分叉」若走「纯事件追加 + 重放投影」路线，对语料表在结构上不成立（详见 §3.2 判据表） |
| **F3** | 向量召回面**零分支隔离**：`vector.py` 全文没有 `branch_id`；`vec_candidate_ids` 的召回 SQL 是 `JOIN npc_memories ON m.id = v.rowid WHERE superseded_by IS NULL AND invalid_reason IS NULL`——**没有 `m.branch_id = ?`** | `vector.py:204-226`（`rg -n "branch" sim/core/persistence/vector.py` → 0 命中） | 单分支下是潜伏问题；**一旦分叉存在，NPC 会召回已被弃分支/父分支的记忆**——既是 T1 信息边界破口，也是出戏风险（NPC 记得本时间线里没发生的事）。列为 M5 硬前置 → ✅ **M5-D2 已落**（裁 11 = 采）：召回句加 `m.branch_id = ?` + 6 钉子 + over-fetch 抗饥饿（§5-C5） |

### 0.2 六条主张（12 点已全裁，见 `docs/arch/m5-rulings.md` §B）

| 编号 | 主张 | 一句话理由 |
|---|---|---|
| **A1** | 事件流主表**不需要再加 `branch_id` 列**（它已是 PK `(branch_id, seq)` 的一部分）；真正缺的是 ①`npc_profiles` 的分支身份（复合 PK）②可选的全局总序 `global_seq` | 问题要拆成「身份唯一性 / 总序 / 谱系引用」三件事，混着问会得出错的迁移 |
| **A2** | **同表加列 ≫ 分文件**。分文件只保留为 §12 已定的 abandoned 分支冷归档搬移形态，不做主存储布局 | 分文件作废跨表 JOIN（治理 JOIN、`vec_candidate_ids` 正是跨表）、分裂事务边界、破坏 `UNIQUE(entry_id)` 类约束 |
| **A3** ✅ 已落 | **零迁移先让 T1 断言 5 可证伪**：断言对象从「seq 整数集合」改成「`(branch_id, seq)` 对集合」——复合主键已保证唯一，**不需要任何 schema 改动**就能让 C6 从「不可证伪」变成「可证伪」 | 现在 `before <= world.all_event_seqs()` 在分叉下是**恒真**的：删掉父分支 51-100 再在新分支重写成 1-50，断言照样过（**实测补一条**：旧口径的鉴别力还是偶然的——子分支一推进到同量重占 seq，它就完全看不见；只有对口径稳定） |
| **A4** | 读档分叉物理形态＝**有界表克隆 + 语料表按分叉点截断克隆**；**否决谱系回退读**；纯事件重放路线对语料表结构上不成立（F2） | 克隆保住了全域 `WHERE branch_id = ?` 纪律（D4 R4「跨分支 id 视作不存在」是明文裁决），零读路径改动 |
| **A5** | 玩家档游标表**只指 `(branch_id, seq)`，不复制世界态**；唯一 JSON 载荷是 `agent_override`，且必须是**封闭 schema + 版本号 + 纯函数应用**（否则同一 anchor 载入两次结果不同 → T2 破） | `agent_override` 是玩家所有权物，不是世界态副本；可重放性要求它进折叠链 |
| **A6** | **anchor 引用即热钉**：被任一 anchor 指向的分支永不整分支冷归档 | §12 体积治理（abandoned 整体移出主库）与 §12 读档流程（anchor 可指向 abandoned 分支）**互相打架**——不钉住就读不回来 |

### 0.3 与既有裁决的边界

- 本文**不改**任何已裁结论（M3-D6 V1/V4/V6、M4-D2 裁 14-2、M4-D4 裁 10），只在分叉语境下**追加适用条件**。
- 任何「给 memories/knowledge 补事件」的方案＝改冻结事件基线＋触 S1/X7 写入门，**须 codex 复核**，本文只列为中长期项（§8 待裁点 7）。
- 架构域（`world.py` 事件总线接线、生产 Pathfinder 持有者、driver 的 fork 编排）本文只标依赖，不越界施工。

---

## 1. 现状盘点（实测，非推断）

### 1.1 表清单 × 分支身份矩阵

| 表 | 分支列 | 身份形态 | 事件可重建？ | 读路径分支过滤 | 备注 |
|---|---|---|---|---|---|
| `branches` | `id` 即分支 | PK `id` | — | — | 已有 `forked_from_branch` / `forked_from_seq` / `status` / `abandoned_at` |
| `events` | `branch_id` | **PK `(branch_id, seq)`** | 真相源 | ✅ `read_range(branch_id, …)` | seq = 分支内 `MAX(seq)+1`（`store.py:143-152`） |
| `snapshots` | `branch_id` | PK `(branch_id, seq)` | 缓存 | ✅ | `seq` = 快照点事件流最大 seq（重放窗口不错位） |
| `player_anchors` | `branch_id` | PK `id` | 游标 | ✅ | 详见 §4 |
| `entropy_log` | `branch_id` | PK `id`（autoinc） | 熵材料 | ✅ 索引带 branch | `event_seq` 是**分支内**引用 |
| `npc_profiles` | `branch_id`（普通列） | **PK `id` 单列** ⚠️ **F1** | 否（无事件源） | ✅ `materialize` | 索引有 branch，**主键没有** |
| `npc_health` | `branch_id` | PK `id`（autoc） | 否 | ✅ `materialize_hidden` | 一行 = 一条健康属性 |
| `npc_memories` | `branch_id` | PK `id`（autoc）+ `UNIQUE(entry_id)` **全局** | **否**（F2） | `iter_visible` ✅ / `get`+`supersede` ❌ 不带分支 | §6.1 克隆身份之争源于此 |
| `relationships` | `branch_id` | PK `(branch_id, owner_id, other_id)` | **否**（F2） | ✅ | 只有 `last_interaction`（tick），无 seq |
| `knowledge` | `branch_id` | PK `id`（autoc） | **否**（F2） | ✅ | `source_knowledge_id` 是 **autoinc int 链指针** |
| `structures` | `branch_id` | PK `(branch_id, structure_id)` | ✅ 有 fold 器 | ✅ | M4-D2 落地 |
| `matter_state` | `branch_id` | PK `(branch_id, subject_id)` | ✅ 有 fold 器 | ✅ | M4-D2a 改复合主键 |
| `material_balances` | `branch_id` | PK `(branch_id, ref, material_id)` | ✅ 有 fold 器 | ✅ | M4-D2d |
| `npc_memory_vec` | **无** ⚠️ | vec0 虚拟表，rowid = `npc_memories.id` | — | **❌ F3** | alembic 范围外（需 `LOAD EXTENSION`） |
| `llm_profiles` | 无（合理） | PK `id` | — | — | 配置面，与分支无关 |

**读法**：11 张表已是「分支内身份」；`npc_profiles` 掉队（F1）；`npc_memory_vec` 根本没有分支概念（F3）；
语料三表（memories/knowledge/relationships）没有事件源（F2）——这三条决定了 §2/§3 的形态选择。

### 1.2 事件流主表现状

- PK `(branch_id, seq)`；`seq` 由 `SELECT max(seq) WHERE branch_id=?` + 1 分配（`store.py:143-152`）。
  → **分叉后新分支的 seq 从 1 重新开始**，与父分支 seq 空间**重叠**。
- 索引三条全部以 `branch_id` 打头（`idx_events_branch_tick` / `_actor` / `_type`）→ 读路径天然分支内。
- `parent_seq`（因果链）是**分支内**引用 → 分叉后指向父分支事件的 `parent_seq` 会**悬空**（§2.6 待裁点 3）。
- `entropy_log.event_seq` 同为分支内引用 → 同上。

### 1.3 读档路径现状（伪码 vs 实际）

`docs/data/event-sourcing.md` §4.1 的 `load_anchor` 伪码做的是：定位 anchor → 找快照 → 重放事件到
`MaterializedWorld`（**纯内存**）→ 应用 override → 建新分支 → 旧分支标 abandoned。

**与真实代码的三处缝**（全部属 M5 施工时的必答题，本文只登记）：

| 缝 | 事实 | 影响 |
|---|---|---|
| 缝 1 | 伪码只重建**内存** `MaterializedWorld`；真实世界的当前态在**投影表**里（`npc_profiles` / `matter_state` / `structures` / `knowledge` / `npc_memories` / `relationships`）。伪码**没有投影表克隆步骤** | 新分支的投影表全空 → 读档后世界「失忆」。**这是 §3 的核心缺口** |
| 缝 2 | 所有 store 实例**构造时绑死 `branch_id`**（`NpcStore._branch_id` / `KnowledgeStore._branch_id` / `SqlMemoryStore._branch_id` / `MemoryWritePipeline`），无 `rebind()` | 分叉后须**重建全部 store 实例**或新增 rebind API（架构域裁决） |
| 缝 3 | `SqlEventStore`（async aiosqlite）与 `SqlMemoryStore`（**同步 sqlite3**）是**两条独立连接** | fork 需要「建分支 + 克隆投影 + 标 abandoned」的**原子性**，跨连接做不到（§3.7） |

### 1.4 T1 断言 5（历史不可销毁）现状

- DESIGN §16 的写法：`before = world.all_event_seqs()` → `load_anchor` → `assert before <= world.all_event_seqs()`。
- 仓内**无 `all_event_seqs` 实现、无对应 T1 钉子**（`rg "all_event_seqs" sim/` → 0 命中；`sim/tests/test_t1_*` 14 个文件里无此项）。
- **在分叉下该断言恒真（不可证伪）**：seq 是分支内整数，两个分支的 seq 空间重叠；
  删掉父分支的 51–100、在新分支重写成 1–50，整数集合视角下断言照过。→ 必须换口径（§2.4 案 C / §6.2）。

---

## 2. Q1｜`branch_id` 全局化：事件流主表要不要全局 `branch_id`？

### 2.1 先把问题拆成三件

派单把「全局化」当成一个问题，实测它是三个独立问题，混着问会导出错的迁移：

| 子问题 | 现状 | 是否需要动 schema |
|---|---|---|
| ① **身份唯一性**：一个事件在全世界档里怎么被唯一指认？ | 已有：PK `(branch_id, seq)` 全局唯一 | ❌ 不用动 |
| ② **总序**：全世界档事件有没有一个单调递增的全局序？ | 无（seq 分支内） | 🟡 可选（`global_seq`） |
| ③ **谱系引用**：跨分支引用（`parent_seq` / `evidence_seq`）怎么解析？ | 无解析规则 | 🟡 可选（加 `*_branch_id` 列）或定解析规则 |

**直接回答派单的问题**：「事件流主表要不要全局 `branch_id`？」——**不用，它已经是主键的一部分。**
真正缺的是 §0.2-A1 的两件事：`npc_profiles` 的分支身份（必须动，F1）、`global_seq`（可选，§2.5）。

### 2.2 案 A｜同表加列

给 `events` 加 `global_seq INTEGER`（世界档总序，append 时分配，只增不复用）。

| 维度 | 评价 |
|---|---|
| 可证伪性 | ✅ T1 断言 5 可写成 `before_global ⊆ after_global`，且能发现「删 A 分支补 B 分支」 |
| 事务边界 | ✅ 单表单事务；`counters` 单行 `UPDATE … RETURNING` 分配（SQLite 单写者，无并发撞号） |
| 跨表 JOIN / 唯一约束 | ✅ 零影响（`(branch_id, seq)` 主键保留，分支内局部序不动） |
| 热路径成本 | 🟡 每事件多写 1 列 + 1 个 counter 行更新（append 本已每批 1 次 `max(seq)` 查询，量级不变） |
| 回填风险 | ⚠️ 历史行需回填且**必须确定性**（否则审计序不可复现）；建议列先 NULL + 唯一索引（SQLite 唯一索引允许多 NULL）渐进迁移 |
| 体积 | 每事件 +8B（INTEGER）；主库 2GB 预算下可忽略（预估） |

### 2.3 案 B｜分文件（每分支一个 SQLite / abandoned 分支移出主库）

| 维度 | 评价 |
|---|---|
| 跨表 JOIN | ❌ **致命**：`vec_candidate_ids` 的治理 JOIN（`JOIN npc_memories`）与知识级联读都在**同库跨表**；分文件后这些查询要么跨 ATTACH（慢且脆）要么复制语料（回到克隆） |
| 事务边界 | ❌ **致命**：fork 的「建分支 + 克隆投影 + 标 abandoned」跨文件无法单事务；崩溃后半写不可恢复 |
| 唯一约束 | ❌ `UNIQUE(entry_id)`（`idx_memories_entry`）退化为 per-file；跨文件出现同 `entry_id` 时无任何库级保护 |
| 运维 | ❌ 备份/一致性/迁移要处理 N 个文件；`branches` 表放哪都要单点 |
| 已有依据 | 🟡 DESIGN §12 v2.1 只说「abandoned 分支整体冷归档（gzip + **单独 SQLite 文件移出主库**）」——这是**搬移形态**，不是主存储布局 |

**结论**：分文件**否决为主方案**（A2）。保留为 abandoned 分支的冷归档搬移形态，且必须先解 §4.6 的 anchor 热钉问题。

### 2.4 案 C｜零迁移：改断言口径 —— ✅ **已落（M5-D2）**

> 实施记录：`sim/tests/test_t1_m5_history_preserved.py`（6 钉子，零 schema）。
> oracle = `world_event_keys(sf) -> set[tuple[str, int]]`（跨全部分支读
> `(branch_id, seq)`）；对照组 `naive_seq_set` 保留在测试里**不删**，用来证明新口径
> 确有鉴别力。二阶守卫 `test_falsifiability_guard_pair_keys_detects_delete_and_rewrite`
> 实测：把 oracle 换成裸 seq 会红 4 个钉子（已本地验证）。
> **实测补一条**：裸 seq 口径的鉴别力是**偶然**的——子分支尚未跑够时被删的 seq
> 还没被重占，此时它能抓到；一旦新分支推进到相同条数（同量重占 seq），它就完全
> 看不见了。故旧口径的「有时能抓」不可依赖，只有对口径稳定。

不动任何 schema，把 T1 断言 5 的比较对象从「seq 整数集合」改成「`(branch_id, seq)` 对集合」：

```
before = {(r.branch_id, r.seq) for r in 所有分支事件}      # 复合主键保证全局唯一
load_anchor(anchor)
after  = {(r.branch_id, r.seq) for r in 所有分支事件}
assert before <= after            # 集合包含，且 now 可证伪
```

- **为什么这就够了**：`(branch_id, seq)` 由复合主键保证唯一且不可复用；删父分支 51–100、在子分支重写 1–50，
  `before` 里的 `("main",57)` 在 `after` 里消失 → **断言变红**。可证伪性已达标。
- **零迁移、零 schema、只加测试**——这是本稿唯一「今天就能落」的一条。
- 不能替代 `global_seq` 的场景：需要**跨分支单调总序**的场合（审计日志按时间排序、整段转冷的切点、跨分支时间线对照）。

### 2.5 建议：`global_seq` 的必要性判据（挂 M5 尾 / 0008）

只有当出现下列**具体需求**时才加 `global_seq`：

1. 审计面要回答「按世界档总序第 N 个事件是什么时候发生的」（跨分支混合时间线）；
2. 冷归档要按**单一全局切点**整段搬移（§12「事件日志主库超阈值后按快照点以前整段转冷」在多分支下若各分支切点不同，实现会碎）；
3. 外部工具（调试覆盖层）要一个不依赖分支上下文的稳定事件句柄。

若 M5 不落 1/2/3 → **不加**。M5 若落 → 走 §2.6 草案。

### 2.6 0008 迁移预估（**只预估，不动手**）

**触发条件**（三条独立，建议合成一支迁移，也可拆 0008/0009）：

| 编号 | 变更 | 必要性 | 手法 | 预估行数 |
|---|---|---|---|---|
| 0008-a | `npc_profiles` PK `(id)` → **`(branch_id, id)`**（**F1，必须**） | 分叉克隆的前提 | `op.batch_alter_table(..., naming_convention=…)` + `drop_constraint` + `create_primary_key`（**0006 对 `matter_state` 的同款手法，`0006_m4_structures.py:34-36` 有可直接复制的模板**） | ~40 行（含 downgrade） |
| 0008-b | `npc_memories` `UNIQUE(entry_id)` → **`UNIQUE(branch_id, entry_id)`**（仅当 §6.1 采「保留 entry_id」案时） | 可选，与 6.1 绑定 | drop + create index | ~15 行 |
| 0008-c | `events` 加 `global_seq` + 唯一索引 + `counters` 单行表（仅当 §2.5 判据命中时） | 可选 | `add_column`（先 NULL）+ `create_index` + 回填脚本 | ~90 行（含回填） |
| 0008-d | `knowledge` 加 `evidence_branch_id`（§5.4 C4） | 可选 | `add_column` + index | ~15 行 |

**预估汇总**：必落 ~40 行 + 测试 6–8 例；全量落 ~160 行 + 测试 14–20 例。量级与 0006/0007 同档。
**风险**：

- 0008-a 会改 `npc_profiles` 的身份 → 所有 `session.get(NpcProfile, id)` 式**单键查找**必须同步改双键。
  先例：M4-D2a 改 `matter_state` 主键时同步改了 `_project_matter` 与 **10 处测试**的 `session.get`。
  `rg "session.get\(NpcProfile|session.get\(Event" sim/` 的命中数需在施工前清点（本文未清点，列为施工首步）。
- 0008-c 的回填必须**确定性排序**（建议 `(created_at, branch_id, seq)` 升序），否则审计序不可复现 → 与 T2 逐位一致的精神一致。
- `npc_profiles` 无外键声明（`models.py` 无 `ForeignKey`），故改主键不触发级联；但 `npc_health.npc_id`、
  `relationships.owner_id/other_id`、`npc_memories.npc_id` 语义上引用它——**引用面靠应用层纪律维持**，改主键时须同步核对。

---

## 3. Q2｜读档 = 分叉的物理形态

### 3.1 三个候选

| 案 | 形态 | fork 事务做什么 | 首读代价 |
|---|---|---|---|
| **A** | **全量克隆投影** | `INSERT branches` + 12 张分支表的 `INSERT…SELECT` + 旧分支 `status='abandoned'` | O(1)（投影已在） |
| **B** | **纯事件追加**（新分支只写自己的事件） | `INSERT branches` + 旧分支 abandoned | O(父分支事件数) 折叠 |
| **C** | **谱系回退读**（子分支读 = 自己 ∪ 祖先中 `seq ≤ F` 的行） | 只有 `INSERT branches` | O(1) 读，但**每次读都跨分支** |

### 3.2 判据表：谁能从事件流重建（决定 A/B 分界）

| 投影表 | 有 fold 器？ | 事件源？ | 案 A 克隆 | 案 B 重放投影 |
|---|---|---|---|---|
| `matter_state` | ✅ `fold_matter_snapshot` | ✅ `matter.*` | 克隆 | ✅ 可行 |
| `structures` | ✅ `fold_structure_snapshot` | ✅ `structure.*` | 克隆 | ✅ 可行 |
| `material_balances` | ✅ `fold_material_balance` | ✅ `material.moved` | 克隆 | ✅ 可行 |
| `npc_profiles`（含 lod） | ✅ 投影即 `npc.lod_change` | 🟡 部分（只有 lod 有事件；姓名/OCEAN/PAD/needs 无事件） | 克隆 | ❌ 不完整 |
| `npc_health` | ❌ | ❌ | 克隆 | ❌ 不可能 |
| **`npc_memories`** | ❌ | ❌ **F2** | 克隆 | ❌ **不可能** |
| **`knowledge`** | ❌ | ❌ **F2** | 克隆 | ❌ **不可能** |
| **`relationships`** | ❌ | ❌ **F2** | 克隆 | ❌ **不可能** |

**结论（承派单问题）**：
- **「copy-on-write」在 SQLite 单文件 + 投影表已物化的形态下，实际就是「新分支追加 + 克隆投影行」**（不是文件系统的 CoW）。
  新分支的事件永远是**追加**（append-only 不变），被复制的是**投影表行**，且**按分叉点截断**。
- **纯事件重放路线（案 B）只能覆盖有 fold 器的 4 张表**；语料三表在结构上不成立（F2）。
  → **A 与 B 不是二选一，是分工**：有 fold 器的走「克隆即时 + 重放核对」，语料表只能克隆。
- **案 C（谱系回退读）否决**：
  1. 打破全域 `WHERE branch_id = ?` 纪律（D4 明文裁决：跨分支 id 视作不存在，R4）；
  2. `SqlMemoryStore.supersede` / `get` **本来就不带分支过滤**（`memory_store.py:99-111`），谱系读会让治理 UPDATE 跨分支命中；
  3. `npc_memory_vec` 无 branch 列（F3），谱系读下向量召回面无从加过滤；
  4. 每次读跨分支 = 每次读跨表 JOIN，pi 侧成本不可控。

### 3.3 克隆正确性的前置条件（P1，**必答**）

案 A 的正确性依赖一条未被任何文档写明的不变式：

> **P1：fork 发生时，父分支的投影表必须已经追平到分叉点（无「已产事件未投影」的 in-flight 批次）。**

- 为什么必需：克隆取的是**父分支投影表的当前值**。若父分支还有已落 `events` 但未投影的批次，
  新分支就会继承一个「比事件流旧」的物化态 → 缝上不一致，且此偏差**不可事后修复**（只能整分支重来）。
- 为什么当前不成立：`NpcStore.flush_tick` 是「事件 + 投影同事务」，但**投影只在 flush 那一刻发生**；
  driver 在两批之间的 tick 上收到读档请求，就存在 in-flight 批次。
- 建议落地形态（数据域可自证，driver 侧配合）：
  - fork 前置断言：`父分支最后一条已投影事件的 seq == max(events.seq WHERE branch_id=父)`；
  - 不满足 → **fail-closed**（拒绝 fork 并返回结构化失败原因，§19「不静默丢弃」精神），
    或先强制 flush 再 fork（推荐后者：把「投影追平」做成 fork 的第一步，而非断言）。
- 附带不变式：**父分支必须与建新分支在同一事务里标 `abandoned`**（DESIGN §12 与
  `event-sourcing.md` §4.1 第 7 步都是这么写的）。这条让「父分支投影 == 分叉点状态」成立，
  也让 `relationships` 这类**无 seq、只有累计值**的表可以「全量克隆、不截断」（见 §3.6）。

### 3.4 克隆的身份问题：语料表 id 怎么办（成本核心）

克隆必须换 id（`npc_memories.id` / `knowledge.id` 是 autoincrement），于是**内部指针断裂**：

| 表 | 克隆后必断的指针 | 修法 |
|---|---|---|
| `npc_memories` | `superseded_by`（指 `entry_id`）；`idx_memories_entry UNIQUE(entry_id)` **全局唯一** | 见 §6.1 两案 |
| `knowledge` | `source_knowledge_id`（int id，told 链）；`source_memory`（`entry_id`） | 同事务内建 `old_id → new_id` 映射，克隆后**重写指针**；链式一致（told 链任意深度）须核对 |
| `npc_memory_vec` | rowid 必须重键到新的 `npc_memories.id` | 从 **vec 表自身**读向量字节 `INSERT … SELECT`（V4 裁决：vec 表为准）→ **零 LLM 调用**。⚠️ 若走重新 embed，单次 fork 就是上万次 LLM 调用——**红线禁止** |
| `relationships` / `npc_profiles` / `npc_health` | 无内部指针 | 直接改 `branch_id` 列值即可（前提 0008-a 已把 `npc_profiles` 主键改复合） |

### 3.5 建议形态（A4）

```
fork(anchor) 事务（单事务，async 引擎）：
  1. [P1] 强制 flush 父分支未投影批次（或断言已追平）
  2. INSERT branches(新分支, forked_from_branch, forked_from_seq=anchor.seq, status='active')
  3. 有界表克隆（行数 O(实体数)，语句 ≤ 7 条 INSERT…SELECT）
       npc_profiles / npc_health / relationships / matter_state / structures / material_balances
  4. 语料表克隆（按分叉点截断，见 §3.6；id 重映射 + 指针重写 + vec 行重键）
       npc_memories / knowledge
  5. UPDATE branches SET status='abandoned', abandoned_at=? WHERE id=父分支
  6. COMMIT
```

- 步骤 3 的 6 张表全部是「改一列 `branch_id` 的值」或「PK 已是复合 → 直接换 `branch_id` 值」，
  **零 id 重映射**（`matter_state` / `structures` / `material_balances` 的主键含 `branch_id`，
  换值不撞；`npc_profiles` 需 0008-a；`npc_health` 是 autoinc，克隆得新 id 但无指针）。
- 步骤 4 是全部成本所在 → 与 pi 对账（§7）。

### 3.6 截断判据：分叉点之后的语料**不得**进入新时间线

若只 `INSERT…SELECT … WHERE branch_id=父` 全量克隆，会把父分支在分叉点**之后**写入的记忆一并带进新分支
——玩家读档回到 earlier 时刻，却发现 NPC 记得「还没发生的事」。这既是 T1 信息边界问题，也是出戏问题。

| 表 | 截断判据 | 依据 |
|---|---|---|
| `npc_memories` | `COALESCE(event_seq, -1) <= F AND created_at_tick <= fork_tick` | `event_seq`（NULL = 推理转述）+ `created_at_tick`（模型已有列） |
| `knowledge` | `COALESCE(evidence_seq, -1) <= F AND learned_at <= fork_tick` | `evidence_seq`（witnessed 锚定）+ `learned_at`（模型已有列） |
| `relationships` | **不截断，全量克隆** | 无 seq 概念；正确性**完全依赖 P1 + 同事务 abandoned** |
| 其余 6 张 | **不截断，全量克隆** | 同上（投影值即分叉点状态） |

- **冲突态 fail-closed**：`event_seq <= F` 但 `created_at_tick > fork_tick`（或 knowledge 的镜像情形）
  在 P1 成立时**不可能出现**；一旦出现说明投影/事件序已错乱 → 建议**拒绝 fork**（而非静默取其一），
  并作为一条 T1 钉子（诊断用）。
- 在 P1 成立的前提下，两个谓词都等价于「全量」——截断是**纵深防御**，防的是「fork 落在两批之间」的历史实现。

### 3.7 fork 的原子性：两套连接（缝 3）

| 面 | 连接 | 能否并入 fork 单事务 |
|---|---|---|
| `branches` / `events` / 全部 SQLAlchemy 投影表 | async aiosqlite（`SqlEventStore.session_factory`） | ✅ |
| `npc_memories`（经 `SqlMemoryStore`） | **同步 sqlite3**（`memory_store.py:26`） | ❌ 两条独立连接 |

三个选项：

| 选项 | 做法 | 评价 |
|---|---|---|
| (a) 接受两阶段 + journal | fork 先在 async 事务建分支/克隆投影/标 abandoned，再在同步连接克隆 memories；加 `fork_journal(branch_id, stage, done)` 供崩溃续跑 | 可行但引入恢复协议（多一个状态机） |
| (b) 把 `SqlMemoryStore` 迁 async | 与全部持久层统一 | 干净，但改 M3 收官代码 + 触碰 S5 治理语义（codex 域），**超出本单** |
| **(c) 推荐** | **clone 走 async 引擎直写 `npc_memories` 表**（`INSERT … SELECT` 批处理），不经 store 类 | fork 是**冷路径批处理**不是热路径；绕过 store 类可接受（store 类的存在理由是「唯一写入口 + S1 纪律」，而克隆是**字节复制既有合规行**，不产生新内容、不经 LLM、不经扫描面）。崩溃语义 = 单事务回滚，无 journal |

**建议 (c)**；若 codex 判定「npc_memories 的任何写入都必须经 store 类」→ 退 (a) 并接受 journal。

### 3.8 与 §12 体积治理的相容性（先算清，别误报）

| 项 | 单分支 | 分叉 F 个 | 备注 |
|---|---|---|---|
| 快照（治理后：8 热 + 每日首） | 9 份 × ≤5MB ≈ **45MB** | ×F | §12 的「430MB/游戏日」是**不治理**的原始量（86 份/日），治理后不是约束项 |
| 语料克隆（memories + knowledge + vec） | 0 | **×F，且每次读档再克隆一份** | **真正的体积杀手**（§7 对账点 2） |
| events 段 | 与分支数线性 | ×F | 每分支各写各的，总量≈并集 |

结论：**§12 的「主库稳态 <2GB」在快照侧不破**（45MB/分支 × F=20 分支 ≈ 900MB）；
**破口在语料克隆**（每次读档复制一份完整语料 + 向量）。这条必须与 pi 的体积模型对账后再定 F 的上限。

---

## 4. Q3｜玩家档游标表 schema 草案

### 4.1 定位：游标**不复制世界态**（派单要求，也是硬约束）

玩家档 = **一个指向世界档的坐标** + **玩家所有权的一份覆盖**。

- **不做**：把世界状态（NPC 档、关系、记忆、物质态）序列化进 anchor。做了就等于第二份真相源，
  与 C4 唯一写路径、C6 append-only、§19 禁止事项全线冲突。
- **做**：`agent_override` —— 但它必须小、封闭、可重放（§4.4）。

### 4.2 现有列逐列复核（`models.py:97-110` / `schema.md` §4）

| 列 | 现状 | 复核结论 |
|---|---|---|
| `id` | TEXT PK（12 hex 不透明串，与 kilo 的 anchor id 约定一致） | ✅ 保留 |
| `name` | TEXT NOT NULL | ✅ 保留（玩家命名，§12「自由创建、命名、回退」） |
| `branch_id` | TEXT NOT NULL | ✅ **游标第一半**；可指向 abandoned 分支（读档目标） |
| `tick` | INTEGER NOT NULL | ✅ 游标的时间面；用于「找最近快照」 |
| `seq` | INTEGER NOT NULL | ✅ **游标第二半**；= 该分支事件流中「已包含的最后一条事件 seq」 |
| `agent_override` | TEXT NOT NULL DEFAULT `'{}'` | ⚠️ **无 schema、无版本、无校验** → §4.4 |
| `created_at` / `updated_at` | REAL | ✅ 保留（`updated_at` 兼作「回退后重写」时间戳） |
| — | — | 🟡 缺 `protected`（kilo K7 已把 `player_anchors.protected` 列为待迁移项）→ 建议**并入同一支 0008**，避免两支迁移改同表 |
| — | — | 🟡 缺 override 版本号 → 建议落在 `agent_override` JSON 内（`"v"`），不单独开列 |

### 4.3 建议新增（**只提案**）

| 列/约束 | 建议 | 理由 | 归属 |
|---|---|---|---|
| `protected` BOOLEAN NOT NULL DEFAULT 0 | 采 | 与 kilo K7 锚点 CRUD 的「保护档不可删」对齐；**同支 0008** | 跨域（kilo 提出，我域落迁移） |
| `UNIQUE(branch_id, seq)`？ | ❌ 否 | 一个分支上多个 anchor 指向同一坐标是合法的（不同名字的同一时刻） | — |
| `created_from_anchor_id` TEXT NULL | 🟡 挂起 | 只为前端画存档树；不进数据语义 | 待裁 |
| `snapshot_hint_seq` | ❌ 否 | `latest_snapshot(branch, before_tick)` 已能定位（§12 现有协议），加列=第二真相源 | — |

### 4.4 `agent_override` 封闭 schema 草案（A5 的核心）

**为什么必须封闭**：T2 要求「同一 anchor 载入两次 → 逐位一致」。若 override 是自由 JSON 且应用逻辑
依赖「缺失键=保持原值 / 未知键=忽略」这类隐式语义，那它就是**未定义的折叠输入** → 破 T2。
若它是**版本化封闭模型 + 纯函数**，它就是折叠链的一等公民。

草案（形状以仓内已有 `HiddenState`（M2-S2）/ `MatterSnapshot`（M2）的 frozen + `extra="forbid"` 体例为准）：

```
agent_override = {
  "v": 1,                          # 版本；未知版本 → fail-closed（对照 advance_build 的
                                   #   UnknownBuildRuleError 先例：绝不回落）
  "npc_id": "<主角 entity_id>",
  "body": {                        # 身体覆写（对应 §13 健康档的玩家所有权部分）
     "position": {"x": int, "y": int},
     "inventory": [ {"item_id": str, "count": number} ],   # 数量域约束（同 MatterPayload 的 ge/le）
  }
}
```

约束清单：

| # | 约束 | 对齐先例 |
|---|---|---|
| 1 | `extra="forbid"` + 封闭版本号 | `HiddenState`（M2-S2）、`MatterPayload`（M2-D6 29 钉子） |
| 2 | 数量/坐标域约束（`ge/le`、`allow_inf_nan=False`） | `MatterPayload` 同款；防止 NaN 静默进世界态 |
| 3 | 应用入口是**纯函数** `apply_override(world, override) -> world`，进折叠链；禁止就地改内存态 | §19 禁止事项「不要为世界状态直接赋值」 |
| 4 | **override 不得承载叙事文本**：只改状态面，不改 `content`/`monologue`；LLM 文本永远走 S1 写入门 | S1/S4（拒写不落库）、M5-K8 三形态投递面 |
| 5 | 未知 `v` → 抛错不静默忽略 | `UnknownBuildRuleError`（M4-D2b） |
| 6 | 落库形态：JSON **列**（现状）即可；若要可查询才升格为子表 | 现状 `agent_override TEXT DEFAULT '{}'` 已够 |

**反模式（明令禁止）**：`agent_override` 里塞 `{"world_state": {...}}` / `{"relationships": [...]}` /
`{"memories": [...]}` —— 那是把世界态复制进玩家档，直接违反 §4.1。

### 4.5 读档侧的「override 与事件流的关系」

- override **不是事件**：它是玩家意图的落点，**不产 `events` 行**（否则玩家档就成了世界档的一部分，
  而 §12 明确「世界档 append-only 含全部废弃分支」是世界的，玩家档不属于世界）。
- **推论（须裁决）**：override 生效后，新分支的物化态 = `fold(父前缀, F)` + `override` + `fold(子分支事件)`。
  若要把 override 变成可审计/可重放的**事件**，需要一个新 kind（触 §19 事件白名单 + codex 复核）→ 待裁点 8。

---

## 5. Q4｜fold 跨分支正确性条件

对照 D4 治理七列的先例「**继承失效、不继承替代**」（`_cascade` 广度递归、只置 `invalidated` +
`invalid_reason`、表内无替代指针、已失效行幂等不重写、仍向下遍历）。分叉语境下要追加的条件：

| 编号 | 条件 | 现状 | 落地形态 |
|---|---|---|---|
| **C1** | **fold 器/级联必须分支参数化，只读本分支** | ✅ 大部分已满足：`materialize_matter_replay` / `materialize_structures_replay` 走 `read_range(self._branch_id, …)`；`KnowledgeStore._cascade` 每条查询都带 `branch_id`（D4 R4） | 补钉子：同 id 跨分支各重建（`test_replay_branch_isolated` 已是此形，扩到语料三表） |
| **C2** | **折叠规则单一来源——分叉不许引入第三套语义** | ✅ `fold_matter_snapshot` / `fold_structure_snapshot` / `fold_material_balance` 三处都被快照路径与重放路径共用（M3-C2 逐位相等的纪律） | 分叉重放**必须**调同一批 fold 函数；新增「分叉专用折叠」= 违规，CR 拦 |
| **C3** | **治理态随克隆集整体继承；级联绝不跨分支** | ✅ `_cascade` 带 `branch_id`；克隆把治理列一起带走（`invalidated` / `invalid_reason` / `superseded_by` / `source_knowledge_id` / `source_memory`） | 钉子：子分支里某条 knowledge 已失效 → 重级联不重复计数、不改 `invalid_reason`；父分支后续治理动作**不影响**子分支（父已 abandoned，本就无新写入） |
| **C4** | **证据链跨分支会悬空**：`knowledge.evidence_seq` 锚定的是**父分支**的事件（事件不克隆） | ❌ 现无解析规则 | 三选一（待裁点 4）：①加 `evidence_branch_id` 列（0008-d，引用变二元组，最干净）；②定义谱系解析（沿 `forked_from_branch` 上溯）；③置 NULL（**否决**：信息销毁，违 §19） |
| **C5** | **向量候选集必须分支内** | ✅ **已落（M5-D2 / 裁 11）**——见下 | **M5 硬前置**：`vec_candidate_ids` 召回 SQL 加 `AND m.branch_id = ?`（同句 push-down，不是 Python 侧后过滤，R2 纪律）；`branch_id` **必填 + keyword-only + 无默认**（fail-closed：fork 后新分支不是 `'main'`，默认值会静默读到错分支）。配 T1 钉子 `TestVecBranchIsolation`（6 例）。⚠️ 附带发现：`k` 是 vec0 在过滤**之前**的取回上限 → 分支过滤会使候选少于 `top_k`（多分支下语料按分叉数复制，最近邻易被他分支占满 → **候选饥饿**），故加 `RECALL_OVERFETCH_FACTOR=4` 过取后裁到 `top_k`（钉子 `test_branch_filter_does_not_starve_local_candidates` 实测：系数改 1 即红）。F>4 时仍会饿 → **per-branch 向量分区**（vec metadata partition / 按分支建表）列为后续件 |
| **C6** | **分支身份先于一切**：任何 fold 前先确认目标 `branch_id` 存在且 `status='active'` | 🟡 `event-sourcing.md` §2.2 步骤 2 写了「branch_id 存在且 status=active」，但 `store.append` **未实现**该校验 | fork 后旧分支仍可能收到 append（driver 漏闸）→ 建议在 `append` 入口加 fail-closed 校验（待裁点 5） |

---

## 6. Q5｜T2 回放逐位一致在「分叉重放」下的口径

### 6.1 语料身份之争（前置，影响 §3.4 成本）

克隆 `npc_memories` 时 `entry_id` 怎么办：

| 案 | 做法 | 成本 | 风险 |
|---|---|---|---|
| **(i) 克隆时重映射 `entry_id`**（推荐 v1） | 新 uuid；同事务建 `old→new` 映射并重写 `superseded_by` | O(行数) 映射表 + 指针重写；**零 schema 改动、零既有代码改动** | 映射表与 `INSERT…SELECT` 的两步耦合（先插后改指针，同事务可行）；链式一致性须核对 |
| (ii) 保留 `entry_id` + `UNIQUE(branch_id, entry_id)` | 克隆是纯字节拷贝 | 需 0008-b（索引重建） | ⚠️ `SqlMemoryStore.supersede` / `get` **不带分支过滤**（`memory_store.py:91-111`；其中 `get` 的跨分支可读是 **S5 审计面的明文设计**）→ 同 `entry_id` 跨分支共存会让 `supersede` 的 `UPDATE … WHERE entry_id=?` **一次命中多行 → 跨分支治理污染**。要采此案必须先给治理面加分支过滤，**触 S5 语义（codex 域）** |

**建议 (i)**；(ii) 留待裁（若未来语料量级让 O(行数) 映射成为瓶颈再启）。

### 6.2 三种重放与断言

| 编号 | 重放 | 定义 | 断言 |
|---|---|---|---|
| **R1** | 同分支重放（**现状**） | `fold(events[b], 1..N)` | == `materialize(b)` 逐位相等（M3-C2 已钉：matter；D2b/D2d 已钉：structures / balances） |
| **R2** | **分叉重放**（新） | `fold(events[父], 1..F)` 接 `fold(events[子], 1..M)` | 见 A/B/C 三条 |
| **R3** | 分叉重放 × 冷启对照 | 子分支首读走「克隆结果」，另一路走「纯事件重放 R2」 | 两者**逐位相等**（把 §3.2 的「克隆 vs 重放」变成可执行断言，而不是口头等价） |

**R2 的三条断言**（这就是派单问的「断言什么」）：

| 断言 | 内容 | 抓什么 bug |
|---|---|---|
| **A｜接缝一致** | `子分支克隆所得物化态 == fold(events[父], 1..F)` **逐位相等** | 克隆漏表/漏列/错截断（§3.6）、P1 未追平（§3.3） |
| **B｜段内一致** | `fold(events[子], 1..M)` 逐事件推进 == 在线投影逐步结果 | 折叠规则分叉（C2）、投影/重放两套语义 |
| **C｜前缀无关** | 父分支在 F 之后**再追加 N 条事件**，重跑 R2 → 子分支结果**逐位不变** | 跨分支泄漏（F3 向量召回、C4 谱系引用）、谱系回退读（案 C） |

**C 是 F3/C4 的照妖镜**：只要有任何一处读面跨了分支，往父分支追加事件就会改变子分支的重放结果。

### 6.3 RNG 与 seed 口径（分叉下的确定性）

- 现状：确定性流靠 seed，熵注入靠 `entropy_log.value` 落库重放（`event-sourcing.md` §5）。
  `branches` 表**当前没有 seed 列**。
- 分叉要复现，子分支的初始 RNG 状态必须**等于父分支在 F 时刻的流状态**，否则接缝处行为跳变（断言 A 抓不到，
  因为 RNG 不在物化态里 → **要单列一条断言 D**）。
- 草案（三选一）：

| 选项 | 做法 | 评价 |
|---|---|---|
| (a) | `branches` 加 `seed INTEGER`；分叉时新分支 seed = 由世界 seed 确定性重放到 F 派生 | 纯函数、可复现；需新增「重放到 F 得流状态」的能力（可能昂贵） |
| (b) | 分叉时把父分支 F 时刻的 RNG 流状态**序列化进新分支的第一份快照** | 一次性成本；快照已有 gzip 通道；无新列 |
| (c) | 不管，让子分支用新 seed | ❌ **否决**：接缝处「确定性混沌」行为跳变，破坏 T2 精神（世界看起来不连续） |

- 铁律对齐：seed **不出现任何戏内接口**（§11）——本节所有 seed 讨论纯属存储面。

### 6.4 「可比字段集」白名单（否则 T2 分叉后必然假红）

逐位一致**不可能**覆盖的字段，必须显式排除并写进断言：

| 排除项 | 原因 | 处置 |
|---|---|---|
| `created_at`（unixepoch 落库时钟） | 墙钟 | 排除 |
| `npc_memories.id` / `knowledge.id` / `npc_health.id`（autoinc） | 克隆必换 id | 排除（比较业务键：`(branch_id, entry_id)` / `(branch_id, holder_id, fact)`） |
| `npc_memory_vec.rowid` | 跟随 `npc_memories.id` | 排除（比较向量**内容**的话另立断言） |
| `embedding` | LLM 嵌入非逐位稳定 | 排除；克隆路径要求**字节拷贝**（V4：vec 表为准），可另钉「克隆后向量字节相等」 |
| `entropy_log.id` | autoinc | 排除（比 `(branch_id, stream, tick, value)`） |
| `is_cold` / `abandoned_at` / `updated_at` | 归档与时钟面 | 排除 |
| `last_accessed_tick` | 读侧副作用 | 排除（**注意**：读档/回放不得改它，否则回放不纯） |

**建议**：定义一个 `COMPARABLE_FIELDS` 显式集合 + 「排除项必须有名字」的断言纪律，
让 T2 假红时能立刻分辨「真不一致」还是「比较了不可比字段」。

### 6.5 测试落点

| 文件 | 用例数 | 状态 |
|---|---|---|
| `sim/tests/test_t1_m5_history_preserved.py` | **6** | ✅ **已落（M5-D2）**：C6 断言（`(branch,seq)` 对集合）+ **可证伪性二阶守卫**（删父补子必红、旧口径必绿）+ abandoned 不删行 + append 不改历史行 + 跨分支 seq 重叠不撞主键 |
| `sim/tests/test_t1_m5_fork_replay.py` | 6–8 | ⏳ 未落：R2 的 A/B/C + 断言 D（seed 连续）+ 可比字段集守卫（随 fork 事务件） |
| `sim/tests/test_m5_fork_clone.py` | 6–8 | ⏳ 未落：克隆完整性（12 表覆盖）+ 截断判据 + id 重映射指针自洽 + vec 行重键 + 冲突态 fail-closed + 事务回滚无半写（随 fork 事务件） |
| `sim/tests/test_t1_m3_vec_governance.py`（改） | **+6** | ✅ **已落（M5-D2）**：`TestVecBranchIsolation`（跨分支不召回 / 父分支不可见 / 未知分支空候选 / 不过取不饿死 / 谓词在召回句内 / 签名 fail-closed）；既有 4 条治理钉子零回归 |

---

## 7. Q6｜与 pi M5-P1 的交叉对账 —— ✅ **已回填（pi M5-P1 交付，2026-09-27）**

> pi 侧同单：M5 perf 预研「时间刻度 + 双轨存档」= `docs/perf/m5-time-scale-fork-budget.md`。
> 对账模式沿用 M4：他出**实测常数与红线**，我出**存储形态与公式**。下表第三列已由
> pi 回填（其 §4.6），第四列是我对回填的**复核与一处口径修正**。

| # | 对账点 | 我的口径（存储侧公式/判据） | pi 回填（实测常数，本机暖态中位） | 复核 / 我要补的 |
|---|---|---|---|---|
| 1 | **单次 fork 的克隆行数** | 6 张有界表 = O(实体数)；2 张语料表 = O(P×D)，D = 分叉时游戏日数 | 克隆 **0.608µs/行**（纯文本）/ **5.090µs/行**（含 1536B 向量 blob）；有界表不随 D 增长 | ✅ 一致。`T_clone ≈ 文本行×0.61µs + 向量行×5.09µs` 直接可用 |
| 2 | **语料体积（真正的杀手）** | bytes ≈ 行数 × (行宽 + 1536B 向量)，∝ 分叉次数 F | 单记忆行 json ≈ **2535B**（向量占 1536B）；向量化后每行 ~4–8x 纯文本行 | ✅ 一致。**F 的体积上限仍待真语料量级**（10 游戏日 × 50 NPC 的实际行数未实测） |
| 3 | **快照侧是否破 §12 的 2GB** | 治理后 9 份/分支 × ≤5MB ≈ 45MB/分支 → 快照侧非瓶颈 | 本机 pos-only 快照 gzip **447B**（50 实体）；全量含属性**未实测**；快照摊销 0.00045ms/tick | ✅ 双方同结论（快照侧非瓶颈）。**遗留**：DESIGN §12 的「≤5MB/份」至今无人实测，建议 M5 真快照落地时补测（否则体积预算无依据） |
| 4 | **fold 成本：克隆 vs 前缀重放** | 4 张有 fold 器的表：重放 O(事件数) vs 克隆 O(投影行数) | 重放 **0.74µs/事件**、克隆 **5.09µs/行**；**交叉判据 r = 0.145**（行数/事件数 < 0.145 时克隆更便宜） | ⚠️ **口径修正**：`r=0.145` **只适用于 4 张有 fold 器的表**。语料三表**无重放路径**（F2：无事件源），克隆 5.09µs/行是唯一形态，不参与该交叉。pi 该行已注明 F2，此处把适用边界写死，免得后人对语料表说「重放更便宜」 |
| 5 | **F3 加分支过滤的检索成本** | 同句 push-down（非 Python 侧后过滤），预期≈0 | ⏳ 待实测（他明确写「本件无法在 D1 未收编前测其 SQL」） | ✅ **本单（M5-D2）F3 已落地 → 现在可跑 before/after**。另请 pi 顺带实测 **over-fetch**：`k` 由 `top_k` 变为 `top_k × RECALL_OVERFETCH_FACTOR(4)` 的距离计算增量 |
| 6 | **读档端到端墙钟** | 建议进 `PI_BENCH_ADVISORY` 口径 | 同意 advisory；分解 = flush + 克隆 + 首次物化；读档应后台不阻塞 tick | ✅ 一致（与 M4-P1 摊还先例同款） |
| 7 | **快进档 × 读档交互** | clone 事务内不逐行 Python（须 `INSERT…SELECT` 批量） | 强支持：`append` **78.7µs/事件**；60× 档 1.57ms/tick ≫ 0.277ms 预算 → 必批量 flush；读档期间快进挂起 | ✅ 一致，且与我 §3.7「clone 走 async 引擎直写」同诉求（批量事务摊销） |
| 8 | **多分支同时物化的驻留** | 驻留 = N × 单分支物化态 | 单分支轻量 profile dict **11.5KB**（50 NPC 骨架）；上限按 `SOAK_RSS_GROWTH_LIMIT_MB=128` 精神反推 N | ✅ 一致。「档预览是否要同时物化 N 分支」是**前端域待裁**，未定前不做驻留优化 |
| 9 | **摊还/降级对本稿的影响** | 降级**不得改变折叠规则**（否则破 C2 / R2-B） | 一致：「降级只改节拍、不改规则」，批处理窗口 fold 必须调同一批 `fold_*` | ✅ 闭环，无待办 |


---

## 8. 待裁点汇总

| # | 待裁 | 我的建议 | 裁谁 | 关联 |
|---|---|---|---|---|
| 1 | `npc_profiles` PK 改复合（**F1**） | 必落 0008-a，照 0006 模板 | Claude（+ 我施工） | §2.6 |
| 2 | `global_seq` 加不加 | M5 不落则**不加**；先落零迁移的案 C 断言口径 | ✅ **已裁 = 不加**（`m5-rulings.md` §B 裁 2），案 C 口径 ✅ 已落 | §2.5 |
| 3 | 跨分支 `parent_seq` 悬空怎么解 | 加 `parent_branch_id` 列 / 定义谱系解析 / 置 NULL（后者否决） | Claude | §2.1③ |
| 4 | `knowledge.evidence_seq` 跨分支悬空（C4） | 加 `evidence_branch_id`（0008-d） | Claude | §5-C4 |
| 5 | `append` 是否校验 `status='active'`（C6） | 落 fail-closed 校验，防 fork 后误写父分支 | Claude | §5-C6 |
| 6 | fork 原子性方案 | 采 (c) clone 走 async 引擎直写；若 codex 判「必须经 store 类」→ 退 (a)+journal | Claude + **codex** | §3.7 |
| 7 | 是否给 memories/knowledge 补 `*.written` 事件（解 F2） | **M5 不做**（改冻结事件基线 + 触 S1/X7）；列为中长期，先记提案 | Claude + **codex** | §3.2 |
| 8 | `agent_override` 要不要变成事件 | M5 不做（保持玩家档不产事件） | Claude | §4.5 |
| 9 | `player_anchors.protected` 并入 0008 | 采（与 kilo K7 合并，同表一支迁移） | Claude + kilo | §4.3 |
| 10 | 语料 `entry_id` 克隆策略 | 采 (i) 重映射（零 schema）；(ii) 留待裁 | Claude（(ii) 需 codex） | §6.1 |
| 11 | **F3 向量召回分支隔离** | **M5 硬前置**，fork 存在之前必须补 + 钉子 | ✅ **已裁并已落**（`m5-rulings.md` §B 裁 11 = 采；M5-D2 实施 + 6 钉子） | §5-C5 |
| 12 | anchor 热钉 vs 分支冷归档（A6） | 采「anchor 引用即热钉」 | Claude | §3.8 / §4.1 |

---

## 9. 建议实施顺序（裁决后）—— 进度

1. ✅ **零迁移先行**（**M5-D2 已落**）：T1 断言 5 口径改 `(branch_id, seq)` 对集合 + 可证伪性守卫（§2.4 案 C / §6.5 第 1 行，6 钉子）。
2. ✅ **F3 前置**（**M5-D2 已落**，裁 11）：向量召回分支隔离 + T1 钉子（+6 例）。附带 `RECALL_OVERFETCH_FACTOR`（候选饥饿防御，见 §5-C5）。
3. ⏳ **0008-a（F1）**：主键改复合 + 全量单键查找清点与改双键（等裁 1）。
4. ⏳ **fork 事务 + 克隆**：P1 前置条件 → 6 张有界表克隆 → 语料表截断克隆 + id 重映射 + vec 行重键 → 原子性（等裁 6/10）。
5. ⏳ **R2 三断言 + seed 连续（断言 D）** + 可比字段集（可与 3/4 并行）。
6. ⏳ **可选尾巴**：`parent_branch_id`（裁 3）、`evidence_branch_id`（裁 4）、`protected`（裁 9）。`global_seq` **已裁不落**（裁 2）。
7. ⏳ **后续件（施工中发现，非本轮裁）**：per-branch 向量分区（F>4 时向量召回候选饥饿的正解）→ 需提案。

## 10. 本文边界与门禁

- 零代码、零 schema、零迁移、零测试；不改任何既有文档（`schema.md` / `event-sourcing.md` 的回写
  随裁决落地一并做，避免本稿与实现漂移）。
- 本文所有「实测」结论均给出仓内位置（文件:行号 / 表名），可复核；
  所有「预估」均标注为公式或算例，**不含任何未实测的性能数字**。
- 跨域只登记不施工：driver 的 fork 编排与 store 实例 rebind（架构域）、`player_anchors.protected`
  的路由面（kilo）、S5 治理语义与新事件族（codex）。
- 登记：`docs/README.md` §2 文档索引（随本单提交）。
