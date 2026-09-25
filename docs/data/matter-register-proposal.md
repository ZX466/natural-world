# matter 注册持久化 — §19.4 裁决与实施记录（方案 A）

> 数据域（opencode），M3-C3，2026-09-24；裁决 2026-09-25。方案 A 已实施：
> `MatterLedger.register` 返回 `MATTER_BUILD` 立账事件，**零 schema、零迁移**。
> 依据：`docs/data/schema.md §9`（structures 表设计）、`§19.4`（注册≠落库边界）、
> `§17.2`（MatterPayload 语义）、`docs/data/migration.md §4.9 + §6.2`
> （structures 迁移草案，**未实现**）、`docs/arch/m3-plan.md §6`（C3 提案项）、
> `sim/world/matter.py`（MatterLedger.register 现状）、
> `sim/core/persistence/npc_store.py`（fold_matter_snapshot / _project_matter）。
> 实现范围裁后：注册持久化通路 + 冷启不丢单测。

## 0. 一句话

`MatterLedger.register` 返回 `MATTER_BUILD` 立账事件（`amount=0`、
`durability=integrity`、`note="register"`）；调用方 flush 后，快照与事件重放两条
冷启路径均不丢注册对象。structures 表不作注册主路径。

## 1. 裁决前基线（§19.4 + 代码实证）

| 面 | 现状 | 缺口 |
|---|---|---|
| `MatterLedger.register(id, integrity, decay_rate)` | 仅 `_items[id] = snapshot`，**返回 None** | 无事件 → 不进 `events` 表 |
| `materialize_matter`（快照路径） | SELECT `matter_state` WHERE branch | 注册未投影 → 不在结果 |
| `materialize_matter_replay`（重放路径） | 折叠 `events` 内 `matter.*` | 无注册事件 → 不在结果 |
| `matter_state` 表 | 0004 已建；`_project_matter` UPSERT | **首个 MATTER_\* 事件才建行** |
| `structures` 表（§9） | **仅文档设计**；migration 草案 003 **未实现** | models.py 无 Structure |
| 冷启 | `register` 空账本 + `materialize_*` | **只回「已投影对象」，注册即丢** |

§19.4 原文把「注册持久化」标为 M3 待定项，二选一线索：
**MATTER_BUILD/register 事件** vs **保留 structures 表**。

## 2. 方案对比（历史留档）

| # | 方案 | 机制 | schema | 写路径 | 冷启保真 | 风险 |
|---|---|---|---|---|---|---|
| A | **register 产 `MATTER_BUILD` 事件（已采）** | `register()` 返回 `WorldEvent`，`amount=0`、`durability=integrity`、`decay_rate=rate`、`note="register"`；走既有 C4 唯一写路径 → `_project_matter` 首事件建行 | **零改动** | 唯一写路径（事件） | 重放/快照均含 | register 签名变更（见 §4） |
| A' | 新 kind `MATTER_REGISTER` | 同 A，专用 kind + payload 登记 | 零列改动；**EventKind 追加**（冻结基线允许追加） | 同 A | 同 A | 多一种 kind 的折叠/校验分支；与 BUILD 语义重复 |
| B | **structures 表作注册主路径** | `register` 直写 `structures` 行；`materialize_matter` 需 UNION 或双读 | 新表 + 迁移 003（草案未实现） | **双真相**（structures 存在性 vs matter_state 熵态） | 须两表一致 | 违「matter_state=事件流投影」；§14 回放判据失效；C4 旁路直写 |
| C | A+B 混合 | 注册走事件；structures 仅存 §9 拓扑列（tiles/kind/material/owner） | structures 列裁剪 | 事件为主 | 同 A | 结构域 M4 才需要拓扑；M3 过早建表 |

## 3. 裁决结论与理由（方案 A）

1. **零 schema、零迁移**：复用 `MatterPayload` + 既有 `_project_matter` /
   `fold_matter_snapshot` 单一折叠规则——注册 = 新对象首事件，与 §17.2
   「新建对象 durability<0 → 1.0」及现有 UPSERT 路径自然衔接。
2. **唯一写路径不破**（C4）：注册产事件 → flush 投影；无「内存注册 + 另一张表」
   双真相。方案 B 的 structures 直写 = matter 域旁路 UPDATE（codex C11 反面）。
3. **冷启两入口同构**：`materialize_matter` 与 `materialize_matter_replay`
   在有注册事件后均能重建同一 `MatterLedger`（§19.3 逐位相等判据覆盖注册）。
4. **structures 不作注册主路径**（否 B/C 的注册半边）：
   - §9 表未实现，M3 注册需求用新表过重；
   - structures 语义 = **拓扑/建造元数据**（tiles/kind/material/load_bearing），
     matter 注册 = **熵态账本身份**——两域正交，硬绑会把 M4 建造列拖进 M3 注册；
   - 若 M4 需要 structures，应走 **C：事件仍是熵态真相，structures 只做拓扑投影**
     （从 BUILD/REGISTER 事件投影 tiles/kind，不从 register 直写）。
5. **否 A' 新 kind**：`MATTER_BUILD` 已覆盖「立账 + 携带 durability/decay_rate」；
   `amount=0` + `note="register"` 区分注册与增建。审计分账若 M5+ 有实证需求，
   再走 CR 追加 `MATTER_REGISTER`。

## 4. 实施记录（已完成）

1. `sim/world/matter.py::MatterLedger.register` 已改为返回 `WorldEvent`：
   `tick=0`、`x=-1`、`y=-1`；先经 `matter_event` 校验并构造事件，再写账本，
   避免非法 payload 留下半注册状态。
2. 投影/重放零改动：`MATTER_BUILD` 已由 `_MATTER_KINDS`、`PAYLOAD_MODELS`、
   `_project_matter` 与 `fold_matter_snapshot` 覆盖。
3. flush 口径：
   - `NpcStore.flush_tick([event])`：事件落库并同事务投影 `matter_state`，
     供 `materialize_matter` 快照路径读取；
   - `flush_events(store, [event])`：只落事件，供
     `materialize_matter_replay` 重建；当前生产代码无 `register` 调用点，
     本批不造调用方。
4. `sim/tests/test_m3_matter_register.py` 9 用例覆盖：立账事件形状、
   `flush_tick` 冷启不丢、纯事件重放不丢、仅注册对象快照/重放逐位相等、
   `amount=0` 不扭曲 integrity、重复注册不替换、非法 payload 不半注册、
   x/y=-1 不标脏、定位坐标透传。
5. `schema.md §19.4` 已回写为规范契约；`m3-plan.md §6` 保留裁决记录。

## 5. 裁决结果（历史提案问题已闭合）

1. **A vs A'**：采 A，零新 EventKind；`note="register"` 保留审计区分。
2. **返回事件 vs EventSink**：采返回事件，flush 权在调用方。
3. **structures**：M3 不建表，§9 设计保留给 M4 拓扑投影。
4. **x/y**：默认 -1 未定位；显式坐标可透传，tiles 拓扑留 M4。

---

## 6. 裁决（2026-09-25，Claude 主树裁决——4 点全采主张）

> 裁决依据 = 主树实证（非仅提案推演）：`_project_matter` 首事件即建行
> （`existing is None` 分支），折叠按 `durability`（结算后耐久）而非 `amount`
> ——`MATTER_BUILD(amount=0, durability=integrity)` 首事件即立账且 amount=0
> 不扭曲 integrity，方案 A 的关键前提成立。另：x/y=-1 与 C3 已收编的
> `event_tile_position`（-1 哨兵不标脏）天然衔接——纯注册不触发 chunk 失效。

1. **采 A（BUILD 立账），否 A'**。零新 kind；`amount=0 + note="register"` 区分
   注册与增建。审计分账若 M5+ 有实证需求再走 CR 追加 `MATTER_REGISTER`。
2. **采「返回事件」**。`register()` 返回 `WorldEvent`，flush 权在调用方——与
   `damage`/`build` 同风格，测试可纯函数断言；不注入 EventSink。
3. **structures 表 M3 不建**，§9 设计保留给 M4；届时再裁「拓扑列是否从事件
   投影」（倾向 C：事件是熵态真相，structures 只做拓扑投影，不直写）。
4. **x/y 默认 -1**（未定位）。MatterPayload 加 tiles 字段属 M4 结构域，M3 不扩。

**实施结果**：opencode 已按 §4 完成 `register` 签名、立账事件、9 用例钉子与
`schema.md §19.4` 回写；作为「M3-C3 后续件」交付待收编。当前无生产
`MatterLedger.register` 调用点，不新增调用方。
