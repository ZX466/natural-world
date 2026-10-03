# M5 收官预告盘点（docs/config/m5-c10-closure-inventory.md）

> 维护：cline（依赖/配置/文档域）｜基线：main `76dd14a`（六树同头）｜单号：M5-C10（零代码）
> **性质：只读盘点**——本单**不关闭任何挂账**，只做「谁 / 依赖什么 / 预计哪轮关」三列登记。
> 关闭动作一律由对应单的 owner 执行；本稿对他人域文件**只读不代改**（含 `docs/arch`、`docs/security`、`docs/api`、`sim/`）。
> **数据来源全部为实测**，不采信转述：台账逐行扫 `⏳`、git 逐 commit 核 `shared/` 面、pytest 实跑 A6 钉。

---

## 0. 一页速览

| 问 | 答 |
|---|---|
| 台账里还有 `⏳` 吗 | **零个**。README §5.4 全 29 行 + §5.3 全 M4 行状态列 100% `✅`（实测）。`⏳` 仅存于 §2 图例文字与 C9 runbook 自指行 |
| 挂账清点出几项 | **9 项**（§1），其中 **3 项卡在别人手上**（Claude 域 2、用户 1），**6 项本域或已定标待跑** |
| M5 有协议版本变更吗 | **有，且未登记**（§2）——`fast_forward` 等 4 次 `shared/` 改动，`versioning.md §7` 零 M5 行，`v` 仍 `1.0` |
| 收官门禁能过吗 | **当前不能**（§3）——R-4 施工未落 ⇒ A6 钉 **6 skip**（实测），收官门「台账零挂账」不成立 |
| T4 能跑吗 | **不能**，缺 key 与执行许可（§4 已备分钟级行动单，key 一到即可零准备执行） |

**本单最重要的一条**（§2.3）：派单假设「若 M5 全程零登记需求，写明论证收官即用」——
**实测前提不成立**。M5 确实动了协议面（K3 新增 WS action `fast_forward` + HTTP 路由 `/api/anchors/current`），
按 `versioning.md §3` 分类属 **minor**（新增消息类型/新增可选字段），但 §7 表**一行未加**、`_PROTOCOL_VERSION` 仍 `"1.0"`。
**这不是本单能自行修的**（`versioning.md` 归 kilo 域、版本号归架构决策）⇒ 报 Claude 裁决。

---

## 1. 挂账全清点（9 项）

**清点口径**：README 台账状态列全 `✅`（无 `⏳`），故挂账**不在台账里**，而在各域预研稿的「待派/待裁/待定标」登记行。
下表按「收官前是否必须关」分 **A 类（收官阻断项，3 项）** 与 **B 类（可带入 M6，6 项）**。

### 1.1 A 类 — 收官阻断（不关则收官门不成立）

| # | 挂账项 | 谁 | 依赖什么 | 预计哪轮关 | 实测现状（`76dd14a`） |
|---|---|---|---|---|---|
| A1 | **R-4 施工未落**（`anchors.py` 游标分支硬编码 `'main'`） | **Claude**（写路径/架构） | 只需改 `sim/api/anchors.py` 3 处字面量 → 接 `branches.is_current` | **M5 收官轮**（唯一真阻断） | L274 `WHERE branch_id = 'main'`、L345 `branch_id="main"` **仍在**；A6 钉实测 **5 passed / 6 skipped**，6 skip 全是「施工未落」 |
| A2 | **T4 真跑 52 条** | **用户**（key）＋ **Claude**（执行许可）＋ cline（跑） | 三把锁：key 存在／`T4_RUN=1`／≤60 预算闸 | **M5 收官轮**（用户给 key 后分钟级可跑，§4） | 本轮 env 实测 `T4_API_KEY` 未设、`T4_RUN` 未设；`--collect-only` 基线 53 collected ≤ 60 预算闸 |
| A3 | **S8 复验 4 钉**（W-A1-1／W-A1-2／W-A2-1／W-A2-2） | **codex**（钉）＋ **Claude**（W-A2-2 唯一真依赖接线） | W-A1×3 属「文件落盘即解」；**W-A2-2 须 `sim/npc` 决策层消费权力档** | **M5 收官轮**（codex 已出执行版 `b104882`，等接线） | codex S10 已把 4 钉 BLOCKED 分类解除；`sim/npc/` 存在但 `power` 消费面**未接线** |

### 1.2 B 类 — 可带入 M6（收官不阻断，须有主即可）

| # | 挂账项 | 谁 | 依赖什么 | 预计哪轮关 | 实测现状 |
|---|---|---|---|---|---|
| B1 | **P11 / W-D3 蔓延事件预算 N 值** | **pi**（定标机） | 需定标机跑 `fires` 事件量级 | M6 首轮 | opencode A9 已给 **advisory 建议 N=2**；K12 待裁点 5 采①「N 由 pi 定标机定」⇒ **建议直接接 N=2 起跑**，不必等定标 |
| B2 | **P5 措辞生成载体**（因果未知「应该能行/不好说」） | **Claude**（架构域） | prompt 装配 + 措辞生成 | M6 | 全仓**零实现载体**（m4-closure-preaudit §2 起登记，三轮未动）；T4 探针集已备好，措辞落地即可跑 |
| B3 | **批次 E 物化单**（`anchor_packages` 施工） | **opencode**（数据面）＋ Claude 派单 | 迁移号 **待定**（0011~0013 已占 main；0014 在 A9 分支未合） | M6 | A3 设计稿已可施工（§3.3 改动面清单齐）⇒ 号段须按 A9 合入后实际 head 定，**不可先占 0015** |
| B4 | **R-4 复验缺口 G1/G2/G3** | **kilo**（G1/G2 补钉）＋ **opencode**（G3） | G1 状态码未钉死、G2 另两种 0 行情形无钉、G3 钉与施工冲突 | M6 或随 A1 同轮 | kilo K13 已出复验单 `02b331d`（基线 5 passed/6 skipped）；**G3 有陷阱**：A1 施工会让钉 5 由绿转红，须 opencode 更新为「子当前+父 abandoned」 |
| B5 | **CHAOS / POWER 定标轮** | **pi** | 权力向量化 tick 成本（≈174x 已实测）+ 混沌接线 | M6 | P9/P10 预算案已交；缺的是**合入后定标机复测**（P10 权力、S8 `flip≤0.25`） |
| B6 | **R-5③ / E-13 物化基准点判据** | **codex**（判据）＋ opencode（执行） | E-13：火势物化基准点须先证「快照+重放不能逐位重建」才许加列 | M6 | A9 已把 `fires` 登记进可重放族 ⇒ **包不为火扩格式**结论成立；E-13 是防未来滥加列的闸 |

### 1.3 已关闭（曾挂账，本轮实测确认可销）

| 曾挂账项 | 销账依据（实测） |
|---|---|
| **S8 复验单「未出执行版」** | codex S10 `b104882` 已出（4 钉 BLOCKED 分类解除 + 可执行命令块）⇒ 单**已关**，剩 A3 的接线 |
| **K12 火灾出站面零变更「无守卫钉」** | kilo K13 `02b331d` 15 例守卫钉（10 即绿/5 skip-locked）⇒ **已关** |
| **C8 报备的 2 项 hash 待订正** | main `2471850` 已「K2 hash 订正 + 6 行 hash 回填」⇒ **已关** |
| **批次 D 火灾数据面** | opencode A9 `395887a`（0014 + FireStore + 43 钉）**已交付，未合 main** ⇒ 单已关，**待收编** |

---

## 2. versioning §7 登记面盘点（**结论：M5 有 minor 级协议变更，§7 零登记**）

### 2.1 实测：M5 期间动过 `shared/` 的 commit（4 个）

| commit | 主题 | `shared/` 改动 | 协议面性质（按 `versioning.md §3`） |
|---|---|---|---|
| `a149bb9` | M5-K3 批次 B：`fast_forward` action / session 首帧 / anchors current | openapi **+84/-2**、protocol.ts **+69/-3** | **minor ×2**：① WS `action` 枚举**新增成员** `"fast_forward"`（＝新增消息类型档）；② HTTP **新增路由** `/api/anchors/current` ＋ 新 schema `SessionAnchor` |
| `aca9d3f` | M5-K8 R-3①③ 快照对齐 | openapi +19、protocol.ts +26 | **minor**：新增 `GET /api/anchors/{id}` 路由；另 `name` 加 `minLength/maxLength` 约束（收紧，非新增） |
| `7dc8d69` | M5-K10 PlanDelta schema 补齐（裁 19 CRITICAL） | openapi +10、protocol.ts +5 | **minor**：`PlanDelta` 补进封闭 schema（补漏，非破坏） |
| `b188ba0` | M5-K2 D-8 rtoken 口径订正 | openapi +1/-1、protocol.ts +1/-1 | **真零变更**：仅 `RToken.description` 文字 ⇒ §7 已有注记，**口径正确** |

### 2.2 现状核对（三处，结论一致）

| 载体 | 现状 | 是否与 M5 变更相符 |
|---|---|---|
| `versioning.md §7` 登记表 | 只有 **1 行 `1.0`（2026-09-19 基线）** ＋ K2 一条「形态与版本号均不变」注记 | ❌ **无任何 M5 行** |
| `sim/api/ws.py:60` | `_PROTOCOL_VERSION = "1.0"` | ❌ 未随 minor 增量升 `1.1` |
| `shared/openapi.json:5` | `"version": "1.0.0"`（FastAPI app 级 `0.1.0`，与协议号不同轴，可不动） | ✅ 不适用（见 §2.4 注） |

### 2.3 为什么这不是「零变更」——三点论证

1. **K12 的「零变更」是 K12 单的结论，不是 M5 全程的结论**。K12 火灾预研确实论证了 WS/HTTP 出站面零变更（火光走 `lights[].kind` 自由字符串），kilo K13 已把它钉成 15 例守卫钉。**但 K3 早在 K12 之前就新增了 `fast_forward` action 与 `/api/anchors/current` 路由**——两者是不同单的不同结论，不能互相覆盖。
2. **`versioning.md §3` 的分类表直接命中**：「新增消息 type → minor」「新增可选字段 → minor」。`fast_forward` 是 `set_control` 消息 `action` 枚举的新成员，落在「新增消息类型」行；`/api/anchors/current` 是新增路由，旧 client 不感知（§3 铁律：静默忽略，不崩溃不出戏）⇒ **向后兼容，按定义是 minor，不是 major**。
3. **兼容性风险实际很低，但登记义务独立于风险**。`_ERROR_UNKNOWN_TYPE`（`ws.py:75`）与 §3 铁律共同保证旧端见到 `fast_forward` 不会崩；client 侧 `net/protocol.ts:21` 已同步注释。**所以升 `1.1` 无破坏面**——正因如此，**不登记才是缺口**：登记表失去了「协议面何时变过」的可追溯性，而收官轮正是要固化这种可追溯性。

---

## 3. 收官轮门禁清单预告

### 3.1 判定标准（对照 M2/M3/M4 体例）

| 里程碑 | 体例 | 收官判据出处 |
|---|---|---|
| M2 | 九轮收编，**零新依赖** | `docs/README.md` §5.1 标题行 |
| M3 | 收官门预审体例：钉子清单全绿 ＋ 功能非 bench 全量 ＋ S4 10k 零回归；结论 **1104 passed / 0 failed** | `docs/security/m3-closure-preaudit.md` |
| M4 | 收官门预审体例：四钉子 99 用例 ＋ 旧钉回归 141 ＋ S4 7 passed ＋ 全量 **1391 passed / 0 failed**；动态复验待 T5 首跑 | `docs/security/m4-closure-preaudit.md` |
| **M5（建议）** | **全批次 ✅ ／ 台账零 ⏳ ／ 挂账全部有主 ／ 门禁全绿** | 本稿（派单给定） |

### 3.2 四道门清单（收官轮逐项打勾）

| 门 | 判据 | 当前实测（`76dd14a`） | 状态 |
|---|---|---|---|
| **G1 台账** | §5.4 零 `⏳` ＋ §5.3 M4 行零待收编 | 29/29 行 `✅`；M4-C4 行「断言组本轮待收编」**已收编**（C8 报备后 main 已订正） | ✅ **通过** |
| **G2 全量** | `pytest -m "not bench"` 0 failed | 主树报 **2081 passed / 127 skipped**；本树同头 | ✅ **通过** |
| **G3 协议登记** | `versioning.md §7` 有 M5 行 ＋ `v` 与 §3 分类一致 ＋ `gen-protocol --check` EXIT 0 | `gen-protocol --check` **EXIT 0**（kilo K13 / opencode A9 两树独立实测）；**但 §7 零 M5 行、`v` 仍 1.0** | ❌ **不通过**（§2） |
| **G4 挂账有主** | A 类三项全关；B 类六项有主且登记在册 | A1/A2/A3 **均未关**；B1–B6 已全部有主（§1.2） | ❌ **不通过** |

### 3.3 收官轮最小待办（按依赖排序，**均非本域可做**）

---

## 4. T4 分钟级行动单（key 到位 → 出结果）

> 前置：`docs/config/m5-c9-t4-probe-runbook.md`（259 行，§1 前置 / §2 命令 / §4 判据 / §5 失败分支）。
> 本节是**压缩到分钟级**的执行卡，**不替代** runbook；判据细节以 runbook §4 为准。

### 4.1 触发条件（三者齐，缺一不动）

| # | 条件 | 谁给 | 现状 |
|---|---|---|---|
| 1 | 用户完成 Deepseek key 轮换并告知 | 用户 | ❌ `T4_MODEL_API_KEY` 未设 |
| 2 | Claude 给出**执行许可** | Claude | ❌ 未给 |
| 3 | 本树 HEAD 与 main 同步 | cline 自查 | ✅ `76dd14a` 六树同头 |

### 4.2 分钟级步骤

| 步 | 动作 | 预期 | 耗时 |
|---|---|---|---|
| 1 | 设 key（**运行时环境变量，永不落盘**）：`$env:T4_MODEL_API_KEY='<key>'` | 无输出 | 30s |
| 2 | 开第二把锁：`$env:T4_RUN='1'` | 无输出 | 5s |
| 3 | **形态自检**：`uv run pytest sim/tests/test_t4_probes.py -m t4 --collect-only -q` | 末行 **`53 collected`**（≠0、≠全 skip） | 20s |
| 4 | **真跑**：`uv run pytest sim/tests/test_t4_probes.py -m t4 -q` | 52 条；产物落 `t4-results/`（已 gitignore） | **3–8 分钟**（视端点） |
| 5 | **判读**：先形态道（exit≠5、无全 skip、有 `t4-report.json`）→ 再内容道（`hard_red[]` 空） | 见 §4.3 | 2min |
| 6 | **留痕三处**：回执 + 台账 M4-C2 行尾追加现状标注 + `.orca/memory.md` ②节 | 不改历史行 | 5min |
| 7 | **销 key**：`Remove-Item Env:T4_MODEL_API_KEY` | `$env:T4_MODEL_API_KEY` 为空 | 5s |

### 4.3 判据速记（**顺序不可颠倒**，详见 runbook §4）

- **形态道先判**：exit≠5（否则收集 0 用例）／**非全 skip**（三把锁缺任一 ⇒ 全部 skip 且退出码 0 = **假绿**）／`t4-report.json` 存在。
- **内容道后判**：`hard_red[]` 为空 = 真绿；`inconclusive[]` 非空 ⇒ **人工复核，不得当绿**。
- **最可能失败分支**：4xx（key 待轮换）⇒ `llm_http_4xx`，按 runbook §5.1 诊断，不改探针代码。

---

## 5. 本单变更清单与边界

| 文件 | 性质 |
|---|---|
| `docs/config/m5-c10-closure-inventory.md` | **新**：本盘点稿 |
| `docs/README.md` | **+2 行**：§2 文档地图登记 ＋ §5.4.5 台账 M5-C10 行 |
| `.orca/memory.md` | **+1 行**：②节本轮快照 |

**未做（刻意）**

| 项 | 原因 |
|---|---|
| 改 `docs/api/versioning.md` §7 / `sim/api/ws.py` `_PROTOCOL_VERSION` | **kilo 域 / 架构域**；§2.4 只报甲乙两案，**登记动作待 Claude 裁决** |
| 关闭任何 A/B 类挂账 | 派单明令「盘点只读不代改」；挂账 owner 见 §1 各行 |
| 改 `docs/security/`（S8/S10/E 批）、`docs/api/`（K12/K13/R-4） | codex / kilo 域正文 |
| 改 `sim/`、`client/`、`.github/workflows/` | 零代码单；A1/A3 接线分别归 Claude 架构域 |
| 真跑 T4 | 无 key、无执行许可（§4.1）；且 key 纪律要求运行时环境变量 |
| `gen-protocol --check` 实跑 | 根 `node_modules` 缺失（仅 `client/node_modules` 在）；采用 kilo K13 / opencode A9 两树**独立实测 EXIT 0** 的回执为证，并在此标注**未由本树复跑** |

**验证**：本单为纯文档；实测项已在各节标注命令与数字（A6 钉 `5 passed/6 skipped` 亲跑；`⏳` 全仓 13 处逐处核对；`shared/` 4 commit 逐个 `git show --stat` 核）。未跑 pytest 全量（零生产码）。
1. **A1 R-4 施工**（Claude）→ 解锁 A6 钉 6 skip、给 B4/G3 复验清场。
2. **§2.4 甲案登记**（kilo + Claude 拍板）→ G3 转绿。
3. **A2 T4 真跑**（用户给 key → Claude 给许可 → cline 跑，§4 行动单已备）。
4. **A3 W-A2-2 接线**（Claude `sim/npc` 消费权力档）→ S8 复验 4 钉解锁。
5. **收编 `395887a`（A9 批次 D）** —— 注意它会占 `0014`，**批次 E 物化单迁移号须在收编后定**（B3）。
6. 宣告收官时，建议照 M3/M4 体例出一份 `m5-closure-preaudit.md`（安全域 codex）静态预审。

### 2.4 建议（**报 Claude 裁决，本单不改**）

| 案 | 做法 | 代价 | 我的倾向 |
|---|---|---|---|
| **甲** | 收官轮前 kilo 补 §7 一行 `1.1｜M5-K3/K8/K10：WS action 增 fast_forward；HTTP 增 /api/anchors/current 与 GET /{id}；PlanDelta 补封闭 schema（均 minor，旧端静默忽略）`，并把 `ws.py:60` 升 `1.1` | 需同步改 `ws.py` 常量 + 前端 `net/ws.ts`（§1 注明「与前端同步」），**是代码改动** | ✅ **推荐**：一次成本，把 M5 的协议增量正式入账 |
| **乙** | §7 补一行注记「M5 全部为向后兼容增量，按 §3 铁律不升版」，`v` 保持 `1.0` | 零代码；但与 §3 分类表字面冲突（枚举新增被明文列为 minor） | 备选，须 Claude 明写「minor 不触发升版」这条例外 |

> **注**：`openapi.json info.version` 是 OpenAPI 文档版本（现 `1.0.0`），与协议号 `v` 不同轴；`main.py:164` 的 `0.1.0` 是 FastAPI app 版本。三者不要求同值，本单不建议动。
> **边界**：`docs/api/versioning.md` 与 `sim/api/ws.py` 均**不属本域**（前者 kilo 域、后者架构域），本单**只盘点不代改**。

