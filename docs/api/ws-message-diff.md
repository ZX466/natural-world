# ext ↔ 快照逐成员 diff 明细（M2-K3 交付 / ext 返工验收清单）

> 能力域：接口 / 兼容性（kilo） | 2026-09-22 | 任务单：M2-K3（见本树 `.orca/talking.txt`）
> **本文 = Claude 域 `openapi_ext` 返工的验收清单**；返工完成后由 kilo 做 K3 复验（`--check` + 形状抽查，口径见 §4）。
> 真相源：`shared/openapi.json`（裁决：切源暂缓，见 `docs/api/codegen.md` §4.1，cline M2-C4 已落档）。
> ext 基线：`sim/api/openapi_ext.py` @ `59ffd86`——`git log --oneline --follow` 确认 59ffd86 之后该文件**零改动**。
> 比对方式：`TestClient(app).get("/openapi.json")` 实跑生成本机生成物，与快照做**结构 diff**（非目测）；`LZ_MASTER_KEY` 用本地临时值不入库。与 M2-K2 同口径。

---

## 0. 结论摘要（返工范围）

结构骨架**正确，内容未对齐**。M2-K2 已确认的 6 项（14 成员 + oneOf/discriminator 进 `components.schemas`、`wsMessages` 废除、channel 下沉、error 无 ref、hello/hello_ack 不进联合）**返工时不要动**。需要返工的共 5 类：

| 类 | 项数 | 章节 | 严重度 |
|---|---|---|---|
| ① 缺失 schema | 17 个（另 5 个判「不施工」，见 §2） | §2 | P0 |
| ② WS 成员字段/required/enum 差异 | **61 处字段级差异**（ADD 22 + DEL 10 + MOD 29）+ 8 处 required 清单不一致，涉及 **10 个成员** | §1 | P1 |
| ③ `nullable: true` → `oneOf:[…, null]` | 5 处（其中 2 处随字段删除、1 处快照侧也要改） | §3 | P1 |
| ④ 信封 `v` description 系统性偏差 | 1 行改动消 14 处 | §1.6 | cosmetic（不影响类型） |
| ⑤ HTTP 路由/路径差异 | 1 处需裁定、1 处随 ② 处理 | §2.3 | P2 |

> **计数口径**（便于逐条对账，下同）：
> - 字段级差异合计 **61 处 = ADD 22 + DEL 10 + MOD 29**。
> - MOD 里 **11 处结构性**（动了 `$ref`/`oneOf`/enum/channel，真实影响类型）+ **18 处仅 description 偏差**（§1.6，白名单可放）。
> - 另有 **8 个成员的 required 清单不一致**。
>
> 字段级差异分布在 **10 个成员**：
> `FullSnapshotMessage`、`StateDeltaMessage`、`PerceptionMessage`、`MonologueMessage`、`ImpulseFeedbackMessage`、`CombatEventMessage`、`TimescaleMessage`、`ControlAckMessage`、`SyncRequestMessage`、`MoveRequestMessage`。
> 另 4 个成员（`PlayerImpulseMessage`/`SetControlMessage`/`LoadAnchorMessage`/`WsErrorMessage`）的差异只在 §1.6 的 description，加上 §3 的 `preset`、§1.5 的 `ref` 两处具体字段。

其中 §3 推翻任务单里的一个前提假设，**请先读 §3.1**（`subject` 在快照中不存在）。

---

## 1. WS 成员逐字段 diff

> 口径：「信封字段」`v`/`ws_seq`/`channel`/`type` 的 type/enum 两边一致（ext `_envelope` 统一且对齐），只有 §1.6 的 `v` description 偏差。
> 「REAL」= 影响 `openapi-typescript` 产出的类型；「cosmetic」= 仅 description，不影响类型（§4.2 白名单）。
> **ADD = 快照有 ext 无；DEL = ext 有快照无。**

### 1.1 `FullSnapshotMessage`（6 处 REAL + required）

| 字段 | 快照 | ext @59ffd86 | 动作 |
|---|---|---|---|
| `actors.items` | `$ref Actor` | 内联 object 6 字段，形状等价 | 抽 `Actor` 改 `$ref` |
| `lights.items` | `$ref Light`（rtoken/x/y/kind/radius/flicker，全 required） | 内联 `{"type":"object"}`（**完全敞开，零校验**） | 抽 `Light` 改 `$ref` |
| `structures.items` | `$ref Structure`（rtoken/tileset_ref/x/y/phase:enum[built,collapsing,rubble]） | 内联 `{"type":"object"}` | 抽 `Structure` 改 `$ref` |
| `map` | `$ref MapInfo`（tileset/w/h） | 内联 object 3 字段 | 抽 `MapInfo` 改 `$ref` |
| `weather` | `$ref Weather`（visual/ambient_light） | 内联 object 2 字段，形状等价 | 抽 `Weather` 改 `$ref`（`StateDeltaMessage` 共用） |
| `combat` | `oneOf:[$ref CombatInfo, {"type":"null"}]`，**optional** | `{"type":["object","null"]}` 且 **required** | 改 oneOf + `$ref` + **从 required 移除** |
| required | `[v,ws_seq,channel,type,map,lights,actors,structures,weather]` | 同上但多含 `combat` | 按快照 |

### 1.2 `StateDeltaMessage`（4 处 REAL）

| 字段 | 快照 | ext | 动作 |
|---|---|---|---|
| `actors.items` | `$ref ActorDelta`（required 仅 `rtoken`；`op`:enum[add,remove] + sprite/x/y/facing/anim/tint 全 optional） | 内联 object 6 字段、**无 `op`** | 抽 `ActorDelta` 改 `$ref`（`op` 是 WS 协议 §4.1「增量以 rtoken 为键，op 缺省视为 update」的载体，**不能省**） |
| `lights` | `$ref LightDelta`，**optional** | 缺失 | 补 optional |
| `structures` | `$ref StructureDelta`，**optional** | 缺失 | 补 optional |
| `weather` | `$ref Weather`，**optional** | 缺失 | 补 optional |

### 1.3 `PerceptionMessage`（2 处 REAL，**推翻任务单前提，见 §3.1**）

| 字段 | 快照 | ext | 动作 |
|---|---|---|---|
| `form` | **optional**，`oneOf:[{string,enum[bubble,thought,plan]},{null}]` | 缺失 | 补，用 oneOf-null 形（§3.2），**不要用 nullable** |
| `subject` | **快照无此字段** | `{"type":"string","nullable":true}` | **DEL** |

### 1.4 `MonologueMessage`（2 处 REAL + 2 处 cosmetic）

| 字段 | 快照 | ext | 动作 |
|---|---|---|---|
| `form` | **required**，`enum[bubble,thought,plan]` | 缺失 | 补 + 进 required |
| `reaction` | **快照无此字段**（W7 字段最小化） | nullable object | **DEL** |
| `content` 的 description | `"第一人称叙事化独白，无数值无系统词"` | 无 | cosmetic，补 |
| 成员 description | `"M1 独白三形态呈现（§8）；content 必须第一人称世界内语言、无数值无系统词，永不直接渲染 LLM 原始思维链"` | 无 | cosmetic，补 |

### 1.5 其余 8 个成员

**`ImpulseFeedbackMessage`**（DEL 2 + ADD 3 + channel 改值）
- DEL `accepted`、DEL `content`（快照无此二字段，ext 还在用 M0 简写法）
- **ADD `injected`**（boolean，**required**）
- **ADD `cue`**（`enum[accepted,hesitation,complaint,resistance]`，**required**）
- **ADD `reaction_monologue`**（`$ref MonologueReaction`，**required**）
- **channel `narrative` → `control`**
- required：ext 的 `[v,ws_seq,channel,type,accepted,content]` → 快照的 `[v,ws_seq,channel,type,injected,cue,reaction_monologue]`
- cosmetic：补成员 description（§10 意愿冲突度表现；cue 非数值；自我怀疑非被操纵感）

**`CombatEventMessage`**（DEL 3 + ADD 6 + required 全换）
- DEL `kind`、DEL `attacker`、DEL `defender`（§9 决策点制表现只用 rtoken，不暴露交战双方）
- **ADD `exchange`**（integer min=0，**required**，desc「战斗内局部序号，非世界 tick」）
- **ADD `rtoken`**（`$ref RToken`，**required**）
- **ADD `posture_visual`**（string，**required**）
- **ADD `projectiles`**（`array<$ref Projectile>`，optional）
- **ADD `hits`**（`array<$ref Hit>`，optional）
- **ADD `exchange_resolved`**（boolean，**required**）
- required：ext 的 `[v,ws_seq,channel,type,kind]` → 快照的 `[…,exchange,rtoken,posture_visual,exchange_resolved]`

**`TimescaleMessage`**（DEL 1 + ADD 3 + channel 改值）
- **ADD `mode`**（`enum[normal,combat]`，**required**）
- **ADD `active`**（boolean，**required**）
- **ADD `note`**（optional，新增时直接用 oneOf-null 形 §3.2，**不要用 nullable**）
- DEL `rate`（契约不携带数值）
- **channel `render` → `control`

**`ControlAckMessage`**（DEL 2 + ADD 3 + channel 改值）
- DEL `ack_of`、DEL `ok`（ws.py 实发的是 action/applied/speed，见 §6）
- **ADD `action`**（`enum[pause,resume,set_speed]`，**required**）
- **ADD `applied`**（boolean，**required**）
- **ADD `speed`**（`integer enum[1,4,16]`，optional）
- **channel `session` → `control`**
- required：ext 的 `[v,ws_seq,channel,type,ack_of,ok]` → 快照的 `[…,action,applied]`

**`SyncRequestMessage`**
- **ADD `reason`**（string，**required**；值域 `gap_detected|reconnect|after_load`）

**`MoveRequestMessage`**
- **channel `control` → `render`**
- cosmetic：补成员 description、`target_x`/`target_y` 补 description

**`PlayerImpulseMessage`**
- `preset` 走 §3.1 修法（`nullable` → `oneOf-null`）

**`WsErrorMessage`**
- **ADD `ref`**（string，**required**）→ required 变 `[v,ws_seq,channel,type,ref,code,message]`
- M2-K2 说的「error 无 ref」指**不用 `$ref` 引用外部 schema**；`ref` 字段本身**要保留**（ws-protocol.md §4.5 有它）
| `PlayerImpulseMessage` | `preset` 走 §3.1 修法（`nullable`→`oneOf-null`） |
| `WsErrorMessage` | **ADD `ref`**（string, required）→ required 变 `[v,ws_seq,channel,type,ref,code,message]`；M2-K2 已确认「error 无 ref」指**不用 `$ref` 引用外部 schema**，`ref` 字段本身**要保留**（ws-protocol.md §4.5 有它） |

### 1.6 通道枚举错值（返工最易漏，单独列出）

| 成员 | 快照 channel | ext channel | 证据 |
|---|---|---|---|
| `MoveRequestMessage` | `render` | `control` | `ws.py:267` `_CHANNEL_FOR["move_request"]="render"` |
| `TimescaleMessage` | `control` | `render` | ws-protocol.md §3.2 明确 control |
| `ControlAckMessage` | `control` | `session` | `ws.py:257` 实发 `"channel":"control"` |
| `ImpulseFeedbackMessage` | `control` | `narrative` | ws-protocol.md §3.2 明确 control |

### 1.7 信封 `v` description 系统性偏差（1 行改动消 14 处）

ext 的 `_envelope` 给 `v` 加了 `"description": "协商后的协议版本 major.minor"`，快照 14 个成员的 `v` **均无 description**。这是唯一一个「一个改动消全部」的 diff。

**返工动作（二选一）**：① 删掉 `_envelope` 里 `v` 的 description（推荐，1 行）；② 保留，由 kilo 在快照 14 处补同款 description（kilo 域动作，复验前处理）。
> 若选 ②，请在回执中标注，kilo 复验前补齐；否则 §4.1 的「结构 diff 归零」会残留 14 处。

---

## 2. 缺失 HTTP schema 清单（P0，共 22 个）+ 来源路由与施工点

根因（M2-K2 已定位）：sim HTTP 路由是裸 `dict[str, Any]`——`sim/api/main.py:108` `health()`、`:118` `world_map()` 都没挂 `response_model`，FastAPI 生成不出子结构；anchors 三路由**根本不存在**（M5 阶段）。

### 2.1 可在本轮直接施工的 17 个（缺了它们 = 切源丢 schema）

| # | schema | 快照定义要点 | 来源 / 施工点 | response_model 目标 |
|---|---|---|---|---|
| 1 | `Actor` | required=[rtoken,sprite,x,y,facing,anim]；tint optional；facing→`$ref Facing` | `FullSnapshotMessage.actors.items` | WS 成员内联 → 抽 schema |
| 2 | `ActorDelta` | **required 仅 [rtoken]**；op:enum[add,remove] + 其余全 optional | `StateDeltaMessage.actors.items` | 同上 |
| 3 | `Light` | required=[rtoken,x,y,kind,radius,flicker] | `FullSnapshotMessage.lights.items` | 同上 |
| 4 | `LightDelta` | required=[rtoken]；flicker optional | `StateDeltaMessage.lights.items` | 同上 |
| 5 | `Structure` | required=[rtoken,tileset_ref,x,y,phase]；phase:enum[built,collapsing,rubble] | `FullSnapshotMessage.structures.items` | 同上 |
| 6 | `StructureDelta` | required=[rtoken]；其余 optional | `StateDeltaMessage.structures.items` | 同上 |
| 7 | `Weather` | required=[visual,ambient_light] | `FullSnapshotMessage`+`StateDeltaMessage` 两处 | 同上 |
| 8 | `MapInfo` | required=[tileset,w,h] | `FullSnapshotMessage.map` | 同上 |
| 9 | `RToken` | `type:"string"` + description（不透明替身/不可反查/连接生命周期内有效） | **9 处引用**：`Actor`/`ActorDelta`/`Light`/`LightDelta`/`Structure`/`StructureDelta`/`Projectile`/`Hit`/`CombatEventMessage.rtoken` | 同上（抽公共） |
| 10 | `Facing` | `enum:["n","e","s","w"]` | Actor.facing + ActorDelta.facing | 同上 |
| 11 | `CombatInfo` | required=[active] | `FullSnapshotMessage.combat.oneOf[0]` | 同上 |
| 12 | `Projectile` | required=[rtoken,kind,x0,y0,x1,y1,dur] | `CombatEventMessage.projectiles.items` | 同上 |
| 13 | `Hit` | required=[rtoken,visual,bleed]；bleed:enum[none,light,heavy] | `CombatEventMessage.hits.items` | 同上 |
| 14 | `MonologueReaction` | required=[form,content]；form:enum[bubble,thought,plan] | `ImpulseFeedbackMessage.reaction_monologue` | 同上 |
| 15 | `HealthStatus` | required=[status,world_running,in_combat]；status:enum[ok] | **GET /api/health 200** | `main.py:108` → `response_model=HealthStatus`（settings 四路由已是范例，照抄） |
| 16 | `WorldMapResponse` | required=[w,h,tileset,chunks]；chunks=`array<MapChunk>` | **GET /api/world/map 200** | `main.py:118` → `response_model=WorldMapResponse`；快照 description 明写「对齐 sim `map_static_payload`」，`ws.py:174` 即该函数 |
| 17 | `MapChunk` | required=[cx,cy,collision_b64]；collision_b64 = base64(每格 1 字节 0/1，chunk 内行优先) | `WorldMapResponse.chunks.items` | 随 #16 |

### 2.2 判「本轮不施工」的 5 个（复验期望值，不是漏项）

| schema | 判定理由 | 复验期望 |
|---|---|---|
| `AnchorCreate` / `AnchorRename` / `AnchorListItem` | anchors 三路由（`/api/anchors`、`/api/anchors/{id}`）在 sim 中**不存在**（M5 阶段），无路由可挂 `response_model` | 复验时 `MISSING in ext` **允许残留这 3 个**；建议在 `openapi_ext.py` 留 TODO 注释指明 M5 施工点，防遗忘 |
| `ProblemDetail` | 快照中**无任何路由引用**，是错误响应统一形状的规范保留位 | 不施工、不建路由；保持快照定义 |
| `WsEnvelope` | 快照中**无任何路由引用**，W6 之后成员自带信封字段，仅文档性定义 | 同上 |

> 若 Claude 域希望本轮就把结构 diff 打到「只剩 2 个」（`ProblemDetail`+`WsEnvelope`），可以把 3 个 anchor schema 以纯 dict 形式加进 `_WS_SCHEMAS`（它们 tiny：`AnchorCreate`/`AnchorRename` 都是 `{name:string}`）——可以但非必须，**不挂路由也能定义 schema**。此为可选项，不影响 §4.1 判绿（判据允许残留 5 个）。

### 2.3 附带差异（返工时裁定，不阻塞）

| 项 | 快照 | ext/sim 现状 | 处置建议 |
|---|---|---|---|
| 路径参数名 | `/api/settings/profiles/{id}` | FastAPI 自动生成 `{profile_id}`（因 `main.py` 形参名是 `profile_id`） | 访问路径相同，差异只在生成的 path 模板。**倾向改快照向实现靠齐**（kilo 域，复验前改）→ sim 侧**不要动形参名**（会碰 settings 路由实现，超出返工范围） |
| `ProfileCreate`/`ProfileUpdate` 字段 | 显式 `type:"string"` | Pydantic 在 3.1 展开成 `anyOf` | **生成器行为，非缺陷**；前端类型归一后等价 → §4.2 白名单 |
| `ProfileListItem` 的 `active`/`api_key_hint`、三个 Profile* 的 description | 有 | 无 | cosmetic → §4.2 白名单 |
| `Profile*` 的 `additionalProperties` | `false` | 缺省 | cosmetic → §4.2 白名单 |
| `ProfileCreate/ListItem` 的 `minimum` | `0`/`1` | `0.0`/`1.0` | JSON 浮点序列化，语义等价 → §4.2 白名单 |
| `components.schemas` 多出 `HTTPValidationError`/`ValidationError` | 无 | FastAPI 自动生成 422 | §4.2 白名单（快照不需补） |
| `info.title`/`info.description` | mock 源文案 | sim 文案 | §4.2 白名单（切源自然消解） |

---

## 3. nullable 修法对照（`oneOf:null` 正确形）

### 3.1 ⚠ 先读：任务单前提有一处需修正

任务单列「preset/subject/attacker/defender/reaction/note 六字段」的 nullable 修法。逐字段核快照后的真实结论：

| 字段 | 快照中是否存在 | 真实处置 |
|---|---|---|
| `PlayerImpulseMessage.preset` | **存在**，但快照自己写的就是旧 `nullable` 形 | 改 oneOf-null；**且快照侧要一起改**（两域各改一边，见 §6 附注 1） |
| `PerceptionMessage.subject` | **不存在**（快照 perception 只有 sense/content/form） | **整字段删除**，不存在 nullable 修法（ext 上有、快照无 → DEL） |
| `CombatEventMessage.attacker` / `defender` | **不存在** | **整字段删除**，同上 |
| `MonologueMessage.reaction` | **不存在**（W7 已删） | **整字段删除**，同上 |
| `TimescaleMessage.note` | **存在**，`oneOf:[{string},{null}]` | 补字段时**直接用这个正确形**，不要用 nullable |

→ 真正需要「`nullable` → `oneOf-null`」改写的只有 **1 处**（`preset`），另 1 处（`note`）是**新增字段时直接写对**；其余 4 个字段的正确处置是**删除**。

### 3.2 通用修法（照这个形写，别再出现 `nullable`）

```jsonc
// ❌ ext 现状（OpenAPI 3.1 no-op，openapi-typescript 不产 | null，前端把「可为空」静默丢掉）
"preset": { "type": "string", "nullable": true }

// ✅ 目标形
"preset": { "oneOf": [{ "type": "string" }, { "type": "null" }] }
```

**enum + null 嵌套形**（`PerceptionMessage.form`、`TimescaleMessage.note` 用；注意 oneOf 第一支是带 enum 的 string，不是裸 string）：

```jsonc
// 快照 PerceptionMessage.form 原文，直接可抄
"form": {
  "oneOf": [
    { "type": "string", "enum": ["bubble", "thought", "plan"] },
    { "type": "null" }
  ]
}
```

**ref + null 混用样例**（`FullSnapshotMessage.combat` 用；快照原文）：

```jsonc
"combat": { "oneOf": [{ "$ref": "#/components/schemas/CombatInfo" }, { "type": "null" }] }
```

**改完的自检**：ext 侧 `nullable` 关键字出现次数必须 = **0**（当前 5 处）。

---

## 4. 复验口径（K3 返工后由 kilo 执行）

判据 = **生成物与快照结构 diff 归零**（白名单见 §4.2）。两条命令：

```powershell
# ① 生成本机 sim 生成物（TestClient 口径，不占端口）
$env:LZ_MASTER_KEY="<64位hex临时值>"; $env:PYTHONPATH="<kilo 树路径>"
uv run python <gen_sim.py>     # → sim-openapi.json

# ② 结构 diff（白名单过滤后全空 = 绿）
uv run python <diff.py>        # → diff-report.txt
```

`<gen_sim.py>` / `<diff.py>` = kilo 本机私有脚本（本次比对同款：成员清单、逐字段 shape 签名、channel/type enum、required、additionalProperties、nullable 计数、paths 六项检查），复验时随回执附「白名单外差异 = 0」结论。

### 4.1 逐项验收标准（与 §1-§3 对应）

1. SECTION「成员清单」：`MISSING in ext` 从 22 → **≤5**（只许剩 `AnchorCreate`/`AnchorRename`/`AnchorListItem`/`ProblemDetail`/`WsEnvelope`，见 §2.2）。
2. SECTION「逐字段」：§1 表格与 §1.5 清单列出的 44 处字段级差异**全部归零**，8 处 required 清单随之对齐；`v` description 若选 kilo 补快照则由 kilo 在复验前补齐。
3. SECTION「channel/type enum」：4 处错值全归零。
4. SECTION「nullable」：ext 侧 = **0**；快照侧 = 0（preset 一起改）或 1（kilo 未改时，需在回执标注）。
5. SECTION「paths」：差异只剩 `{id}` vs `{profile_id}`，按 §2.3 裁定后单边归零。

### 4.2 已知白名单（出现不算返工失败）

| 差异 | 原因 | 处置 |
|---|---|---|
| `HTTPValidationError` / `ValidationError` | FastAPI 自动生成 422 形状 | 白名单 |
| `info.title` / `info.description` | 快照是 mock 源说明文案 | 白名单 |
| `ProfileCreate`/`ProfileUpdate` 字段 `anyOf` | Pydantic 可选字段在 3.1 的展开行为 | 白名单（前端类型归一后等价） |
| `Profile*` 的 description / `additionalProperties` / `minimum` 浮点 | 生成器不吐 description、`additionalProperties` 缺省、JSON 浮点序列化 | 白名单（不影响类型） |
| `WsMessage` oneOf 成员顺序 | 两边一致，非差异 | — |

---

## 5. 返工顺序建议（Claude 域施工）

1. **先抽公共子 schema**（§2.1 的 #1-#14，共 14 个）——它们是 §1 WS 成员 diff 的前置，抽完 `$ref` 才有落点。抽时注意 `required` 别搞错：`Actor` 是 6 个 required，`ActorDelta`/`LightDelta`/`StructureDelta` **只有 `rtoken` 一个 required**（增量语义：只带变动字段）。
2. **改 12 个 WS 成员**（§1）——其中 4 处 channel（§1.6）和 6 处字段增删最容易漏，建议逐成员对表打勾。
3. **删 `_envelope` 里 `v` 的 description**（§1.7，1 行消 14 处 diff）。
4. **挂 HTTP `response_model`**：`health=HealthStatus`、`world_map=WorldMapResponse`（§2.1 的 #15/#16/#17）——当前路由上只有这两个能挂。
5. ** anchors 3 schema 不动**（§2.2），但留 TODO 注释指明 M5 施工点。
6. 验证：`uv run pytest sim/tests/test_openapi_ext.py -q`（现 8 用例，注意**新增字段可能要求同步补/改用例**——尤其 combat 从 required 改 optional、ControlAck 换字段、`ActorDelta.op`）+ 全量 `uv run pytest -m "not bench"`。
7. 完成 → 本树 `.orca/talking.txt` 留言板回执 kilo， kilo 做 K3 复验。

---

## 6. 证据与附注

- ext 基线确认：`git log --oneline --follow -- sim/api/openapi_ext.py` → 59ffd86 之后**零提交**（`git diff 59ffd86 HEAD -- sim/api/openapi_ext.py` 空）。
- **channel 佐证**：
  `sim/api/ws.py:267` `_CHANNEL_FOR = {"move_request":"render","set_control":"control","sync_request":"session","hello":"session"}`；
  `ws.py:256-262` control_ack 实发 `{"type":"control_ack","channel":"control","action":"resume","applied":true,"speed":1}`；
  → **ext 的 `ControlAckMessage` 三项都错**（channel + 字段名），快照与 ws.py 实发**一致**，返工以快照为准。
- **`ActorDelta.op` 佐证**：ws-protocol.md §4.1 state_delta 样例含 `{"op":"add",...}` / `{"op":"remove","rtoken":"rt_5"}`，且明写「`op` 缺省视为 update」→ 该字段是协议契约不是可选装饰。
- **`WorldMapResponse` 佐证**：快照 description 明写「对齐 sim/api/main.py::world_map → map_static_payload」；`ws.py:174` 即该函数（chunk 模式产物）→ 施工路由确认。
- **附注 1（快照侧 kilo 要改的一处）**：`PlayerImpulseMessage.preset` 快照现在是 `nullable` 旧写法。
  **ext 与快照必须一起改**，否则 §4.1 第 4 项残留 1 处。
  为避免同文件冲突：**Claude 返工只改 ext 侧**，快照侧由 kilo 在复验前统一改。
  同理 `{id}`→`{profile_id}`（§2.3）也由 kilo 改快照。
- **附注 2（两处新发现，任务单未列）**：①`WsErrorMessage.ref` 字段缺失（M2-K2 确认的「error 无 ref」指不用 `$ref` 引用，字段本身要保留）；②`MonologueMessage.form` 缺失（required）。这两处会让前端类型少了判别字段，属 P1，已在 §1.5 列出。
- 本文件不含实现码；字段命名 / 出戏边界依据 `ws-protocol.md` §3 §4 §5 与 `DESIGN.md` §6 §9 §10 §19。
