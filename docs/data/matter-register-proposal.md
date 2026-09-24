# matter 注册持久化 — §19.4 待定项提案（register 事件 vs structures 表）

> 数据域（opencode），M3-C3，2026-09-24。**本文为提案**——按活跃约定
> 「schema 先提案 → Claude 裁决 → 再动代码」，**未动 models.py / 未出迁移**。
> 依据：`docs/data/schema.md §9`（structures 表设计）、`§19.4`（注册≠落库边界）、
> `§17.2`（MatterPayload 语义）、`docs/data/migration.md §4.9 + §6.2`
> （structures 迁移草案，**未实现**）、`docs/arch/m3-plan.md §6`（C3 提案项）、
> `sim/world/matter.py`（MatterLedger.register 现状）、
> `sim/core/persistence/npc_store.py`（fold_matter_snapshot / _project_matter）。
> 实现范围裁后：注册持久化通路 + 冷启不丢单测。

## 0. 一句话

`MatterLedger.register` 只进内存账本、**不产事件** → 空账本冷启（仅回放/快照重建）
丢「已注册未结算」对象；本提案裁「注册如何持久化」：**主张 register 产
`MATTER_BUILD` 事件（amount=0 语义 = 立账）**，否 structures 表作注册主路径。

## 1. 现状（§19.4 + 代码实证）

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

## 2. 方案对比

| # | 方案 | 机制 | schema | 写路径 | 冷启保真 | 风险 |
|---|---|---|---|---|---|---|
| A | **register 产 `MATTER_BUILD` 事件**（主张） | `register()` 改为返回 `WorldEvent`（或内部 enqueue），`amount=0`、`durability=integrity`、`decay_rate=rate`、`note="register"`；走既有 C4 唯一写路径 → `_project_matter` 首事件建行 | **零改动** | 唯一写路径（事件） | 重放/快照均含 | register 签名变更（见 §4） |
| A' | 新 kind `MATTER_REGISTER` | 同 A，专用 kind + payload 登记 | 零列改动；**EventKind 追加**（冻结基线允许追加） | 同 A | 同 A | 多一种 kind 的折叠/校验分支；与 BUILD 语义重复 |
| B | **structures 表作注册主路径** | `register` 直写 `structures` 行；`materialize_matter` 需 UNION 或双读 | 新表 + 迁移 003（草案未实现） | **双真相**（structures 存在性 vs matter_state 熵态） | 须两表一致 | 违「matter_state=事件流投影」；§14 回放判据失效；C4 旁路直写 |
| C | A+B 混合 | 注册走事件；structures 仅存 §9 拓扑列（tiles/kind/material/owner） | structures 列裁剪 | 事件为主 | 同 A | 结构域 M4 才需要拓扑；M3 过早建表 |

## 3. 主张与理由（方案 A）

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
5. **否 A' 新 kind（默认）**：`MATTER_BUILD` 已覆盖「立账 + 携带 durability/decay_rate」；
   amount=0 + note 区分注册与增建。仅当裁决要求审计上注册/建造分账时再追加
   `MATTER_REGISTER`（EventKind 追加合法，payload 复用 MatterPayload）。

## 4. 实施草案（**裁后**动代码）

1. `MatterLedger.register` 签名：
   ```python
   def register(
       self, matter_id: str, *, integrity: float, decay_rate: float,
       tick: int = 0, x: int = -1, y: int = -1,
   ) -> WorldEvent:
   """注册并返回 MATTER_BUILD 立账事件（amount=0；调用方负责 flush）。"""
   ```
   - 重复注册仍 `ValueError`（现行为保留）；
   - 返回事件 = 显式交回调用方 flush（与 `damage`/`build` 一致的「产事件」风格）；
   - **兼容**：现有测试 `ledger.register(...)` 忽略返回值仍绿（返回值不破坏调用）。
2. 投影/重放：**零改动**（MATTER_BUILD 已在 `_MATTER_KINDS` / `PAYLOAD_MODELS` /
   `_project_matter` 覆盖）。
3. 调用方（裁后接线）：创世/装配层 register 后 `flush_tick([event])` 或同批入队。
4. 测试钉子 `sim/tests/test_m3_matter_register.py`：
   - register → flush → `materialize_matter` 含该 id；
   - 空账本仅重放（不读表）→ `materialize_matter_replay` 含该 id（冷启不丢）；
   - 快照/重放逐位相等（扩展 §19.3 判据到「仅注册」对象）；
   - 重复注册拒；amount=0 不扭曲 integrity。
5. 文档：裁决落回 `schema.md §19.4`（去掉「待定」，改指向本提案结论）。

## 5. 待裁决点

1. **采 A（BUILD 立账）还是 A'（新 kind MATTER_REGISTER）？**
   本提案主张 **A**（零新 kind；审计 note 可后补）。若要求注册/建造事件流分账 → A'。
2. **register 返回事件 vs 内部总线 enqueue？**
   本提案主张 **返回事件**（与 damage/build 同风格，flush 权在调用方，测试可纯函数断言）；
   若裁「register 必须自含持久化」则改为注入 EventSink——偏离现风格，不推荐。
3. **structures 表是否保留给 M4 拓扑？**
   本提案主张 **保留 §9 设计但 M3 不建表**；M4 建造时再裁「拓扑列是否从事件投影」。
   本提案不否定 structures 本身，只否定其作 **注册** 主路径。
4. **x/y 坐标**：注册事件默认 -1（未定位）还是强制带 tiles？
   MatterPayload 无 tiles 字段；定位注册可后续加 x/y 或 M4 structures 拓扑。
   本提案主张 **M3 默认 -1**（与现 register 无坐标一致；chunk 失效不因纯注册触发）。
