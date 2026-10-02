# M5 批次 C 权力机制 · API 面契约（docs/api/m5-power-api.md）

> 能力域：接口 / 兼容性（kilo） | M5-K11 | 施工单（裁 31-1 下放施工权）
> **依据链**：D-10 裁定「**权力完全不可见**（纯 Agent 内部，协议面零改动）」（裁 27-C）
> → kilo K4 协议面预研（`m5-batch-c-prestudy-authority.md` §2，五条铁律 + 四候选面，**四案全否决**）
> → codex S3 安规判据（`docs/security/m5-authority-criteria-preplan.md`，红线 A/B/C + 8 钉）
> → 裁 31-1 施工下放（opencode 接数据面 0013 + store 读写面；kilo 接 API 面；Claude 接 `sim/npc` 决策层）。
> **状态**：**已施工**（`sim/api/outbound_guard.py` + `sim/api/ws.py::_send_to` 接线 + 18 钉
> `sim/tests/test_m5_power_api.py`）。本稿是**施工级契约**，不是提案；后续机制施工以本稿为准。
> **体例**：对照 `anchors-api.md` §1.6（条款 + 逐钉验收），但**只写施工必需**——不重述 codex 判据全文，
> 只写「API 侧必须怎样」与其可执行形态。

## 0. 一句话与三条硬边界

D-10 之下，API 面的全部工作只有一件事：**确保权力不出现在任何出站体里**，且这件事要有机械闸与可证伪钉。

| 边界 | 内容 | 可执行形态 |
|---|---|---|
| **B1 零新增** | 不新增任何 HTTP 路由、WS 帧 type、WS 字段、事件 kind、错误码 | 钉 §4 第五组 + codex 红线 A 三处闭合枚举 |
| **B2 零数值** | 权力数值 / 档位 / 位阶名在出站体（含嵌套、含列表内元素）零出现 | 闸门 `strip_authority_fields` + 钉 §4 第二/三组 |
| **B3 零旁路** | 权力的表达只能经**既有**叙事面（`monologue` / `perception` / `state_delta.plan`），且不豁免既有扫描闸 | 本稿 §2（钉子归 codex 红线 C 与既有 `test_m5_*` 面） |

## 1. 结论先行：HTTP 面零新路由（论证）

**结论：不新增任何 HTTP 路由/响应模型/错误码。** 论证三条，任一独立成立即足够：

1. **D-10 已裁**：权力完全不可见 ⇒「玩家可读权力状态」这个需求本身不存在 ⇒ 无路由可加。
2. **K4 四案全否决**：`m5-batch-c-prestudy-authority.md` §2.2 的四个候选承载面
   （A 零 schema 改动＝默认、B 扩 `monologue.form`、C `state_delta` 顶层可选数组、D 新 S→C 帧）
   已逐一否决；B/C/D 的唯一动机是「让玩家看见位阶」，而 D-10 把它删掉了 ⇒ **无案可挑**。
3. **HTTP 已有结构性密封**：全部 `/api` 路由都声明了 `response_model`（实测 13 条路由全覆盖，
   钉 `test_every_http_route_declares_response_model`），FastAPI 按 `response_model` 序列化 ⇒
   返回 dict 里的未声明字段**不可能**出现在响应中。**没有 `response_model` 的路由 = 没有闸**，
   该钉把「将来有人加了个裸 dict 路由」变显式红。

**因此施工面收缩为「WS 出站咽喉装闸」**（§3.1）——HTTP 侧零代码、零 schema。

## 2. 权力的表达面（B3，唯一允许的表达路径）

| 面 | 载体 | 既有闸门（不新增） |
|---|---|---|
| `monologue`（thought/bubble/plan） | 文本 | `banned_words.scan()`（`ws.py` 出站终扫）＋ `impulse_gate` 三扫 |
| `perception.narrative` | 文本 | prompt 装配终扫（`assemble_prompt`） |
| `state_delta.plan[].text` | 文本 | 同上（计划文本进 prompt 面） |

**禁旁路三条**（与 codex 红线 C 同源，本稿只强调 API 侧责任）：
- ❌ 为权力叙事加「直通」扫描例外；
- ❌ 把权力塞进 `state_delta` 顶层可选数组（K4 候选面 C 已否决——那会让不可见量变成协议承诺）；
- ❌ 用「位阶标签」把数值叙事化后放进新字段（`{label:string}` 窄组件先例只允许承载**既有可见物**
  如 `story_label`/`SessionAnchor`，权力不在其列）。

**「被操纵感」红线**（`m5-plan.md` 点名的最高安规风险）：权力带来的抱怨**必须自我怀疑**，
指向外部命令源即出戏——`manipulation` 码在权力语境**零豁免**（codex 钉
`test_authority_manipulation_phrases_red` 已就位，机制施工直接用，API 侧零改动）。

## 3. 出站闸（施工面，本单实际改动）

### 3.1 WS 咽喉：`ConnectionManager._send_to`（`sim/api/ws.py`）

**为什么是这里**：广播（`broadcast_json`）、定向（`send_json_to`）、订阅者投递（`send_to_subscriber`）
三面**共用** `_send_to` ⇒ 闸接在这一个函数即**全覆盖**，且**新帧无法绕过**（将来任何人加发送路径，
只要走 manager 就自动过闸；绕过 manager 直发 `ws.send_json` 属白盒负钉可捕获的形态）。

**行为规约**：

| 项 | 规定 | 理由 |
|---|---|---|
| 剥除 | 递归删除禁键（dict/list/tuple 全深度，大小写不敏感） | 数值可能藏在 `actors[].meta` 之类嵌套里 |
| 纯函数 | **不就地改入参**（深拷贝式重建） | 出站构造点常复用同一份 dict，就地掏空会把调用方的世界状态一起改没 |
| 留痕 | 剥除即 `structlog` warning ＋ 追加到 `leak_events()` | **静默丢字段 = 制造新的不可见 bug**：牙齿表达被无声吞掉且无人知晓 |
| 异常 | **不抛**（生产面不因开发期脏数据挂死连接） | fail-closed 落在**钉子**上（红），不落在运行时（连接死） |
| 干净载荷 | **逐字不变、零记录** | 闸门不得扰动正常出站面（否则每个连接每帧都多一次深拷贝） |

**自检面（会抛）**：`assert_outbound_clean(obj)` → `OutboundAuthorityLeak`（带命中路径）。
用途＝测试与开发期断言；**禁止**注册成 HTTP/WS 错误码（§5）。

### 3.2 HTTP 面：不装中间件（论证）

中间件改写响应体需要缓冲整个 body、重算 `content-length`、绕过流式响应——为一批**结构上不可能泄漏**
的响应（§1 论证 3）引入这些风险不划算。**结构密封（`response_model`）+ 钉子**是本仓既有风格的正解
（与 `ProblemDetail` 靠 `openapi_ext` 手工声明而非运行时魔法同源）。将来若某路由去掉 `response_model`，
该钉立即红——那时才讨论装闸。

### 3.3 prompt 装配面：**不在本单所有权**

codex 红线 B 的第三面是 `assemble_prompt` 产物（`sim/agent`/`sim/llm` 域，Claude/sim 决策层）。
本单**只登记不改**：codex 的 `test_prompt_assembly_recursive_clean` 已在测该面；API 侧无需接线。

## 4. 钉子清单（`sim/tests/test_m5_power_api.py`，18 例）

| 组 | 例数 | 覆盖 | 关键钉 |
|---|---|---|---|
| ① `TestForbiddenKeyScanner` | 7 | 递归扫描 + 剥除纯函数语义 | `test_strip_is_pure_and_deep`（不就地改）／`test_key_set_matches_codex_redline_b`（**跨域键集防漂移**） |
| ② `TestOutboundStrip` | 3 | WS 咽喉实测（假 WS 真发） | `test_ws_send_strips_forbidden_keys`（零禁键 + 留痕路径逐条对齐）／`test_ws_send_clean_payload_untouched`（干净面零扰动） |
| ③ `TestWhiteboxNails` | 3 | **白盒负钉** | 禁键字面量在 `sim/api/` 生产代码里只允许出现在闸门模块（防第二真相源）／`_send_to` 源码必须含 `strip_authority_fields`（防闸被摘掉） |
| ④ `TestErrorCodeSeal` | 3 | 错误码面零新增 | WS 词表 11 项闭合且零权力族／快照 `components.responses` 零权力码／`_TYPE_TITLE` 仍 6 项 |
| ⑤ `TestHttpSurfaceSeal` | 2 | 「零新路由」的可执行形式 | 全 `/api` 路由声明 `response_model`／快照 `paths` 零 authority/power |

**分工（不重复造钉）**：codex 的 `test_m5_authority_surface.py` 在**帧构造层**测（闭合枚举 +
代表性帧递归扫描）；本文件在**咽喉层**与**错误码/HTTP 密封层**测。两者可各自独立红。

## 5. 错误码面零新增

- HTTP 沿用 ProblemDetail 四键（`type/title/status/detail`，`title`+`status` 必填，`errors.py`）——
  **权力面不新增任何机器码**（钉 `_TYPE_TITLE` 仍 6 项）。
- WS 错误码词表 11 项闭合（`ws.py::_ERROR_*`）——**权力面不新增 code**。
- **`OutboundAuthorityLeak` 是开发期自检异常，永不进任何出站面**：把「权力泄漏」做成错误码，
  等于给玩家一个「这里有权力机制」的观测信号——**反向违反 D-10**（钉
  `test_no_authority_exception_leaks_into_http_errors`）。

## 6. 对 opencode（0013 + store 读写面）的接口要求

**假设 P1（API → store：本单零依赖）**：API 层**不需要** store 提供任何权力读方法。
若将来 HTTP/WS 确需读，唯一允许形态是 `sim/core/persistence` 暴露**领域方法**；
**`sim/api` 不得直接 import 表模型**（保持既有分层：API 只经 `loop.state` 与 store 门面）。

**假设 P2（store → API：返回值禁含禁键）**：store 任何返回 `dict` 的方法（整行投影
`select(表)`、entity 序列化）**不得**含禁键。若因整行投影不可避免而含了，闸门会剥除并留痕 ⇒
**视为接口违规**，请改为**显式列清单**投影。闸门是第三道防线，不是第一道：
第一道是「白名单式出站构造」（`snapshot_payload`/`delta_payload` 逐字段挑 `rtoken/x/y/sprite/anim`，
不是整行透传），第二道是 `response_model`，第三道才是本闸。

**假设 P3（事件面）**：权力事件若入事件流，kind 必须登记进 `event_validation.PAYLOAD_MODELS`
（闭合集，codex 红线 A③ 钉）且**API/WS 侧零投影**；**新增 kind 会撞 codex 现有钉**，故新增前须同 CR。

**假设 P4（schema 面）**：0013 只加 DB 列，**不经 `openapi_ext` 注入** ⇒ 快照与生成物**零变化**
（与 0009 `rng_state` 同款推理）。若你判断需要注入 ext 或加端点，**先停**：那是 D-10 的推翻，须主树显式提请。

**假设 P5（迁移纪律）**：0013 加列后，`create_all` 建表路径（新库/测试库）与 alembic 路径（旧库）
必须都有该列——两路径分叉的后果已被台账实证（仓库根陈旧 `world.db` 缺列 ⇒ 随机 teardown 红）。

## 7. 键集纪律与协作

- `AUTHORITY_FORBIDDEN_KEYS`（`sim/api/outbound_guard.py`）与 codex 红线 B 的键级资产**同源**、
  **只增不减**；两侧任一改动**必须同 CR**（钉 `test_key_set_matches_codex_redline_b` 会在漂移时报红）。
- 键级判层 ≠ 词级判层：键名管**结构化出站**，`BANNED_WORDS` 管**叙事文本**；两者互补不重复
  （codex `test_authority_words_not_in_banned_surface` 钉住不混层）。
- 扩键面（如机制引入 `authority_tier` 之类新键名）走 CR：先改本模块常量 + codex 红线 B 文档，
  再改 codex 测试副本，**三处同提交**。
- **prompt 装配面**（红线 B 第三面）在 `sim/agent`/`sim/llm` 域，本单不接线；codex 已钉现状。

## 8. 将来机制施工时，API 侧的动作清单

1. 机制加新字段/新表 ⇒ **API 侧零动作**（闸与白名单投影已覆盖）；
2. 机制想加出站面（帧/字段/路由） ⇒ **停，走 CR 推翻 D-10**（不是本单能批的）；
3. 机制加事件 kind ⇒ 登记 `PAYLOAD_MODELS`（opencode/Claude 域），API 侧仍零投影；
4. 机制让 HTTP 需要读权力 ⇒ 停（B1），除非 D-10 被显式推翻且本稿 §1 论证被重写；
5. 任何「为了调试想临时出个权力数值」 ⇒ 用日志（`structlog`）**不用**出站面；日志是本地运维面，
   不是玩家可观测面。

## 9. 不在本稿范围

- 机制本体与决策层（`sim/npc`，Claude 域）；权力数据面（`sim/core/persistence`，opencode 域）。
- 安规判据本体（codex 域，`m5-authority-criteria-preplan.md`）。
- prompt 装配面的扫描接线（`sim/agent`/`sim/llm` 域）。
- T4 P6 真模型一轮判读（主树收官窗口）。
