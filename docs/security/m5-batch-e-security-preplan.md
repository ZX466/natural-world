# M5 批次 E 断线演练·安规预研 + 权力复验执行单定稿
（docs/security/m5-batch-e-security-preplan.md）

> 维护：Codex（安全/合规/风险域）· 依据：M5-S10 派单（2026-10-03，批次 E 安规面预研 +
> 权力复验执行单定稿）、m5-security-preplan.md §9（S7 三面盘点，批次 D 已补、本稿补批次 E）、
> m5-authority-criteria-preplan.md §2-4（红线 A/B/C）、m5-anchor-materialization-preplan.md
> （A3 物化四问 + 五原因码固定集 + 4 张不可重建表登记）、m5-fire-data-preplan.md §4
> （A8 物化扩界 + 「不还原火场」fail-closed 声明）、m5-power-budget.md §3-4
> （P10 `POWER_MAX_BIAS=0.2` + flip≤0.25/熵≥阈值「一箭双雕」）、m5-power-threatmodel.md §5
> （S9 复验单：14 自动覆盖 + 4 钉 BLOCKED）、m5-plan.md 批次 E 行（负责域 + 验收口径 +
> 「断多久算回来已变」待定标）· 日期：2026-10-03 · 树：ZX466/codex
> 状态：**纯预研·零代码零 schema**；只出安规面与复验终版，**不抢施工**。
> 约束：词表零扩散（META_SHELL 8 词纪律不变）；D-10 不破；批次 E 不在 §18 缩范围序内。

## 0. 一句话 + 现状快照

**批次 E 的安规命题是三问：①「离线期间世界怎么变」回来时能不能还原；②物化包装什么、
**权力状态进不进包**；③离线期产出的叙事文本是不是「没人看时的免检区」——三问的答案分别是
「已发生必须还原 / 权力不进包 / 离线不是豁免期」。**

现状快照（本机实测，2026-10-03，main `76dd14a` 同头）：

- `sim/world/authority/` **仍不存在** ⇒ S9 §5 的 4 钉（`W-A1-1`/`W-A1-2`/`W-A2-1`/`W-A2-2`）
  **BLOCKED 前提未变**（对象未落，非判据失效；见 §5）。
- 重连路径**已就绪且零新增 schema**：客户端重连首帧即 `sync_request{reason:"reconnect"}`
  （`client/src/net/ws.ts` L56-62）；服务端既有 `session_state_payload`（`ws.py` L891）
  + `full_snapshot`；`load_anchor` 成功路径已**一帧双载**（告知帧 + 全量快照，`ws.py` L882-888）。
- 告知帧**已有 fail-closed 兜底先例**：`fork_notice`（`ws.py` L920-930）对档名终扫，
  命中禁词 ⇒ 退化为无档名兜底行 + `ws.fork_notice_degraded` warning，**不静默放行、不扩词表**。
  离线回归告知句**照此体例**即可（复用 `scan()`，非新判梯）。
- **结构性保证（已存在，零新增）**：`ControlState` 是**连接级**、`unregister` 即丢
  （`ws.py` L274-277「断线重连=新连接新状态」）⇒ 离线期**不存在**「玩家控制态」可落盘，
  这使「离线不得写玩家档」在倍率/暂停/快进三项上**结构上已成立**，只需钉住事件面。
- A8 fail-closed 声明可作**同款判据体例**：`kind="anchor"` 历史点读档**不还原火场**
  ⇒ 读档不吸收「未来的火」；离线回归对「未发生的未来」同理（§1.1 判定）。
- **定标缺口（先于施工）**：`m5-plan.md` §6-3 与 §210 明写「**断多久算回来已变**须由
  Claude 在批次 E 开工前定标」⇒ 本稿给判据形态，**不替 Claude 定数值**。

## 1. ① 断线演练的呈现边界：离线回归是否同理 fail-closed

### 1.1 判定：先分清三个「变」，fail-closed 只对中间那个

| 变的东西 | 是什么 | 真相源 | 回来时怎么办 |
| --- | --- | --- | --- |
| A 世界**已经发生**的事（NPC 移动、坍塌、火灾焦化、语料写入） | **过去** | 事件流（append-only，世界档） | **必须还原**（C6 历史不可销毁；`store.append` 只增不删） |
| B 世界**本会继续但没继续**的（离线期无人驱动、按墙钟该跑却没跑的 tick） | **未发生** | 无事件 ⇒ 无事发生 | **绝不补偿**（＝A8「不还原火场」同款 fail-closed） |
| C 玩家的**会话控制态**（倍率/暂停/在途快进） | 连接级内存 | `ControlState` 随连接丢弃 | **必须丢弃**（重连＝新连接新状态，已是现状纪律） |

**判定（可直接抄进 E 批施工单的一句话）**：离线回归对 B 必须 fail-closed——
**「已发生的必须还原，没发生的不许补偿」**。这正是 §17 验收「离线再回来世界已变」的
安规完整表述：**变的是过去，不是被跳过的未来。**

若实现选择了「按墙钟补算并把结果当发生过」⇒ 那是把 B 伪装成 A，**等价于重掷混沌**
（A3 §1.3 原话：父分支在 anchor 时刻的 rng 不可得，「回退旧存档」会重掷混沌），
且会让 §17 的「世界已变」这句话**同时指两件相反的事**（变了＝真发生；变了＝假补算）。

### 1.2 呈现边界三条

1. **不得用「补算」制造 B**：禁止离线期按墙钟推进 tick 后丢弃其事件（既烧成本又造假历史）；
   也禁止把补算结果塞进玩家档。判据：**离线推进产生的事件数与实际推进 tick 数一致**
   （丢事件即 C6 破：世界档 append-only，丢了补不回来）。
2. **告知帧只讲过去、不承诺未来、且不含元信息/量值**：告知文本是**戏内口语行**
   （`fork_notice` 体例：不含量词数值、不出现分支/快照/系统词）⇒ 离线回归的告知
   **不得**出现「你错过了 X 场火 / 你不在时世界按 X 速度推进 / 你断了 3600 秒」这类
   **元信息或量值**（既破出戏感，也把「离线期发生了什么」变成可推算的元信息）。可讲的只有
   **回来后的现状**（A 类已发生的事），且必须经既有 `scan()` 终扫兜底（同 `fork_notice`：
   命中即退化为无细节兜底行 + warning，不静默放行）。
3. **离线不是豁免期**：玩家断线时 Agent 与世界仍在推进 ⇒ 离线期产出的**叙事文本是正常出站面**，
   不是「没人看的时候」。既有闸门（`banned_words.scan` 出站终扫 / `impulse_gate` 入站三扫
   / 红线 B 递归禁键）**照常生效**，**不得**因「离线期无玩家输入」而开直通例外
   （W-A1-1 同款纪律：机制/特例自建判梯＝第二真相源）。

### 1.3 离线演练的威胁面清单（供 §3 钉化）

| 威胁 | 触发场景 | 既有守卫（复用） | 缺口 |
| --- | --- | --- | --- |
| 离线期事件写玩家档 | 驱动把离线推进结果落 `player_anchors` | m5-plan 批次 E 负责域行（不得写玩家档）；`ControlState` 连接级（控制态结构性无载体） | 玩家档**游标不得前进**（m5-plan §3 验收口径已列该断言）⇒ 需钉 |
| 补算丢事件（C6 破） | 离线按墙钟跑 tick 后丢弃部分事件 | `store.append` append-only + `seq` 单调分配 | 「丢弃」是**代码选择**不是状态 ⇒ 无现成守卫，需白盒/计数钉 |
| 告知帧夹带元信息/量值 | notice 里写「断了 3600 秒」「推进了 N tick」 | `fork_notice` 终扫兜底（只挡**禁词**） | **数值/秒数属结构层，词表管不到** ⇒ 需键级/正则钉 |
| 离线期成为叙事免检区 | 玩家不在 ⇒ Agent 文本不过闸 | 无 | **无豁免**（§1.2 三）⇒ 需钉「离线产出文本照常过闸」 |
| 断线重连泄露内部 id | 告知帧/快照带 branch_id / seq / tick / entity_id | `session_state_payload` 既有纪律（这些一律不出网关；钉 `test_anchor_pointer_keeps_only_narrative_fields` 造数侧多带 `tick` 断言帧里只剩叙事化两项） | 已封；演练期须**复跑**该钉（§3 E-11） |
| 离线期写权力态 | 机制在途，离线期推进顺手调 `PowerStore` | A7 写面 fail-closed 四条 + 分支闸门 | 与在线期同口径；**离线不构成豁免**（同 §1.2 三） |
## 2. ② 物化单安规面：包内容边界（权力状态进不进包）

### 2.1 问题重述（A3 §1.4 已登记，本稿给安规裁决）

A3 §1.4 已把 `npc_power` 登记为**第 4 张不可重建表**（无事件源 ⇒ 事件重放永远重建不出
anchor 时刻的值），并给出两条包路径（(A) 行值进 `corpus_blob` / (B) 补事件），
且明写「**本单只登记，不扩 `corpus_blob` 格式**（归批次 E 物化单）」。
派单要 codex 给的是**第三种可能性的判定**：包内**只读放行**是否可行、推荐哪种。

### 2.2 三个候选方案与安规裁决

| 方案 | 做法 | 安规评估 | 裁决 |
| --- | --- | --- | --- |
| **不进包（fail-closed）** | 包不含 `npc_power`；读档时该表**按未表态兜底 0** 处理 | ①**不违反 D-10**（包是玩家档内面，不出网关，且值永不出站）；②但**违背 A3 §3.2 解锁条件**——该条件要求「3/4 张不可重建表进包」才允许 `kind="anchor"` 物化 ⇒ 若走此案，历史点读档对**权力表**必须 fail-closed（与 A7 头注同款：「在扩包之前，历史点读档对本表仍然 fail-closed」） | ✅ **本阶段采纳**（与 A7/A3 现状一致，零改动） |
| **进包（A3 路径 A）** | `corpus_blob` 扩格式含 `npc_power` 行值 | ①技术上可行（gzip JSON 加一组键）；②**但引入新风险**：包是**玩家档**，`npc_power` 进包 = 「权力态有了存档载体」⇒ 将来若有人给包加出站/诊断面，权力值就有了泄漏路径（D-10 的攻击面从 0 变 1）；③收益有限：历史点读档后权力从 0 重算，与 A7 的「无事件源、只有当前值」语义**不冲突**（重算即可） | ⚠️ **本阶段不做**（D-10 收益不抵风险；归批次 E 施工单再议） |
| **进包但只读** | 包内有值，读档只读不写 | ❌ **最差案**：既扩了包格式（攻击面 +1），又造出「读档后权力可写」的第三真相源；且「只读」在 D-10 下无法验证（值不出站 ⇒ 无观测点 ⇒ 只读承诺不可证伪） | ❌ **否决**（不可证伪的承诺＝没有钉） |

### 2.3 推荐（与 A7/A3 现状同向，零改动）

**推荐：暂不让 `npc_power` 进包，历史点读档对权力表保持 fail-closed。** 理由三条：

1. **D-10 交叉**：进包会给「权力值」造出**第一个持久载体**。目前权力态的唯一载体是
   `npc_power` 表（值永不出站、永不进包）⇒ 攻击面为 0；一旦进包，包就成了第二个载体，
   而包是玩家档（将来极可能接诊断/出站面），**D-10 的「攻击面收敛为 0」论证（S8 §3）
   就被削弱**。不进包则 S8 §3 的推导链完整。
2. **A3 判据不被说谎**：A3 §3.2 的解锁条件（不可重建表进包）若为满足而把权力表塞进包，
   是**为了让条件成立而扩大载体**——正是 A3 §1.4 (B) 被否决的同款反向操作
   （(B) 也是「为了可重建而补事件」）。留 fail-closed 更诚实。
3. **可后补且成本对称**：包格式扩 `corpus_blob` 是「加一组键」的**可后置**动作
   （A3 已说明扩包归批次 E）；而「权力值泄漏」一旦发生是**不可逆的**（append-only 事件流
   里删不掉）。两害相权，**先不扩**。

**「进包但只读」为何不可证伪（一句话钉死）**：D-10 下权力值不出站 ⇒ 包内是否有值
在**外部不可观测** ⇒ 「只读」承诺没有任何观测面可测 ⇒ 不可测的承诺不是承诺，是许愿。

### 2.4 交叉检查：A8 火灾增量后，包内清单是否变化

| 包内成分 | A3 现状 | A8 火灾增量后 | 本稿安规判定 |
| --- | --- | --- | --- |
| 快照指针（`seq`/`tick`） | 有 | 不变 | 已封 |
| `rng_state`（anchor 时刻捕获） | 有（本设计的核心） | 不变 | 已封（离线回归亦依赖它，见 §1.1 A 类） |
| `agent_override`（玩家覆盖副本） | 有（现硬编码 `{}`） | 不变 | **待查**：覆盖副本若将来纳入任何状态，权力不得进 override（D-10） |
| `corpus_blob`（3 张不可重建表行值） | 有 | **不变**（火场中间态不入库 ⇒ 火灾只动可重放表；A9 已施工 `0014 fires`，只存生命周期不存火势 ⇒ 仍属可重放族，见 §2.5） | 已封 |
| `npc_power` | **无**（本稿裁决：保持无） | 不变 | **本稿裁决**：保持不进包 |

### 2.5 与 A9 的交叉（2026-10-03 留言板，施工已落地：`0014 fires`）

A9（opencode）已施工并推送 `395887a`，其结论与本稿一致但**粒度更细**，本稿采信并补记：

- A9 建了 `fires` 表（`0014`），但**只存生命周期**（起火 tick/熄灭 tick/终止态），
  **不存火势中间态**（强度/燃料/蔓延半径）⇒ A8「火场中间态不入库」的裁定**仍然成立**，
  `fires` 属**可重放族**（有事件源 + `fold_fire`）⇒ **物化包不为火扩格式**的结论不变（§2.4 末行）。
- A9 回报一处**与派单的偏差**（已在迁移头注自述）：派单要求「快照双列 CHECK」，
  本表**无** `snapshot_seq`/`snapshot_tick`——理由是「加了是无人写入的**死列**（未来谎言）」。
  **本稿采信该偏差**，并据此补一条批次 E 的前置条件（见 §3.1 E-13）。
- **给批次 E 的一句话**：若真要给火势物化基准点，**随批次 E 加列 + 同款成对 CHECK**
  （体例同 `fires` 的 `ck_fires_end_pair`）——但**先问 D 批施工单**：火势若已能由
  「快照 + 事件窗口重放」逐位重建（A9 已钉「快照↔重放逐位相等」照妖镜），
  则物化基准点是**重复表达**，不必加。
## 3. ③ 施工级安规钉清单（按归属拆四组）

**分组原则**：数据面/物化器 → opencode；出站面 → kilo；演练面/复验 → 我；
离线推进编排（架构+体验）→ Claude。钉号沿 S9 体例（D 组=数据面，K 组=出站，E 组=演练/本稿）。

### 3.1 归 opencode（数据面 + 物化器）

| # | 钉 | 可证伪判据 | 建议落点 | 复用手法 |
| --- | --- | --- | --- | --- |
| E-1 | **离线推进不写玩家档**钉（负钉·白盒） | 离线推进/世界档追加代码零 `player_anchors`/`PlayerAnchor` 写入；判据：正则扫离线推进生产代码（目标文件为 E 批新增）命中 `PlayerAnchor(`/`set(anchor` 即红 | `sim/tests/test_m5_offline_drill.py::TestDrillWritePath::test_offline_never_writes_player_anchor` | m5-plan 批次 E 负责域行、A7 O-1 单入口负钉（`TestPowerWriteSurface`） |
| E-2 | **玩家档游标零前进**钉（正向） | 离线期推进后 `player_anchors.seq`/`tick` 逐字段不变；判据：推进前后该行逐字段相等 | `sim/tests/test_m5_offline_drill.py::TestDrillWritePath::test_player_cursor_frozen` | m5-plan §3 验收口径原句「玩家档游标未动」、A3 §0 事实表 |
| E-3 | **事件不丢**钉（对照 C6） | 离线推进的 tick 数 == 事件行数增量（同事务同批）；判据：`store.append` 后 `events` 行数增量 == 推进 tick 数，缺任一即红 | `sim/tests/test_m5_offline_drill.py::TestDrillWritePath::test_offline_events_not_dropped` | C6 append-only、T1 材料守恒同款「计数相等」判据 |
| E-4 | **物化包零权力**钉（负钉·白盒，本稿 §2.3 裁决） | `corpus_blob` 编解码零 `npc_power`/`power_level`；判据：白盒扫包编解码器零禁键字面量（复用 K11「禁键只允许在闸门模块」体例） | `sim/tests/test_m5_anchor_packages.py::TestPackageSeal::test_package_carries_no_power_state` | K11 `TestWhiteboxNails::test_forbidden_key_literals_only_in_guard_module`、A7 `test_state_columns_are_forbidden_key_tripwires`（命名即绊线） |
| E-5 | **读档对权力表 fail-closed**钉 | 物化包不含权力 ⇒ `kind="anchor"` 读档后 `npc_power` 按「未表态兜底 0」处理且**不报错**（A7 口径）；判据：读档完成且 `materialize()` 返回空 dict（无行=兜底 0） |
| E-13 | **火势物化基准点按需再加列**钉（本轮**不落**） | 批次 E 若要给火势物化基准点，须随本单加列 + 同款成对 CHECK（`fires` 体例），**且先证明「快照 + 事件窗口重放」不能逐位重建**（A9 已钉照妖镜 ⇒ 若已能重建则加列＝重复表达＝未来谎言）；判据：无「快照↔重放逐位不等」的失败用例 ⇒ 不许加列 | `sim/tests/test_m5_fire_state.py::TestReplayMirror::test_replay_equals_snapshot_path`（A9 既有照妖镜钉，收编后复用，**本单不新增**） | A9 `0014_fires.py` 头注「死列 = 未来谎言」偏差自述、S9 D-4 成对不变式进 DB | `sim/tests/test_m5_anchor_packages.py::TestPackageSeal::test_anchor_load_leaves_power_fallback_zero` | A7 头注「在扩包之前，历史点读档对本表仍然 fail-closed」、`test_materialize_filters_and_omits_unknown` |

### 3.2 归 kilo（出站面）

| # | 钉 | 可证伪判据 | 建议落点 | 复用手法 |
| --- | --- | --- | --- | --- |
| E-6 | **告知帧零元信息/量值**钉 | 离线回归告知文本零 `tick`/`seq`/`秒`/`倍速` 等结构层量值（正则扫告知构造）；判据：白盒扫告知文案零数字量词（`fork_notice` 已有同款纪律：「不含量词数值」） | `sim/tests/test_m5_session_state.py::TestOfflineNotice::test_offline_notice_has_no_meta_quantities` | `fork_notice` doc 注（`ws.py` L921）、M5-K3 D-6 叙事化纪律 |
| E-7 | **告知帧终扫兜底**钉 | 告知文本经 `scan()` 零命中（复用 `fork_notice` 体例，命中即退化 + warning）；判据：构造含禁词档名 ⇒ 退化为无细节兜底行且 `ws.fork_notice_degraded` 有记录 | `sim/tests/test_m5_notice_outbound.py::TestOfflineNotice::test_offline_notice_degrades_on_banned` | `fork_notice` L927-930 逐行同款（F-6 出站纵深） |
| E-8 | **重连帧零新增**回归钉 | 重连首帧仍是 `sync_request`/`full_snapshot` 既有形状，帧 `type` 集合零新增；判据：`test_ws_frame_types_closed` 复跑仍绿 + `shared/protocol.ts` 零 diff | `sim/tests/test_m5_authority_surface.py::TestProtocolClosedness::test_ws_frame_types_closed`（既有 10 钉直接复用） | S3 红线 A、批次 E 负责域行「不新增 schema」、`gen-protocol --check` EXIT 0 |
| E-9 | **离线叙事不过豁免**钉（负钉·白盒） | 离线推进/叙事产出代码零「离线期跳过扫描」形态的直通分支；判据：白盒扫离线模块零 `if offline: skip`/「离线跳过」旁路注释与实现 | `sim/tests/test_m5_offline_drill.py::TestNoScanBypass::test_offline_text_still_scanned` | W-A1-1 同款（特例自建判梯＝第二真相源）、红线 C 无旁路 |

### 3.3 归我（演练面 + 复验）

| # | 钉 | 可证伪判据 | 建议落点 | 复用手法 |
| --- | --- | --- | --- | --- |
| E-10 | **断多久算已变**定标钉 | 离线 T tick 后重连，断言世界态与断线前**不同**且玩家档游标未动（§17 验收落成可执行判据）；判据：N 由 Claude 定标后写进常量，演练级 nightly 复跑 | `sim/tests/golden/test_assertions_offline.py::test_offline_return_world_changed`（归 cline nightly，codex 出判据） | m5-plan §3 批次 E 验收口径「断线 N tick → 重连 → 断言世界状态与断线前不同」、T5 golden 扩展 |
| E-11 | **告知帧面零泄露内部 id**回归钉 | 重连/离线回归帧零 `branch_id`/`seq`/`entity_id`；判据：复用既有 `test_anchor_pointer_keeps_only_narrative_fields`（造数侧多带 `tick`，帧里只剩叙事化两项）+ `test_no_banned_world_values` | `sim/tests/test_m5_session_state.py`（既有钉复跑，零新增） | `session_state_payload` doc 注、`_rtoken` 不透明替身体制 |
| E-12 | **零代码边界**钉 | 本稿只出案不施工；判据：E 批施工单里我域只交本稿 + §5 复验终版 | 本稿（无需测试） | S9 D-15、S8 §5 同款 |
## 4. ④ 交叉：S7 §9 三面盘点中批次 E 未覆盖项的补全

S7（`m5-security-preplan.md` §9）盘点了权力/火灾生态/混沌三面，**批次 E 当时未开工**，
故未单独成面。本稿补齐，按三面对齐：

| 面 | S7 §9 覆盖 | 批次 E 增量 | 本稿落点 |
| --- | --- | --- | --- |
| 面① 权力（W-A1/W-A2） | 已覆盖（词面 CR + 意愿管线旁路禁） | **离线期是权力机制的「无人观察期」**：若机制以「玩家不在时多推一点权力」为实现便利 ⇒ 玩家重连后行为分布突变，且**无任何可观测事件解释它** | §1.2 三「离线不是豁免期」+ E-9 |
| 面② 火灾生态（W-D1/D2/D3） | 已覆盖（S9 细化 + K12/A8 对齐） | **离线期火在烧**：火灾是离线期最可能的「已发生」事件（无人驱动蔓延则火停）⇒ 离线回归面对的是「火已灭/未灭」的二值世界；A8 已裁「火场中间态不入库」⇒ 离线**不补算火**（同 §1.1 B 类） | §1.1（离线对 B fail-closed）+ §2.4（包不为火扩格式） |
| 面③ 混沌流（W-C1/W-C2） | 已覆盖（rng_state 零出站 + chaotic 输出禁字符串内插） | **离线期 rng 连续性**：离线推进照常抽签 ⇒ 重连后 rng 状态与「从未离线」逐位一致（T2/C5）；若离线期 rng 被重置 ⇒ 混沌断链（`restore_rng_state` 的 fail-closed 纪律同款） | §1.1 A 类（rng 属已发生）+ §2.4（包内 rng_state 是核心） |
| **新增面④ 断线/物化（本稿新增）** | S7 未成面 | 离线推进（世界档只增）+ 物化包（包自足）两条**新写入面** | §1（呈现边界）+ §2（包内容边界）+ E-1..E-12 |

## 5. 权力复验执行单定稿（S9 §5 落成「接线合入即跑」终版）

### 5.1 4 钉 BLOCKED 的终版判定与解除条件

S9 §5 已判：`W-A1-1`/`W-A1-2`/`W-A2-1`/`W-A2-2` 四钉**自动覆盖不成立**
（它们不是 K11/A7 能连带的面），且因 `sim/world/authority/` **目录不存在** ⇒ **BLOCKED（对象未落）**。
本稿给终版口径：

| 钉 | 判据（承 S9） | 运行命令 | 预期输出 | 解除 BLOCKED 的条件 |
| --- | --- | --- | --- | --- |
| `W-A1-1` | `sim/world/authority/*.py` 白盒扫零内建词面字面量过滤（禁 `if ... in text` 形态） | 见 §5.2 命令块 | 「零命中」PASS 行 | 机制文件落盘（含任一 `*.py`）⇒ 扫得到对象 |
| `W-A1-2` | 机制若引入戏内新词，`banned_words.py` diff 与用例同步（有 CR 引用） | `git diff --stat sim/llm/prompts/banned_words.py` + 机制词面核对 | 无词面漂移 PASS | 机制若**零新增词面** ⇒ 本钉恒绿（无需解除） |
| `W-A2-1` | `sim/world/authority/*.py` 零 `UtilityDecision` 构造参数直改/import | 见 §5.2 命令块 | 「零命中」PASS 行 | 机制文件落盘 |
| `W-A2-2` | 同输入换权力档，`willingness_conflict` 返回**不同 band** | 接线单随附的行为核（Claude 域） | band 随档变化 PASS | **机制接线完成**（不止落文件，还要 `PowerStore`→utility 传导） |

**终版结论**：四钉**不是「等代码写完就跑」的机械等待**，而是分两类——
`W-A1-1`/`W-A2-1` 是**白盒扫描**（文件落盘即解除，只需扫），
`W-A1-2` 是**词表 CR 核对**（零新增词面即恒绿），
`W-A2-2` 是**行为核**（须接线完成才可跑，是四钉里唯一真依赖施工的）。

### 5.2 四钉的可执行命令块（接线合入即粘贴跑）

```powershell
# 前提：cd 到任一工作树；机制落盘后先 git fetch + merge 到含机制的分支
# W-A1-1 + W-A2-1：一次扫两个判据（零命中 = 双 PASS）
$mech = Get-ChildItem -Recurse sim\world\authority\*.py -ErrorAction SilentlyContinue
if (-not $mech) { Write-Output "BLOCKED: sim/world/authority/ 尚未落盘"; exit 0 }
Select-String -Path $mech.FullName -Pattern 'if\s+.*\s+in\s+.*text|banned|BANNED_WORDS|REWRITE' `
  | ForEach-Object { "W-A1-1-HIT: $($_.Filename):$($_.LineNumber): $($_.Line.Trim())" }
Select-String -Path $mech.FullName -Pattern 'UtilityDecision|Intent\(' `
  | ForEach-Object { "W-A2-1-HIT: $($_.Filename):$($_.LineNumber): $($_.Line.Trim())" }
Write-Output "扫描完成：上方零 HIT 行 = W-A1-1 与 W-A2-1 双 PASS"
```

**判据**：输出**零 HIT 行** ⇒ `W-A1-1`/`W-A2-1` 双 PASS；
出现任一 `-HIT` ⇒ 对应钉 FAIL（词面漂移面 / 意愿旁路嫌疑）。

### 5.3 flip≤0.25 / 熵≥阈值断言口径定稿（与 P10 一箭双雕，红线 C 侧写死）

P10 已裁 `POWER_MAX_BIAS = 0.2`（裁 32），并把「flip 守卫」与「熵坍缩守卫」提为两条
**可证伪**断言（`m5-power-budget.md` §4：**flip_rate ≤ 0.25**、动作熵**不坍缩**）。
本稿从**安规红线 C** 侧把同一条断言的口径写死（性能与安规共用，**不另立第二条判据**）：

| 项 | 口径（定稿） | 为什么这是安规命题（不只是性能命题） |
| --- | --- | --- |
| **flip_rate ≤ 0.25** | 权力接入前后，50 NPC 动作分布被改判的 NPC 占比 ≤ 0.25；破限 = **偏置过强** | flip 率过高 ⇒ 权力**在替玩家做决定**，Agent 行为不再「基于处境」而是「基于位阶」⇒ 玩家感到被操纵（红线 C「被操纵感」最高风险） |
| **熵 ≥ 阈值**（P10 定标） | 动作分布熵**不低于**权力接入前基线（P10 实测 2.52→1.80 是越界样本；`MAX_BIAS=0.2` 下应停在 ~2.4 以上）⇒ 熵**坍缩 = 红** | 熵坍缩 = 分布整体推向单一动作 ⇒ 叙事多样消失、世界「变便宜」；熵是**分布坍缩的单一指标**（比 flip 更敏感） |
| **共用一条断言** | flip 与熵**同源同测**（同一权力接入前后对照），不写两套探针 | 派单明写「性能与安规共用一条断言」；两套探针必有一套被绕过 |

**红线 C 侧写死的三句（可直接抄进机制施工单的安规验收）**：

1. `POWER_MAX_BIAS = 0.2` 是**安规常量不是性能调参**——它同时守 flip≤0.25 与熵≥阈值
   （P10 §4 已论证「一箭双雕」：熵坍缩＝操纵前兆）。
2. 断言**在离线/重连后同样成立**（本稿 §1.2 三延伸）：离线期不因「无玩家观察」而放宽偏置。
3. flip/熵任一破限 ⇒ **机制接线 fail-closed**（不降级放行），与 A7 写面 fail-closed 纪律同款。

### 5.4 复验执行单（一页速查，接线合入即跑）

| 顺序 | 跑什么 | 命令 | PASS 判据 | 归属 |
| --- | --- | --- | --- | --- |
| 1 | K11 18 钉 + A7 45 钉（自动覆盖面） | `uv run pytest sim/tests/test_m5_power_api.py sim/tests/test_m5_power_state.py -q` | 全绿（接线只须不破既有钉） | 已有 |
| 2 | W-A1-1/W-A2-1 白盒双扫 | §5.2 命令块 | 零 HIT | 我 |
| 3 | W-A1-2 词表 CR 核对 | §5.2 后 `git diff --stat sim/llm/prompts/banned_words.py` | 零新增词面（或新增有 CR+用例） | 我 |
| 4 | W-A2-2 意愿 band 行为核 | 机制接线单随附核 | 同输入换档 band 变 | Claude（我复核） |
| 5 | flip≤0.25 + 熵≥阈值 | 机制接线单随附断言 | 两项均不破 | pi 定标（我复核口径） |
| 6 | 批次 E 面（若 E 批已合入） | `uv run pytest sim/tests/test_m5_offline_drill.py sim/tests/test_m5_anchor_packages.py -q` | 全绿（本稿 E 组钉） | 三方 |

### 5.5 M6-S2 追加复验（S1 终扫兜底防摘）

| 顺序 | 跑什么 | 命令 | PASS 判据 | 归属 |
| --- | --- | --- | --- | --- |
| 7 | S1 `load_failed` 终扫兜底回归 | `uv run pytest sim/tests/test_m5_session_state.py::TestLoadAnchorEmitsSessionState -q` | `13 passed`；钉 `test_failure_message_is_terminal_scanned` / `test_failure_message_never_bypasses_scan_call` 均在 | codex |
| 8 | 摘除/直通负核（临时补丁，核后撤销） | 临时把 `_load_failed_frame` 的主文案出站条件改为恒真后跑同一命令 | `test_failure_message_is_terminal_scanned` 或 `test_failure_message_never_bypasses_scan_call` 转 FAIL；临时补丁不提交 | codex |

> 执行提示：先复跑钉集确认现状，再做第 8 行负核证明可摘性；负核后必须 `git diff` 清零，
> 不把补丁留在工作区或提交。

## 6. 变更纪律

- 本稿只出案不施工；E-1..E-12 对齐三方回执后，施工方在自己的单里落钉。
- **「断多久算回来已变」仍待 Claude 定标**（m5-plan §6-3）；本稿给判据形态（E-10）不替裁数值。
- **物化包裁决（§2.3）可被推翻**：若批次 E 确需历史点读档还原权力态，须先在本稿 §2.2
  更新裁决并走 CR（推翻的是 D-10「攻击面收敛为 0」论证，不是一条小口径）。
- 词表零扩散：META_SHELL 8 词填值纪律不变（本稿不触碰；E-7 复用现行 `scan()` 不扩词表）。
- D-10 不破：本稿全部裁决与钉均以「权力零出站、攻击面为 0」为前提。
- 纪律沿用 S9：钉号脚本核对零悬空（RUF003 全角括号；负钉白盒断言落源码级）。
