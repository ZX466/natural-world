# M5 接口面预研：时间刻度控制面 + 读档=分叉协议面

> 能力域：接口 / 兼容性（kilo） | 状态：**提案稿（预研），零代码零 schema 改动**
> 派单：Claude 主树 `.orca/talking.txt`「M5-K1」（2026-09-27）
> 门禁：本稿只列问题、提案与待裁点。**不改** `sim/**`、`shared/**`、`client/**`，**不碰** `shared/protocol.ts`。
> 依据：DESIGN.md §2 C6 / §10 时间锁定 / §12 双轨存档 / §13 十个现实系统 / §17 M5 行 / §19 禁止事项
> 既有资产：`ws-dispatch-proposal.md`（K4 §8.1-8.8 裁决）→ K6 落地（`set_control` pause/resume/speed 连接级栈）→ K9 集成对账 → K10（`PlanDelta` schema）

---

## 0. 速览

**结论十条**

1. **M5「时间刻度」在 DESIGN 里有两处所指，接口面必须先消歧**（§2.0）：§10「时间锁定」已把 1x/4x/16x + 战斗时间尺**锁死**并已落地；§13/§17 的「加内容六项·时间刻度」另有所指（世界日历/长跨度推进）。**这是 M5-K1 的头号待裁点（D-1）**，不裁则后面全部提案无锚。
2. **玩家倍率通道已完备，M5 大概率不需要新 action**：`_handle_set_control`（`sim/api/ws.py:410`）+ `SetControlMessage`（`sim/api/openapi_ext.py:248`）+ `ControlAckMessage`（`:388`）三者闭环，语义正交于战斗时间尺。
3. **不扩 `speed` 枚举**（主张）：`{1,4,16}` 是 DESIGN §10 明文锁定的档位集，且 `clock.ALLOWED_SPEEDS` 硬校验（`sim/core/clock.py:20`）。M5 若要「快进」，走**新 action**（长跨度推进语义），别把稳态倍率枚举撑大（量化理由见 §2.3）。
4. **暂停栈在高倍速前必须重做语义**（实测四宗问题，§1.4 G-1~G-4）：其中 **G-1 是协议违约**——`pause→pause→resume` 实发出 `control_ack{speed:0}`，而 schema 枚举是 `[1,4,16]` 且 `additionalProperties:false`。前端 TS 类型断言会红。
5. **`timescale`（S→C）已定义但零实现**（G-5）：`sim/api/` 内除 `openapi_ext.py` 外无任何 `timescale` / `COMBAT_SCALE` 引用 ⇒ 战斗慢镜前端当前无感知。
6. **「世界已分叉」不能靠 diff 告知**（§3.2）：可用的游标只有 `ws_seq`（传输序号，跨连接不连续），而 `tick`/`seq`/`branch_id` 一律禁出网关（`ws-protocol.md` §2/§5）⇒ **M5 走全量 `full_snapshot`**，增量 diff 若要则必须先引入不透明 `catchup_token`。
7. **rtoken 跨分叉稳定**（`_rtoken` = `sha256(entity_id)[:12]`，`ws.py:122`）⇒ **同一 rtoken 在分叉前后可指不同状态**，前端绝不可拿它做跨分支 diff 或身份连续性推断。分叉/读档**必重发全量**。
8. **✅ 已裁 21-A / 已落（M5-K2）**：`versioning.md` §8-1「rtoken 连接生命周期内有效、重连由 full_snapshot 重分配」与实现（稳定派生、跨连接不变）相悖（G-8/D-8）——**裁 21-A 采①文档订正、实现不动**，`ws-protocol.md` §5 + `versioning.md` §7/§8-1/§8-4 + `RToken.description` 已全部改口径，协议形态与版本号不变。
9. **重连后前端不知道当前刻度**（G-7/D-5）：连接期只发一帧 `full_snapshot`，没有「当前是否暂停 / 当前倍率 / 当前游标」下发面。M5 一旦上刻度面板与读档 UI，这是**前必修**。
10. **生成管线不变量**：以上全部字段将来一律走 `openapi_ext.py` → `shared/openapi.json` → `npm run gen:protocol`，**禁手写 `protocol.ts`**。字段级归属清单见 §4.2。

**待裁清单导航**：D-1~D-5（时间刻度）见 §2.7；D-6~D-9（读档分叉）见 §3.8；汇总表见 §5。

---

## 1. 现状盘点（铁证行号取自本分支 HEAD）

### 1.1 玩家侧速度通道

| 环节 | 位置 | 事实 |
|---|---|---|
| 时钟常量 | `sim/core/clock.py:17-20` | `TICKS_PER_REAL_SECOND_NORMAL=60.0`（1 tick=1 游戏秒，1x=60 tick/s）／`COMBAT=1.0`／`MAX_CATCHUP_REAL_SECONDS=4.0`／`ALLOWED_SPEEDS={0.0,1.0,4.0,16.0}` |
| 有效速率 | `clock.py:60-66` | `ticks_per_real_second = base(时间尺) × speed(倍率)`——**两个因子正交** |
| 分发块 | `ws.py:410-432` | `set_speed`（校验排除 bool，值 ∈ `(1,4,16)`，否则 `bad_speed`）／`pause`（压 `_PRE_PAUSE_SPEED` + `set_speed(0.0)`）／`resume`（弹栈，空则回落 1.0） |
| 会话态 | `ws.py:450-457` | `_PRE_PAUSE_SPEED: list[float]` 是**模块级全局**（注释自称「连接级」，K9 已记 MEDIUM） |
| 协议 | `openapi_ext.py:248-256 / 388-397` | `SetControlMessage{action:pause\|resume\|set_speed, speed:1\|4\|16}`；`ControlAckMessage{action, speed?, applied}`，两帧皆 `additionalProperties:false` |
| 文档 | `ws-protocol.md` §4.3 | 已明记「`control_ack.speed` = 用户设定倍率，**不是**当前有效 tick 率」 |

### 1.2 战斗时间尺通道

| 环节 | 位置 | 事实 |
|---|---|---|
| 事件源 | `sim/core/tick.py:126-134` | `issue_combat_scale(entering)` → 切 clock + 落 `combat_scale` 世界事件（可回放） |
| 协议 | `openapi_ext.py:378-387` | `TimescaleMessage{mode:normal\|combat, active:bool, note:string\|null}`（control 通道，S→C） |
| 广播 | —— | **零实现**：`sim/api/ws.py` / `main.py` 内无 `timescale` / `COMBAT_SCALE` 引用。`ws-dispatch-proposal.md` §1.5 指定的「`run_world_driver` 投影 `combat_scale` 事件广播」未接线 |

### 1.3 存档与分叉数据面

| 环节 | 位置 | 事实 |
|---|---|---|
| 分支模型 | `sim/core/persistence/models.py:35-46` | `Branch{id, forked_from_branch, forked_from_seq, status, abandoned_at}`（0001 迁移已建列） |
| 游标模型 | `models.py:97-110` | `PlayerAnchor{id, name, branch_id, tick, seq, agent_override, updated_at}` |
| 快照模型 | `models.py:73-94` | `Snapshot{branch_id, seq, tick, snapshot_data, is_cold, schema_version}`（seq = 该点事件流最大 seq） |
| 读档入口 | `ws.py:536-560` | `load_anchor` → `_ANCHOR_LOAD_HOOK`（`ws.py:521`，**生产无注册方**）或 `_ANCHOR_IDS` 同步查表 → 成功即回 `snapshot_payload` |
| 分叉写入方 | —— | **零**：`forked_from_branch` / `forked_from_seq` / `abandoned_at` 全仓无生产写入点；`_ANCHOR_LOAD_HOOK` 只在 `sim/tests/test_ws_gateway.py:628/650/684` 出现 |
| 戏外 CRUD | `docs/api/anchors-api.md` | `GET/POST/PATCH/DELETE /api/anchors` 契约已定（K1），CRUD 路由仍未施工（Claude 域） |

> 判读：**读档=分叉目前是「查表即回快照」的替身**。M5 分叉本体（定位→快照→重放→新分支→旧分支 abandoned）属架构/数据域施工；本稿只定**前端可见性**的协议面。

### 1.4 协议面既有缺口（G-1 ~ G-8）

| # | 缺口 | 证据 | 严重度 |
|---|---|---|---|
| G-1 | `pause→pause→resume` 实发 `control_ack{action:"resume", speed:0}`，**违反** `ControlAckMessage.speed` 枚举 `[1,4,16]` | 本机实测：`ws.py:429` `int(restored)`，restored=`0.0`；schema `openapi_ext.py:393` | **HIGH（协议违约，前端类型断言红）** |
| G-2 | 无暂停时 `resume` 静默把倍率改回 1x 并回 `applied:true` | 本机实测（栈空 → 回落 1.0）；`ws.py:429` | MEDIUM（未声明的状态变更） |
| G-3 | 暂停期间 `set_speed` **立即解除暂停**（暂停无独立表示，等价于 speed=0）；随后 `resume` 又按栈弹回旧值 | 本机实测序列 `pause→set_speed 16→resume`：clock `0.0→16.0→1.0`，末态既非 16x 也非暂停 | MEDIUM（刻度面板上线后成可见 bug） |
| G-4 | `_PRE_PAUSE_SPEED` 模块级全局，多连接互窃倍率 | `ws.py:452`（K9 已记） | MEDIUM |
| G-5 | `timescale` 帧零广播实现 | `rg timescale sim/api/` 仅命中 `openapi_ext.py` | MEDIUM |
| G-6 | 分叉零写入方（见 §1.3 末行） | 全仓 grep | **阻塞 M5**（非接口域） |
| G-7 | 无「连接期刻度/游标初值」下发面 | `ws.py:340-349` 连接首帧只回 `hello_ack`，此后 `full_snapshot` | MEDIUM（M5 UI 前必修） |
| G-8 | `versioning.md` §8-1「rtoken 连接生命周期内有效、重连重分配」与实现（稳定派生）相悖 | `ws.py:122-130` vs `versioning.md:69` | **✅ 已关闭**（裁 21-A 采①，M5-K2 落地：文档四处 + `RToken.description` 经管线同步 + 口径钉子） |

> G-1/G-2/G-3 为本轮**新发现**（既有测试只覆盖单次 pause/resume：`test_ws_gateway.py:306/327/403`），零代码门禁下**只记录不修**，建议随 M5 刻度面施工一并收（见 §5 D-3）。

---

## 2. 块一：时间刻度控制面

### 2.0 术语消歧（先裁这个，否则后面全是空转）

DESIGN 里「时间刻度」出现在两处，所指不同：

| 出处 | 原文 | 所指 | 现状 |
|---|---|---|---|
| §10 时间锁定 | 「1 tick = 1 游戏秒；基准速度 **1x = 60 tick/s** 实机；支持暂停 / 4x / 16x。例外：战斗期间自动切战斗时间尺」 | **玩家侧速度控制面** | 已落地（M0/M4：`clock` + `set_control` + `control_ack`） |
| §13「加内容六个」+ §17 M5 行 | 「加内容六个（可增量，缩范围从这里砍）：时间刻度 / 不成文规矩 / 权力牙齿 / 巧合连锁 / 身体会坏 / 生命始终」 | **世界侧时间系统**（日历相位/节气/长跨度推进一类内容），与 §18 缩范围序里的「节气（保留昼夜+集市日）」相邻 | 部分底座在：`sim/core/calendar.py`（`TICKS_PER_GAME_DAY`／`DayPhase`／`game_time`／`is_market_day`）；玩家侧无任何呈现通道 |

**kilo 主张（D-1）**：M5 接口面**只承接玩家侧快进/变速**（即 §10 的延伸），世界日历/节气内容面归 §13 那条线（其呈现需求是「叙事化时间标签」，已由 `anchors-api.md::story_label` 承接）。理由：§10 的 1x/4x/16x 是**冻结契约**，而 §17 M5 行的「时间刻度」是**内容增量**；两者混谈会让「扩 speed 枚举」被误当成必选项。

### 2.1 三层刻度是正交量，协议面各归各位

| 层 | 谁驱动 | 传输/呈现通道 | 现状 |
|---|---|---|---|
| L1 玩家倍率 `speed ∈ {1,4,16}` | 玩家（`set_control.set_speed`） | C→S `set_control` + S→C `control_ack` | 已闭环 |
| L2 战斗时间尺 `normal\|combat` | sim（`issue_combat_scale`） | S→C `timescale` | schema 有、**广播无**（G-5） |
| L3 世界日历相位（昼夜/集市日） | sim（`calendar.phase_of_day` / `is_market_day`） | 目前**只经 HTTP `story_label`** 露出 | 无 WS 面 |

三层的乘积关系只在服务端成立（`clock.py:60-66`）。**协议面铁律：任一时刻至少有一层对前端可见**——M5 若上刻度面板，L1 与 L2 都得可见（⇒ G-5/G-7 必须先清），L3 可继续只走戏外 HTTP。

### 2.2 三个案（是否新增 control action）

| 维度 | 案 A：扩 `speed` 枚举 | 案 B：新增 action（长跨度推进） | 案 C：协议零改动 |
|---|---|---|---|
| 形 | `speed: 1\|4\|16` → `+64`（或更多） | `action: "fast_forward"` + 推进目标（叙事化时间点） | M5 刻度全在服务端，玩家仍只有 1/4/16 |
| 兼容 | 旧 client 不会发 64 ⇒ 无感；**新 client 发 64 给旧 sim → `bad_speed`**（错误码已有，可接受） | 新 type 值 ⇒ minor 升级，旧 sim 回 `bad_action`，旧 client 不发 | 零风险 |
| 与 DESIGN §10 | **相悖**（§10 明文「支持暂停/4x/16x」，枚举是契约的一部分） | 相容（§10 未禁止长跨度推进） | 相容 |
| 背压语义 | 稳态倍率，逐帧背压（§2.3 量化） | 一次性批处理：限帧摊还 + 中间态不可见 | 无 |
| 结论 | ❌ 不采（撑大枚举会连带 `clock.ALLOWED_SPEEDS`、`ControlAckMessage.speed`、`client` 三处） | ⭕ **推荐（仅当 M5 真的要「快进」）** | ⭕ 若 D-1 裁「M5 刻度=世界侧内容」，则本块整体零改动 |

**kilo 主张（D-2）**：`speed` 枚举**不扩**。M5 若要玩家侧快进，走**新 action**（建议命名 `fast_forward`，语义=「推进到某叙事化时间点」，服务端批处理+限帧摊还，完成后按 §3.2 走全量重同步）。理由三条：①§10 锁枚举；②`clock.ALLOWED_SPEEDS` 是硬校验，扩枚举要动内核域；③两者的背压/落库/广播模型不同（§2.3），混在一个枚举里会让「稳态 64x」和「一次推进一天」共享同一条帧预算。

### 2.3 高倍速的量化边界（M5 若扩档必须带这张表）

`base=60 tick/s`（normal）下的推导（**pi 域 tick 成本待复核**）：

| 倍率 | tick/s | 每帧 tick（60fps） | 1 游戏日（86 400 tick）实机耗时 | 单帧 tick 上限（`MAX_CATCHUP=4s`） | 每帧 sim 成本（按 0.125~0.23 ms/tick，T5 golden 10 实体实测区间） |
|---|---|---|---|---|---|
| 1x | 60 | 1 | 24 min | 240 | 0.13~0.23 ms |
| 4x | 240 | 4 | 6 min | 960 | 0.5~0.9 ms |
| 16x | 960 | 16 | 90 s | 3 840 | 2.0~3.7 ms |
| 64x（若扩） | 3 840 | 64 | 22.5 s | 15 360 | 8.0~14.7 ms |
| 256x（若扩） | 15 360 | 256 | 5.6 s | 61 440 | 32~59 ms |

- **帧预算**：`FRAME_BUDGET_SECONDS = 1/60`（`ws.py:45`）。16x 约占预算 12~22%，**64x 已顶到 48~88%**（未计事件落库 + 广播 + WS 序列化），256x 必然过预算。
- **广播帧率不随刻度变**：`run_world_driver` 按**帧** drain/广播（每帧一帧 `state_delta`），刻度只改变「每帧覆盖多少 tick」。⇒ **前端插值与丢帧检测语义不变**（`ws_seq` 仍是传输序号），这是刻度扩展对协议面最友好的一点。
- **单帧 tick 上限才是真风险**：`MAX_CATCHUP_REAL_SECONDS=4.0` 意味着一次 4 秒卡顿在 16x 下要补 3 840 tick（≈1 秒 CPU，`clock.py:83-86` 只截断 dt、不限 tick 数）。
- ⇒ **若 M5 扩档，必须同时定「单帧 tick 预算 + 超出丢弃并请求全量重同步」的口径**（否则前端静默漂移）。这是内核域（pi/Claude）的账，接口域只登记依赖。

### 2.4 暂停栈语义要不要扩

**先说结论**：高倍速本身**不要求**栈变深；真正的问题是**暂停没有独立表示**（暂停 ≡ `speed=0`，G-3），于是任何 `set_speed` 都能单方面解除暂停，`resume` 又按栈弹值，三条路径互相打脸（实测 `pause→set_speed 16→resume` 末态 1.0）。

| 方案 | 语义 | 优点 | 缺点 |
|---|---|---|---|
| ① **幂等单值**（推荐） | 暂停=一个 bool + 一个记忆倍率；`pause` 幂等（已暂停再 pause → 同 ack），`resume` 无暂停时 → `error{bad_action}` 或 no-op（**不回 speed:1 的假 applied**），暂停中 `set_speed` 只改记忆值、**不解除暂停** | 无栈深；消除 G-1/G-2/G-3 三宗；UI 语义直白（一个暂停键） | 需改 `ws.py`（Claude 域施工）；`_PRE_PAUSE_SPEED` 须从模块全局迁到**连接级**（顺带清 G-4） |
| ② 有界栈 | 保留栈，加深度上限 1（超出回 `bad_action`） | 改动小 | 治标：`set_speed` 解除暂停仍在；G-1 需额外把 `int(restored)` 夹到枚举内 |
| ③ 暂停中禁变速 | 暂停时 `set_speed` → `bad_action` | 最小 | 玩家「暂停着调刻度」是常见手势，UX 差 |

**kilo 主张（D-3）**：采**方案 ①**。栈是实现细节泄漏到协议语义（玩家只有一个视角，没有「嵌套暂停」这种 UI 对应物）；高倍速也不需要栈深——需要的是**记忆值 + 幂等 + 连接级隔离**。附带：连接级化后 `ConnectionManager`（K8 引入）已是每连接 `subscriber_id` 的家，记忆值挂那里即可（K6 提案 §8.9 部署债 #2 同源）。

### 2.5 serverToClient 要不要新增「刻度变化广播」

现状**只有回执，没有广播**：`control_ack` 是**请求-响应**语义（`set_control` 触发），`timescale` 是**sim 驱动**语义（战斗事件触发）。缺口是第三种情形：**服务端单方面改刻度**（保护性降速、日切降速、离线追赶完成、崩溃恢复后续跑）。

| 案 | 形 | 评价 |
|---|---|---|
| A 零新增 | 服务端单方面改速**不进协议**（只发 `control_ack` 形状的推帧？—— 那就破坏了 ack 的请求-响应语义） | ❌ 前端刻度面板会与真实刻度**静默漂移** |
| B 扩 `timescale` | 把 `TimescaleMessage` 从「战斗时间尺」扩成「通用刻度帧」（加 `speed`/`reason`） | ⚠️ 语义混淆：L1 倍率与 L2 战斗尺正交，塞进一个帧会让前端难以区分「我设的倍率」与「战斗慢镜」；且 `timescale` 已被 `mode:normal\|combat` 钉死语义 |
| C **新增 `rate_change`**（control 通道，S→C） | `{speed, paused, reason}`，`reason` 取值如 `player`/`protective`/`catchup_done`/`recovered`；仅在**非玩家发起**的刻度变更时广播 | ✅ **推荐（预留）**。versioning §3：新增 type = minor，旧 client 静默忽略（铁律：client 永不因未知 type 崩溃） |

**kilo 主张（D-4）**：M5 **不新增**（当前无「服务端单方面改速」需求，加了就是死 schema）；但**把 `rate_change` 登记为预留名 + 触发条件清单**（§4.2 表第 2 行），一旦 D-1 裁「玩家侧快进（案 B）」或引入离线追赶，**必须**同时落地它——否则快进过程中前端无任何进度/完成感知。

**连接期初值（G-7 / D-5）**：与广播不同，这是**当下就有缺口**的事实——重连后前端不知道世界此刻是暂停还是 16x、不知道自己在哪个游标。两条路：

- 扩 `hello_ack`（`ws.py:343-348` 现在只有一个空壳信封）——**最省**，但 `hello_ack` 尚无 schema（`_TYPE_OF` 无此项），等于顺手补一个消息；
- 新增 session 通道首帧（承载刻度 + 游标叙事标签 + 协议能力集）——**更完整**，M5 读档 UI 也需要它。

⇒ 主张与 §3.4 的「世界已分叉」告知载体**合并成同一帧**（见 D-6 案 A），避免两次新增消息。

### 2.6 与既有债的关系

- K9 抓的 **HIGH**「`if moved:` 才广播 `state_delta` ⇒ plan-only 变更不上线」与本块无关但同属 M5 刻度面板的数据面（`docs/api/m4-integration-audit.md` §2.3 挂账）。
- K9 抓的 **MEDIUM**「`_PRE_PAUSE_SPEED` 模块级全局」= 本块 G-4，方案 ① 一并清。
- G-5「`timescale` 零广播」= 本块 D-4 的前置（战斗慢镜当前前端无感知）。

### 2.7 本块待裁

| # | 待裁 | 选项 | kilo 建议 | 影响面 |
|---|---|---|---|---|
| D-1 | M5「时间刻度」指玩家快进还是世界日历内容 | ①玩家侧快进/变速 ②世界侧日历/节气 ③两者都做 | ①（②的呈现需求已由 `story_label` 承接） | 整块范围；②成立则本块零改动 |
| D-2 | 是否扩 `speed` 枚举 | ①不扩（新增 action）②扩到 64 ③不扩也不新增 | ③→若 D-1=① 则采① | `clock.ALLOWED_SPEEDS`／`ControlAckMessage`／`client` 三处联动 |
| D-3 | 暂停语义 | ①幂等单值 ②有界栈 ③暂停中禁变速 | ① | `ws.py:410-457` + G-1/G-2/G-3/G-4 |
| D-4 | 是否新增刻度广播 | ①不新增 ②扩 `timescale` ③新增 `rate_change` | ① 现（M5 不触发），③ 登记预留 | `openapi_ext._WS_SCHEMAS` + `_TYPE_OF` |
| D-5 | 连接期刻度/游标初值载体 | ①扩 `hello_ack` ②新增 session 首帧 | ②（与 D-6 合并成一帧） | WS 消息集合 +1 |

---

## 3. 块二：读档=分叉的前端可见性

### 3.1 M5 验收原文拆成三个协议场景

DESIGN §17 M5 行验收：「**离线再回来世界已变**；C6 测试绿」。拆成三个前端可感知场景：

| 场景 | 触发 | 前端必须知道 | 现状 |
|---|---|---|---|
| S1 重连追赶 | 断线期间世界自转，回来后 `sync_request` | 世界现状全量 | ✅ `sync_request` → `full_snapshot`（K5 已首修，`ws.py:401-407`） |
| S2 读档分叉 | `load_anchor` | 世界**换了一条时间线**（旧分支被弃） | ⚠️ 替身：查表即回 `full_snapshot`，无分叉语义、无告知帧（G-6） |
| S3 离线自转归来 | 长时间离线（多游戏日）后回来 | 「变了多少」——是否需要摘要 | ❌ 无。`full_snapshot` 只给当下渲染态，不给「你不在时发生了什么」 |

> S3 的「摘要」是**内容域**决定（Claude/数据域），接口域只保证：**若要摘要，必走既有通道 + 禁词扫描 + 零真实 id**（见 §3.7）。

### 3.2 full_snapshot 重发 vs 增量 diff

| 依据 | 内容 | 判读 |
|---|---|---|
| `ws-protocol.md` §2 | 信封只有 `ws_seq`（传输序号，**WS 端点维护**） | 唯一在协议面存在的序号，**跨连接不连续**、**不表达世界位置** ⇒ 不能当 diff 游标 |
| `ws-protocol.md` §5 + `versioning.md` §8-2 | `tick`/`seed`/`seq`/`branch_id` 一律禁出网关 | 真游标不可用 |
| `ws.py:122-130` | `_rtoken = "rt-" + sha256(entity_id)[:12]` | rtoken **稳定派生** ⇒ 可作实体级 diff 键，但**不是世界位置游标**（见 §3.3） |
| `anchors-api.md` §0 | 保守口径：即便 §11 只禁戏内，**戏外也取零原始世界数值** | 连「用 anchor 的 seq 当游标」都被既有裁决排除 |

**结论（D-7）**：M5 的重同步**一律走全量 `full_snapshot`**（现状即是，`sync_request`/`load_anchor` 都回它）。增量 diff 若未来确有需求（50 NPC × 长离线期的带宽），必须先引入**不透明 `catchup_token`**（服务端签发、跨连接有效、**不含 tick/seq/branch 语义可推性**），随 `full_snapshot` 下发、随 `sync_request` 回传——**在 Claude 裁「M5 是否需要 diff」之前，不预留字段**（预留即 schema 债）。

### 3.3 rtoken 语义：稳定 ≠ 身份 ≠ 跨分支连续性

- **实现**：`sha256(entity_id)[:12]`，同一 `entity_id` 永远同一 rtoken，**跨连接、跨分支都不变**（`ws.py:122-130`）。
- **文档（本稿发现时的原文）**：`versioning.md` §8-1 写「rtoken 连接生命周期内有效、不可反查游戏状态、**重连由 full_snapshot 重分配**」⇒ **与实现相悖**（G-8）。**该处已按裁 21-A 订正**（M5-K2）。
- **分叉下的含义**：读档分叉后，同一个 `rt_xxxx`（同一个陈默）在两条分支上**位置/状态/关系可能完全不同**。前端若拿 rtoken 做「增量合并」或「身份连续性」推断，会把两条时间线**焊死**。

**kilo 主张（D-8）** — **✅ 已裁 21-A（2026-09-27）：采①「文档订正、实现不动」，本稿措辞即终裁口径，M5-K2 已落地**：

1. **保持稳定派生**（不改实现）——rtoken 稳定对渲染缓存/精灵复用/前端 diff 有利；
2. **在 `ws-protocol.md` §5 明文三句**：rtoken ≠ 身份标识，≠ 跨分支连续性，**分叉/读档后必重发全量**（已落，并附「口径订正记录」小节留痕）；
3. **订正 `versioning.md` §8-1 措辞**——「重连由 full_snapshot 重分配」→「重连恒以 `full_snapshot` 重建前端状态，rtoken 本身稳定不变」（已落；§7 加注「版本号不变」、§8 加第 4 条裁决记录）；
4. **附带**：`RToken.description` 同一口径错误经生成管线同步（`openapi_ext.py` → `shared/openapi.json` → `shared/protocol.ts`），**协议形态零变更**；`ws-message-diff.md` 加一行「本文为 M2-K3 时点记录」提示；`sim/tests/test_m2_openapi_rework.py::test_rtoken_opaque_shape` 补口径断言做钉子。

### 3.4 「世界已分叉」的告知载体

`branch_id` 绝不出网关 ⇒ 分叉**不能**以「分支 id 变了」告知。三案：

| 案 | 形 | 优点 | 缺点 |
|---|---|---|---|
| A **新增 S→C session 消息**（推荐） | 读档成功后随 `full_snapshot` 之后发一帧「世界已换了一条时间线」的告知（叙事化措辞 + 叙事化时间标签 + 当前刻度，见 D-5 合并帧） | 语义显式；前端可做「回到过去」的表现层；不进 render 通道不污染渲染态 | +1 消息（minor 升级，旧 client 静默忽略） |
| B 塞 `full_snapshot` 可选键 | 加 `world?: {story_label, ...}` | 零新消息 | `full_snapshot` 是 render 通道 + `additionalProperties:false`；把「叙事化时间标签」塞进渲染快照会**污染 render-only 边界**（`ws-protocol.md` §4.1 标注 `[render-only]`） |
| C 纯 HTTP | 前端读 `GET /api/anchors` 判断 | 零 WS 改动 | 无推送语义（读档是 WS 触发，HTTP 轮询有竞态与延迟）；且**分叉这件事本身发生在 WS 会话里**，HTTP 无法表达「刚才那次读档分叉了」 |

**kilo 主张（D-6）**：采**案 A**，且与 D-5 的连接期初值**合并为一帧**（一次新增解决两个缺口）。铁律：该帧**只含叙事化措辞与叙事化时间**，**零 branch/seq/tick/seed**（§3.7 逐项自检表）。

### 3.5 玩家档游标在协议面的呈现

- **已定**：`anchors-api.md` §1.1 —— 列表项 `{id, name, story_label, created_at, protected}`；`story_label` 叙事化（"第二日 · 清晨 · 雨刚停"），构造期未就绪降级空串；**不回传** `branch_id`/`tick`/`seq`/`agent_override`。
- **缺口**：前端**不知道「我现在在哪」**——没有「当前所在游标/分支」的只读面。玩家视角的表现是：读档后不知道回到哪一段、不知道当前世界时间。
- **kilo 主张（D-9）**：
  - 「当前游标」只读面走**戏外 HTTP**（`GET /api/anchors/current` 之类，K1 文档未定义 ⇒ **需 Claude 裁是否新增路由**），字段同 `AnchorListItem` 口径（`story_label` + `name` + `updated_at`），**零原始数值**；
  - **WS 侧不承载**「当前游标」查询（避免同一事实两个真相源）；WS 只在**事件发生时**（读档成功/世界推进完成）以 D-6 的告知帧携带一次叙事化标签。

### 3.6 M5 预计新增 schema 面（**只列清单，不定义**）

> 本节仅登记「将来要进 `openapi_ext.py` 的东西」与依赖关系。**字段名/形状一律待施工时定稿**，本稿不写 schema（零 schema 门禁）。

| # | 候选面 | 通道/方向 | 用途 | 依赖 | 备注 |
|---|---|---|---|---|---|
| S1 | `rate_change`（预留） | control / S→C | 服务端单方面改刻度的告知 | D-4 | 仅在服务端单方面改速时落地；否则**不建** |
| S2 | 连接期状态帧（刻度 + 游标叙事标签 + 能力集） | session / S→C | 重连后前端恢复「世界此刻的样子」 | D-5 + D-6 | 与 S3 合并成一帧 |
| S3 | 分叉/时间线切换告知 | session / S→C | 「世界已换了一条时间线」的叙事化告知 | D-6 | 读档成功后紧随 `full_snapshot` |
| S4 | 长跨度推进（`fast_forward`）请求 | control / C→S | 玩家侧快进到叙事化时间点 | D-2 | 仅当 D-1 裁「玩家侧快进」 |
| S5 | 推进进度/完成帧 | control 或 session / S→C | 推进期间的最小可感知反馈 | S4 | 措辞须过禁词扫描（§3.7） |
| S6 | 离线归来摘要帧 | narrative 或 session / S→C | 「你不在时发生了什么」的叙事化摘要 | S3 + 内容域裁决 | **内容域未定前不预留字段** |
| S7 | `catchup_token` | session / 双向 | 增量 diff 游标（若未来要 diff） | D-7 | **不预留**；等 Claude 裁 |
| S8 | `GET /api/anchors/current` 响应项 | HTTP | 「当前在哪」的戏外只读面 | D-9 | HTTP 路由，字段同 `AnchorListItem` |

> 「能力集」= 客户端可问「服务端支持哪些可选帧」的布尔位集（`versioning.md` §2 协商的延伸）。**可选项**：M5 不做也能活（前端按未知 type 静默忽略即可，§2.5 铁律）⇒ 列为**最后才做**的一项。

### 3.7 出戏边界自检表（M5 新增面逐项过）

| 面 | 禁入字段 | 措辞约束 |
|---|---|---|
| 全部 WS 帧 | `branch_id` / `tick` / `seed` / `seq` / `entity_id` / `source_id` / 真实 `anchor_id` 以外的内部 id | —— |
| render 通道 | 一切叙事文本（`[render-only]` 边界，`ws-protocol.md` §4.1） | —— |
| narrative 通道（进 Agent 感知） | 一切数值与系统词 | **必须过 `banned_words.scan()`**：`BANNED_WORDS_META`（含 `玩家`/`游戏`/`tick`/`模型`）+ `BANNED_WORDS_PERSIST`（`分支`/`branch`/`重放`/`快照`/`回放`/`abandoned`）+ 数值字段模式（`sim/llm/prompts/banned_words.py:27-69`） |
| session/control 通道（戏外 meta shell） | 原始 `tick`/`seq`/`branch_id` 仍禁（`anchors-api.md` §0 保守口径）；但**禁词不适用**（戏外允许「存档管理」字样，DESIGN §2 C3） | 分叉告知措辞走**戏外**：可以说「回到之前那段日子」，但**不得出现** `tick 86400` 这类原始数值 |

> 注意 `REWRITE_MAP`（`banned_words.py:93-103`）：`分支→岔路`、`快照→留影`、`回放→复述`。若分叉告知最终**走 narrative 通道**（S6 摘要），这些替换词面就是 sim 侧的默认改写路径——但**改写后仍须复扫**，且**协议面不得替 sim 决定措辞**（禁词治理归安规域 codex）。

### 3.8 本块待裁

| # | 待裁 | 选项 | kilo 建议 | 影响面 |
|---|---|---|---|---|
| D-6 | 分叉告知载体 | ①新增 session 帧 ②塞 `full_snapshot` 可选键 ③纯 HTTP | ①（与 D-5 合并成一帧） | WS 消息集合 +1；render 边界零污染 |
| D-7 | 重同步走全量还是增量 | ①全量 ②diff+不透明 token | ①（②需先裁带宽需求） | 前端重连/读档路径 |
| D-8 | rtoken 跨连接/跨分叉口径 | ①文档订正、实现不动 ②改成每连接重分配 | **✅ 已裁 21-A 采①**（K2 已落） | `ws-protocol.md` §5 + `versioning.md` §7/§8 措辞 + `RToken.description` |
| D-9 | 「当前游标」只读面 | ①新增 HTTP 路由 ②WS 承载 ③不做 | ① | `anchors-api.md` 增路由（Claude 域施工） |

---

## 4. 块三：生成管线不变量 + `openapi_ext` 注组件清单

### 4.1 五步管线与三条铁律

```
1. 定契约（ws-protocol.md / anchors-api.md 字段级）
2. 写注入源：sim/api/openapi_ext.py 的 _SUB_SCHEMAS / _WS_SCHEMAS / _TYPE_OF / WsMessage 联合
3. 同步快照：shared/openapi.json（与注入源逐字段相等）—— 生成管线唯一真相源
4. 生成：npm run gen:protocol（cd client）→ shared/protocol.ts（**永不手写**）
5. 钉子：sim/tests 侧 schema/帧断言 + client/src/net/__tests__/protocol-types.test.ts 类型断言
```

**铁律**

1. **双处同步**：改 schema 必须 `openapi_ext.py` **与** `shared/openapi.json` 逐字段相等（钉子：`TestPlanDeltaSchema::test_ext_source_matches_snapshot`）。
2. **禁手写 `protocol.ts`**（m4-plan 批次 C 铁律）。
3. **测试 import 顺序**：测试里 import `openapi_ext` **必须先** `import sim.api.main`，否则 circular import（`openapi_ext` → `main` → `openapi_ext`）。

### 4.2 「哪些字段将来进 `openapi_ext` 注组件」清单

| 候选字段 | 目标 schema | 所属消息 | 归类 | 备注 |
|---|---|---|---|---|
| `action: "fast_forward"` | `SetControlMessage.action` 枚举 | C→S | **扩枚举**（非新消息） | 仅当 D-2 采案 B；同一枚举改动连带 `clock.ALLOWED_SPEEDS` |
| 推进目标（叙事化时间点） | `SetControlMessage` 新可选键 | C→S | 新字段（minor） | 形状待定；禁原始 tick |
| `rate_change` 全字段 | **新子 schema** + **新 WS 消息** | S→C | 新增（minor） | §3.6 S1；预留不建 |
| 连接期刻度（`speed`/`paused`） | 新子 schema（建议 `ClockState`）+ 新 WS 消息 | S→C | 新增（minor） | §3.6 S2；与分叉告知合并 |
| 分叉/时间线切换告知（`story_label` 类） | 新子 schema（建议 `TimelineNotice`） | S→C | 新增（minor） | §3.6 S3；零 branch/seq |
| `catchup_token` | 新子 schema | 双向 | **不预留** | §3.6 S7；等 D-7 裁 |
| 推进进度/完成 | 新子 schema（或并入 S2 帧） | S→C | 新增（minor） | §3.6 S5 |
| 离线归来摘要 | narrative 新子 schema | S→C | **不预留** | §3.6 S6；内容域未定 |
| `GET /api/anchors/current` 响应项 | 复用 `AnchorListItem` | HTTP | 复用既有组件 | §3.6 S8；**零新组件** |
| （既有）`plan` | `PlanDelta` + `StateDeltaMessage.plan` | S→C | 已落地 | K10，勿重复定义 |

### 4.3 施工前必须清的既有债（本稿只登记）

| # | 债 | 位置 | 归属 |
|---|---|---|---|
| G-1/G-2/G-3 | 暂停/resume 三宗语义缺陷（含协议违约 `speed:0`） | `ws.py:410-457` | 我域提案、Claude 域施工 |
| G-4 | `_PRE_PAUSE_SPEED` 模块级全局 | `ws.py:452` | 同上（方案 ① 顺带清） |
| G-5 | `timescale` 零广播 | `sim/api/` | Claude 域（`run_world_driver` 接线） |
| G-7 | 无连接期刻度/游标初值面 | `ws.py:340-349` | 随 D-5/D-6 落地 |
| G-8 | ~~`versioning.md` §8-1 措辞与实现相悖~~ | —— | **✅ 已清**（M5-K2：裁 21-A 采①，`ws-protocol.md` §5 / `versioning.md` §7+§8-1+§8-4 / `ws-message-diff.md` 头注 / `RToken.description` 经管线同步） |
| 旧债 | `openapi_ext.py:17`「anchors 不施工」注释 + 测试 `ADDED_SCHEMAS` 白名单两处 M2-K3 遗留注释 | `openapi_ext.py` | 待 M5 锚点路由落地时改（Claude 域文件） |

### 4.4 验收命令（M5 任何协议面改动后必跑）

```bash
cd client
node ../tools/gen-protocol.ts --check     # 漂移闸：生成物 ≡ 快照
npm run typecheck && npm run lint && npm run test && npm run build
cd .. && uv run pytest -m "not bench"     # 全量功能面
uv run pytest sim/tests/test_ws_gateway.py sim/tests/test_m5_plan_delta.py
```

---

## 5. 待裁清单汇总（交 Claude）

| # | 待裁 | 选项 | kilo 建议 | 阻塞谁 |
|---|---|---|---|---|
| D-1 | M5「时间刻度」语义归属 | ①玩家快进/变速 ②世界日历内容 ③两者 | ① | 整块 §2；②成立则本块零改动 |
| D-2 | 是否扩 `speed` 枚举 | ①不扩+新 action ②扩到 64 ③两者都不 | ③→D-1=① 时采① | `clock` / `ControlAckMessage` / client 三处 |
| D-3 | 暂停语义 | ①幂等单值 ②有界栈 ③暂停禁变速 | ① | `ws.py` 施工 + G-1~G-4 |
| D-4 | 刻度广播 | ①不新增 ②扩 `timescale` ③新增 `rate_change` | ①现（M5 不触发）+ ③登记预留 | WS 消息集合 |
| D-5 | 连接期刻度/游标初值 | ①扩 `hello_ack` ②新 session 首帧 | ②（与 D-6 合并） | 前端重连恢复 |
| D-6 | 分叉告知载体 | ①新 session 帧 ②`full_snapshot` 可选键 ③纯 HTTP | ① | 读档 UI |
| D-7 | 重同步全量 vs diff | ①全量 ②diff+不透明 token | ① | 前端重连/读档路径 |
| D-8 | rtoken 口径 | ①文档订正、实现不动 ②改实现 | **✅ 已裁 21-A 采①**（M5-K2 已落） | 文档两处措辞 + `RToken.description`（形态零变更） |
| D-9 | 「当前游标」只读面 | ①新增 HTTP 路由 ②WS 承载 ③不做 | ① | `anchors-api.md` 增路由 |

**裁 D-1 之前，§2 的其余提案都只是「若」**；建议先裁 D-1，再一次性裁 D-2~D-5。

---

## 6. 不在本稿范围

- **分叉本体实现**（定位→快照→重放→新分支→旧分支 abandoned）：架构/数据域（Claude + opencode），本稿只登记 G-6。
- **`load_anchor` driver 化**（`_ANCHOR_LOAD_HOOK` 生产注册方、`run_world_driver` 接管广播路径）：Claude 域（K6 提案 §8.9 部署债 #2）。
- **内容域决定**：离线归来摘要说什么、推进过程中世界发生什么。
- **安规面**：任何新增 narrative 措辞的词表治理归 codex（改 `banned_words.py` 走 CR）。
- **性能域**：单帧 tick 预算、扩档后的背压口径归 pi。
- **施工**：本稿裁完之后，协议面改动一律按 §4.1 五步管线走，**先钉子后生成**。
