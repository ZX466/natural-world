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

## 1. 三路由契约

BASE = `/api/anchors`。所有路由 `tags: ["anchors"]`，与 `settings.py` 同模块模式。

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
| 请求 | `AnchorCreate` = **仅 `name`** |
| 201 | `AnchorListItem`（含服务端生成的 `id`） |
| 400 | 当前世界未就绪（无 loop / 无活跃分支）→ 无法取游标 |
| 422 | pydantic 校验失败（`name` 缺失 / 超长 / 空） |

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

**服务端游标来源**（构造规则，客户端不参与）：
`branch_id` = 当前活跃分支 id、`tick`/`seq` = 世界当前游标、`agent_override` = 当前主角 agent 状态快照（`models.py` §6 PlayerAnchor 的内部结构，不经 HTTP 回传）。
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
| 400 | `/errors/world-not-ready` | 世界未就绪 | 无活跃 loop / 分支，无法取游标 |
| 404 | `/errors/anchor-not-found` | 玩家档不存在 | PATCH / DELETE 的 `{anchor_id}` 无行 |
| 409 | `/errors/anchor-protected` | 该档不可删除 | DELETE 时 `protected=true` |
| 422 | `/errors/validation` | 请求校验失败 | pydantic `RequestValidationError`（FastAPI 自动，兜底 §3.2） |

- `ProblemDetail` 的形状**固定为 `title` + `status` 必填，`type` + `detail` 可选**（`shared/openapi.json` 保留位已定，勿改）。
- `title`/`detail` 是**戏外工程措辞**，可不进戏内、不回灌 Agent（`openapi.md` §5）。
- 错误响应**不含** `agent_override` / `branch_id` / `tick` 等内部结构。

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

`handle_client_message`（`ws.py:188`）当前只分发 3 类，其余进白名单后也**静默 `return None`**：

| 消息 | 白名单 `_ALLOWED_CLIENT_TYPES` | `_CHANNEL_FOR` | 分发块 | 现状 |
|---|---|---|---|---|
| `move_request` | ✅ | ✅ render | ✅ | 完整（寻路 + `issue_move`）；**校验失败静默 `return None`**（`ws.py:221,230,234`，同属静默缺陷，见 `ws-dispatch-proposal.md` §4） |
| `hello` | ✅ | ✅ session | ✅ | 完整（鉴权握手） |
| `sync_request` | ✅ | ✅ session | ⚠️ | **回错型**：返回 `control_ack{action:"resume"}`（`ws.py:257-266`）——契约要求回 `full_snapshot`（`ws-protocol.md:48`）。**M5-K4 订正**（本行原记「完整（回 `control_ack`）」有误），修法见 `ws-dispatch-proposal.md` §5 |
| `set_control` | ✅ | ✅ control | ❌ 无 | **静默忽略**——白名单放行但落 `return None`，客户端收不到 ack 也不知被拒。修法见 `ws-dispatch-proposal.md` §1 |
| `player_impulse` | ❌ | ❌ | ❌ | 压根未注册 → 回 `unknown_type` error 帧。修法见 `ws-dispatch-proposal.md` §2 |
| `load_anchor` | ❌ | ❌ | ❌ | 压根未注册 → 回 `unknown_type` error 帧。修法见 `ws-dispatch-proposal.md` §3 |

> **M5-K4 交付**：上表四类待修项的分发块契约已出（`docs/api/ws-dispatch-proposal.md`），含验收对表 20 项 + 待裁清单 8 项。本节表格从「现状描述」转为「施工进度跟踪」。

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
| 无「删全部 / 批量」端点 | 已定型 | 玩家档数量级十位数（§6.2 同论证），不需要批量操作；也无 list 删除语义 |
| `updated_at` 时间源 | 已定型 | `time.time()`（同 `PlayerAnchor.updated_at`，`models.py:107`）；只写一次（§1.4），不随改名推进 |

## 7. 不在本文件范围

- WS `load_anchor` 消息形状与分叉重放 → `ws-protocol.md` §4.4 + DESIGN §12。
- 迁移与数据安全（SQLite schema、Fernet）→ cline 配置域 + codex 安全域。
- 前端存档管理 UI → cline 前端域。
- 类型生成与切源 → `codegen.md` §4 / §4.1（本契约的 schema 已进快照，不改变切源暂缓结论）。
