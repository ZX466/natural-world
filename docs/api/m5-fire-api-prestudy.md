# M5 批次 D 火灾生态 · API/事件出站面预研（docs/api/m5-fire-api-prestudy.md）

> 能力域：接口 / 兼容性（kilo） | M5-K12 | **预研案（零代码零 schema）**
> **依据链**：DESIGN §14「承重依赖图 → 级联坍塌 → 坍塌范围伤人 + **火灾蔓延（M5）**」
> → `m5-plan.md` 批次 D（蔓延接在 M4 坍塌**之后**；§18 缩范围序：生态=1、火灾蔓延=2）
> → codex 安全预研 `docs/security/m5-security-preplan.md` §10.2 面②（**W-D1/W-D2/W-D3** 已在册）
> → kilo K11（`docs/api/m5-power-api.md`：D-10 三硬边界、出站咽喉闸、**P1–P5 接口要求体例**）
> → 裁 21-C②（不预砍；砍是执行期决定）｜裁 31-2（批次 D+E 合并收尾）。
> **状态**：提案制。**本稿只出案不抢施工**——事件 kind 登记归 opencode 数据面，火势传播语义归 Claude，
> 安规判据归 codex，tick 成本口径归 pi。**所有权**：`docs/api/` 文档 + 自树 memory；
> 本稿对 opencode 的要求以「接口要求清单」（§4）形式给出，收编时由 Claude 对齐。
> **词表纪律**：**零扩散**——本稿不新增任何词面（W-D2 的破坏类题面随语料 CR 走，不预扩）。

## 0. 一句话结论（推荐案）

**新增 3 个 `fire.*` 事件 kind 承载「火势生命周期」，而「烧毁的物质后果」走既有 `structure.collapsed`

- `matter.damage` 族；WS/HTTP 出站面零变更（火光走既有 `lights[].kind`，自由字符串非枚举），
  `shared/` 与 `protocol.ts` 零 diff。**

| 面          | 结论                                                                         | 代价                                            |
| ----------- | ---------------------------------------------------------------------------- | ----------------------------------------------- |
| 事件流      | **新增** `fire.ignited` / `fire.spread` / `fire.extinguished`                | `EventKind` + `PAYLOAD_MODELS` 登记（opencode） |
| 烧毁        | **既有** `structure.collapsed{cause:"damage"}` + `matter.damage`             | **零枚举扩展**                                  |
| WS 帧       | **零新增**（type 集不变）                                                    | 无                                              |
| WS 字段     | **零新增**（`lights[].kind="fire"` + `flicker`；**不扩** `Structure.phase`） | 无                                              |
| HTTP        | **零新路由**                                                                 | 无                                              |
| 快照/生成物 | **零 diff** ⇒ `gen-protocol --check` EXIT 0                                  | 无                                              |

## 1. 事件出站面判定（派单 ①）

### 1.1 四类事件 × 既有族/新 kind 判定表

| 事件                         | 语义                                       | 判定                                                                 | 依据                                                                                                                                                                                                                        |
| ---------------------------- | ------------------------------------------ | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **起火** `fire.ignited`      | 某坐标/构件开始燃烧（火源诞生）            | **新增 kind**                                                        | 既有 19 kind 无「正在燃烧」这一存在性语义：`structure.*` 是**建造生命周期**（started/checkpoint/completed/collapsed/removed），`matter.damage` 是**物质损伤**（不承载火势存在）；`npc.act` 是**动作**（火不是动作）         |
| **蔓延** `fire.spread`       | 火从既有火源传播到新目标（**每目标一次**） | **新增 kind**                                                        | 同上；且 codex **W-D1** 明写「蔓延每一步状态变更必须产事件（`fire.spread` 类新 kind 须登记白名单 + payload 模型）」                                                                                                         |
| **扑灭** `fire.extinguished` | 火源熄灭（火势消失）                       | **新增 kind**                                                        | 熄灭是**火势自身的态变**，不是物质损伤也不是结构移除；塞进既有族会让「为什么灭了」丢失可重放性（T2/C5）                                                                                                                     |
| **烧毁**                     | 燃烧致构件失去承载 → 坍塌/移除；材料被消耗 | **既有族**：`structure.collapsed{cause:"damage"}` ＋ `matter.damage` | codex §10.2 面②末行：「**蔓延必须走 damage/collapse 既有事件族**（payload 域约束 `test_t1_m4_structure_payloads` 52 面已锁）」；守恒折叠器（`fold_matter_snapshot`）只认既有族 ⇒ 自定义烧毁事件会让 T1 材料守恒断言**失配** |

### 1.2 为什么新增 kind 不违反「裁 24 不新增安规面」

- 裁 24 的纪律对象是**安规面**（词表/判层/闸门），不是事件 kind；codex 在 **W-D1** 里已经**指定了
  新 kind 的合法路径**（登记白名单 + payload 模型 + 0006/0007 同款迁移与钉子体例）。
- 事件 kind 是**内部可重放面**，不是出站协议面：它不进 `shared/openapi.json`、不进 `protocol.ts`、
  不进任何 WS 帧 ⇒ **对玩家协议面零影响**（这正是 K11 P3 的口径：「API/WS 侧零投影」）。
- 反向纪律（**新增 kind 的代价清单**，缺一即欠账）：
  1. `PAYLOAD_MODELS` 闭合集登记 + `extra="forbid"` 封闭 payload（既有体例）；
  2. `test_t1_m4_structure_payloads` 同款钉（**kind 白名单 + 事件/payload 等集**）；
  3. **事件预算**（codex **W-D3**）：蔓延**不得 per-tick 产事件**——判据「连续 10 tick 同因事件 > N 即实现偏差」，
     N 由 pi 在定标机定标；我侧只要求口径＝**火势状态变更驱动**（同一火势无变更则零事件）；
  4. **可重放**：新事件必须能被 T2 回放逐位重建（`fire.*` 的状态必须是事件的纯函数投影，
     **禁**任何「只存在于内存的火势」——否则读档回来火就没了，与 C6/离线验收「离线再回来世界已变」冲突）。

### 1.3 payload 形态建议（**归因零字段**，见 §3）

```python
# 建议形态（opencode 登记时照此；字段名可微调，**键的类别不可增**）：
FireIgnitedPayload:  fire_id, x, y                      # 无 actor/intent/cause 归因字段
FireSpreadPayload:   fire_id, x, y, from_x, from_y      # 传播的**几何**，不含「谁点的」
FireExtinguishedPayload: fire_id, x, y, end: Literal["out","fuel_out","doused"]
# end 是**物理终止态**，不是「被谁扑灭」——「doused」只表示火灭了，不记是谁灭的
```

**禁加字段**（泄漏面，见 §3）：`actor_id` / `igniter` / `cause_human` / `culprit` / `authority_*`。

## 2. WS 消息面影响面（派单 ②）——**零变更**三论证（复用 K11 体例）

| 论证           | 内容                                                                                                                                                                                                                                                                                                | 判据/钉                                                                                      |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| **A 零新帧**   | `fire.*` 是**事件流** kind，不是 WS 帧 type。WS 帧构造点（`snapshot_payload`/`delta_payload`/`monologue_payload`/`session_state_payload`）全是**白名单式投影**（逐字段挑 `rtoken/x/y/…`，不是整行透传），**无 fire 投影位** ⇒ 不新增投影点即零新帧                                                  | codex 红线 A①（WS 帧 type 集对拍）保持绿；我的 K11 咽喉钉（`_send_to`）不受影响              |
| **B 零新字段** | 火光的可见表达走**既有** `Light {rtoken,x,y,kind,radius,flicker}`——其中 **`kind` 是自由 `string`（非枚举）** ⇒ `kind="fire"` 落进既有形状即可。**关键反面**：`Structure.phase` 是**枚举** `["built","collapsing","rubble"]`，扩 `"burning"` **就是**一次快照变更 ⇒ 本稿**明确不扩**（见 §5 待裁 3） | `[O]` 快照 `Light.properties.kind` 仍 `{type:string}` 无 enum；`Structure.phase.enum` 仍三项 |
| **C 零新路由** | 玩家不需要读「火势数值」（度数/燃料/蔓延半径属世界真相，出戏边界同 `tick/seq/seed`）⇒ 无读需求即无路由；且全部 `/api` 路由声明 `response_model`，结构密封（K11 §1 论证 3）                                                                                                                          | 快照 `paths` 键集不变；K11 `test_every_http_route_declares_response_model` 保持绿            |

**⇒ 影响面预测**：`shared/openapi.json` **零 diff**、`shared/protocol.ts` **零 diff**
（`gen-protocol --check` EXIT 0），前端零改动。**若将来确要 `phase="burning"`**：
那是 minor 档（扩枚举）——须走 `versioning.md` §7 变更登记 + `openapi_ext` + 快照 + `gen-protocol`
**同提交**，并补前端 `[C]` 键集断言；**不在本稿授权范围**。

## 3. D-10 边界核查（派单 ③）：蔓延会不会间接暴露「谁放任火蔓延」

**一句话安规论证**：火灾本身是**物质/世界事件**、无权力语义；风险只在**归因**——
若蔓延或叙事带上「谁点的火 / 谁本该去救 / 谁有权下令救」这类**意图归因**，就等于把
**权力位阶与知情义务**投影到出站面，正是 D-10 禁止的「权力的影子」（`m5-power-api.md` §0 B2/B3）。
**封堵三条**（缺一条即敞口）：

1. **事件层零归因**：`fire.*` payload **无 actor/intent 键**（§1.3）；烧毁走 `structure.collapsed{cause:"damage"}`
   ——`cause` 是**物理类目**（decay/damage/support_lost），不是「谁烧的」。⇒ 事件可重放、可回放，
   而回放本身**不含归因**。
2. **叙事层归因须过既有闸 + 自我怀疑纪律**：Agent 说什么都要过 `banned_words.scan()` 出站终扫与
   `impulse_gate` 三扫；「某人故意烧的」「上面让我看着火的」属**指向外部命令源**⇒ 触「被操纵感」红线
   （codex `manipulation` 码在权力语境零豁免）。**允许**的写法是**自证式观察**
   （「火是从东边过来的」「那家铺子烧穿了」——只讲**可观察事实与自身感受**，不讲**谁该负责**）。
3. **出站闸兜底**：K11 的咽喉闸（`sim/api/outbound_guard.py`）递归剥除禁键 + 留痕；
   **建议把「归因键」纳入钉子而非键集**（见 §5 待裁 4）。

**交叉引用（codex `m5-security-preplan.md` §10.2 面②）**：

- **W-D1**：蔓延/生态每一步状态变更必须产事件（禁直写表）——本稿 §1 的 kind 登记即其执行形态；
- **W-D2**：玩家念头间接纵火 ⇒ T3 语料补「破坏类指令」样本，**随语料 CR 加、不预扩**（本稿零词表扩散）；
- **W-D3**：蔓延事件预算「事件驱动非 per-tick」——本稿 §1.2 代价 3 同款口径；
- 另 W-C2（混沌输出禁字符串内插进叙事文本）**同样适用**：`chaotic()` 的火势抽样值只能进 payload 数值字段，
  **禁** `f"…{chaotic(...)}"` 进 narrative/monologue。

## 4. 对 opencode（火灾数据面）的接口要求清单（K11 P1–P5 体例）

**假设 F1（数据面落点与方法签名）**：火势状态需要一张新表（建议 `fires`）＋既有族事件投影。
建议签名（**可微调命名，但「返回行不得含归因键」与「变更必产事件」两条不可让**）：

```python
# 建议（domain 层，sim/core/persistence）：
async def upsert_fire(branch_id: str, *, fire_id: str, x: int, y: int) -> FireRow: ...
async def set_fire_end(branch_id: str, fire_id: str, end: FireEnd) -> None: ...
def active_fires(branch_id: str) -> Sequence[FireRow]: ...   # FireRow 含坐标/燃料，**禁**归因键
```

**假设 F2（禁直写表，W-D1）**：一切火势状态变更**必须经 `store.append` 产事件**；
新增写表 SQL 不经 `store.append` 即红（codex 钉体例）。同理**禁**任何「只存在于内存的火势」——
火势必须是事件流的纯函数投影（否则读档回来火没了，违 C6 与离线验收）。

**假设 F3（kind 登记同 commit，K11 P3）**：`EventKind.FIRE_*` + `PAYLOAD_MODELS` 登记 +
`extra="forbid"` 封闭 payload + `test_t1_m4_structure_payloads` 同款钉（kind 白名单 + 等集）**同提交**；
新增 kind 会撞 codex 现有闭合集钉，故**新增前须同 CR**。

**假设 F4（守恒走既有族）**：燃烧消耗材料**必须**走 `matter.damage`（既有族），
不得自定义材料消耗路径——折叠器（`fold_matter_snapshot`）零改动即让 T1 材料守恒成立
（`m5-plan` 批次 D 验收口径：「材料守恒在蔓延中仍须成立」）。

**假设 F5（迁移纪律）**：新表走**0014**（0013 已占）同款体例（`create_table` + 快照双列 CHECK +
往返钉）；且 `create_all`（新库/测试库）与 alembic（旧库）**两条路径列集一致**——
K11 P5 已记该教训（陈旧 `world.db` 缺列 ⇒ 随机 teardown 红）。

## 5. 待裁点（6 点，含推荐采法）

| #   | 待裁                                       | 选项                                                                                   | **推荐**                                                                 | 理由                                                                                                                                                                                                                        |
| --- | ------------------------------------------ | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `fire.*` 命名                              | `ignited/spread/extinguished` vs `started/spread/out` vs `fire.on/fire.move/fire.off`  | **`fire.ignited` / `fire.spread` / `fire.extinguished`**                 | 与既有 `structure.started`/`npc.lod_change` 同族（**过去式/分词**），读事件流自带时序；`fire.on/off` 会被误读为状态而非事件                                                                                                 |
| 2   | 烧毁归因落点                               | ①既有 `structure.collapsed{cause:"damage"}` ②扩 `StructureCollapseCause` 加 `"burned"` | **①**                                                                    | 零枚举扩展、守恒断言零改动；代价＝事件层无 fire 归因——而归因**本就不该**在事件层（§3）                                                                                                                                      |
| 3   | 是否扩 `Structure.phase` 加 `"burning"`    | ①不扩（火光走 `lights[].kind`）②扩（快照 minor 变更）                                  | **①**                                                                    | ②是一次快照+生成物变更（须 versioning §7 登记 + 三处同提交）；火光用 `kind="fire"` 已够表达，且 `phase` 语义是**结构状态**（built/collapsing/rubble），燃烧是**火势**——混进去会让「构件状态」与「火势」两套语义挤进一个枚举 |
| 4   | 归因键是否进 `AUTHORITY_FORBIDDEN_KEYS`    | ①不扩键集，改钉 payload 白名单 ②扩键（`culprit`/`igniter`/`attribution`…）             | **①**                                                                    | 键集是 **codex 资产**（活资产、只增不减、须同 CR）；而本案 `fire.*` payload 白名单**根本没有**归因键 ⇒ 加键是空转。**若将来出现带归因键的事件 payload**，再同 CR 扩键不迟                                                   |
| 5   | 蔓延事件预算口径（N 值）                   | ①W-D3 的 N 由 pi 定标机定 ②先不设阈值                                                  | **①**，我侧只加一条口径：**火势状态变更驱动**（无变更零事件），N 值等 pi | N 需定标机实测（本地负载噪声大，裁 29-C 有先例）；口径先立可防「per-tick 产事件」的写法漂移                                                                                                                                 |
| 6   | `fire.ignited` 是否带 `cause`（自然/人为） | ①不设 ②设枚举 `{natural, human}`                                                       | **①**                                                                    | 「人为」=归因字段＝泄漏面（§3）；且玩家纵火入口已有 `impulse_gate` 三扫 + W-D2 语料 CR，不需要事件层再记一次                                                                                                                |

## 6. 与既有资产的关系（不重复造钉）

| 既有                                                        | 归属             | 本稿动作                                                       |
| ----------------------------------------------------------- | ---------------- | -------------------------------------------------------------- |
| codex **W-D1/D2/D3**（火灾面②缺口钉）                       | codex            | 引用，不重写；本稿 §1/§3 只说明其执行形态                      |
| kilo **K11 出站咽喉闸 + 18 钉**（`m5-power-api.md`）        | 我（本轮已施工） | 火灾出站**继承**该闸；本稿只补「归因键不入 payload」的前置要求 |
| **`test_t1_m4_structure_payloads` 52 面**（payload 域约束） | 既有             | 烧毁走既有族即零改动；新 kind 须同款补钉（F3）                 |
| **T1 材料守恒**（`test_assertions_conservation`）           | 既有             | 燃烧经 `matter.damage` 即成立（F4）                            |
| **T2 回放逐位一致（C5）**                                   | 既有             | 火势必须是事件纯函数投影（F2 禁内存态）                        |
| **pi tick 预算**（蔓延 per-tick 传播）                      | pi               | 待裁 5 只定口径，N 值归 pi                                     |

## 7. 不在本稿范围

- 火势传播语义与物理参数（燃料、蔓延半径、扑灭判定）＝ Claude 域。
- 火势表/事件登记/迁移（0014）＝ opencode 域（要求见 §4）。
- tick 成本模型与 N 值定标 ＝ pi 域。
- 安规判据与 T3 破坏类语料（**不预扩**）＝ codex 域。
- 前端火光渲染（`lights[].kind="fire"` + `flicker` 的表现层）＝ cline 前端域；契约面零变更。
- 生态（砍树→水土流失→河浊→鱼少，§18 缩范围序第 1 位）：本稿只提一句——**同款判定**
  （`eco.shift` 类新 kind 走 W-D1 同路径，WS/HTTP 同样零变更），**生态整体是可砍项，不在本稿展开**。
