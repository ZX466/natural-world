# 玩家档锚点接口契约（docs/api/anchors-api.md）

> 能力域：接口 / 兼容性（kilo） | M5-K1 | 对齐 DESIGN.md §7 §12 C6、`openapi.md` §3/§4.3、`ws-protocol.md` §4.4
> 本文为**设计契约稿（零代码）**：字段 / 校验 / 状态码 / 错误形四要素齐，Claude 域照此施工 `sim/api/anchors.py`。
> 真相源：`shared/openapi.json`（保留位 schema `AnchorCreate`/`AnchorRename`/`AnchorListItem`/`ProblemDetail`，TS 侧已生成，见 `shared/protocol.ts`）。

## 0. 定位与边界

玩家档（PlayerAnchor）= **时间线游标**，不是世界状态的副本（DESIGN §7 / §12）。CRUD 属戏外 meta shell，归 HTTP；
**载入**（触发分叉 + 快照 + 事件重放 + `full_snapshot` 回流）归 WS `load_anchor`（`ws-protocol.md` §4.4）。

| 关注点 | 契约 |
|---|---|
| 世界档（World Line） | `append-only`，**永不删除**（C6）。所有本文件删除操作只动 `player_anchors` 行 |
| 出戏边界 | 响应**不回传** `branch_id` / `tick` / `seq` / `seed` / `agent_override`（零原始世界数值落前端） |
| api_key 纪律 | 本接口**无任何密钥字段**（不创建、不返回、不更新）；与 `openapi.md` §2 一致 |
| 时间展示 | 玩家按 `story_label`（叙事化时间标签）识别进度，绝不见 "tick 86400" |

> 保守口径依据 `openapi.md` §1：即便 §11 仅禁止戏内出现 tick/seq，戏外也取零原始世界数值。

## 1. 路由契约

BASE = `/api/anchors`。所有路由 `tags: ["anchors"]`，与 `settings.py` 同模块模式。

### 1.0 `GET /api/anchors/current` — 当前游标（**M5-K3 / 裁 21-A D-9，kilo 已施工**）

| 项 | 值 |
|---|---|
| 请求 | 无参数 |
| 200 | `AnchorListItem`（**单对象**，五键与列表项同构，**零原始数值**） |
| 404 | 空库（还没有任何玩家档）时——与列表的「200 + `[]`」是两回事：列表问"有什么"，当前指针问"你在哪" |

- **判据**：末梢游标 = `updated_at` 最大者（与 §1.4 的 `protected` 派生同源，故本路由返回的 `protected` 恒为 `true`）；同刻多档按 `id` 降序兜底，保证返回**确定**。
- **⚠ 声明顺序铁律（本路由唯一高风险项）**：必须注册在 `/{anchor_id}` **之前**——FastAPI 按声明顺序匹配，路径参数路由若在前会把 `"current"` 当 anchor_id 吃掉并回 404。钉子见 `sim/tests/test_m5_api_anchors.py::TestCurrentAnchorRoute`（实跑 200 且不落 404 分支 + 白盒顺序双钉）。
- 与 WS 侧的关系：`session_state.anchor`（`ws-protocol.md` §4.6）取同一行数据，**只随事件发**（接入/读档），不做 WS 查询面——同一事实两个真相源会漂。

### 1.1 `GET /api/anchors` — 列表

| 项 | 值 |
|---|---|
| 请求 | 无参数 |
| 200 | `AnchorListItem[]`，**空库返回 `[]`**（不是 404） |
| 排序 | `updated_at` 降序（最近存的在前）。该列**只写一次**（见 §1.4 末条），故排序稳定、不受改名影响 |

```jsonc
// 200
[
  {
    "id": "9f3c1a7b2e04",
    "name": "初到临河",
    "story_label": "第二日 · 清晨 · 雨刚停",
    "created_at": "2026-09-19T03:20:00Z",
    "protected": false
  }
]
```

- `story_label` 由 sim 用 §13 calendar 叙事化产出。**构造期降级**：若 calendar 未就绪，返回空串 `""`（字段保留、非 null）——前端对空串显示「未标注」。
- `protected` 见 §1.4。

### 1.2 `POST /api/anchors` — 新建游标

| 项 | 值 |
|---|---|
| 请求 | `AnchorCreate` = **仅 `name`**（1..64，与 `ProfileCreate` 同口径） |
| 201 | `AnchorListItem`（含服务端生成的 `id`） |
| 400 | 当前世界未就绪（无 loop / **无「当前活跃分支」**——含查不到当前行与多当前歧义两种 fail-closed）→ 无法取游标（**先于** 422 判定，R-9；判据见 §1.6 R-4.1-S） |
| 422 | pydantic 校验失败（`name` 缺失 / 超长 / 空）**或** 档名命中禁词（见下） |

```jsonc
// POST /api/anchors
{ "name": "初到临河" }

// 201
{
  "id": "9f3c1a7b2e04",
  "name": "初到临河",
  "story_label": "",
  "created_at": "2026-09-19T03:20:00Z",
  "protected": true              // 新档即末梢 → 见 §1.4
}
```

**`name` 校验规则**（与 `settings.py::ProfileCreate` 同口径）：

```python
name: str = Field(min_length=1, max_length=64)
```

- `min_length=1` 拒绝空串与纯缺省；`max_length=64` 与 Profile name 一致（同一设置面板组件复用）。
- **`name` 唯一性：不设唯一约束**。玩家可重名（"第 2 周" 存两次很正常）；去重职责归客户端按 `id` 引用，不归服务端。
- **`additionalProperties: false`（`extra="forbid"`）**：拒绝 `{"name": "...", "tick": 100}` 这类越权字段。客户端若想指定游标位置，那是**另一个接口**（本契约不给，见 §5）。

**档名禁词（F-6 / 裁 28-G S-6 落地 + 裁 29-A ③② 契约化，2026-09-30）**：

| 项 | 值 |
|---|---|
| 判定 | `name` 过 **`sim.llm.prompts.banned_words.scan()`**（Agent 面向词表：`BANNED_WORDS_META` ∪ `BANNED_WORDS_PERSIST`，**不扩词表**） |
| 命中 | `422`，`type: "/errors/anchor-name-rejected"`，`title: "档名含不可用词汇"`，`detail` 含命中词与人读上下文 |
| 覆盖 | **POST 与 PATCH 双写路径**（改名同样受检） |
| 顺序 | **世界未就绪（400）先判，词表（422）后判**（R-9；与 §1.2 状态码表同序） |

- **为什么 fail-closed 是对的**（裁 29-A ③）：档名**会进 D-6 分叉告知帧的游标指针**（`SessionAnchor.name`）与 `story_label` 面 ⇒ 存在回灌路径 ⇒ 沿用 Agent 面向的 fail-closed 闸门，不另造口径。
- **玩家可感知的代价**（已登记，见 §6.7 已定型决策备忘）：Agent 词表含 `存档`/`读档`/`游戏`/`玩家`/`分支`/`快照`/`重放`，故「存档：第二日」「读档前」「分支甲」等**戏外语义合法**的名字会被 422 挡下（K7 复验实测 10 个样本 7 拒 3 放）。这是**已知取舍**，不是缺陷——若将来要放开，走下面的钩子。
- **「戏外词表」钩子（裁 29-A ② 立结构 → **裁 30-B① 集合与时机落定**，2026-10-01）**：
  - **集合初值已裁 = 8 词**（`BANNED_WORDS_META_SHELL`，`{重开, 读档, 存档, 快照, 回放, 游戏, 模拟, 玩家}`）：判据是「**游戏行为词**」——戏外语境正常、Agent 面必须拦（双面成立才入表）。**元信息词不入**（`AI`/`模型`/`prompt`/`token`/`seed`/`tick`/`profile`/`随机数`/`概率`/`注定`/`luck`）与**纯工程词不入**（`entity_id`/`branch`/`分支`/`abandoned`）⇒ 这两类在**戏外面仍按拦**处理（沉浸契约的第一观感是安全底线）。词表是活资产，**只增不减且同 CR**（codex 域）。
  - **判层模型（订正此前「豁免表」措辞）**：本表**不是** `scan()` 的豁免源——Agent 面分派**永不读它**（S5 §2.5）。它只服务**纯戏外面**扫描 `scan_meta_shell(text)` ＝ `BANNED_WORDS − BANNED_WORDS_META_SHELL`（戏外面比 Agent 面**宽**，但**不是无扫描**：未被 META_SHELL 覆盖的词在戏外面仍拦）。
  - **锚点 `name` 维持 F-6、明确「不接钩子」**（裁 30-B①②）：本接口档名判定式**仍是** `banned_words.scan()`（纯 Agent 词表），**行为与契约零变化**；8 词落地后「存档：第二日」「读档前」等名字**仍被 422 挡**（见上「已知取舍」，非缺陷）。**锚点 name 是跨界字段**（进 D-6 告知帧与 `story_label`）⇒ 回灌路径成立，fail-closed 不放宽。
  - **接线时机 = 空函数先行（YAGNI，裁 30-B②）**：codex M5-S6 只建**空表 + `scan_meta_shell` 空函数**；**首个消费方**（错误 title 国际化 / 未来覆盖层等不进任何 WS 戏内帧的纯戏外面）出现时才接。届时本接口**不改 HTTP 契约**（仍 422 同一 code），只在其自身判定式里按面选表。
- **前端提示口径**：`title` 是人读短标题（戏外工程措辞，§2）；玩家看到的应是「档名含不可用词汇」而非内部词表名——`detail` 里的命中词仅供调试，别直接上屏。

**服务端游标来源**（构造规则，客户端不参与）：
`branch_id` = **当前活跃分支** id（真源定义与取值纪律见 **§1.6**，禁 `'main'` 字面量兜底）、`tick`/`seq` = 世界当前游标、`agent_override` = 当前主角 agent 状态快照（`models.py` §6 PlayerAnchor 的内部结构，不经 HTTP 回传）。
`id` 由 sim 生成：`uuid4().hex[:12]`，与 `sim/api/settings.py:131` 的 profile id **逐字一致**（无前缀惯例——全仓不用 `prof_`/`anc_` 字面前缀；前端按不透明字符串对待，详见 §6.5）。

### 1.3 `PATCH /api/anchors/{anchor_id}` — 重命名

| 项 | 值 |
|---|---|
| 请求 | `AnchorRename` = **仅 `name`**，必填（重命名不接受 `null` 清空） |
| 200 | `AnchorListItem`（改名后的整项） |
| 404 | anchor 不存在 |
| 422 | pydantic 校验失败 |

```jsonc
// PATCH /api/anchors/9f3c1a7b2e04
{ "name": "临河镇第二日" }

// 200 ← 整项回传（列表页直接替换该项，无需再 GET 全列）
{ "id": "9f3c1a7b2e04", "name": "临河镇第二日", "story_label": "第二日 · 清晨 · 雨刚停",
  "created_at": "2026-09-19T03:20:00Z", "protected": true }
```

- **与 `ProfileUpdate` 的差异（有意）**：Profile 的 `name: str | None` 可选择性更新；anchor 重命名语义是全量替换，故 `name` 必填非可空。二者形状相同但约束不同——**不要**为了省事复用 `ProfileUpdate` 模型。
- 只改 `name`；**不动**游标字段（`branch_id`/`tick`/`seq`）与 `agent_override`。改名不改变档指向的世界时刻。
- **改名不动 `updated_at`**（见 §1.4 末条：该列只在 INSERT 时写一次）。否则改个旧档名会让它「变成最新档」并抢走 `protected`，语义错误。
- 对 `protected: true` 的档**允许改名**（保护只约束删除，见 §1.4）。

### 1.4 `DELETE /api/anchors/{anchor_id}` — 删除游标

| 项 | 值 |
|---|---|
| 请求 | 无 body |
| 204 | 已删除，无响应体 |
| 404 | anchor 不存在 |
| 409 | `protected: true` — 拒绝删除（世界线末梢保险） |

**`protected` 语义**：该档是否为当前世界线的**末梢游标**。末梢 = 从它之后没有更新的档（再往后玩家未存档）。删末梢会丢掉「最新的可回退点」，故设保险。

- 判定规则：`protected = NOT EXISTS(其他 anchor.updated_at > 本档.updated_at)`。
- 新建档后，旧档自动降为 `protected: false`（列表接口的 `protected` 是**派生只读字段**，不是用户可改列）。
- 409 是**唯一**的删除拒绝原因；删除不碰世界档（C6）。
- **`protected` 落库**（`player_anchors.protected` 新列）：构造时计算写入，列表时直接读，避免 N+1 查询。
- **`updated_at` 只写一次**（`default=lambda: time.time()`，仅 INSERT 赋值；改名/删除都不改它）。它代表「这个档是什么时候存的」，不是「记录什么时候被改过」——后者若参与排序，改名就会篡改 `protected` 归属。删掉末梢后，剩余档中的最新者**不自动补位**为 `protected`（保守：补位要重算，且删档后立刻有新存档才是常态；真需要时由下一次新建档统一维护）。

### 1.5 切列与 CRUD v2 增补条款（**正式契约**，2026-09-29 合入）

> **裁决依据**：裁 21-C④（`protected` 无写入方暂不切列）→ 裁 26-C④（同上，派单记为「CRUD 落地单再切」）→ **裁 27-C**（D-14 `/current` 保底、**D-15** DELETE 同步摘除，全采 kilo 契约）→ **裁 28-C**（**GAP-A＝0010**、**GAP-B 回填强制**、S-7 归属 kilo 先落函数）。
> 提案原件：`docs/api/m5-batch-c-prestudy-authority.md` §3（K4）+ 审计稿 `docs/api/m5-batch-a-c-compat-audit.md` §3（K5）。本节是**合入后的正典**，施工单以本节为准（不再回看提案稿）。
> **落地现状**：`0008_m5_fork_identity.py` 第 9 项已落 `player_anchors.protected`（`NOT NULL, server_default=0`）；读路径目前**仍是派生**（`anchors.py::_max_updated_at()`）；POST/rename/DELETE **未施工**。

**I. 切列三步（顺序不可颠倒）**

```
[前置 0] POST 路由落地（写入方）——同一事务：清旧末梢 protected=false + 写新档 protected=true（§6.1 A2 锁 + A3）
   ↓
[前置 1] 存量回填迁移 = **0010**（down_revision 指向 0009；0009 已予 branches.rng_state，见 裁 27-B）
        UPDATE player_anchors SET protected = (updated_at = 全表最大)
   ↓
[前置 2] 读路径开关式切换：list_items / get_item / current_item 全部读列，删除派生分支
```

- **回填是强制项（裁 28-C GAP-B）**：`0008` 给存量行的默认值是 `0` ⇒ **只落 CRUD 不回填 = 全表 `protected=false`** ⇒ DELETE 末梢的 409 保险丝**静默失效**（数据不丢，保险丝没了）。回填后必须能断言「`protected=true` 的行数 = 1（空库 0）」。
- **迁移号（裁 28-C GAP-A）**：回填取 **0010**；0009 已由裁 27-B 预定给 `branches.rng_state`，两者都取 0009 会让 alembic 出现两个 `down_revision=0008` 的 head。
- **回滚**：切列若引发回归 ⇒ 恢复派生读路径 + 停用 CRUD 的 `protected` 写入，**列保留不删、不需数据迁移**（列值与派生式在正常态等价）。

**II. 条款 C1~C4**

| 条款 | 内容 |
|---|---|
| **C1** | 读路径从派生切列是**一次性开关**；切列后 `protected` 列是**唯一真相源**，派生分支删除，**不留双读**（双源必漂：`updated_at` 派生 vs 构造时快照，中途改名/删档即分叉） |
| **C2** | 四个末梢消费者**同源**：①列表 `protected` ②`/current` ③WS 首帧 `session_state.anchor`（取 `current_item()` 同一行，自动同源）④WS 标签注册表 `_ANCHOR_LABELS` |
| **C3** | 不变量钉子：常驻断言「`protected=true` 行数 ≤ 1」——存两档后恒 1、**删末梢后为 0 是合法退化态**（见 §1.4 末条「不补位」与 III 的 `/current` 保底） |
| **C4** | 切列前后各面行为对照（正常态 / 退化态）见 III 表 |

**III. v2 增量条款（相对 §1.2–§1.4 的收紧与新增）**

| 路由 | v2 条款 |
|---|---|
| `POST /api/anchors` | ①**同事务**写：新档 `protected=true` + 清其余 `protected=false`；②`updated_at` 只写一次（不变）；③成功响应照 K7 模式调 `register_anchor_id(id, name, story_label)`；④`400 /errors/world-not-ready` 判据 = 当前活跃 loop 存在（`app.state.loop`）；游标 `branch_id` 取**当前活跃分支**（客户端不参与游标，D-16 随 D-10 闭合按此默认） |
| `PATCH /api/anchors/{id}` | ①**不动** `updated_at` / `protected`（复述为硬约束）；②成功后同步刷新 WS 标签表的 `name`（`register_anchor_id` 幂等覆盖） |
| `DELETE /api/anchors/{id}` | ①`409` 当且仅当 **`protected=true`（切列后读列，不再派生）**；②硬删（不变）；③**成功后必须摘除 WS 注册表**：调 `unregister_anchor_id(id)`（裁 27-C D-15 / 28-C S-7，函数已在 `sim/api/ws.py` 落地，**调用点属 CRUD 单**）；④**不补位**（与 §1.4 末条成对） |
| `GET /api/anchors` | 切列后读列（II.C1）；排序仍按 `updated_at`；无分页（§6.2 B1 维持） |
| `GET /api/anchors/current` | **D-14 保底**：判据 = `protected=true` 的行；**若无 protected 行（删末梢后的合法退化态），回退 `max(updated_at)` 保底不 404**，响应 `protected` 字段此时为 `false`（语义=「没有受保护的末梢」）。选此案的理由：若只用 `protected` 为唯一判据，退化态下会 404 而列表里明明有档（玩家视角自相矛盾） |

**IV. 摘除后的 WS 侧错误映射（K5 C-3 口径，**不新增 error code**）**

`unregister_anchor_id` 之后 `load_anchor` 查表未命中 → **`load_failed`**（不是 `bad_anchor`：后者语义是「形状非法/缺失」；「存在过但已删」归载入失败成立），文案「这个档读不出来了」。钉子见 `sim/tests/test_ws_gateway.py::TestUnregisterAnchorId`（注册→摘除→失配 / 标签指针清空 / 告知帧 `anchor=null` / 幂等与可逆，4 例）。

**V. 施工单须同时写死的三件事**（K5 审计发现，防返工）

1. 回填迁移编号 = **0010**（GAP-A）。
2. 回填是**强制**项，且带「true 行数 = 1」断言（GAP-B）。
3. `DELETE` 路由里**必须**有 `unregister_anchor_id` 调用（S-7 调用点）——否则已删档在 WS 侧继续「存在」，`load_anchor` 回假成功。

### 1.6 「当前活跃分支」真源与游标取值条款（**正式契约**，R-4 增补，2026-10-01 合入）

> **依据链**：缺陷 R-4（K7 复验发现 `anchors.py` 游标分支硬编码 `'main'`）→ opencode M5-A4 出条款原件 `docs/data/m5-r4-active-branch-contract.md` → **裁 30-D 全采** → 联合单 = A4 条款 + **kilo 契约面（本节）** + Claude 取值施工。
> **与 §1.5 的体例一致**：条款 R-4.1~R-4.7 的**编号与措辞同 A4 原件、逐字可对**（本节只补接口侧判据、状态码归属与施工钉子，不改原件语义）。**施工单以本节为准**，A4 原件仅作依据核对。
> **配套前置**：opencode M5-A5 迁移 **0012**（`branches.is_current` + 部分唯一索引）落地**前**，真源按 **R-4.3 过渡期**判据（唯一的 `status='active'` 行）。
> **与 §1.2 的关系**：§1.2「服务端游标来源」写的是**目标口径**（「`branch_id` = 当前活跃分支 id」）；本节给出该「当前活跃分支」的**唯一定义与取值纪律**。

**条款 R-4.1（真源定义）**

**当前活跃分支 = `branches` 表中「当前」的那一行**，查询形如 `SELECT id FROM branches WHERE <当前谓词>`。

- 真源是**表**，**不是**：`'main'` 之类的字面量、进程内常量、WS 会话状态、driver 内存态。
- 需要「当前世界线」的读路径**一律**经这一个查询：

| 读路径 | 取值形态 | 边界 |
|---|---|---|
| POST 记档游标（`branch_id`/`tick`/`seq`） | HTTP 内部取，落 `player_anchors` 行 | 响应**不回传**（§0 出戏边界不变） |
| `GET /api/anchors/current` 的分支 | HTTP 内部取（判末梢档用） | 响应**零原始数值**（§0 不变） |
| D-6 告知帧的 branch | 驱动侧取，用于分叉身份 | **禁出网关**（`branch_id` 不进任何 WS 载荷） |
| fast-forward 目标分支 | 驱动侧取 | 禁出网关 |

- **fail-closed**：查不到「当前」⇒ 报「无当前世界线」，**禁止**回退到 `'main'` 或任何默认串。猜分支 = 记档指向错误世界线，比拒绝更坏。

**R-4.1-S（状态码归属｜kilo 裁定，A4 原件留「409/503 由 kilo 契约定」的悬项）**

| 情形 | 契约 | 理由 |
|---|---|---|
| 真源查询 **0 行**（`branches.is_current` 无 1） | **`400` + `/errors/world-not-ready`**（沿用 §1.2 既有机器码，`detail` 写「无当前世界线」） | §1.2 已定「无活跃分支」＝世界未就绪＝400；**零新增 code ⇒ 零快照变更**，前端错误映射不动 |
| **歧义库**：0 行当前 **且** `branches` 存在 ≥2 个 `status='active'` 行 | **同 `400` + 同一 code**，`detail` 写「世界线状态歧义，请重开世界」 | 歧义是**服务端数据完整性**异常而非客户端可重试态；`409` 语义是「客户端动作与当前状态冲突」，`503` 语义是「稍后重试」，两者都误导。**同码 + detail 区分**保住 fail-closed 且不引 500 面 |
| `is_current=1` 第二行 | 写层 **IntegrityError ⇒ fail-closed**，不落 HTTP 面 | DB 层不变量（方案 A），HTTP 面根本到不了 |

- **登记为待升级项（不在本轮）**：若 0012 落地后仍需**机器码级**区分歧义（前端要分别提示「重开世界」vs「稍后再试」），则新增 `500 /errors/branch-ambiguous`——**那是一次快照变更**（ext 补 500 声明 + `shared/openapi.json` 同步 + `gen-protocol` 重生成），**归 kilo 单独立单**，不在 R-4 施工单里顺手做。**登记单见 §2.1（只登记、零施工）**。
- **⚠ 触发形态订正（2026-10-01，K10 核对 0012 落地后的事实；**状态码裁定不变**）**：本节初稿写「当前行 ≥2（歧义，仅 0012 落地前可能）」——落地后**该形态不可达**：部分唯一索引 `ux_branches_current` 使第二个 `is_current=1` 直接 IntegrityError（A5 `test_m5_branch_current.py` 已钉）。**歧义在 0012 后表现为「`is_current` 全 0」**：0012 的 `BACKFILL_SQL` 只在**唯一** active 时置 1，**≥2 个 active ⇒ 一行都不置**（不按 recency 兜底）⇒ `SqlEventStore.current_branch_id()`（`sim/core/persistence/store.py:181`，已落）抛 `NoCurrentBranchError`。**验收构造方式随之确定**：钉 #3 的歧义 fixture = 两条 `status='active'` + `is_current` 全 0，**不是**「硬塞两个 `is_current=1`」（那会被 DB 拒、测不到 HTTP 面）。

**条款 R-4.2（唯一性不变量）**

**同一时刻至多一个「当前」分支。** 该不变量目前**不成立**：`store.py::_assert_branch_writable` 的「不存在即开线」（裁 5）允许向任意新分支名 append 并自动开线，于是分叉后「子线 active + 父线被按需开线再次 active」= 两个当前。

- **R-4.2.1**：`append` 的按需开线必须**收紧**为——仅当 `branches` 表**当前行为零**时才允许开线；已有当前行时向另一分支 append ⇒ fail-closed（`InactiveBranchError` / `MultipleCurrentBranchesError`）。**这是不变量成立的唯一入口**（A5 施工项）。
- **R-4.2.2**：`fork.py` 的「父转 abandoned + 子转 active」是**唯一**允许改变当前行的写路径（现状已如此；只在 `parent_status == 'active'` 时改父——父已 abandoned 时子仍 active，属再分叉，合法）。

**条款 R-4.3（真源载体：`branches.is_current` + 部分唯一索引）**

- **方案 A 采**（A5 迁移 **0012**）：`branches.is_current INTEGER NOT NULL DEFAULT 0` + `CREATE UNIQUE INDEX ux_branches_current ON branches(is_current) WHERE is_current = 1` ⇒ 不变量由**数据库层**保证，第二个 `is_current=1` ⇒ IntegrityError。
- **方案 B 否决**：真源 = `status='active'` 且 `created_at` 最新（靠 recency 猜）。**否决理由**：读档子线（历史点分叉，A3 §3.2）**故意**与父线并存且可能**更晚**被 fork/触碰 ⇒ `created_at` 最新 ≠ 玩家当前线；recency 会把「玩家正在跑的线」换成「最近被分叉出去的线」，且**静默错**——正是 R-4 要根治的病。
- **过渡期（零迁移，0012 落地前）**：「当前」= 唯一的 `status='active'` 行；**若出现 ≥2 个 active ⇒ fail-closed**（按 R-4.1-S 回 400 + 「世界线状态歧义」），**不 recency 兜底**。

**条款 R-4.4（分叉后的当前行归属：head 模式 vs anchor 模式）**

| fork 模式 | 当前行归属 | 被封存父线 | 允许多个读档子线 |
| --- | --- | --- | --- |
| `kind="head"`（现行：读最近档） | **子分支** | 是（`status='abandoned'`） | 否（只有一条当前） |
| `kind="anchor"`（A3：回退旧档） | **父分支保持当前** | **否**（玩家还在跑它） | **是**（多条读档子线并存，`is_current=0`） |

⇒ 「至多一个当前」与「多条读档子线并存」**不矛盾**：读档子线不是当前。head 模式自动把当前行交给子分支；anchor 模式**不动**父分支的当前身份。

**条款 R-4.5（多子并存时的选择规则）**

- 多条读档子线并存时，**由显式用户动作决定**「当前」（读档 / 切档请求显式声明目标分支），**不由任何时间戳或数量规则推断**。
- 读档子线要成为当前 ⇒ 必须走一次显式切换（把目标分支 `is_current=1`、其余置 0，**同一事务内**；撞唯一索引 ⇒ IntegrityError ⇒ fail-closed）。
- 切换后原当前分支**不自动封存**（它可能仍是玩家想切回的线）；封存是显式动作。⚠️ 与 head-fork「父自动 abandoned」不冲突：head-fork 是**派生**新线（双轨存档语义），切档是**回到**既有线。

**条款 R-4.6（与既有条款的接口）**

- **裁 A6（anchor 引用即热钉）**：被任一 anchor 指向的分支永不整分支冷归档 ⇒ 被选为「当前」的分支天然热存，两条款不打架。
- **D-9 / 0010（当前游标 = `protected` 列优先，同刻按 id 降序）**：那是**档**的游标；本契约是**分支**的当前行。两者是不同层：**档游标 → 档的 `branch_id` → 该分支**；**两者不得互相推导**——禁止用「`protected` 档的 branch」当分支当前行（多个档可指同一分支，而当前行是分支属性）。
- **R-6（列表排序，kilo 域）**：与本契约无交集，纯列表顺序。

**条款 R-4.7（施工单须写死——六条钉子，与 §1.5 V 体例一致）**

**⚠ 施工前必读（opencode A4 警告）**：`sim/api/anchors.py` 的**取 `seq`**（`:274` `SELECT COALESCE(MAX(seq), 0) … WHERE branch_id = 'main'`）与**建档**（`:345` `create_item(…, branch_id="main", …)`）**两处必须同改**。只改其一会让档的 `(branch_id, tick, seq)` 三元组**自相矛盾**（branch 指向子线、`seq` 却来自父线）⇒ **比两者都错更坏，且更难查**。

| # | 钉子（可测断言） | 落点 |
|---|---|---|
| 1 | 分叉后 POST 记档 ⇒ 档的 `branch_id` = **子分支**、`seq` 取自**同一分支**（三元组自洽） | `sim/tests/test_m5_anchors_branch_source.py` |
| 2 | 历史点分叉（`kind="anchor"`）后 POST 记档 ⇒ 落在**仍在跑的父分支**（当前行未转移） | 同上 |
| 3 | 多 active ⇒ **fail-closed**：回 `400 /errors/world-not-ready` 且 `detail` 含「歧义」；**断言响应/落库中零处出现 `'main'` 兜底** | 同上 |
| 4 | `is_current=1` 的第二行 ⇒ **IntegrityError**（DB 层不变量，0012 后） | A5 迁移往返钉 |
| 5 | head-fork ⇒ 父 `abandoned` + 子当前；anchor-fork ⇒ 父仍当前 + 子非当前 | 同 #1 文件 |
| 6 | 查不到当前行 ⇒ 报错，**不**回退 `'main'`（钉子须实跑一次「branches 表空 / 全 abandoned」场景） | 同 #1 文件 |

- **落点文件名已写死**：`sim/tests/test_m5_anchors_branch_source.py`（新建）。命名入 `test_m5_*.py` glob ⇒ 自动进每提交 CI 门禁（`ci.yml` M5 步骤），**不得**并入 bench 或用 `-m` 标记排除。
- **验收面在 §5.2**（`[T]`/`[O]`/`[C]` 三类断言 + 跨钉总闸，M5-K10 备齐）——本段是「要什么」，§5.2 是「怎么判红」，两处互引。
- **⚠ 已登记的施工缺口（0012 落地后仍在）**：`0012_branches_current.py` docstring 自述「本迁移**不移动当前行**」⇒ head-fork 后当前行仍停在已被封存的父分支，读档侧会报「无当前分支」。**该缺口由 R-4 施工单的 `fork.py` 当前行交接关闭**（§5.2 钉 #5 即其验收面），不是新缺陷。
- **kilo 域零施工**：本节**不新增 schema、不改快照**（R-4.1-S 刻意复用既有 400 机器码）⇒ `gen-protocol --check` 应保持 EXIT 0、生成物零变化（该保证已升格为 §5.2 的一只总闸）。

## 2. 错误形（ProblemDetail，RFC 7807 风格）

统一错误体（与 `openapi.md` §5 一致）：

```jsonc
{
  "type": "/errors/anchor-not-found",   // 机器可读错误码，URI 风格但不要求可解析
  "title": "玩家档不存在",               // 人读短标题，戏外工程措辞
  "status": 404,                        // 与 HTTP status 一致
  "detail": "9f3c1a7b2e04 不存在"       // 具体上下文（含被拒 id/字段名）
}
```

| 状态码 | `type` | `title` | 触发 |
|---|---|---|---|
| 400 | `/errors/world-not-ready` | 世界未就绪 | 无活跃 loop / 无「当前活跃分支」（含 0 行与歧义两种 fail-closed，判据见 §1.6 R-4.1-S），无法取游标 |
| 404 | `/errors/anchor-not-found` | 玩家档不存在 | PATCH / DELETE 的 `{anchor_id}` 无行 |
| 409 | `/errors/anchor-protected` | 该档不可删除 | DELETE 时 `protected=true` |
| 422 | `/errors/validation` | 请求校验失败 | pydantic `RequestValidationError`（FastAPI 自动，兜底 §3.2） |

- `ProblemDetail` 的形状**固定为 `title` + `status` 必填，`type` + `detail` 可选**（`shared/openapi.json` 保留位已定，勿改）。
- `title`/`detail` 是**戏外工程措辞**，可不进戏内、不回灌 Agent（`openapi.md` §5）。
- 错误响应**不含** `agent_override` / `branch_id` / `tick` 等内部结构。

### 2.1 `/errors/branch-ambiguous` 快照登记单（**只登记，零施工**｜M5-K10，2026-10-01）

> **状态**：**未施工、未登记快照、未进任何生成物**。本节存在的唯一目的是**把 R-4.1-S 的待升级项写成可施工的规格**，让将来那一单不必重新考古。
> **⚠ 本节不是契约**：`shared/openapi.json` 里 `branch-ambiguous` **当前 0 次**（反向钉见 §5.2 总闸），`sim/api/errors.py::_TYPE_TITLE` **无此条目**，HTTP 面**到不了**这个 code。**任何施工单读到本节都不得据此改码**。

| 项 | 值 |
|---|---|
| `type` | `/errors/branch-ambiguous`（URI 风格，不要求可解析，同 §2 其余码） |
| 形状 | **ProblemDetail 四键**（§2 已定形，零新组件）：`type` + `title` + `status` + `detail` |
| `status` | **`500`**（**未裁定为契约值**——见下方「为什么是 500 / 未裁定」） |
| `title` | 候选：`世界线状态歧义`（人读短标题，戏外工程措辞，**待施工时定稿**） |
| `detail` | 形态：说明 `branches.is_current` 无当前行且存在 ≥2 个 `status='active'` 行、需重开世界；**禁**写出分支 id 以外的内部结构 |
| 触发条件 | **歧义库读取**：读「当前活跃分支」真源时，`is_current` 命中 0 行 **且** `branches` 存在 ≥2 个 `status='active'` 行（0012 `BACKFILL_SQL` 对歧义库**一行都不置**的结果，见 §1.6 R-4.1-S 订正） |
| 现状处置 | 走 **`400 /errors/world-not-ready`**（§1.6 R-4.1-S 已裁，本单**不翻案**） |

**与 `400 /errors/world-not-ready` 的边界（一句话）**：`world-not-ready` 答的是「**世界还没准备好**」（可重试：等开线、等 loop 起），`branch-ambiguous` 答的是「**世界线状态自相矛盾**」（重试无用：必须人工重开世界）——**同一读路径的两种失败语义，机器码必须能分开**，否则前端只能把两种都提示成「稍后再试」，玩家对着一个永远好不了的状态反复重试。

**为什么是 500 / 为什么标「未裁定为契约值」**：歧义是**服务端数据完整性**异常（库里的分支状态互相矛盾），不是客户端能修的请求问题（故非 4xx），也不是「稍后重试会好」的瞬时态（故非 503 的通常语义）。选 500 是为了**与「已裁定不选 409/503」不冲突**，且复用既有 ProblemDetail 形。**但 500 面会把 anchors 的 `responses` 声明面扩一格**，属快照变更（见下）⇒ 该取舍**留待施工那一单连同快照一起正式裁定**，本单不定案。

**将来施工那一单必须同改的四处（缺一即半成品，防返工，同 §1.5 V 体例）**：

1. `sim/api/errors.py::_TYPE_TITLE` 增 `"/errors/branch-ambiguous": "世界线状态歧义"`（**不增**则 `title` 退化为「请求错误」，与 `_TYPE_TITLE.get(...) or _STATUS_TITLE[...]` 的兜底链同款坑）。
2. `sim/api/anchors.py`：`NoCurrentBranchError` 的映射**按「是否歧义」分流**——歧义 ⇒ 本 code；其余 0 行情形仍 `400 /errors/world-not-ready`（**R-4.1-S 的 0 行档不许被顺手改道**）。
3. `sim/api/openapi_ext.py` 的 `_attach("/api/anchors", "post", [...])` 补 `"500"` 声明（§5.1 关键坑：`exception_handler` 写的响应**不会自动进** `/openapi.json`）。
4. `shared/openapi.json` 同步 + `npm run gen-protocol` 重生成 + `client/src/net/__tests__/protocol-types.test.ts` 加键集断言。

**禁做的事**：❌ 在 **R-4 施工单**里顺手加（§1.6 R-4.1-S 已明写「归 kilo 单独立单」）；❌ 只改 `errors.py` 不改 ext/快照（⇒ live↔快照漂移破 K3 铁律，前端类型缺该响应）；❌ 借本 code 之名把 **0 行**（真·世界未就绪）也改道成 500。

## 3. sim 全局 404 handler 提案

### 3.1 问题

现状（M5-K1 调研实证）：`sim/api/` 下**无任何 `exception_handler`**，路由以 `raise HTTPException(404, detail=...)`（`settings.py:226,233`）裸错返回：

```jsonc
{ "detail": "anchor 不存在" }     // 非 ProblemDetail 形
```

三个后果：

1. **无 ProblemDetail 形**：错误体是 `{detail}`，客户端拿不到 `status`/`type`，无法做稳定的错误处理分支。
2. **OpenAPI 无 404 响应声明**：FastAPI 的 `HTTPException` 不进 schema → `/openapi.json` 里 PATCH/DELETE 只见 200/204，客户端生成类型里没有错误分支（M2-K3 复验已记录的 3 处 ext 缺 404 = `openapi.md` 记录项，根因即此）。
3. **404 只在路由内显式 raise**：未匹配到路由的 `/api/anchors/xxx` 拼写错误、或 `/api/anchor` 少个 s，会返回 FastAPI 默认 `{"detail":"Not Found"}`，同样非 Problem 形。

### 3.2 提案：三层接法

```python
# sim/api/errors.py（新增，归 Claude 域施工；本文只定契约与接法）
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_STATUS_TYPE = {
    400: "/errors/bad-request",
    404: "/errors/not-found",
    409: "/errors/conflict",
}

def install_error_handlers(app: FastAPI) -> None:
    """全局错误形归一：HTTPException / 404 Route / 422 validation → ProblemDetail。"""

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_TYPE.get(exc.status_code, "/errors/http-error")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": code,
                "title": _TITLES.get(exc.status_code, "请求错误"),
                "status": exc.status_code,
                "detail": str(exc.detail),
            },
        )

    # 未匹配路由的 404 也走 ProblemDetail（Starlette 抛的是 StarletteHTTPException，
    # 与 app.exception_handler(StarletteHTTPException) 同一处理器——上面的分支覆盖它）

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 只回「哪个字段 + 原因」，不回全部错误路径（避免内部结构泄漏）
        first = exc.errors()[0]
        detail = f"{'.'.join(str(x) for x in first['loc'][1:]) or 'body'}: {first['msg']}"
        return JSONResponse(
            status_code=422,
            content={"type": "/errors/validation", "title": "请求校验失败",
                     "status": 422, "detail": detail},
        )
```

**三条要点**：

1. **路由内代码零改动**：`settings.py` / 新 `anchors.py` 继续 `raise HTTPException(404, detail="anchor 不存在")`，只把 `detail` 当 `ProblemDetail.detail` 用。但要**指定精确 type**：404 统一映射 `/errors/not-found` 会丢失「到底是 profile 还是 anchor」的区分度 → 建议路由传机器码而非人话：
   ```python
   raise HTTPException(status_code=404, detail="/errors/anchor-not-found")
   ```
   由 handler 把 `detail` 同时用作 `type`。**这是对 `settings.py` 现状的小幅改写**（4 处 404 + 1 处 422 + 1 处 500），归 Claude 域；若不改写，则统一 type 为 `/errors/not-found`，前端按 `status` 分支即可（可接受降级）。
2. **`RequestValidationError` 不自动进 schema**——它返回的 422 由 handler 产出 ProblemDetail 形，需 §3.3 的 `custom_openapi` 补声明。
3. **handler 不吞噬业务语义**：409 `protected` 仍在路由内 `raise HTTPException(409, detail="/errors/anchor-protected")`，handler 只换形不改状态码。

### 3.3 OpenAPI 声明问题（关键坑）

**`exception_handler` 写的响应不会自动进 `/openapi.json`**——FastAPI 只从 `response_model`/`responses=` 参数生成。解法：在 `sim/api/openapi_ext.py` 的 `custom_openapi()` 里**手动注入响应声明**（与 WS 注入同款机制，M2-K3 已验证可行）：

```python
# openapi_ext.py — custom_openapi() 内，schema 组装后：
PROBLEM_RESPONSE = {"$ref": "#/components/responses/Problem"}
SCHEMAS["ProblemDetail"] = {...}          # 已有（保留位快照已定形）
components.setdefault("responses", {})["Problem"] = {
    "description": "RFC 7807 问题详情（戏外工程措辞，不回灌 Agent）",
    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}},
}
# anchors 路由逐条补 responses（施工时照抄形状）：
#   PATCH / DELETE: {"200"/"204": ..., "404": $ref, "409": $ref(仅 DELETE)}
```

- 快照 `shared/openapi.json` 已有 `components.responses.Problem` + `ProblemDetail`，且 anchors 路径**已经引用了 `$ref: #/components/responses/Problem`**（M2-K3 复验确认）——所以本次施工是**在 sim 侧补齐定义以对齐快照**，不是新增契约。
- 施工后 `TestClient(app).get("/openapi.json")` 应见 anchors 三路由的 404/409/422 响应声明，与快照一致（这同时消解 M2-K3 记录的「ext 缺 3 处 404」）。

## 4. HTTP 错误 vs WS error 通道的关系

两套错误通道**并存且刻意不统一**：

| | HTTP `ProblemDetail` | WS `WsErrorMessage` |
|---|---|---|
| 传输 | HTTP 响应体（请求-响应） | WS 帧（可被服务端主动推，不必须回应某请求） |
| 形状 | `{type, title, status, detail?}` | `{v, ws_seq, channel:"error", type:"error", ref, code, message}` |
| 通道 | `channel` 无此概念 | `channel: "error"`（固定） |
| 措辞 | **戏外工程措辞**（`title`/`detail` 直白） | **戏内第一人称 / 无内部细节**（`ws-protocol.md` §4.5） |
| 失败对象 | HTTP 请求（meta shell 操作） | WS 消息（含戏内动作，如 `move_request` 被拒） |
| 关联请求 | `detail` 含被拒 id | `ref` = 被拒消息的 `type` |

**分流规则**（施工时照此判断）：

- **meta shell 操作失败**（profile/anchor CRUD）→ HTTP ProblemDetail。例：anchor 不存在、重名校验、protected 删除。
- **WS 消息被拒** → `WsErrorMessage` + `code`（`unknown_type` / `bad_channel` / `auth_error`，见 `ws.py:196-256`）。
- **`load_anchor` 的失败走哪边？** → 它是 WS 消息（session 通道），但失败多发生在**载入执行阶段**（anchor 不存在、重放失败）。契约：`load_anchor` 自身**不返回 error 帧作为回答**——前端应在调用前先 `GET /api/anchors` 确认 id 存在；若仍失败（如重放中世界状态损坏），sim 发 `WsErrorMessage`（`ref: "load_anchor"`, `code: "load_failed"`）并**保持现有 WS 连接**不断线。
- **绝不允许**：把 `ProblemDetail.detail` 的工程措辞（"9f3c1a7b2e04 不存在"）塞进 WS `message`；也绝不允许把戏内文风写进 HTTP `title`。

### 4.1 sim WS 分发现状（施工前必读）

`handle_client_message`（`ws.py:210`）当前分发**六类**（K4 提案 §1-§5 已由 M5-K6 全量施工），各走独立 `_handle_*` 纯函数：

| 消息 | 白名单 `_ALLOWED_CLIENT_TYPES` | `_CHANNEL_FOR` | 分发块 | 现状（M5-K6 后） |
|---|---|---|---|---|
| `move_request` | ✅ | ✅ render | ✅ | 完整。**8.6 已修**：非法类型目标（含 bool）→ `error{code:"bad_target"}`；不可达/主角不存在保留静默（§4 权衡，高频消息免噪声） |
| `hello` | ✅ | ✅ session | ✅ | 完整（鉴权握手；错/缺 → `auth_error`） |
| `sync_request` | ✅ | ✅ session | ✅ | **M5-K5 已修**：回 `full_snapshot`（经 `snapshot_payload(loop, pf.tile_map)`）。K1 时曾误记「完整（回 `control_ack`）」——实为**回错型**，契约（`ws-protocol.md:48`）要求回全量快照；K4 发现、K5 首修（提案 §5/§8.7），回归钉 `test_ws_gateway.py::TestSyncRequest` |
| `set_control` | ✅ | ✅ control | ✅ | **M5-K6 已修**：回 `control_ack{action,applied:true,speed?}`（`applied` 恒 true = 8.1 占位）；`pause`/`resume` 走连接级 `_PRE_PAUSE_SPEED` 栈（§1.2：不进 `GameClock`）；`resume` 回 `speed`=暂停前值；`pause` 的 ack 不带 `speed`（schema enum 无 0）；携带 `speed` 容忍忽略（8.2）；`bad_action`/`bad_speed` 拒绝面见 §1.4 |
| `player_impulse` | ✅ | ✅ control | ✅ | **M5-K6 已修**：注册两处（白名单 + channel）成对。入站校验 `bad_impulse`（缺失/非串/全空白）与 `impulse_too_long`（>64 字，戏内 message「话说得太长了，说不清。」）；通过即回**乐观** `impulse_feedback{injected:true,cue,reaction_monologue}`（§2.4「入网即回」，不 await LLM、不改世界态）。`preset` 非串容忍忽略。**`cue` 规则是占位**——冲突度规则表归 LLM 域（8.3），M4 前定稿 |
| `load_anchor` | ✅ | ✅ session | ✅ | **M5-K6 已修**：注册两处。`anchor_id` 缺失/空/非串 → `bad_anchor`；**不透明串纪律**（§6.5）：`anc_01` 等不被前缀特征拒绝，走正常查表 → 找不到即 `load_failed`；**失败不断线**（§3.3），载入异常降级 `load_failed` 不炸 handler。成功走**短期同步路径**：`snapshot_payload` 回 `full_snapshot`（8.4 定案），长期 driver 化 TODO 见提案 §3.4 |

> **M5-K4 交付**：上表四类待修项的分发块契约已出（`docs/api/ws-dispatch-proposal.md`），含验收对表 20 项 + 待裁清单 8 项。本节表格从「现状描述」转为「施工进度跟踪」。
>
> **M5-K5 进度**：8.7（sync_request 回错型）已首修，表中该行由 ⚠️ 转 ✅。K4 §8.4/8.5（load_anchor 发 `full_snapshot` 的时机 + `tile_map` 传递）也已顺便确证走 `pf.tile_map`——`Pathfinder` 已暴露该 property（`pathfinding.py:96-98`），**签名无需变更**（K4 §8.5 备选案成立）。
>
> **M5-K6 进度**：K4 提案 §1-§5.1 全量施工落地（8.1-8.6/8.8 兑现；8.3 规则表与 8.7 sync_request 除外）。§7 验收对表 20 项除 14（K5 已过）外逐条落钉，**钉子共 56 例**（含 8 项 M5-K6 新增边界）。**load_anchor 的两处部署债**：① `_ANCHOR_IDS` 是进程内登记集（同步查表替身）——真实 `GET /api/anchors` 路由（`anchors-api.md` §4）尚未实现，落地时应改为 `register_anchor_id()` 由落库路径调用；② `_ANCHOR_LOAD_HOOK` 是载入钩子占位——「定位→快照→重放」异步 driver 化（提案 §3.4 长期方案）时接入。**error code 词表已收敛**：10 项全小写 snake（`_ERROR_*` 常量），§7 #15 有越界钉子防新码脱管。

**对 M5 的三条影响**（下列为 K1 时点判断；完整分发块契约见 `ws-dispatch-proposal.md`）：

1. **`load_anchor` 需新增注册**（白名单 + `_CHANNEL_FOR: session` + 分发块），否则本契约 §4 的载入链路无从谈起。这属 Claude 域 M5 施工。
2. **`set_control` 的静默忽略是已存缺陷**（不是本契约引入）：契约已定 `ControlAck` 三字段（action/applied/speed），缺的只是分发块。建议 M5 顺手补，或按 §6 待决议单独排期。
3. **前端「先 `GET /api/anchors` 再 `load_anchor`」的预检**（§4 分流规则第 3 条）必须做到——因为当前 `load_anchor` 连 `unknown_type` 都回得不友好。

## 5. 施工清单 + 验收对表（Claude 域，照本文施工）

**验收对表用法**：右列「验收标准」是**可测断言**——Claude 施工后逐条自测；kilo 复验时照此逐条核。
断言分两类：`[T]` = pytest 断言（`sim/tests/test_api_anchors.py`）、`[O]` = OpenAPI/静态形状断言（`client.get("/openapi.json")` 或快照 diff）、`[C]` = 前端类型断言（`client/src/net/__tests__/protocol-types.test.ts`）。
测试 fixture 沿用 `sim/tests/test_m2_openapi_rework.py:46-56` 的 `client` 写法（`LZ_MASTER_KEY` + 临时 sqlite）。

| # | 施工项 | 验收标准（可测断言） |
|---|---|---|
| 1 | `sim/api/anchors.py`：`APIRouter(prefix="/api/anchors", tags=["anchors"])` + 三路由 + pydantic `AnchorCreate`/`AnchorRename`/`AnchorListItem`（`extra="forbid"`） | `[O]` `GET /openapi.json` 后 `paths["/api/anchors"]["post"]["operationId"]=="createAnchor"`、`paths["/api/anchors/{anchor_id}"]["patch"]["operationId"]=="renameAnchor"`、`["delete"]["operationId"]=="deleteAnchor"`（三者与快照逐字同）；`[O]` 路径键确为 `{anchor_id}`（**非 `{id}`**，否则 §5#7 漂移）；`[T]` 三 schema 均 `additionalProperties:false` |
| 2 | `PlayerAnchor` 表补 `protected` 列 + alembic 迁移 | `[T]` 建档后 `AnchorListItem.protected` 为 `bool`；迁移 `upgrade()` 后 `player_anchors` 有 `protected` 列且 NOT NULL 有默认；`[T]` 新建第二档后，第一档 `protected==False`、第二档 `==True`（§1.4 派生规则） |
| 3 | `sim/api/errors.py` §3.2 handler + `main.py` 调 `install_error_handlers(app)` | `[T]` **未匹配路由** 404 也是 ProblemDetail 形（`{"type","title","status","detail"}`，非 FastAPI 默认 `{"detail":"Not Found"}`）；`[T]` 422（缺 `name`）形同 ProblemDetail 且 `status==422`；`[T]` `title`/`status` 必填，`type`/`detail` 出现 |
| 4 | `openapi_ext.py` 注入 `ProblemDetail`/`responses.Problem` + anchors 响应声明 | `[O]` `components.schemas.ProblemDetail` 存在且 `required==["title","status"]`；`[O]` `components.responses.Problem.$ref` 或内联 `content.application/json.schema.$ref` 指 `#/components/schemas/ProblemDetail`；`[O]` anchors 三路由的 404/409/422/400 响应声明齐全（清单见 §5.1） |
| 5 | 路由 404/409 的 `detail` 用 §3.2 机器码（含 `settings.py` 小幅改写） | `[T]` `PATCH /api/anchors/<不存在>` 回 `404` 且 `body["type"]=="/errors/anchor-not-found"`；`[T]` `DELETE` 末梢档回 `409` 且 `type=="/errors/anchor-protected"`；`[T]` `POST` 世界未就绪回 `400` 且 `type=="/errors/world-not-ready"` |
| 6 | 测试：`sim/tests/test_api_anchors.py` | `[T]` **空库** `GET /api/anchors` → `200` + `[]`（**非 404**；这是最易写错的一条）；`[T]` POST 回 `201` 且 body 含全部 5 键 `{id,name,story_label,created_at,protected}`（`story_label` 可为 `""`，**不得缺键**）；`[T]` PATCH 回 `200` 且 `name` 已改、`created_at` 不变；`[T]` `name` 缺失/空串/65 字符 → `422`；`[T]` 越权字段 `{"name":"x","tick":100}` → `422`（`extra="forbid"`）；`[T]` 响应体**不含** `tick`/`seq`/`seed`/`branch_id`/`agent_override`（出戏边界，§0） |
| 7 | `shared/openapi.json` 的 anchors 路径已就绪（M5-K2 归一 `{anchor_id}`） | `[O]` `paths` 键为 `/api/anchors` 与 `/api/anchors/{anchor_id}`；**`/api/anchors/{id}` 必须为 0 处**；`[O]` `AnchorListItem.properties` 恰为 `{id,name,story_label,created_at,protected}` 五键（无 tick/seq/seed/branch_id）；`[C]` `protocol-types.test.ts` K03 #5 绿；`[O]` 形参名逐字 `anchor_id`（`sim/api/anchors.py` 的 `def rename_anchor(anchor_id: str, ...)`），否则 FastAPI 生成 `{id}` 造成漂移 |

### 5.1 OpenAPI responses 声明清单（#4 注入点，供 `custom_openapi` 手抄）

**为什么单列**：`exception_handler` 写的响应**不会自动进** `/openapi.json`（§3.3 关键坑）——必须手注。以下是与 `shared/openapi.json` 逐字对齐的 4 处注入点。

**注入点**：`sim/api/openapi_ext.py::custom_openapi()`（L445）内，`schemas.update(...)`（L457-459）**之后**、`_strip_pydantic_decorations(schema)`（L460）**之前**，加：

```python
# --- anchors 路由 Problem 响应声明（M5-K3 §5.1；与快照 components.responses.Problem 对齐）---
PROBLEM = {"$ref": "#/components/schemas/ProblemDetail"}
components.setdefault("responses", {})["Problem"] = {
    "description": "RFC 7807 问题详情（戏外工程措辞，不回灌 Agent）",
    "content": {"application/json": {"schema": PROBLEM}},
}
_problem_resp = {"$ref": "#/components/responses/Problem"}

def _attach(route_key: str, method: str, codes: list[str]) -> None:
    op = schema["paths"].get(route_key, {}).get(method)
    if op is None:
        return
    for code in codes:
        op.setdefault("responses", {})[code] = dict(_problem_resp)

_attach("/api/anchors", "post", ["400", "422"])                  # 世界未就绪 / 校验失败
_attach("/api/anchors/{anchor_id}", "patch", ["404", "422"])     # 不存在 / 校验失败
_attach("/api/anchors/{anchor_id}", "delete", ["404", "409"])    # 不存在 / 末梢受保护
```

**四类响应 → 状态码 → 触发**（与 §2 表一一对应）：

| 状态码 | 注入到 | `type` 机器码 | 触发条件 | `[T]` 断言 |
|---|---|---|---|---|
| 404 | PATCH / DELETE | `/errors/anchor-not-found` | `{anchor_id}` 无行 | `client.patch("/api/anchors/deadbeef", json={"name":"x"}).status_code==404` |
| 409 | DELETE | `/errors/anchor-protected` | 该档 `protected=true` | 删末梢档 → `409` |
| 422 | POST / PATCH | `/errors/validation` | pydantic 校验失败 | 缺 `name` → `422` |
| 400 | POST | `/errors/world-not-ready` | 无活跃 loop / 分支 | 无世界态时 POST → `400` |

**验收（#4）**：`[O]` 注入后 `client.get("/openapi.json")` 的 `paths["/api/anchors"]["post"]["responses"]` 键集 ⊇ `{201,400,422}`；`paths["/api/anchors/{anchor_id}"]["delete"]["responses"]` 键集 ⊇ `{204,404,409}`；`paths["/api/anchors/{anchor_id}"]["patch"]["responses"]` 键集 ⊇ `{200,404,422}`。**这三条补上后，M2-K3 记录的「ext 缺 3 处 404」随之消解**（§3.3）。

> ⚠ **注入顺序**：必须在 `get_openapi(...)`（L449）**之后**——`get_openapi` 会用 `app.routes` 重建 `paths`，之前注入的会被冲掉。`custom_openapi()` 有 `if app.openapi_schema: return` 缓存（L447-448），故只在首次调用时注入一次，正确。

> ⚠ **两处 M2-K3 遗留注释需 M5 施工时订正**（位于 Claude 域，kilo 不代改）：
> - `sim/api/openapi_ext.py:17`：「anchors 三 schema（M5 阶段）与 ProblemDetail/WsEnvelope 无路由可挂，不施工。」→ M5 施工后应改为「anchors 三 schema 随 M5 路由生成；ProblemDetail/responses.Problem 由本文件 §5.1 注入」。
> - `sim/tests/test_m2_openapi_rework.py` 的 `ADDED_SCHEMAS` 白名单未含 anchors 三 schema（§2.2 判「本轮不施工」）→ M5 施工后复验口径会变（`MISSING in ext` 应为 0），该测试的期望值需同步。

### 5.2 R-4 六钉验收对表（M5-K10，2026-10-01｜`[T]`/`[O]`/`[C]` 三类，沿用 §5 体例）

**归属**：条款在 **§1.6**（R-4.1~R-4.7 + R-4.1-S），本节是它的**验收面**——Claude 域 R-4 施工后逐条自测，kilo 复验照此核。两处互为交叉引用，改一处必须同步另一处。

**已落地的施工基线（复验起点，非本单产物）**：

| 件 | 位置 | 状态 |
|---|---|---|
| 真源读入口 | `sim/core/persistence/store.py::SqlEventStore.current_branch_id`（`:181`）—— 谓词**只有** `is_current`，查不到 ⇒ 抛 `NoCurrentBranchError`（**禁**回退 `'main'`） | ✅ A5 已落（`1eeb294`） |
| 数据面载体 | `sim/core/persistence/alembic/versions/0012_branches_current.py`：`is_current` 列 + 部分唯一索引 `ux_branches_current … WHERE is_current = 1` + `BACKFILL_SQL`（**仅唯一 active 置 1**，≥2 active ⇒ 一行都不置） | ✅ A5 已落 |
| 开线闸收紧 | `CurrentBranchConflictError`（`InactiveBranchError` 子类）——「仅当无当前行才可开线」 | ✅ A5 已落（钉子 `test_m5_branch_current.py`） |
| **待施工** | `sim/api/anchors.py`：`get_current_seq()`（`:264`，现 `WHERE branch_id = 'main'`）与 `create_anchor()`（`:345`，现 `branch_id="main"`）**两处同改**接真源 | ⏳ **Claude 域（R-4 施工单）** |

**fixture 约定**（本组钉子与 §5 既有 `client` fixture 不同，**必须真 branches/events 行**）：
HTTP 壳沿用 §5 的 `client` 写法（`sim/tests/test_m2_openapi_rework.py:46-56`，`LZ_MASTER_KEY` + 临时 sqlite）；
**分支行/事件行**用 async session 直插，照 `sim/tests/test_m5_branch_current.py` 已有的 `_branch(...)`（`:93`）/ `_branch_row(...)` 助手写法（**复用，不重造**）。
落点文件 **`sim/tests/test_m5_anchors_branch_source.py`**（§1.6 R-4.7 已写死）——命名入 `test_m5_*.py` glob ⇒ 自动进每提交 CI 的 M5 步骤，**禁**并入 bench、**禁**用 `-m` 排除。

| # | R-4.7 钉子 | 断言与判红判据 |
|---|---|---|
| 1 | 分叉后 POST 记档 ⇒ `branch_id` = **子分支**、`seq` 取自**同一分支**（三元组自洽） | `[T]` fixture：子分支 `child`（`status='active'`、`is_current=1`、`MAX(seq)=3`）＋父分支 `parent`（`status='abandoned'`、`is_current=0`、`MAX(seq)=99`）——**两分支的 `seq` 必须刻意不等**（否则「只改一处」的缺陷在断言里不可见）。`POST /api/anchors {"name":…}` → `201`，直查 `player_anchors` 新行：断言 `branch_id == "child"` **且** `seq == 3`。**判红**：`seq == 99` ⇒ 取 seq 那处仍按父线取（**三元组自相矛盾，比两处都错更坏**，A4 警告）；`branch_id == "parent"` ⇒ 建档那处未改 |
| 2 | 历史点分叉（`kind="anchor"`）后 POST 记档 ⇒ 落在**仍在跑的父分支** | `[T]` fixture：父 `parent`（`active`、`is_current=1`、`MAX(seq)=5`）＋读档子线 `child`（`active`、`is_current=0`、`MAX(seq)=77`，**故意更大**作 recency 诱饵）。`POST` → `201`，断言新行 `branch_id == "parent"` **且** `seq == 5`。**判红**：`branch_id == "child"`（哪怕 `seq` 对）⇒ 用了「最新/recency」而非真源当前行——正是 R-4.3 否决方案 B 要根治的病 |
| 3 | 歧义 ⇒ **fail-closed**，不默认 `'main'` | `[T]` fixture：**两条 `status='active'` + `is_current` 全 0**（= 0012 `BACKFILL_SQL` 对歧义库的真实结果；**不是**硬塞两个 `is_current=1`——那会被部分唯一索引拒掉、测不到 HTTP 面）。`POST` → 断言 `400` 且 `body["type"] == "/errors/world-not-ready"`、`detail` 含「歧义」（或至少含「无当前活跃分支」）；**断言 `player_anchors` 行数不变**（fail-closed ≠ 「记到某条线上」）。<br>`[T]` **负钉（白盒，K5 审计同款手法）**：读 `sim/api/anchors.py` 源码，断言 `branch_id="main"`／`branch_id = "main"`／`WHERE branch_id = 'main'` **零出现**——钉死字面量兜底复发（R-4 就是这么来的，且它在 K7 复验时潜伏在 `:345` 与 `:274` 两处）。<br>`[O]` 同一场景下 `paths["/api/anchors"]["post"]["responses"]` 键集仍 ⊇ `{201,400,422}` 且**不含 `500`**（歧义**不走** 500，见 §2.1 登记单） |
| 4 | `is_current=1` 第二行 ⇒ **IntegrityError** | `[T]` **已由 A5 覆盖**：`sim/tests/test_m5_branch_current.py` 两例（直接插第二个 `is_current=1`、以及交接时撞索引）断言 `IntegrityError` 且 msg 含 `UNIQUE constraint failed: branches.is_current`。**验收口径＝引用该钉即算通过，本单不重复造**。<br>`[O]` 迁移往返后 `PRAGMA index_list(branches)` 含 `ux_branches_current` 且 `partial = 1`（锁「部分」二字：全列唯一索引会让两条 `is_current=0` 的读档子线互撞，见 R-4.4） |
| 5 | head-fork ⇒ 父 `abandoned` + 子当前；anchor-fork ⇒ 父仍当前 + 子非当前 | `[T]` **⚠ 依赖 `fork.py` 当前行交接**（同属 R-4 施工单；0012 docstring 已自述「本迁移**不移动当前行**……施工单落地前 head-fork 后当前行仍停在已被封存的父分支」——**这是已登记的已知缺口，必须由本施工单关掉**）。head-fork 后断言父 `status=='abandoned'` **且** `is_current==False`、子 `is_current==True`；anchor-fork 后断言父仍 `is_current==True`、子 `is_current==False`。**判红**：head-fork 后当前行仍在父 ⇒ 红；中间态出现两个 1 或零个 1 ⇒ 红（**必须同事务**，否则第二个 `is_current=1` 直接 IntegrityError） |
| 6 | 查不到当前行 ⇒ 报错，**不**回退 `'main'` | `[T]` **三种 0 行情形各跑一次** `POST`（①`branches` 空表 ②全 `status='abandoned'`、`is_current` 全 0 ③唯一 `active` 但 `is_current=0`，= 0012 前的历史库形态）：三者均 `400` + `/errors/world-not-ready`，且 **`player_anchors` 零新增**。**判红**：任一 `201`/`500`/`503` 即红（`201` = 又写进了一条猜的线） |

**跨钉总闸（三条，任一红即整体不通过）**

| 闸 | 断言 | 为什么 |
|---|---|---|
| `[O]` live ≡ 快照 | `client.get("/openapi.json")` 的 anchors 段与 `shared/openapi.json` **逐字段相等**（K3 铁律） | R-4 是**纯服务端取值**改动，协议面零变化；一旦 live 多了 500/409 声明而快照没同步，前端类型与文档即漂移 |
| `[O]` 生成管线 | `cd client && node ../tools/gen-protocol.ts --check` **EXIT 0** 且 `git status shared/` **零 diff** | 这是「R-4.1-S 复用 400 机器码」换来的好处——**钉住它**，防止施工顺手加新 code 把快照面扩一格 |
| `[O]` 登记单反向钉 | `shared/openapi.json`、`sim/api/errors.py`、生成物中 `branch-ambiguous` 出现次数 **各 = 0** | §2.1 是**登记单不是契约**；此钉防它被误当成待施工清单（§2.1「禁做的事」第 1 条） |

**前端 `[C]` 面（K10 新增一条断言，命名有坑）**

`client/src/net/__tests__/protocol-types.test.ts` 增 `M5-K10-R4 #1`：`operations['createAnchor']['responses']` 键集 ≡ 快照（**无 `500`**、无新键），且 `AnchorListItem` 仍**恰为五键**（`branch_id`/`tick`/`seq` 仍不可达，§0 出戏边界）——R-4 改的是服务端取值，前端类型面**零变化**，故只需一条防漂移断言。

> **⚠ 命名冲突（必读）**：该文件已有**历史 M5-K10** 标签（裁 19 `state_delta.plan` 一轮，`:17`/`:369`/`:370`）。本轮单号沿用 **M5-K10**（Claude 派单口径），故**新断言必须用 `M5-K10-R4` 前缀**，**勿复用 `K10 #n`**——否则 grep 锚点会把两轮同名断言混起来，review 时无法分辨。

## 6. 待决议与已知风险

> **提案制说明**：以下为 kilo 提案（K3 提案制），**不擅改契约**，待主树裁决后落档。每项含：现状 / 选项 / 建议 / 影响面。

### 6.1 `protected` 判据的并发安全

**现状**：`protected` 在 §1.4 定为落库存列，判据 `NOT EXISTS(其他 anchor.updated_at > 本档.updated_at)`——即「最新一档」。当前 sim 无任何显式锁（无 `asyncio.Lock`/`StaticPool`/`BEGIN IMMEDIATE`），`ProfileStore` 每方法各开一个 session、事务短；单用户本地运行（`openapi.md` §2）。FastAPI 异步 handler 与 WS 驱动协程共享一个事件循环，**同一 `POST` handler 内的读与写之间可能被 `await` 切开**。

| # | 选项 | 描述 | 评估 |
|---|---|---|---|
| A1 | 维持现状派生 | 同 §1.4 判据，靠 SQLite 隐式行锁 | 竞态窗口 = 「查最大 updated_at」到「写本档」之间被切。最坏后果：两档同为 `protected=true` 或**无一档为 true**（旧的未清）。**不会丢数据**，只影响保险丝有效性 |
| A2 | 显式进程锁 | `AnchorStore` 上挂 `asyncio.Lock`，写方法包住 | 覆盖率最全（同进程内所有写路径串行），成本一行。但锁只在单进程有效（多 worker 时无效，sim 当前单进程） |
| A3 | 事务内重算 | 把「清旧 protected + 写新档」放同一 `with session` 事务内，靠 SQLite 写事务串行 | 最符合 SQL 语义；若 SQLAlchemy 层两段不是同一事务则仍可能裂。需确认 `ProfileStore` 的事务边界（跨两段 with 则无效） |
| A4 | 反范式化去掉比较 | `protected` 不用「比较得出」，改用一个**单行哨兵表 / `MAX` 查询 + `UPDATE ... WHERE` CAS | 消除读-写间隙，但引入第二张表或更复杂 SQL，收益不成比例 |

**建议**：**A2 + A1 组合**——`AnchorStore` 加 `asyncio.Lock` 包写方法（`create`/`delete`），读方法不加锁（锁是进程内协程串行，与单 worker 部署匹配）。理由：①本问题是「进程内协程交错」而非多进程并发，锁即根治；②成本一行、无 schema 改动；③即使锁失效，退化到 A1 也只是保险丝偶发失效，不丢存档（C6 世界档不受影响）。
**不改的部分**：`updated_at` 只写一次（§1.4）本身就是最强的竞态削减——没有「时间被后续写入推进」，判据的输入就不漂。
**影响面**：`sim/api/anchors.py`（新增，非已有代码）；无快照变更；无前端变更。

### 6.2 分页 / 游标

**现状**：`GET /api/anchors` 契约为 `AnchorListItem[]` 裸数组（快照定形，`list[json]` 直返）。`ProfileStore.list_profiles` 是 `.order_by().all()` 全量。玩家档语义 = 玩家手动存的进度点（DESIGN §12：自由创建/命名/回退），数量级是**十位数而非万级**。

| # | 选项 | 描述 | 评估 |
|---|---|---|---|
| B1 | 维持裸数组（不分页） | 照 §1.1 现状 | 前端一处 `map` 渲染；与 profiles 列表形状完全一致（UI 组件可复用）。十位数量级下无性能问题 |
| B2 | offset/limit 分页 | `?limit=20&offset=40` | 存档列表对「跳到第 N 页」无真实需求；offset 深翻页在排序变动时会漏/重 |
| B3 | 游标分页 | `?cursor=<updated_at>&limit=20` + 响应包 `{items, next_cursor}` | 改动快照顶层形（`AnchorListItem[]` → 对象），**破坏已生成的前端类型**（K03 测试、settingsApi 同款）；获得的能力（深翻页）本场景用不到 |
| B4 | 上限截断 | 裸数组不变，但服务端超过 N 条只回最新 N 条 + `total` 头 | 需加响应头字段，仍是形状微调 |

**建议**：**B1，本版不加分页**。理由：①DESIGN §12 玩家档是玩家主动存的少量进度点，与「无限增长的数据集」不同性质；②`AnchorListItem[]` 与 `ProfileListItem[]` 同形，meta shell UI 可复用同一个列表组件（cline 前端域的最短路径）；③一旦将来真要分页，因为**响应体形不变**（仍可保持数组），只需加 query 参数即可演进，不会破坏已生成类型。
**明确否决 B2/B3/B4 的原因**：三者都为本版引入复杂度，换取一个本场景不存在的需求；B3 还额外破坏类型兼容。
**升级触发条件**（写进契约防遗忘）：单档 `agent_override` 很大 + 玩家档过百 → 届时走 B3 并改 `AnchorListPage` 新 schema，老字段保留过渡（versioning.md §7 登记）。
**影响面**：无（维持现状）；仅需在 §1.1 明记「无分页」为有意决策——已由本表落档。

### 6.3 DELETE 语义：软删 vs 硬删 vs 归档

**现状**：§1.4 定为硬删（删 `player_anchors` 行，世界档不动）。DESIGN C6 只说世界档 append-only，**未规定玩家档删除的物理形态**。快照 DELETE 响应是 `204` 无 body，已定形。

| # | 选项 | 描述 | 评估 |
|---|---|---|---|
| C1 | 硬删（现约定） | `DELETE FROM player_anchors WHERE id=?` | 最简单、204 无 body 与之天然匹配。玩家「不想看到这个档了」即彻底消失 |
| C2 | 软删（`deleted_at` 列） | 打标记，列表过滤掉 | 可「撤销删除」；但列表接口需加过滤条件、`protected` 判据要把软删行排除（NOT EXISTS 子查询多一个 `AND deleted_at IS NULL`），复杂度上渗 |
| C3 | 归档（移到 `abandoned` / 冷表） | 与 §12「abandoned 分支冷归档」同思路 | 语义上最贴 §12；但 §12 的 abandoned 说的是**分支**不是玩家档，把两个 abandoned 混义会误导后来读者 |
| C4 | 拒绝删（只允许改名） | 不提供删除 | 与「自由创建、命名、回退」冲突——玩家无法清理试错档 |

**建议**：**C1 硬删**，与 §1.4 / 快照 204 保持一致。理由：①世界档不可删（C6）已保证「删玩家档永远不销毁世界历史」——玩家能删的只是**自己的游标**，这是最低风险面；②204 无 body 是快照定形，软删/归档都要加过滤或迁表，属自找麻烦；③软删的「可撤销」价值在本地单用户存档场景很弱（玩家删档是有意的，误删可重新存一个）。
**若将来要 C2 的触发条件**：出现「误删后要求恢复」的真实反馈，再加 `deleted_at`——届时是**加列 + 加过滤**，不动 204 契约。
**影响面**：无（维持硬删）；`player_anchors` 表不增删列（除 §1.4 的 `protected`）。

### 6.4 ProblemDetail 要不要 `instance` 字段

**现状**：RFC 7807 的 `instance`（本错误发生的 URI 引用，如 `/api/anchors/9f3c1a7b2e04`）**不在** `shared/openapi.json` 的 `ProblemDetail` 快照里（现有：`type`/`title`/`status`/`detail`）。加它 = 改快照 schema + regen protocol.ts + 前端类型测试三处联动（K03 惯例）。WS 侧无对应字段（`WsErrorMessage` 无 instance）。

| # | 选项 | 描述 | 评估 |
|---|---|---|---|
| D1 | 不加（现约定） | 维持四字段 | `detail` 已含被拒 id（如 `"9f3c1a7b2e04 不存在"`），信息不丢 |
| D2 | 加 `instance`，回**客户端请求的 URL** | 如 `/api/anchors/9f3c1a7b2e04` | 对单用户本地应用**零价值**：URL 就是前端自己拼的，回显它等于把前端刚发出去的东西还回来 |
| D3 | 加 `instance`，回**规范化资源 URI** | 如 `anchor:9f3c1a7b2e04` | 有微价值（机器可关联到具体资源），但需要定义命名空间，且前端目前无处消费 |
| D4 | 不加 `instance`，改用 `detail` 承载（现约定的一种实现） | `detail: "anchor 9f3c1a7b2e04 不存在"` | 同 D1 |

**建议**：**D1（不加）**。理由：①RFC 7807 的 `instance` 是为**跨服务/日志关联**设计的，本项目是单用户本地应用，无此需求；②`detail` 已把被拒 id 带给前端，前端 `SettingsApiError` 只用 `status` + `detail`（`settingsApi.ts:23-35` 实证）——加 `instance` 是 TS 侧无人读取的死字段；③快照 `ProblemDetail` 是**保留位已定形**（M2-K3 已按 4 字段对齐 ext），加字段等于推翻 K3 的一次对齐，形成返工。
**如果将来要加**：应由「日志/遥测需要」驱动（而非 RFC 完备性驱动），且必须走 K03 三处联动 + versioning.md §7 登记。
**影响面**：无（不加）；明确把「RFC 7807 字段完备性不是目标，前端可消费性才是」写进契约，防后人「补字段」式返工。

### 6.5 附带发现：`anc_` 前缀惯例不存在（K1 文档小误，已订正）

K1 版 §1.2 曾写「`id` 由 sim 生成（建议 `anc_` 前缀 + 短随机，与 `prof_` 惯例一致）」——**该惯例不存在**。实证：`sim/api/settings.py:127-131` 与 `memory_store.py:60` 均用 `uuid4().hex`（前者截 12 位、后者全长），全仓无任何 `prof_`/`anc_` 字面前缀。
**订正**：anchor id 用 `uuid4().hex[:12]`，与 profile 逐字一致。前端**不得**依赖任何前缀特征做校验或路由（如 `startsWith('anc_')`）——按不透明字符串对待（与 `rtoken` 不透明替身同一纪律：客户端只握引用，不解析其构造）。
**影响面**：仅文档订正；无快照/类型/代码变更。

### 6.6 待决议清单汇总（状态跟踪）

| # | 事项 | kilo 建议 | 状态 |
|---|---|---|---|
| 1 | 路径参数名 `{id}` vs `{anchor_id}` | `{anchor_id}` | ✅ **裁 5 已批，M5-K2 落地** |
| 2 | `protected` 并发安全 | `asyncio.Lock` 包写方法 + 判据不变 | ⏳ 待裁 |
| 3 | 分页/游标 | 不加，维持裸数组 | ⏳ 待裁 |
| 4 | DELETE 语义 | 硬删（C1） | ⏳ 待裁 |
| 5 | ProblemDetail `instance` | 不加（D1） | ⏳ 待裁 |

> 前四条对应 §6.1-§6.4。全部为「维持契约现状 + 明记理由」型提案——**无一条要求改快照**。

### 6.7 已定型决策备忘（K1 → K2 延续，非待裁）

| 事项 | 结论 | 说明 |
|---|---|---|
| `story_label` 构造期空串 | 已定型 | calendar 未就绪时返回 `""`（字段非 null），前端显「未标注」。若 calendar 给出结构化时间，具体格式需与 narrative 域对齐，本文只定非空性 |
| `agent_override` 不回传 | 已定型 | §0 出戏边界。§12 读档需要它，但载入走 WS `load_anchor`（服务端从库自取），**不经 HTTP**，客户端无需该字段 |
| 档名禁词（Agent 词表） | **已定型（裁 29-A ③ / 裁 30-B①）** | 档名过 `scan()`，命中 422 `/errors/anchor-name-rejected`（§1.2 档名禁词小节）。**取舍已知**：戏外语义合法的「存档/读档/分支」类名字会被挡；**明确不接戏外词表钩子**（锚点 name 是跨界字段、有回灌路径，fail-closed 维持）。钩子本身已落集合（`BANNED_WORDS_META_SHELL` 8 词）+ 接线时机（空函数先行），归 codex 域 |
| 列表排序 `updated_at` 降序 | **已定型（裁 29-A R-6「契约为准改实现」）** | K7 实现曾是升序，main `a50f903` 已改；钉子 `test_m5_api_anchors.py::TestSchemaMatchesSnapshot::test_list_is_newest_first` 防回退 |
| 游标 `branch_id` 取当前活跃分支 | **契约 + 验收面已齐（§1.6 + §5.2），⏳ 取值施工在途（Claude 域）** | 数据面载体已由 A5 落地（0012 `is_current` + 部分唯一索引 + `store.py::current_branch_id`）。**剩余施工**＝`anchors.py` 取 seq（`:264`）与建档（`:345`）**两处同改**，验收面见 §5.2 六钉。另登记：`fork.py` 当前行交接未落（0012 docstring 自述）＝head-fork 后读档侧会报「无当前分支」，由同一施工单关闭（§5.2 钉 #5） |
| 无「删全部 / 批量」端点 | 已定型 | 玩家档数量级十位数（§6.2 同论证），不需要批量操作；也无 list 删除语义 |
| `updated_at` 时间源 | 已定型 | `time.time()`（同 `PlayerAnchor.updated_at`，`models.py:107`）；只写一次（§1.4），不随改名推进 |

## 7. 不在本文件范围

- WS `load_anchor` 消息形状与分叉重放 → `ws-protocol.md` §4.4 + DESIGN §12。
- 迁移与数据安全（SQLite schema、Fernet）→ cline 配置域 + codex 安全域。
- 前端存档管理 UI → cline 前端域。
- 类型生成与切源 → `codegen.md` §4 / §4.1（本契约的 schema 已进快照，不改变切源暂缓结论）。
