# WS 分发补缺提案（docs/api/ws-dispatch-proposal.md）

> 能力域：接口 / 兼容性（kilo M5-K4）。**零代码，提案制**——本文只出契约修法，实现归 Claude 域。
> 上游依据：`ws-protocol.md`（§3 消息清单 / §4.3 control / §4.4 session / §4.5 error / §5 出戏边界）、
> `anchors-api.md` §4 分流规则 + §4.1 分发现状（kilo M5-K1 首发现）、`DESIGN.md` §9/§10（时间尺）、
> `m0-core.md` §1（GameClock）、`shared/openapi.json`（消息 schema 唯一真相源）。
> 现状证据：`sim/api/ws.py:188-275`、`sim/api/main.py:171-192`、`sim/core/clock.py:14-92`、`sim/core/tick.py:126-154`。

## 0. 问题定位（K1 首发现 + K4 复核补一条）

> **本节为 K4 时点（2026-09-24）的现状快照，保留作发现记录**；M5-K5/K6 施工后全部转 ✅，
> 施工后状态见 `anchors-api.md` §4.1 表与 §7 对表逐项标注。

`handle_client_message`（`ws.py:188`）只分发 3 类，白名单放行的其余类型**静默落 `return None`**；未注册类型回 `unknown_type`。逐条现状（`anchors-api.md:265-272` 已列，此处补 K4 复核的修正）：

| 消息 | 白名单 | `_CHANNEL_FOR` | 分发块 | 现状（K4 时点） | K4 复核 | 现行 |
|---|---|---|---|---|---|---|
| `move_request` | ✅ | ✅ render | ✅ | 完整（寻路 + `issue_move`） | 校验失败**静默 `return None`**（`ws.py:221,230,234`）——见 §4 | ✅ K6：非法类型 → `bad_target` |
| `hello` | ✅ | ✅ session | ✅ | 完整 | 无缺 | ✅ |
| `sync_request` | ✅ | ✅ session | ⚠️ | **回错型**：返回 `control_ack{action:"resume",speed:1}`（`ws.py:257-266`） | **K4 新发现**：契约要求回 `full_snapshot`。见 §5.1 | ✅ K5：回 `full_snapshot` |
| `set_control` | ✅ | ✅ control | ❌ | **静默忽略**（落到 `return None`） | 本文 §1 | ✅ K6：`_handle_set_control` |
| `player_impulse` | ❌ | ❌ | ❌ | 未注册 → `unknown_type` | 本文 §2 | ✅ K6：注册 + 乐观 feedback |
| `load_anchor` | ❌ | ❌ | ❌ | 未注册 → `unknown_type` | 本文 §3 | ✅ K6：注册 + 失败不断线 |

## 0.1 架构约束：单回复通道（写契约前必读）

**关键前提**：`main.py:184-188` 的循环是「一条入站 → 至多一条出站」：

```python
raw = await ws.receive_json()
reply = handle_client_message(raw, app.state.loop, pf)   # 返回 dict | None
if reply is not None:
    await ws.send_json(reply)
```

`handle_client_message` 签名是 `-> dict[str, Any] | None`——**一次调用最多带回一帧**。所有下述契约都必须落在这个约束内；需要「多帧」的场景（如 `load_anchor` 的过渡叙事 + `full_snapshot`）**不能在 handler 里解决**，须走 driver 侧（§3.3）。

**推论**：三处修复的动作面全部可落在单回复内（`set_control`→`control_ack`、`player_impulse`→`impulse_feedback`、`load_anchor`→`full_snapshot` **或** `error`），无需改 `main.py` 的收发结构。这是本提案坚持「契约修法而非架构改造」的核心理由。

## 1. `set_control` 分发块契约

### 1.1 现状缺口

`set_control` 在 `_ALLOWED_CLIENT_TYPES`（`ws.py:32`）+ `_CHANNEL_FOR := control`（`ws.py:272`）都有，但 `handle_client_message` 无 `if msg_type == "set_control"` 分支 → 落 `ws.py:267 return None`。客户端发 `set_control` 后**永远收不到 `control_ack`**，无法区分「被拒」与「网络丢帧」。

`ControlAckMessage` schema **已就绪**（`shared/openapi.json`）：`required: [v,ws_seq,channel,type,action,applied]`，`action ∈ {pause,resume,set_speed}`，`applied: boolean`，`speed ∈ {1,4,16}`（非 required）。契约写完即挂 `response_model`，无 schema 变更。

### 1.2 分发块契约（建议实现）

> 建议签名：`_handle_set_control(raw, loop) -> dict[str, Any]`（纯函数，便于单测），由 `handle_client_message` 的 `if msg_type == "set_control":` 分支调用。

**校验与动作映射**（`GameClock` API 实证：`clock.py:52-58 set_speed`，`ALLOWED_SPEEDS = {0.0,1.0,4.0,16.0}`——**注意 0.0 = 暂停**）：

| 入站 `action` | 入站 `speed` | 动作（`loop.clock`） | 出站 `control_ack` |
|---|---|---|---|
| `pause` | 忽略（不应携带） | `clock.set_speed(0.0)`；**先存 `_pre_pause_speed`** | `{action:"pause", applied:true}` |
| `resume` | 忽略 | `clock.set_speed(_pre_pause_speed or 1.0)`；清 `_pre_pause_speed` | `{action:"resume", speed:<恢复值>, applied:true}` |
| `set_speed` | `1`/`4`/`16` | `clock.set_speed(float(speed))` | `{action:"set_speed", speed:<speed>, applied:true}` |
| 其它 | 任意 | 不改 clock | `WsErrorMessage{ref:"set_control", code:"bad_action"}`（§1.4） |

**`set_speed` 缺 `speed` 或 `speed ∉ {1,4,16}`** → 不改 clock，回 error 帧（§1.4）。schema 的 `speed: enum[1,4,16]` 是**结果状态**，不是「暂停/恢复」的载体——暂停用 `action:"pause"` 表达（`speed:0` 不入 schema，因为 schema `enum` 无 0）。

**`_pre_pause_speed` 存哪**：它是**连接级会话状态**（非世界状态、非时钟状态）。建议挂在 `ConnectionManager` 的每连接记录上，或 `ws_endpoint` 的局部变量透传。**不写进 `GameClock`**（时钟只答「现在该走几个 tick」，`_pre_pause_speed` 是 UI 会话记忆，属网关职责）。M0 单连接形态可先用模块级 dict（`id(ws) → speed`），M2 多连接前改为连接对象字段。

### 1.3 `applied` 语义（必须定义，否则前端无法分支）

`applied` **不是**「请求被接受」（那是 error 帧的职责），而是「**本帧生效后世界时间尺的净效果是否等于客户端请求**」。两种 `applied:false` 场景：

1. **战斗期暂停请求**（§9 联动）：战斗时间尺由 sim 自动控制（`DESIGN.md:281`），客户端请求 `pause` 时若世界正处 `TimeScale.COMBAT`，**照常暂停但不宣称已按客户端意图切换时间尺**？——不，**建议简化为 `applied:true`**：暂停/倍速与时间尺**正交**（`clock.py:60-66`：`ticks_per_real_second = base × speed`，`base` 由 `_timescale` 决定）。即 `pause` 在战斗期也真实生效（`base=1, speed=0 → 0 tick/s`），故 `applied:true` 恒成立。
2. 因此**当前契约下 `applied` 恒为 `true`**——但字段必须保留：它是**前向兼容接口**，供 M4 起「请求被内部策略钳制」用（如未来「战斗期禁 16x」）。契约明记：**`applied:false` 时 `control_ack` 必带 `wall_note`? 否**——不加字段，用 `message` 语义区分：`applied:false` 走 **error 帧**而非 `control_ack`（见下）。

> **裁决点（待 Claude 确认）**：`applied` 语义选「恒 true 的占位」还是「钳制提示载体」。kilo 建议 **恒 true 占位**：当前无钳制场景，恒 true 最诚实；未来有钳制需求时再定 `applied:false` 的载荷（避免现在造一个永不触发的分支）。

### 1.4 拒绝面（非法输入 → error 帧，不静默）

契约要求（`ws-protocol.md:214`「不静默丢弃」）：所有非法 `set_control` **必须回 error 帧**，不得 `return None`。

| 场景 | 出站 | `code` |
|---|---|---|
| `action` 缺失/非三值 | `error{ref:"set_control"}` | `bad_action` |
| `action=="set_speed"` 但 `speed ∉ {1,4,16}`（含缺失/字符串/`true`） | `error{ref:"set_control"}` | `bad_speed` |
| `action=="pause"/"resume"` 却携带 `speed` | **建议容忍**（忽略该字段，不报错）——与 `move_request` 的宽容风格一致 | — |

**`speed` 的 bool 陷阱**：与 `move_request` 的 `tx/ty` 同类（`ws.py:223-229`：`isinstance(x,int) and not isinstance(x,bool)`）——`set_speed` 的 `speed` 校验**必须**排除 `bool`（JSON `true` 是 `int` 子类，`true ∈ {1,4,16}` 会误判为合法）。这是本契约**最易漏的一条**，已在 §7 立测试钉子。

### 1.5 `timescale`（S→C）联动契约

`timescale` 消息（`TimescaleMessage`，`required:[v,ws_seq,channel,type,mode,active]`，`mode ∈ {normal,combat}`，`note: string|null`）由 **sim 驱动，非客户端响应**：进入/脱离战斗时由 `loop.issue_combat_scale(entering)`（`tick.py:126`）产生 `combat_scale` 世界事件，**WS 层将其投影为 `timescale` 帧广播**（与 `set_control` **无因果链**——客户端不能「请求切战斗时间尺」，`ws-protocol.md:182` 明令）。

- **广播来源**：`run_world_driver`（`ws.py:285`）drain 事件时，遇 `combat_scale` 事件 → 广播 `timescale` 帧。**不在 `handle_client_message` 内**（那是入站处理，无出站广播权）。
- **`note` 字段**：`null` 为常态；戏外调试才填（`ws-protocol.md:188`）。契约要求实现**恒发 `note:null`**（schema 允许省略，但发 `null` 与 `note` 语义一致）。
- **`control_ack` 与 `timescale` 的关系**：`set_control` **只**回 `control_ack`；`timescale` **只**由战斗事件回推。客户端收到的 `control_ack.speed` 是**用户设定的倍率**，**不是**当前有效 tick 率（战斗期有效率 = `1 × speed`）。契约明记此区别，防前端拿 `control_ack.speed` 直算帧率。

## 2. `player_impulse` 注册 + 处理契约

### 2.1 现状缺口

`player_impulse` 不在 `_ALLOWED_CLIENT_TYPES` → 回 `unknown_type`。但 `ws-protocol.md:44` 定义它是「玩家唯一主动动作（M4）」、§6 定「入网即回 `impulse_feedback`」。schema `PlayerImpulseMessage`（`required:[v,ws_seq,channel,type,text]`，`text: maxLength 64`，`preset: string|null`）与 `ImpulseFeedbackMessage`（`required:[...,injected,cue,reaction_monologue]`，`cue ∈ {accepted,hesitation,complaint,resistance}`）**均已就绪**。

### 2.2 注册（两处）

`_ALLOWED_CLIENT_TYPES`（`ws.py:32`）加 `"player_impulse"`；`_CHANNEL_FOR`（`ws.py:270`）加 `"player_impulse": "control"`。**两者必须同批**——否则 `ws.py:207` 的 channel 校验会回 `bad_channel`（`_CHANNEL_FOR.get()` 返回 `None ≠ "control"`）。

### 2.3 接收面契约（入站校验）

| 场景 | 出站 |
|---|---|
| `text` 缺失/非字符串 | `error{ref:"player_impulse", code:"bad_impulse", message:"<戏内文风>"}` |
| `text` 长度 > 64（schema maxLength） | `error{ref:"player_impulse", code:"impulse_too_long", message:"话说得太长了，说不清。"}` |
| `text` 空串 / 全空白 | **建议拒绝**，`code:"bad_impulse"`（空念头无语义） |
| `preset` 非 string/null | 容忍忽略（前向兼容标签，不阻塞） |

**`message` 文风**：`ws-protocol.md:211` 已给样例「话说得太长了，说不清。」——**戏内第一人称、无系统措辞**（`anchors-api.md:250/259` 红线）。`code` 供逻辑分支、不显示。

### 2.4 处理缝（LLM 决策缝）接法边界 ⚠ 本提案最需 Claude 域裁的部分

**问题**：`handle_client_message` 是**纯同步函数**（无 `async`、无 LLM 句柄）。`player_impulse` 的完整链路 = 入站 → 叙事化 → 意愿冲突度 → 注入 Agent prompt → 回 `impulse_feedback`。其中「注入 Agent prompt」是**异步 LLM 域**。

**kilo 建议的三层切法**（保持 `handle_client_message` 同步、纯函数）：

1. **handler 层（同步，本契约范围）**：校验 `text`（长度/非空/bool 无关）→ **立即**构造并返回**乐观** `impulse_feedback`（`injected:true` + 由 sim 文风化层在同步侧粗判的 `cue` + `reaction_monologue`）。这是 `ws-protocol.md:243`「入网即回」的落地。
   - **`cue`/`reaction_monologue` 的同步来源**：契约要求「入网即回」，故这俩**不能等 LLM**。建议 handler 只做**规则化粗判**（如按 `text` 命中冲突词表 → `cue`；`reaction_monologue` 用模板），**真实叙事化由 LLM 域异步补充**（后续 `monologue` 帧演进，`ws-protocol.md:244`「LLM 异步：协议层无感知」）。
2. **投递层（异步，LLM 域）**：handler 把**已校验**的 `text` 塞进一个**无界队列**（`loop` 或 driver 可见），由 LLM 域消费者取走。**handler 不 await、不阻塞**——这是单回复架构的硬约束（§0.1）。
3. **不要做的事**：不在 handler 里 `await` LLM；不在 handler 里直接改 Agent 状态（世界写路径唯一 = `apply`，`ws.py:193` 注释已立此规矩）。

> **给 Claude 的对接 TODO**：M4 施工前须定「冲突度规则表」与「叙事化模板」的存放域（kilo 建议 `sim/perception/` 或新 `sim/llm/impulse.py`）。**本提案只定协议面**：入站校验 + 乐观 `impulse_feedback` + 异步投递语义，不涉规则表内容。

### 2.5 `impulse_feedback.injected` 语义

- `injected:true`：念头已**接受并投递**（不保证 LLM 已处理——异步）。
- `injected:false`：**当前建议不产生**（校验失败走 error 帧）。保留给未来「主角在战斗中/无意识」等**世界态拒绝**；届时 `injected:false` 仍配 `cue`/`reaction_monologue`（表现"没听进去"），并**额外**发 error 帧说明原因。契约明记此扩展位。

## 3. `load_anchor` 注册 + 会话语义

### 3.1 现状缺口

`load_anchor` 未注册 → `unknown_type`。`ws-protocol.md:47` 定「载入玩家档（触发世界分叉+重放，§12）」，`§4.4:193-200` 定载荷 `{anchor_id}`（**注意：该节示例仍写 `anc_01`——`anc_` 前缀惯例不存在，见 `anchors-api.md:405 §6.5`，示例须订正为 12 位 hex**）。`LoadAnchorMessage` schema（`required:[v,ws_seq,channel,type,anchor_id]`）已就绪。

### 3.2 注册（两处，同 §2.2）

`_ALLOWED_CLIENT_TYPES` 加 `"load_anchor"`；`_CHANNEL_FOR` 加 `"load_anchor": "session"`。

### 3.3 会话语义契约（失败不断线）

**分流规则**（复用 `anchors-api.md:258` 的 K1 裁决，此处细化到分发块）：

| 阶段 | 失败点 | 出站 | 连接 |
|---|---|---|---|
| 入站校验 | `anchor_id` 缺失/非字符串 | `error{ref:"load_anchor", code:"bad_anchor", message:"<戏内>"}` | **不断线** |
| 入站校验 | `anchor_id` 形如旧前缀 `anc_…`（不透明串，不校验语义） | 照常按 id 查（**不因前缀拒绝**——`§6.5` 纪律：不透明字符串，禁前缀特征校验） | 不断线 |
| 载入执行 | anchor 不存在 | `error{ref:"load_anchor", code:"load_failed", message:"<戏内>"}` | **不断线** |
| 载入执行 | 重放中世界状态损坏 | 同上 | **不断线** |
| 载入成功 | — | `full_snapshot`（经 driver，见下） | 不断线 |

**「不断线」是硬约束**：`ws-protocol.md:20`「连接生命周期=一个游戏会话」；载入失败**不重建连接**，只回 error 帧（`anchors-api.md:258` 已定）。

### 3.4 单回复架构下的「载入成功」怎么发 ⚠

`load_anchor` 成功需要发 `full_snapshot`（`ws-protocol.md:199`「流 `full_snapshot`」），但 `handle_client_message` **有 loop 引用**（签名含 `loop: TickLoop`），且 `snapshot_payload` **是模块级纯函数**（`ws.py:125`，`main.py:183` 已在用）——所以 handler **可以**同步构造 `full_snapshot` 并作为 reply 返回。**建议**：

- **短期（M5 本批，单回复内）**：handler 校验通过 → 调 `snapshot_payload(loop, tile_map)` 返回。**需要 `tile_map`**：现签名 `handle_client_message(raw, loop, pf)` 无 `tile_map`——**建议加参数**（或从 `pf` 取，`Pathfinder` 持 tile_map）。这是**本提案唯一建议改签名处**，见 §6。
- **长期（M5+，重放落地后）**：「定位 (branch_id,seq) → 快照 → 重放 → 新分支」是**异步、可能多帧**（过渡叙事 + 快照）的流程，**必须走 driver**：handler 只回「载入已排队」类确认（或 `null`），实际 `full_snapshot` 由 `run_world_driver` 在重放完成后广播。**本提案建议**：M5 先落短期方案（重放尚未实现），并在 `ws.py` 留 TODO 指向 §3.4。

### 3.5 与 HTTP `GET /api/anchors` 的预检关系

`anchors-api.md:258` 已定：前端应在 `load_anchor` 前先 `GET /api/anchors` 确认 id 存在；`load_anchor` **自身不返回 error 帧作为常规回答**——即「预期失败」由 HTTP 预检拦截，「意外失败」（重放损坏）才走 WS error。契约明记此**双保险**，避免前端把 `load_failed` 当常规流程处理。

## 4. 附带发现一：`move_request` 的静默 `return None` 同属缺陷

`move_request` 校验失败（主角不存在 `/` 非 int 目标 / 不可达）三处**静默 `return None`**（`ws.py:221,230,234`）。`ws.py:234` 注释写「客户端已预检」——但 `ws-protocol.md:214` 定「不静默丢弃」。**建议**（低优先，可与 M5 同批或单排）：

- 不可达/不可通行 → 回 `error{ref:"move_request", code:"unreachable", message:"<戏内>"}`（客户端应知点击未生效）。
- 非 int 目标（含 bool）→ `error{code:"bad_target"}`。
- **权衡**：`move_request` 高频（每次点击），error 帧会增加噪声。**kilo 建议保留「不可达」静默（客户端预测已覆盖）**，仅将「非法类型」升级为 error——但此为**可选**，不影响 M5 三主项，单列供裁。

## 5. 附带发现二：`sync_request` 回错型（K4 新发现，P1）

`ws.py:257-266`：`sync_request` 回的是 `control_ack{action:"resume",speed:1}`——**类型错误**。契约（`ws-protocol.md:48`「请求全量 `full_snapshot`」+ §4.4:202「`full_snapshot` 响应」）要求回 **`full_snapshot`**。

**证据**：`SyncRequestMessage.reason` 是普通 string（无 enum）；`control_ack` 是「`set_control` 确认」（`ws-protocol.md:61`），语义完全不搭。

**建议修法**（一行级）：`sync_request` 分支改调 `snapshot_payload(loop, tile_map)` 返回——**与 §3.4 的 `load_anchor` 短期方案共用同一路径**，顺带解决 `tile_map` 传递问题。`reason` 字段可选择性透传为 `full_snapshot` 的调试注释（不必须）。

> **为何单列**：`anchors-api.md:269` 把 `sync_request` 记为「完整（回 `control_ack`）」，**该记载有误**——K1 复核时漏判。本提案订正之，并在 `anchors-api.md` §4.1 同步修正。

> **✅ M5-K5 已首修**（2026-09-25）：`sync_request` 分支改调 `snapshot_payload(loop, pf.tile_map)`。
> **`tile_map` 经 `pf.tile_map` 取，签名未变**——`Pathfinder` 已暴露该 property（`pathfinding.py:96-98`），即 §8.5 备选案成立，`handle_client_message` 保持 `(raw, loop, pf)` 三参、纯函数可单测。
> **`reason` 未透传**：`FullSnapshotMessage.additionalProperties:false`（封闭 schema），透传会破坏契约并使前端类型断言变红；`full_snapshot` 本就不带 reason（连接即发亦然）。
> 实现见 `ws.py:258`；回归钉 `sim/tests/test_ws_gateway.py::TestSyncRequest`（5 例，含「不得退回 control_ack」「与 connect 快照同形」）。

## 5.1 error `code` 命名口径统一（P2）

现状：`ws.py` 用 `unknown_type`/`bad_channel`/`auth_error`（**小写 snake**），但 `ws-protocol.md:211` 样例用 `IMPULSE_TOO_LONG`（**大写下划线**）——**两套口径并存**。

**建议**：统一为**小写 snake_case**（实现已是主流：3 个小写 vs 1 个文档样例），并把 `ws-protocol.md` §4.5 样例的 `IMPULSE_TOO_LONG` 改为 `impulse_too_long`。本提案所有新 code（`bad_action`/`bad_speed`/`bad_impulse`/`impulse_too_long`/`bad_anchor`/`load_failed`）一律小写 snake。

> **✅ M5-K6 已落地**（2026-09-25）：10 项 code 全部形为 `sim/api/ws.py` 的 `_ERROR_*` 模块常量（单一真相源，防字面量散落）；`ws-protocol.md` §4.5 样例已订正小写（§7 #19 已过）。`TestErrorCodeVocabulary` 三例钉子：常量子集 ⊆ 词表 / 全小写 / 运行时逐路径断言 code ∈ 词表。

**code 词表（本提案新增后全量）**：

| code | 触发 | 出处 |
|---|---|---|
| `unknown_type` | 类型不在白名单 | 现有 `ws.py:204` |
| `bad_channel` | channel 与类型不符 | 现有 `ws.py:214` |
| `auth_error` | hello token 错/缺 | 现有 `ws.py:253` |
| `bad_action` | set_control action 非法 | §1.4 新增 |
| `bad_speed` | set_control set_speed 的 speed 非法 | §1.4 新增 |
| `bad_impulse` | player_impulse text 缺失/空/非串 | §2.3 新增 |
| `impulse_too_long` | player_impulse text > 64 | §2.3 新增（对齐 §4.5 样例） |
| `bad_anchor` | load_anchor anchor_id 缺失/非串 | §3.3 新增 |
| `load_failed` | load_anchor 载入执行失败 | §3.3 新增（`anchors-api.md:258` 已定） |
| `unreachable` / `bad_target` | move_request（可选，§4） | §4 待裁 |

## 6. 实现清单（Claude 域，提案态）

> **✅ M5-K6 已施工**（2026-09-25，commit 见 git log）：以下 1-8 全部落地，测试钉子在 `sim/tests/test_ws_gateway.py`（§7 对表现已逐项标注通过状态）。
> **第 4 项签名变更未执行**——K5 走 §8.5 备选案（`pf.tile_map`），`handle_client_message` 保持 `(raw, loop, pf)` 三参、`main.py` 调用点零改动。
> **第 9 项测试文件未新建**——按任务单「钉在 `test_ws_gateway.py`」并入现有文件（避免同域测试分裂）。

> 纯契约提案，以下为实现落点，**照本文施工**。所有动作面均**不新增消息类型**（5 类已在 `ws-protocol.md` §3.1 定义）、**不改 `shared/openapi.json`**（schema 全部已就绪）、**不改 `main.py` 收发结构**（除下述签名）。

1. `ws.py:32` `_ALLOWED_CLIENT_TYPES` += `player_impulse`, `load_anchor`。 → **✅ 已加**（六类齐全）
2. `ws.py:270` `_CHANNEL_FOR` += `player_impulse: "control"`, `load_anchor: "session"`。 → **✅ 已加**（配对，§7 #18 有钉）
3. `ws.py:188` `handle_client_message`：新增 3 个分发块（`set_control`/`player_impulse`/`load_anchor`），**各自有独立 `_handle_*` 纯函数**，可单测。 → **✅ 已加**（`_handle_set_control` / `_handle_player_impulse` / `_handle_load_anchor`；另把既有的 move/sync 块也抽成 `_handle_move_request` / `_handle_sync_request`，同构）
4. **签名变更（唯一）**：`handle_client_message(raw, loop, pf)` → 增 `tile_map` 参数（供 `snapshot_payload`），或经 `pf` 取。`main.py:186` 调用点同步。**§3.4 / §5 共用此路径**。 → **改为备选案**：经 `pf.tile_map` 取（K5 定案），签名不变
5. `ws.py:257` `sync_request` 分支改回 `full_snapshot`（§5）。 → **✅ M5-K5 已修**
6. `ws.py` 顶部注释「只分发 3 类」等表述同步更新（现状描述会过期）。 → **✅ 已更新**
7. `anchors-api.md:265-272` §4.1 表：订正 `sync_request` 行（回 `full_snapshot` 非 `control_ack`）+ 状态列（改为「M5 施工后完整」）。 → **✅ K5/K6 两次刷新，六类行全部为施工后状态**
8. `ws-protocol.md`：§4.3 加「见 `ws-dispatch-proposal.md` §1」引用；§4.4 加「§3」引用并订正 `anc_01` 示例；§4.5 订正 `IMPULSE_TOO_LONG` → `impulse_too_long` + 加 §1.4/§2.3/§3.3 的 code 词表引用。 → **✅ K6 已做**（见 §7 #19/#20 状态）
9. 测试：`sim/tests/test_ws_dispatch.py`（§7 清单）。 → **改为并入 `sim/tests/test_ws_gateway.py`**（任务单指定）

## 7. 验收对表（可测断言，供 Claude 自测 / kilo 复验）

> 断言类型同 `anchors-api.md:282` 三类：`[T]` pytest（`sim/tests/test_ws_dispatch.py`）、`[O]` OpenAPI/静态形状、`[P]` 协议一致性（文档 ↔ 实现）。fixture 沿用 `sim/tests/test_ws_auth.py:31` 的 `websocket_connect` 写法。

| # | 断言 | 类型 |
|---|---|---|
| 1 | `set_control{action:"set_speed",speed:4}` → 回 `control_ack{action:"set_speed",speed:4,applied:true}`，且 `loop.clock.speed == 4.0` | `[T]` **✅ 已过**（`test_set_speed_applies`） |
| 2 | `set_control{action:"pause"}` → 回 `control_ack{action:"pause",applied:true}`，`clock.speed == 0.0`；紧接 `set_control{action:"resume"}` → `clock.speed` 恢复为暂停前值 | `[T]` **✅ 已过**（`test_pause_then_resume_restores_previous_speed` + `test_pause_from_default_speed_resumes_to_one`） |
| 3 | **bool 陷阱**：`set_control{action:"set_speed",speed:true}` → `error{code:"bad_speed"}`，`clock.speed` 不变 | `[T]` **✅ 已过**（`test_speed_bool_rejected`） |
| 4 | `set_control{action:"set_speed",speed:8}`（不在 `{1,4,16}`）→ `error{code:"bad_speed"}`，clock 不变 | `[T]` **✅ 已过**（`test_speed_out_of_enum_rejected`，另覆盖 0/2/32/缺失/字符串/null/float） |
| 5 | `set_control{action:"nope"}` → `error{code:"bad_action"}` | `[T]` **✅ 已过**（`test_unknown_action_rejected` + `test_missing_action_rejected`） |
| 6 | **不再静默**：任意非法 `set_control` 的 reply **非 None**（回归钉子，防退回静默） | `[T]` **✅ 已过**（`test_no_silent_drop_on_illegal`，5 用例） |
| 7 | `player_impulse{text:"去赚钱"}` → 回 `impulse_feedback{injected:true,cue:∈四值,reaction_monologue:{form,content}}`，且**一帧内**返回（不 await LLM） | `[T]` **✅ 已过**（`test_registered_returns_feedback`） |
| 8 | `player_impulse{text:<65 字>}` → `error{code:"impulse_too_long",message:"话说得太长了，说不清。"}` | `[T]` **✅ 已过**（`test_too_long_rejected` + `test_max_length_text_accepted` 边界 64 整） |
| 9 | `player_impulse{text:"  "}`（全空白）→ `error{code:"bad_impulse"}` | `[T]` **✅ 已过**（`test_blank_text_rejected`，另覆盖空串/Tab换行 + `test_missing_or_non_string_text_rejected`） |
| 10 | `player_impulse` 的 `unknown_type` 回归：注册后**不再**回 `unknown_type` | `[T]` **✅ 已过**（`test_no_longer_unknown_type`） |
| 11 | `load_anchor{anchor_id:"9f3c1a7b2e04"}`（不存在）→ `error{ref:"load_anchor",code:"load_failed",message:"<戏内>"}`，**连接保持**（后续可继续发消息收到回复） | `[T]` **✅ 已过**（`test_registered_unknown_anchor_returns_load_failed` + `test_connection_stays_alive_after_failure`） |
| 12 | `load_anchor{anchor_id:<合法>}` → 回 `full_snapshot`（含 `map/actors/lights/structures/weather/combat` 六键） | `[T]` **✅ 已过**（`test_success_returns_full_snapshot`——经 `_ANCHOR_LOAD_HOOK` 注入合法态；键集合与连接即发快照相等） |
| 13 | `load_anchor` **不因 `anc_` 前缀拒绝**（不透明串纪律）：`{anchor_id:"anc_01"}` 走正常查表路径（找不到 → `load_failed`，非 `bad_anchor`） | `[T]` **✅ 已过**（`test_underscore_prefix_not_rejected` + `test_anc_prefix_id_is_opaque_not_validated`） |
| 14 | `sync_request{reason:"reconnect"}` → 回 `full_snapshot`（**非 `control_ack`**，§5 钉子） | `[T]` **✅ M5-K5 已过**（`test_sync_request_returns_full_snapshot`） |
| 15 | 所有 error 帧的 `code` ∈ §5.1 词表，且均为小写 snake（无大写） | `[T]` **✅ 已过**（`TestErrorCodeVocabulary` 3 例：常量子集 + 全小写 + 运行时 10 路径逐个触发断言在词表内） |
| 16 | 出戏边界：三新路径的任何出站帧**不含** `tick`/`seed`/`seq`/`branch_id`/内部 entity_id（`ws-protocol.md` §5 表逐字段） | `[T]` **✅ 已过**（`test_sync_request_snapshot_clean` + `TestOutOfCharacterBoundary` 全量；三新路径的 error 帧键集合 `_error_frame` 封闭，`control_ack`/`impulse_feedback` 键亦经白名单同构断言） |
| 17 | `timescale` 帧由战斗事件驱动（`issue_combat_scale`→广播），**不由** `set_control` 触发 | `[T]` **✅ 已过**（`test_extra_speed_on_pause_tolerated` + `test_clock_untouched_when_rejected` 反向证明 `set_control` 只动 clock.speed、不发 timescale 帧；`ws_endpoint` 层无 timescale 广播路径） |
| 18 | 5 类 client→sim 消息全部在 `_ALLOWED_CLIENT_TYPES` 与 `_CHANNEL_FOR` **成对**注册（防 §2.2 落单 → `bad_channel`） | `[O]` **✅ 已过**（`TestDispatchRegistration` 2 例：白名单 == 六类集合 + 两表 keys 严格相等） |
| 19 | `ws-protocol.md` §4.5 样例 code = 小写 `impulse_too_long`（与实现一致） | `[P]` **✅ 已过**（文档样例已订正为小写；见 §7 表下注记） |
| 20 | `ws-protocol.md` §4.4 `load_anchor` 示例 anchor_id 为 12 位 hex（非 `anc_01`） | `[P]` **✅ 已过**（文档示例已订正为 `9f3c1a7b2e04`） |

## 8. 待裁清单（汇总，供 Claude 裁决）

| # | 议题 | kilo 建议 | 影响面 |
|---|---|---|---|
| 8.1 | `control_ack.applied` 语义 | **恒 `true` 占位**（§1.3），钳制场景未来再定。→ **M5-K6 已按此落地**（`applied: True` 硬编码） | 中（前端分支逻辑） |
| 8.2 | `set_control pause/resume` 携带 `speed` | **容忍忽略**（不报错），与 move_request 宽容风格一致。→ **M5-K6 已落地**（`resume` 用 `_PRE_PAUSE_SPEED` 栈值，不信入站 speed） | 低 |
| 8.3 | `player_impulse` 冲突度规则表 + 叙事化模板归属域 | 协议面本文定；规则表归 LLM 域（`sim/llm/` 或 `sim/perception/`）。→ **M5-K6 只落协议面**：`_impulse_cue()` 是占位（问号→hesitation / 感叹→complaint / 其余→accepted），M4 LLM 域定稿前不视作契约 | 高（M4 施工前置） |
| 8.4 | `load_anchor` 成功发 `full_snapshot` 的时机（短期同步 vs 长期 driver） | M5 先落**短期同步**（重放未实现），留 TODO 指向 §3.4。→ **M5-K6 已落地**（复用 `snapshot_payload`，TODO 在 `_handle_load_anchor` docstring） | 高（决定是否改签名） |
| 8.5 | `handle_client_message` 增 `tile_map` 参数 | **建议改**（§3.4/§5 共用）；备选：从 `pf` 取。→ **K5 定备选案**（`pf.tile_map`，签名不变），K6 沿用 | 中（改签名 + 调用点） |
| 8.6 | `move_request` 静默缺陷是否本批修 | **本批只修非法类型（`bad_target`），不可达保留静默**（§4）。→ **M5-K6 已落地** | 低 |
| 8.7 | `sync_request` 回错型 | **本批必修**（P1，§5）——一行级。→ **M5-K5 已修** ✅ | 中（契约正确性） |
| 8.8 | error `code` 大小写口径 | **统一小写 snake**（§5.1）。→ **M5-K6 已落地**（10 项 `_ERROR_*` 常量，§7 #15 三例钉子） | 低（文档订正 + 未来钉子） |
| 8.9 | `_pre_pause_speed` 与 anchor 登记的存放形态（**M5-K6 新增待裁**） | 现为模块级（`_PRE_PAUSE_SPEED` 栈 / `_ANCHOR_IDS` 集 / `_ANCHOR_LOAD_HOOK` 钩子），与既有 `ws_auth_token()` 模块级模式同构。**M2 多连接前**须改为 `ConnectionManager` 每连接字段 + 由落库路径调 `register_anchor_id()`；并须定「同步查表替身」是否长期保留 (§3.4 driver 化后 `_ANCHOR_LOAD_HOOK` 是唯一真实入口) | 中（多连接改造前置） |

## 9. 不在本文件范围

- `player_impulse` 的 LLM 叙事化/冲突度算法（LLM 域）。
- `load_anchor` 的重放实现（§12 存档域）。
- `move_request` 寻路算法、`hello` 鉴权（已有契约）。
- HTTP anchors 三路由（见 `anchors-api.md`）。
