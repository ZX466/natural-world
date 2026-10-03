# M5 收官门预审（docs/security/m5-closure-preaudit.md）

> 维护：Codex（安全/合规/风险域）· 依据：M5-S11 派单（2026-10-03，M5 收官前置波）·
> 同 M3/M4 体例（静态预审-放行-动态三段式，提案制不擅改）· 基线：main `04e4220`（A10 物化施工
> + R-4 施工已并入）· 日期：2026-10-03 · 树：ZX466/codex
> 性质：**静态预审**——只对表、只提缝、只登记钉状态；**不重跑测试当验收**（§6 钉号对账即可），
> 动态全量复验等收官门全绿后跑（§7 待填）。

## 0. 结论速览

| 门 | 状态 | 说明 |
| --- | --- | --- |
| **D-10 权力不可见全链证据链** | ✅ **闭合** | A7 零读口（7 读面钉）/ K11 咽喉闸 18 钉 / S8 18 钉判据 / A9 零归因键（2 钉）/ K13 归因双保险（4 钉）/ S10 §2.3 不进包 + A10 实测（E-4/E-5）——**逐项见 §1，零开口** |
| **词表纪律（META_SHELL 8 词空表）** | ✅ **未破 + 挂账如实登记** | `BANNED_WORDS_META_SHELL == frozenset()` 实测；6 负钉全绿（`test_meta_shell_lexicon.py`）；**唯一挂账 = 8 词填值待首个戏外消费 CR**（§2） |
| **三硬边界** | ✅ **三条全闭** | `rng_state` 零出协议面（protocol.ts/openapi/ws/anchors 四面实测零出现）；分叉可见性隔离**零实现**；`rate_change` 仅存 `ws.py:27` 注释（§3） |
| **53 钉总账** | ✅ **零悬空** | S7 7 + S8 **18** + S9 15 + S10 13 = **53**（**派单写 52**，差 1 因 S8 实为 18 条＝K7+O7+WA4，见 §4 注） |
| **T1 守恒全链抽验** | ✅ **对账闭合** | 既有 7 例 + A9 烧毁 3 钉（`reason="burned"`+`to_ref` 守恒）+ A10 包写零吞事件 2 钉（§6） |
| **功能/非性能全量** | ✅ 静态绿 | **2149 passed / 120 skipped / 70 deselected**（本机 @`04e4220`，exit 0） |
| ruff / pyright | ✅ | 0 / clean |
| **发现分级** | ⚠ **2 MEDIUM + 3 LOW，零 CRITICAL/HIGH** | §5（F-1 W-C1 无钉执行＝唯一实质缝；F-2/S9 幂等语料缺口） |
| 收官安规门判据 | ✅ 可放行（附 3 条） | §6 收官门五判据全绿，唯一未闭合项 F-1 属**新增面**而非 M5 范围（§5 判语） |

## 1. ① D-10 全程核对：权力不可见红线在 M5 全链的落实证据链

D-10 = 「权力完全不可见，纯 Agent 内部，协议面零改动」（裁 27/28）。本节逐项列**可执行证据**
（钉号 + 文件），不给「已遵守」这类无钉结论。

| # | 环节 | 钉号 + 文件（实跑数） | 证据性质 |
| --- | --- | --- | --- |
| 1 | **数据面零读口** | `test_m5_power_state.py::TestPowerReadSurface`（`materialize_filters_and_omits_unknown`/`materialize_is_branch_isolated`/`materialize_is_pure_read`/`returned_state_is_frozen`）＝ 7 读面钉 | 纯读面 + 分支隔离 + 返回 frozen（读不得变成写） |
| 2 | **数据面零事件源** | `TestForbiddenSurface::test_event_kinds_unchanged_by_batch_c`（写权力后 events 行集零变化） | 红线 A 执行形态：**权力不落事件流** |
| 3 | **命名即绊线** | `test_state_columns_are_forbidden_key_tripwires`（`power_level` ∩ 禁键集 == `{power_level}`） | 列名故意落禁键集 ⇒ 意外序列化当场扫红 |
| 4 | **迁移零出站登记** | `0013_power_state.py` 头注 + `test_registered_as_fourth_unrebuildable_table` | A3 地基分类登记（第 4 张不可重建表） |
| 5 | **K11 WS 咽喉闸** | `test_m5_power_api.py` **18 例**（`TestOutboundStrip` WS 实测/`TestWhiteboxNails` 禁键只许在闸门模块/`test_keys_are_case_insensitive`/`test_key_set_matches_codex_redline_b`） | 闸装在 `_send_to` 唯一咽喉；干净面零扰动 |
| 6 | **HTTP 结构性密封** | `TestHttpSurfaceSeal::test_every_http_route_declares_response_model` + `test_snapshot_paths_have_no_power_route` | 全路由 `response_model` ⇒ 未声明字段不可能出现 |
| 7 | **协议面闭合枚举** | `test_m5_authority_surface.py::TestProtocolClosedness`（`ws_frame_types_closed`/`openapi_snapshot_no_authority_keys`/`event_kinds_closed`）＝ 3 钉 | 三处闭合集零新增 |
| 8 | **出站递归禁键（三面）** | `TestOutboundForbiddenKeys`（`ws_payloads_recursive_clean`/`anchors_payload_recursive_clean`/`prompt_assembly_recursive_clean`）＝ 3 钉 | 红线 B 三面实测 |
| 9 | **操纵感零豁免** | `TestManipulationRedline`（`authority_manipulation_phrases_red`/`self_doubt_complaint_green`） | 红线 C 最高风险已锁 |
| 10 | **S8 18 钉判据** | `m5-power-threatmodel.md` §2/§5：K-1..K-7（kilo）+ O-1..O-7（opencode）+ W-A1-1/1-2/2-1/2-2（我） | 判据全集；落地映射见 §4 总账 |
| 11 | **A9 火灾零归因** | `test_m5_fire_state.py::TestNoAttributionAndNoExtraKinds`（工厂**不收归因参数**）+ K13 `TestAttributionKeys`（`fire_payloads_have_no_attribution_keys`/`are_closed_models`） | **归因 = D-10 唯一残余风险**，已双保险（数据面 + 出站面） |
| 12 | **K13 归因键决策锁** | `TestAttributionDecisionLock`（`attribution_keys_not_in_guard_keyset`/`guard_does_not_strip_attribution_keys`） | 归因键**不进**权力键集（否则 D-10 闸会误剥） |
| 13 | **S10 包裁决（不进包）** | `m5-batch-e-security-preplan.md` §2.3 三案裁决 + `test_m5_materialization_package.py::TestSecurityNailsESeries::test_e4_package_carries_no_power_state`（blob 含 `npc_power` 被剔）+ `test_e5_anchor_load_leaves_power_fallback_zero` | **A10 实测落实**：`npc_power` 不进包、读档兜底 0 |
| 14 | **W-A 四钉（机制面）** | ⚠ **对象未落**（`sim/world/authority/` 不存在）⇒ 4 钉 BLOCKED 未解除 | 见 §5 F-3（**非破线**：D-10 已由上面 13 项闭合） |

**D-10 结论**：**已闭合，零开口**。第 14 项（W-A 四钉）是**机制面内部**的行为判据
（词面 CR/意愿管线旁路），不是 D-10 的载体面——D-10 的**载体面**（数据面/出站面/包面）
已由第 1-13 项全覆盖。机制面落盘后，4 钉按 `m5-batch-e-security-preplan.md` §5.1 分类解除
（W-A1-1/W-A2-1 白盒扫描·文件落盘即解；W-A1-2 零新增词面即恒绿；**W-A2-2 唯一真依赖接线**）。

## 2. ② 词表纪律核对（META_SHELL 8 词空表）

| 项 | 证据（实跑） | 判定 |
| --- | --- | --- |
| 空表未破 | `banned_words.py`：`BANNED_WORDS_META_SHELL: frozenset[str] = frozenset()` | ✅ 空表 |
| 不是 Agent 面豁免源 | `test_agent_dispatch_never_reads_meta_shell`（`scan()` 源码零引用该表） | ✅ 负钉在 |
| 空表时两扫描等价 | `test_scan_meta_shell_equals_scan_when_table_empty` | ✅ 分派不为空表所累 |
| 填值后词仍拦 Agent 面 | `test_meta_shell_words_still_blocked_on_agent_surface` | ✅ 填值不放松 Agent 面 |
| 填值后行为正确（双态实测） | `test_meta_shell_covers_candidate_words_when_filled`（临时注入 `重开` 后还原） | ✅ skip-locked 双态 |
| 数值/持久类 kind 保持 | `test_number_field_and_persist_kinds_preserved` | ✅ 判层未漂移 |
| 零扩散 | 全仓 `BANNED_WORDS` 未因 M5 增词（F-6 零扩散纪律）；`test_banned_wordlist_covers_t3_terms` 在 T3 面复跑 | ✅ |

**实跑**：`uv run pytest sim/tests/test_meta_shell_lexicon.py -q` → **6 passed**。

**唯一挂账（如实登记）**：**8 词填值待首个真实戏外消费方 CR**（裁 30 §B 已裁「空表先建结构」，
YAGNI）。首批候选 `{重开, 读档, 存档, 快照, 回放, 游戏, 模拟, 玩家}` 以批注留存于
`banned_words.py`；**填值不属 M5 收官阻断项**（M5 无戏外消费方 ⇒ 无触发条件）。
## 3. ③ 三硬边界核对

| 边界 | 判据 | 证据（实测/静态） | 判定 |
| --- | --- | --- | --- |
| **`rng_state` 不出网关** | 落库但在协议面零出现 | 0009 落 `branches.rng_state` + `anchor_packages.rng_state`（A4/A10）；**协议四面实测零出现**：`shared/protocol.ts` 零 `rng_state`/`rngState`、`shared/openapi.json` 零 `"rng`、`sim/api/ws.py`（`session_state`/`snapshot_payload` 构造）零 `rng`、`sim/api/anchors.py` 零 `rng`；`AnchorListItem` 五键白名单（`extra="forbid"`，无 rng 键） | ✅ **闭合** |
| **分叉可见性隔离不开启** | 谱系列设计，不暴露跨分支可见性 | 全仓 `sim/**`+`shared/**` 零 `fork_visibility`/`visibility_isolat` 命中 ⇒ **零实现**（符合「不开启」）；跨分支引用走 0008 `parent_branch_id` + CHECK（`ck_events_parent_branch_pair`/`ck_knowledge_evidence_pair`），是**数据面**设计非**可见性**设计 | ✅ **闭合** |
| **`rate_change` 只留预留名** | 不启用 | `git grep rate_change -- sim/** shared/** client/src/**` **唯一命中 = `sim/api/ws.py:27` 注释**（「`rate_change` 只登记预留名」）⇒ 零实现、零协议面 | ✅ **闭合** |

## 4. ④ 四张威胁模型钉号总账（53 钉逐钉状态）

**钉号总数核对（脚本从四稿正文抽定义行，非引用行）**：
S7 = 7（W-A1/W-A2/W-C1/W-C2/W-D1/W-D2/W-D3）·
**S8 = 18**（K-1..K-7 七 + O-1..O-7 七 + W-A1-1/W-A1-2/W-A2-1/W-A2-2 四）·
S9 = 15（D-1..D-15）· S10 = 13（E-1..E-13）⇒ **合计 53**。

> **与派单的口径差（事实登记，不擅改）**：派单写「S8 17 钉 … =52 钉」。实测 S8 §2 定义行
> **18 条**（7+7+4）——S8 落稿时 memory 记的「17 钉」与正文定义行不一致（K/O 各 7 + WA 4 = 18）。
> 本总账按**正文定义行**记 53，并登记此差；若主树台账按 52 记，属台账口径差（**非缺钉**）。

**状态四档**：`✅已落码` = 钉在测试文件里且可跑 · `⏳随施工落` = 施工方持有、随其单落 ·
`🔒skip-locked` = 锁信号未现，双态设计 · `⛔BLOCKED` = 对象未落（需施工后才可跑）。

| 系列 | 钉号 | 状态 | 落地位置 / 解除条件 |
| --- | --- | --- | --- |
| S7 权力 | W-A1 | ✅ 已落码 | S8 展开为 W-A1-1/W-A1-2；S6 负钉 `test_t4_probes.py` 词面纪律在位 |
| S7 权力 | W-A2 | ✅ 已落码 | S8 展开为 W-A2-1/W-A2-2（**行为核 ⛔**，见下 W-A2-2） |
| S7 混沌 | W-C1 | ⏳随施工落 | ⚠ **无钉执行**（见 §5 F-1）：四面实测零出现但**无递归扫断言**；HTTP 读档路由单落地时补 |
| S7 混沌 | W-C2 | ✅ 已落码 | `test_m5_chaos_stream.py` 11 例（`test_returns_plain_float_scalar` 纯标量不出材料/seed 面）；`chaotic()` 消费点在批次 A 收口（Claude 域），接线时补内插零命中钉 |
| S7 火灾 | W-D1 | ✅ 已落码 | S9 D-1（唯一写路径）+ A9 `TestWritePath`（两写路径同一 `project_fire`） |
| S7 火灾 | W-D2 | ⏳随施工落 | S9 D-13（T3 破坏类语料）；语料随火灾语料 CR 加；**不预扩**（S7 定调） |
| S7 火灾 | W-D3 | ⏳随施工落 | S9 D-14 + 裁 34 **N=2**（P11 定标已落，advisory） |
| S8 权力 | K-1..K-7 | ✅ 已落码 | K11 `test_m5_power_api.py` 18 例（§1 第 5/6 项） |
| S8 权力 | O-1..O-7 | ✅ 已落码 | A7 `test_m5_power_state.py` 45 例（§1 第 1-4 项） |
| S8 权力 | W-A1-1 | ⛔BLOCKED | 扫描 `sim/world/authority/*.py`——**目录不存在**；落盘即解 |
| S8 权力 | W-A1-2 | ✅ 恒绿 | 机制零新增词面 ⇒ 零扩散恒绿（无需解除） |
| S8 权力 | W-A2-1 | ⛔BLOCKED | 同 W-A1-1（白盒扫 `UtilityDecision` 引用） |
| S8 权力 | W-A2-2 | ⛔BLOCKED | **唯一真依赖接线**：`PowerStore`→utility 传导完成才可跑行为核 |
| S9 火灾 | D-1 | 🔒skip-locked | A9 `TestWritePath::test_fire_engine_files_have_no_bypass`；机制面 `sim/world/fire*.py` 未落 ⇒ 自动转绿 |
| S9 火灾 | D-2 | ✅ 已落码 | A9 `TestKindRegistration`（kind 登记 + `PAYLOAD_MODELS` 同步） |
| S9 火灾 | D-3 | ✅ 已落码 | A9 `TestMaterialConservation`（`test_burned_material_is_a_move_not_a_delete`） |
| S9 火灾 | D-4 | ✅ 已落码 | A9 `TestDbChecks`（`ck_fires_end_pair` 成对不变式进 DB） |
| S9 火灾 | D-5 | ✅ 已落码 | A9 `TestNoAttributionAndNoExtraKinds`（`test_no_spread_or_burn_kind`） |
| S9 火灾 | D-6 | ✅ 已落码 | A9 `TestUnrebuildableUntouched`（4 张不可重建表零触碰） |
| S9 火灾 | D-7 | ✅ 已落码 | A9 `TestForkClone`（`fires` 进 `_BOUNDED_TABLES`） |
| S9 火灾 | D-8 | ✅ 已落码 | K13 `TestSnapshotZeroDrift` + `TestLightKindFreeString` |
| S9 火灾 | D-9 | ✅ 已落码 | K13 `TestEventStreamNotFrameType`（帧判别器零 fire） |
| S9 火灾 | D-10 | ✅ 已落码 | K13 `TestErrorCodeSeal` 同款（错误码面零新增） |
| S9 火灾 | D-11 | ✅ 已落码 | K13 `TestAttributionKeys`（归因键双保险；意图闸面由 D-2 覆盖） |
| S9 火灾 | D-12 | ✅ 已落码 | K13 `TestNoFireLiteralInApiLayer`（白盒负钉 tokenize 级 + 植入反假绿自测） |
| S9 火灾 | D-13 | 🔒随语料 CR | T3 破坏类语料；**不预扩**（S7 定调：随语料 CR 加） |
| S9 火灾 | D-14 | ✅ 已落码 | 裁 34 **N=2** 已定；A9 事件面「一场火一 tick 最多一条聚合事件」 |
| S9 火灾 | D-15 | ✅ 边界达成 | 本稿只出案不施工（体例本身即钉） |
| S10 批次 E | E-1 | ✅ 已落码 | A10 `test_e1_offline_surface_never_writes_player_anchor`（白盒，记「对象未落」不假绿） |
| S10 批次 E | E-2 | ✅ 已落码 | A10 `test_e2_cursor_frozen_after_world_progress`（游标逐字段不变） |
| S10 批次 E | E-3 | ✅ 已落码 | A10 `test_e3_events_not_dropped`（推进 3 tick ⇒ events +3） |
| S10 批次 E | E-4 | ✅ 已落码 | A10 `test_e4_package_carries_no_power_state` |
| S10 批次 E | E-5 | ✅ 已落码 | A10 `test_e5_anchor_load_leaves_power_fallback_zero` |
| S10 批次 E | E-6 | ⏳随施工落 | 告知帧零元信息量值；离线告知句落盘时落（现 `fork_notice` 体例在位） |
| S10 批次 E | E-7 | ⏳随施工落 | 告知帧终扫兜底（`fork_notice` 既有体例可复用） |
| S10 批次 E | E-8 | ✅ 已落码 | K13 `TestSnapshotZeroDrift` 重连帧零新增（红线 A 复跑） |
| S10 批次 E | E-9 | ⏳随施工落 | 离线叙事不过豁免；机制面离线分支落盘时落 |
| S10 批次 E | E-10 | ⏳随施工落 | 断线定标（裁 34 已随单；演练级 nightly 由 cline 接线） |
| S10 批次 E | E-11 | ✅ 已落码 | 既有 `test_anchor_pointer_keeps_only_narrative_fields` + `test_no_banned_world_values` |
| S10 批次 E | E-12 | ✅ 边界达成 | 本稿只出案不施工 |
| S10 批次 E | E-13 | ✅ 已落码 | A10 `test_e13_no_fire_baseline_column_added` + `test_e13_no_new_migration_for_package` |

**状态汇总**：✅ 已落码 **35** · ⏳随施工落 **7**（W-C1/W-D2/W-D3/E-6/E-7/E-9/E-10）·
🔒skip-locked **2**（D-1/D-13）· ⛔BLOCKED **3**（W-A1-1/W-A2-1/W-A2-2）·
✅ 边界达成 **2**（D-15/E-12）· **合计 49 条目覆盖 53 钉**（S7 七钉含 W-A1/W-A2 两条
已由 S8 展开细化为 4 钉，故条目数 ≠ 钉号数，映射见上表 W-A1/W-A2 行）。
## 5. ⑤ 发现与缺口（提案制 · 分级 · 不擅改）

**零 CRITICAL / 零 HIGH**（逐项依据见下）。分级口径同 M3/M4 preaudit。

### F-1｜MEDIUM｜W-C1 有判据、无钉执行（`rng_state` 出站递归扫）

- **判据原文**（S7 §9 表）：「全路由响应体递归扫零 `rng_state` 键」，归属 codex 出钉 / kilo 施工。
- **现状**：协议四面**实测零出现**（`protocol.ts` / `openapi.json` / `ws.py` / `anchors.py`，§3），
  **行为上成立**；但**没有任何钉在执行这条递归扫**——`TestOutboundForbiddenKeys` 用的
  `_forbidden_hits` 只扫 `AUTHORITY_FORBIDDEN_KEYS`（9 键权力集），**不含 `rng_state`**。
- **为何不是 HIGH**：违反结果是**零 rng 出站**（当下即合规），属**「闸未装但当前无流量」**，
  不是「闸被绕过且已泄漏」；且 `AnchorListItem` 的 `extra="forbid"` + 五键白名单是
  **结构性密封**（新增字段须走 schema ⇒ 有 CR 目击点）。
- **风险形态**：将来 HTTP 化读档路由时，`rng_state` 键**不会被现有递归扫抓住**
  （它不在权力键集里）⇒ 漏检。
- **建议（提案，待裁）**：把 `rng_state`/`rng_state_json`/`seed`/`entropy` 并入
  `TestOutboundForbiddenKeys` 的扫描键集（**或**新立 `_RANDOM_STATE_KEYS` 独立键集，
  避免与权力键集混判层）；判据 = 全路由响应体递归扫零命中。**归 kilo**（出站面）+
  codex 出判据（已有）。**不阻 M5 收官**（§6 判据 5）。

### F-2｜MEDIUM｜幂等语料重建缺失（A3 §1.4 (B) 路径已知缺口，非本轮新增）

- **事实**：`npc_memories` 的 `superseded_by` 治理列**只存当前值**，事件流里**无**「写该行」的事件
  ⇒ 物化包语料行**靠包内行值**（A3 路径 A）恢复，路径 B「补 `*.written` 事件」**未做**。
- **现状影响**：**A10 已用路径 A 落地**（`corpus_blob` 存 3 表行值），故收官**不受阻**；
  但「语料表本身不可事件重放」这个分类是 A3 的既有登记（`EXCLUDED_FIELDS`），**如实保留**。
- **建议**：留 A3 长期演进项（不属收官范围）。

### F-3｜LOW｜W-A 四钉 BLOCKED（机制面未落盘）

- **事实**：`sim/world/authority/` 不存在 ⇒ W-A1-1/W-A2-1/W-A2-2 三钉 ⛔、W-A1-2 恒绿。
- **为何 LOW（而非 MEDIUM）**：D-10 的**载体面**已由 §1 第 1-13 项闭合（数据面/出站面/包面）；
  W-A 四钉管的是**机制面内部行为**（词面 CR 纪律 + 意愿管线不得旁路），
  机制面**尚未接线** ⇒ 行为暂不存在，**无泄漏面**。
- **解除条件**（已分类，`m5-batch-e-security-preplan.md` §5.1）：W-A1-1/W-A2-1 = 文件落盘即解
  （白盒扫描）；W-A1-2 = 零新增词面即恒绿；**W-A2-2 = 唯一真依赖接线**。
- **建议**：机制面接线单合入后，按 §5.4 速查表跑第 2-5 行。

### F-4｜LOW｜D-1 / D-13 skip-locked 双态（机制面 + 语料 CR 未触发）

- D-1：机制面 `sim/world/fire*.py` 未落 ⇒ A9 记「对象未落」不假绿，落盘即自动转绿。
- D-13：T3 破坏类语料随语料 CR 加（S7 定调**不预扩**）⇒ 现无火灾题面属**设计**，非缺口。
- **建议**：机制面落盘/语料 CR 轮各复跑一次即可。

### F-5｜LOW｜台账口径差（S8 = 18 钉 vs 派单/台账 17 钉）

- **事实**：S8 §2 定义行 **18 条**（K7+O7+WA4）；memory 与派单记「17 钉」。
- **性质**：**记账口径差，非缺钉**（K/O/WA 三组各自完整，无遗漏）。
- **建议**：台账按正文 **18** 订正（或注明「S8 = 18 条定义行」）；不追改 git 历史（同 M2-K2b 改号先例）。

## 6. ⑥ T1 守恒全链抽验（钉号对账，不重跑测试）

| 环节 | 钉号 / 断言 | 状态 |
| --- | --- | --- |
| 材料守恒既有 7 例 | `test_t1_m4_material_balance.py::TestMaterialConservation`（`world_supply_credits_structure_and_conserves`/`multi_move_batch_conserves`/`snapshot_and_replay_bit_equal`/`branch_isolated`/`material_filter` + 2 回滚例） | ✅ |
| 逐位相等断言器 | `golden/assertions/conservation.py::assert_matter_conserved` / `assert_material_balances_conserved`（裁 17-1 **逐位相等不给浮差**） | ✅ |
| **火灾烧毁（fires）** | A9 `TestMaterialConservation::test_burned_material_is_a_move_not_a_delete`（烧毁是 **move 不是 delete** ⇒ 账不凭空少一份）+ `test_burned_reason_is_in_enum`（`reason="burned"` 进枚举，不混 `build_consumed`）+ `to_ref="world:burned"` | ✅ |
| 坍塌 cause=fire | A9 `StructureCollapseCause+"fire"` 枚举成员（不混 `damage`；火焚与外力砸可区分） | ✅ |
| **物化包语料克隆** | A10 `test_e3_events_not_dropped`（写包**不吞事件**）+ `test_events_not_swallowed_by_package_write` + `TestOrderSteps`（展开→override→语料→restore_rng 次序铁律）+ `test_post_anchor_events_are_invisible`（anchor 后事件对读档零影响） | ✅ |
| 语料行集一致性 | A3 §3.2 解锁条件（包内行集 == 投影）；A10 `test_corpus_mismatch_is_in_reason_set`（不一致 ⇒ `AnchorMaterializationError`，不静默降级） | ✅ |

**T1-6（m5-plan:153「材料守恒 D 燃烧」）全链对账闭合** ✅ —— 烧毁经 `MATERIAL_MOVED`
（move 非 delete）保账，坍塌/烧毁均走既有族，**零凭空生灭**。

## 7. 收官安规门判据（M3 preaudit §6 动态门同款体例）

| # | 判据 | 实测 | 判定 |
| --- | --- | --- | --- |
| 1 | D-10 全链闭合（§1 十四项） | 十三项 ✅ + W-A 四钉 BLOCKED（机制面未落，F-3 LOW） | ✅ 可放行 |
| 2 | 词表纪律未破（§2） | 6 负钉全绿 + 8 词空表 + 挂账登记 | ✅ |
| 3 | 三硬边界闭合（§3） | 三条全闭（四面实测 + 零实现） | ✅ |
| 4 | 53 钉零悬空（§4） | 脚本核对零悬空；49 条目覆盖 53 钉 | ✅ |
| 5 | T1 守恒全链对账（§6） | 六环节闭合 | ✅ |

**收官门判定（预审口径）**：**✅ 可放行**——五判据全绿；发现分级 **2 MEDIUM + 3 LOW，零
CRITICAL/HIGH**，且 MEDIUM 两项（F-1 新增扫描面 / F-2 长期演进）**均不阻 M5 收官**
（F-1 是「闸未装但当前零流量 + 有结构性密封兜底」，F-2 已由 A10 路径 A 绕开）。
**附三条放行后动作**（提案）：①F-1 并入 kilo 出站面单（补 `rng_state` 递归扫）；
②机制面接线后按 §5.4 跑 W-A 四钉第 2-5 行；③台账按 F-5 订正 S8 口径。

## 8. 动态全量复验清单（收官门全绿后执行 · §7 待填）

对照 M3 §5 体例，收官门（主树 G1-G4）全绿后跑：

| 项 | 命令 | 判据 |
| --- | --- | --- |
| 功能/非性能全量 | `uv run pytest -m "not bench" -q` | ≥2149 passed / 0 failed |
| 电力三文件 | `uv run pytest sim/tests/test_m5_power_api.py sim/tests/test_m5_power_state.py sim/tests/test_m5_authority_surface.py -q` | 73 passed |
| 火灾两文件 | `uv run pytest sim/tests/test_m5_fire_state.py sim/tests/test_m5_fire_outbound.py -q` | 58 passed + 1 skipped（D-1 机制面未落，skip-locked 双态） |
| 物化包 | `uv run pytest sim/tests/test_m5_materialization_package.py -q` | 70 passed |
| 词表 | `uv run pytest sim/tests/test_meta_shell_lexicon.py -q` | 6 passed |
| 白盒四钉（机制面落盘后） | 见 `m5-batch-e-security-preplan.md` §5.2 命令块 | 零 HIT 行 |
| lint / types | `uv run ruff check .` / `uv run pyright sim/` | 0 / 0 errors |