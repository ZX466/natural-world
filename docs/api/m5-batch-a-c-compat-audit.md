# M5 批次 A/C 接口兼容审计：批次 A 出站对账 + CRUD v2 实施清单 + 0009 rng_state 边界

> 能力域：接口 / 兼容性（kilo） | 状态：**审计稿（提案制），零代码零 schema 改动**
> 派单：Claude 主树 `.orca/talking.txt`「M5-K5」（2026-09-29）
> 门禁：只动 `docs/api/`；`prettier` 过；审计脚本**一次性、不入库**（跑在 `C:\Users\...\Temp\kilo\`，用完即弃）。
> 依据：裁 27 §B（种子 b2 采 `branches.rng_state`）/ §C（D-10 权力完全不可见＝协议零新增；D-14 `/current` 保底；D-15 摘除）；K3 四面（main `9f0852f`）；K4 预研（`m5-batch-c-prestudy-authority.md`）；`anchors-api.md` §1.0/§1.4/§3.2/§5/§6；`versioning.md` §3 兼容三档。

---

## 0. 速览

**审计结论六条**

1. **批次 A 出站 24 个实发样本全部合规**：实发键 ⊆ schema 属性、`type`/`channel` ∈ 枚举、必填键齐全、**零原始 `tick`/`seq`/`branch_id`/`entity_id`/`seed`**（`ws_seq`/`v` 按 §2/§1.7 明记非世界真相，列入白名单）。HTTP 六端点同样零禁键。
2. **🔴 缺口 GAP-A（迁移号撞车，本轮最高价值发现）**：`0008` 第 9 项已落 `player_anchors.protected`（`NOT NULL server_default=0`），而**裁 27-B 已把 0009 预定给 `branches.rng_state`**。我方 CRUD 回填迁移若也取 0009 → **迁移链分叉**。⇒ 回填迁移须取 **0010**（或与 opencode 让号）。
3. **🔴 缺口 GAP-B（回填是强制项，不是建议）**：因为 0008 给存量行的 `protected` 是 `0`，**只要 CRUD 落地而回填未做，全表 `protected=false`** ⇒ DELETE 末梢的 409 保险丝**静默失效**（数据不丢，保险丝没了）。这正是「无写入方暂不切列」的实质原因，现在有了可证伪的机理。
4. **旧客户端兼容三档全部安全**：K3 的四项变更分别落在「扩枚举 / 加可选键 / 加新 type / 加新路径」四档；旧 client 对未知 `type` 的行为**有实现级证据**（`client/src/net/ws.ts:99-101` 的 `default:` 静默忽略）。
5. **⚠ GAP-C（前端欠账，非协议违约）**：客户端 `dispatch()` 只处理 `full_snapshot`/`state_delta`，其余（含 K3 新增的 `session_state` 与全部 `control_ack`/`monologue`）**一律进 `default:` 忽略** ⇒ K3 协议面合规但**前端零消费**。归属前端域（Claude），不阻塞协议面，但 M5 验收「刻度面板/读档 UI」落地时必须先补。
6. **0009 `rng_state` 的协议边界已用数据证明**：快照与生成物中 `rng_state`/`branches`/`forked_from`/`abandoned` **出现 0 次**；`branch_id` 仅 1 次且在 `info.description` 的**边界声明散文**里（生成物 0 次）；`seed` 3 次全在 description/summary 散文。⇒ **落 0009 不需要改 `shared/protocol.ts`，也不需要动 `openapi_ext`**（理由链见 §4）。

**缺口登记（GAP-A ~ GAP-D）与待施工清单见 §5**；锚点 CRUD 实施清单见 §3（分「Claude 施工」与「我域 API 契约」两列，归属逐条写明）。

---

## 1. 审计方法与可信度声明

**做法**：写一次性脚本（不入库），加载 `shared/openapi.json` 快照后：

1. 实例化真实构造器（`snapshot_payload` / `delta_payload` / `monologue_events_to_frames` / `_control_ack` / `session_state_payload` / `fast_forward_done_frames` / `_error_frame`），逐帧对拍：键集 ⊆ schema 属性、`type`/`channel` ∈ 枚举、`required` 齐全；
2. 递归扫描禁键（`tick`/`seq`/`branch_id`/`entity_id`/`source_id`/`seed`/`rng_state`/`agent_override`/`updated_at`…）与禁值词；
3. 用 `TestClient`（`SIM_DB_PATH` 指临时目录，**不落仓库**）实打 6 个 HTTP 端点做同样两查；
4. 统计快照/生成物中 `rng_state`/`branch_id`/`seed` 等词的出现次数与**原文语境**（区分「数据字段」与「描述散文」）；
5. 另跑一次 **type 发射点普查**（`sim/api/*.py` 内各 WS type 字面量出现处），补上第 1 步的盲区。

**可信度与盲区（必须声明）**：

- ✅ 能证明：**已注册构造器产出的帧**合规、HTTP 响应体合规、快照/生成物文本层边界。
- ❌ 不能证明：**「没有任何未注册的构造器」**——第 1 步只覆盖我实例化的构造器。第 5 步的发射点普查是为此补的，但它仍是**字面量级**启发（若某处用变量拼 type 会漏）。
- ⚠ 误报白名单：`full_snapshot` 这个 **type 值本身**含 "snapshot" 一词，脚本已把协议 type 值列入白名单（协议词汇≠内容泄漏）。同理 `ws_seq`/`v` 不算世界真相（`ws-protocol` §2/§1.7）。

---

## 2. 块一：批次 A 协议面现行契约对账

### 2.1 实发项 ⊆ schema（24 样本，全 OK）

| 面 | 样本（实发构造器 × 变体） | 结果 |
|---|---|---|
| render | `full_snapshot`（快进完成帧同形） | OK |
| render | `state_delta`（含 `plan` 的 K10 形状） | OK |
| narrative | `monologue` × 3 form（bubble/thought/plan） | OK ×3 |
| control | `control_ack` × 4（pause 无 speed / pause+paused / resume / set_speed） | OK ×4 |
| control | 快进完成帧 `control_ack{action:"fast_forward"}` | OK |
| control | `timescale`（**手工构造**——无发射点，见 GAP-D） | OK（形状合规 ≠ 有实现） |
| session | `session_state` × 2（有游标+notice / 空游标） | OK ×2 |
| error | 全词表 11 码逐个 | OK ×11 |

判据：键集 ⊆ 属性、`type`/`channel` ∈ 枚举、`required` 全齐、零禁键、零禁值词。**结论：批次 A（K3）协议面零违规。**

### 2.2 零原始数值（出戏边界）

| 项 | 结果 | 依据 |
|---|---|---|
| `tick` / `seq` / `branch_id` / `entity_id` / `seed` / `source_id` | **0 次**（WS 24 样本 + HTTP 6 端点） | `ws-protocol` §5 禁出表 |
| `ws_seq` / `v` | 出现（**白名单**） | §2 = 传输序号；§1.7 = 协议版本。两者非世界真相，schema 内明记 |
| `agent_override` / `updated_at` | **0 次**（HTTP anchors 三响应确认） | `anchors-api` §0 保守口径：戏外也取零原始数值 |
| `rtoken` | 出现于 render 面（预期内） | K3 之前既有；裁 21-A 口径＝稳定派生替身（`versioning` §8-1） |

### 2.3 旧客户端兼容三档（K3 四项变更逐项定档）

| 变更 | 兼容档（`versioning` §3） | 旧 sim + 新 client | 新 sim + 旧 client | 证据 |
|---|---|---|---|---|
| `set_control.action += fast_forward` | **扩枚举** | 新 client 发给旧 sim → `error{bad_action}`（可恢复，玩家见「不知道要怎么调」） | 旧 client 不发该值 → 无感 | `ws-dispatch-proposal` §1.4 |
| `SetControlMessage += advance_hours` | **加可选键** | 旧 sim 忽略未知键（action 未知先被拒） | 不发 → 无感 | 快照 `SetControlMessage` |
| `ControlAckMessage` 增 `fast_forward` + 可选 `paused` | **扩枚举 + 加可选键** | —— | 旧 client 的 ack 消费者若对 `action` 穷举且无 default，运行时会落空分支（**当前无此类消费者**：ack 全进 `ws.ts` 的 `default:`，见 GAP-C） | `ws.ts:86-102` |
| 新消息 `session_state` | **加新 type** | —— | **静默忽略**（`default:` 分支有实现级注释「未知类型/戏外未实现消息：静默忽略」） | `ws.ts:99-101` |
| `WsMessage` 联合 14→15 | **加新 type** | 旧 client 重新生成类型后多一成员 | 未重新生成则运行时无感（前端不校验 JSON） | 快照联合 + `protocol-types.test.ts` K04 #1 |
| `GET /api/anchors/current` | **加新路径** | 旧 client 不请求 | 旧 client 无此调用 → 无感 | 快照 `paths` |

> 判读：**四档全部落在 minor 兼容内**；唯一的「非零反馈」是新 client 对旧 sim 发 `fast_forward` 得到 `bad_action`——这是**设计内的可恢复错误**（快进是新功能，旧 sim 不支持），不是破坏。

### 2.4 缺口登记（只登记，不在本轮修）

| # | 缺口 | 证据 | 归属 | 建议动作 |
|---|---|---|---|---|
| **GAP-C** | 前端 `dispatch()` 只处理 `full_snapshot`/`state_delta`；`session_state`/`control_ack`/`monologue`/`impulse_feedback` **全部进 `default:` 忽略** | `client/src/net/ws.ts:86-102` | 前端域（Claude） | M5 刻度面板/读档 UI 落地前先补 `session_state` 消费；协议面无债 |
| **GAP-D** | `timescale` schema 有、**零发射点**（K9 记的 G-5；本轮普查再次确认 `sim/api` 内该 type 字面量只在 `openapi_ext`） | type 普查：`timescale` 仅 `openapi_ext.py:415/484` | Claude 域（战斗慢镜面接线） | 接线时按「事件先行、帧后投影」；在此之前它是**未触发的 schema**（R1 的已知例外，须在文档登记而非假装已实现） |
| **GAP-E** | `combat_event` schema 有、**零发射点**（`sim/combat/__init__.py` 仅 508 字节桩） | type 普查：`combat_event` 仅 `openapi_ext.py:395/483` | 战斗域（未开工） | 不阻塞 M5；M6/战斗批次开工时接线 |
| **GAP-F** | `perception` 帧**只进 prompt 侧**（`loop.perception_frames` + `main.py:85` `attach_perception`），**不进 WS 广播** | `sim/core/tick.py:40-72`、`main.py:79-86` | 我域（登记） | 这是**有意的不对称**（Agent 靠感知、玩家靠独白），但它在 `WsMessage` 联合里占一个永不发射的成员 ⇒ 需在 `ws-protocol` §3.2 明记「perception 不经 WS 出站」，否则后人会以为漏接 |

---

## 3. 块二：anchors CRUD v2 接口实施清单

> 裁 27-C 已采 D-14（`/current` protected 优先 + 无则回退 `max(updated_at)`）与 D-15（DELETE 同步摘除 `_ANCHOR_IDS`，新增 `unregister_anchor_id`）。本块把它们与 K4 §3.3 的 v2 增量条款落成**可施工清单**，并逐条标归属。

### 3.1 施工项（Claude 域施工 / 我域复验）

| # | 施工项 | 归属 | 契约出处 | 验收断言（可测） |
|---|---|---|---|---|
| S-1 | `sim/api/errors.py`：ProblemDetail 归一 handler + `main.py` 安装 | Claude | `anchors-api` §3.2/§5#3 | 未匹配路由 404 也是 `type/title/status` 形；422 同形 |
| S-2 | 三路由 + pydantic（`AnchorCreate`/`AnchorRename`/`AnchorListItem`，`extra="forbid"`） | Claude | §5#1 | `[O]` operationId 逐字对齐快照；`[T]` 响应五键齐全 |
| S-3 | **回填迁移**（存量 `protected`）——**必须，且必须取 0010**（GAP-A） | Claude/数据域 | 本文 §3.3 | `[T]` 回填后 `protected=true` 行数 = 1（空库 0） |
| S-4 | 读路径切列：`list_items`/`get_item`/`current_item` 读列，删派生分支 | Claude | K4 条款 C1 | `[T]` 断网直改列值后列表与 `/current` 同源变化 |
| S-5 | POST 同事务写 `protected`（清旧 + 写新，§6.1 A2 锁 + A3 事务） | Claude | K4 v2 表 | `[T]` 存两档后恰有 1 档 true |
| S-6 | DELETE 409 **读列**判定 + 硬删 | Claude | K4 v2 表 | `[T]` 删末梢 → 409 `/errors/anchor-protected` |
| S-7 | **`unregister_anchor_id(id)`** 函数 + DELETE 成功调用 | Claude 施工 / **文件在 kilo 域 `sim/api/ws.py`（需知会避免撞车）** | 裁 27-C D-15 | `[T]` 删档后 `load_anchor` 失配回 `load_failed`；`[T]` `register→unregister` 幂等 |
| S-8 | POST 成功 `register_anchor_id(id, name, story_label)`（K7 模式） | Claude | K4 v2 表 | `[T]` 存档后 WS 注册表含该 id + 标签 |
| S-9 | 快照 responses 声明（§5.1 四处注入点；`/current` 的 404 声明 K3 已加） | Claude | §5.1 | `[O]` 三路由 `responses` 键集 ⊇ `{201,400,422}` / `{200,404,422}` / `{204,404,409}` |

**路由顺序**：**本批无新增顺序风险**——K4 §3.2 R-6 的陷阱只在「新增**静态段**路径」时才有（`/current` K3 已前置并留白盒钉）；PATCH/DELETE 与 `/{anchor_id}` **同路径不同方法**，FastAPI 不存在方法间顺序问题。钉子复用 `TestCurrentAnchorRoute::test_route_declared_before_anchor_id_route`（若将来加 `/api/anchors/{id}/xxx` 才需重跑该钉）。

### 3.2 契约项（我域，已交付/待补，不施工）

| # | 契约项 | 状态 | 落点 |
|---|---|---|---|
| C-1 | D-9 `/current` 契约（含路由顺序铁律） | ✅ 已落（K3） | `anchors-api` §1.0 |
| C-2 | K4 的 C1~C4 条款 + CRUD v2 增量表 | ⏳ **待合入正式契约**（K4 稿是提案） | 下一单合入 `anchors-api` §1.2–§1.4 + 新增「切列」小节 |
| C-3 | 摘除后的 `load_anchor` 错误映射 | ✅ 现状即可接受，**登记不新增 code**：删档 id 查表未命中 → `load_failed`（不是 `bad_anchor`——后者语义是「形状非法/缺失」）。文案「这个档读不出来了」成立 | 本文 §3.4 |
| C-4 | `GAP-F`（perception 不出 WS）在 `ws-protocol` §3.2 明记 | ⏳ 待施工单同批 | 建议随 S-1 同单（纯文档一行） |
| C-5 | 协议零新增证据（D-10 闭合后） | ✅ 本文 §2/§4 | — |

### 3.3 🔴 GAP-A：迁移号撞车（必须在施工单开工前解决）

| 事实 | 证据 |
|---|---|
| 最新迁移是 `0008_m5_fork_identity.py` | `sim/core/persistence/alembic/versions/` |
| `0008` 第 9 项**已落** `player_anchors.protected`（`NOT NULL, server_default=0`） | `0008_m5_fork_identity.py:16,79-86` |
| **裁 27-B 把 0009 预定给 `branches.rng_state`**（"一支 add_column 的 0009…0009 随批次 A 开工单落"） | `m5-rulings.md:161-164` |
| ⇒ 我方**回填迁移**若也取 0009 → 两个 `down_revision = 0008` 的 head，**迁移链分叉** | — |

**建议**：①回填迁移取 **0010**（`down_revision` 指向 opencode 实际落地的那个 0009）；或②与 opencode 协调让号（谁先落谁拿 0009，另一方顺延）。**两种都可以，但必须在同一个施工单里写死**，否则 alembic 会在某人的机器上「找不到唯一 head」。

### 3.4 切列后各面行为对照（契约，一句话版）

| 场景 | 切列前（现状） | 切列后（v2 契约） |
|---|---|---|
| 列表 `protected` | 派生（max `updated_at`） | 读列；值脏（多档 true）时如实回多档 true（不隐藏） |
| `/current`（有 protected 行） | max `updated_at` | 该 protected 行 |
| `/current`（**全表无 protected 行**——删末梢后的合法态） | max `updated_at` | **回退 max(`updated_at`)**（D-14 保底，不 404） |
| `load_anchor` 已删档 | 查表命中 → **假成功** | 摘除后查表未命中 → `load_failed`（C-3） |

---

## 4. 块三：0009 `rng_state` 的协议边界与生成管线证据

### 4.1 边界声明（契约级）

`rng_state` 是 `RngRegistry` 快照 + 每流 PCG64 状态的 JSON 包（≈198 B/流，`sim/core/rng_state.py`）。**它是分支级世界真相，与 `seed`/`tick` 同族** ⇒

- **禁令**：`rng_state`（及其内部任一流名、指纹、版本号）**永不进任何 WS 载荷、任何 HTTP 响应、任何 prompt**；与 `ws-protocol` §5 禁出表同列，与 `banned_words` 两套口径同列（戏内 narrative 必过扫描；戏外 session 虽不过词表，但仍禁该列本身）。
- **理由**（不是形式主义）：RNG 状态可**逆向推演抽签序列**——泄漏它等于泄漏「世界的运气从哪一刻起、走过哪些流」。`seed` 已禁（它是同族最小泄露面），`rng_state` 是它的**超集**。
- **落库形态不影响协议面**：`branches.rng_state` 是 **DB 列**（裁 27-B b2），不是 schema。

### 4.2 证据：快照与生成物里 `rng_state` 出现 0 次

| 词 | `shared/openapi.json` | `shared/protocol.ts` | 语境判定 |
|---|---|---|---|
| `rng_state` | **0** | **0** | —— |
| `branches` | **0** | **0** | 无任何分支端点（`paths` 8 条：health / world-map / anchors×3 / settings×4） |
| `forked_from` / `abandoned` | **0** / **0** | **0** / **0** | —— |
| `branch_id` | 1 | **0** | 唯一出现在 `info.description` 的**边界声明散文**（"…出戏边界：tick/seed/seq/branch_id/…永不进…"）；openapi-typescript 不把 `info` 映射进生成物 ⇒ 生成物 0 次 |
| `seed` | 3 | 2 | 三处全是 description/summary 散文：`info.description`（边界声明）、`listAnchors.summary`（「玩家档列表（**不回传**原始 tick/seq/seed」）、`MapChunk.collision_b64.description`（「**不含** seed/tick/entity_id」） |

### 4.3 结论：落 0009 **不需要**改 `shared/protocol.ts`（四步论证）

1. **0009 的全部内容是 `branches` 表加一列**（`branches.rng_state`），不经 `openapi_ext` 注入（那是 HTTP/WS 面）；`branches` 无 HTTP/WS 端点。
2. **生成物输入是快照**（`gen-protocol` 只读 `shared/openapi.json`）⇒ 快照零变化 ⇒ 生成物零变化。**已实跑留痕**：`cd client && node ../tools/gen-protocol.ts --check` → `通过：生成物与提交一致`（K5 轮，HEAD `78ccdf1`；同期 `test_m5_batch_b_schema.py` 17 例绿，含「ext ↔ 快照逐字段相等」判据）。**落地 0009 的一方请在收编时再跑一次留痕**。
3. **双处同步铁律不受影响**：铁律管的是「`openapi_ext` 与快照不得漂」，而 0009 两处都不碰。
4. **协议版本号不变**（`versioning` §7 基线 1.0）：无 schema 变更 ⇒ 无版本位变更。**不需要在 `versioning.md` §7 登记新版本**（若要留痕，写成「DB 迁移，无协议面影响」注记即可）。

### 4.4 未来风险与纪律（若将来给分支/世界线开只读面）

**若**将来要开 `GET /api/branches/{id}`（或 `/api/world/line` 之类），则**那是一次新的协议面**（我域 + 一份 schema 变更），必须：

- 在端点契约里**明写「分支只读面不含 `rng_state`/`seed`/`parent_branch_id`/`forked_from_seq`」**（防后来者 `SELECT *` 顺手回传）；
- 建议的钉子：`GET /api/branches/{id}` 的响应键集 ⊆ 显式白名单（含 `id`/`story_label`/`created_at` 一类叙事化字段），且**递归禁键扫描**含 `rng_state`；
- 顺带注意：`branch_id` 这类**内部标识**一旦进入戏外面，就成了前端可依赖的字段——届时要按「标识 ≠ 身份 ≠ 连续性」口径（K2 的 rtoken 三条推论同源）重新评估。

---

## 5. 缺口与待施工汇总

| # | 内容 | 归属 | 阻塞谁 | 建议动作 |
|---|---|---|---|---|
| **GAP-A** | 迁移号撞车：0009 已被 `branches.rng_state` 预定，我方回填须让号 | Claude/数据域协调 | CRUD 施工单开工 | 同一单里写死「回填 = 0010（或让号）」 |
| **GAP-B** | `protected` 存量回填是**强制**项（0008 默认 0 ⇒ 不回填则 409 保险丝静默失效） | Claude | S-4/S-6 | 切列单必须含回填 + 「true 行数 = 1」断言 |
| GAP-C | 前端零消费 K3 新帧（`session_state` 等全进 `default:`） | 前端域 | M5 刻度面板/读档 UI | UI 落地前先补 `session_state` 消费 |
| GAP-D | `timescale` 零发射（G-5） | Claude | 战斗慢镜 | 接线时事件先行；文档登记为未触发 schema |
| GAP-E | `combat_event` 零发射（战斗域未开工） | 战斗域 | 无 | 不阻塞 M5 |
| GAP-F | `perception` 有意不出 WS，但在联合里占永不发射成员 | 我域（登记） | 无 | `ws-protocol` §3.2 明记一行（建议随 S-1 同单） |
| C-2 | K4 的 C1~C4 + v2 增量表尚未合入 `anchors-api` 正式契约 | 我域 | 施工单开工前 | 下一单合入（本稿不施工） |

---

## 6. 不在本稿范围

- **CRUD 全部施工**（S-1~S-9）：Claude 域；我域复验。
- **0009 `branches.rng_state` 迁移本体**：数据域（opencode/pi 按裁 27-B）。
- **`gen-protocol --check` 的收编前实跑**：建议由落地 0009 的一方留痕（本稿只给论证）。
- **D-10 已闭合的协议面**：裁 27-C 裁「权力完全不可见」⇒ 批次 C **协议零新增**，本文无任何权力相关 schema 建议。
- **前端消费实现**（GAP-C）：前端域。
