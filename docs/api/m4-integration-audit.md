# M4 收官对账单 — K6×K7×K8 三方汇聚 + 8 新事件 kind 注册完整性 + 协议↔安规

> 能力域：接口 / 兼容性（kilo，跨域集成对账）
> 依据：`.orca/talking.txt` M5-K9 派单卡（M4 收官对账单）；对齐 DESIGN §4/§8/§14/§19、`docs/api/ws-protocol.md`、`docs/api/ws-dispatch-proposal.md`、`docs/arch/m4-plan.md`、`docs/arch/t5-golden-scaffold.md`
> 树：ZX466/kilo @ `1f55579`（= main） · 日期：2026-09-27 · 性质：**只读对账（不改码）**，产出本文件 + **1 处 CRITICAL 回执标红**（见 §1，修复提案待新单）
> 口径：✓ = 已对齐且可证；⚠ = 已知缺陷/悬空面（**多为批次待派的显式延迟**，不阻断本单）；🔴 = **CRITICAL 缝**（同一域内自相矛盾、可致收官门红）

---

## 0. 结论摘要（TL;DR）

| # | 轴 | 结论 |
|---|---|---|
| 1 | 协议面 K6×K7×K8 汇聚 | 🔴 **1 处 CRITICAL**：K7 发 `state_delta.plan` 顶层键，但**冻结 schema 无 `plan` 且 `additionalProperties:false`** → 语义打架、plan 面不可达前端 |
| 2 | 8 新 kind 注册完整性 | ⚠ **5 kind 无生产者**（`structure.started/completed/removed`、`material.moved`、`npc.lod_change`）——**批次 C 行为链待派**的显式延迟，非实现缺陷 |
| 3 | 协议↔安规 | ⚠ **`impulse_gate` 已实现未接线**（28 钉子绿），`impulse_feedback.injected:false` 分支**在线上不可达**——**批次 A 接线归 Claude** 的显式延迟 |

**对收官门的影响**：轴 1 是**我方（kilo）域内**的 schema/实现打架，**建议开新单直修**（改 `openapi_ext.py` + 重生成 `shared/openapi.json`/`protocol.ts`，走生成管线，禁手写）——**本单只读，不改码**（派单卡纪律：只读+文档）。轴 2/3 是**跨域已裁的显式延迟**，只需在台账留痕，不改码。

---

## 1. 🔴 CRITICAL — `state_delta.plan` 越界冻结 schema（K7 遗留）

### 1.1 事实（已实证）

- **K7 实现**（`sim/api/ws.py::delta_payload`，`0c5327a` 收编）在 `state_delta` 帧上追加**顶层可选键** `plan`：
  ```python
  plan_items = [{"rtoken": _rtoken(e), "text": t} for e, t in sorted(known.items()) ...]
  if plan_items:
      payload["plan"] = plan_items      # 顶层键，与 actors 并列
  ```
- **冻结 schema**（`sim/api/openapi_ext.py::"StateDeltaMessage"` → `shared/openapi.json` → `shared/protocol.ts`）：
  - 属性集 = `{v, ws_seq, channel, type, actors, lights, structures, weather}`；
  - **无 `plan`**；
  - `additionalProperties: false`（`_envelope()` 第 44 行对**每个**信封强制）。

### 1.2 实证（脚本 `openapi.json` 对帧校验）

```
StateDeltaMessage properties: ['actors','channel','lights','structures','type','v','weather','ws_seq']
additionalProperties: False
has 'plan' property: False
emitted keys: ['actors','channel','plan','type','v','ws_seq']
keys violating additionalProperties:false -> ['plan']
VERDICT: SCHEMA-ILLEGAL (plan key rejected by frozen schema)
```

### 1.3 为什么是 CRITICAL（三连锁）

1. **契约自相矛盾**：`ws.py` 注释自称「`plan` 是 `state_delta` 顶层可选键（裁 14-3）」，而**同仓**的 schema 真源禁止该键。二者不可能同真。
2. **前端可达性归零**：`shared/protocol.ts` 的 `StateDeltaMessage` 无 `plan` ⇒ TS 侧读数 `plan` 是 excess property，**计划看板（批次 B 交付目标）拿不到数**。
3. **违我方铁律**：`m4-plan.md` 批次 C 明确「**新增 HTTP/WS 字段 = kilo（走 OpenAPI 生成管线，禁手写 protocol.ts）**」——K7 加线字段**未走生成管线**，正是该条禁止项。

> 性质：**非**跨域延迟，**是 kilo 域内** K7 单方加字段漏更 schema。**已按派单卡「立即回执标红」上报**；修复**另开新单**（本单只读）。

### 1.5 追加铁证 — K7 测试引用了**不存在**的 schema

`sim/tests/test_m5_plan_delta.py` 第 9 行白纸黑字：

> `text=当前计划文本（可空串=无计划）。`**`PlanDelta.additionalProperties:false`**`。`

但全仓（`sim/`、`shared/`、`docs/`）**无任何 `PlanDelta` schema 定义**（`rg "PlanDelta"` 仅命中 `PlanDeltaStore` 类与测试注释）。⇒ K7 的钉子**把一条并不成立的 schema 假设写成判据**，而 schema 从未落地。**这是「实现了没注册」在协议- schema 面的实例**，坐实 CRITICAL。

### 1.4 修复提案（最小、走管线）

- **改 schema 真源**：`sim/api/openapi_ext.py` 的 `"StateDeltaMessage"` 增 `plan` 属性：
  ```python
  "plan": {"type": "array", "items": {"$ref": "#/components/schemas/PlanItem"}},
  ```
  并新增 `PlanItem` 子 schema（`{rtoken: RToken, text: string}`，`additionalProperties:false`，required 二者）。`plan` **不进 `required`**（可选字段，账本空时不发）。
- **重生成物**：`npm run gen:protocol`（勿手写 `protocol.ts`），提交 `shared/openapi.json` + `shared/protocol.ts` 生成物。
- **补钉子**：`test_m2_openapi_rework.py` 同款「实发 schema ≡ 快照」断言扩到 `plan` 属性；并加一条**运行期帧校验**（`delta_payload` 带 plan 时 ⊂ schema 属性集）防再犯。

> 归口：本单**只读**，修复**另开新单**（待派单卡授权动码）；本文件已标红并即时回执。

---

## 2. 对账① — 协议面 K6×K7×K8 汇聚点

### 2.1 汇聚面清点

| 面 | 落点 | 交互点 | 状态 |
|---|---|---|---|
| K6 分发块 | `ws.py::handle_client_message` + `_handle_{move,set_control,player_impulse,load_anchor,sync}` | 五类 C→S 消息白名单 × channel 成对 | ✓ |
| K7 `plan` 字段 | `ws.py::delta_payload` 顶层 `plan` | 与 K6 的 `state_delta` 同帧 | 🔴 schema 越界（§1） |
| K8 monologue | `ws.py::monologue_payload` + `monologue_events_to_frames` + `route_monologue` | 独立帧，不复用 `state_delta` | ✓ 形状对齐 `MonologueMessage` |
| K8 投递面 | `MONOLOGUE_DELIVERY_ALL/SELF` + `ConnectionManager.subscriber_id` | `_handle_player_impulse` 的 `reaction_monologue` 是**另一条**独白来源 | ✓（见 2.4 注） |

### 2.2 帧形状 vs schema（逐字段）

| 帧 | 实现键集 | schema 键集 | 结论 |
|---|---|---|---|
| `monologue` | `{type,channel,v,ws_seq,form,content}` | 同（`MonologueMessage`） | ✓ **逐键相等**，无 actor/rtoken（W7 字段最小化守住） |
| `impulse_feedback` | `{type,channel,v,ws_seq,injected,cue,reaction_monologue}` | 同（required 全含） | ✓ |
| `control_ack` | `{type,channel,v,ws_seq,action,applied[,speed]}` | 同（`ControlAckMessage`） | ✓ |
| `state_delta` | `{...,actors[,plan]}` | `{...,actors,...}` **无 plan** | 🔴 |

### 2.3 `state_delta.plan` 的**第二处**不一致（非 schema，属行为）

K7 `delta_payload` 的 docstring 称「改计划不必伴随移动——塞 ActorDelta 会被 moved 过滤漏掉，故与 actors 并列」。但**驱动层只在该帧有 `moved` 时才发 `state_delta`**：

```python
# sim/api/ws.py::run_world_driver
if moved:                      # ← plan-only 变更（无移动）时整帧不发
    payload = delta_payload(loop, moved)
```

⇒ **「计划变了但 NPC 没动」的 tick，`plan` 变更不会上线**（写注释与实现不符）。severity：⚠ HIGH（计划看板更新会滞后到下一个移动帧；defers→plan 的「原地缓一缓」场景最易踩）。修复：驱动层把发送条件从 `if moved:` 放宽为 `if moved or plan_dirty:`（需 `delta_payload` 暴露**是否含 plan 变更**的判定，或由 `PlanDeltaStore` 出 dirty 位）。

### 2.4 K8 投递面 × K6 的 `reaction_monologue`（缝的正当性核验）

- K6 `_handle_player_impulse` 回的 `reaction_monologue = {form:"thought", content:"这话我记下了。"}` 是**同步占位**（§8.3，冲突度规则表归 LLM 域）。
- K8 投递面按 `form` 路由：`thought ∈ MONOLOGUE_DELIVERY_SELF` ⇒ **定向本人**。
- **一致**：`impulse_feedback.reaction_monologue` 走的是**直接应答**（同一连接），不经 `route_monologue` 的多播面——两条路径**语义不冲突**（前者 1:1 echo，后者事件流多播）。**无需改**；建议在 `ws.py` 投递面契约处补一行注记，防后人误把二者合并。

### 2.5 `pause` 的 `_PRE_PAUSE_SPEED` 在多连接下的串扰（K8 引入多连接后暴露）

- `_PRE_PAUSE_SPEED: list[float]`（`ws.py:451`）是**模块级全局**，注释自称「连接级会话状态」（提案 §1.2 注记「M2 多连接前改为 ConnectionManager 每连接字段」）。
- K8 已引入**多连接**（旁观者连接），但 `pause/resume` 仍读写**同一全局栈** ⇒ **A 连接 pause、B 连接 resume 会互窃倍率**。
- severity：⚠ MEDIUM（当前单玩家演示无感；多观察者连接下行为错乱）。修复：把栈挂到 `ConnectionManager` 的 per-connection 字段（同 `subscriber_id` 的挂载方式）。**归口 = kilo**，建议随 §1 修复同批落。
- **同源观察（§2.5b）**：`main.py::ws_endpoint` 给**每条**玩家连接都设 `subscriber_id = subscriber_for_protagonist(loop)`（= 唯一主角）。⇒ 「本人」面=**所有已连接玩家**，`thought` 定向实为「发给全部主角连接」。**单玩家演示下等价**，非缺陷；但**多客户端（同主角多开）时私密性=共享**。若产品语义要求「仅发起点的那条连接」，需把 identity 下沉到**每连接**（hello token 绑定）而非「主角 id」。当前**按设计（单主角）可接受**，记 ⚠ 观察。

---

## 3. 对账② — 8 新事件 kind 注册完整性

**M4 新增 8 kind**（来源：`c719171` D2a 建 6 + `NPC_HIDDEN_EMERGE`（E1 批）+ `NPC_MONOLOGUE`（K8 `732e8c8`））：

| kind | payload 模型 | 工厂 | `PAYLOAD_MODELS` | 生产者（非测试） | 折叠/投影 | 结论 |
|---|---|---|---|---|---|---|
| `npc.hidden_emerge` | `HiddenEmergePayload` | `hidden_emerge_event` | ✓ | `sim/npc/runtime.py:89` | 无派生表（叙述+hidden 账本另路） | ✓ |
| `structure.started` | `StructureStartedPayload` | `structure_started_event` | ✓ | **无** | `fold_structure_snapshot` ✓ | ⚠ 无生产者 |
| `structure.checkpoint` | `StructureCheckpointPayload` | `structure_checkpoint_event` | ✓ | `sim/world/structure.py:151` | 同上 ✓ | ✓ |
| `structure.completed` | `StructureCompletedPayload` | `structure_completed_event` | ✓ | **无** | 同上 ✓ | ⚠ 无生产者 |
| `structure.collapsed` | `StructureCollapsedPayload` | `structure_collapsed_event` | ✓ | `sim/world/support_graph.py:170` | 同上 ✓ | ✓ |
| `structure.removed` | `StructureRemovedPayload` | `structure_removed_event` | ✓ | **无** | 同上 ✓（返回 None=删行） | ⚠ 无生产者 |
| `material.moved` | `MaterialMovedPayload` | `material_moved_event` | ✓ | **无** | `fold_material_balance` ✓ | ⚠ 无生产者 |
| `npc.monologue` | `NpcMonologuePayload` | `npc_monologue_event` | ✓ | `sim/npc/runtime.py:129` | 无派生表（叙述） | ✓ |

### 3.1 「实现了没注册 / 注册了没生产者」两面

- **实现了没注册**：**无**。全 19 kind（含 8 M4 新）均在 `PAYLOAD_MODELS` 登记；`test_t1_m4_structure_payloads` 钉「`PAYLOAD_MODELS` 与 `EventKind` 等集」。
  - 附带核验：`PAYLOAD_MODELS` 的键集 == `EventKind` 成员集（20 处 `EventKind.` 引用中 1 处是 `_validate_npc_act` 内的 `is` 判定，非字典键）。
- **注册了没生产者**：**5 kind**（上表 ⚠ 行，含 M2 遗留 `npc.lod_change`）。

### 3.2 塌陷器/折叠器覆盖（轴②的「折叠器」子项）

| 折叠函数 | 覆盖 kind | 位置 |
|---|---|---|
| `fold_matter_snapshot` | `matter.decay/damage/build/collapse` | `npc_store.py:651` |
| `fold_structure_snapshot` | `structure.started/checkpoint/completed/collapsed/removed` | `npc_store.py:758` |
| `fold_material_balance` | `material.moved` | `npc_store.py:857` |
| （无）| `npc.hidden_emerge`、`npc.monologue` | 叙述类，**刻意无派生表** |

- **投影分派** `_project_events`（`npc_store.py:603`）覆盖 LOD/matter/structure/material 四族；`hidden_emerge`/`monologue` **无分支**（不突变派生表，符合设计）。
- ✓ **无「有 kind 无折叠规则」的悬空**：5 个 structure kind + material 全覆盖；两个叙述 kind 无表是设计。

### 3.3 结论（轴②）

⚠ 的**根因是显式延迟**，非缺陷：`docs/arch/m4-plan.md` 批次 C 载明「**施工 tick 推进/quality/坍塌触发行为链 = Claude（待派）**」——正是这 4 个建造 kind 的**生产者**所在批次。M4 当前交付的是**数据面（D2：schema/投影/折叠/重放）**，行为链尚未派单。**不阻断本单**，但须在台账写明：**这些 kind 只要行为链接线即可产出，数据面已就绪**。

---

## 4. 对账③ — 协议 ↔ 安规

### 4.1 error `code` 词表闭合 ✓

- 实现 `sim/api/ws.py` 有 **10** 个 `_ERROR_*` 常量：`unknown_type/bad_channel/auth_error/bad_action/bad_speed/bad_impulse/impulse_too_long/bad_anchor/load_failed/bad_target`。
- 文档词表（`ws-dispatch-proposal.md` §5.1）**10 项**（含可选 `bad_target`，现已实现）。
- 钉子 `sim/tests/test_ws_gateway.py::TestErrorCodeVocabulary` 三例：**常量子集 ⊆ 词表** / **全小写 snake（无大写）** / **运行时逐路径触发的 code ∈ 词表**。
- ⇒ ✓ **闭合**，无越界、无大写残留（§4.5 样例 `IMPULSE_TOO_LONG` 已订正小写）。

### 4.2 ⚠ `impulse_gate` 已实现、未接线（`injected:false` 分支线上不可达）

- **实现**：`sim/agent/impulse_gate.py::impulse_gate()`（M4-A2 `7504873`）——hidden↔banned↔操纵感**三扫**，拒绝码闭合枚举 `REASONS`（5 个）；28 钉子绿（`test_m4_impulse_gate.py`）。
- **契约**：`docs/security/m4-impulse-gate-contract.md` 明写接线点「`ws.py::_handle_player_impulse` 长度校验之后、prompt 装配之前；`admitted=False → injected:false + error 帧`」。
- **现状**：`_handle_player_impulse`（`ws.py:459`）**只做长度/空串校验**，**未调用** `impulse_gate`，`injected` **恒 `True`**。
- **核验**：全仓非测试代码 **0 处**调用 `impulse_gate(`（`rg` 结果仅 `sim/agent/impulse_gate.py` 自身定义）。
- **性质**：**显式延迟**——同契约文首「**本文 + 钉子是接线契约，实现归 Claude（批次 A）**」，且 `m4-plan.md` 批次 A「注入语义/prompt 装配/措辞生成 = Claude（待派）」。⇒ 协议面（我方）**无需再动**（跨域注记早有此约定）。
- **对收官门的记法**：安规**判梯与拒绝码已闭合可测**；**唯一缺口是执行点接线**（批次 A）。建议在本对账单 + memory 留痕，**不标 CRITICAL**（有明确归口与派单计划）。

### 4.3 出戏边界复验（K8 投递面）

- `monologue` 帧**无** rtoken/actor/内部 id（W7 最小化）⇒ 客户端无法反推说话者内部身份，投递面由服务端按 `form` 定。✓
- `state_delta` 的 rtoken 替身出网关（`_rtoken`），内部 `entity_id` 不出。✓
- `error.message` 保持戏内文风、不含内部真相（§4.5 三原则）。✓

---

## 5. 行动项（建议）

| 优先级 | 项 | 归口 | 本单可否落 |
|---|---|---|---|
| 🔴 CRITICAL | `state_delta.plan` 补进 `openapi_ext.py::StateDeltaMessage` + 新增 `PlanItem`；`npm run gen:protocol`；补 schema/帧钉子 | kilo | ✖ **只读（另开新单）** — 已回执标红 |
| ⚠ HIGH | 驱动层 `if moved:` → 放行 plan-only 变更帧（§2.3） | kilo | ✖ 只读（建议同新单） |
| ⚠ MEDIUM | `_PRE_PAUSE_SPEED` 全局栈 → per-connection（§2.5） | kilo | ✖ 只读（建议同新单） |
| ⚠ 延迟 | `impulse_gate` 接线（`injected:false`） | Claude（批次 A） | ✖ 留痕迹 |
| ⚠ 延迟 | 4 建造 kind 生产者（施工行为链） | Claude（批次 C） | ✖ 留痕迹 |
| ⚠ 遗留 | `npc.lod_change` 无生产者 | M2 遗留（待确认归口） | ✖ 留痕迹 |
| ⚠ 延迟 | `impulse_gate` 接线（`injected:false`） | Claude（批次 A） | ✖ 留痕迹 |
| ⚠ 延迟 | 4 建造 kind 生产者（施工行为链） | Claude（批次 C） | ✖ 留痕迹 |
| ⚠ 遗留 | `npc.lod_change` 无生产者 | M2 遗留（待确认归口） | ✖ 留痕迹 |

---

## 6. 附：核验方法与可复现命令

- 事件族清点：`rg -n "^[ ]{4}[A-Z_]+ = " sim/core/events.py`
- `PAYLOAD_MODELS` 与 `EventKind` 等集：`pytest sim/tests/test_t1_m4_structure_payloads.py`
- 生产者审计（非测试）：脚本遍历 `rg -g '!**/tests/**' "<factory>\(" sim`
- schema 越界实证：读 `shared/openapi.json` 的 `StateDeltaMessage.properties` 与 `additionalProperties`，比对 `ws.delta_payload` 的键集
- error code 闭合：`pytest sim/tests/test_ws_gateway.py::TestErrorCodeVocabulary`
- 协议生成物一致：`npm run gen:protocol:check`（在 `client/`）

---

## 裁 19（2026-09-27 Claude 主树）

**CRITICAL（K7 plan 越界冻结 schema）——采 kilo 提案，修复派回 kilo（域内自纠）**：
PlanDelta schema 缺失是 K7 实现与冻结 schema 的真缝（钉子把不成立的假设写成判据）。
修复路径三步（kilo M5-K10 执行）：①openapi_ext 注入 PlanDelta 组件（additionalProperties
同封闭口径）②gen-protocol 生成→protocol.ts 同步 ③K7 钉子的 schema 假设改为引用
真实 schema。**修复完成后 plan 面才可达前端**——列入 M4 收官门前必修，K7 回归钉随修随绿。
**F-1（codex S4：裁 16-4 已裁未落）——采**：banned 词表补「概率/注定」是 codex 域
CR 纪律内（词面变更 owner=codex），本域放行，随 M4-S4b 落。
**F-2（impulse_gate 无生产调用方）——采，接线归我（Claude 批次 A 件）**：接线点
ws.py `_handle_player_impulse` 长度校验后插 gate 调用+injected:false 分支+
1 条 ws 层 e2e 钉——本裁决后我立即做，不另派单。
**pi P4 复核意见采**：timeout 90 维持（等 C5 首跑实测数再终裁）。
