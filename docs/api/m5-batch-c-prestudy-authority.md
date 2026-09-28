# M5 批次 C 协议面预研：权力牙齿 + anchors CRUD/切列契约草案 + 复用面清单

> 能力域：接口 / 兼容性（kilo） | 状态：**提案稿（预研），零代码零 schema 改动**
> 派单：Claude 主树 `.orca/talking.txt`「M5-K4（提前派，提案制）」（2026-09-28）
> 门禁：本稿只出**协议面结论 + 契约草案 + 待裁点**。**不改** `sim/**`、`shared/**`、`client/**`，不碰 `shared/protocol.ts`。
> 依据：DESIGN §13 加内容六项 / §18 缩范围序第 5 位 / §10 界面双层铁律 / §12 双轨存档 / §14 事件是真相；
> `docs/arch/m5-plan.md` §批次 C ｜ 裁 21-C②（不预砍）｜ 裁 24-C（批次 C 验收判据待 codex 提案）｜ 裁 26-C④（protected 无写入方暂不切列）
> 上一轮：M5-K3 批次 B 四面已收编（main `9f0852f`），本稿的「复用面清单」即以它为基线。

---

## 0. 速览

**结论八条**

1. **立场**：批次 C 的机制本体（§13/§18 未展开，`m5-plan` 明写「**本骨架不发明机制**」）**不是本稿能定的东西**——本稿只回答「**任何机制落地时，协议面必须满足什么、哪些候选面可选、哪些一律不做**」，并把机制相关的分歧点变成**待裁项**交 Claude/codex。
2. **协议面零新增是默认答案**：权力牙齿若以「言语/感知/计划」表达，**现有 `perception` + `monologue` + `state_delta.plan` 三面已足够**（沿用裁 21-A D-4「死 schema 防线」：无触发场景不建帧、不预留字段）。
3. **`perception.sense` 不扩**（D-12）：权力不是新感官，是既有感官（看/闻/触/直觉）里的叙事内容——「威势」「怠慢」是 sight/interoception 的第一人称描述，不是新 channel 值。
4. **`monologue.form` 是否扩是唯一真待裁**（D-11）：命令/通牒/密谋都是言语，扩 form（如 `order`）= 扩枚举（minor）+ 投递路由表一行（K8 契约的 `MONOLOGUE_DELIVERY_ALL/SELF`）；复用 bubble/plan 则零改动。**代价对比决定是否值得扩。**
5. **`protected` 切列是一次开关式切换，不是长期双源**（§3.2）：读路径从「派生（max updated_at）」换成「读列」，**存量回填是必要前置**（否则全 `false` ⇒ DELETE 末梢的 409 保险丝静默失效）。
6. **🔧 新发现（切列前必须裁）：删末梢不补位 ⇒ 存续「无 protected 行」是合法状态**（`anchors-api.md` §1.4 已定「删末梢后剩余档不自动补位」）。切列后 `/api/anchors/current` 若以 `protected` 为判据，将在这种合法状态下回 404——**与列表里明明有档矛盾**。契约须补保底条款（D-14）。
7. **🔧 新发现（CRUD 契约缺口）：删档后 WS 仍认它存在**。`ws.py::_ANCHOR_IDS` 是**只增不减的集合**（`register_anchor_id` 只加、无摘除口），`load_anchor` 只查这张表 ⇒ 生产 hook 接线前，**删掉一档后 `load_anchor` 仍回「成功 + 全量快照」**（假成功）。契约须要求 DELETE 同步摘除，或把 `load_anchor` 的存在性判定换成查库（D-15）。
8. **批次 C 对批次 B 协议面的复用面共 9 项**（§4），其中三处带**陷阱**：快进摊还预算（权力随时间累积/衰减 ⇒ 批次 A 依赖，但摊还与广播抑制口径耦合）、`frames_of` 两帧出口（多帧纪律已成型）、锚点标签注册表（新增 `name/story_label` 供数，别退回只注册 id）。

**待裁导航**：D-10~D-13（权力牙齿协议面）见 §2.5；D-14~D-16（切列/CRUD）见 §3.6；汇总见 §5。**建议先裁 D-10（是否需要结构化可见面），再裁 D-14（`/current` 保底口径）**——这两条不定，后面的施工面无法排。

---

## 1. 证据盘点

### 1.1 权力牙齿的现状：零实现、零契约、判据未裁

| 事实 | 证据 |
|---|---|
| 领域目录**不存在** | `ls sim/world/` → `fog/map/matter/pathfinding/structure/support_graph/weather`，**无 `authority/`** |
| DESIGN 只给了一行名字 | `DESIGN.md:388`「加内容六���：时间刻度 / 不成文规矩 / **权力牙齿** / 巧合连锁 / 身体会坏 / 生命始终」；`DESIGN.md:115` 目录列了 `authority`（§5 占位，标注 M5） |
| 骨架明写「不发明机制」 | `m5-plan.md:118`「§13/§18 未展开机制细节，**本骨架不发明机制**；具体形态待 Claude 派单前定」 |
| 验收判据**未裁**（可证伪断言待补） | `m5-plan.md:121` + 裁 21 §6-③「批次 C 开工前须先补这一裁」＋ 裁 24-C：由 codex 出可证伪断言提案，**本裁不预填** |
| 依赖面 | `m5-plan.md:120`：批次 A（时间刻度——**权力随时间累积/衰减**）＋ M3 关系/知识传播底座（已收官） |
| 安规风险点（已由规划点名） | `m5-plan.md:119`「权力牙齿与念头注入的边界是 M5 最高安规风险点」；§10 原文「抱怨必须是自我怀疑，**绝不能是被操纵感**」 |

> 判读：**协议面此刻能做的最有价值的事，是把「机制落地时会被绊倒的协议面决策」提前全部摊开**，而不是替机制选型。本稿三块即按此分工。

### 1.2 现有协议面清单（哪些面可承载 / 哪些必封）

| 面 | 契约现状（`shared/openapi.json` 真源） | 权力牙齿适配度 | 备注 |
|---|---|---|---|
| `perception`（narrative） | `sense ∈ {sight, sound, smell, touch, interoception}` + `content`（第一人称、无数值无系统词）+ 可选 `form` | **高**：威势/敬畏/怠慢都是既有感官的叙事内容 | 扩 `sense` = 扩枚举（minor）但语义可疑（D-12 主张不扩） |
| `monologue`（narrative） | `form ∈ {bubble, thought, plan}` + `content`；投递面路由 `bubble/plan` 广播、`thought` 定向本人（`ws.py:328-329`） | **高**：命令/通牒/密谋天然是言语 | 「私密 vs 公开」两态已有路由承载（D-11） |
| `state_delta.plan`（render） | 顶层可选 `PlanDelta{rtoken, text}`（K10 落地，`additionalProperties:false`） | **中高**：权力驱动的意图（顶撞/服从/缄默）写进计划文本即可 | **零 schema 改动**；注意既有债：驱动层 `if moved:` 才广播（plan-only 不上线，K9 记的未修债） |
| `state_delta.actors`（render） | 封闭 schema，实体视觉属性 | **低**：只当视觉线索（站位/光效/旗帜），**禁位阶数值** | 扩 actors 需改封闭 schema，成本高、收益低 |
| `timescale`（control） | 模式/激活态广播 | **零**（已占名给战斗时间尺） | 扩它会混淆「战斗慢镜」与「刻度」，K1 §2.5 已否决过 |
| `session_state`（session，K3） | 连接期初值 + 游标指针 | **低**：属会话/元信息面，权力状态不入 | 复用面（§4）但**不承载权力** |
| HTTP `/api/anchors` | 玩家档 CRUD 契约（读两路由已落地） | **零** | 与权力无关 |
| 新 S→C 帧 | —— | **默认不建** | 死 schema 防线（D-4 `rate_change` 先例） |

### 1.3 anchors 现状：`protected` 列已落库，但**无写入方**

| 事实 | 证据 |
|---|---|
| `player_anchors.protected` 列**已落库** | `models.py:134` `protected: Mapped[bool] = nullable=False, default=False`；迁移 `0008_m5_fork_identity`（D3-a/裁 9） |
| 读路径**仍是派生** | `anchors.py::list_items/get_item` 用 `_max_updated_at()` 算 `protected`（模块 docstring 明写「等 POST 落库时改为构造时计算写列」） |
| `/current` 用派生 | `anchors.py::current_item()` = `order_by(updated_at desc, id desc).first()`，`protected=True` 硬编码 |
| **无任何写入方** | 全仓无 `PlayerAnchor(protected=...)` 写入、无 POST 路由（anchors.py 只有两个 GET） |
| 切列裁决已定序 | 裁 26-C④：「protected 无写入方暂不切列：采——**POST/CRUD（Claude 域）落地单再切**，登记批次 C 检查单」 |
| 末梢的**四个消费者** | ① 列表 `protected` ② `/current` ③ WS 首帧 `session_state.anchor`（取 `current_item()` 同一行）④ WS 标签注册表 `_ANCHOR_LABELS`（K3 新增） |

---

## 2. 块一：权力牙齿的协议面

### 2.0 立场声明（先划界，避免越权）

- **本稿不选机制**（权力从哪来、怎么流转、谁能命令谁）——那是 Claude 架构域 + codex 安规域的裁。
- **本稿只定协议面**：①机制落地时不可协商的五条铁律；②候选承载面与成本表；③安规侧的协议面义务；④需要 Claude 裁的分歧点。
- 判据仍按裁 21-A 的成熟度要求：**没有触发场景的 schema 一律不建**（宁可后补，不留死契约）。

### 2.1 五条不可协商的协议面铁律（从批次 A/B 的血泪总结）

| # | 铁律 | 依据（已发生的教训） |
|---|---|---|
| R1 | **死 schema 防线**：无触发场景不建帧、不预留字段、不扩枚举 | 裁 21-A D-4：`rate_change` 只登记预留名、**不定义 schema** |
| R2 | **出戏边界**：位阶/影响力/权重/人缘等**任何数值或系统词**不进任何帧（含 narrative）；需要玩家可见就用**叙事化标签**（`story_label` / `content` 先例） | §5/§10 + `banned_words` 两套口径（戏内 narrative 过扫描，戏外 session 不过） |
| R3 | **可见性走投递面路由，不新造机制**：「私密」（心腹密谋/腹诽）与「公开」（当众号令）是既有 form 路由的职责（K8 契约） | `ws.py:328` `MONOLOGUE_DELVVERY_ALL/SELF`；thought 定向本人是有先例的隐私面 |
| R4 | **事件是真相、帧是投影**（§14）：权力变更必须先落世界事件（可重放、重连可重建），WS 帧只是投影；**没有事件的面不许有帧** | K8 独白「事件进流 + WS 投影」模式；无事件面 ⇒ 重连后前端无法重建该状态 |
| R5 | **兼容三档成本表**（`versioning.md` §3）：扩枚举（minor，多端联动）＞ 加可选键（minor，需双端同时理解）＞ 加新 type（minor，旧端静默忽略）。选**最便宜且够用**的 | 裁 21-A D-4 与 K3 实践（新增 `session_state` type 是最便宜档） |

### 2.2 候选承载面矩阵（四案 + 成本）

| 案 | 形 | 承载什么 | 出戏风险 | 兼容成本 | 何时才该用 | 评价 |
|---|---|---|---|---|---|---|
| **A. 零 schema 改动**（推荐默认） | 权力表达全部经 `monologue`（bubble/plan/thought）+ `perception`（既有 sense）+ `state_delta.plan` 文本 | 命令/通牒/密谋/顶撞/服从/威势的**可观察表达** | 低（都是第一人称文本，走既有 banned/操纵感扫描） | **0**（连生成物都不变） | 绝大多数情形 | ✅ **默认采** |
| B. `monologue.form` 扩值（如 `order`/`decree`） | 扩枚举 + 投递路由表加一行 | 权力言语需要**独立 form 语义**（前端分样式/分面板） | 低 | 枚举扩（minor）：`MonologueMessage.form` / `PerceptionMessage.form` / `MonologueReaction.form` 三处 + 投递表 | 当「权力言语」在 A 案下与「计划/气泡」不可区分时 | ⭕ 待裁 D-11 |
| C. `state_delta` 新增顶层可选数组（如 `standing[]`） | 参照 K10 `plan` 的先例（顶层可选数组 + 窄组件 + `additionalProperties:false`） | 权力**结构化**、可渲染（如旗帜/站位/徽记） | **中**：极易夹带数值（rank/influence）⇒ 破 R2 | 组件 + 属性 + 生成物 + 前端类型断言四处 | 当权力**必须在渲染上可观察**且**只有视觉线索**时 | ⚠️ 仅在 C 必要时；禁数值 |
| D. 新 S→C 广播帧（如 `authority_shift`） | sim 驱动的状态变更广播（`timescale` 同型） | 权力**跃迁**（升/降/失权）的即时告知 | 中 | 新 type（minor）＋投影实现 ＋ 事件 | 仅当「跃迁」本身是玩家必须知道的**事件性事实**（而非可从言语/计划推出的结果） | ❌ **批次 C 一律不预建**（R1） |

**主张**：**A 为默认，B 待裁（唯一有理由的扩面），C 需举证，D 不建**。若最终裁「权力完全不可见」（纯 Agent 内部），协议面**零改动**——这也是一个合法结局（对应裁 21-C② 的「不预砍」与可砍性：砍掉时协议面无沉没成本）。

### 2.3 安规侧（codex 域）的协议面义务——报备三条

1. **「被操纵感」是 M5 最高安规风险**（`m5-plan.md:119` + §10）。协议面能做的义务：权力类 narrative 文本**必须与 M4 念头注入走同一道扫描**（`impulse_gate` 的 banned / 操纵感 / hidden 三扫，`ws.py` M4-A2 接线段），**不新造词表**（词表是活资产，扩面按 CR 走 codex）。
2. **拒绝权必须在文本里可见**：若机制允许 NPC 拒绝玩家/上级的命令，拒绝的表达也走既有 form 面（bubble/plan），**不得只存在于事件流里**（R4 之外再加一条玩家可感知约束——否则玩家会觉得被系统推着走，正是 §10 禁的那种感觉）。
3. **不得新增「玩家不可见但影响玩家」的暗面**（暗改玩家数值/暗改关系且零表现）——这是 R2 的社会面版本：一切对玩家有后果的变更，必须有至少一个**玩家可感知**的表现面（言语/计划/感知/视觉线索四者之一）。

### 2.4 若最终裁「玩家需要看见位阶」——叙事化标签口径（复用先例）

- 参照 `story_label`（「叙事化时间标签，非 tick 数值」）与 `SessionAnchor{ name, story_label }`（K3 新增的**窄组件**）两条先例：位阶若要给玩家看，做成**窄组件 + 叙事化字符串**（如「镇上说话有分量的人」），**禁**整数/百分比/进度条。
- 组件形态建议：`{ label: string }` 单键闭组件（`additionalProperties:false`），挂在哪一面由 D-10 裁（`state_delta` 顶层可选 vs `session_state`——**注意 `session_state` 是元信息面，R2 更严**）。
- 生成物联动照旧：`openapi_ext` → 快照 → `gen-protocol` → 前端类型断言（K3 三硬判据不变）。

### 2.5 块一待裁

| # | 待裁 | 选项 | kilo 建议 | 影响面 |
|---|---|---|---|---|
| D-10 | 权力状态是否需要**结构化、玩家可见**的承载面 | ①不需要（言语/计划足够） ②需要视觉线索 ③需要数值型仪表盘 | **①**（②需举证；③违反 R2 一票否决） | 决定是否动 schema；③会连带 `versioning.md` §5 出戏边界表 |
| D-11 | `monologue.form` 是否扩（命令/通牒类） | ①复用 bubble/plan ②扩 `order` ③扩两类 | **①起步**，前端确有分面需求时再②（扩枚举是三档兼容里最贵的一档） | 枚举三处 + 投递路由表 + 前端样式映射 |
| D-12 | `perception.sense` 是否扩 | ①不扩（权力不是新感官） ②扩「威势/敬畏」 | **①** | 扩枚举成本 vs 语义增益；②会把「权力」塞进感官枚举，形成长期语义债 |
| D-13 | 权力**跃迁**是否需要 sim 驱动的 S→C 广播 | ①不（从言语/计划可推） ②需要（跃迁本身是事件性事实） | **①**（R1 死 schema 防线；真需要时按 `timescale` 的先例接线：事件先行、帧后投影） | 新 type = 新组件 + 投影实现 + 前端 |

---

## 3. 块二：`protected` 切列 + anchors CRUD 契约草案（我出契约，Claude 出施工）

> 本块是**契约草案**，不是施工单。已有契约（`anchors-api.md` §1.2–§1.4、§2、§5、§6）继续有效，本块只做三件事：①把切列的前置/顺序/回滚/一致性写成可执行条款；②补三条**已发现的契约缺口**（§3.2 缺口 1、§3.3 缺口 2、§3.4 缺口 3）；③列待裁。

### 3.1 切列的前置依赖与顺序（裁 26-C④ 的可执行化）

```
[前置 0] POST 路由落地（写入方存在）            ← Claude 域，CRUD 单
   ↓ 必须同事务：清旧末梢 protected=false + 写新档 protected=true（anchors-api §6.1 A2/A3）
[前置 1] 存量回填：UPDATE player_anchors SET protected = (updated_at = 全表最大)
   ↓ 独立迁移 0009（不夹带进 0008；0008 已收编）
[前置 2] 读路径切换：list_items / get_item / current_item 全部读列
   ↓ 一次性开关式切换，不长期双源
[验收]  §3.2 一致性矩阵四条 + §3.3 契约缺口钉子
```

- **回填是不可省的前置**：不回填 ⇒ 全表 `protected=false` ⇒ DELETE 末梢的 409 保险丝**静默失效**（数据不丢，但保险丝没了）。这正是「无写入方暂不切列」这条裁的实质原因。
- **回填的判定式**必须与派生式**逐字同源**（`updated_at` 最大者；同刻按 `id` 降序取一），否则会出现「回填后有两档 true」——见 §3.2 缺口 1 的不变量钉。

### 3.2 切列契约条款（含三条缺口）

**条款 C1（切换性质）**：读路径从派生切列是**一次性开关**；切列后 `protected` 列是**唯一真相源**，派生代码删除（不留双读）。理由：双源必然漂（派生读 `updated_at`、列存构造时快照，中途改名/删档后两者会分叉）。

**条款 C2（一致性矩阵——四个末梢消费者必须同源）**

| 消费者 | 位置 | 切列前 | 切列后（契约） |
|---|---|---|---|
| 列表 `protected` | `anchors.py::list_items` | 派生（max updated_at） | **读列** |
| `/current` 判据 | `anchors.py::current_item` | max(updated_at) | **`protected=true` 的行；若无 → 保底取 max(updated_at)**（缺口 1） |
| WS 首帧 `session_state.anchor` | `main.py::_current_anchor_pointer` → `current_item()` | 同一行 | **同一行**（自动同源，无需改动） |
| WS 标签注册表 | `ws.py::_ANCHOR_LABELS` | `register_anchor_id(id,name,story_label)`（K3） | **同源**；但**删档须摘除**（缺口 2） |

**🔧 缺口 1（切列后必然踩，必须现在裁）**：`anchors-api.md` §1.4 已定「**删末梢后剩余档中的最新者不自动补位**为 protected」——于是「**全表无 protected 行**」是**合法状态**。若 `/current` 以 `protected` 为唯一判据，此时回 404，而列表里明明有档（玩家视角：刚删掉末梢 → 存档页显示有档但「当前」指针说没有）。
⇒ **契约补条款**：`/current` 判据 = `protected=true` 优先；**若无 protected 行，回退到 `updated_at` 最大者**（保底不 404），并在响应里照旧只给五键（`protected` 字段此时为 `false`，语义是「没有受保护的末梢」）。这与列表的派生式在正常态下等价，在退化态下更可用。**（D-14）**

**🔧 缺口 2（CRUD 与 WS 侧的一致性，现有实现缺口）**：`ws.py::_ANCHOR_IDS` / `_ANCHOR_LABELS` 是**只增不减**的模块级集合（`register_anchor_id` 只加；`reset_anchor_registry` 是**测试辅助**，生产不调用）。`load_anchor` 的成功判定只查这张表 ⇒ **删掉一档后，WS 仍认它存在**：
- 现状（生产 hook 未接，D3-c 之前）：`load_anchor` 已删 id → 查表命中 → 回「成功 + 全量快照」= **假成功**；
- D3-c 接线后：hook 查库失败 → 降级 `load_failed`（不假成功，但错误分类从 `bad_anchor` 变成 `load_failed`，语义可接受）。
⇒ **契约补条款**：`DELETE /api/anchors/{id}` 成功时**同步摘除** WS 注册表（新增 `unregister_anchor_id(id)`，与 `register_anchor_id` 成对）；POST 成功时照 K7 模式调 `register_anchor_id(id, name, story_label)`。**摘除是 WS 侧一行函数 + 一个调用点**（`anchors.py` 删除路由内），属 CRUD 落地单的连带施工。**（D-15）**

**条款 C3（不变量钉子）**：切列后必须常驻一条不变量断言：**`protected=true` 的行数 ≤ 1**（数据脏了就 409 之外还要能发现）。验收形态：`[T]` 插入 N 档后 `SELECT count(*) WHERE protected` 恒为 1；`[T]` 删末梢后为 0（合法退化态，呼应缺口 1）。

**条款 C4（回滚）**：切列若引发回归，回滚 = 恢复派生读路径 + 停用 DELETE/POST 的 protected 写入（列保留不删）。**回滚不需要数据迁移**（列值与派生式在正常态等价）——这是「先切读、后切写」顺序的价值。

### 3.3 CRUD 契约草案 v2（相对 `anchors-api.md` §1.2–§1.4 的增量条款）

已有契约继续有效（请求/响应五键/`name` 校验/`extra="forbid"`/404/409/422/硬删/不分页/ProblemDetail 四键形）。以下为**切列 + WS 联动所需的增量条款**：

| 路由 | 增量条款（v2 新增/收紧） | 状态 |
|---|---|---|
| `POST /api/anchors` | ①**同事务**写：新档 `protected=true` + 清其余 `protected=false`（§6.1 A2 锁 + A3 事务）；②`updated_at` 只写一次（不变）；③成功响应照 K7 模式 `register_anchor_id(id, name, story_label)`；④`400 /errors/world-not-ready` 的判据须写死：**当前活跃 loop 存在**（现 `app.state.loop`）；**分支 id 的来源需裁**（见 D-16） | ①②③ 新增；④ 半新 |
| `PATCH /api/anchors/{id}` | ①**不动** `updated_at` / `protected`（原契约已定，v2 复述为硬约束）；②成功后 WS 标签表的 `name` 应同步刷新（`register_anchor_id` 幂等覆盖即可） | ① 复述；② 新增 |
| `DELETE /api/anchors/{id}` | ①`409` 当且仅当 **`protected=true`（切列后从列读，不再派生）**；②硬删（不变）；③**成功后摘除 WS 注册表**（缺口 2）；④**不补位**：删除末梢后剩余档保持 `protected=false`（原契约已定，v2 与缺口 1 联动成对条款） | ①③ 新增 |
| `GET /api/anchors` / `/current` | ①切列后读列（条款 C1）；②`/current` 保底（缺口 1）；③**排序仍按 `updated_at`**（不变）；④无分页（§6.2 B1 维持） | ①② 新增 |

**协议面影响**：**schema 零新增**——`AnchorCreate` / `AnchorRename` / `AnchorListItem` / `ProblemDetail` / `responses.Problem` 已在 `shared/openapi.json` 快照里（待 Claude 域施工注入 ext，`anchors-api.md` §5.1 已给注入点代码）。**生成物零变更**（除非裁 `ProblemDetail.instance`——§6.4 主张不加）。

### 3.4 出游标归属与 fork 编排的接缝（读档/建档互不代劳）

- `PlayerAnchor` 内部四列 `branch_id/tick/seq/agent_override` 由**服务端**取当前活跃游标（`anchors-api.md` §1.2 已定），客户端不参与。
- **读档不自动建档**（v2 明确）：`load_anchor` 成功（K3 两帧：告知 + 全量）**不**写新 `PlayerAnchor` 行；「读档后另存一档」是玩家**显式** `POST` 的动作。理由：自动建档会让 `protected` 末梢在玩家没要求时被改写（保险丝语义被系统动作推动），且 D3-b 的 fork 编排（`locate_anchor` → `orchestrate_load_anchor`）产出的是**分支**，不是玩家档——两者是不同轨（§12 双轨）。
- D3-b 编排的 `register_child` 回调与本块**无耦合**：它登记的是**子分支 id**（`_ANCHOR_IDS` 是玩家档 id 集），两者不要混用同一个注册表。**（已在 K3 复核：`register_anchor_id` 只在 anchors.py 落库路径被调）**

### 3.5 块二待裁

| # | 待裁 | 选项 | kilo 建议 | 影响面 |
|---|---|---|---|---|
| D-14 | 切列后 `/current` 的判据（**缺口 1**） | ①仅 `protected` ②`protected` 优先 + 无则回退 max(updated_at) ③切列后强制补位（推翻「不补位」） | **②**（③推翻已定契约；①在合法退化态下 404 与列表矛盾） | `/current` 语义 + 钉子 + 文档 §1.0 |
| D-15 | 删档后 WS 注册表摘除（**缺口 2**） | ①加 `unregister_anchor_id` + DELETE 调 ②`load_anchor` 存在性判定改查库 ③不动（靠 D3-c hook 兜底） | **①**（一行函数 + 一个调用点，最小闭环）；③会留「假成功」窗口 | WS 网关 + anchors 删除路由 |
| D-16 | `POST` 的 `branch_id` 来源 | ①当前活跃分支（§1.2 现行约定） ②显式指定 ③读档后的新分支 | **①**（客户端不参与游标；②破「不采客户端自报」口径） | 400 判据实现 + 与 D3-b 的接缝说明 |

---

## 4. 块三：批次 C ↔ 批次 B 协议面复用面清单

> 以 M5-K3（main `9f0852f`）落地的协议面为基线。「陷阱」列是**已知的、会咬人的**耦合点。

| # | 批次 B 资产 | 位置 | 批次 C 怎么用 | 陷阱 / 注意事项 |
|---|---|---|---|---|
| R-1 | `session_state` 消息（连接期初值 + 游标指针） | `openapi_ext._WS_SCHEMAS` / `ws.py::session_state_payload` | 若权力状态需在**接入**即可见（当前极可能不需要），它是天然的「初值帧」；否则**不动** | 它是**元信息面**（R2 更严）：位阶数值进这里最容易破边界；扩字段要重过三硬判据 |
| R-2 | `frames_of()` 两帧出口 | `ws.py::frames_of` | 若「读档/建档」类动作需要「动作帧 + 状态帧」两帧（如 DELETE 后前端要立刻知道当前指针变了） | 单回复通道已是 `dict \| list[dict]`；**新增两帧场景要同步更新 `ws-protocol.md` §4.4 的例外清单** |
| R-3 | `ControlState`（连接级会话态） | `ws.py::ControlState` | 玩家侧的权力相关偏好（如「我是否接受某人的命令」）若需要会话记忆，挂这里 | **不进 GameClock**；断线即丢（跨连接不延续） |
| R-4 | `step_fast_forward` 限预算摊还 + 预算共享 | `ws.py` | 批次 C 依赖批次 A（权力随时间累积/衰减 ⇒ 可能需要「快进一段时间看权力变化」） | ⚠️ **摊还与广播抑制耦合**：快进期抑制逐帧 `state_delta`，若权力走 `plan`/actors 面，则**快进期间该面的更新不上线**——这是可接受的（终态全量会补上），但**必须在文档写明**，否则会被当 bug |
| R-5 | 锚点标签注册表 `_ANCHOR_LABELS`（`name`/`story_label`） | `ws.py::register_anchor_id` | CRUD 落地单的供数点（K7 模式）：POST 成功后注册、DELETE 成功后摘除 | ⚠️ **只增不减**（缺口 2）；新增注册点时**必须成对写摘除**；老调用点（只传 id）仍在，标签退化为空串 |
| R-6 | `/api/anchors/current` 路由 + 路由顺序纪律 | `anchors.py` | CRUD 落地时新增任何路径参数路由（如 `/api/anchors/{id}/…`）都要**排在静态段之后** | ⚠️ K3 的坑：静态段必须声明在路径参数**之前**；`TestCurrentAnchorRoute` 已有白盒顺序钉，CRUD 新路由请复用同一钉法 |
| R-7 | 叙事化标签先例（`story_label` / `SessionAnchor` 窄组件） | `anchors-api.md` §1.1、`openapi_ext._SUB_SCHEMAS.SessionAnchor` | 位阶若要可见，做成同型窄组件（§2.4） | 禁数值；组件 `additionalProperties:false` |
| R-8 | 三硬判据管线 + 钉子命名 | `sim/tests/test_m5_batch_b_*.py` | 批次 C 的 schema 面钉子沿用：`ext↔快照逐字段相等` / `实发项 ⊆ schema 属性` / `生成物 TS 含新键` | 快照是手维护 mock（**不可从实跑 app 整份重生成**——会冲掉 operationId/summary/tags 的手写口径） |
| R-9 | 出戏边界两套口径 + `bad_advance` 式词表纪律 | `ws-dispatch-proposal.md` §5.1（11 码）、`banned_words` | 权力类 WS 拒绝面若需新 code，按词表纪律登记（我的域）；narrative 文本走既有扫描 | 词表是活资产：扩面按 CR 走 codex；不新造词表 |

**反向清单（批次 C 不该碰的批次 B 面）**：`timescale`（已占名给战斗时间尺）、`speed` 枚举 `{1,4,16}`（§10 锁）、`full_snapshot`/`state_delta` 的封闭 schema 键集（扩键要动生成物 + 前端断言）、`player_anchors` 的 `updated_at` 只写一次（改名/删档都不得推进它，否则篡改末梢归属）。

---

## 5. 待裁汇总（交 Claude；codex 出权力牙齿可证伪断言提案）

| # | 待裁 | 选项 | kilo 建议 | 阻塞谁 |
|---|---|---|---|---|
| D-10 | 权力是否需要结构化玩家可见面 | ①不需要 ②仅视觉线索 ③数值仪表盘 | **①**（③违反 R2 一票否决） | 决定是否动 schema |
| D-11 | `monologue.form` 是否扩 | ①复用 ②扩 `order` | **①起步** | 枚举三处 + 投递表 |
| D-12 | `perception.sense` 是否扩 | ①不扩 ②扩威势/敬畏 | **①** | 枚举 + 长期语义债 |
| D-13 | 权力跃迁是否要 S→C 广播 | ①不 ②需要 | **①**（R1） | 新 type 或零改动 |
| D-14 | 切列后 `/current` 判据（缺口 1） | ①仅 protected ②回退保底 ③强制补位 | **②** | `/current` 语义 + 钉子 |
| D-15 | 删档后 WS 注册表摘除（缺口 2） | ①加摘除函数 ②改查库 ③不动 | **①** | 网关 + 删除路由 |
| D-16 | `POST` 的 `branch_id` 来源 | ①当前活跃分支 ②客户端指定 ③读档后新分支 | **①** | 400 判据 + fork 接缝 |

**裁序建议**：**D-10 先裁**（决定后面三案是否还成立）→ **D-14/D-15**（切列与 CRUD 的两条缺口，越早越好，施工单开工前必须有答案）→ D-11~D-13、D-16。

**与 codex 的分工**：裁 24-C 已定「批次 C 开工前补验收判据，由 codex 出可证伪断言提案」。本稿只提供**协议面可测断言的落点**（供其引用）：`TestBatchBSchema` 同款的 ext↔快照一致性、实发项 ⊆ schema 属性、生成物含新键；以及 R2 出戏边界的递归键/值检查（K3 已有现成写法，见 `sim/tests/test_m5_session_state.py::test_no_banned_world_values`）。

---

## 6. 不在本稿范围

- **权力牙齿的机制本体**（权力来源/流转/命令-拒绝语义/累积衰减曲线）：Claude 架构域 + codex 安规域裁；本稿只定协议面。
- **批次 C 验收判据**：裁 24-C 指定 codex 出可证伪断言提案；本稿只给协议面断言落点。
- **CRUD 施工 / 切列施工 / 回填迁移 0009 / ProblemDetail 注入**：`anchors-api.md` §5 清单，Claude 域施工（我复验）。
- **`sim/core/thresholds.py` 与 perf 红线**：pi 域（K3 已注明可跑红线验证）。
- **词表扩面**（权力叙事词、命令类措辞）：安规域 codex 走 CR。
