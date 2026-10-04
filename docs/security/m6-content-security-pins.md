# M6 内容面安规预研：语言阶层 / 空间迷雾 / 生态动物（docs/security/m6-content-security-pins.md）

> 维护：Codex（安全/合规/风险域）· 依据：M6-S4 派单（2026-10-04）·
> 基线：main `3f321b4` · 日期：2026-10-04 · 树：ZX466/codex
> 性质：**预研·零代码零 schema**；范围判断归主树，本稿不裁做不做、不裁参数值。
> 约束：词表零扩散（`META_SHELL` 继续空表）；D-10 不破；只在本树施工。

## 0. 一句话 + 现状快照

**M6 内容面的安规命题是：语言阶层只能外显为行为，迷雾只能暴露玩家已得感知，
生态/动物事件不得把归因或计数升格成元信息。**

现状（本机核库，非推测）：

| 项 | 事实 | 出处 |
| --- | --- | --- |
| 语言判定已落 | `LanguageProfile(literacy, jargon, class_register)` + 识字/行话降质；`literacy` 只做判据不进文本 | `sim/agent/language.py` |
| 语言挂载点 | `PerceptionFrame.narrated()` 在通道分组输出前降质，只动叙事文本，不裁原始观测 | `sim/perception/frame.py` |
| 意愿输入域 | `willingness_conflict` 只接人格/风险/需求/处境四项，无权力档参数 | `sim/agent/will.py` |
| 迷雾 v0 | `FogOfWar` 只存已揭示 chunk；模块注明「不进事件流也不进存档」 | `sim/world/fog.py` |
| 迷雾前端边界 | M0 client 明写「不做区块迷雾渲染」；当前协议无 `fog.reveal` 帧 | `docs/arch/m0-client.md`、`shared/protocol.ts` |
| 物质事件 | `MatterPayload` 已带 `x/y`、`amount`、`durability`；fire 生命周期 payload 零归因键 | `sim/core/events.py` |
| 动物/生态机制 | 当前无 `fauna.py`/`ecology.py`，动物只留物种 profile 占位 | `Test-Path sim/world/fauna.py` = false；`DESIGN.md §7` |

## 1. 语言阶层：档位不是权力泄漏面，但受三条边界约束

### 1.1 对照 S11 的判定

派单问：「NPC 说话的语域档（粗/日常/文雅）由权力与亲疏决定——档位本身是不是
权力语义的泄漏面？」

**判定：否，前提是档位只以行为外显。** S11 口径是「不可见的是状态，可测的是
行为」：语域是可观察行为；只要玩家无法从语域推出 `npc_power.power_level`
的连续值或档位号，它不是 D-10 泄漏面。

**三条边界（超出任一即转为泄漏面）：**

1. **不直接依赖 power 档**：语域选择不得读 `npc_power` 或 `authority` 量级。
   若产品确需影响，只能先转成人格/亲疏/处境等既有意愿域输入。
2. **不出机器档号**：`粗/日常/文雅` 或其数值索引、阈值、切分点不得出现在
   WS/prompt 文本。
3. **不造连续可读量**：语域是离散行为表现，不提供「越文雅=权力越高」的可
   排序数值。

### 1.2 施工级安规钉

| 钉 | 可证伪判据 | 落点建议 | 归属 |
| --- | --- | --- | --- |
| LC-1 旁路禁 | `speech_register`/新模块生产码零 `npc_power`/`power_level`/`authority` 引用；`willingness_conflict` 签名不得新增权力参数 | 新增模块存在后扫；同 W-A2-1 白盒手法 | Claude（我复核） |
| LC-2 元信息禁 | 玩家可见叙事文本禁 `class_register`/档号/阈值键名与数值索引；可直接套 `scan()` 终扫 | `test_m5_session_state.py::TestLoadAnchorEmitsSessionState` 体例 | codex 判据 / kilo 出站面 |
| LC-3 排序可读性核 | 固定输入下只换语域档，不引入 `npc_power` 值；对同一行为样本验证语域可变而权力量级不出文本 | 机制施工单随附核 | codex 复核 |

**与既有钉交叉**：LC-2 走现行 `scan()`，不扩 `META_SHELL`；LC-1 与 S8 W-A2-1
同源，是「机制不得旁路意愿/叙事管线」的扩展，不是第二真相源。

## 2. 空间迷雾：只投影已感知事实，禁前端反推

迷雾是视角面投影，不是世界真相。当前 v0 未进协议；若 M6 新增 `fog.reveal`，
必须满足四条：

| 钉 | 可证伪判据 | 落点建议 | 归属 |
| --- | --- | --- | --- |
| FG-1 帧只载揭示事实 | `fog.reveal` payload 只含玩家实际踏入/实际观察后确认的 chunk 坐标；禁邻居/候选/房间形状等未探索字段 | 新帧走 `openapi_ext.py` + versioning CR | kilo |
| FG-2 增量不外泄邻块 | 一次 reveal 只改变该 chunk 的可见位，`state_delta`/`full_snapshot` 不得携带邻块推断；测试构造 reveal 前后帧 diff，禁揭示坐标外新增地理键 | API 帧测试 | kilo |
| FG-3 静态几何不做作弊通道 | `full_snapshot.map` 仅 `w/h/tileset` 现状；地形、障碍、道路、NPC 分布不得进帧；前端拿不到可用种子/静态地形哈希反推未探索区 | `test_ws_gateway.py` 回归 + `gen-protocol --check` | kilo |
| FG-4 持久化不做全图化 | 若读档要重放迷雾，只能按玩家/视角的真实历史揭示事件或最小存储面重建；禁将全图 discovered 位集一次性塞进包/响应 | 物化包施工单 | opencode |

**判定补充**：真正「已踏入」的 chunk 暴露给玩家是正当事实；防作弊重点不是藏
历史，而是**不提供未探索区先验**。因此 v0 的纯内存设计是安全形态；接入前端
时优先复用它，不新增世界真相出口。

## 3. 生态 / 动物：复用既有事件族，禁归因升格

生态序 1 离火灾面最近，动物是物种级行为投影。当前基线没有新模块；施工前
先按纪律封顶：

| 钉 | 可证伪判据 | 落点建议 | 归属 |
| --- | --- | --- | --- |
| EN-1 事件族复用 | 生态/动物每步状态变更优先走 `matter.*`/`material.moved`/`structure.*`/既有移动族；新增 kind 必须证明既有族表达不了，且经 `PAYLOAD_MODELS` 闭合 CR | `test_m5_authority_surface.py::TestProtocolClosedness` | opencode 数据面 |
| EN-2 归因零升格 | 动物/生态事件 payload 禁 `actor`/`authority`/意图归因/权力词键，同 fire 零归因纪律；`extra="forbid"` | 复用 D-5 黑名单判定 | opencode |
| EN-3 量值最小化 | 生态投影可为重放带 `x/y`、`quantity`、`durability`；这些是物理账本字段，不是玩家叙事元信息。若 M6 决定把 quantity 送玩家面，必须另行裁「是否属于戏内可观察计数」，不能默认出站 | 数据面白盒 + 出站面钉 | opencode/kilo |
| EN-4 动物叙事零物种数值 | 动物 `hp`/嗅觉半径/语言词数等 profile 值不得进玩家文本；只以行为外显（例如「它蹭了蹭你」）；文本终扫零数值键 | perception/monologue 钉 | Claude/kilo |
| EN-5 新增帧最小集 | 若确需动物行为帧，先复用 `perception`/`monologue`；新协议字段走 versioning CR 且保持封闭模型 | `shared/protocol.ts` + `openapi.json` | kilo |

**铁律 1 口径**：「零元信息量值」约束的是玩家可见叙事/协议面，不等于禁止
重放所需的物理坐标与账本量。把两类量混谈会误伤 T1/T2；本稿按「事件可载、
玩家面必裁」分界。

## 4. 三组归属与执行序

| 组 | 钉 | 归属 | 触发时点 |
| --- | --- | --- | --- |
| 数据/机制面 | LC-1、EN-1、EN-2、EN-3 | opencode / Claude | 模块落盘即跑 |
| 出站面 | LC-2、FG-1、FG-2、FG-3、EN-4、EN-5 | kilo | 新帧/新字段进协议 CR 时 |
| 复核/行为面 | LC-3、FG-4 | codex 复核 / opencode 施工 | 机制接线与读档扩展时 |

**交叉钉复用，不重建**：

- 语言文本与失败/告知文案继续走现行 `scan()`；`META_SHELL` 不预填 8 词。
- 红线 B 当前禁键集是权力面资产；生态/动物归因若要泛化成通用禁键，须走
  CR 扩键，不得私自改 `AUTHORITY_FORBIDDEN_KEYS`。
- T3 现有 69 条已覆盖身份/指令/越权类；新增语域、迷雾、动物题面前先逐条
  试扫，确有命中缺口再走语料 CR；不为「预感」扩语料。

## 5. 残余风险

1. **语域与权力的间接相关**：若玩法让高权力 NPC 的生活语境自然更文雅，玩家
   仍可做弱统计推断。这不是 D-10 泄漏，但 LC-3 要防「实现顺手直连」；叙事
   抽样可弱化信号，是否做属主树裁。
2. **迷雾全图化冲动**：断线重连容易改成「全图位集」。若如此，FG-4 必须先落，
   否则前端将获得可用先验。
3. **生态计数误放玩家面**：`quantity` 对账本必须存在；若被直接放进叙事，
   会变成铁律 1 违例。施工单应显式分「账本字段」与「玩家可观察计数」。

## 6. 变更纪律

- 本稿零代码；所有钉在对应施工单中落地，预研不抢施工。
- 本稿不裁 M6 内容范围，不预填 `META_SHELL`，不改协议。
- 任何词面/协议键/禁键集扩展必须走 CR；本稿只给可证伪判据与归属。
