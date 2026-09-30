# M5-R-4 · 「当前活跃分支」真源契约补充（数据面）

**归属**：条款稿 = 本文；合入 `docs/api/anchors-api.md` = **kilo**（本单不改 anchors-api，
避免同文件双写）。施工（POST 取值接线）= Claude。

**触发缺陷 R-4**（codex S4 CR）：分支硬编码 `'main'`——分叉后 POST 记档指错世界线。
现状两处硬编码（`sim/api/anchors.py`）：

| 行 | 现状 | 危害 |
| --- | --- | --- |
| `:274` | `SELECT COALESCE(MAX(seq), 0) FROM events WHERE branch_id = 'main'` | 游标 `seq` 取自错误世界线 |
| `:345` | `create_item(payload.name, branch_id="main", ...)` | 档的 `branch_id` 指向错误世界线 |

两处**必须同改**：只改其一会让档的 `(branch_id, tick, seq)` 三元组**自相矛盾**
（branch 指向子线、seq 却来自父线）⇒ 比两者都错更坏，且更难查。

---

## 条款 R-4.1（真源定义）

**当前活跃分支 = `branches` 表中「当前」的那一行**，查询形如
`SELECT id FROM branches WHERE <当前谓词>`。

- 真源是**表**，**不是**：`'main'` 之类的字面量、进程内常量、WS 会话状态、driver 内存态。
- 需要「当前世界线」的读路径**一律**经这一个查询：POST 记档游标（branch/tick/seq）、
  `GET /api/anchors/current` 的分支、D-6 告知帧的 branch、fast-forward 目标分支。
- **fail-closed**：查不到「当前」⇒ 报「无当前世界线」（409/503 由 kilo 契约定），
  **禁止**回退到 `'main'` 或任何默认串。猜分支 = 记档指向错误世界线，比拒绝更坏。

## 条款 R-4.2（唯一性不变量）

**同一时刻至多一个「当前」分支。** 该不变量目前**不成立**：`store.py::_assert_branch_writable`
的「不存在即开线」（裁 5）允许向任意新分支名 append 并自动开线，于是分叉后
「子线 active + 父线被按需开线再次 active」= 两个当前。

- **R-4.2.1**：`append` 的按需开线必须**收紧**为——仅当 `branches` 表**当前行为零**时才
  允许开线；已有当前行时向另一分支 append ⇒ 抛 `InactiveBranchError`
  （或新异常 `MultipleCurrentBranchesError`）fail-closed。**这是不变量成立的唯一入口**。
- **R-4.2.2**：`fork.py` 的「父转 abandoned + 子转 active」是**唯一**允许改变当前行的
  写路径（现状已如此，且只在 `parent_status == 'active'` 时改父——父已 abandoned 时子仍
  active，属再分叉，合法）。

## 条款 R-4.3（真源载体：建议加 `branches.is_current` + 部分唯一索引）

「当前」需要**可判定的载体**。两个候选：

| 方案 | 判定 | 结论 |
| --- | --- | --- |
| **A：`branches.is_current INTEGER NOT NULL DEFAULT 0` + 部分唯一索引** `CREATE UNIQUE INDEX ux_branches_current ON branches(is_current) WHERE is_current = 1` | 显式、可索引、**数据库层**保证不变量（第二个 `is_current=1` ⇒ IntegrityError ⇒ fail-closed 在写入层） | **建议采**（1 条迁移 0012） |
| B：真源 = `status='active'` 且 `created_at` 最新 | 靠 recency 猜 | **否决** |

**否决 B 的理由**：读档子线（历史点分叉，见 A3 §3.2）**故意**与父线并存，且子线可能比父线
更晚被 fork/被触碰 ⇒ `created_at` 最新 ≠ 玩家当前线。recency 选法会把「玩家正在跑的线」换成
「最近被分叉出去的线」，且**静默错**——正是 R-4 要根治的病。

**过渡期（零迁移）**：在 0012 落地前，「当前」= 唯一的 `status='active'` 行；
**若出现 ≥2 个 active ⇒ fail-closed**（报「世界线状态歧义，请重开世界」），**不 recency 兜底**。

## 条款 R-4.4（分叉后的当前行归属：head 模式 vs anchor 模式）

| fork 模式 | 当前行归属 | 被封存父线 | 允许多个读档子线 |
| --- | --- | --- | --- |
| `kind="head"`（现行：读最近档） | **子分支** | 是（`status='abandoned'`） | 否（只有一条当前） |
| `kind="anchor"`（A3：回退旧档） | **父分支保持当前** | **否**（玩家还在跑它） | **是**（多条读档子线并存，`is_current=0`） |

⇒ 「至多一个当前」与「多条读档子线并存」**不矛盾**：读档子线不是当前。
head 模式自动把当前行交给子分支；anchor 模式**不动**父分支的当前身份。

## 条款 R-4.5（多子并存时的选择规则）

- 多条读档子线并存时，**由显式用户动作决定**「当前」（读档 / 切档请求显式声明目标分支），
  **不由任何时间戳或数量规则推断**。
- 读档子线要成为当前 ⇒ 必须走一次显式切换（把目标分支 `is_current=1`、其余置 0，
  同一事务内；撞唯一索引 ⇒ IntegrityError ⇒ fail-closed）。
- 切换后原当前分支**不自动封存**（它可能仍是玩家想切回的线）；封存是显式动作。
  ⚠️ 这与 head-fork「父自动 abandoned」不冲突：head-fork 是**派生**新线（双轨存档语义），
  切档是**回到**既有线。

## 条款 R-4.6（与既有条款的接口）

- **裁 A6（anchor 引用即热钉）**：被任一 anchor 指向的分支永不整分支冷归档 ⇒ 被选为
  「当前」的分支天然热存，两条款不打架。
- **D-9 / 0010（当前游标 = protected 列优先，同刻按 id 降序）**：那是**档**的游标；
  本契约是**分支**的当前行。两者是不同层：**档游标 → 档的 branch_id → 该分支**；
  两者不得互相推导（禁止用「protected 档的 branch」当分支当前行——多个档可指同一分支，
  而当前行是分支属性）。
- **R-6（列表排序，kilo 域）**：与本契约无交集，纯列表顺序。

## 条款 R-4.7（钉子要求，kilo/Claude 施工时补）

1. 分叉后 POST 记档 ⇒ 档的 `branch_id` = **子分支**、`seq` 取自**同一分支**（三元组自洽）；
2. 历史点分叉后 POST 记档 ⇒ 落在**仍在跑的父分支**（当前行未转移）；
3. 多 active ⇒ fail-closed（**不 recency**、不默认 `'main'`）；
4. `is_current=1` 的第二行 ⇒ IntegrityError（DB 层不变量，方案 A）；
5. head-fork ⇒ 父 `abandoned` + 子当前；anchor-fork ⇒ 父仍当前 + 子非当前；
6. 查不到当前行 ⇒ 报错，**不**回退 `'main'`。

## 附：为什么不能用 `'main'`

分叉后父分支被封存，`'main'` 仍是那条**被弃时间线**（裁 5 闸门会拒其 append）。
POST 记档若继续用 `'main'`：档的 branch 指向被弃线、seq 取自被弃线 ⇒
**读档时从被弃线分叉**，且档的 tick/seq 与真实世界线不符 ⇒ 玩家看到的世界线错乱且难查。
这与 0008 的 `parent_branch_id`、0011 的物化包同属「世界线身份必须显式携带」的纪律。
