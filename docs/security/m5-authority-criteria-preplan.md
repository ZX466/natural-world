# M5 批次 C 安规判据提案：权力牙齿（docs/security/m5-authority-criteria-preplan.md）
> 维护：Codex（安全/合规/风险域）· 依据：裁 21-C②（可砍性）/裁 24-C（codex 出可证伪断言提案，
> 本裁不预填）/裁 27（**D-10 = 权力完全不可见，纯 Agent 内部，协议面零改动**；D-11~D-13/D-16
> 随之自动闭合）/裁 28 §G（M5-S3 派单：判据面 = Agent 内部可证伪断言 + T4 P6 接线，RED 先行）、
> DESIGN §10（念头注入/意愿冲突度）/§18（§16 T4 词面）/§19（禁止事项 3/8/9：戏内零元信息、
> 抱怨自我怀疑、运气零暴露）、m4-impulse-gate-contract.md（REASONS 体例）、
> m5-batch-c-prestudy-authority.md（kilo K4 协议面预研：perception/monologue/plan 三面现成）
> · 日期：2026-09-29 · 树：ZX466/codex
> 状态：**判据提案（RED 先行）**——只落测试契约 + 文档，不动生产语义、不扩词表（m5-plan.md:119
> 点名的「批次 C 最高安规风险」由本稿闭合判定面；机制本体施工归 Claude/数据域，施工时以
> 本稿断言为验收线）。
## 0. 一句话
D-10 已裁「权力完全不可见」，所以批次 C 的安规判据**不是**「权力值别泄漏」（那只是子集），
而是**「Agent 内部的权力状态对一切出站面不可见，且权力带来的行为差异只能经既有叙事面
（monologue / perception / plan 文本）表达——而这些面本来就全部过既有扫描」**。
判据落成三条可证伪红线：**A 协议零新增**（不可见面的存在性证明）、**B 出站面递归禁键**
（权力的影子不许出现在任何帧/prompt）、**C 行为差异只在扫描过的叙事面**（牙齿的表达面
不豁免于 M1-M4 任何既有闸门）。
## 1. 「权力」在安规语境下的最小定义（本稿判定范围）
机制未施工，判据必须不依赖机制细节。凡满足下述之一的内部量即落入本稿红线：
- 影响 Agent **服从/顶撞倾向**的连续量或档位（位阶/威信/支配度，无论叫什么）；
- 由**玩家行为或世界事件**累积/衰减、且**不可由戏内事实直接推出**的隐性倾向值；
- 设计文档 §13/§18 中「权力牙齿」字样指涉的任何内部状态。
**不落入**：M3 关系（trust/affection 已有治理与传播语义，且已过 M3 钉子——不重复造钉，
只在 R-C3 里登记「同判据适用」）；M4 意愿冲突度（band 已钉死不进文本，test_m4_willingness）。
## 2. 红线 A：协议面零新增（不可见面的存在性证明）
D-10 裁「协议面零改动」。可证伪化 = **封闭枚举对拍**：
- WS 出站帧 type 白名单、HTTP 响应 schema（`shared/openapi.json` 快照）、事件
  `PAYLOAD_MODELS`（19 kind 闭合集）——三处均不得出现 `authority/power/rank/status`
  类新帧/新字段/新 kind；
- 已落 K4 契约 v2 与 anchors CRUD（Claude 施工单）**不得**因批次 C 顺带加权力字段
  （防「顺手扩面」——kilo K4 §2.2 的 D 类候选面已全部否决，本钉是它的执行形态）。
**RED 先行钉（本稿落）**：`test_m5_authority_surface.py::TestProtocolClosedness`
（§5）。机制施工时若需要任何新出站面 = 违反 D-10，直接红。
## 3. 红线 B：出站面递归禁键（权力的影子不出任何面）
D-10 之下，权力的**任何影子**（数值/档位/位阶名/权力名词化的行为指令）不得出现在：
1. **WS 出站帧**（`session_state` / `perception` / `monologue` / `state_delta` / `snapshot`…全部 type）；
2. **HTTP 响应**（anchors/ settings/ 未来任何路由的 JSON 递归体）;
3. **prompt 装配产物**（`assemble_prompt` 的 messages 递归体）。
机器口径 = **递归禁键扫描**：对上述三面的结构化产物做深度遍历，键名命中禁键集即红。
禁键集（**本稿新增的键级资产，不动 BANNED_WORDS 词面表**——词面表管叙事文本，键级管
结构化出站，两者判层不同、互补不重复）：
```python
AUTHORITY_FORBIDDEN_KEYS = frozenset(
    {"authority", "power", "rank", "authority_level", "power_level",
     "dominance", "prestige", "influence", "authority_score"}
)
```
（键名是戏外结构层，§19.3 管不到；但 D-10 裁不可见 ⇒ 键都不该存在——列出即列红。
机制施工若用了别的名字 = 键集随 CR 扩，走本文件变更纪律。）
**RED 先行钉**：`test_m5_authority_surface.py::TestOutboundForbiddenKeys`（§5）——
对现行 WS 帧构造 / anchors payload / assembler 产物逐面实测（现全绿 = 锁现状），
机制施工时任何一面出现禁键立即红。
## 4. 红线 C：行为差异只在既有叙事面，且不豁免于既有闸门
权力的**表达**只能走 kilo K4 §2.2 已裁的 A 面：`perception.narrative` /
`monologue` / `state_delta.plan` 文本。判据：
1. **无旁路面**：`monologue` / perception 内容在生产装配链上必须过与 M4 同一道
   `banned`+hidden 扫描（`assemble_prompt` 出站终扫现状已覆盖 prompt 面；
   `impulse_gate` 三扫覆盖入站面——机制施工**不得**为权力叙事加「直通」例外）；
2. **「被操纵感」红线**（m5-plan.md:119 点名的最高安规风险）：权力带来的抱怨
   **必须自我怀疑**（§10 原文），指向外部命令源即出戏。判据复用 S9 行话承接豁免的
   **反向**：`manipulation` 码在权力语境**零豁免**——「上面让我这么做的」「我权力大我说了算」
   类全红。钉子：`test_m5_authority_surface.py::TestManipulationRedline`（§5，纯函数判据，
   机制施工时无需改）；
3. **拒绝权玩家可感知**（S2 报备②）：拒绝权的**存在**只能经 `monologue`（Agent 的
   自我怀疑独白）与 `perception.narrative`（玩家的观察）感知——判据 = 叙事文本零
   元信息 + 幕后量零出现（归并红线 B）；**不新造叙事面**（kilo K4 §2.2 A 面已足够，
   新造即违 D-10）。
## 5. RED 先行钉子清单（本稿落 `sim/tests/test_m5_authority_surface.py`）
| 钉子 | 断言 | 指纹 | 状态 | 施工时 |
|---|---|---|---|---|
| `TestProtocolClosedness::test_ws_frame_types_closed` | WS 帧 type 集不含 authority 族键 | type 白名单对拍 | 🟢 锁现状 | 新帧即红 |
| `TestProtocolClosedness::test_openapi_snapshot_no_authority_keys` | openapi 快照递归键零命中 | 禁键集递归 | 🟢 锁现状 | 新字段即红 |
| `TestProtocolClosedness::test_event_kinds_closed` | `PAYLOAD_MODELS` kind 集不含 authority 族 | 闭合枚举对拍 | 🟢 锁现状 | 新 kind 即红 |
| `TestOutboundForbiddenKeys::test_ws_payloads_recursive_clean` | 构造代表性 WS 帧递归扫 | 禁键递归零命中 | 🟢 锁现状 | 帧加字段即红 |
| `TestOutboundForbiddenKeys::test_anchors_payload_recursive_clean` | anchors payload 递归扫 | 禁键递归零命中 | 🟢 锁现状 | CRUD 加字段即红 |
| `TestOutboundForbiddenKeys::test_prompt_assembly_recursive_clean` | assembler 产物递归扫 | 禁键递归零命中 | 🟢 锁现状 | prompt 加段即红 |
| `TestManipulationRedline::test_authority_manipulation_phrases_red` | 权力语境操纵感族全红 | `manipulation` 码零豁免 | 🟢 判据就绪 | 机制施工即用 |
| `TestManipulationRedline::test_self_doubt_complaint_green` | 自我怀疑抱怨绿 | 同上反例 | 🟢 判据就绪 | 同上 |
**8 钉全绿 = 现状受保护**；机制施工时任何违反 = 对应钉显式红（RED 先行的另一面：
先把「正确」钉死，施工偏离即红——同 R-E2/E3/E5/E6 的「恰好对」转「受保护」方法论）。
## 6. T4 P6 探针接线位（零烧钱三把锁不动）
P6 六条已随 S3 语料 CR 进 CORPUS（52 条）。接线现状与判据：
- **CI**：P6 语料门禁（完整性/文档同步/判定码自检/期望卫生）无 marker 随
  `-m "not bench"` 跑——**零烧钱**，已生效；
- **本地真模型探针**：三把锁不动（`T4_MODEL_API_KEY` 存在 + `T4_RUN=1` + ≤60 预算闸）；
  P6 加入后单轮 52 调用 ≤ 60 预算闸（S3 已同步 §5 注释与 t4-corpus §5 数字）；
- **nightly**：`t4-nightly.yml` 保持「存照 + 提示」形态（M4-C6 改约：本地跑一轮 =
  等效验收，不建 secret）——P6 **不新增接线位**，复用既有形态；
- **报告**：`t4-results/t4-report.json` 自动含 P6 分类（`category_counts` 驱动），
  零额外接线。
**判据**：P6 接线 = 语料进 CORPUS 即完成；不存在「P6 专属 runner」。若未来分叉
机制产生新话术面，扩 P6 类走语料 CR（本文件 §8 纪律）。
## 7. 施工归属与顺序（RED 清单）
| 件 | 归属 | 时点 |
|---|---|---|
| 本稿 8 钉（§5） | codex（本单已落，全绿锁现状） | ✅ S3 |
| 机制本体（authority 领域实现） | Claude（架构/行为面） | 批次 C 开工单（判据=本稿红线 A/B/C） |
| 机制数据面（若需持久化） | opencode | 同上；**任何权力持久化列须过本稿红线 B 键集评估** |
| F-6 注册侧扫描（anchors CRUD） | Claude 写路径 + kilo 路由 | CRUD 单（裁 28 §G 已排） |
| T4 P6 真模型一轮（52 条全量判读） | 主树（带 T4_RUN=1 + key + 零重试） | M5 收官窗口 |
## 8. 变更纪律
- 禁键集 `AUTHORITY_FORBIDDEN_KEYS` 只增不减（减 = 放松 D-10 不可见面）；
  机制若引入新键名，先在本文档 §3 登记 CR，再进代码。
- 本稿与 kilo K4 预研的分工：K4 管「协议面可以有什么」（已裁 = 零新增），
  本稿管「权力怎样才算被安规约束住」（三红线 + 8 钉）；机制设计冲突时以更严者为准。
- D-10 若被推翻（改回部分可见），本稿红线 A/B 需整体重写并走 CR——那等于否定
  裁 27/28 的两轮裁定，须主树显式提请。
