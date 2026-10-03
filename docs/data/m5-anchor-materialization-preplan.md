# M5-A3 · anchor 世界态物化数据面设计（批次 E 前置）

**纯文档零代码**。落点是 A2 修正 2：`docs/data/m5-chaos-stream-data-preplan.md` §3 修正 2
——历史点分叉时父分支在 anchor 时刻的 `rng_state` 不可得，**「回退旧存档」会重掷混沌**。
本稿把「物化包」设计到可施工：包内容、迁移接缝、fail-closed 解锁条件、成本口径。
施工由 Claude 派单（`fork.py` 改动面见 §3.3，本稿只列）。

## 0. 既有事实（引用仓库现状，非推测）

| 事实 | 出处 |
| --- | --- |
| 快照 = gzip 压缩全量状态；`snapshots(branch_id, seq, tick, snapshot_data, is_cold, schema_version)`；`seq` = 该点事件流最大 `events.seq` | `models.py::Snapshot`、`store.py::write_snapshot` |
| 快照选取 = `tick <= before_tick` 按 `(tick DESC, seq DESC) LIMIT 1`，**不过滤 `is_cold`、不判分支状态** | `store.py::latest_snapshot` |
| 快照 cadence = 每 1000 tick；同分支留最近 8 份 + 每日首份；单份 ≤5MB gzip（预算）/ 实测 ~7KB（50 实体 pos-only 代理） | `docs/perf/budget.md:90`、`m5-time-scale-fork-budget.md:168` |
| 8 张**有界表**（可 `INSERT…SELECT` 克隆）：`npc_profiles`/`npc_health`/`relationships`/`matter_state`/`structures`/`material_balances`/**`npc_power`（0013）**/**`fires`（0014）** | `fork.py::_BOUNDED_TABLES` |
| 2 张**语料表**（按分叉点截断克隆）：`npc_memories`（`event_seq`/`created_at_tick`）、`knowledge`（`evidence_seq`/`learned_at`） | `fork.py::_clone_memories/_clone_knowledge` |
| **新增（0014 / M5-A9）**：`fires`（火场生命周期）有事件源 + fold 器 ⇒ **属可重放族，不进包**（它与 `npc_power` 正相反：后者无事件源 ⇒ 第 4 张不可重建）；| 折叠/重放物化器覆盖 6 张：`npc_health`(hidden)/`matter_state`/`structures`/`material_balances`/`npc_profiles`(lod) | `npc_store.py::materialize_*_replay`、`flush_tick` |
| **无事件源、不可重建的 4 张**：`npc_memories`（`superseded_by` 治理列）、`knowledge`（told 链/源记忆指针 + 治理列）、`relationships`（累计值原地演进，`npc_store.py`/`fork_replay.py` 均无物化器/可比字段）、**`npc_power`（M5-A7 / 0013，批次 C 权力态：无事件源——红线 A 禁新增 kind，增量走显式写面，本表只有「当前值」）** | 预研稿 §3.7、`fork_replay.py::EXCLUDED_FIELDS`、`m5-power-data-preplan.md` |
| 历史点分叉 fail-closed：`fork_seq < head_seq` 抛 `ForkError`（消息已指向本方案） | `fork.py:346-352` |
| RNG 状态只存**分支当前值**，每次 fork 覆写 | `models.py::Branch.rng_state`（0009）、`fork.py:372-377` |
| 存档写路径已同事务位（`create_item` 一个 session = A3 同事务）；`agent_override` 现硬编码 `"{}"` | `sim/api/anchors.py:192-210` |
| 冷热分层**尚未实现**：全仓无任何代码把 `is_cold` 置 1，`latest_snapshot` 也不按它过滤 | `store.py:252`、`models.py:119` |
| 裁 A6：anchor 引用即热钉——被任一 anchor 指向的分支永不整分支冷归档 | 预研稿 §3.9/§4.1 |

**分类结论（本稿的地基）**：世界态分两类——**可重放的 6 张**（原 5 张 + M5-A9 `fires`）（有 fold 器，快照 + 事件窗口
可重建）与**不可重建的 4 张**（前 3 张语料/关系表 + M5-A7 新增 `npc_power`）（只有「当前值」）。【**`fires` 不进包**（0014 / M5-A9）：它有事件源（`fire.ignited`/`fire.extinguished`）且有 fold 器 ⇒ 属可重放族，读档靠「快照 + 事件窗口重放」即可重建 ⇒ **物化包不为火扩格式**；火场中间态（强度/燃料）一律不入库。】物化包必须同时兜住两类，
否则历史点分叉会把「回退前的当前值」当成「回退点的历史值」——那正是 fail-closed 要防的
近似糊。

## 1. 问题一：物化包内容（三件如何组包）

### 1.1 包形态建议：`anchor_packages`（1 张新表，包自足 + 快照指针）

| 列 | 内容 | 理由 |
| --- | --- | --- |
| `anchor_id` PK/FK→`player_anchors.id` | 1:1 | 包是档的附属物 |
| `branch_id` / `tick` / `seq` | anchor 游标三元组 | 与列一致，读档校验用 |
| `snapshot_seq` / `snapshot_tick` | 展开所用快照点（**引用** `(branch_id, seq)`） | 零 blob 复制；丢了可退化为全前缀重放（§4.3） |
| `rng_state` TEXT NULL | **anchor 时刻**的状态包（`capture_rng_state()` 输出） | **本设计的核心**（§1.3） |
| `agent_override` TEXT | 档的 agent 覆盖副本 | 包自足，读档不 JOIN |
| `corpus_blob` BLOB | 3 张不可重建表的行值（gzip JSON） | 唯一出路（§1.4） |
| `state_hash` | 展开后 `WorldState.state_hash` | R-2 对账/回归基线 |
| `schema_version` / `created_at` | 版本与时刻 | 与 `snapshots` 同口径 |

### 1.2 快照展开 + `agent_override` 应用点（次序是铁律）

**展开**：`latest_snapshot(anchor.branch_id, before_tick=anchor.tick)` → gunzip → JSON →
`WorldState`；重放窗口 = `(snapshot_seq, anchor.seq]`，逐事件过 fold 器
（`npc_store.py::materialize_*_replay` + `flush_tick`）。

⚠️ **须收紧的判据**：现有 `latest_snapshot` 只判 `tick <= before_tick`、**不判 `seq`**。
同 tick 内多事件时，可能选出「tick 在窗口内、`seq` 已超 `anchor.seq`」的快照 ⇒ 窗口倒挂、
事件被跳过。物化路径**必须加 `snapshot.seq <= anchor.seq`** 判据（施工项，非本单动手）。

**应用次序（不可换）**：

1. 展开世界态（快照 + 窗口重放）；
2. **再套** `agent_override`（快照里可能存着旧 override ⇒ 先套会被覆盖；它是玩家档的
   agent 身份覆盖，**不参与 fold、不写事件**，只在 resume 前生效一次）；
3. 再灌 3 张不可重建表的包内行值；
4. 最后 `restore_rng_state(pkg.rng_state)`；
5. 然后才 resume 第一个 tick。

**快照缺失时的重放起点（fail-closed 判据）**：从 `seq = 0`（分支起点）全前缀重放到
`anchor.seq`，**仅当三条全满足**：

- **事件连续**：`COUNT(*) == MAX(seq)` 且 `MIN(seq) == 1`（无洞 ⇒ 重放不缺事件）；
- **无语料写入**：该分支在 `anchor.seq` 之前**没有** 3 张不可重建表的行**晚于**任何可用
  快照——简化判据：**该分支的 `npc_memories`/`knowledge`/`relationships` 行数与包内
  `corpus_blob` 的行集一致**（包是权威，快照缺失只影响可重放那 5 张）；
- **`rng_state` 非 NULL**。

任一不满足 → 抛 `AnchorMaterializationError`（**返回部分包 = 禁止**）。**禁止**用
`Branch.seed` 派生兜底（seed 不含 PCG64 进度 ⇒ 抽签必然跳变，A2 已实测）。

### 1.3 `branches.rng_state` 恢复：**必须按 anchor 存，不能读时取**

`branches.rng_state` 是**分支当前值**、每次 fork 覆写；anchor 行没有自己的 RNG 快照
⇒ 读档时从分支列取，拿到的是**存档之后**的值（A2 §3 修正 2 的病：回退旧档重掷混沌）。
唯一正确形态：**存档那一刻捕获 → 落 `anchor_packages.rng_state`**，
读档时 `restore_rng_state(pkg.rng_state)`，与 0009 的 fork 落库路径**同格式、同事务**。

- **物化时机 = 存档时（`create_item` 的 A3 同事务位）**，不是读档时。决定性理由：**快照会
  被淘汰**（留最近 8 份 + 每日首份）⇒ 懒物化会让老档随快照 GC **永久不可读档**。存档时
  物化一次，之后包自足、与快照生死解耦。
- 与 fork 事务的一致性：包在**存档事务**里写，分支 rng 落库在 **fork 事务**里写；两者
  写的是同一份 `capture_rng_state()` 输出 ⇒ 读档接缝逐位一致（可复用 A-DATA 的端到端
  逐位一致钉）。

### 1.4 4 张不可重建表必须**进包**（否则 §3.2 条件永不满足）

`npc_memories`/`knowledge`/`relationships`/`npc_power` 无事件源 ⇒ 事件重放**永远**重建不出 anchor
时刻的值。可选路径只有两条：

- **(A) 语料行值进包**（本稿建议）：`corpus_blob` 存 3 表行值（gzip JSON），克隆时**从包
  取行**而非从父分支当前表取。代价 = O(每 anchor × 语料行数) 存储（§4.4 配额）。
- **(B) 补 `*.written` 事件 + relationships 变更 seq**（预研稿 §3.7 备选 1）：把语料写入
  变成可重放。代价 = 事件白名单扩容 + 写入路径改造 + **relationships 仍无解**（累计值
  原地演进需记变更量或全量）。

⇒ **建议 (A) 先落地**（数据面可控、零事件面改动），(B) 作为长期演进。

> **M5-A7 增补（0013 `npc_power` 已登记）**：批次 C 权力态同样无事件源（红线 A 禁新增 kind）⇔ 它是第 4 张「只有当前值」的表。本单只**登记**，不扩 `corpus_blob` 格式（归批次 E 物化单）；在扩包之前，**历史点读档（`kind="anchor"`）对本表仍然 fail-closed**（当下不误认：包内语料行集不含 `npc_power` ⇒ 不允许物化）。规模与保存口径见 `m5-power-data-preplan.md` §4 待裁点 6。

## 2. 问题二：与 0008/0009/0010 的接缝（要新迁移吗）

**既有三迁移零改动**：物化所需的全部读取面已存在——`snapshots`（0001）、
`events`（0001+0008 身份列）、`player_anchors.agent_override`（0001）、
`branches.rng_state`（0009）、`player_anchors.protected`（0010，与物化无关但同属档面）。
⇒ **「定义包」零迁移**。

**落库需要 1 条迁移**：`create_table('anchor_packages')`（0011 或 Claude 另派号；
**本单只设计不占号**——A2 撞号教训）。纯新建表 ⇒ 无回填 ⇒ 不需要 batch
（与 0008 因 CHECK 才需 batch、0009 纯 add_column 的判据都不同）。

**既有 anchor 的迁移接缝（关键）**：老档**没有包**，且其 anchor 时刻 `rng_state`
**不可得**（分支列已被后续 fork 覆写）⇒ 分三类：

| 类别 | 判据 | 处置 |
| --- | --- | --- |
| 可救 | anchor 游标 = 该分支**最后一次** fork 点，且此后该分支未再 fork | 分支列 `rng_state` 即该时刻值 ⇒ 可物化（**唯一可救子类**） |
| 不可救（典型） | 存档后分支又跑过 / 又 fork 过 | `AnchorMaterializationError(rng_unavailable)` |
| 结构性不可救 | 分支已冷归档搬移（A6 只保证「被 anchor 指向」不搬，但**未被指向**的会） | `AnchorMaterializationError(snapshot_lost)` |

**建议只读诊断面（不做回填）**：`GET /api/anchors/{id}/materialization` →
`{ready: bool, reason: str|None}`，原因码固定集
`no_package` / `rng_unavailable` / `snapshot_lost` / `event_gap` / `corpus_mismatch`。
理由：让产品对老档显示「该档不可回退」而不是让玩家撞 500。

**不做的事（纪律）**：① 不用 `Branch.seed` 派生兜底；② 不「近似重置治理列」
（D3-b 纪律）；③ 不给老档批量回填包（回填=重掷混沌=骗人）。

## 3. 问题三：`fork.py` fail-closed 的解锁条件与改动面

### 3.1 现状（一句话）

`fork.py:346-352`：`fork_seq < head_seq` ⇒ `ForkError`，理由是「投影表当前值 ≠ 分叉点状态」。
物化包齐备后该前提被替换，但**还有两条硬前提不在包内**：语义（父分支要不要封存）与
语料克隆源（从表还是从包）。

### 3.2 解锁条件（**全部**满足才解封 `kind="anchor"`）

1. **包 ready**：`anchor_packages` 有行 + 快照/窗口可展开 + `rng_state` 非 NULL；
2. **3 张不可重建表进包**（§1.4 (A)）：否则语料仍取「当前值」= 近似糊，条件永不满足；
3. **`kind` 参数化**：现行逻辑在 fork 后把父分支标 `abandoned`（读最近档语义）。**回退旧档
   不得封存当前正在跑的父分支** ⇒ 必须显式区分
   `kind="head"`（现行：封存父）/ `kind="anchor"`（父分支**保持 active**，只加子线）。
   禁止靠 `fork_seq == head_seq` 隐式区分（那是当前的 fail-closed 位置）；
4. **语料克隆源切到包**：`_clone_memories/_clone_knowledge` 现在用
   `_truncation_sql(event_seq/evidence_seq)` 对**父分支表**做截断；历史点 + 包语义下包是
   **全量行值、无截断判据** ⇒ 需包侧携带行级 seq 标注（`created_seq`/`evidence_seq`/
   `superseded_by`），克隆改为「按包写行 + 重映射 `entry_id`/id + R-2 指针重写」；
5. **钉子集**（施工单必须齐）：
   - 接缝逐位一致（rng 从包恢复，非分支列）✔ 复用 A-DATA 逐位钉形制；
   - 3 张表行值 = 包内容（R-2 可比字段集，跨分支比 `relationships` 累计值）；
   - R-1 记忆 content/向量字节相等、`R-2 superseded_by` 零跨分支悬空；
   - 父分支仍 `active` 且**可继续 append**（分叉不回溯污染）；
   - vec 字节重键 + `vec_pending` 不泄漏；
   - 包缺失/rng 缺失 ⇒ `AnchorMaterializationError`（不是 `ForkError`、不是静默降级）。

### 3.3 改动面清单（只列，施工归 Claude）

| 文件 | 改动 |
| --- | --- |
| `sim/core/persistence/anchor_package.py`（新） | `materialize_anchor()` / `AnchorPackage` / `AnchorMaterializationError` / `MATERIALIZATION_REASONS` |
| `sim/core/persistence/alembic/versions/0011_*.py`（新，**号待派**） | `create_table('anchor_packages')` |
| `sim/api/anchors.py` | `create_item` 同事务写包（A3 位）；新增只读诊断路由 `/{id}/materialization` |
| `sim/core/persistence/fork.py` | 删/改 `fork_seq < head_seq` fail-closed → `kind` 参数；新增 `package` 入参；语料克隆源切包；`agent_override` 透传；展开+窗口重放调用点（`preflush` 之后） |
| `sim/core/persistence/fork_orchestration.py` | 读档编排：`diagnose → materialize → fork(kind="anchor")` |
| `sim/core/persistence/store.py` | `latest_snapshot` 增 `seq <=` 判据（或新增 `snapshot_for_anchor()`，不破既有调用方） |
| `sim/tests/test_m5_anchor_materialization.py`（新） | §3.2 钉子集 |

**不动**：`EventKind` 白名单（语料走包，不新增事件）、`branches`/`events`/`snapshots` 结构。

## 4. 问题四：成本口径（数字取 pi 实测）

### 4.1 物化写入（存档时，一次；不进 tick 热路径）

| 项 | 量级 | 依据 |
| --- | --- | --- |
| 快照展开（gunzip + JSON） | ~0.1–0.4ms | 同 `write_snapshot` 0.451ms 的逆过程量级（pi） |
| 窗口重放（最坏） | **≤14.8ms** | ≤1000 tick × 20 事件/tick × **0.74µs/事件**（pi，`fold_matter_snapshot` 1k/10k/100k 恒定） |
| 窗口重放（典型） | ~0 | anchor 恰在快照点 |
| 语料包写（10k 行） | ~6.1ms | **0.61µs/行**（5 万行无向量实测档，pi） |
| **单次物化合计** | **≈0.5–25ms** | 相当于 **10–60 个 tick** 的存档成本（append 78.7µs/事件 × 20 = 1.57ms/tick，pi） |

**建议红线（advisory，对齐既有口径）**：物化 ≤ **50ms/次**、异步卸载不阻塞 tick
（比照 `bench-plan.md` 快照 ≤500ms 单次 / ≤0.5ms/tick 摊销）；多分支物化重放仍守
**≤1.0µs/事件**（pi 红线 ⑤）。

### 4.2 读档（消费包）

包行读 + 展开（~0.4ms）+ 窗口重放（≤14.8ms）+ 语料行灌入（10k 行 ~6.1ms）+ fork 克隆
（有界 6 表 `INSERT…SELECT` 0.61µs/行 + 向量 5.09µs/行，pi）+ rng 恢复（~0）
⇒ **≈20–40ms 一次性**，与现行 head-fork **同量级**（不新增量级）。

### 4.3 存储分层（关键取舍）

- **快照是缓存，不是资产**：引用即可。丢了 ⇒ 退化为**全前缀重放**
  （10 日 = 1.728M 事件 × 0.74µs ≈ **1.28s**，一次性读档可接受）。
  ⇒ 建议设**前缀上限**（如 >2M 事件 ⇒ `AnchorMaterializationError`「请重开档」，
  避免 1.28s+ 读档与「禁每 tick 全量重放」反例同源）。
- **语料 + rng 是不可重建资产**：必须在包内（§1.4）。每 anchor 一份 ⇒
  **O(anchor 数 × 语料行数)**：10k 行 ≈ 2MB/anchor（~200B/行）⇒ 100 anchor × 50k 行
  ≈ **1GB**，逼近主库稳态 <2GB ⇒ **必须设配额**：建议包体总量 ≤ 主库 **10%**，
  超限则该 anchor 标 `no_package`（fail-closed），并按 LRU 回收**未被 protected 引用**的包。

### 4.4 禁反例（沿用 pi 口径）

- ❌ 读档时每 tick 全量重放当日累计事件：`86400 × 20 × 0.74µs = 1.28s/帧级`（破线 23x）
  → 物化只做**一次**，不做逐 tick 重放。
- ❌ 逐 anchor 复制 ≤5MB 快照 blob：N 个 anchor = N×5MB；应**引用 + 可退化**（§4.3）。

## 5. 一句话结论（四问各一条）

1. **包 = 快照指针 + 3 张不可重建表行值 + anchor 时刻 `rng_state` + `agent_override` +
   `state_hash`；存档时（`create_item` 同事务）一次物化，读档 O(1) 取包；`rng_state`
   必须按 anchor 存（分支列只有 fork 时刻值，读时取会重掷混沌）；快照缺失时从 seq 0 全前缀
   重放，判据 = 事件连续 + 语料行集一致 + rng 可得，否则 `AnchorMaterializationError`。**
2. **既有 0008/0009/0010 零改动即可定义包；落库只需 1 张新表 `anchor_packages`（1 条
   `create_table`，号待派）；老档无包且 rng 不可得 ⇒ 不可物化，只给只读诊断面，不用 seed
   派生兜底、不批量回填。**
3. **解锁 `kind="anchor"` 需五条同时成立：包 ready、3 张不可重建表进包、`kind` 参数化
   （回退旧档不封存父分支）、语料克隆源切包、钉子集齐；改动面 7 处（§3.3），零事件白名单
   改动、零 branches/events/snapshots 结构改动。**
4. **成本：单次物化 ≈0.5–25ms（最坏项是 ≤1000 tick 窗口重放 14.8ms）、读档 ≈20–40ms
   （与现行 head-fork 同阶）、不进 tick 热路径；存储上快照是可弃缓存（丢了退化为 1.28s
   全前缀重放，设上限），语料+rng 是不可重建资产必须内联 ⇒ 每 anchor O(语料行数)，
   需 10% 配额 + LRU。**
