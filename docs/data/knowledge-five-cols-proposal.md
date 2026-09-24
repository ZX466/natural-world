# knowledge 五列扩展 + 级联失效 — B3 schema 提案（**裁 10 已全采，M3-D4 实施**）

> 数据域（opencode），M3-D3 B3，2026-09-23。**本文为提案**——按活跃约定
> 「schema 先提案 → Claude 裁决 → 再动代码」，**未动 models.py / 未出迁移**。
> 依据：`docs/security/m3-evidence-chain.md §5/§6`（codex M3-S2 提案语义）、
> `docs/security/m3-preplan.md §1 R1/R5/R6`（风险母本）、
> `docs/arch/m3-plan.md §3 批次 B`（B1 双列口径 / B3 合并提案）、
> `docs/data/schema.md §8`（现 knowledge 表）。
> 实现范围裁后：B3（本提案）→ R1 闭环。

> **裁决落定（2026-09-24，裁 10 全采；M3-D4 已实施）**：§8 四点全部按本提案主张落——
> ①七列拆分口径（4 语义 + 3 治理）②`invalidated` 独立位（不造 `superseded_by` 替代列）
> ③knowledge 落库**走写入门**（X7，不新增裸写）④级联触发点由**调用方串联**
> （存储层不互依赖；`session=` 入参把级联并进源记忆 supersede 的同一事务）。
> 实施落点：`0005_m3_knowledge_governance` / `models.py::Knowledge` /
> `sim/core/persistence/knowledge_store.py` / `sim/tests/test_t1_m3_knowledge_cascade.py`（20 用例全绿）。
> 本文档保留为**设计依据与理由留档**（含 §2.1 为何不用 `superseded_by` 的论证）。

## 0. 一句话

`knowledge` 表（`0002_m3_reserved` 已建空表）**缺治理列**：记忆可 supersede，
但其派生的知识永久有效 → 被治理的记忆借知识表复活，S5 旁路（R1）。本提案补
**5 列 + 1 索引 + 2 级联接口**，并定 supersede 传播语义（**继承失效、不继承替代**）。

## 1. 现状（0002 已建列，schema.md §8）

| 列 | 类型 | 约束 |
|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT |
| `holder_id` | TEXT | NOT NULL |
| `fact` | TEXT | NOT NULL（自由文本，X7 走写入门扫描） |
| `confidence` | REAL | NOT NULL（0.0–1.0） |
| `source` | TEXT | NOT NULL（witnessed/told/inferred） |
| `learned_at` | INTEGER | NOT NULL |
| `branch_id` | TEXT | NOT NULL |

索引：`idx_knowledge_holder(branch_id, holder_id)` / `idx_knowledge_source(branch_id, source)`。

**缺口**：无 `superseded_by`/`invalid_reason` 类治理列；无派生源键 → 无法级联失效。

## 2. 提案：新增列（§5 数据需求照抄 + 治理列）

| # | 列 | 类型 | 约束 | 语义 | 来源 |
|---|---|---|---|---|---|
| 1 | `subject_npc_id` | TEXT | NULL | 他人属性知识：主体 npc_id；**自身事实知识为 NULL** | evidence-chain §5 |
| 2 | `subject_attr_id` | TEXT | NULL | 属性主键（戏外，`f"{subject}.health_{id}"`）；自身事实 NULL | evidence-chain §5 |
| 3 | `evidence_seq` | INTEGER | NULL | witnessed：`npc.hidden_emerge` 事件 seq（持久层分配后回填） | evidence-chain §5 |
| 4 | `source_knowledge_id` | INTEGER | NULL | told：teller 的 knowledge 行 `id`（**链上回溯键**，级联递归用） | evidence-chain §5 |
| 5a | `source_memory` | TEXT | NULL | R1：派生源记忆 `entry_id`（反思/转述落库记录） | preplan §1 R1 |
| 5b | `invalidated` | BOOLEAN | NOT NULL DEFAULT 0 | R1/§6：级联或直接失效位（0=有效） | evidence-chain §5/§6 |
| 5c | `invalid_reason` | TEXT | NULL | 失效原因（结构化串，**不含 LLM 原文/词面**） | 同 `npc_memories` |

> 任务书「五列」= 上表 1/2/3/4 + 治理（5a/5b/5c 三合一，与 codex §5「治理列」一行对应）。
> 列名与 `npc_memories` 治理列对齐（`invalid_reason` 同名）+ 新增 `invalidated` 布尔位
> （knowledge 无「替代行」语义，需独立失效位）。

### 2.1 为什么 `invalidated` 是布尔位而非复用 `superseded_by`

- 记忆：supersede = 「旧条目被新条目替代」，`superseded_by` 指向替代行；
- 知识：**继承失效、不继承替代**（§6 终裁）——源记忆失效 → 派生知识**只失效**，
  不存在「知识 B 替代知识 A」的概念。故用 `invalidated` 布尔位（0/1），
  不做「替代链」。

### 2.2 约束（CHECK，迁移内以 `sa.CheckConstraint` 落）

- `source IN ('witnessed','told','inferred')`（已有语义，补 CHECK）；
- `confidence` 0.0–1.0；
- **形态约束**（软，应用层把关 + 文档；SQLite CHECK 表达力有限）：
  - `source='witnessed'` ⇒ `evidence_seq IS NOT NULL` 且 `subject_npc_id IS NOT NULL`；
  - `source='told'` ⇒ `source_knowledge_id IS NOT NULL`（链根自我披露例外：允许 NULL）；
  - `subject_npc_id IS NULL ⇔ subject_attr_id IS NULL`（成对：自身事实两列同 NULL）。

## 3. 提案：新增索引

| 索引 | 列 | 用途 |
|---|---|---|
| `idx_knowledge_source_memory` | `(branch_id, source_memory)` | 源记忆 supersede → 反查派生知识（R1 级联起点，O(log n)） |
| `idx_knowledge_source_kid` | `(branch_id, source_knowledge_id)` | told 链向下递归（级联传播，避免全表扫） |
| `idx_knowledge_subject` | `(branch_id, subject_npc_id, subject_attr_id)` | 按主体+属性查有效知识（evidence 判定 teller 行一致性） |

（现有两索引保留。）

## 4. 提案：级联失效接口

`KnowledgeStore`（新增，归属 `sim/core/persistence/`，形状对镜 `SqlMemoryStore`）：

```python
class KnowledgeStore:
    def __init__(self, conn: sqlite3.Connection, *, branch_id: str = "main") -> None: ...

    def supersede_source_memory(self, entry_id: str, reason: str) -> int:
        """源记忆被 supersede → 使该源派生的**全部** knowledge 行失效（R1 起点）。
        返回失效行数（0 = 无派生，幂等）。沿 source_knowledge_id 向下递归传播。"""

    def invalidate_by_source(self, entry_id: str, reason: str) -> int:
        """按派生源记忆 entry_id 失效（= supersede_source_memory 的别名/显式名）。"""

    def invalidate_by_row(self, row_id: int, reason: str) -> int:
        """直接失效一条 knowledge 行 + 沿 told 链向下递归传播。"""
```

**递归传播语义（§6 终裁）**：

```
失效种子（源记忆 supersede 派生行 / 直接指定行）
  └─ 置 invalidated=1, invalid_reason=reason
       └─ 沿 source_knowledge_id 找「以本行为 teller 行 id」的下游行
            └─ 递归（深度 = 传播深度，天然有界：told 链置信 floor 0.1 ⇒ ≤ 4 跳）
```

- **只失效、不替代**：下游行 `invalidated=1` 后不再产出/消费；无「替代行」指向。
- **幂等**：已失效行跳过（`invalidated=1` 不再改 `invalid_reason`）。
- **事务内**：与源记忆 supersede 同一事务（异常整批回滚，无半失效）。
- **分支隔离**：全部 SQL 带 `branch_id=self._branch_id`（R4 母本纪律）。
- **纯度**：读写只碰 `knowledge` 表；不改 `npc_memories`（源侧由 `SqlMemoryStore.supersede` 负责）。

## 5. 写入路径（R1 闭环）

- knowledge 落库**必须走写入门**（banned + hidden 双扫，X7；与记忆同工具同入口）——
  不在 `KnowledgeStore` 开裸 INSERT；实际写入归 `MemoryWritePipeline` 扩展或
  `sim/npc/propagation.py` 消费侧（B4/B5 已就绪，`retell` 现写 memory；知识表落库
  为 B3 新通路，须复用同一扫描）。
- `source_memory` 在落库时记录派生源 `entry_id`；源 supersede 回调
  `invalidate_by_source(entry_id)`（同事务）。

## 6. 迁移计划（**裁后**执行，本批不动）

- 新迁移 `0005_m3_knowledge_governance`（`down_revision = 0004_m2_npc_attributes`）：
  `op.add_column` × 7（1/2/3/4/5a/5b/5c）+ `create_index` × 3 + CHECK。
- `models.py::Knowledge` 同步加字段（同批）。
- **零漂移自检**：`upgrade head` → `revision --autogenerate` 须仅 `pass`。
- 空表（0002 预留）→ `add_column` 无需回填；`invalidated` 用 `server_default="0"`。

## 7. 对表（§6）

| 项 | 结论 |
|---|---|
| X8（自身属性扫描面） | 不变：`subject_npc_id IS NULL` 的行为自身事实，不涉他人隐藏属性 |
| S5/R1 | **继承失效、不继承替代**：源记忆 supersede → 派生 knowledge `invalidated=1`，沿 told 链往下；无替代行 |
| R4 分支隔离 | 全 SQL 带 `branch_id` |
| R3 双列口径 | knowledge 侧同理：**任一治理位非空即不可见**（`invalidated=1 OR invalid_reason IS NOT NULL`）；B1 终裁若取「双列任一非空」，本提案同口径 |

## 8. 待裁决点（**裁 10 已全采，见文首裁决栏**）

1. **五列拆分口径**：任务书「五列」是否按本提案 = 4 语义列 + 3 治理列（共 7）？
   或治理列合并为 1（如仅 `invalid_reason`）？ → **采纳 7 列**。
2. **`invalidated` 独立位 vs 复用 `superseded_by`**：本提案主张独立布尔位
   （knowledge 无替代语义）；若裁「统一双列」则改为 `superseded_by`+`invalid_reason`。
   → **采纳独立位**（codex 预审①同向：无替代行语义，别造 replacement 列）。
3. **落库入口**：`KnowledgeStore` 新增裸写 vs 扩 `MemoryWritePipeline`？
   本提案主张**不新增裸写**，knowledge 落库经写入门（R1/X7）。 → **采纳走写入门**。
4. **级联触发点**：`SqlMemoryStore.supersede` 是否直接持有 `KnowledgeStore` 回调，
   或由调用方（runtime/传播）串联？本提案主张**调用方串联**（存储层不互依赖）。
   → **采纳调用方串联**；`KnowledgeStore.invalidate_*` 的 `session=` 入参让调用方
   把级联并进同一事务（裁 10「supersede 事务内级联」）。

## 9. 交付物清单（**M3-D4 已全部落地**）

- [x] 迁移 `0005_m3_knowledge_governance`（add_column×7 + 索引×3 + CHECK×3，downgrade 回 0002 原型）
- [x] `models.py::Knowledge` 加 7 字段 + 3 索引 + 3 CHECK
- [x] `sim/core/persistence/knowledge_store.py`（`KnowledgeStore` + 级联 + 写入门 + `fill_evidence_seq`）
- [x] `schema.md §8` 更新（列/索引/约束/治理语义）
- [x] T1 钉子 `sim/tests/test_t1_m3_knowledge_cascade.py`（20 用例：R1 端到端 / 链断拒收闭环 / 幂等 / 分支隔离 / 同事务回滚 / 写入门 X7 / `evidence_seq` 回填）
- [x] `MemoryWritePipeline.decide` 抽出共用判梯 + `scan_fact` 供知识写入复用（记忆侧 116 用例回归全绿，行为不变）
- [ ] 传播侧 knowledge 落库接线（叙事文本由架构域 runtime/传播给出，本批只交付数据面形状与回填机制）

> 状态：**已实施待收编**。裁 10 依据见文首裁决栏；codex M3-S5 按钉子验收。
