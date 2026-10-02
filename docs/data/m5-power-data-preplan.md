# M5 批次 C 权力机制 · 数据面预研（压缩版 · 兼施工案）

> **归属**：数据面（opencode）。**依据**：`docs/security/m5-authority-criteria-preplan.md`
> （codex 判据 8 钉 + D-10 权力不可见）、`docs/arch/m5-rulings.md` 裁 24（不新增安规面）、
> `docs/api/m5-batch-c-prestudy-authority.md`（kilo K4 协议面）、`docs/data/m5-anchor-materialization-preplan.md`
> （A3 地基分类）、`docs/security/m5-security-preplan.md` §9（W-A1/W-A2 三面威胁）。
> **授权**：裁 31-1「预研稿内推荐案 = 施工案」——本文 §4 的推荐即本单施工内容，不等下一轮裁决。
> **状态**：已实施（0013 + `models.py` + `power_store.py` + `fork.py` 克隆登记 + 钉子）。

---

## 1. 一句话结论

权力**落一张新表 `npc_power`**（每 NPC 一行、分支内复合主键、**量纲归一到 [-1, 1]**），
**不新增任何事件 kind**（红线 A），写面是**显式幂等增量写**（`PowerStore.apply/apply_batch`，
fail-closed），读面是**一次 SELECT 物化**（`PowerStore.materialize`）；**不设任何对外读口**
（D-10：只服务内部决策层）。

## 2. 存哪：新表 vs 并入（对照 0006 先例 + A3 地基分类）

| 方案 | 判定 | 结论 |
| --- | --- | --- |
| **新表 `npc_power`** | 独立演进（衰减游标/量纲/审计列不污染宽表）；克隆语义复用 0006 的 `INSERT…SELECT` 有界表模板；A3 分类里**显式登记为第 4 张「不可重建」表** | **采**（0006 structures 同款判据：新建领域 = 新表，宽表不当垃圾桶） |
| 并入 `npc_profiles` 两支 `add_column` | 迁移更便宜、克隆现成，**但**：`npc_profiles` 在 A3 分类里算「可重放 5 张」之一（`lod` 面）。把**无事件源**的状态塞进去 ⇒ 分类当场说谎：读档时这几列会退化成「快照里的当前值」，**正是 A3 反对的「拿回退前的当前值当回退点的历史值」近似糊** | **否**（分类地基不许被污染，比省一支 add_column 贵） |

**索引决策：零索引**。主键前导列就是 `branch_id` ⇒ 分支查询天然走 PK 前缀，再加
`idx_*_branch` 是纯冗余（`matter_state` 那支是历史遗留）。迁移因此只有
`create_table`（0011 同款判据：无 ALTER ⇒ 不需 `batch_alter_table`）。

**命名决策（反直觉但重要）**：状态列叫 **`power_level`**——它**故意落在 codex 红线 B 的
`AUTHORITY_FORBIDDEN_KEYS` 里**。理由：这张表**永远不该出站**（D-10），而禁键扫描
（codex `TestOutboundForbiddenKeys`）是对**键名**做精确匹配；用禁键内的列名 ⇒ 将来任何人
不小心把行值塞进出站 payload，扫描**当场变红**，而不是靠 review 记忆兜住。
**若将来要改名，必须先改 codex 稿的禁键集（同变更纪律），不许悄悄换成中性名。**

## 3. 事件 kind：**不新增**（红线 A）

codex 已用 `test_event_kinds_closed` 把 `PAYLOAD_MODELS` 的 kind 集合**钉死**，且 A 线要求
「事件 kind 不得出现 authority 族」。⇒ 权力的每一次变化**不落事件流**。

- 写面 = **显式增量写**（决策层在既有 tick 批次里调 `apply_batch`），与事件流解耦。
- 代价（必须登记）：本表**无事件源** ⇒ ① 没有 `materialize_*_replay` 路径（重放物化器
  覆盖不到）；② 历史点读档（anchor 物化）**拿不到**本表的值 ⇒ 属 A3「不可重建」族，
  **第 4 张**（前 3 张：npc_memories / knowledge / relationships）。本单只**登记**，
  扩 `corpus_blob` 格式属批次 E 物化单。
- 与 M3 `relationships` 的边界：codex §1 已判「M3 关系不重复造钉，只在 R-C3 登记同判据适用」。
  本表**不是**关系（不表达 pair 之间的认知），只表达「该 NPC 面对玩家的权势标量」。

## 4. 六个待裁点 → 推荐采法（= 施工案，裁 31-1 授权）

| # | 待裁点 | 推荐采法 | 理由 / 改动的代价 |
| --- | --- | --- | --- |
| 1 | 量纲：归一 [-1,1] vs 原始分 | **归一 [-1, 1]**，`0` = 与玩家平权 | 与 `integrity`/OCEAN 同族可读；越界由 DB CHECK + 写面夹取双重拦。若机制要原始分 ⇒ **一支迁移放宽 CHECK**（成本已知、可预算） |
| 2 | 粒度：每 NPC 一行 vs 全局一行 | **每 NPC 一行** | 服从/顶撞是 per-NPC 倾向；全局行会诱发「所有 NPC 同步变」的耦合 bug，且无法表达个体差异 |
| 3 | 写入形态：显式增量 vs 事件投影 | **显式增量**（`apply`/`apply_batch`） | 红线 A 禁新 kind；投影要求 payload 携带增量 ⇒ 只能改既有 payload（闭合集，`extra="forbid"`）⇒ 不可行 |
| 4 | 是否记原因/审计列 | **不记**（机制单按需加列） | 每次决策写一行审计 = 热路径写放大；**加列不需 batch**（纯 `add_column`，0009 同款）⇒ 成本可后置 |
| 5 | 衰减游标形态 | **单列 `updated_at_tick`** | `matter_state` 同款；不做桶表（桶表 = 每 NPC 每桶一行，克隆与体积都不划算） |
| 6 | 是否进 anchor 包 | **登记为第 4 张不可重建表**，本单不扩包格式 | 扩 `corpus_blob` 格式 = 物化单的活（批次 E）；不登记才是错（会让 A3 §3.2 条件「语料一致」说谎） |

## 5. branch_id / 分叉语义（对照 0008 / 0009 先例）

- **身份**：PK `(branch_id, npc_id)`——0008 `npc_profiles` 同款（分叉后同 id 跨分支共存）。
- **克隆**：进 `fork.py::_BOUNDED_TABLES`（`INSERT…SELECT` 换 `branch_id`，零 id 重映射），
  与 `matter_state`/`structures` 同款。**逐字节等于父分支当前值**（分叉点 = 父分支头部，
  与有界表的 P1 前提一致）。
- **R-4 交叉**：当前行交接归 fork 交接单（A6 口径稿）；本表**不参与**交接判断，
  读档子线（active + 非当前）**照写不误**（0012 闸门只锁开线）。
- **父分支封存后本表不动**（C6：分叉只增不减，父行值是那段时间线的历史事实）。
- **逐分支惰性衰减**：`updated_at_tick` 记的是「该行最后一次被写到的 tick」，
  衰减由决策层按 `tick - updated_at_tick` 计算后调 `apply` ⇒ **不做隐式衰减**
  （隐式衰减会让「读一次表」变成写操作，破坏纯读契约）。

## 6. 施工清单（本单已落）

| 文件 | 改动 |
| --- | --- |
| `sim/core/persistence/alembic/versions/0013_power_state.py`（新） | `create_table('npc_power')`：复合 PK + 两 CHECK（量纲、`tick >= 0`）+ `created_at`；downgrade drop table |
| `sim/core/persistence/models.py` | `NpcPower`（与迁移同源 ⇒ autogenerate 零漂移） |
| `sim/core/persistence/power_store.py`（新） | `PowerState` / `PowerStore`（`materialize` / `apply` / `apply_batch`）+ `PowerWriteError` + `POWER_MIN/POWER_MAX` |
| `sim/core/persistence/fork.py` | `_BOUNDED_TABLES` 加 `npc_power`（列全显式，漏列即静默丢字段） |
| `sim/tests/test_m5_power_state.py`（新） | 20 钉（结构/迁移往返、写面 fail-closed、读面纯读、分叉克隆、禁面与登记钉） |
| `docs/data/schema.md` | 新增 §21 `npc_power` |
| `docs/data/m5-anchor-materialization-preplan.md` | 地基分类从 3 张扩为 **4 张**（登记，不改包格式） |

**不动**：`sim/api/`（kilo/Claude 面）、`sim/npc/`（决策层 = Claude 核心机制面）、
`sim/core/events.py` 的 `EventKind`/`PAYLOAD_MODELS`（红线 A）、`thresholds.py`、
`shared/openapi.json`（**零协议面改动 ⇒ gen-protocol 快照零漂移**）。

## 7. 缺口与风险（交下一单）

| 缺口 | 影响 | 归属 |
| --- | --- | --- |
| 无事件源 ⇒ 无重放物化器 | 快照 GC 后本表只剩当前值 | 批次 E（anchor 包第 4 张） |
| 衰减/累积的**语义**未定义 | 本表只提供载体，delta 由谁算、衰减率多少未定 | Claude 机制面（`sim/npc/`） |
| 量纲若改宽 | 需一支迁移放宽 CHECK | 按需，已知成本 |
| `apply` **非幂等**（增量语义） | 同一 delta 调两次 = 两次效果 | 机制单若需幂等必须自带去重（登记为待裁） |
| 越界夹取**如实上报**（`clamped=True`） | 调用方须检查该事实，勿当无事发生 | 机制面读 `PowerState.clamped` |
