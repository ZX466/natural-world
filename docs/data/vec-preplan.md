# npc_memory_vec 预研（M3 向量检索前置调研）

> **状态**：M3 预研，**零代码零依赖安装**（`sqlite-vec>=0.1.6` 已是 pyproject 依赖且已装）。
> 归属：数据 / 数据库域（opencode）。对齐 `docs/data/schema.md` §5/§6/§10、
> `sim/core/persistence/vector.py`（M1 脚手架，仍锁 M3）、`sim/npc/memory.py`（M2-D3 打分缝）。
> 本文件只做**调研与缝标注**，不含实现；实现方案待 M3 派单 + 需要时报告用户装包。

---

## 1. 现状锚点（已有资产，勿重复造）

| 资产 | 位置 | 状态 |
|---|---|---|
| `npc_memories.embedding` 列 | schema §5；`models.py:179` `LargeBinary, nullable=True` | **已建**（M3 填） |
| `npc_memory_vec` vec0 虚拟表 | schema §6 | 锁 M3；DDL 在 Alembic 范围外（需 LOAD EXTENSION） |
| 脚手架 `vector.py` | `sim/core/persistence/vector.py` | `load_sqlite_vec` / `create_memory_vec_table(dim=384)` / `memory_vec_exists` 已备 |
| 依赖 | `pyproject.toml:19` `sqlite-vec>=0.1.6`；`numpy>=2.1` | **已装**，无需新增 |
| 打分缝 | `sim/npc/memory.py`：`retrieve`/`Scorer`/`MemoryHit` | M2-D3 已落地；M3 只换**候选生成器**，API 形状不变（§18） |
| MemoryEntry | `sim/llm/memory_scan.py:44` | 目前 **无 `embedding` 字段**（DB 列在、dataclass 未加） |

**关键约束（§18）**：`npc_memory_vec` 在 M3 的角色 = **候选生成器**，替换/前置
目前的 `iter_visible(npc_id)`；打分仍是 `base_score × Π(Scorer)`，**向量只影响「取哪些候选」，
不影响「怎么打分」**——这是与 M2 缝的硬边界。

---

## 2. sqlite-vec vs 手写余弦：对比

### 2.1 方案 A — sqlite-vec（vec0 虚拟表）

```sql
CREATE VIRTUAL TABLE npc_memory_vec USING vec0(embedding FLOAT32[384]);
-- 检索
SELECT rowid, distance FROM npc_memory_vec
WHERE embedding MATCH ? AND k = 20 ORDER BY distance;
```

| 维度 | 评价 |
|---|---|
| 召回 | 内置 ANN / 暴力，`k=` 近邻 + `distance`，SQL 内完成 |
| 集成 | 与 SQLite 同进程；`rowid` ↔ `npc_memories.id` 天然关联 |
| 维度 | **固定**（vec0 要求，§6 已注 384 或 768） |
| 依赖 | 已是项目依赖 + 已装；需连接 `enable_load_extension`（`vector.py` 已封装） |
| 代价 | 无 Python 侧矩阵运算；扩展加载一次性 |
| 风险 | 扩展加载在 aiosqlite/async 下的连接处理（见 §5 缝）；维度一改要重建表 |

### 2.2 方案 B — 手写余弦（numpy，内存/全表扫）

```python
# 伪代码：候选 = 本 npc 可见条目 → 全量余弦 → top_k
q = q / np.linalg.norm(q)
M = np.stack([e.emb for e in candidates])      # (n, d)
sims = M @ q                                    # (n,)
top = np.argsort(-sims)[:k]
```

| 维度 | 评价 |
|---|---|
| 召回 | 精确（暴力余弦 = ground truth，无 ANN 近似误差） |
| 集成 | 纯 numpy，无扩展；但需把 embedding 从 DB 读出到内存 |
| 维度 | 任意（不锁 vec0 约束） |
| 依赖 | numpy 已在 |
| 代价 | 每 NPC 每检索 O(n·d) 内存运算；n 大了要反复反序列化 BLOB |
| 风险 | 无索引 → n 增大后线性退化；「读全部 BLOB」I/O 随 n 涨 |

### 2.3 对比结论（M3 建议）

| 判据 | A sqlite-vec | B 手写余弦 | 采纳 |
|---|---|---|---|
| 50 NPC 千级量级性能 | 优（k-NN 剪枝） | 可接受（见 §3） | A |
| 精确性 | 近似（可调） | 精确 | 平手（量级小，A 的近似无感） |
| 维度自由度 | 固定 | 任意 | B（但可锁维度换 A 的索引） |
| 集成复杂度 | 中（扩展加载） | 低（纯 numpy） | B |
| 与 SQL 同源 | 是（SQL 内） | 否（搬内存） | A |

> **倾向 A（sqlite-vec）+ 短线 B 兜底**：量级小（§3）两法都够快，但 A 与 SQLite
> 同源、`rowid` 直连、免反序列化，且 `vector.py` 脚手架已就绪；B 可在 A 的扩展
> 加载在 async 下出问题时作**降级路径**（同 `VectorIndex` 接口两实现）。
> **最终裁决留 M3**：本预研只给对比与缝，不选型硬编码。

---

## 3. 量级估算：50 NPC × 千级记忆

**假设**（M3 目标量级，保守取大）：

| 量 | 值 | 依据 |
|---|---|---|
| NPC 数 | 50 | MVP 固定（§1.3） |
| 每 NPC 记忆条数 | 1,000 | 「千级」（含被 supersede 的治理条目） |
| 可见（`superseded_by IS NULL`） | ~60%≈600 | `iter_visible` 视图（§5/S5） |
| 维度 d | 384 | `DEFAULT_EMBEDDING_DIM`（或 768） |

**总规模**：50 × 1,000 = **5 万条**；可见 ≈ **3 万条**。

**单 NPC 检索**（候选 600 条）：
- 存储：600 × 384 × 4B ≈ **0.92 MB**（FLOAT32）；全库 5 万条 ≈ 77 MB。
- B 手写余弦：600×384 ≈ **230K 次 MAC** ≈ numpy 亚毫秒级（<1ms）。
- A sqlite-vec：vec0 `k=20` 近邻，量级同亚毫秒。

**单 tick 广播检索**：若 50 NPC 各检索一次 → 50 × 亚毫秒 ≈ **<50ms/tick**（B）；
A 类似或更好。**结论：两方案在 M2/M3 目标量级均非瓶颈**，选型应以**集成/确定性**优先，
而非性能。真正要盯的是 **embedding 生成**（LLM/API，见 §4）——那才是开销大头。

**写出（写记忆时算 embedding）**：5 万条若逐条实时调 embedding API，成本/延迟需治理
（批量化 + 缓存 + 降级，M3 成本治理议题）。

---

## 4. embedding 来源缝（挂 LLM client，对齐 M1 单 profile 形）

**现状**：`sim/llm/client.py::LlmClient.complete(profile, messages, decision)` 是唯一 LLM
出口——**单 profile**（`ProfileSnapshot`：base_url/model/temperature/max_tokens），
api_key 调用瞬间解密用完即丢（K3），`llm.*` 监控口径对齐 `docs/perf/llm-monitoring.md`。

**embedding 是独立能力，不能塞进 `complete()`**（那是 chat completions，返文本 token）。
缝的设计原则：**同 profile 生命周期、同监控口径、同 key 安全纪律，但独立方法**：

```
# 缝草案（M3 实现时落地，非本批）
@dataclass
class LlmClient:
    ...
    async def embed(
        self,
        profile: ProfileSnapshot,      # 复用同一 profile 形（base_url/model/key）
        texts: list[str],              # 批量（成本治理：一次多条）
    ) -> list[list[float]]: ...        # 与 texts 等长；dim 由 embedding model 定
```

| 缝面 | 约定 | 对齐对象 |
|---|---|---|
| 调用形 | `embed(profile, texts) -> list[vector]`，**批量** | `complete(profile, messages)` 同为 `profile` 入参 |
| profile | 复用 `ProfileSnapshot`；embedding model 名可同 profile 的 `model` 或独立字段 | M1 client 单 profile 形 |
| key 安全 | 明文只在调用瞬间解密、用完即丢；绝不进日志（K3/K4 + `redact_sensitive`） | client.py 现有纪律 |
| 监控 | 加 `llm.embed_request/response/error`，口径同 `llm.*` | llm-monitoring.md |
| 降级 | embedding 失败 → 该条**退回标量检索**（不阻塞写入/检索）；世界照常转 | client.py「失败降级由上层」 |
| 维度 | profile 绑定 embedding dim，写入 `npc_memory_vec` 前**锁定**（§6） | schema §6 |
| schema | 是否给 `llm_profiles` 加 `embedding_model`/`embedding_dim` 列 = **M3 待裁**（本批不动） | §10 |

**独立 profile 的可能**：chat 模型（如 deepseek-chat）通常不产 embedding；embedding 多走
独立端点/模型（如 `text-embedding-3-small`、bge-m3）。故 §10 可能需**第二条 profile 缝**
（或 profile 增 `embedding_*` 字段）——**标注为 M3 裁决项**，本预研不擅改 schema。

---

## 5. 集成缝（与 M2 打分缝的接法）

```
retrieve(store, query, scorers=...)                      # sim/npc/memory.py，形状不变
   └─ 候选来源（M3 换此项）：
        M2:  store.iter_visible(npc_id)                  # 标量全量可见
        M3:  VecCandidateSource(store, vec_index)        # 向量 k-NN → entry_ids → 取 MemoryEntry
                   └─ 实现二选一：SqliteVecIndex(A) / NumpyCosineIndex(B)
```

- **缝的位置**：新增 `CandidateSource` 协议（`candidates(query) -> Iterable[MemoryEntry]`），
  `retrieve` 的 `isinstance(store, MemoryStoreLike)` 分支改为可注入候选源；
  `Scorer` 打分链**一字不改**（§18 边界）。
- **向量表 ↔ 记忆表关联**：`npc_memory_vec.rowid` = `npc_memories.id`（§6）；
  `npc_memories.embedding` BLOB 与 vec 表**双写**（M3 决定单一真相源：建议 vec 表为准，
  BLOB 列留迁移兼容）。
- **S5 过滤**：向量召回**后**仍须过滤 `superseded_by IS NOT NULL`（治理条目永不进候选）；
  A 方案下 vec 表不含被取代条目则可在写入时不同步，或召回后按 npc_memories 过滤。
- **async 连接**：`vector.py` 用**同步 `sqlite3`** 连接；aiosqlite 下 `enable_load_extension`
  需在底层连接操作（可能经 `conn.run_sync` 或独立只读连接）——**M3 集成风险点，标注**。
- **确定性（C5）**：向量距离相同 → 按 `entry.id` 稳定排序兜底（与 M2 同款）。

---

## 6. 待裁决项（报 Claude，M3 派单前）

| # | 议题 | 选项 |
|---|---|---|
| V1 | 索引实现 | A sqlite-vec（倾向）/ B numpy 余弦 / 双实现（A 主 B 降级） |
| V2 | 维度 d | 384（脚手架默认）/ 768；随 embedding model 锁 |
| V3 | embedding profile | 复用现有 profile 的 model / §10 增 `embedding_*` 列 / 第二条独立 profile |
| V4 | 单一真相源 | vec 表为准 / `npc_memories.embedding` BLOB 为准 / 双写一致 |
| V5 | 召回时机 | 每 tick 广播 / 按需 / 批量窗口（性能 vs 实时性） |
| V6 | 治理条目 | vec 表是否含被取代条目（写入策略） |
| V7 | 写路径 | embedding 生成挂 `MemoryWritePipeline.write()` 内联 / 异步补算（影响 S1 守卫边界） |

> V7 涉及**写路径与 S1 守卫边界**，是安全敏感项（Codex 复核域），M3 需先提案。
> 本预研零代码，不触碰写路径（§18 读侧 only 纪律不变）。

---

## 7. 结论（一句话）

`npc_memory_vec` 在 M3 只是**候选生成器**的替换，打分 API 形状与 S1/写路径纪律不变；
技术上 sqlite-vec 与手写余弦在 50×千级量级均非瓶颈，选型看**集成/确定性**，
真正成本在 **embedding 生成**（挂 LLM client 独立 `embed()` 缝，对齐 M1 单 profile + 监控 + K3/K4）。
本文件为调研稿，**实现待 M3 派单**；需装包或改 schema 前先报告用户/Claude。
