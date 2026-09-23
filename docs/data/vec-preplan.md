# npc_memory_vec 预研（M3 向量检索前置调研）

> **状态**：M3 预研，**零代码零依赖安装**（`sqlite-vec>=0.1.6` 已是 pyproject 依赖且已装）。
> 归属：数据 / 数据库域（opencode）。对齐 `docs/data/schema.md` §5/§6/§10、
> `sim/core/persistence/vector.py`（M1 脚手架，仍锁 M3）、`sim/npc/memory.py`（M2-D3 打分缝）。
> 本文件只做**调研与缝标注**，不含实现；**V1/V4/V6 已裁决**（见 §7.1），
> V2/V3/V5/V7 挂 M3 提案制（§7.2）。实现待 M3 派单 + 需要时报告用户装包。

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

## 2. sqlite-vec vs 手写余弦：对比（**已裁决 V1 = A 主 B 降级**）

两实现**同接口**（`CandidateSource`），M3 按扩展可用性切换。以下只保留结论行，
详细 A/B 维度逐项对比已并入结论、不再分列（防误导）。

### 2.1 方案 A — sqlite-vec（vec0 虚拟表，**主实现**）

```sql
CREATE VIRTUAL TABLE npc_memory_vec USING vec0(embedding FLOAT32[384]);
-- 检索
SELECT rowid, distance FROM npc_memory_vec
WHERE embedding MATCH ? AND k = 20 ORDER BY distance;
```

- **优点**：与 SQLite 同进程、`rowid` ↔ `npc_memories.id` 直连、SQL 内 ANN 剪枝、
  免 Python 侧反序列化；依赖已装、`vector.py` 脚手架已封装 `enable_load_extension`。
- **约束**：vec0 **固定维度**（§6，384 或 768）；维度一改要重建表。
- **风险**：扩展加载在 aiosqlite/async 下的连接处理（→ 触发降级 B，见 §5 缝）。

### 2.2 方案 B — 手写余弦（numpy，**降级兜底**）

```python
# 伪代码：候选 = 本 npc 可见条目 → 全量余弦 → top_k
q = q / np.linalg.norm(q)
M = np.stack([e.emb for e in candidates])      # (n, d)
sims = M @ q                                    # (n,)
top = np.argsort(-sims)[:k]
```

- **角色**：A 的扩展加载失败时的**降级路径**（同 `CandidateSource` 接口，零 SQL 扩展依赖）。
- **优点**：精确（暴力余弦 = ground truth）、维度任意、纯 numpy（已在）。
- **代价**：每 NPC 每检索 O(n·d)；n 大了需反复反序列化 BLOB、无索引线性退化——仅作兜底。

### 2.3 结论行（裁决合并）

| 判据 | A sqlite-vec（主） | B 手写余弦（降级） | 采结 |
|---|---|---|---|
| 50 NPC 千级量级性能 | 优（k-NN 剪枝） | 可接受（见 §3） | 两法均非瓶颈 |
| 集成 / 与 SQL 同源 | 优（SQL 内、rowid 直连） | 差（搬内存） | **V1：A 主** |
| 鲁棒性（扩展不可用） | 差 | 优（无扩展） | **V1：B 降级** |

> **V1 采结**（见 §7.1）：sqlite-vec 主实现 + numpy 余弦降级，**同接口两实现**。

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
- **向量表 ↔ 记忆表关联**：`npc_memory_vec.rowid` = `npc_memories.id`（§6）。
  **V4 采结（§7.1）**：**vec 表为准**，`npc_memories.embedding` 仅作**写路径缓存**、
  不参与读；一致性对账测试钉住（vec 表 ↔ BLOB）。
- **治理过滤（V6 采结，召回端红线）**：向量候选**必须 JOIN `npc_memories`** 并过滤
  治理列（`superseded`/`invalid`/`abandoned` 不召回）——codex R2 落点。
  **不允许**「写入时不同步」的旁路：过滤在召回**端**，JOIN 为硬约束。
- **async 连接**：`vector.py` 用**同步 `sqlite3`** 连接；aiosqlite 下 `enable_load_extension`
  需在底层连接操作（可能经 `conn.run_sync` 或独立只读连接）——**M3 集成风险点，标注**。
- **确定性（C5）**：向量距离相同 → 按 `entry.id` 稳定排序兜底（与 M2 同款）。

---

## 6. 裁决项（原「待裁决」，已裁决见 §7）

| # | 议题 | 选项 | 状态 |
|---|---|---|---|
| V1 | 索引实现 | A sqlite-vec / B numpy 余弦 / 双实现（A 主 B 降级） | **已裁决**（§7.1） |
| V2 | 维度 d | 384（脚手架默认）/ 768；随 embedding model 锁 | 挂起（§7.2） |
| V3 | embedding profile | 复用现有 profile 的 model / §10 增 `embedding_*` 列 / 第二条独立 profile | 挂起（§7.2） |
| V4 | 单一真相源 | vec 表为准 / `npc_memories.embedding` BLOB 为准 / 双写一致 | **已裁决**（§7.1） |
| V5 | 召回时机 | 每 tick 广播 / 按需 / 批量窗口（性能 vs 实时性） | 挂起（§7.2） |
| V6 | 治理条目 | vec 表是否含被取代条目（写入策略） | **已裁决**（§7.1） |
| V7 | 写路径 | embedding 生成挂 `MemoryWritePipeline.write()` 内联 / 异步补算（影响 S1 守卫边界） | 挂起（§7.2，安全敏感） |

---

## 7. 裁决栏（Claude 裁决，2026-09-22）

> 来源：主树 `talking.txt`「裁 3 已批（V 系裁决）」。以下为**采结**，M3 实现据此；
> 未裁项挂 M3 提案制。

### 7.1 已裁决（3 项，采结）

| # | 议题 | **采结** | 落地要点 |
|---|---|---|---|
| **V1** | 索引实现 | **A 主 B 降级** | sqlite-vec 为主实现；async 扩展加载失败 → numpy 余弦降级（**同接口两实现**）。 |
| **V4** | 单一真相源 | **vec 表为准** | `npc_memories.embedding` 仅作**写路径缓存**；一致性对账测试钉住（vec 表 ↔ BLOB）。 |
| **V6** | 治理条目 | **治理过滤（召回端）** | vec 候选**必须 JOIN `npc_memories`** 且过滤治理列（`superseded`/`invalid`/`abandoned` 不召回）——**codex R2 落点，召回端红线**。 |

- **V1 对 §5 的收口**：候选源接口 `CandidateSource`（`VecCandidateSource`）→ 两实现
  `SqliteVecIndex`（主）/ `NumpyCosineIndex`（降级），M3 按扩展可用性切；见 §5 缝。
- **V4 对 §5 的收口**：`rowid` = `npc_memories.id`；**读以 vec 表为准**，BLOB 列不参与读
  （仅写入时双写/缓存），避免双源分叉。
- **V6 对 §5 的收口**：替换/收紧原「S5 过滤」小节——召回**端**即过滤，**JOIN 治理列为硬约束**
  （不再允许「写入时不同步」的处理方式）。

### 7.2 挂起（4 项，挂 M3 提案制）

| # | 议题 | 挂起理由 | 触发时点 |
|---|---|---|---|
| **V2** | 维度 d | 随 embedding 模型选定才锁（§6）；提前锁死会误配模型 | M3 embedding 模型选型 |
| **V3** | embedding profile 缝 | chat 模型不产 embedding，可能需 §10 增 `embedding_*` 列或第二条 profile——**改 schema，须提案** | M3 embedding 接入 |
| **V5** | 召回时机 | 性能 vs 实时性权衡依赖实测（§3 非瓶颈，可后定） | M3 世界循环接线 |
| **V7** | embedding 生成挂写路径 | **触 S1 守卫边界，安全敏感**（Codex 复核域）；内联 vs 异步补算影响唯一写入口纪律 | M3 写路径接入，**须先提案 + codex 复核** |

> V3/V7 涉及 **schema / 写路径-S1** 变更 → 走「先提案 → Claude 裁决 → 再动代码」约定；
> 本预研零代码，不触碰写路径（§18 读侧 only 纪律不变）。

---

## 8. 结论（一句话）

`npc_memory_vec` 在 M3 只是**候选生成器**的替换，打分 API 形状与 S1/写路径纪律不变；
技术上 sqlite-vec 与手写余弦在 50×千级量级均非瓶颈（**V1 已裁：A 主 B 降级**），
真正成本在 **embedding 生成**（挂 LLM client 独立 `embed()` 缝，对齐 M1 单 profile + 监控 + K3/K4）。
本文件为调研稿，**实现待 M3 派单**；需装包或改 schema（V3）前先报告用户/Claude，
V7（写路径触 S1）须先提案 + codex 复核。
