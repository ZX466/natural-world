# M5 批次 C 权力机制·安规威胁模型（docs/security/m5-power-threatmodel.md）

> 维护：Codex（安全/合规/风险域）· 依据：M5-S8 派单（2026-10-02，裁 31-1 施工下放后）、
> 裁 27/28（D-10 裁为 **权力完全不可见，纯 Agent 内部，协议面零改动**；D-11~D-13/D-16 随之
> 自动闭合）、m5-authority-criteria-preplan.md（S3 三红线 + 8 钉）、m5-security-preplan.md §9.1
> （W-A1/W-A2）、kilo K4 预研（协议面可承载/必封面）、m3-evidence-chain.md §8-7（写入门不被
> 新列绕过）、memory-scan.md（S1 唯一写入门）· 日期：2026-10-02 · 树：ZX466/codex
> 状态：**纯预研·零代码零 schema**；只出威胁模型与施工级安规钉清单，**不抢施工**——
> 钉子清单是 kilo/opencode 本轮施工的安规输入（他们回执对本清单逐条对齐）。
> 约束：词表零扩散（META_SHELL 8 词填值纪律不变）；D-10 不可见不破。

## 0. 一句话 + 现状快照

**权力机制（D-10 裁不可见）的安规命题不是「怎么藏数值」，而是「不可见面一旦被写入方
或投影层碰到，最小暴露路径有哪几条、每条由哪个既有守卫兜住、哪条是新缺口」。**

现状快照（本机实测，2026-10-02）：`sim/world/authority/` **不存在**；`0013` 迁移未落；
全仓 `authority` 字样仅两处——`sim/world/__init__.py`（目录占位）与
`sim/tests/test_m5_authority_surface.py`（S3 的 10 个判据钉）。即**机制零实现**，
本稿是它的**安规前置**而非事后补丁。

## 1. W-A 逐条展开

### 1.1 W-A1：机制引入新戏内词面绕过词表 CR

| 项 | 内容 |
|---|---|
| ① 攻击面 | 谁 = 权力机制作者（Claude 域，sim/world/authority/ 新文件）；从哪个面 = **叙事面**（`monologue` / `perception.narrative` / `state_delta.plan` 文本，装配链经 `assemble_prompt`）；什么输入 = 机制自带的位阶称谓（「按品阶/按资历/按身份」类词） |
| ② 守卫复用 | `assemble_prompt` 出站终扫（`banned_words.scan`，命中即 `PromptAssemblyError` 拒出站）；`MemoryWritePipeline.decide` S1 唯一写入门；`impulse_gate` 入站三扫（I-1 banned / I-3 操纵感）；S6 判层负钉（`scan()` 源码零 `META_SHELL` 引用——戏外表接不进 Agent 面） |
| ③ 缺口 | 机制若在**自己模块内**自带词面过滤（`if "位阶" in text: rewrite`），就是**第二套判梯**——绕过 `banned_words` 的 CR 纪律，且词面永不同步（与 `banned_words.py` 模块注「映射表与词表同模块维护，漂移即 CI 红」精神相悖）。**机制侧自建过滤 ≠ CR 流程**：CR 是「加进 `banned_words.py` + 17 用例词面守卫 + 文档同步」，机制自建是「不登记、不守卫、不文档」 |
| ③ 施工级钉 | **W-A1-1（负钉·白盒源码级）**：机制生产代码零内建词面字面量过滤——判据：`sim/world/authority/*.py` 中不得出现 `if ... in text` 形态的词面判定（正则扫生产代码，禁 `re` 搜词表模式 + 禁硬编码词表字面量）。建议落点：`sim/tests/test_m5_power_gate.py::TestNoInlineLexicon::test_authority_module_has_no_inline_word_filter`（白盒源级手法同 S6 判层负钉 `test_agent_dispatch_never_reads_meta_shell`）<br>**W-A1-2（CR 流程钉）**：机制新增的戏内词面必须出现在 `banned_words.py` 且 t4-corpus/banned 用例同步——判据：`git diff` 含 `banned_words.py` 新增词面时，`test_banned_words_*` 全绿方可通过（CR 门禁既有，改动只增不减纪律不变） |
| ④ D-10 相容 | 相容且互为加固：D-10 说「不可见」，W-A1 说「不可见的载体不许自建旁路」——若权力词走自建过滤进叙事面，等于**给不可见面造了一条可见通道**。W-A1 是 D-10 的「防止实现绕过不可见裁定」条款 |

### 1.2 W-A2：决策偏差旁路意愿管线

| 项 | 内容 |
|---|---|
| ① 攻击面 | 谁 = 机制作者；哪个面 = **决策层**（utility 打分 / Intent 选择）；什么输入 = 机制累积的内部量（位阶/影响力档位），表现为「因权力而服从/顶撞/沉默」的行为偏移 |
| ② 守卫复用 | M4 `will.py` 四档模板（`_TEMPLATES`）＋ `willingness_conflict` 判定（band1/2/3 产出 conflict，band 字段**已钉死不进文本**，见 `test_m4_willingness`）；M5-S1 §5「读档不得作为抱怨/操纵对象」；S3 红线 C（`manipulation` 码零豁免：权力语境操纵感全红，`TestManipulationRedline` 已锁） |
| ③ 缺口 | 若机制**直改** `UtilityDecision` 的 scoring 字段（不经 `willingness_conflict` 产 verdict），则行为偏移对玩家不可解释、对 T4 不可测——T4 P3 类（意愿抱怨合规）失去判据。**更深一层**：机制若把权力量写进「意愿 band」，band 是软判据（T4 P3 靠人工抽检档位区分度），会污染既有档位语义 |
| ③ 施工级钉 | **W-A2-1（负钉·白盒）**：authority 模块零 `UtilityDecision` 字段直改——判据：`sim/world/authority/*.py` 中不得出现对 `UtilityDecision`/`Intent` 构造参数的赋值式引用（import 该类型即红，源级白盒）。建议落点：`sim/tests/test_m5_power_gate.py::TestBypassingWillingness::test_authority_does_not_touch_utility_decision`（白盒源级，同 S6 手法）<br>**W-A2-2（正向钉）**：权力影响必须经 `willingness_conflict` 产出 band——判据：存在一条权力测试用例，`willingness_conflict` 对「高位+被挑衅」与「低位+被挑衅」返回**不同 band**（可证伪：同输入换权力档，band 必须变；band 不变则权力未接线或接线无效）。建议落点：`sim/tests/test_m5_power_gate.py::TestBypassingWillingness::test_authority_shifts_willingness_band` |
| ④ D-10 相容 | 相容：D-10 禁的是「状态可见」，W-A2 禁的是「行为不可解释」——**不可见 ≠ 不可生效**：权力应作为「Agent 内部倾向」影响决策（这正是 D-10「纯 Agent 内部」的含义），但影响必须走既有可判定的管线（意愿冲突度），否则机制变成不可测的黑箱 |

## 2. 施工级安规钉清单（按归属拆两组）

**分组原则**：kilo = API 面（出站投影 + 错误码）；opencode = 数据面（写路径 + 分支隔离）。
每钉一句可证伪判据 + 建议落点文件名，**kilo/opencode 回执逐条对齐**。

### 2.1 归 kilo（API 面）

| # | 钉 | 可证伪判据 | 建议落点 | 复用手法 |
|---|---|---|---|---|
| K-1 | 出站剥除**正向**钉 | 任一读档/世界态路由响应体递归键扫**零** `AUTHORITY_FORBIDDEN_KEYS` 命中（9 键全集，非抽样） | `sim/tests/test_m5_power_gate.py::TestOutboundStrip::test_no_authority_keys_in_any_route_payload` | S3 红线 B 递归扫（`_iter_keys`/`_forbidden_hits` 现成工具） |
| K-2 | 出站剥除**负钉**（防「剥除层被绕过」） | 直接调用路由 handler（不经剥除层）得到的 dict 键集 ⊆ 白名单五键 —— 即剥除是**handler 内建**而非外层包装，外层包装被摘掉仍不出键 | `…::TestOutboundStrip::test_handler_itself_omits_authority_fields` | S6 判层负钉源码级手法：`inspect.getsource(handler)` 零禁键字面量 |
| K-3 | **构造隔离**（X2 体例，最高优先） | 合成一条含权力键的内部态（构造器实造）→ 经真实路由 → 响应体零命中。防「用干净样本测剥除」的假绿 | `…::TestOutboundStrip::test_strip_survives_dirty_input` | M3 X2 构造隔离扫描同款 |
| K-4 | 错误码 **fail-closed** 钉 | 权力相关请求命中非法输入时返回**结构化机器码**（`/errors/...` 形态，走 ProblemDetail 四键），不得裸 500/静默忽略 | `…::TestErrorCode::test_authority_error_is_structured_problem_detail` | F-6 双钉（`/errors/anchor-name-rejected` 先例）+ `errors.py::_TYPE_TITLE` |
| K-5 | 错误**文案戏外**钉 | 错误 title/detail 不含权力术语（玩家面不出「位阶」等戏内未定义词） | `…::TestErrorCode::test_authority_error_text_is_meta_shell` | 戏外面判层（M5-S6 CR-1 §2.2 四层模型第 3 层） |
| K-6 | WS 帧类型**闭合**回归钉 | 帧 type 集合不含权力族（承接 S3 `test_ws_frame_types_closed`，机制施工后复跑） | `sim/tests/test_m5_authority_surface.py`（既有钉复跑，不新增） | S3 红线 A |
| K-7 | 递归扫描器**共用**钉 | 剥除层用的扫描器与测试用的一致（同一 `_forbidden_hits`，不各写一份） | `…::TestOutboundStrip::test_strip_and_test_share_scanner`（源级：剥除模块 import 测试扫描器所在模块） | 反对「测试自己造判梯」 |

### 2.2 归 opencode（数据面）

| # | 钉 | 可证伪判据 | 建议落点 | 复用手法 |
|---|---|---|---|---|
| O-1 | 写路径**输入信任边界**钉 | 权力态写入只经 store/engine 单一入口，零裸 `session.add()` / 裸 UPDATE 直写 | `sim/tests/test_m5_power_gate.py::TestWritePath::test_authority_write_goes_through_store`（源级白盒：禁裸 add/直写 SQL） | S3 `test_no_persistent_surfaced_state_without_branch_id` 白盒扫描体例 |
| O-2 | 写路径 **fail-closed** 钉 | 非法权力态 payload（越界/缺字段/错误类型）写入 → 抛错且**零行落库**（不是静默截断） | `…::TestWritePath::test_invalid_authority_state_rolls_back` | T1 范式：正向落库断言 + 负向零写（**裁 28-A 的正向钉教训**：只有负向回滚断言会被「压根没写」的假实现骗过，故必须配正向落库断言） |
| O-3 | **branch_id 隔离·不可见**钉 | 读路径按 `branch_id` 过滤；兄弟分支权力态互不可见（跨分支 id 视作不存在） | `…::TestBranchIsolation::test_sibling_branch_authority_not_visible` | R-E5（分叉可见集钉：`iter_valid`/`get` 分支过滤同款） |
| O-4 | **branch_id 隔离·不可写**钉 | 向已弃分支（`status != 'active'`）写权力态 → `InactiveBranchError`，零行写入 | `…::TestBranchIsolation::test_cannot_write_authority_to_abandoned_branch` | 裁 5 分支闸门 `InactiveBranchError` 既有面 |
| O-5 | fork 克隆**幂等**钉 | fork 不克隆权力态（内部量随分支重算）**或**克隆但不跨分支污染——二者择一但必须显式：判据=fork 后子分支权力态与「父分支被弃」语义自洽（不可出现「继承父分支权力位」的隐式跨分支继承） | `…::TestBranchIsolation::test_fork_authority_lineage_is_explicit` | R-E2（祖父指针保留钉：显式性优于隐式继承） |
| O-6 | 迁移 **CHECK/索引** 钉 | 0013 迁移后：权力列有域约束（越界 CHECK）+ 分支索引（读写都按 branch 过滤） | `…::TestSchema::test_authority_columns_have_check_and_index` | 0008 四件体例（`ck_knowledge_evidence_pair` + `idx_knowledge_evidence`） |
| O-7 | **零 out-of-band** 钉 | 权力态不出事件流（`PAYLOAD_MODELS` 仍 19 kind 闭合集——若新增 kind 必须先过 codex CR） | `sim/tests/test_m5_authority_surface.py::test_event_kinds_closed`（既有钉复跑，闭合集断言会自动捕获新增） | S3 红线 A③ |

## 3. D-10 相容论证：不可见 = 最小攻击面

D-10 裁「权力完全不可见」在安规上等价于**最小攻击面定理**，推导三步：

1. **可见面 = 可攻击面**。任何出站字段都是潜在的信息泄漏通道（被观测即可被推断：
   位阶数值可被玩家通过行为差分反推——即使数值本身零出站，「因权力而多问一句」的行为
   差分也是侧信道）。裁 D-10 选不可见 = **把攻击面收敛为 0**，是安规上的最强形态。
2. **不可见 ⇒ 通道须零**：因此 WS 帧类型/openapi schema/事件 kind 三处闭合集
   **不得新增**（S3 红线 A 已是此断言）；任何「借既有字段夹带」（如在 `state_delta`
   的某字段里塞权力派生量）都是**侧信道复活**——K-1 递归扫描抓的是键名，
   **值域夹带需靠 W-A1 词面 + K-2 源码白盒双兜**（故 K-3 构造隔离是最高优先：脏输入才见真章）。
3. **不可见不豁免行为纪律**：D-10 只说「状态不可见」，没说「行为不可生效」。权力**应当**
   影响 Agent 内部决策（否则机制无意义），但影响必须经**可判定的管线**（W-A2-2：意愿
   band 随权力档变化）——**「不可见的是状态，可测的是行为」**，这两句合起来是 D-10 的
   安规完整表述，也是本机制的验收句雏形。

## 4. 施工后复验单（下一波派单用：逐钉核）

| 钉 | 复验动作 | 判红条件 |
|---|---|---|
| W-A1-1 | 白盒扫 `sim/world/authority/*.py` 词面字面量过滤 | 命中内建过滤 → 词面漂移面 |
| W-A1-2 | 核 `banned_words.py` diff 与用例同步 | 有词面无守卫 = CR 未走完 |
| W-A2-1 | 白盒扫 authority 模块对 `UtilityDecision` 的引用 | import 即红（旁路嫌疑） |
| W-A2-2 | 意愿 band 随权力档变化 | 同输入换档 band 不变 → 机制无效或旁路 |
| K-1..K-3 | 递归扫描 + 源码白盒 + 构造隔离三联 | 任一漏 → 出站剥除面有洞 |
| K-4/K-5 | 错误码结构化 + 文案戏外 | 裸 500 或台词带权力词 → fail-closed 破 |
| K-6/K-7 | 既有闭合集钉复跑 + 扫描器共用 | 新 kind / 各写判梯 |
| O-1/O-2 | 写路径单入口 + 非法输入零落库（**必须配正向落库断言**） | 裸写或只负向断言 |
| O-3..O-5 | 分支隔离三钉（不可见/不可写/克隆显式） | 任一跨分支面开口 |
| O-6/O-7 | 迁移约束 + 事件闭合集 | 无 CHECK/索引或新增 kind |

## 5. 变更纪律

- 本稿只出案不施工；钉清单对齐 kilo/opencode 回执后，施工方在自己的单里落钉。
- D-10 若被推翻（改回部分可见），本稿 §3 需整体重写并走 CR——那等于否定裁 27/28。
- 禁键集 `AUTHORITY_FORBIDDEN_KEYS`（9 键，键级）随本稿不变；机制若引入新键名，
  须先在本稿 §2 登记再进代码。
- 词表零扩散：META_SHELL 8 词填值纪律不变（本稿不触碰）。
