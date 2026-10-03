# M5 批次 D 火灾生态 · 数据面预研（火灾损伤的存储形态与事件归属）

> **归属**：数据面（opencode）· 纯预研（**零代码零迁移**），施工随下一单（裁 31-1 模式：
> 预研案即施工案，但火灾面比权力面大，值得完整一轮）。
> **依据链**：DESIGN §14「承重依赖图 → 级联坍塌 → 坍塌范围伤人 + **火灾蔓延**（M5）」+「integrity
> 归零变 rubble 永不恢复，进事件日志」→ `docs/data/schema.md` §14（`matter_state`「施工/破坏/
> **火灾**改变其数值…**快照 + 事件重放可逐位重建**」）→ codex `m5-security-preplan.md` §10.2
> 面② **W-D1/W-D2/W-D3**（蔓延每步状态变更必须产事件 / T3 破坏类样本 / 事件预算沿用混沌判据）
> → 裁 24（不新增**安规**面；D-10 只约束权力）与 kilo `m5-power-api.md` §6 **P3 纪律**
> （新增 kind 须登记 `PAYLOAD_MODELS` 闭合集 + API/WS 零投影 + 同 CR）→ A7 `m5-power-data-preplan.md`
> （`npc_power` fail-closed 语义）→ A3 `m5-anchor-materialization-preplan.md` 地基分类。
> **状态**：**已施工**（裁 33 2026-10-03 落卡；M5-A9 交付，见文末 §8 施工落地记）。

---

## 0. 一句话结论

**火灾损伤零新表零新列**（全部落在既有 `matter_state` / `structures` / `material_balances`
的既有列上，**属 A3「可重放」那一侧**）；**火场中间态不入库**（纯运行态，不进 A3 任何一类 ⇒
批次 E 物化包**不需要**为火扩格式）；事件面**新增 2 个边界 kind**（`fire.ignited` /
`fire.extinguished`）+ **蔓延/烧毁走既有族**（`matter.damage` / `matter.collapse` /
`structure.collapsed`），因果链走 0008 谱系列；另扩**两个枚举成员**（坍塌 `cause="fire"`、
材料去向 `reason="burned"`）保材料守恒与审计。

## 1. 物质状态存哪：既有表够不够（问题①）

### 1.1 判定：**够，且不该新表/新列**

| 火灾后果 | 落点（既有列） | fold 器 |
| --- | --- | --- |
| 焦化 / 强度衰减 | `matter_state.integrity`（`matter.damage` 的 `amount` ≤ 0 / `durability` 结算后值） | `_project_matter` + `fold_matter_snapshot`（M3） |
| 工艺损失（烧过的木棚不再是好手艺） | `matter_state.quality` | 同上 |
| 烧毁归零 | `matter_state.is_rubble = 1`（`matter.collapse`，**永不恢复**，§14 铁律） | 同上 |
| 结构坍塌 | `structures.phase = rubble`（`structure.collapsed`，tombstone 保留） | `_project_structure` + `fold_structure_snapshot`（M4-D2b） |
| 材料从账本消失 | `material_balances` 逐 ref 移动 | `_MaterialEventFields` 投影（M4-D2d） |

`MatterPayload` 现有字段（`matter_id / x / y / amount / durability / decay_rate / note`）**已经够用**
：`amount ∈ [-1,1]` 装损伤量、`durability ≥ 0` 装结算后耐久、`note` 是自由文本（可记火源引用）。
⇒ **新增 `fire.spread` 类 kind 不会带来新信息，只会带来第二套投影路径**——而 A3/schema §19.3 的
铁律是「快照路径与重放路径**不得各写一套**折叠规则」。codex W-D1 的重点是「**必须产事件**、
不许直写表」，用既有族产事件**满足**该要求（括号里的 `fire.spread` 是举例）。

### 1.2 A3 地基判定（关键）

- **火灾损伤 = 可重放**：三张受影响表（`matter_state` / `structures` / `material_balances`）**全在
  A3 的「可重放 5 张」里**，且每张都有 fold 器 ⇒ 快照 + 事件窗口可逐位重建。
- **火场中间态（哪些结构在烧、强度、燃料剩余）= 不入库** ⇒ **不进 A3 任何一类**：
  既不是第 5 张「不可重建表」，也不是可重放表。**这是本稿对批次 E 最有用的一条**：物化包
  不必为火场扩任何格式（§4）。
- 为什么火场不入库（三条论证）：① 入库的唯一收益是「读档后火继续烧」，而它的代价是新表 ⇒
  克隆（`fork.py` 有界表清单）、物化包、`corpus_blob` 格式、诊断面**四处扩展**；② 读档后火场
  归零**不破坏世界一致性**——所有持久后果都在事件流里，fold 器逐位重建，方向是 fail-closed
  （不会留半截火场污染历史），与批次 A 混沌流「纯函数 + 事件驱动、不落表」先例一致；
  ③ 蔓延需要跨 tick 的随机演化时，由**混沌流**（`sim/world/chaos.py`）按 `tick` 现抽即可，
  不需要把抽签进度落库（0009 的 `rng_state` 承接的是**同一分支**的连续性，跨档不适用）。

## 2. 事件面：四类 kind 的归属（问题②）

| 火概念 | 有无物质变更 | 既有族能否表达 | **推荐** |
| --- | --- | --- | --- |
| **起火** ignite | 否（火场诞生，无损伤） | 否——既有族每次都携带物质变更 | **新增 `fire.ignited`**：origin 结构/坐标、燃料类别、强度初值 |
| **蔓延** spread（焦化） | 是 | **能**：`matter.damage` | **零新增**：走 `matter.damage`，因果挂 0008 谱系（见下） |
| **烧毁** burnout（归零） | 是 | **能**：`matter.collapse` + `structure.collapsed` | **零新增 kind**；坍塌 `cause` 扩 `"fire"` |
| **扑灭** extinguish | 否（停止蔓延） | 否 | **新增 `fire.extinguished`**：`fire_id` + 终结原因 |

**为什么边界事件值得新增（信号 ≠ 状态）**：① 混沌/生态机制（W-D1 语境下 D 依赖 A+B）需要
「起火了」这个**可订阅信号**；② 叙事面要能说「那场火」（因果根），而损伤事件本身只说「焦了」；
③ 谱系（0008 `parent_seq` / `parent_branch_id`）需要一根**根事件**——损伤事件全部挂在它下面，
因果链才闭；④ 若将来火场要持久化，事件源已就位（fold 器可后补，成本低）。

**因果链怎么接（不扩既有 payload）**：`matter.damage` / `matter.collapse` / `structure.collapsed`
的 payload 是 `extra="forbid"` 闭合集 ⇒ **不给它们加 `fire_id` 字段**（那是 schema 变更，且会把
火 id 复制到每一条损伤上）。用 0008 已有的谱系列：火损伤事件的 `parent_seq` 指 `fire.ignited`
的 seq（同分支）或 `parent_branch_id + parent_seq`（跨分支）。**这正是 0008-d 那一族的用法**。

**事件预算（W-D3，钉「事件驱动非 per-tick」）**：蔓延若每 tick 产一条 damage ⇒ 事件风暴。
推荐**按场聚**：一场火每「累计焦化量 ≥ 阈值」或「每 K tick」发一条 damage（`amount` 累计、
`note` 记火源），与混沌注入判据同款（20–150 条/游戏日量级，pi 的 `CHAOS_*` 红线同思路）。
阈值与 K 由 pi 定标机定，本稿只给口径。

**K11 P3 纪律对本面的效力**：新增 kind 须①在 `EventKind` 登记字符串、②建 payload 模型
（`extra="forbid"` + 域约束）、③登记 `event_validation.PAYLOAD_MODELS`（闭合集唯一 schema 真相源）、
④API/WS 侧**零投影**（火灾不是权力面，但同样不进任何出站体）。⚠️ codex `test_event_kinds_closed`
断言「kind 集不含 authority 族」+「`len(PAYLOAD_MODELS) == len(EventKind)`」⇒ 新增 `fire.*`
**不撞**那条钉；真正要守的是**不得新增 authority 族 kind**（裁 24 的「不新增安规面」只约束权力）。

## 3. 与 `npc_power` 的交叉：烧毁对权力行的影响（问题③）

**推荐：原样保留，一行不动；机制面算出 delta 后照常 `PowerStore.apply`。**

| 方案 | 判定 | 理由 |
| --- | --- | --- |
| **原样保留**（推荐） | ✅ | 权力语义是「该 NPC 面对玩家的权势标量」；火灾对它的影响**是机制判断**（Claude 的 `sim/npc` 域），数据面不可推导 |
| 删行 | ❌ | 破坏 A7 铁律「**无行 = 未表态，调用方兜底 0**」（删行后该 NPC 的权力被静默重置为 0）；且**删历史**与 C6「历史不可销毁」方向冲突；库里也留不下「谁烧的、何时删的」 |
| 失效标记（`power_level=0` 或加 `burnt` 位） | ❌ | `power_level=0` 与「平权」**同值** ⇒ 语义塌陷（分不清「被烧到平权」与「本来就平权」）；加 `burnt` 位 = 给 D-10 不可见的表塞一个语义混杂列，且与 A7 的量纲/衰减游标纪律打架 |

**与 A7 fail-closed 语义的对齐**：A7 的 fail-closed 是「**输入非法 / 分支不可写 ⇒ 零写**」，
不是「状态变化时删改行」。火灾的正确姿势 = 机制面算出 delta → 照常 `apply`（照旧夹取 + 如实
上报 `clamped`）。**若机制面要表达「此 NPC 已随火场湮灭」**，那是**人物退场**语义，不属于
`npc_power` 域（该走 npc 存在性/隐藏档，Claude 域）——本稿只做**边界登记**，不预先加列。

## 4. 物化单扩界（批次 E 准备，问题④）

A3 物化四问在火灾后的增量（**结论：包格式不变、原因码集不变，只多一条钉子与一条 fail-closed 声明**）：

| 四问 | 火灾增量 |
| --- | --- |
| ① 包里装什么 | **不含火场**（运行态不入库）。`corpus_blob` 仍只收 3 张不可重建语料表 + `npc_power`（A7 已登记为第 4 张，格式归批次 E）——**火灾不新增第 5 张** |
| ② 展开 + `agent_override` 应用次序 | **不变**。火灾损伤经 fold 器在「快照 + 事件窗口」阶段落，`override` 仍在其后套 |
| ③ `rng_state` 按 anchor 存 | **不变**（蔓延若用混沌抽样，其状态包仍随 anchor 存；火场不额外带状态） |
| ④ 不可重建表必须进包 | **判据不变且更清晰**：火灾只动**可重放**表 ⇒ A3 §3.2 条件 2「语料行集与包一致」不受火灾影响（这是本稿对批次 E 最实质的贡献：**火灾不会让「回退前的当前值」冒充「回退点的历史值」**） |

**新增一条 fail-closed 声明 + 一条照妖镜钉**：

- 声明：`kind="anchor"`（历史点读档）**不还原火场** ⇒ 回退到「火正烧到一半」的档，展开后火不再
  续烧（世界一致：已发生的焦化/坍塌在事件流里，未发生的蔓延是未来）。方向 fail-closed。
- 钉子形态（照妖镜体例，批次 E 施工时落）：在 `anchor.seq` **之后**注入一批火灾事件 ⇒
  物化结果**逐位不变**（证明读档不吸收未来的火）。

## 5. 六个待裁点 → 推荐采法（= 下一单施工案）

| # | 待裁点 | 推荐采法 | 理由 / 改动成本 |
| --- | --- | --- | --- |
| 1 | 火场是否持久化 | **不持久化**（零新表零新列） | 收益（读档续烧）远低于四处扩展成本；方向 fail-closed；混沌按 tick 现抽（§1.2） |
| 2 | 四类 kind 归属 | **2 新（`fire.ignited`/`fire.extinguished`）+ 2 走既有族**；`spread` **不独立成事件** | 避免第二套投影路径（§19.3 铁律）；spread 若日后被生态机制当**信号**订阅，再加不迟（届时字段与 damage 不重叠） |
| 3 | 坍塌原因枚举 | 扩 `StructureCollapseCause = +"fire"` | **不混 `damage`**：火焚与外力砸在审计/叙事上必须可区分；扩枚举成员**不是**新 kind（不撞红线 A③），成本 = Literal 一行 + fold 分支 + 钉 |
| 4 | 烧毁材料的账本去向 | 扩 `MaterialMoveReason = +"burned"`，`to_ref="world:burned"`（`material.moved`） | **材料守恒**（T1 `test_assertions_conservation`）：烧毁不产 `to_ref` ⇒ 账本凭空少一份 ⇒ 撞守恒钉。`world:*` 前缀是既有外部基准语义（允许净负）。**不混 `build_consumed`**（审计会说成「盖房子烧的」） |
| 5 | 因果链载体 | 用 0008 **谱系列**（`parent_seq` / `parent_branch_id`），**不给 damage payload 加 `fire_id`** | 既有 payload 是 `extra="forbid"` 闭合集；加字段 = schema 变更 + 火 id 复制到每条损伤 |
| 6 | 烧毁对 `npc_power` 行 | **原样保留**；机制面显式 `apply`；删行/失效标记全否 | 破坏 A7「无行 = 未表态兜底 0」+ 与 C6 方向冲突（§3） |

**事件预算口径**（不占待裁点，随 ② 落）：蔓延损伤**按场聚合**发事件（W-D3「事件驱动非 per-tick」），
阈值由 pi 定标机定。

## 6. 施工清单（下一单，本单零代码）

| 文件 | 改动 |
| --- | --- |
| `sim/core/events.py` | `EventKind` 加 `FIRE_IGNITED` / `FIRE_EXTINGUISHED`；两个 payload 模型（`extra="forbid"` + 域约束）；`StructureCollapseCause` 扩 `"fire"`；`MaterialMoveReason` 扩 `"burned"` |
| `sim/core/persistence/event_validation.py` | `PAYLOAD_MODELS` 登记 2 个新 kind（闭合集唯一真相源） |
| `sim/core/persistence/npc_store.py` | 投影分派：`fire.*` **不投影**（无物质变更）；`structure.collapsed(cause="fire")` 走既有坍塌分支（**不写新分支**） |
| `sim/core/persistence/fork.py` | **零改动**（火场不入库 ⇒ 有界表清单不变） |
| 迁移 | **零迁移**（无新表无新列；枚举成员是 Python 侧 Literal，非 DB 约束） |
| `sim/tests/test_m5_fire_events.py`（新） | kind 登记闭合 / payload 域约束 / 损伤经既有族落库且 **events 之外零写表** / 守恒（烧毁后 `material_balances` 净额）/ cause 枚举 / 谱系可解析 |
| `sim/world/fire.py`（Claude 域） | 火场运行态；只产 `WorldEvent`，**不碰 store**（C4 唯一写路径） |

## 7. 缺口与风险

| 缺口 | 影响 | 归属 |
| --- | --- | --- |
| 蔓延事件聚合阈值未定 | 事件量级未定（W-D3 判据需要 N） | pi（定标机） |
| 「火正烧」在读档后不续 | 产品可见差异（世界一致但火没了） | Claude 域（是否需要续烧由机制面定；续则本稿 §1.2 的成本表重新评估） |
| T3 破坏类样本缺火灾题面 | codex W-D2 已登记「机制施工时随语料 CR 加，不预扩」 | codex（机制施工时） |
| 火灾对 `npc_power` 的 delta 语义未定义 | 数据面已就绪（照常 `apply`），语义待机制面 | Claude（`sim/npc`） |

## 8. 施工落地记（M5-A9，裁 33 落卡）

裁 33 逐条采 A8 推荐（五处全采）：两枚举成员（坍塌 `cause="fire"`、材料
`reason="burned"` + `to_ref="world:burned"`）、**2 新 kind**（`fire.ignited` /
`fire.extinguished`）、蔓延走 `matter.damage`、烧毁走 `matter.collapse` /
`structure.collapsed`、火场不改 `npc_power`。

**三处与预研稿不同的落法（原因记录）**：

1. **落了 `fires` 表**（0014），而预研 §0/§1.2 写的是「火场中间态不入库、零新表」。
   落地口径 = **折中且更严**：表只存**生命周期**（起火/熄灭两态），**仍然不存火势中间态**
   （强度/燃料/蔓延半径一律不入库）⇒ §1.2 的核心结论不变：A3「不可重建」**不增第 5 张**，
   物化包**不为火扩格式**。之所以要这张表：K12 **F2** 禁「只存在于内存的火势」，火场必须是
   **事件流的纯函数投影**；有表 + fold 器才有「读档回来火还在不在」的可判定载体。
2. **不落快照双列**（派单写「快照双列 CHECK」）：fires 是事件纯函数投影，重建靠
   「快照 + 事件窗口重放」，**无快照指针语义**；加了是无人写入的**死列**（未来谎言）。
   本表真正的成对不变式是 `(ended_tick, end)`，已落 `ck_fires_end_pair`；批次 E 若要火势
   物化基准点，随那一单加列 + 同款 CHECK。
3. **蔓延事件按场聚合**：裁 33 沿用 W-D3 口径「无状态变更零事件 / 每 tick ≤1 条」，
   N 值仍由 pi 定标机定（P11），本层不设常量。

**A3 分类同步**：`fires` 登记进 A3 的**可重放**族（与 `npc_power` 的第 4 张不可重建表正相反）。
