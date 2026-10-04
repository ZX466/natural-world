# M6-P0 物化读档·安规钉预研（docs/security/m6-materialization-security-pins.md）

> 维护：Codex（安全/合规/风险域）· 依据：M5-S13 派单（2026-10-03，S12 P0 序展开）·
> 基线：main `2bd2bff`（A11 已落编排链 + hooks fail-closed 桩 + 诊断路由）·
> 日期：2026-10-03 · 树：ZX466/codex
> 性质：**施工级钉预研·零代码零 schema**——只出钉清单与 CR 预备案；**范围判断归主树**；
> **8 词 CR 案只预备不填值**（词表零扩散纪律不变）。
> 体例：沿 S9/S10/S11（每钉一句可证伪判据 + 建议落点 + 复用手法；钉号脚本核对零悬空）。

## 0. 一句话 + 现状快照（本稿的核心是「已有什么、缺什么」）

**A11 把物化读档的安规骨架落了大半（诊断路由形状钉 ＋ hooks fail-closed 桩钉 ＋ 机器码
「不出站」决策），本稿的增量只有三处真缺口：①诊断路由**未进红线 B 递归扫**；
②玩家可见失败文案**收窄到无法区分原因**（`load_failed` 单码）；③8 词 CR 的触发点已可
精确定位（`快照` 是 persist 禁词，**任何带原因码的文案必命中**）。**

现状实测（2026-10-03，`2bd2bff`）：

| 项 | 实测事实 | 出处 |
| --- | --- | --- |
| 诊断路由已落 | `GET /api/anchors/{anchor_id}/materialization`，`response_model=AnchorMaterializationStatus` | `sim/api/anchors.py:542-543` |
| **响应形状已锁** | `{anchor_id, ready, reason}` **三键**，`extra="forbid"`；doc 注明「**不含任何世界状态内容**（不返 seq/tick/branch_id/包内行值）」 | `sim/api/anchors.py:115-129` |
| 内部诊断对象**更宽** | `MaterializationDiagnosis` 带 `snapshot_seq` ＋ `steps` ⇒ **路由层已正确丢弃**（`extra="forbid"` 是结构性密封） | `anchor_package.py:484-492` |
| reason 固定集 | `MATERIALIZATION_REASONS = (no_package, rng_unavailable, snapshot_missing, event_gap, corpus_mismatch)` 五码 | `anchor_package.py:124-130` |
| 不可物化**不是 HTTP 错误** | 一律 200 + `ready=false` + 原因码；anchor 不存在 404；无世界 400 `world-not-ready` | `anchors.py:546-557` |
| 机器码**刻意不出站** | `ANCHOR_MATERIALIZATION_MACHINE_CODE = "anchor-materialization-unavailable"` 定义在持久层，**不在** `_TYPE_TITLE`，A11 有钉 `test_machine_code_still_absent_from_snapshot` | `anchor_package.py:132-135` / `test_m5_materialization_api.py:524` |
| hooks 缺省桩 fail-closed | `unavailable_hooks()` 四步全抛 `AnchorLoadUnavailable(HOOKS_UNAVAILABLE)`；`set_materialization_hooks(None)` 复位 | `fork_orchestration.py:144-174` |
| E 系已落码 | `TestSecurityNailsESeries` E-1..E-5 + E-13（包零权力 + 读档兜底 0 + 玩家档零写 + 事件不丢） | `test_m5_materialization_package.py` |
| 三件套实跑 | **116 passed**（package + api + orchestration） | 本机实测 |

**判定**：派单①③（A11 已实现）⇒ 本稿给**验证设计 + 补缺口**，不重钉已有的；
派单②**是本稿最大发现**（§2）；④⑤ 见 §3/§4。

## 1. ① 诊断路由出站面钉（验证设计 + 一个真缺口）

### 1.1 A11 已落的钉（**复跑即可，本稿不重建**）

| 已有钉 | 覆盖 | 出处 |
| --- | --- | --- |
| `test_payload_has_no_world_internals` | 响应体零世界内部字段 | `test_m5_materialization_api.py::TestMaterializationRoute` |
| `test_reason_is_from_fixed_set` | reason ∈ 五码固定集 | 同上 |
| `test_route_payload_is_exactly_three_keys` | 形状恰三键（**白名单式**） | `::TestDiagnosisDelegate` |
| `test_route_shape_matches_persistence_diagnosis` | 路由丢弃 `snapshot_seq`/`steps`（构造隔离体例） | 同上 |
| `test_route_is_read_only` / `test_unknown_anchor_is_404` / `test_without_world_is_400` | 只读语义 + 错误码 | 同上 |
| `test_route_exists_in_app_but_not_in_mock_snapshot` | **路由在 app 但不在 mock 快照**（协议面零 diff） | `::TestProtocolSurfaceUntouched` |

**「零世界内部字段」如何钉**（派单问的验证设计）：A11 的形态是**响应模型白名单**
（`AnchorMaterializationStatus` 三字段 ＋ `extra="forbid"`）⇒ 由 FastAPI 按 `response_model`
序列化 ⇒ **未声明字段不可能出现**（同 K11 §1 论证 3 的结构性密封思路）。
`test_payload_has_no_world_internals` 正是对这个事实的端到端实测。

### 1.2 真缺口 M-1：诊断路由**未进红线 B 递归扫**（**MEDIUM**，建议补）

- **事实**：`test_m5_authority_surface.py::TestOutboundForbiddenKeys::test_anchors_payload_recursive_clean`
  只扫 `AnchorListItem`（列表项五键）；**`AnchorMaterializationStatus` 未被任何递归扫覆盖**。
- **为何不是 HIGH**：该响应模型是三字段白名单 ＋ `extra="forbid"` ⇒ 权力键**当前不可能**出现；
  且路由**零权力语义**（ready/reason 与权力无关）。
- **风险形态**：将来给 `AnchorMaterializationStatus` 加字段（如 `note`、`player_hint`）时，
  **红线 B 不会自动抓**——它不在递归扫名单里 ⇒ 第二真相源（新的出站面无禁键守卫）。
- **建议钉 M-1**（判据一句话）：诊断路由响应体递归键扫**零** `AUTHORITY_FORBIDDEN_KEYS` 命中。

| # | 钉 | 可证伪判据 | 建议落点 | 归属 |
| --- | --- | --- | --- | --- |
| M-1 | 诊断路由进红线 B 递归扫 | `AnchorMaterializationStatus(...).model_dump()` 递归键扫零命中 9 键（**非抽样**） | `sim/tests/test_m5_authority_surface.py::TestOutboundForbiddenKeys::test_materialization_status_recursive_clean`（**加一钉，不改既有**） | codex 出判据 / 已有测试文件落 |

> **建议落点说明**：加在 `test_m5_authority_surface.py`（红线 B 的家）而非新建文件——
> 红线 B 三面扫（ws/anchors/prompt）应**聚在一处**，拆文件会让「三面」变四家。
## 2. ② 物化失败的玩家可见通道：CR 预备案（**推荐案：终扫兜底，不填表**）

### 2.1 先把缺口说准（S12 说的「无通道」需要修正措辞）

S12 §3.1 判据二写的是「物化失败**裸 500**」。**实测：A11 之后已不是裸 500**——
WS 侧 `load_anchor` 失败会降级为 `load_failed` 帧（`ws.py:881-885`，含「这个档读不出来了。」），
HTTP 侧诊断路由返 200 + `ready=false` + 原因码。
**真正的缺口不是「没有通道」，而是「通道把原因吞掉了」**：

| 层 | 现在给玩家什么 | 丢掉了什么 |
| --- | --- | --- |
| HTTP 诊断路由 | `ready=false` + 五码之一（机器可读） | 玩家看到的**戏内说法**（前端需自行映射，且映射文案无处可钉） |
| WS `load_anchor` 失败 | 单码 `load_failed` + 固定文案「这个档读不出来了。」 | **五码全部压成一个码**：`no_package`（还没存档过）／`rng_unavailable`（不可救）／`snapshot_missing`（老档搬走了）／`event_gap`（世界档有洞）／`corpus_mismatch`（语料对不上）——**玩家与运维都分不清** |

**关键事实（决定推荐案的实测依据）**：WS hook 契约是 `(anchor_id: str) -> bool`
（`ws.py:805-808`）⇒ `AnchorLoadUnavailable.reason` **在 hook 边界就被压成布尔**，
编排层的六码（含 `hooks_unavailable`）**根本没有出站通道**。

### 2.2 词面实测（**这是本稿的判定依据，不是推测**）

对三条候选文案跑现行 `scan()`（本机实测）：

| 候选文案 | `scan()` 命中 | 含义 |
| --- | --- | --- |
| 「这个档读不出来了。」（**现行**） | **零命中** | 「档」**不在**禁词表 ⇒ 现文案本身合规 |
| 「没这个档。」（现行 `bad_anchor`） | **零命中** | 同上 |
| 「这个档回不去了（**快照**不存在）。」 | **命中 `快照`（kind=persist）** | **任何带原因说明的文案必命中** |

补充实测（8 词候选与现行词表的关系）：

- 8 词**全部已在** `BANNED_WORDS`（`重开/读档/存档/快照/回放/游戏/模拟/玩家`）；
- 其中 **`快照`/`回放` 属 `BANNED_WORDS_PERSIST`**（记忆写入即拒，语义最重）；
- `存档/快照/回放/游戏/玩家` 已在 `REWRITE_MAP`（有世界内等价物：账册/留影/复述/日子/主顾）。

### 2.3 CR 预备案（**只预备，不填值**）

**推荐案：终扫兜底（沿 `fork_notice` 体例），本阶段不填 8 词表。**

| 项 | 内容 |
| --- | --- |
| **推荐** | **案 A = 终扫兜底**：任何面向玩家的物化失败文案经 `scan()` 终扫，命中即**退化为无原因兜底行** ＋ `logger.warning`（同 `fork_notice` 的 `ws.fork_notice_degraded` 体例），**不静默放行、不扩词表** |
| **文案要点** | ①**主因一句**用「档/日子」词族（「档」实测零命中，**安全**）；②**原因不进文案**（原因走 HTTP 诊断路由的机器码，前端按码映射）；③退化行必须**仍能区分「读不了」与「没这个档」**（现文案已能）；④**禁**在文案里出现 reason 英文码（`snapshot_missing` 等是戏外词） |
| **触发边界** | 仅当**玩家可见文案**需要携带原因时触发本 CR；**HTTP 诊断路由的机器码不算**（戏外面，词表管不到）；**日志/告警不算**（开发面） |
| **触发时点** | 若前端要「按原因给不同提示」，则走 CR：①**先**试案 A（终扫兜底 ＋ 前端按机器码映射）⇒ 够用则**永不填表**；②案 A 表达不了才考虑**填表**（且只填被实证需要的词，逐词同 CR） |
| **案 B（填表）何时才成立** | 仅当出现**无法用「档/日子」词族表达**的语义，且该语义**必须**进玩家文案。届时**逐词** CR：①该词进 `META_SHELL`（**不是** `BANNED_WORDS`）；②必须双面成立才入（戏外面允许 ∧ Agent 面仍拦）——S6 负钉 `test_meta_shell_words_still_blocked_on_agent_surface` 即该纪律的执行形态 |
| **不成立的做法** | ❌ 把 8 词一次性填进 `META_SHELL`（YAGNI 破：填了就要维护，且未证明必要）；❌ 把原因码写进玩家文案再靠词表兜（**两错叠加**：既出戏又不可测）；❌ 给物化面开 `scan()` 豁免（同 W-A1-1「特例自建判梯 = 第二真相源」） |

**给主树的裁建议（一句话）**：**P0 物化面不需要 8 词 CR**——
现文案（「档」词族）实测零命中，玩家侧根本不需要原因说明（原因走 HTTP 机器码）；
**只有当产品明确要求「按原因给不同戏内提示」时**才走 CR，且**先案 A 后案 B**。
本稿**不填任何词**（纪律：不预填）。

## 3. ③ hooks 缝安规钉（防「桩被换成尽力而为」）

### 3.1 A11 已落（A11 的桩设计正确，本稿只给**加强钉**）

| 已有钉 | 覆盖 | 出处 |
| --- | --- | --- |
| 缺省桩四步全抛 | `HOOKS_UNAVAILABLE` ＋ 零副作用 | `test_m5_materialization_orchestration.py`（L563/L572） |
| 原因码封闭集 | 出口只有「物化五码 + `hooks_unavailable`」 | 同上（L482/L492） |
| 复位成对 | `set_materialization_hooks(None)` 复位成 fail-closed 桩 | `fork_orchestration.py:167-173` |

### 3.2 建议加强钉 M-2（**LOW**，构造隔离体例）

**风险形态**：将来有人把缺省桩从「抛 `hooks_unavailable`」改成「尽力而为」
（例如 `_expand` 返回 `{}`、`_rng` 静默跳过）⇒ 读档会**静默成功但世界态错误**——
比抛异常**更坏**（异常至少有 `load_failed` 帧，静默错误会污染世界线且不可审计）。

| # | 钉 | 可证伪判据 | 建议落点 | 归属 |
| --- | --- | --- | --- | --- |
| M-2 | **桩不许降级**钉（白盒 ＋ 双态） | ①白盒：`fork_orchestration.py` 的 `_unavailable` 四步函数体**零** `return`/`pass`/`None` 早退（只许 `raise`）；②双态：把桩临时换成「尽力而为」实现跑一遍，`hooks_unavailable` 断言**必须转红**（skip-locked 反假绿） | `sim/tests/test_m5_materialization_orchestration.py::TestHooksStubFailsClosed` | opencode（A11 域）＋ codex 判据 |

**为何 LOW**：当前桩实现正确（A11 已落 ＋ 有钉）；M-2 防的是**未来退化**，当下无泄漏面。
## 4. ④ S10 E 系钉复跑清单（M6 物化读档开工前）

**基线实测（`2bd2bff`）**：package ＋ api ＋ orchestration 三件套 **116 passed**。

| # | 复跑项 | 命令/落点 | 判据 | 现状态 |
| --- | --- | --- | --- | --- |
| 1 | E-1 玩家档零写 | `test_m5_materialization_package.py::TestSecurityNailsESeries::test_e1_offline_surface_never_writes_player_anchor` | 物化/分叉面零 `PlayerAnchor(` | ✅ 在位（扫 `anchor_package.py`＋`fork.py`＋离线面 glob） |
| 2 | E-2 玩家档游标冻结 | `::test_e2_cursor_frozen_after_world_progress` | 推进后游标逐字段不变 | ✅ 在位 |
| 3 | E-3 事件不丢 | `::test_e3_events_not_dropped` | 推进 3 tick ⇒ events +3 | ✅ 在位 |
| 4 | E-4 包零权力 | `::test_e4_package_carries_no_power_state` | blob 含 `npc_power` 被剔 | ✅ 在位 |
| 5 | E-5 读档兜底 0 | `::test_e5_anchor_load_leaves_power_fallback_zero` | 读档后 `npc_power` 无行 = 兜底 0 | ✅ 在位 |
| 6 | E-13 火不进包 | `::test_e13_no_fire_baseline_column_added` ＋ `test_e13_no_new_migration_for_package` | 包列集零火列；不为火新增迁移 | ✅ 在位 |
| 7 | **anchor 后事件零影响** | `::test_post_anchor_events_are_invisible` | anchor 后事件对读档窗口零影响 | ✅ 在位（A8 fail-closed 同款） |
| 8 | **父分支可写不封** | `::test_anchor_kind_parent_not_sealed` ＋ `test_anchor_kind_parent_still_appendable` | 读档不封父分支（C6） | ✅ 在位 |
| 9 | **新增缺口 M-3（建议补）** | 见 §4.1 | — | ❌ **未落** |

### 4.1 新增缺口 M-3（**MEDIUM**）：物化读档**未进红线 B 递归扫**的姊妹项

- **事实**：`diagnose_anchor_materialization` 返回的 `MaterializationDiagnosis` 带
  `snapshot_seq`/`steps` ⇒ 路由层丢弃（已密封）；但**没有任何钉断言「物化编排层
  不把权力键带进诊断/物化产物」**。
- **风险**：`Materialization` 产物带 `corpus`（3 表行值）＋`fires` ＋`world`（钩子展开）⇒
  若将来钩子实现把权力态塞进 `world`，**没有钉会在物化链上抓**（E-4 只管 blob，不管钩子产物）。
- **建议钉 M-3**：物化产物 `corpus`/`world` 递归键扫**零** `AUTHORITY_FORBIDDEN_KEYS` 命中
  （world 是钩子产物 ⇒ 正是**构造隔离**该用的地方）。

| # | 钉 | 可证伪判据 | 建议落点 | 归属 |
| --- | --- | --- | --- | --- |
| M-3 | 物化产物零权力键 | `Materialization.corpus`/`world` 递归键扫零命中 9 键（含 **world**——钩子注入面，最易夹带） | `sim/tests/test_m5_materialization_package.py::TestSecurityNailsESeries::test_materialization_artifact_has_no_power_keys` | opencode ＋ codex 判据 |

## 5. ⑤ D-10 攻击面复评（物化读档全链：诊断 → 物化 → 分叉）

**前提**：裁 34 已落「`npc_power` 不进包」＋ E-13 判据（火基准点按需再加列）。
**结论：物化链当前未新增 D-10 攻击面**，残余风险四条：

| # | 残余风险 | 一句判据 | 当前状态 | 归属 |
| --- | --- | --- | --- | --- |
| R-1 | 钩子 `world` 夹带权力 | `Materialization.world` 递归键扫零命中（M-3） | ❌ 无钉 | opencode |
| R-2 | 诊断路由加字段绕过红线 B | 响应体递归键扫零命中（M-1） | ❌ 无钉（结构性密封兜底） | codex 判据 / 任一树落 |
| R-3 | 包内 `corpus_blob` 夹带权力 | blob 编解码零禁键字面量（E-4 在位） | ✅ 有钉 | opencode |
| R-4 | 机器码出站泄漏 | `anchor-materialization-unavailable` 不进 `_TYPE_TITLE`/协议快照（`test_machine_code_still_absent_from_snapshot`） | ✅ 有钉 | kilo |

**D-10 复评结论**：**包面（E-4）与机器码面（K11/R-4）已闭**；**两处未闭**（R-1/R-2）
都是「**将来加字段时无钉可抓**」，当下**零泄漏面**（结构性密封：白名单响应模型 ＋
`extra="forbid"` ＋ blob 白名单）⇒ **不阻 M6 开工**，建议随 P0 施工一并落 M-1/M-3。

## 5.1 M6-S1 执行记录（codex）

- **案 A 已落**：`sim/api/ws.py` 的 `load_anchor` `load_failed` 玩家文案在最终出站边界调用
  现有 `scan()`；命中时记录 `ws.anchor_load_message_degraded` warning，并按固定候选序退化为
  零命中文案。主文案与每个兜底候选均复扫，所有候选再次命中才 fail-closed 为空文案并记录 error。
- **8 词纪律保持**：未修改 `BANNED_WORDS` 或 `META_SHELL`；`META_SHELL` 继续为空。
- **W-A 四钉状态**：`sim/world/authority/` 当前尚未落盘，因此 W-A1-1、W-A1-2、W-A2-1、
  W-A2-2 均保持 `BLOCKED`，不将缺失实现误报为通过。authority 落盘后逐钉执行：
  白盒扫内建词面过滤、核对词表与用例同步、拒绝 `UtilityDecision`/`Intent` 旁路引用，并以同一
  输入切换权力档验证 `willingness_conflict` 的 band 发生变化。

## 6. 钉号总账（本稿 3 条 ＋ 归属）

| 钉 | 描述 | 分级 | 归属 | 状态 |
| --- | --- | --- | --- | --- |
| M-1 | 诊断路由进红线 B 递归扫 | MEDIUM | codex 判据（加一钉到 `test_m5_authority_surface.py`） | 待落 |
| M-2 | hooks 桩不许降级（白盒 ＋ 双态） | LOW | opencode（A11 域） | 待落 |
| M-3 | 物化产物（`corpus`/`world`）零权力键 | MEDIUM | opencode | 待落 |

**零重建声明**：A11 已落的诊断路由 8 钉 ＋ hooks 桩 3 钉 ＋ E 系 6 钉 ＋
`test_machine_code_still_absent_from_snapshot`，本稿**只复跑不重建**（§4 清单 1-8）。

## 7. 变更纪律

- 本稿只出案不施工；M-1/M-2/M-3 落点由主树派单，施工方在自己的单里落。
- **8 词不预填**（§2.3）：本稿**未触碰** `BANNED_WORDS`/`META_SHELL`；
  CR 只**预备触发条件与推荐案**，填值须在「案 A 表达不了」时**逐词**走 CR。
- D-10 不破：§5 的 M-1/M-3 都是 D-10 的持续守卫补强（不扩攻击面，只补钉）。
- 范围判断归主树：本稿给 P0 的安规钉与 CR 预备案，**不裁 M6 做什么**。
- 纪律沿用 S9/S11：钉号与钉名**脚本核对零悬空**（引用既有钉必先 grep `def|class`）。
