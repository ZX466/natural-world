# M5-CRUD 复验与代码审查（K7 派单）：§1.5 v2 对表 + OpenAPI live↔快照对账 + F-6 双钉 + 我域代码审查

> 能力域：接口 / 兼容性（kilo） | 状态：**复验/审查稿，提案制零代码零 schema 改动**
> 派单：Claude 主树 `.orca/talking.txt`「M5-K7（续派）」（2026-09-30）｜被审对象：main `12dbbb1` M5-CRUD（Claude 域施工）
> 门禁：只动 `docs/api/`；复验脚本**一次性、不入库**（跑在 `C:\Users\...\Temp\kilo\`，仓库零残留）；未改任何被审代码。
> 依据：`anchors-api.md` §1.5 v2（本人 K6 合入的正典）/ §1.1–§1.4 / §2 / §5 验收对表；裁 27-C/28-C/28-G；`versioning.md` §3/§7。

**缺陷编号口径**：本稿用 **R-n**（review findings），**不与既有 D-n / GAP-n 撞号**。

---

## 0. 结论

**对表结论**：§1.5 v2 的**七条可执行条款全部通过**（C1 无双读 / C2 同源 / C3 ≤1 / D-14 退化保底 / D-15 摘除 / V.1+ V.2 迁移已落 / V.3 调用点在位）。**F-6 双钉两条通过、一条口径冲突**（R-5，HIGH 待裁）。**OpenAPI live↔快照四处漂移**（R-2/R-3，HIGH，其中一处是**悬空 `$ref`**）。**代码审查抓到 1 CRITICAL + 2 HIGH**（R-1 死等挂死事件循环、R-4 分叉后游标指向错分支、R-6 排序违约）。

| # | 分级 | 缺陷 | 证据 | 归属 |
|---|---|---|---|---|
| **R-1** | **CRITICAL** | `main.py::_hook_wait` 在**同一事件循环**内用 `time.sleep` 忙等 fork task ⇒ task 永不推进，**生产 `load_anchor` 会无限死等，整个服务挂死** | 探针 1：`task 完成? False`（0.81s 内 505 次忙等，`future` 亦未完成）；`main.py:130-138` 无超时兜底 | Claude（`main.py`） |
| **R-2** | **HIGH** | live spec **悬空 `$ref`**：`components.responses.Problem.$ref → #/components/schemas/ProblemDetail`，但 live `components.schemas` **无 `ProblemDetail`**（43 个 schema 里没有）⇒ `/openapi.json` 不自洽 | 探针 4：`live ProblemDetail in schemas: False`、`refs 指向 ProblemDetail 次数: 1` | Claude（`_attach_problem_responses`） |
| **R-3** | **HIGH** | live↔快照四处漂移（违反 K3「ext ↔ 快照逐字段相等」铁律）：①`AnchorCreate`/`AnchorRename` live 有 `minLength/maxLength`、快照只有 `{"type":"string"}`；②`GET /current` live **缺 404** 声明（快照有）；③`GET /{anchor_id}` live 有 `get`+422、**快照完全没有 get 操作**；④`ProblemDetail` 见 R-2 | 探针 4 逐项 diff | Claude + kilo（快照侧需同步） |
| **R-4** | **HIGH** | 游标来源**硬编码 `branch_id="main"`**（`anchors.py:343` 与 `get_current_seq()` 的 `WHERE branch_id='main'`）⇒ 分叉后活跃分支是**子分支**时，POST 记的档指向 main 线，读档会载入**错误世界线**（违反 §1.5 v2「取当前活跃分支」） | `anchors.py:272,343`；D3-b fork 已生产挂载 ⇒ 可触发 | Claude（`anchors.py`） |
| **R-5** | **HIGH（待裁）** | F-6 把 **Agent 面向**词表用在**戏外 meta shell** 的档名上：实测「存档：第二日」「读档前」「分支甲」「快照」「重放」「游戏开始」「玩家」**全部 422**——与 DESIGN §2 C3「meta shell 允许存档管理字样」及本项目自订的「戏外禁词不适用」口径直接冲突 | 探针 2（`scan()` 对 10 个档名逐个） | codex 口径 + Claude 落地，需**复议** |
| **R-6** | **MEDIUM** | 列表排序**升序**，契约 §1.1 写「`updated_at` **降序**（最近存的在前）」⇒ 违约。**这条是本人 K7 的实现欠债**（K3 只钉了 D-9 路由，没钉排序） | `anchors.py:118` `order_by(updated_at)`；探针 3：列表 = 插入顺序 | Claude（或我域补钉子后由 Claude 改） |
| **R-7** | **MEDIUM** | F-6 拒绝的 `title` 退化为「请求错误」：`_TYPE_TITLE` 缺 `/errors/anchor-name-rejected`（其余机器码均有中文短标题） | 探针 5：`422 F-6 词表 … title='请求错误'` | Claude（`errors.py` 一行） |
| **R-8** | **LOW** | ①`get_current_seq()` 走私有 `store._session_local` 且表名/`'main'` 双硬编码；②`tick`（读 loop.state）与 `seq`（查 DB max）取自**不同时刻**（契约允许，建议注明）；③POST 先 `_assert_name_clean` 后判世界就绪 ⇒ 无世界时非法名先得 422（契约 §1.2 把 400 列在前） | `anchors.py:262-274,337-343` | Claude |
| **R-9** | **LOW** | ①`register_new_branch` 只 `debug` 日志，但注释称「供后续读档链可载性」——**实际不登记**（这是**对的**：K4 §3.4 警告过子分支 id 与玩家档 id 是两套注册表，勿混），但**注释在夸大功能**，应改成「显式不登记 + 理由」；②`rename_anchor` 里 `register_anchor_id` 与 `_item_payload` **重复注册**（幂等无害）；③`GET /current` 空库 404 复用 `anchor-not-found`（「没有档」vs「这个档不存在」语义可分辨，建议专用码或在契约记明） | `main.py:140-142`、`anchors.py:354-355,325` | Claude（注释/文案） |

---

## 1. 复验方法与盲区

**做法**（一次性脚本，不入库）：①**机制探针**——在真实 asyncio loop 内复现「`create_task` + `time.sleep` 忙等」是否饿死 task（用于判 R-1）；②**活 HTTP 对表**——`TestClient` 打 anchors 五路由，逐条断言 §1.5 v2 条款（含**直改 DB 列**验证「无双读」）；③**live↔快照结构 diff**——逐 schema、逐 path/method/responses 键集对比；④**词表探针**——`scan()` 对 10 个档名与 3 条 `fork_notice` 文案逐个跑。

**盲区（声明）**：
- 未跑**真实 fork 的端到端**（R-4 是**代码级证据 + 契约比对**，未实跑分叉后再 POST 的场景——因分叉需生产 DB 状态，属重环境）。
- 排序/词表等断言取**样本值**，不是穷举。
- 未审 `settings.py` 的 404 换码改动（超出派单列的文件范围）。

---

## 2. §1.5 v2 条款对表（逐条可执行）

| 条款 | 判定 | 复验动作与观测 |
|---|---|---|
| **C1 切列无双读**（读路径全读列） | ✅ **PASS** | 绕过 API 直接把全表 `protected` 改 `false` → `GET /api/anchors` 的 `protected` 同步变 `[False, False]`、`/current` 也随之。若仍有派生式残留，列表会**仍显示末梢 true**（实测没有） |
| **C2 四消费者同源** | ✅ **PASS** | 列表/`/current`/WS `session_state.anchor` 同源（后者取 `current_item()` 同一行）；标签表由 POST/PATCH 经 `register_anchor_id` 供数（探针见 `label={'name': '初到临河', …}`） |
| **C3 不变量 ≤1** | ✅ **PASS** | 连续 POST 两档 → 列表里 `protected=true` 行数 = **1**；直改全 false 后为 0（**合法退化态**，D-14 前提） |
| **D-14 退化保底** | ✅ **PASS** | 全表无 protected 行时 `GET /api/anchors/current` 仍 **200**，回 `updated_at` 最大者且 `protected=false`（语义=「没有受保护的末梢」），**不 404** |
| **D-15 DELETE 摘除** | ✅ **PASS** | 删一个非 protected 档 → `204`，注册表 `before=True → after=False`，`anchor_pointer()` → `None`（调用点在 `anchors.py:366`） |
| **V.1 回填迁移 = 0010** | ✅ **PASS** | `sim/core/persistence/alembic/versions/0010_protected_backfill.py` 已落（2026-09-30 15:20），`down_revision` 指向 0009，`UPDATE … SET protected = 1 WHERE id = (末梢)` |
| **V.2 回填强制 + 断言** | ✅ **PASS（机制）** | 0010 docstring 明写「既有行全是 0」，只回填不切列；切列（读列）已在其后落地 ⇒ 保险丝不会静默失效。**建议**：加一条迁移级断言（回填后 true 行数 ≤ 1），现无钉子覆盖 |
| **V.3 DELETE 必调 `unregister_anchor_id`** | ✅ **PASS** | 同 D-15；调用点在位 |
| **§1.2 POST 五键 + 零原始数值** | ✅ **PASS** | 响应键恰 `{id,name,story_label,created_at,protected}`；`tick`/`seq`/`branch_id`/`agent_override` 零出现 |
| **§1.3 PATCH 不动 `updated_at`/`protected`** | ✅ **PASS** | 改名后 `created_at` 不变；实现只 `row.name = name` |
| **§1.4 409 读列 + 硬删 + 不补位** | ✅ **PASS** | 删末梢 → `409 /errors/anchor-protected`；删非 protected → `204`；删末梢后剩余档保持 `protected=false` |

---

## 3. OpenAPI live↔快照独立对账（§5.1 + §5#7）

**独立复跑**：`cd client && node ../tools/gen-protocol.ts --check` → **通过：生成物与提交一致**（生成物与快照一致；本节问题是 **live ↔ 快照** 漂移，不影响生成物，但会让**未来任何一次 regen 把 live 的真实形状写进快照**时静默改变前端类型）。

**逐项 diff**：

| 项 | live | 快照 | 判定 |
|---|---|---|---|
| `POST /api/anchors` responses | `201,400,422` | `201` | live 齐（快照缺 400/422 声明） |
| `PATCH /{anchor_id}` responses | `200,404,422` | `200,404` | live 齐 |
| `DELETE /{anchor_id}` responses | `204,404,409,422` | `204,404,409` | live 齐（多 422） |
| `GET /current` responses | `200` | `200,404` | ❌ **live 缺 404**（注入清单未覆盖该路由） |
| `GET /{anchor_id}` | live 有 `get`（`200,422`） | **快照无 get 操作** | ❌ **快照漏登记** |
| `AnchorListItem` | — | — | ✅ `live ≡ snap` |
| `AnchorCreate` / `AnchorRename` | `name: {type,string,minLength:1,maxLength:64}` | `name: {type:string}` | ❌ **长度约束双漂** |
| `ProblemDetail` | **live 无此 schema** | 有（`required:[title,status]`） | ❌ **悬空 `$ref`**（R-2） |

**根因与修法建议**：

1. **R-2 悬空 `$ref`**：`anchors-api` §5#4 原文要求「`openapi_ext.py` 注入 `ProblemDetail`/`responses.Problem`」——实做只注了 `responses.Problem`（**指向一个 live 侧不存在的 schema**）。修法二选一：①在 `_attach_problem_responses` 里同时 `schemas.setdefault("ProblemDetail", …)`（与快照逐字对齐，最小）；②把 live 的 `responses.Problem` 改成内联 schema。**我方建议 ①**（快照是真相源，live 侧注入其副本）。
2. **R-3a 长度约束**：`AnchorCreate/AnchorRename` 的 `minLength/maxLength` 是契约（§1.2「与 ProfileCreate 同口径：1..64」）⇒ 应**补进快照**（快照是真相源），而不是在 live 剥掉。注意 `openapi_ext` 已有 `_strip_pydantic_decorations` 后处理，但它是按空 `description` 剥装饰，不会剥长度约束。
3. **R-3b `/current` 缺 404**：`_attach_problem_responses` 的清单加一条 `_attach("/api/anchors/current", "get", ["404"])`。
4. **R-3c 快照漏 `GET /{anchor_id}`**：K3 之前该路由已实现（live 有），但快照只登记了 patch/delete ⇒ **生成物里 `paths['/api/anchors/{anchor_id}']['get']` 缺失**，前端若调「按 id 查」则生成类型里没有该操作。修法：快照补 `get`（含 200/404/422 的 Problem 声明）。
5. **建议补的钉子**（防同类漂移再发生；我域可落，等 Claude 裁）：
   - `live["components"]["schemas"]["ProblemDetail"] == snap[...]`，且**live 内所有 `$ref` 均可解析**（防悬空引用）；
   - `AnchorCreate`/`AnchorRename` ≡ 快照（长度约束一起锁）；
   - §5.1 三处 responses 键集 ⊇ 断言（post/patch/delete）+ `/current` 的 404；
   - 列表排序方向断言（§1.1 降序）——这条同时会把 **R-6** 从「实现欠债」变成「钉子红灯」。

---

## 4. F-6 双钉验证

| 钉 | 判定 | 观测 |
|---|---|---|
| ① scan 消费点 | ✅ **PASS** | `anchors.py:83 _assert_name_clean` 在 **POST 与 PATCH** 两个写路径都调用；不扩词表（复用 `sim.llm.prompts.banned_words.scan`） |
| ② 422 形 | ✅ 形状 PASS / ⚠ title 退化 | ProblemDetail 四键齐全（`type/title/status/detail`）；但 `/errors/anchor-name-rejected` **未登记进 `_TYPE_TITLE`** ⇒ `title="请求错误"`（R-7，其余 5 个机器码都有中文短标题） |
| ③ `fork_notice` 退化行 | ✅ **PASS** | `fork_notice("")` = 「你回到了先前的那段日子」；`fork_notice("x")` = 「你回到了「x」那段日子」；三条样本（含空名退化行）`scan().ok = True` |
| ⚠ **词表口径冲突（R-5）** | ❌ **HIGH 待裁** | `BANNED_WORDS_META` 含 `存档`/`游戏`/`玩家`；`BATCH` PERSIST 含 `分支`/`快照`/`重放`。实测 7/10 个「戏外合法档名」被 422：存档：第二日 / 读档前 / 游戏开始 / 玩家 / 分支甲 / 快照 / 重放；而「初到临河」「第一日」「世界线」放行 |

**R-5 的性质说明（避免误伤）**：F-6 是 codex S2b §4.2 的裁定（注册侧 fail-closed、过现行 scan、零词表扩散），落地面没有走样；**冲突在裁定本身的口径**——Agent 面向的词表被用在**戏外 meta shell** 的玩家自由输入上。按 DESIGN §2 C3（戏外 meta shell 允许「存档管理」字样）与本项目自订的两套禁词口径（narrative 过扫、session 不适用），「存档/读档/分支」恰是戏外**应当允许**的词。⇒ 建议**复议三选一**：①档名不扫（它不回灌 prompt，Agent 看不见）；②扫但只用「戏外词表」（当前为空，等于不扫，但留了钩子）；③维持现状并在契约里明记「档名禁用 Agent 词表词」——**若选③，至少把 `_TYPE_TITLE` 补上中文标题并把禁令写进 `anchors-api` §1.2**（现在契约里没有这条，玩家会莫名被拒）。

---

## 5. 我域文件审查（anchors.py 写路径 / errors.py / ws.py setter）

### R-1（CRITICAL）`main.py::_hook_wait` 同 loop 忙等 ⇒ 生产读档挂死

```python
future = asyncio.get_running_loop().create_future()
task = asyncio.get_running_loop().create_task(_drive())   # 排到本 loop
return _hook_wait(task, future)                          # ← 同 loop 内 time.sleep 忙等
```

`_hook_wait` 用 `time.sleep(0.001)` 轮询 `task.done()`，**阻塞的正是那个 loop 的线程** ⇒ `_drive()` 永远拿不到执行机会 ⇒ `while not task.done()` **永真**。而调用链是 `ws_endpoint`（async，在 loop 线程）→ `handle_client_message`（同步）→ hook ⇒ **命中生产路径**。

- **机制实证**：探针 1 在真实 loop 内复现——`task 完成? False`、`future 完成? False`，0.81s 内 505 次空转。
- **为什么没被现有测试抓到**：CRUD 的 21 例测的是 HTTP 面；`_production_load_hook` 只在 lifespan 里注册，WS `load_anchor` 的测试用例都用 stub hook（`_ANCHOR_LOAD_HOOK = lambda: True`），**从不走真 hook**。
- **后果**：玩家点一次读档 → 事件循环 100% 阻塞 → WS 广播、驱动 tick、其它连接全部停摆；且**无超时兜底**，`handle_client_message` 的 `except Exception` 也救不了（这不是异常，是挂起）。
- **建议修法（三选一，我推荐 ②）**：①**改 async 缝**：`handle_client_message` 保持同步纯函数，但让 hook 返回 `asyncio.Task`，由网关 `await`（分发块返回值的 await 化会破坏「纯函数可单测」铁律，改动面大）；②**批处理范式**（与 K3 `fast_forward` 同构）：handler 只**登记**读档请求并立即回受理帧，驱动侧按帧预算执行分叉，完成时定向回 `session_state` 告知 + `full_snapshot`——**零新增消息类型**、不阻塞握手、且顺带满足 §4.4「读档毫秒级、期间显示片刻后」；③在**独立线程**跑 loop（`asyncio.run_coroutine_threadsafe` + `concurrent.futures` 等待）——能通但把世界推进搬离主 loop，与驱动的 flush 顺序耦合变复杂。
- **无论选哪个，请加一条钉子**：真 hook 在位时 `load_anchor` 必须在**有界时间内**返回（当前是无界）。

### R-4（HIGH）游标分支硬编码 `'main'`

`create_anchor` 传 `branch_id="main"`，`get_current_seq()` 写死 `WHERE branch_id = 'main'`。分叉落地后（M5 的核心卖点就是「读档 = 分叉」，D3-b 的 fork 已生产挂载），**活跃分支是子分支**，此时 POST 记的 `(branch_id, seq)` 指向 main 线 ⇒ `load_anchor` 会把世界拉回 **main 的那一段**，而不是玩家以为的那条线。契约 §1.5 v2 v2 表明写「取当前活跃分支」⇒ 实现违约。

- 取「当前活跃分支」的真源建议：`branches` 表的活动闸门（opencode 裁 5 的 `append` 拒写非 active 分支机制里应有 active 标记或父链判定），或 `app.state` 上挂一个「当前分支 id」（由 fork 编排更新）。**这是数据域接口，建议派 opencode + Claude 联合单**，我域出「游标来源」的契约补充。

### 其余审查意见（R-6 ~ R-9）

- **R-6 排序违约**：`order_by(updated_at)` 升序 vs 契约 §1.1 降序。**这条是本人 K7 的欠债**（K3 只钉了 D-9 路由顺序，没钉排序方向，钉子缺口是我的）。
- **R-7**：`errors.py::_TYPE_TITLE` 补 `/errors/anchor-name-rejected` → 「档名不可用」（一行）。
- **R-8**：`get_current_seq()` 建议提到 store 的公开方法并去私有属性；`tick`/`seq` 取自不同时刻（契约允许，建议 docstring 注明）；POST 的「世界未就绪」判据应**先于**词表扫描（契约 §1.2 的 400 在前）。
- **R-9**：`register_new_branch` 注释改为「**显式不登记**：子分支 id 与玩家档 id 是两套注册表（K4 §3.4），登记会污染 `load_anchor` 的可载性判定」；`rename_anchor` 的双重注册删一处；`/current` 空库 404 的机器码建议专用（如 `/errors/no-anchors`）或在契约 §1.0 记明复用 `anchor-not-found`。

---

## 6. 建议动作清单

| 动作 | 归属 | 优先级 |
|---|---|---|
| 修 R-1（读档挂死）+ 加「真 hook 有界返回」钉子 | Claude（`main.py`） | **P0** |
| 修 R-2 悬空 `$ref`（live 注入 `ProblemDetail` 副本） | Claude（`_attach_problem_responses`） | **P0** |
| 修 R-3a/3b/3c（长度约束入快照 / `/current` 404 注入 / 快照补 `GET /{anchor_id}`） | 快照侧 = **我域**；live 侧 = Claude | **P1** |
| 修 R-4（游标取当前活跃分支） | opencode（真源）+ Claude（取值） | **P1**（分叉可用即触发） |
| 复议 R-5（F-6 词表口径）并把结论写进 `anchors-api` §1.2 | codex（口径）+ Claude（落地） | **P1** |
| 修 R-6（排序降序）+ R-7（title）+ R-8/R-9（注释/次序/文案） | Claude；R-6 我域可先补钉子 | P2 |
| 补 §3 的 5 条钉子（悬空 `$ref` / 长度 / responses 键集 / 排序） | 我域（`sim/tests/test_m5_api_anchors.py` 已有 `TestSchemaMatchesSnapshot` 落点） | P2 |

**本稿零改动声明**：未改 `sim/**`、`shared/**`、`client/**`；复验脚本一次性、不入库；`git status` 仅本文件。
