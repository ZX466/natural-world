# M5 批次 D 火灾生态·安规威胁模型（docs/security/m5-fire-threatmodel.md）

> 维护：Codex（安全/合规/风险域）· 依据：M5-S9 派单（2026-10-02，批次 D 火灾生态安规预研 +
> S8 复验单落执行版）、m5-security-preplan.md §10.2（W-D1/W-D2/W-D3 三钉，S7 交付
> `1361783`）、m5-power-threatmodel.md（S8 同款体例：W-X 逐条展开 + 施工级钉清单按归属拆组 +
> §4 施工后复验单）、DESIGN §11（混沌注入判据）/§14（建造与破坏）/§17 M5 行、m5-plan.md
> 批次 D 行（负责域 + T1 材料守恒）、0013_power_state.py + m5-anchor-materialization-preplan.md
> （不可重建 4 张表）· 日期：2026-10-02 · 树：ZX466/codex
> 状态：**纯预研·零代码零 schema**；只出威胁模型与施工级安规钉清单，**不抢施工**——
> 钉子清单是 opencode/kilo/Claude 三方本轮施工的安规输入（他们回执对本清单逐条对齐）。
> 约束：词表零扩散（META_SHELL 8 词纪律不变）；D-10 不破；§18 缩范围序位（生态序 1 /
> 蔓延序 2）本稿只注序位，不预砍（裁 21-C②）。

## 0. 一句话 + 现状快照

**火灾蔓延的安规命题不是「火烧得对不对」，而是「一次蔓延事件族的写入面有多大、烧毁对
不可重建状态意味着什么」——两问都直接落到 D 批施工能否守住 C4 唯一写路径与 T1 材料守恒。**

现状快照（本机实测，2026-10-02）：全仓 **零** fire/ecology/wildfire 命中于生产代码
（`sim/**` 检索 fire|燃烧|蔓延|ecology|生态 仅命中两处无关测试名）⇒ **机制零实现**，
本稿是它的**安规前置**而非事后补丁；`sim/world/chaos.py` 已落 `chaotic`/`chaotic_at`
（批次 A 面，火源演化要读它）；T3 语料 `sim/tests/fixtures/t3_corpus.py` 现状 **69 条**
（六类 A12/B11/C11/D11/E11/F13，无火灾/生态题面 ⇒ W-D2 缺口**现在仍成立**）；
M4 建造破坏数据面已收官（`0006_structures`/`0007_material_balances` + `structure.*`/
`matter.*`/`material.moved` 事件族），蔓延**接在坍塌之后**（m5-plan 批次 D 行）。

## 1. W-D 逐条展开

### 1.1 W-D1：蔓延/生态每一步状态变更必须产事件（禁直写投影表）

| 项 | 内容 |
|---|---|
| ① 攻击面 | 谁 = 蔓延引擎作者（Claude 域 `sim/world/fire`·`sim/world/ecology` 类新模块）＋ opencode 数据面施工者；从哪个面 = **物质/结构投影面**（`matter_state`/`structures`/`material_balances` 的行写）；什么输入 = 「批量物理模拟」式的批量直写（`session.execute(update(...))` 批量 UPDATE、`session.add` 裸写、`.update({k: v for ...})` 字典直改投影），以及「物理引擎算完一次性落表」的正当性话术 |
| ② 守卫复用 | C4 唯一写路径：`SqlEventStore.append` 是 events 落库唯一入口（`store.py`）；`flush_tick`/`flush_rows`（`sim/core/flush.py`）把 `loop.pending_events` 转 store 行，投影经 `projection` 回调同事务写（`npc_store.py::flush_tick`）；`PAYLOAD_MODELS`（`event_validation.py`）是 kind→payload **唯一 schema 真相源**，新 kind 必须在此登记（注释即如此写）；既有 damage/collapse 事件族已把物质损伤锁进事件流（`MatterPayload` 域约束、`matter_event` 工厂、`test_t1_m3_matter_bounds`） |
| ③ 缺口 | 蔓延若以「这是物理模拟不是 Agent 行为」为由**在 C4 之外直写投影**，则火灾成为世界档里**唯一一块无事件源的状态**——不可重放、不可审计、不可回放逐位一致（T2/C5 破），且违背 §19.1「事件唯一写路径」。**对照 0008 四件 CHECK 先例**：0008 把「可表达约束进 DB」立为仓内判据（成对不变式落 `ck_events_parent_branch_pair`/`ck_knowledge_evidence_pair`）⇒ 蔓延新增的成对不变式（如「燃烧量 ≤ 该格存量」）应同样落 DB CHECK 或至少落钉，而不是靠 Python 侧 if |
| ③ 施工级钉 | 见 §4 **D-1..D-7**（数据面组；含分叉克隆 D-7） |
| ④ 材料守恒（T1 第 6 条） | 蔓延必须走既有 damage/collapse 事件族——**烧毁的物质不能凭空消失或复制**（m5-plan 批次 D 验收口径明写「燃烧消耗材料」）。既有守卫：`TestMaterialConservation`（`test_t1_m4_material_balance.py`）+ `assert_material_balances_conserved`（golden `conservation.py`，裁 17-1 逐位相等不给浮差）。**新缺口**：燃烧把「结构里的材料」转成「灰烬」需要一条 `material.moved` 语义（from=结构 ref / to=灰烬 ref）——若实现只减 `material_balances` 而不产 `MATERIAL_MOVED` 事件，折叠重放会与投影不等 ⇒ 逐位相等断言当场红 |

### 1.2 W-D2：玩家破坏类念头（纵火/滥砍）的入站边界

| 项 | 内容 |
|---|---|
| ① 攻击面 | 谁 = 玩家（经 WS `player_impulse`）；从哪个面 = **入站 impulse 面**（`ws.py` M4-A2 段已接 `impulse_gate` 三扫）；什么输入 = 「去烧了那片林子」「把山那头的树全砍了」类**破坏类指令**（玩家可下达世界改写级祈使） |
| ② 守卫复用 | `impulse_gate` 三扫（I-1 banned / I-3 操纵感）+ T3 门禁 69 条（`test_t3_gate.py`，语料↔文档双向同步钉 `test_all_case_ids_present_in_doc`）；既有六类（A12/B11/C11/D11/E11/F13）**零火灾/生态题面** |
| ③ 缺口 | **无新代码缺口**（闸门已接线），但**语料缺口成立**：破坏类题面缺席 ⇒ 三扫对「纵火」这类真实攻击词既无正样本（证明闸门会拦）也无反例（证明闸门不误伤「灭火」「避开火场」这类合法表达）。按 S7 定调：**随语料 CR 加，不预扩**——D 批机制施工时才补（fire/eco 语料与 `t3-corpus.md` 同步改，防漂移） |
| ③ 施工级钉 | 见 §4 **D-13**（语料组，随语料 CR）+ **D-11**（意图闸不被绕） |
| ④ 分类安全 | 机制面新增钉：火源演化必须走 `impulse_gate` 或混沌确定性流，**不得**让「玩家念头」直写火场格（绕过意图闸走「非 LLM 直改世界」，m5-plan 批次 D 安规行明写此约束） |

### 1.3 W-D3：蔓延事件预算同混沌注入判据（事件驱动非 per-tick）

| 项 | 内容 |
|---|---|
| ① 攻击面 | 谁 = 蔓延引擎作者；从哪个面 = **事件量面**（`loop.pending_events` 每 tick 条数 → `flush_rows` → events 表行）；什么输入 = 「每 tick 产蔓延事件」的 per-tick 实现（火场是扩散计算 ⇒ 每格每 tick 一条 `matter.damage` 天然成立） |
| ② 守卫复用 | DESIGN §11 注入点判断标准「这个结果会不会成为一段可以讲述的故事？会，就注入」＋「确定性混沌 vs 注入真随机」二分；`docs/perf/budget.md` §1 事件 apply 行「稳态 ~20 事件/tick（50 NPC 决策产出），p99 50 事件」与每 tick 硬预算 16.6ms（p99 ≤8.3ms）；bench 红线 `APPLY_P99_LIMIT_MS = 0.04`/`TICK_P99_LIMIT_MS = 8.3`（`sim/tests/bench/thresholds.py`） |
| ③ 缺口 | per-tick 蔓延事件会把事件 apply 与存储成本放大 (O(\text{火场格数}))；一旦火场铺满（32×32 默认图占位 `main.py::_default_map` ⇒ 1024 格；内容管线后更大），每 tick 数十至数百条蔓延事件即烧掉整个 tick 预算 ⇒ **蔓延必须是「事件驱动」而非「格驱动」**：同一因果只产一条聚合事件，其余步进折叠进投影 |
| ③ 施工级钉 | 见 §4 **D-14**（预算钉：每 tick 蔓延事件 ≤1 条）+ **D-2**（kind 登记闭合）；N 由 pi 在定标机定（§5 不设新常量） |
| ④ 与混沌的关系 | 蔓延事件预算判据**沿用混沌注入判据同款**（可讲述才产事件），不是新标准；连续 10 tick 同因事件 >N 即实现偏差 |

## 2. 火灾蔓延的事件爆炸半径（写入边界，对照 0008 四件 CHECK 先例）

**问题**：一次蔓延事件族 = 多少行写入？分三层给边界，判据均可证伪。

| 层 | 写入物 | 事件面边界（建议） | DB 约束面（0008 先例） | 判红条件 |
| --- | --- | --- | --- | --- |
| ① 格级传播 | 火场强度逐格推进（`matter_state` 行或火场专表行） | **零事件**：传播步进是投影折叠产物，不产 `MATTER_*` 事件（否则格驱动事件风暴）；只在**状态跃迁**时产事件（点着/烧毁/熄灭） | 火场表若建则须 CHECK 强度域 [0,1] 与 `tick >= 0`（0013 同款两条 CHECK：`ck_npc_power_level_range`/`ck_npc_power_tick_nonneg`） | 每 tick 产 >1 条 `matter.*` 蔓延事件且无状态跃迁 ⇒ 格驱动实现 |
| ② 烧毁物质 | `material_balances` 存量、`matter_state` 完整性、`structures` phase | **必须产 `MATERIAL_MOVED`**（燃烧消耗材料：from 结构 ref → to 灰烬/残骸 ref，quantity>0）＋ `MATTER_DAMAGE`/`MATTER_COLLAPSE`（既有族，不新增）；守恒折叠必须与投影逐位相等 | 成对不变式「from 减/to 加」进 CHECK 或钉（0005/0008 成对 CHECK 判据：可表达约束进 DB） | 只减存量不产 `MATERIAL_MOVED` ⇒ 折叠重放与投影不等（golden 逐位红） |
| ③ 连带失效 | **不可重建 4 张表的火灾语义**（见 §3） | 蔓延**不得**新增事件 kind 去记录权力/关系/记忆的「火灾语义」（红线 A 同款纪律） | 「烧毁对不可重建表的影响」应落**显式列**而非事件源（0013 同款：无事件源 ⇒ 只有当前值） | 火灾状态靠事件重放 ⇒ 需新增 kind ⇒ 触发红线 A 与钉 D-5 |

**建议的写入边界三句话（可直接写进 D 批施工单）**：
1. 蔓延事件族每 tick **≤1 条**（状态跃迁/聚合事件），传播步进零事件；
2. 烧毁的物质**只经既有 `matter.*`/`material.moved` 事件族**表达，新增 kind 一律走 CR（红线 A）；
3. 火灾对不可重建 4 张表的语义落**显式列**（不回放），与 A7/A3 登记口径一致。

## 3. 烧毁对 npc_power/material 状态的连带失效（不可重建 4 张表的火灾语义）

**交叉 A3/A7 登记**（`docs/data/m5-anchor-materialization-preplan.md` §0/§1.4，`0013_power_state.py` 头注）：

| 表 | 为何不可重建 | 火灾语义（蔓延烧毁/生态枯竭的连带影响） | 安规要求 |
| --- | --- | --- | --- |
| `npc_memories` | 治理列 `superseded_by`，无事件源 | 烧毁地点的记忆是否被清空？**禁**：清空 = 制造不可审计的历史空洞 | 蔓延不得 DELETE 记忆行；最坏是新增 `matter.*` 事件让记忆「记得这场火」（可重放） |
| `knowledge` | told 链 + 源记忆指针 + 治理列 | 失火 NPC 是否失智（知识失效）？若**置空知识行**则跨分支证据链悬空（0008 `ck_knowledge_evidence_pair`） | 火灾语义落显式列/标记，不得物理清空；证据链 CHECK 不破 |
| `relationships` | 累计值原地演进（无物化器/可比字段） | 火灾烧毁住所是否重置关系值？累计值**原地演进**语义要求「增量可追溯」 | 火灾影响走增量（`relationships` 累计值增量写）+ 事件留痕，不得整行覆写 |
| `npc_power`（M5-A7/0013） | **无事件源**（红线 A 禁新增 kind，增量走显式写面，本表只有当前值） | 火场中 NPC 权力是否变化？**无事件源 ⇒ 不可重放**；只能走 `PowerStore.apply/apply_batch` 显式增量写面 | 火灾写权力**必须**经 `PowerStore`（fail-closed 四条 + 越界夹取如实上报）；批量火灾走 `apply_batch`（全批原子，批内任一非法整批零写） |

**结论（安规闭环）**：火灾对 4 张不可重建表的语义**只能是显式写面增量**，不得靠事件重放，
也不得物理清行——否则读历史点（`kind="anchor"`）时这 4 张表的「火灾后状态」永远拿不到，
A3 §3.2 的「语料一致」条件当场说谎。**这一条同时是 D 批的施工级钉（D-5 零新增 kind + D-6 零物理清行）与 A7 的同款纪律**
（0013 头注「无事件源 ⇒ 属不可重建第 4 张」，头注已把这条写死，D 批照抄即可）。

## 4. 施工级安规钉清单（按归属拆三组）

**分组原则**（对齐 m5-plan 批次 D 负责域行）：opencode = 数据面（写路径 + 事件 kind 登记 +
材料守恒 + 不可重建表写入）；kilo = API/出站面（WS 帧 + 出站递归扫 + 错误码）；机制面归我
（威胁模型 / 意图闸语料 / 事件预算判据 / 施工后复验）。每钉一句可证伪判据 + 建议落点文件名。

### 4.1 归 opencode（数据面）

| # | 钉 | 可证伪判据 | 建议落点 | 复用手法 |
| --- | --- | --- | --- | --- |
| D-1 | **唯一写路径**钉（负钉·白盒） | 蔓延/生态生产代码零 `session.add`/`session.execute`/`.update(` 裸写 `matter_state`/`structures`/`material_balances`；判据：正则扫 `sim/world/fire*.py`·`sim/world/ecology*.py`·火场表数据面文件，命中裸写即红（目标文件为建设时新增） | `sim/tests/test_m5_fire_spread.py::TestWritePath::test_no_bypass_of_c4_write_path`（A6 白盒体例） | A7 O-1 负钉（`test_m5_power_state.py::TestPowerWriteSurface` 单入口）、m5-power-threatmodel O-1 |
| D-2 | **事件 kind 登记 + payload 闭合**钉 | 新增蔓延 kind（若有任何）已在 `PAYLOAD_MODELS` 登记、`extra="forbid"`、域约束齐；判据：`set(PAYLOAD_MODELS) == set(EventKind)` 恒成立（既有闭合钉 `test_every_kind_has_payload_model` 自动覆盖），且新 kind 与既有 19 kind 无重叠 | `sim/tests/test_t1_m4_structure_payloads.py::TestRegistration`（27 钉同款体例，新建 `test_m5_fire_payloads.py` 承火/生态 kind） | 0006/0007 事件族钉体例、`test_event_kinds_unchanged_by_batch_c` 的闭合集手法 |
| D-3 | **材料守恒逐位相等**钉 | 燃烧消耗材料：一次蔓延事件族折叠后的 `material_balances` == 投影，**逐位相等不给浮差**（裁 17-1）；判据：烧毁结构后 from ref 减、to ref 加，两侧都非空且 quantity>0 | `sim/tests/test_t1_m4_material_balance.py::TestMaterialConservation`（+火案例，落 golden `conservation.py::assert_material_balances_conserved`） | T1 第 6 条既有 6 例 + `assert_material_balances_conserved` |
| D-4 | **成对不变式进 DB**钉（0008 先例） | 「燃烧量 ≤ 该格存量」「from 减 == to 加」这类可表达约束落 CHECK 或钉；判据：火场表/材料转移的 DB CHECK 存在（与 `ck_npc_power_level_range`/`ck_npc_power_tick_nonneg` 同款）或钉死该不变式，**不得只靠 Python if** | `sim/tests/test_m5_fire_spread.py::TestDbChecks::test_burn_invariants_are_db_enforced` | 0008 四件 CHECK（`ck_events_parent_branch_pair`）判据「可表达约束进 DB」、0013 两条 CHECK |
| D-5 | **零新增 kind 优先 / 火灾语义落显式列**钉 | 蔓延与生态**不新增事件 kind** 去承载「烧毁对 4 张不可重建表的影响」（红线 A 同款）；判据：`PAYLOAD_MODELS` 的 kind 集合在批次 D 后仍不含火/生态族（或新增须有同 CR 引用） | `sim/tests/test_m5_fire_spread.py::TestForbiddenSurface::test_no_event_kind_added_for_unrebuildable_state` | `test_event_kinds_unchanged_by_batch_c`（A7 红线 A 执行形态）、0013 头注 |
| D-6 | **不可重建 4 表零物理清行**钉（负钉） | 蔓延不得 DELETE `npc_memories`/`knowledge`/`relationships`/`npc_power` 任一行；判据：白盒扫生产代码零 `delete(`/`query.delete()` 命中这 4 张表；火灾影响走增量/标记 | `sim/tests/test_m5_fire_spread.py::TestUnrebuildable::test_fire_never_deletes_unrebuildable_rows` | A3 §1.4 登记钉（`test_registered_as_fourth_unrebuildable_table`）、A6 分支隔离三钉 |
| D-7 | **fork 克隆完整**钉 | 火场/生态状态若进有界表，须进 `fork.py::_BOUNDED_TABLES`（逐字节克隆父值）且不跨分支污染；判据：分叉后火场行数与父分支相等 | `sim/tests/test_m5_fire_spread.py::TestForkClone::test_fire_state_cloned_byte_equal` | A7 `test_fork_clones_rows_byte_equal`、0008 克隆同款 |

### 4.2 归 kilo（API/出站面）

| # | 钉 | 可证伪判据 | 建议落点 | 复用手法 |
| --- | --- | --- | --- | --- |
| D-8 | **出站递归扫（火/生态禁键）**钉 | 任一 WS 帧/路由响应体递归键扫**零**火/生态禁键命中（若 D-10 类比：火场强度/温度等状态零出站，D 批沿用「可见=可攻击」判据）；判据：新增火/生态字段若进 payload → 递归扫描当场红 | `sim/tests/test_m5_notice_outbound.py`（登记面）或新建 `test_m5_fire_outbound.py::TestOutboundStrip` | K11 `strip_authority_fields` 咽喉闸（`outbound_guard.py`）、`_forbidden_hits` 递归扫 |
| D-9 | **WS 帧类型闭合**回归钉 | 帧 `type` 集合不含火/生态族（D 批零协议面新增，沿批次 C 「零新增」纪律）；判据：`test_ws_frame_types_closed` 复跑仍绿 | `sim/tests/test_m5_authority_surface.py::TestProtocolClosedness::test_ws_frame_types_closed`（既有 10 钉直接复用） | S3 红线 A、`test_event_kinds_closed` |
| D-10 | **错误码面零新增**钉 | 火/生态非法请求走既有 ProblemDetail 四键 / WS 错误码词表，不新增机器码；判据：WS 错误码词表闭合 + 快照 `components.responses` 零火/生态码 | `sim/tests/test_m5_power_api.py::TestErrorCodeSeal`（18 钉同款，新建火变体） | F-6 双钉（`/errors/anchor-name-rejected`）、K11 §5 零新增 |
| D-11 | **意图闸不被绕过**钉 | 火源演化走 `impulse_gate` 或混沌确定性流，蔓延不得让「玩家念头」直写火场格；判据：白盒扫火/生态生产代码零裸 `player_impulse` 消费（除非经 `impulse_gate`） | `sim/tests/test_m5_fire_spread.py::TestIntentGate::test_fire_ignition_passes_impulse_gate` | m5-plan 批次 D 安规行「不得绕 Intent 闸走非 LLM 直改世界」、M4-A2 impulse_gate |
| D-12 | **构造隔离**钉（X2 体例，最高优先） | 合成一条含火/生态脏键的内部态（构造器实造）→ 经真实 WS 帧/HTTP 路由 → 响应体零命中。防「用干净样本测剥除」的假绿 | `sim/tests/test_m5_fire_outbound.py::TestOutboundStrip::test_strip_survives_dirty_fire_input` | K-3 构造隔离（S8 最强钉）、M3 X2 体例 |

### 4.3 归我（机制面：语料 / 预算判据 / 复验）

| # | 钉 | 可证伪判据 | 建议落点 | 复用手法 |
| --- | --- | --- | --- | --- |
| D-13 | **T3 破坏类语料**钉（W-D2，随语料 CR） | 火/生态题面（纵火「去烧了那片林子」/灭火「避开火场」/滥砍）进 `t3_corpus.py` **且** `t3-corpus.md` 同步（`test_all_case_ids_present_in_doc` 双向核对钉自动红）；判据：六类中至少一类含 ≥3 条火/生态样本且期望响应列安全基线 | `sim/tests/test_t3_gate.py`（+破坏类语料，落 69→N 顺带校 `len(CORPUS) == 69` 那条断言） | S7 W-D2「随语料 CR 加不预扩」、`test_banned_wordlist_covers_t3_terms` |
| D-14 | **事件预算判据**钉（W-D3，定标机定 N） | 连续 10 tick 同因蔓延事件 >N 即实现偏差；判据：蔓延为事件驱动非 per-tick，每 tick 蔓延事件 ≤1 条（§2 边界①），且 bench `APPLY_P99_LIMIT_MS=0.04`/`TICK_P99_LIMIT_MS=8.3` 不破 | `sim/tests/bench/test_bench_fire.py::test_fire_tick_event_budget`（新建）+ `docs/perf/budget.md` D 批行 | budget.md §1 事件 apply 行（稳态 ~20/tick，p99 50）、thresholds.py 现有红线 |
| D-15 | **零代码边界**钉 | 本批只出案不施工；判据：批次 D 开工单里我域只交这份稿 + §5 复验单，施工方回执逐条对齐本清单 | 本稿（无需测试） | S8 §5 变更纪律同款 |

## 5. 施工后复验单（S8 §4 落成可执行版：批次 C 核心接线合入后逐钉核）

**用法**：批次 C 核心接线（Claude 域 `sim/npc/`，进行中）合入后，对下表 18 个钉逐行核——
「**自动覆盖**」= 我接线时已被 K11 18 钉/A7 45 钉连带覆盖（引用具体钉号，PASS 条件即那些钉绿）；
「**独立跑**」= 须我单独执行的动作（白盒扫 / 语料 CR / 预算实测）。PASS/FAIL 判据各一句。

### 5.1 18 钉逐行核（W-A 4 + K-1..K-7 7 + O-1..O-7 7；引用具体钉号）

| 钉 | 归属 | 覆盖来源 | PASS 判据 | FAIL 判据 |
| --- | --- | --- | --- | --- |
| W-A1-1 | 我 | **独立跑** | `sim/world/authority/*.py` 白盒扫零内建词面字面量过滤 | 命中 `if ... in text` 形态词面判定 → 第二套判梯 |
| W-A1-2 | 我 | **独立跑** | 机制若引入戏内新词，`banned_words.py` diff 与用例同步（有 CR 引用） | 有词面无守卫 = CR 未走完 |
| W-A2-1 | 我 | **独立跑** | `sim/world/authority/*.py` 零 `UtilityDecision` 构造参数直改/import | import 即红（旁路嫌疑） |
| W-A2-2 | 我 | **独立跑** | 同输入换权力档，`willingness_conflict` 返回**不同 band** | band 不变 → 机制无效或旁路 |
| K-1 | kilo | **自动覆盖**（K11 `TestOutboundStrip::test_ws_send_strips_forbidden_keys` + `TestForbiddenKeyScanner::test_find_hits_recursively`；旁证 S3 `test_ws_payloads_recursive_clean`） | 响应体递归键扫零命中 `AUTHORITY_FORBIDDEN_KEYS` 9 键全集 | 任一路由响应命中禁键 |
| K-2 | kilo | **自动覆盖**（K11 `TestWhiteboxNails::test_forbidden_key_literals_only_in_guard_module` + `test_send_path_wires_the_guard`） | 禁键字面量只在闸门模块 | 第二真相源 |
| K-3 | kilo | **自动覆盖**（K11 `TestOutboundStrip::test_directed_send_also_strips` + `test_ws_send_clean_payload_untouched`（脏/干净对照）） | 构造隔离：脏态经真实 WS → 零命中 | 干净样本假绿 |
| K-4 | kilo | **自动覆盖**（K11 `TestErrorCodeSeal::test_snapshot_has_no_power_response_code`） | 非法输入走 ProblemDetail 四键结构化 | 裸 500/静默忽略 |
| K-5 | kilo | **自动覆盖**（K11 `test_no_authority_exception_leaks_into_http_errors`） | 错误文案零权力术语 | 台词带权力词 |
| K-6 | kilo | **自动覆盖**（`test_ws_frame_types_closed` + `test_event_kinds_closed`，S3 已钉，**A7 `test_event_kinds_unchanged_by_batch_c` 复用**） | 帧 type 集合与 kind 集合闭合、零权力族 | 新增 kind/帧 |
| K-7 | kilo | **自动覆盖**（K11 `test_key_set_matches_codex_redline_b`（跨域键集防漂移）+ `test_strip_is_pure_and_deep`） | 剥除层与测试共用同一扫描器 | 各写一份判梯 |
| O-1 | opencode | **自动覆盖**（A7 `TestPowerWriteSurface` 单入口族：`test_first_apply_creates_row_from_zero`/`test_apply_accumulates_and_advances_tick`） | 写权力零裸 `session.add`/UPDATE | 裸写 |
| O-2 | opencode | **自动覆盖**（A7 `test_nan_and_inf_rejected_zero_write`/`test_bad_tick_rejected`/`test_out_of_range_clamped_and_reported`） | 非法 payload 抛错**零行落库**（配正向落库断言） | 静默截断/半写 |
| O-3 | opencode | **自动覆盖**（A7 `test_materialize_is_branch_isolated`） | 读按 `branch_id` 过滤，兄弟分支互不可见 | 跨分支可见 |
| O-4 | opencode | **自动覆盖**（A7 `test_inactive_branch_rejected_zero_write`） | 向非 active 分支写抛 `InactiveBranchError` 零写 | 误写被弃时间线 |
| O-5 | opencode | **自动覆盖**（A7 `test_fork_clones_rows_byte_equal` + `TestForkClone` 分叉守恒） | fork 克隆逐字节 + 父子值守恒 | 克隆漂移/跨分支污染 |
| O-6 | opencode | **自动覆盖**（A7 `test_level_range_checked_by_db`/`test_no_redundant_index_beyond_pk`） | 量纲 CHECK 在 DB 层 + 零冗余索引 | 无 CHECK/多余索引 |
| O-7 | opencode | **自动覆盖**（A7 `test_no_power_values_in_events`） | 权力不落事件流（写权力后 events 行集零变化） | 新增 kind 承载权力 |

### 5.2 汇总：哪些自动覆盖、哪些须独立跑

- **自动覆盖 14 钉**（K-1..K-7 + O-1..O-7）：由 K11 18 钉（`test_m5_power_api.py` 18 例，五组）+ A7 45 钉
  （`test_m5_power_state.py` 45 例，含迁移往返/写面 fail-closed/读面纯读/分叉克隆/禁面与登记钉）
  连带覆盖；**批次 C 接线只须让既有钉仍绿**，无须新增测试。
- **须独立跑 4 钉**（W-A1-1/W-A1-2/W-A2-1/W-A2-2）：白盒源码扫描 + 词表 CR 核对 +
  意愿 band 行为核，**这些钉等机制文件 `sim/world/authority/` 落盘才有对象可扫**——
  现状该目录**不存在**（S8 §0 实测），故四钉在批次 C 接线前**判 BLOCKED（对象未落）**，
  接线后即跑（每钉一句可证伪判据见 §5.1）。
- **本次（D 批）新增施工级钉 15 条**（D-1..D-15，见 §4）：数据面 7（D-1..D-7 → opencode）+
  出站面 5（D-8..D-12 → kilo）+ 机制面 3（D-13..D-15 → 我，含 D-13 语料 / D-14 预算 / D-15 边界），
  随 D 批施工落钉，本稿不抢施工。

## 6. 变更纪律

- 本稿只出案不施工；D-1..D-15 对齐三方回执后，施工方在自己的单里落钉。
- 若 D 批新增事件 kind（违反 D-5 优先），须同 CR 引用本稿 §2 边界与红线 A。
- **§18 缩范围序位**：生态序 1（第一个可砍）、火灾蔓延序 2（砍时**保留坍塌**）——本稿只注序位，
  **不预砍**（裁 21-C②）；若执行期砍，本稿 §2 边界③/§3 的 4 张表语义随之失效，须走 CR。
- 词表零扩散：META_SHELL 8 词填值纪律不变（本稿不触碰）。
- T1 材料守恒（第 6 条）**不随砍生态而失效**（m5-plan 批次 D 验收口径）——D-3 钉恒成立。
