# M5 收官预检 · G2/G4 门执行（docs/config/m5-c11-closure-precheck.md）

> 维护：cline（依赖/配置/文档域）｜基线：main `04e4220`（含 R-4 施工 + 批次 E 物化单）｜单号：M5-C11（只读预检）
> **性质：只读预检**——只跑不测改（跑测试除外）、只读不代改。G1（台账）与 G3（协议登记）**不归本单**。
> **所有权**：`docs/config/m5-c11-closure-precheck.md`（新）＋ 自树 `.orca/memory.md`。
> **数字全部亲跑**，非转述：全量 `pytest` 两口径分列、ruff/pyright 亲跑、skip 逐条读原始 `SKIPPED` 行解码取原因。

---

## 0. 结论速览

| 门 | 判据 | 结论 |
|---|---|---|
| **G2 全量** | CI 口径 0 failed ＋ 三件套 0 | ✅ **通过**——not-bench **2149 passed / 120 skipped / 0 failed**、bench **69 passed / 1 skipped / 0 failed**、ruff `All checks passed`、pyright `0 errors` |
| **G4 挂账有主** | A 类全关；B 类各有主 | ⚠️ **部分**——C10 的 9 项**已关 4 项**（A1、B1、B3 ＋ 销账项确认）、**A2/A3 仍开**，B2/B5/B6 仍开 |

**相较 C10 的关键变化**：C10 列出 3 项 A 类阻断，**A1（R-4 施工）本轮已关**（main `04e4220`）——
亲跑 A6 钉得 **`13 passed / 0 skipped`**（C10 时是 `5 passed / 6 skipped`），**skip 归零达标**（收官门要求的正是 0）。

---

## 1. G2 全量预检

### 1.1 两口径分列（计数对账）

| 口径 | 命令 | 结果 | 耗时 |
|---|---|---|---|
| **CI 口径**（不含 bench） | `uv run pytest -m "not bench" -q` | **2149 passed / 120 skipped / 70 deselected / 0 failed** | 142.18s |
| **bench 口径** | `uv run pytest -m bench -q` | **69 passed / 1 skipped / 2269 deselected / 0 failed** | 264.84s |

> 两口径**均 0 failed / 0 error**。bench 的 1 skip 是 `test_bench_soak.py:331`「完整 7 日跑（604,800 tick）默认跳过，置 `PI_M2_FULL_SOAK=1` 触发」——**设计内默认跳过**，非缺陷。

### 1.2 skip 分型（逐条读原始 `SKIPPED` 行，取 skip 原因）

**合计 120 = 10 + 1 + 1 + 55 + 53**，与 `pytest` 汇总数一致（对账通过）。

| 型 | 文件 | 数 | 原因（原文） | 收官轮要求 |
|---|---|---|---|---|
| **T4 探针（三把锁未开）** | `sim/tests/test_t4_probes.py` | **53** | 「真模型探针未开启：需 `T4_RUN=1` 且 `T4_MODEL_API_KEY` 已设」 | **须 0**（＝A2 真跑） |
| **T3 live-fire 语料** | `sim/tests/test_t3_live_fire.py` | **55** | 8「样本输入无禁词（输出面样本）」＋ 47「变体池无独立安全响应正文」 | 可留（语料面，**非本轮门**） |
| **T5 golden** | `golden/test_golden_full.py` ＋ `test_golden_smoke.py` | **10 + 1** | 「全量默认跳过（§16 T5 每日跑）；置 `PI_T5_FULL=1`」「冒烟默认跳过；置 `PI_GOLDEN_SMOKE=1`」 | 可留（**不进每提交 CI**，设计如此） |
| **fire 机制面白盒锁** | `sim/tests/test_m5_fire_state.py` | **1** | 「机制面文件尚未落盘（`sim/world/fire*.py`）——D-1 白盒扫随其落盘自动生效」 | 可留（随机制面落盘自动解锁） |
| **A6 六锁钉** | `test_m5_anchors_branch_source.py` | **0** ✅ | — | **已达标**（R-4 施工合入后归零，C10 时为 6） |

**收官轮 skip 账**：若 A2 真跑完成 ⇒ 120 → **67**（−53）；其余四型均为设计内默认跳过或随机制落盘自动解锁。

### 1.3 三件套

| 工具 | 结果 | 备注 |
|---|---|---|
| `ruff check` | ✅ `All checks passed!` | 全仓 |
| `pyright` | ✅ `0 errors, 0 warnings, 0 informations` | 全仓 |
| `gen-protocol --check` | ⚠️ **本树未复跑** | 根 `node_modules` 缺失（仅 `client/node_modules` 在）、无根 `package.json` ⇒ **采 K14 主树实测回执：`EXIT 0`（`shared/` 零 diff——版本升不动物理快照）**，已在稿内标注该证据来源 |
---

## 2. G4 挂账终表（C10 九项逐项更新）

### 2.1 A 类阻断项（3 项）——**A1 已关，A2/A3 仍开**

| # | 挂账项 | C10 时状态 | **本轮实测** | 关闭轮次预测 |
|---|---|---|---|---|
| **A1** | **R-4 施工**（`anchors.py` 游标接 `branches.is_current`） | ❌ 未落，`anchors.py:274/:345` 硬编码 `'main'`；A6 钉 `5 passed/6 skipped` | ✅ **已关**（main `04e4220`「R-4 施工落地——anchors 两处接 `branches.is_current` 真源 + `fork.py` 当前行交接」，裁 30-D 兑现）。**证据三则**：① `anchors.py` 新增 `_current_branch_id_or_400()`（L264），SQL 改 `SELECT id FROM branches WHERE is_current = 1 LIMIT 1`（L276），**原 `'main'` 字面量只剩禁止性注释**（L267/L376「禁 `'main'` 兜底」）⇒ 白盒负钉转绿；② L377 `branch_id = _current_branch_id_or_400()` 真源接线；③ **亲跑 A6 钉 `13 passed / 0 skipped`**（C10 时 `5/6`） | **已关**（`04e4220`） |
| **A2** | **T4 真跑 52/53 条** | ❌ key 未到位 | ❌ **仍开**——本轮 env 实测 `T4_MODEL_API_KEY` **未设**、`T4_RUN` **未设**；skip 分型确认 **53 条仍 skip**（§1.2） | **M5 收官轮**，待用户 key ＋ Claude 执行许可（分钟级行动单见 C10 §4） |
| **A3** | **S8 复验 W-A2-2 接线**（权力档须被决策层消费） | ❌ `sim/npc` 未消费权力档 | ❌ **仍开**——亲扫全仓非测试 `.py`：`power_level`/`NpcPower`/`PowerStore` 命中仅 `models.py:25`（模型）、`power_store.py`（存储）、`0013_power_state.py`（迁移）、`fork.py:185`、`outbound_guard.py:39`、`fire_store.py:203`（**均为存储/边界/出站面**）；**`sim/world/` 下无 `authority/` 目录**（仅 `__pycache__`）⇒ **无决策层消费点**，机制面未施工 | **M6 或收官轮**，Claude 域（codex W-A2-2 钉已备） |

### 2.2 B 类项（6 项）——**B1/B3 已关，B2/B4/B5/B6 仍开**

| # | 挂账项 | 谁 | **本轮实测** | 关闭轮次预测 |
|---|---|---|---|---|
| **B1** | **P11 / W-D3 蔓延事件预算 N 值** | pi | ✅ **已关**——`docs/perf/m5-fire-budget.md` 已落 main（commit `74f869b` 收编态）。**N=2 已采认并给出定标机依据**：「同因（`parent_seq` 指向同一 `fire.ignited`）在连续 10 tick 内聚合 damage 事件 **>2 即实现偏差**」；另钉死 **N 与 F 耦合**（`2F ≤ 100 ⇒ F ≤ 50`，F=同时活动火场数；F 更大则与坍塌共用摊还队列，**不得调大 N**）。P11 系**二次重派**后交付（pi 已致歉超期） | **已关** |
| **B2** | **P5 措辞生成载体** | Claude | ❌ **仍开**——全仓非测试代码扫 `def narrate`/`措辞生成`/`hedge`/`probably` 仅命中 `sim/.../narrate.py:18`、`frame.py:52`（**既有叙述管线，非因果未知「应该能行/不好说」载体**）⇒ P5 缺口**三轮未动**，仍待 Claude 域 | M6 |
| **B3** | **批次 E 物化单** | opencode | ✅ **已关**——main `70ceaa7`「批次 E 物化数据面（`anchor_package` 物化器 + fork kind 参数化 + 语料切包）」，新增 `sim/core/persistence/anchor_package.py`（550 行）＋ `test_m5_materialization_package.py`（1548 行）。**C10 提示的迁移号风险已消解**（按实际 head 定号，未与 A9 `0014` 冲突） | **已关**（`70ceaa7`） |
| **B4** | **R-4 复验缺口 G1/G2/G3** | kilo ＋ opencode | ⚠️ **G1/G3 已关，G2 仍开**——K14 实测回执：A6 钉 **13 例全绿、skip 归零**；**G1 通过**（`_current_branch_id_or_400()` 按 R-4.1-S 回 `400 + /errors/world-not-ready`，detail 区分「无当前世界线」并写明「歧义不可能——部分唯一索引保证至多一个当前」⇒ A6 原注释「409/503 都可」已被按契约实现覆盖，**契约未破**）；**G3 由 opencode 自解**（`test_fork_from_current_line_keeps_single_current` 改**双态**，锁信号＝`fork.py` 出现 `is_current`，两态皆绿带反假绿断言）。**G2 未做**：钉 2（anchor-fork 落父）＋另两种 0 行情形（`branches` 空表 / 全 `abandoned`）无钉，属 A6 文件范围**需主树派 CR** | M6（待派 CR） |
| **B5** | **CHAOS / POWER 定标轮** | pi | ❌ **仍开**——P11 预算案已交（含 N=2 与 F 耦合），但**定标机复测轮未见 main 落地**；`docs/perf/m5-p12-*.md`（P12 性能收官台账，commit `b573712`）**不在 main**（实测 NOT-in-main）⇒ 收官台账与定标轮均待收编 | M6 首轮 |
| **B6** | **R-5③ / E-13 物化基准点判据** | codex ＋ opencode | ⚠️ **部分**——`fires` 已登记可重放族（A9）⇒「包不为火扩格式」成立；K14 另出**批次 E 出站面核对单**（物化错误不进 `_TYPE_TITLE` 三论证＋**`load_outcomes` 是死账本**、物化失败无出站通道的真缺口，建议另立施工单）。**E-13 判据本身**（火势物化基准点须先证「快照+重放不能逐位重建」）仍待 codex 落判据 | M6 |
---

### 2.3 C10「可销账 4 项」复核

| 曾挂账项 | C10 判定 | **本轮复核** |
|---|---|---|
| S8 复验单「未出执行版」 | 已关（codex S10 `b104882`） | ✅ 维持已关 |
| K12 出站面零变更「无守卫钉」 | 已关（kilo K13 `02b331d` 15 例） | ✅ 维持已关；K14 另**顺带指出 K12 稿需订正**（建议新增 3 fire kind 含 `fire.spread`，实际落地 2 个，蔓延走 `matter.damage`＋`parent_seq`）⇒ **K12 稿 §1.1/§1.3/§5 待裁 1 待订正**，已请 Claude 指派下一轮 |
| C8 报备 2 项 hash 待订正 | 已关（main `2471850`） | ✅ 维持已关 |
| 批次 D 火灾数据面 | 已交付待收编 | ✅ 已关并**已收编**（A9 `395887a` 入 main，`0014 fires` 占号） |

---

## 3. 收官轮判门建议（**只报，不代判**）

**建议判门口径**：A2（T4）依赖**外部 key**，非团队可单方关闭⇒ 建议按「**有主 + 执行单零准备就绪**」（C10 §4 行动单）计入**条件通过**，并在收官宣告中显式标注「T4 真跑待 key，runbook 已就绪」；A3（W-A2-2 接线）与 B 类各项按 **M6 带入**处理。**是否采此口径请 Claude 裁决**——本单不代判。

---

## 4. 本单变更清单与边界

| 文件 | 性质 |
|---|---|
| `docs/config/m5-c11-closure-precheck.md` | **新**：本预检稿 |
| `.orca/memory.md` | **+1 行**：②节本轮快照 |

**未做（刻意）**

| 项 | 原因 |
|---|---|
| 改 `docs/README.md` | 派单明令「不碰 docs/README」；台账登记与 G1 判门由 Claude 统一处理 |
| 判 G1 / G3 | 派单明令「G3/G1 不归你」 |
| 关闭任何 A2/A3/B 类挂账 | 只读预检；关闭动作归各 owner |
| 跑 `gen-protocol --check` | 根 `node_modules` 缺失、无根 `package.json` ⇒ 采 K14 主树回执（EXIT 0）并**在稿内标注该证据来源与未复跑事实** |
| 真跑 T4 | 无 key、无执行许可（env 实测两把锁均未设）；key 纪律要求运行时环境变量 |
| 改 `sim/`、他人域 docs | 零代码单；跑测试只跑不改 |

**本单亲跑的门禁**

| 门禁 | 结果 |
|---|---|
| `pytest -m "not bench"` | **2149 passed / 120 skipped / 70 deselected / 0 failed**（142.18s） |
| `pytest -m bench` | **69 passed / 1 skipped / 2269 deselected / 0 failed**（264.84s） |
| A6 钉（skip 归零核对） | **13 passed / 0 skipped**（C10 时 `5 passed / 6 skipped`） |
| `ruff check` | `All checks passed!` |
| `pyright` | `0 errors, 0 warnings, 0 informations` |

**证据可复核性**：全量与 bench 均在本树本 commit 亲跑；skip 分型逐条读 pytest 原始 `SKIPPED` 行取原因（**未凭印象归类**）；A1/A3 的代码证据均给出文件＋行号；B4 的 G1/G3 结论采 kilo K14 主树回执并标明出处。

**环境坑（本轮新记）**：pytest 输出经 `cmd.exe` 重定向落盘时按**系统代码页（GBK/936）**解码，直接 `Get-Content -Encoding UTF8` 读会乱码 ⇒ 读 skip 原因须 `[System.Text.Encoding]::GetEncoding(936).GetString(bytes)`；运行中读文件要用 `File.Open`＋`FileShare.ReadWrite`，否则报「正由另一进程使用」。另：`pytest -m "not bench"` 单次 142s **超出工具 30s 单命令上限**，须 `Start-Process` 后台跑＋分次轮询日志。
| 门 | 本轮状态 | 说明 |
|---|---|---|
| G1 台账 | 不归本单 | 由 Claude 判 |
| **G2 全量** | ✅ **可判过** | 两口径 0 failed；ruff/pyright 0；`gen-protocol --check` 采 K14 回执 EXIT 0（本树未复跑，已标注） |
| G3 协议登记 | 不归本单 | **注**：K14 甲案已执行（§7 三行登记＋`_PROTOCOL_VERSION` 1.0→1.1＋前端同步＋8 断言钉 `test_protocol_version.py`），commit `0fe7170` **已交付但尚未入 main**（实测 NOT-in-main）⇒ G3 的收官判据须待其收编后核 |
| **G4 挂账有主** | ⚠️ **部分** | **A1 已关**（真阻断解除）；**A2/A3 仍开**＋B2/B4(G2)/B5/B6 仍开 ⇒ 严格按 C10 判据「A 类三项全关」，**G4 尚未转绿**，但**真阻断已从 3 降到 2** |

**建议判门口径**：A2（T4）依赖**外部 key**，非团队可单方关闭⇒ 建议按「**有主 + 执行单零准备就绪**」（C10 §4 行动单）计入**条件通过**，并在收官宣告中显式标注「T4 真跑待 key，runbook 已就绪」；A3（W-A2-2 接线）与 B 类各项按 **M6 带入**处理。**是否采此口径请 Claude 裁决**——本单不代判。


