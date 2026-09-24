# HTTP 端点设计（docs/api/openapi.md）

> 能力域：接口 / 兼容性（kilo） | 对齐 DESIGN.md §2 C3 §4 §6 §12 §19
> 本文为**设计文档**，不含实现码。FastAPI 自动产出 OpenAPI schema（`/openapi.json`），前端类型由 `codegen.md` 管线生成。

## 1. 边界定位：戏外 meta shell

所有 HTTP 端点属于 §2 C3 的**戏外（meta shell）**——只服务人类玩家，**任何字段不得回流进 Agent prompt 或世界事件日志**。这与 WS 的戏内/渲染通道（见 `ws-protocol.md`）严格隔离。

**两条铁律在本接口的落地：**
1. **api_key 只在后端流转、前端永不接触**（§4 cryptography/Fernet；与 codex 安全清单呼应）。
2. **戏外 ≠ 戏内**：settings/profile/anchor 的字段（含 branch_id/tick/seq 等游标）只在此 meta shell 出现，且 UI 不把原始数值当文本展示给玩家；seed 在任何客户端响应中都不出现。

> 决策：anchor 响应不回传原始 tick/seq（玩家按 `anchor_id` 载入、看 `story_label` 叙事标签即可），即便 §11 仅禁止戏内出现 tick/seq，这里仍取更保守口径——零原始世界数值落到前端，降低误回灌 Agent prompt 的风险。

## 2. 认证模型

本项目单用户本地运行（§4「单 profile 手动切换」），无多用户鉴权。LLM 的 `api_key` 是**供应商凭证**，不是用户身份。

- 前端通过设置页提交 `api_key` → 后端 Fernet 加密落库（§6 SQLite）。
- 响应**永不返回** `api_key` 明文，只回掩码指示（如 `sk-…3Xy`）与 `profile_id`。
- 前端持有 `profile_id`（戏外会话引用），不含任何密钥；sim 调 LLM 时服务端解密取用。
- 建议加一个本地 `session` 绑定（非密钥），供 WS 连接关联活动 profile——细节留给 cline 配置域与 codex 安全域。

## 3. 端点清单

| 方法 | 路径 | 用途 | 阶段 |
|---|---|---|---|
| GET | `/api/health` | 存活探针 | M0 |
| GET | `/api/world/map` | 碰撞层静态资产（chunk 模式；走 HTTP 不走 WS） | M0 |
| GET | `/api/settings/profiles` | LLM Profile 列表（api_key 仅掩码） | M1 |
| POST | `/api/settings/profiles` | 新建 Profile（提交 api_key，加密落库） | M1 |
| GET | `/api/settings/profiles/{id}` | Profile 详情（api_key 仅掩码） | M1 |
| PATCH | `/api/settings/profiles/{id}` | 更新（api_key 可选，缺省保留） | M1 |
| DELETE | `/api/settings/profiles/{id}` | 删除 | M1 |
| POST | `/api/settings/profiles/{id}/activate` | 设为活动 Profile（单 profile 手动切换） | M1 |
| GET | `/api/anchors` | 玩家档列表 | M5 |
| POST | `/api/anchors` | 新建游标（在当前会话点分叉标记） | M5 |
| PATCH | `/api/anchors/{anchor_id}` | 重命名 | M5 |
| DELETE | `/api/anchors/{anchor_id}` | 删除游标（不动世界档，见 §12） | M5 |
| GET | `/openapi.json` | FastAPI 自动生成的 OpenAPI schema（codegen 源；FastAPI 默认路径，非 `/api/openapi.json`） | M0 |

> 锚点**载入**（触发世界分叉+重放）不经 HTTP，而经 WS `load_anchor`（见 ws-protocol.md §4.4）——因为载入需在长连接上重建渲染流。CRUD（建/列/改名/删）是元数据操作，归 HTTP。
> **anchors 逐字段契约（校验规则/状态码/ProblemDetail `type` 机器码/`protected` 派生语义/sim 全局 404 handler 提案）见 `anchors-api.md`**——本节只留端点清单与形状样例；施工前必读该文 §5 清单。

## 4. 请求 / 响应 schema

### 4.1 世界地图碰撞层（`GET /api/world/map`，M0）

碰撞层是**静态资产**，走 HTTP 不走 WS（codex 意见⑤）。形状对齐 `sim/api/main.py::world_map` → `map_static_payload`：

```jsonc
// GET /api/world/map → 200
{
  "w": 32,
  "h": 32,
  "tileset": "grid",
  "chunks": [
    { "cx": 0, "cy": 0, "collision_b64": "AQEBAQ…" }   // base64(每格 1 字节 0/1，chunk 内行优先)
  ]
}
```

- `collision_b64` 解码后为可通行位（1=可通行），前端填入 `MapStatic.collision: Uint8Array`，供点击寻路的目标合法性预检（WorldScene）。
- 只读静态资产：**不含** `seed` / `tick` / `entity_id`（出戏边界不变）。
- `full_snapshot.map` 只带 `{tileset, w, h}`（尺寸/风格），碰撞层不在 WS 流里。

### 4.2 LLM Profile（M1 定稿，codex K 系列）

`POST /api/settings/profiles`（请求）——字段对齐 sim `LLMProfile` 表，扁平化：

```jsonc
{
  "name": "deepseek-local",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "api_key": "sk-xxxxxxxx",        // 明文入，后端即 Fernet 加密落库（K1/K2）；响应永不回传
  "temperature": 0.9,               // 可选，缺省 0.7
  "max_tokens": 1800                // 可选，缺省 2048；单决策 <2k tok（§17 M1）
}
```

`GET /api/settings/profiles`（响应，列表项）——**K5 序列化白名单，绝不含 api_key 明文字段**：

```jsonc
{
  "id": "prof_01",
  "name": "deepseek-local",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "temperature": 0.9,
  "max_tokens": 1800,
  "active": true,                   // 单 profile 手动切换用
  "api_key_hint": "sk-***3Xy"       // 仅掩码（K5）；不是密钥，不能用于调用
}
```

- **无 `api_key` / `api_key_enc` / `provider` / `params`**：与 sim 表对齐（无 provider 列），符合 W7 字段最小化。
- `PATCH`：`api_key` 省略即保留原密钥（K1/K3）；提供则重新加密替换。
- `POST …/activate`：置唯一活动，其余 `active:false`（§4「单 profile 手动切换」）。

### 4.3 玩家档 Anchor（戏外元数据）

`POST /api/anchors`（请求）

```jsonc
{ "name": "初到临河" }              // 不带 branch_id/tick/seq——服务端从当前会话取游标
```

`GET /api/anchors`（响应，列表项）

```jsonc
{
  "id": "9f3c1a7b2e04",                        // 不透明 id：12 位 hex（uuid4().hex[:12]）；无前缀惯例，勿用前缀特征校验
  "name": "初到临河",
  "story_label": "第二日 · 清晨 · 雨刚停",   // 叙事化时间标签，非 tick 数值
  "created_at": "2026-09-19T03:20:00Z",       // 真实世界时间，便于玩家识别
  "protected": false                          // 只读：是否世界线末梢（不可删的保险）
}
```

- **不含** `branch_id` / `tick` / `seq` / `seed` / `agent_override` 内部结构——客户端按 `id` 经 WS 载入。
- `DELETE`：仅删玩家游标，**世界档 append-only 永不删除**（C6/§12）；`protected` 为 true 时拒绝删除并返回 409。
- `story_label` 由 sim 用 calendar/§13 叙事化产出，UI 直接显示，绝不显示"tick 86400"。

### 4.4 健康与 schema

`GET /api/health` → `{ "status": "ok", "world_running": true, "in_combat": false }`
（`in_combat` 戏外只读，供 meta shell 显示当前状态，不回流戏内。）

`GET /openapi.json` → FastAPI 原生 OpenAPI 3.1 文档（默认路径），作为 `codegen.md` 的类型源。**注意**：当前 sim OpenAPI 只含 HTTP 请求体，WS 消息与响应模型（ProfileListItem/WorldMapResponse）由 `shared/openapi.json` 协议快照增补（见 codegen.md §4）。

## 5. 错误约定

统一 RFC 7807 风格（FastAPI 可定制）：

```jsonc
{ "type": "/errors/profile-not-found", "title": "Profile 不存在", "status": 404, "detail": "prof_99 不存在" }
```

- HTTP 错误是戏外系统信息，`title`/`detail` 可用工程措辞（不进戏内，不会回灌 Agent）。
- 与 WS 的 `error` 通道不同——WS error.message 须戏内文风（见 ws-protocol.md §4.5）。

## 6. 不在本端点范围

- WS 消息协议 → `ws-protocol.md`；类型生成 → `codegen.md`；版本 → `versioning.md`。
- api_key 加密实现、SQLite schema、Fernet 密钥管理 → 依赖/配置域（cline）+ 安全域（codex）。
- Profile 内 LLM 调用、prompt 装配 → sim/llm（§8）。
