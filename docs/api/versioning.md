# 协议版本策略（docs/api/versioning.md）

> 能力域：接口 / 兼容性（kilo） | 对齐 DESIGN.md §4 §17
> 本文为**设计文档**初稿。目标：client 与 sim 能独立演进，不因一侧升级而互相破坏。

## 1. 版本号模型

采用 **major.minor**（不带 patch；协议层无实现缺陷语义，缺陷修复不改变协议形态）。

- **major**：不兼容变更——字段删除 / 改名 / 语义反转 / 消息行为改变。major 不一致 = 必须协商，协商失败即拒绝连接。
- **minor**：兼容增量——新增可选字段 / 新增消息类型。minor 升级对旧端**透明**（旧端忽略未知字段与未知 type）。
- 当前基线：`v = 1.14`（信封 `v` 字段，见 ws-protocol.md §2）。

> 信封里的 `v` 在协商后全程不变，等于协商选定的 major.minor。

## 2. WS 协商流程（connect-time）

```
client ──hello──► { "client_versions": ["1.0","1.1"], "client_build": "0.1.0" }
                            │
sim: 取交集最高 → 选定 v
                            ▼
client ◄──hello_ack── { "v": "1.1", "server_versions": ["1.0","1.1"], "server_build": "0.1.0" }
                            │
                  全程以 v=1.1 收发
                            ▼
（协商失败） client ◄── error{code:VERSION_MISMATCH} + 关闭连接
```

- `hello` / `hello_ack` 走 control 通道，是连接建立后首帧。
- 服务端默认**向后兼容至少一个 major**（即旧 major 仍可连），降低单端独立部署时的断裂面。

## 3. 兼容性规则（保证独立演进）

| 变更类型 | 归类 | 旧 client 行为 | 旧 sim 行为 |
|---|---|---|---|
| 新增可选字段 | minor | 忽略未知字段（`state_delta` 多一个字段不影响渲染） | — |
| 新增消息 type | minor | 收到未知 type → 忽略 + 仅开发模式记日志（不崩溃、不出戏） | — |
| 字段删除 / 改名 | major | 协商阶段即发现 major 不一致 | — |
| 语义反转 | major | 同上 | — |

**核心铁律：client 永不因收到未知 type/字段而崩溃或出戏。** 这是 sim 升级先于 client 部署（或反之）时不破坏体验的保证——未知消息静默忽略，渲染照常。

## 4. HTTP 版本

- 当前单用户本地部署、无外部消费者：HTTP 端点**不引入 URL 版本前缀**（保持 `/api/...`），用 OpenAPI schema 变更 + 重新生成 `shared/protocol.ts` 管控。
- 预留策略：若未来出现外部消费者，引入 `/api/v2/...` 路径前缀；旧路径保留一个里程碑周期。本初稿不实施，仅记预案。

## 5. 版本与生成物的联动（见 codegen.md）

- 改 WS 消息集合或字段 → 先定 minor/major → 更新 sim pydantic 模型 → 重新生成 `shared/protocol.ts`。
- 在 `shared/openapi.json` 的 `info.version` 与 WS 信封 `v` 双处记录版本；CI 漂移闸（codegen.md §5）保证生成物与源同步。

## 6. 回放与确定性不受版本影响

- 回放（C4/C5/T2）基于世界事件流与确定性 RNG，与协议版本正交：旧版本回放仍可由新 sim 重放，因为世界真相（事件 seq/branch）独立于对外协议。
- 协议版本只管"对外呈现的字段集合"，不动世界内部因果——这与 §11「seed/tick/seq 不进任何戏内接口」一致：内部真相不随版本外泄。

## 7. 变更登记（随演进追加）

| 版本 | 变更 | 影响端 | 日期 |
|---|---|---|---|
| 1.14 | 逐层挖深：`VoxelEdit.height` 必需，整数 0..3；`voxel.edited` 记录结果高度。挖 3→2 得木、2→1 得石，只有结果高度 1 且 gid 非零才可走；土坎 1→0 得土但仍阻挡，零高度不可再挖。放置仍要求可走目标，按当前高度扣料（高 1 层的可走面扣 earth）。客户端不再按最后动作推算高度；旧无高度事件按分支顺序累计层数，材料账原样保留。 | sim+client | 2026-10-29 |
| 1.13 | V4b 材料分类：静态高度 1/2/3 分别挖得土/石/木，放置消耗目标格对应材料；`VoxelInventory` 保留必需 `earth`，新增可选 `stone`/`wood`，缺省 0，仍为封闭对象。`voxel.edited.material_id` 扩为三材料，旧 earth 事件原样重放；库存仅进 HUD，数量、原因枚举与渲染高度规则不变。 | sim+client | 2026-10-28 |
| 1.13（资产） | 地形改为单一真相源推导（`terrain_class.py`）：可走面 3947 格（原 820 直线带），高度档 0/1/2/3 = 1112/5515/4379/2994。新增「土坎」概念——阻挡但材质为土的格标 h=1，是 earth 的唯一来源（否则放置永久缺料）。协议字段与消息形状不变。 | sim+client | 2026-10-29 |
| 1.12 | V4a 陈默单格挖放：新增 render 通道 `voxel_request`（起手/取消/放置）与 `voxel_state`（挖掘进度/earth 行囊）；`full_snapshot`、`state_delta` 新增可选 `voxel_edits`。旧端忽略新消息/可选字段；事件、材料与分叉历史保留。 | sim+client | 2026-10-24 |
| 1.11 | W6 鉴权闭环：新增本机 `GET /api/ws-token`（来源/Host/回环连接校验，响应不缓存），生产 WS 在 hello 成功前拒绝写命令，客户端先取 token 并发 hello，hello_ack 后才发同步及暂存命令。既有只读接入问候与 sync 保留；hello/hello_ack 仍为会话握手，不加入世界消息联合。 | sim+client | 2026-10-20 |
| 1.10 | 战斗幽灵帧接线：既有 `combat.scale_change` 事件转发为 `timescale`，交换结算投影为既有 `combat_event`；客户端消费战斗态与表现帧，角标使用戏内措辞。沿用既有 schema，不新增世界事件 kind，不改变战斗结算。 | sim+client | 2026-10-20 |
| 1.9 | S4 建造念头加法：`PlayerImpulseMessage.action?: "build"` 与 `target_pos?: [x,y]` 成对提供；坐标为非负整数且地块可施工。仍先过念头扫描、仅生成世界内念头，实际建造由既有决策/执行边界复验到站、资金和地块。动物复用既有 actors[]，生态/语域不新增帧字段。 | sim+client | 2026-10-20 |
| 1.0 | 协议基线（ws-protocol.md 全量消息 + rtoken/时间口径裁决） | client+sim | 2026-09-19 |
| 1.1 | **M5 三个 minor 级变更合入**（逐项 commit 见右侧登记）：① `a149bb9` M5-K3 批次 B——`fast_forward` action（`SetControlMessage.action` 扩枚举）+ `session_state` 首帧（SessionAnchor 游标指针 `name`/`story_label`）+ `GET /api/anchors/current`（末梢档读路径）；② `f7f6e1b` M5-K7——`GET /api/anchors/{anchor_id}` 单档读端点（响应 `AnchorListItem`，五键白名单）+ `state_delta.plan` 字段（**顶层可选数组**）；③ `7dc8d69` M5-K10——`PlanDelta` **封闭 schema** 补齐（裁 19 CRITICAL：`state_delta.plan` 越界冻结，`additionalProperties:false`） | client+sim | 2026-10-03 |
| 1.2 | **批次 E 只读诊断面进协议快照**（M6-K2，commit 见收编落账）：① `GET /api/anchors/{anchor_id}/materialization`（**新增端点**，响应 `AnchorMaterializationStatus{anchor_id, ready, reason?}`，`additionalProperties:false`，三键白名单）；② `openapi_ext` 手工登记该路由的 `400`/`404` Problem 响应（§3.3 坑：`exception_handler` 产出不会自动进 spec）；③ 诊断面**零新字段**：不返世界真相（`seq`/`tick`/`branch_id`）与随机流状态（M-1 递归扫零命中） | client+sim | 2026-10-04 |
| 1.3 | **M7 渲染面加法变更**（`docs/arch/m7-render-art.md` §2.2，随施工 commit 登记）：① `MapChunk.ground_b64`（新增字段，base64(u16 小端、chunk 内行主序)——地面层走 HTTP 静态通道，沿 codex 意见 5 裁决）；② `TimeInfo` 公共子 schema（`{day,hour,minute,phase,is_market_day}` 五键封闭集，`additionalProperties:false`）+ `full_snapshot.time`/`state_delta.time`（必带）与 `session_state.time`（可选）——戏内时钟权威帧（R3），键全为戏内事实非禁键；③ 出站扫描/键白名单测试同步扩键（安全随行评审记录于执行台账） | client+sim | 2026-10-05 |
| 1.4 | **D10 画布可读性加法变更**（心之声去噪 + 头顶名字）：① `Actor.name` / `ActorDelta.name`（新增**可选**字段，`string`，戏内显示名——名字是戏内事实可出站，D8 感知真名（`display_name_of`）同源裁定；`full_snapshot` 装配了显示名映射时携带，未装配缺省；`entity_id` 仍禁出站）；② 出站键白名单钉同步扩键（`test_ws_gateway.py` actor 键集 + `name`）。**纯加法，无既有字段改型**——旧客户端忽略 `name` 不受影响 | client+sim | 2026-10-07 |
| 1.5 | **D12 街谈巷议署名加法变更**：① `MonologueMessage.name`（新增**可选**字段，`string`，说话人戏内名——**仅 bubble**（外在可观察面：路人看见谁在嘟囔，署名不破 W7 字段最小化：无 rtoken/entity_id）；thought（私密面）不带；未装配显示名映射则缺省）；② `state_delta`/`monologue` 帧构造同源（`monologue_events_to_frames` 投影）。**纯加法**——旧客户端忽略 `name` 不受影响 | client+sim | 2026-10-07 |
| 1.6 | **D17 视觉雾（迷雾 B 案）加法变更**：① 新增 `FogState` schema（`revealed: [{cx,cy},…]`，chunk 坐标整数对，`additionalProperties:false`）；② `StateDeltaMessage.fog`（**可选**，仅本帧有新揭示时出现——增量不制造噪声）；③ `FullSnapshotMessage.fog`（**可选**，已揭示全集——重连/读档重同步）。chunk 粒度（16px），零枚举零内部数值（出戏预核 D-10）；机制面 `fog.reveal` 事件既有（裁 40-4 事件即真相），本版只开 WS 投影面。**纯加法**——旧客户端忽略 `fog` 不受影响 | sim+client | 2026-10-08 |
| 1.7 | **批次 E4/E7 建造投影加法变更**：① `state_delta.structures`（**可选**，`StructureDelta[]`——M 面预留 schema 首次生产启用：`{op, rtoken, x, y, phase}`，phase ∈ built/collapsing/rubble；本批只产 `built`——在建工地不投影，完工才画）；② `full_snapshot.structures` 由硬编码 `[]` 换真实投影（空账本=空数组，形不变）；③ 增量过滤（相位无变化不出键——同 plan/fog 手法）。**纯加法**——旧客户端忽略 `structures` 不受影响 | sim+client | 2026-10-09 |
| 1.8 | **迷雾机制移除（减法变更）**：① `full_snapshot.fog` / `state_delta.fog` 两键删除（`FogState` schema 同撤）；② sim 内核不再产 `fog.reveal` 生产事件（事件 kind 与 no-op handler **保留**——C4 历史事件流不可销毁，旧日志重放不炸）；③ 前端 fog 罩渲染全撤。**纯减法**——雾面本就是观察者投影（裁 40-4），删除不影响世界态与重放确定性；旧客户端收不到 fog 键=本来语义。用户裁决 2026-10-12 | sim+client | 2026-10-12 |

> **1.2 升版说明（M6-K2）**：**新增端点 + 新增响应 schema** 属 §3 兼容性表里的 **minor**
> （纯新增，旧客户端不受影响；无 major 语义反转、无既有字段改型）⇒ 只升 minor 位。
> **版本影响面**：① WS 信封 `v` 与前端 `net/ws.ts` 常量**一并升到 1.2**（单一版本号语义：
> §5「双处记录」；跨树钉 `test_protocol_version.py` 锁两处相等）；② HTTP 侧**不引入 URL 版本前缀**
> （§4 现行口径：单用户本地部署无外部消费者，用 schema 变更 + 重新生成管控），
> 前端的可见变化是 `shared/protocol.ts` **新增** `getAnchorMaterialization` 操作与
> `AnchorMaterializationStatus` 类型（**纯新增，无既有类型改型**）。
> **这次补登记的债**：该端点自 A11 落地起就**不在快照里**（live↔快照漂移，而
> `gen-protocol --check` 只校「生成物↔快照」、不校「live↔快照」，故一直不红）；
> M6-K1 钉出、M6-K2 补齐，并把 live↔快照对拍钉与 K11 路由面钉一起修成真保证。

> **1.1 升版说明（裁 34-1 甲案）**：三个变更均为 **minor**（新增可选 action / 新增可选字段 / 新增端点与响应模型；**无 major 语义反转、无既有字段改型**），故只升 minor 位。
> **零物理快照变更**：本次升版**不动** `shared/openapi.json` 与 `shared/protocol.ts` 的任何字段
> （那三个变更在 1.0 期间就已随各自的 commit 落进快照），本次只补**登记**与**信封版本号**
> ⇒ `gen-protocol --check` 保持 EXIT 0。
> **版本号两落点**：真相源 = `sim/api/ws.py::_PROTOCOL_VERSION`；前端 `client/src/net/ws.ts::PROTOCOL_VERSION`
> 是第二落点，**必须逐字相等**（历史上漂移过一次），现由 `sim/tests/test_protocol_version.py` 的
> 跨树钉 + §7 登记同步钉（防回退、防硬写 `v` 字面量）锁死。
> **已知缺口**：`shared/openapi.json` 的 `info.version` 仍是 FastAPI 默认 `1.0.0`——§5 说「双处记录」，
> 但 HTTP 侧**未接同源常量**（接它要改 `main.py` 的 app `version=` 并改快照，不属本轮）⇒
> 只断言 major 一致，待办登记在 `sim/tests/test_protocol_version.py` 文件末尾。

> 2026-09-27（裁 21-A / M5-K2）：rtoken 生命周期口径**文档订正**，**协议形态与版本号均不变**（仅 `RToken.description` 描述文字修订，走 §5 生成管线），见 §8-4。

## 8. 已批裁决记录（Claude 评审 TASK-001，2026-09-19）

1. **rtoken 口径**：render 通道用 `rtoken`（不透明渲染替身）替代内部 `entity_id`。服务端维护 `rtoken ↔ 内部 id` 映射表（属世界真相，留在 sim）；前端只接触 `rtoken`，永不接触真实 id。`rtoken` 由 sim **稳定派生**（同一实体恒得同一 rtoken，**跨连接、跨分支均不变**）、不可反查游戏状态。**重连时以 `full_snapshot` 全量重建的是前端状态，不是 rtoken 本身**；rtoken 既非身份标识、也非跨分支连续性（读档分叉后同一 rtoken 可指不同状态 ⇒ 分叉/重连后必重发全量）。细则与前端三条推论见 `ws-protocol.md` §5。与 C3/C10 对齐。**（口径订正：早期版本写「连接生命周期内有效、重连由 full_snapshot 重分配」，与实现相悖；裁 21-A / M5-K2 定为「稳定派生 + 全量重建前端状态」，实现不动。）**
2. **时间口径**：信封用 `ws_seq`（传输层单调计数，仅丢帧/乱序检测），**不是世界 tick**。世界 `tick`/`seed`/事件 `seq` 一律不进任何 WS 载荷（§11）。anchor 戏外元数据用叙事化 `story_label`，不回传原始 `tick`/`seq`（比 §11 更保守，已批）。
3. **WS schema 进 OpenAPI**：WS 消息与 HTTP 端点共用同一 OpenAPI（`components/schemas`），经 `openapi-typescript` 生成单一生成物 `shared/protocol.ts`；前端 `net/protocol.ts` 一个 re-export 拿全。FastAPI 端 WS 路由复用同一 pydantic 模型（落地由 Claude 架构域 + cline 配置域；codegen 脚本由 kilo）。
4. **rtoken 跨连接 / 跨分叉口径**（**裁 21-A / M5-K2**，2026-09-27，评审 Claude；提案见 `m5-prestudy-timescale-and-fork.md` §3.3 G-8/D-8）：§8-1 的「连接生命周期内有效、重连由 `full_snapshot` 重分配」**与实现相悖**——实现是 `ws.py::_rtoken` = `sha256(entity_id)[:12]` **稳定派生**（跨连接、跨分支恒定）。**定口径：实现不动、文档订正**为「稳定派生；rtoken 不等于身份标识、不等于跨分支连续性；分叉/重连后必重发全量 `full_snapshot`——重建的是前端状态而非 rtoken」。schema `RToken.description` 经生成管线同步落进 `shared/protocol.ts`；**协议形态与版本号不变**。

> 上述裁决已落进 `shared/openapi.json`（mock）与 `tools/gen-protocol.ts`、`client/src/net/protocol.ts`，并被类型断言单测守护（`client/src/net/__tests__/protocol-types.test.ts`）。

## 9. 不在本文件范围

- 消息字段定义 → `ws-protocol.md`；HTTP 端点 → `openapi.md`；生成管线 → `codegen.md`。
- 回放/确定性内部机制 → 架构域（Claude）+ 测试域。
