# WebSocket 消息协议设计（docs/api/ws-protocol.md）

> 能力域：接口 / 兼容性（kilo） | 对齐 DESIGN.md §3 §4 §6 §9 §10 §11 §12 §19
> 本文为**设计文档**，不含实现码。字段 schema 与 §6 数据契约对齐；出戏边界与 §2 C3 / §10 界面双层铁律一致。

## 1. 链路拓扑

```
client/src/net (WS 客户端)
   │  单条长连接 /ws
   ▼
sim/api/ws  (FastAPI WebSocket 网关)
   │
   ▼
世界模拟内核（确定性 tick · 事件溯源）
```

- 前端分两个渲染边界（§4 硬约束）：**Phaser** 只画 canvas 内世界（消费 render 通道），**React** 只画 canvas 外 UI（消费 narrative 通道）。两者不共享 DOM。
- WS 一条连接复用两类通道，靠消息 `channel` 字段区分，避免 Phaser/React 各开一条。
- 连接生命周期 = 一个游戏会话。断线重连走 `full_snapshot` 全量重建（见 §3.2）。

## 2. 信封格式

所有帧为 JSON 文本帧，统一信封：

```jsonc
{
  "v": 1,                  // 协议版本（见 versioning.md）；协商后全程不变
  "ws_seq": 412,           // 传输序号：本端发出帧的递增计数，仅用于丢帧/乱序检测
  "channel": "render",     // render | narrative | control | session | error
  "type": "state_delta",   // 见 §3 消息清单
  "data": { /* type 载荷 */ }
}
```

**关键：`ws_seq` 不是世界 tick。** 它是传输层单调计数，仅由 WS 端点维护，用于客户端检测丢帧（缺失即请求 `full_snapshot`）。世界 tick、seed、事件 seq 一律不进入此信封（见 §5 出戏边界）。

## 3. 消息类型清单

### 3.1 client → sim

| type | channel | 用途 | 落地 |
|---|---|---|---|
| `player_impulse` | control | 念头注入（玩家唯一主动动作，M4） | M4 |
| `set_control` | control | 暂停 / 倍速（1x/4x/16x） | M0 |
| `move_request` | render | 玩家点击寻路：只发目标格 `{target_x,target_y}`（整数格坐标），sim 寻路驱动主角；无 rtoken（服务端知道主角是谁） | M0 |
| `load_anchor` | session | 载入玩家档（触发世界分叉+重放，见 §12） | M5 |
| `sync_request` | session | 请求全量 `full_snapshot`（重连/丢帧补救） | M0 |

### 3.2 sim → client

| type | channel | 用途 | 落地 |
|---|---|---|---|
| `full_snapshot` | render | 连接/重连/载档后的全量渲染态 | M0 |
| `state_delta` | render | 每 tick 增量渲染态（M0 渲染闭环主载波） | M0 |
| `perception` | narrative | 第一人称感官流叙事（React 侧独白/思维面板来源） | M1 |
| `monologue` | narrative | 独白三形态呈现（气泡 / 思维面板 / 计划看板） | M1 |
| `impulse_feedback` | control | 念头注入即时反馈（意愿冲突表现，M4） | M4 |
| `combat_event` | render | 战斗交换单元结算表现（弹幕/翻滚/受击） | M4 |
| `timescale` | control | 战斗时间尺自动切换通知（§9，sim 驱动） | M4 |
| `control_ack` | control | set_control 确认（含战斗期被钳制提示） | M0 |
| `error` | error | 结构化错误（非法输入/锚点缺失等，不静默丢弃） | M0 |

## 4. 字段 schema

> 字段命名与 §6 数据契约同源；凡是 §6 中标注「禁止进入 prompt / 仅内部关联」的字段，一律不出现在下方任何载荷（见 §5）。
> 标记 `[render-only]` 的字段只供 Phaser 渲染、绝不进 React 文本；标记 `[narrative]` 的只供 React、绝不含数值。

### 4.1 render 通道（喂 Phaser）

#### full_snapshot.data

```jsonc
{
  "map": { "tileset": "linhe_v1", "w": 128, "h": 96 },   // 不含 seed/生成参数
  "lights": [ { "rtoken": "rt_7", "x": 30, "y": 22, "kind": "lamp", "radius": 6, "flicker": 0.2 } ],
  "actors": [
    { "rtoken": "rt_3", "sprite": "npc_villager_m", "x": 40, "y": 50, "facing": "s", "anim": "idle", "tint": 0 },
    { "rtoken": "rt_1", "sprite": "chenmo", "x": 42, "y": 50, "facing": "s", "anim": "walk" }
  ],
  "structures": [ { "rtoken": "rt_s2", "tileset_ref": "hut_wood", "x": 10, "y": 10, "phase": "built" } ],
  "weather": { "visual": "light_rain", "ambient_light": 0.7 },   // 叙事化视觉，无概率值
  "combat": null        // 或 { "active": true } —— 不暴露姿态数值，只标记是否在战斗慢镜
}
```

#### state_delta.data

```jsonc
{
  "actors": [
    { "rtoken": "rt_1", "x": 43, "y": 50, "anim": "walk" },   // 仅变动字段
    { "op": "add", "rtoken": "rt_9", "sprite": "npc_guard", "x": 60, "y": 70, "anim": "idle" },
    { "op": "remove", "rtoken": "rt_5" }
  ],
  "lights": [ { "rtoken": "rt_7", "flicker": 0.35 } ],
  "weather": { "visual": "heavy_rain", "ambient_light": 0.5 },
  "structures": [ { "rtoken": "rt_s2", "phase": "collapsing" } ]
}
```

- 增量以 `rtoken` 为键；`op` 缺省视为 update。
- 客户端按 `ws_seq` 顺序应用；发现缺口超过阈值即发 `sync_request`。

#### combat_event.data（§9 决策点制表现）

```jsonc
{
  "exchange": 3,                  // 交换单元序号（本战斗内序，非世界 tick）
  "rtoken": "rt_1",
  "posture_visual": "attack_high",// 表现层姿态，非内部结算姿态枚举
  "projectiles": [ { "rtoken": "rt_p1", "kind": "arrow", "x0": 40, "y0": 50, "x1": 60, "y1": 50, "dur": 0.3 } ],
  "hits": [ { "rtoken": "rt_3", "visual": "stagger", "bleed": "light" } ],
  "exchange_resolved": true
}
```

- 结算公式（技能 × 姿态 × 距离 / 熵注入）永不出现；客户端只拿表现数据画弹幕与翻滚。
- `exchange` 是战斗内局部序号，不是世界 seq，不影响回放因果。

### 4.2 narrative 通道（喂 React，戏内）

#### perception.data `[narrative]`

```jsonc
{
  "sense": "sight",               // sight|sound|smell|touch|interoception（§7 通道）
  "content": "巷口那盏灯忽明忽暗，像要灭了。",   // 第一人称叙事，无数值无系统词
  "form": null                    // null=感官流；monologue 时填 bubble|thought|plan
}
```

- 内容由 sim 感知层 + 独白叙事化管线产出（§8）；客户端只排版，不改写。
- `content` 绝不含 hp/数值/动机/entity_id（C2/C3）。

#### monologue.data `[narrative]`

```jsonc
{
  "form": "thought",              // bubble（头顶气泡）| thought（思维面板）| plan（计划看板）
  "content": "我干嘛要干这个……算了，先走着。"   // 第一人称叙事化，无数值无系统词
}
```

- §8 铁律：独白永不直接渲染 LLM 原始输出；原始思维链只进开发日志。
- **M1 定稿（W7 字段最小化）**：独白只含 `form` + `content`；戏外调试字段（如 anchor_ref）不入 M1 契约。

### 4.3 control 通道

#### player_impulse.data（C→S，M4）

```jsonc
{
  "text": "去赚钱",               // 玩家原始直觉输入，≤ 64 字
  "preset": null                  // 可选预设标签，便于未来 UI 快捷按钮；不影响叙事化
}
```

- sim 负责：叙事化注入（"你摸了摸空瘪的钱袋……"）→ 意愿冲突度计算 → 注入 Agent prompt。
- 客户端不参与叙事化，不计算冲突度（数值是元信息）。
- **分发契约见 `ws-dispatch-proposal.md` §2**（M5-K4）：注册（白名单+channel）、入站校验（`text` 长度/空串）、乐观 `impulse_feedback` 与 LLM 异步投递缝、error code（`bad_impulse`/`impulse_too_long`）。现状 `player_impulse` **未注册**（回 `unknown_type`）。

#### impulse_feedback.data（S→C，M4）

```jsonc
{
  "injected": true,
  "cue": "complaint",             // accepted|hesitation|complaint|resistance（映射 §10 冲突度区间）
  "reaction_monologue": { "form": "thought", "content": "……行吧。" }
}
```

- `cue` 是表现提示，**不是冲突度数值**；客户端据此选 UI 节奏，绝不显示"抵触度 0.7"。
- **M1 定稿（W7 字段最小化）**：删除 `delay_ms`——节奏由客户端按 `cue` 自行安排，契约不携带数值。
- §10：抱怨必须是自我怀疑（"我干嘛要干这个"），绝不能是被操纵感（"谁在指使我"）——后者即出戏，由 sim 文风化保证，协议层不承载操纵感语义。

#### set_control.data（C→S）

```jsonc
{ "action": "set_speed", "speed": 16 }   // action: pause|resume|set_speed
```

- 战斗时间尺（§9）由 sim 自动切换，**不允许客户端直接设战斗慢镜**。`timescale`（S→C）告知进入/脱离。
- **分发块契约见 `ws-dispatch-proposal.md` §1**（M5-K4）：`action`/`speed` 校验规则、`applied` 语义、`timescale` 联动、拒绝面 error 帧（`bad_action`/`bad_speed`）。现状 `handle_client_message` **无 `set_control` 分发块**（静默 `return None`）——分发块落地是本节契约成立的前提。

#### control_ack.data / timescale.data（S→C）

```jsonc
{ "action": "set_speed", "speed": 4, "applied": true }            // control_ack
{ "mode": "combat", "active": true, "note": null }               // timescale（note 戏外调试用）
```

- **`control_ack.speed` = 用户设定的倍率**，不是当前有效 tick 率；战斗期有效率 = `1 × speed`（`clock.py` 的 `ticks_per_real_second = base × speed`）。前端不得拿此值直算帧率。
- `timescale` **只由战斗事件驱动**（`issue_combat_scale`→广播），与 `set_control` 无因果链。详见 `ws-dispatch-proposal.md` §1.5。

### 4.4 session 通道

#### load_anchor.data（C→S）

```jsonc
{ "anchor_id": "9f3c1a7b2e04" }   // 来自 HTTP anchor 列表（见 openapi.md / anchors-api.md）
```

- 触发 §12 读档流程：定位 (branch_id,seq) → 快照 → 重放 → 新分支 → 流 `full_snapshot`。
- 重放毫秒级，期间客户端显示"片刻后……"叙事化过渡，绝不显示"重放中/tick"。
- `anchor_id` 是**不透明字符串**（12 位 hex，`uuid4().hex[:12]`）——**不得**用 `startsWith('anc_')` 之类前缀特征做校验（`anchors-api.md` §6.5：`anc_` 前缀惯例不存在）。
- **分发契约见 `ws-dispatch-proposal.md` §3**（M5-K4）：注册、入站校验、失败走 WS error 帧（`code:"load_failed"`）**且不断线**、成功发 `full_snapshot`。现状 `load_anchor` **未注册**（回 `unknown_type`）。

#### sync_request.data（C→S） / full_snapshot 响应见 §4.1

```jsonc
{ "reason": "gap_detected" }     // gap_detected|reconnect|after_load
```

### 4.5 error 通道

```jsonc
{ "ref": "player_impulse", "code": "impulse_too_long", "message": "话说得太长了，说不清。" }
```

- message 保持戏内文风（§19 不静默丢弃、不用系统措辞）；code 供客户端逻辑分支，不向玩家显示。
- **`code` 一律小写 snake_case**（M5-K4 §5.1 统一口径；实现已是此风格，本节样例原写 `IMPULSE_TOO_LONG` 已订正）。全量 code 词表见 `ws-dispatch-proposal.md` §5.1。
- 三原则：**不静默丢弃**（非法输入必回 error 帧，不 `return None`）；**不泄露内部真相**（§5 禁出字段不出现在 `message`）；**不断线**（`load_anchor` 失败等只回 error，连接保持）。

## 5. 出戏边界（逐条可查）

> 与 §2 C3、§10 界面双层铁律、§11、§19 一致。**以下字段在任何 WS 载荷中永不出现：**

| 禁出字段 | 来源 | 禁出理由 |
|---|---|---|
| 世界 tick 序号 | §11 | 系统词汇；泄露世界机器节拍 |
| RNG seed | §11 | 世界真相；破坏不可预测性 |
| 事件 seq（WorldEvent.seq） | §6/§11 | 内部因果链，世界真相 |
| branch_id（戏内/渲染通道） | §12 | 存档分叉真相；仅 HTTP 戏外 meta 可见 |
| 内部 entity_id | §6 | 内部主键；render 用 `rtoken` 不透明替身代替 |
| PerceptionFrame.source_id | §6 | "仅内部关联，禁止进入 prompt"，同理不进协议 |
| raw 数值属性（hp/needs/OCEAN/PAD/trust/affection/fear/debt/face/skills/confidence/salience/uncertainty/importance/distortion） | §6/§19 | 玩家观察视图须叙事化，禁止一切系统词汇与数值 |
| embedding 向量 | §6 MemoryEntry | 世界内部检索结构 |
| witnesses 见证者列表 | §6 WorldEvent | "只有见证者获记忆"，列表本身是世界真相 |
| 运气值/概率/偏差参数 | §11/§19 | Agent 不可见的内部状态 |
| agent_override 内部结构 | §6 PlayerAnchor | 玩家档是游标；override 内部结构不戏内暴露 |
| LLM 原始思维链 | §8 | 只进开发日志，永不戏内渲染 |
| api_key | §4/§19 | 只在后端流转，前端永不接触（见 openapi.md） |

**render 通道允许暴露的**：玩家自然能"看见为像素"的视觉空间事实——位置/朝向/精灵/动画/光照/天气视觉/弹幕表现/坍塌 phase。这些是像素原料，不作为数值文本呈现，且永不回流 Agent prompt。

**rtoken 规则**：`rtoken` 由 sim 端 render 投影层分配，是**仅用于精灵跟踪的不透明短命令牌**，与内部 entity_id 解耦、不可反查游戏状态、连接生命周期内有效；重连后由 `full_snapshot` 重新分配。

## 6. 节奏与一致性

- M0 渲染闭环：连接建立 → `full_snapshot` → 周期 `state_delta`（60 tick/s × 1x 基准）。客户端插值渲染；`ws_seq` 缺口 → `sync_request`。
- 念头反馈即时性（§10/§20）：`player_impulse` 入网即回 `impulse_feedback`，最迟下一 `state_delta` 前可见。
- LLM 异步：§3 规划时预检 + 执行 tick 二次校验；过期 Intent 在 sim 内丢弃重规划，协议层无感知，只表现为后续 `monologue`/`perception` 演进——天然无延迟矛盾。
- 战斗慢镜（§9）：进入战斗 → `timescale{mode:combat,active:true}` → 客户端降速渲染，LLM 8s 尾延迟被一个交换单元（10 真实秒）吸收；脱离 → `timescale{active:false}`。

## 7. 不在本协议范围

- HTTP 端点（settings/profile/anchor CRUD）见 `openapi.md`。
- 类型生成管线见 `codegen.md`；版本协商见 `versioning.md`。
- 感知叙事化管线、独白文风化属 sim 内部（§8），不在接口层定义。
