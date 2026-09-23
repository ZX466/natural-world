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
    "id": "anc_01",
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
  "id": "anc_01",
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
`id` 由 sim 生成（建议 `anc_` 前缀 + 短随机，与 `prof_` 惯例一致）。

### 1.3 `PATCH /api/anchors/{id}` — 重命名

| 项 | 值 |
|---|---|
| 请求 | `AnchorRename` = **仅 `name`**，必填（重命名不接受 `null` 清空） |
| 200 | `AnchorListItem`（改名后的整项） |
| 404 | anchor 不存在 |
| 422 | pydantic 校验失败 |

```jsonc
// PATCH /api/anchors/anc_01
{ "name": "临河镇第二日" }

// 200 ← 整项回传（列表页直接替换该项，无需再 GET 全列）
{ "id": "anc_01", "name": "临河镇第二日", "story_label": "第二日 · 清晨 · 雨刚停",
  "created_at": "2026-09-19T03:20:00Z", "protected": true }
```

- **与 `ProfileUpdate` 的差异（有意）**：Profile 的 `name: str | None` 可选择性更新；anchor 重命名语义是全量替换，故 `name` 必填非可空。二者形状相同但约束不同——**不要**为了省事复用 `ProfileUpdate` 模型。
- 只改 `name`；**不动**游标字段（`branch_id`/`tick`/`seq`）与 `agent_override`。改名不改变档指向的世界时刻。
- **改名不动 `updated_at`**（见 §1.4 末条：该列只在 INSERT 时写一次）。否则改个旧档名会让它「变成最新档」并抢走 `protected`，语义错误。
- 对 `protected: true` 的档**允许改名**（保护只约束删除，见 §1.4）。

### 1.4 `DELETE /api/anchors/{id}` — 删除游标

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
  "detail": "anc_99 不存在"             // 具体上下文（含被拒 id/字段名）
}
```

| 状态码 | `type` | `title` | 触发 |
|---|---|---|---|
| 400 | `/errors/world-not-ready` | 世界未就绪 | 无活跃 loop / 分支，无法取游标 |
| 404 | `/errors/anchor-not-found` | 玩家档不存在 | PATCH / DELETE 的 `{id}` 无行 |
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
- **绝不允许**：把 `ProblemDetail.detail` 的工程措辞（"anc_99 不存在"）塞进 WS `message`；也绝不允许把戏内文风写进 HTTP `title`。

### 4.1 sim WS 分发现状（施工前必读）

`handle_client_message`（`ws.py:188`）当前只分发 3 类，其余进白名单后也**静默 `return None`**：

| 消息 | 白名单 `_ALLOWED_CLIENT_TYPES` | `_CHANNEL_FOR` | 分发块 | 现状 |
|---|---|---|---|---|
| `move_request` | ✅ | ✅ render | ✅ | 完整（寻路 + `issue_move`） |
| `hello` | ✅ | ✅ session | ✅ | 完整（鉴权握手） |
| `sync_request` | ✅ | ✅ session | ✅ | 完整（回 `control_ack`） |
| `set_control` | ✅ | ✅ control | ❌ 无 | **静默忽略**——白名单放行但落 `return None`，客户端收不到 ack 也不知被拒 |
| `player_impulse` | ❌ | ❌ | ❌ | 压根未注册 → 回 `unknown_type` error 帧 |
| `load_anchor` | ❌ | ❌ | ❌ | 压根未注册 → 回 `unknown_type` error 帧 |

**对 M5 的三条影响**：

1. **`load_anchor` 需新增注册**（白名单 + `_CHANNEL_FOR: session` + 分发块），否则本契约 §4 的载入链路无从谈起。这属 Claude 域 M5 施工。
2. **`set_control` 的静默忽略是已存缺陷**（不是本契约引入）：契约已定 `ControlAck` 三字段（action/applied/speed），缺的只是分发块。建议 M5 顺手补，或按 §6 待决议单独排期。
3. **前端「先 `GET /api/anchors` 再 `load_anchor`」的预检**（§4 分流规则第 3 条）必须做到——因为当前 `load_anchor` 连 `unknown_type` 都回得不友好。

## 5. 施工清单（Claude 域，照本文施工）

1. `sim/api/anchors.py`：`APIRouter(prefix="/api/anchors", tags=["anchors"])` + 三路由 + pydantic `AnchorCreate`/`AnchorRename`/`AnchorListItem`（`extra="forbid"`，同 `ProfileListItem`）。
2. `PlayerAnchor` 表补 `protected` 列 + alembic 迁移（M5 数据迁移归 cline/perf 域协作；本文只定列语义）。
3. `sim/api/errors.py` §3.2 handler + `main.py` lifespan 调 `install_error_handlers(app)`。
4. `openapi_ext.py` §3.3 注入 `ProblemDetail`/`responses.Problem` + anchors 响应声明。
5. 路由 404/409 的 `detail` 改用 §3.2 要点 1 的机器码（含 `settings.py` 5 处，小幅改写）。
6. 测试：`sim/tests/test_api_anchors.py`（列表空库 200、建/改名/删、protected 409、404 形、422 形、pydantic 越权字段 422）。
7. `shared/openapi.json` 的 anchors 路径**已就绪**（含 `{id}` 参数名），**除非 §6 参数名决议改了，否则不动快照**。

## 6. 待决议与已知风险

| # | 事项 | 说明 / 建议 |
|---|---|---|
| 1 | 路径参数名 `{id}` vs `{anchor_id}` | 快照现为 `{id}`（与 `openapi.md` §3 一致）。K3 曾把 settings 的 `{id}` 改为 `{profile_id}` 对齐 FastAPI 形参名。**建议**：新路由形参直接取 `anchor_id`，并把快照两路径与 `openapi.md` §3 同步改 `{anchor_id}`——一次性做对，免 M5+ 再返工。若求稳不动快照，则形参必须叫 `id`。**需 Claude 裁决**（改快照 3 行，kilo 可顺手做）。 |
| 2 | `story_label` 构造期空串 | calendar 未就绪时返回 `""`。若 calendar 给出结构化时间，`story_label` 格式（`第二日 · 清晨 · 雨刚停`）需与 narrative 域对齐，本文只定字段非 null |
| 3 | `agent_override` 不回传 | 契约确定不回传。但 §12 读档需它——注意：载入走 WS `load_anchor`（服务端自己从库里取），**不经 HTTP**，故客户端无需该字段 |
| 4 | 无「删全部 / 批量」端点 | 玩家档数量级小（十位数），不需要分页与批量 |
| 5 | 并发 | 单用户本地运行（`openapi.md` §2），无需并发/幂等设计；`updated_at` 用 `time.time()`（同 `PlayerAnchor.updated_at`） |

## 7. 不在本文件范围

- WS `load_anchor` 消息形状与分叉重放 → `ws-protocol.md` §4.4 + DESIGN §12。
- 迁移与数据安全（SQLite schema、Fernet）→ cline 配置域 + codex 安全域。
- 前端存档管理 UI → cline 前端域。
- 类型生成与切源 → `codegen.md` §4 / §4.1（本契约的 schema 已进快照，不改变切源暂缓结论）。
