# M5 收官预检终版（G2/G4 + 判据索引）

> 维护：cline（依赖/配置/文档域）｜基线：**main `2bd2bff`**（六树同头）｜单号：M5-C13（只读预检，零代码零 yml）
> 承接：C11（预检首版）＋ C10（收官盘点）＋ C12（T4 checklist ＋ 判机型甲案）。
> **性质：只读预检**——跑测试只跑不改、**不代改他人域**（G1 台账/G3 协议登记均**不归本单**）。
> **本文 §4 是收官判门索引表**：Claude 判门时**逐条引用** §4 的证据出处即可，不必回溯全过程。

---

## 0. 结论速览

| 门 | 结论 | 一句话 |
|---|---|---|
| **G2 全量** | ✅ **可判过** | not-bench **2213 passed / 120 skipped / 0 failed**；bench **67 passed / 3 skipped / 0 failed**；ruff/pyright 0。**skip 分型与 C11 逐条一致（120 = 120，五型零变化）**；bench 多的 2 skip 是**本机负载触发的设计内自跳过**，非回归 |
| **G4 挂账有主** | ⚠️ **A1 已关**；A2/A3 按建议口径 | **真阻断已从 3 降到 1.5**：A1 ✅／A2 外部 key（主树已明写「不阻收官」）／A3 关闭条件已明确且在 Claude 本域施工中 |
| **判机型巡检** | ✅ **首跑成功**（零 yml 零凭据） | 最新 nightly 机型 **AMD EPYC 7763 64-Core Processor＝与 EPYC 基线一致**；**Xeon 未命中**；并**实测到匿名配额按小时重置** |
| **P5 销账** | ✅ 按 codex S12 裁定销账（**附口径边界**） | 销的是「零载体」条目；**复核：P5 探针 7 例已备、生产载体仍未实现**（措辞落地即可跑） |

---

## 1. G2 复跑（对照 C11 基线）

### 1.1 两口径总量

| 口径 | C11 基线（`04e4220`） | **C13 终版（`2bd2bff`）** | 变化 |
|---|---|---|---|
| `pytest -m "not bench"` passed | 2149 | **2213** | **+64** |
| 同上 skipped | 120 | **120** | **0** |
| 同上 failed | 0 | **0** | 0 |
| 同上 deselected | 70 | 70 | 0 |
| 同上耗时 | 142.18s | 158.66s | +16s |
| `pytest -m bench` passed | 69 | **67** | **−2** |
| 同上 skipped | 1 | **3** | **+2** |
| 同上 failed | 0 | **0** | 0 |
| 同上 deselected | 2269 | 2333 | +64 |
| `ruff check` | `All checks passed` | `All checks passed` | — |
| `pyright` | `0 errors` | `0 errors` | — |

> **口径对账提示**：主树留言板记 `2278 passed / 125 skipped`，与本单 not-bench 的 `2213 / 120` **不同基准**（deselected 与是否含 bench 的口径差异）。**判门请以本单命令＋数字为准**（`uv run pytest -m "not bench" -q`），或由 Claude 指定统一基准。

### 1.2 not-bench skip 分型——**逐条对照 C11，五型零变化**

| 型 | 文件 | C11 | **C13** | 变化 | 收官要求 |
|---|---|---|---|---|---|
| **T4 探针（三把锁未开）** | `test_t4_probes.py` | 53 | **53** | **0** | 须 0（＝A2） |
| **T3 live-fire 语料** | `test_t3_live_fire.py` | 55（8＋47） | **55（8＋47）** | **0** | 可留（语料面） |
| **T5 golden 全量** | `test_golden_full.py` | 10 | **10** | **0** | 可留（§16 不进每提交 CI） |
| **T5 golden 冒烟** | `test_golden_smoke.py` | 1 | **1** | **0** | 同上 |
| **fire 机制面白盒锁** | `test_m5_fire_state.py` | 1 | **1** | **0** | 随 `sim/world/fire*.py` 落盘自动解锁 |
| **A6 六锁钉** | `test_m5_anchors_branch_source.py` | 0 | **0** | **0** | 已达标 |
| **合计** | | **120** | **120** | **0** | — |

**关键读法**：**+64 passed 全部来自真实新增用例，没有任何一例由「skip 转绿」凑来** ⇒ 两轮 skip 结构完全稳定，性能/语料面无意外漂移。

### 1.3 bench skip 分型——**本轮唯一变化在此**

| 型 | C11 | **C13** | 变化 |
|---|---|---|---|
| 完整 7 日 soak（需 `PI_M2_FULL_SOAK=1`） | 1 | **1** | 0 |
| **soak 降频自检**（`test_bench_soak.py:200`） | **0** | **2** | **＋2 ← 本轮唯一变化** |

**判定：非回归，是设计内自跳过。** 证据三则：
1. 触发条件＝**本机持续负载降频**：自旋比值 **2.197 / 2.345 > 2.0**（两次采样，短冲程 15.085→33.143ms、14.739→34.569ms）。
2. 代码即设计：`test_bench_soak.py:192` `_skip_if_throttled()` —— docstring 明写「本机持续降频 ⇒ skip（**M5-P7 接管 `throttle_probe` 的信号**）…`PI_THROTTLE_SELFCHECK=0` 可显式关闭」，命中即 `pytest.skip`。
3. skip 文案自带处置口径：「**漂移比判据不受影响**…稍候重跑，或直看 CI」。
⇒ 与本仓既有「负载抖动实证」（第七轮）＋ 裁 1 advisory 口径同族。**判门建议**：按「设计内自跳过」计入，**空闲时重跑可回 69/1**；不宜判为回归。

---

## 2. G4 挂账终表（C10 九项 → 终版）

### 2.1 A 类阻断项

| # | 项 | 终态 | **证据（可复核）** | 关闭轮次 |
|---|---|---|---|---|
| **A1** | R-4 施工（`anchors.py` 接 `branches.is_current`） | ✅ **已关** | main `04e4220`；`_current_branch_id_or_400()`（`anchors.py:264`）＋ `SELECT id FROM branches WHERE is_current = 1 LIMIT 1`（`:276`），原 `'main'` 字面量只剩**禁止性注释**（`:267`/`:376`）；**A6 钉 `13 passed / 0 skipped`**（C10 时 `5/6`） | 已关 |
| **A2** | T4 真跑 52 条 | ⏸ **仍开（外部依赖）** | env 实测 `T4_MODEL_API_KEY`/`T4_RUN` 均未设；skip 分型确认 **53 条仍 skip**。**主树硬边界段已明写「用户待办：轮换 Deepseek key（T4 真跑；**不阻收官**）」** ⇒ **建议按「有主＋执行单零准备就绪」计条件通过**；执行单＝`m5-t4-final-check.md`（40 行单页，**key 一到即可跑**） | 收官轮（条件通过）／M6（实跑） |
| **A3** | S8 复验 W-A2-2（权力档须被决策层消费） | 🔧 **关闭条件已明确，在 Claude 本域施工中** | **关闭判据（三条，可直接照此核）**：① `sim/world/authority/` 出现且有机制实现文件；② 权力档被 **utility/意愿管线**消费（非仅存储）；③ codex **W-A2-2** 钉转绿（同输入换档 ⇒ willingness band 必须变）。**现状实测**：`sim/world/` 下**仅 `__pycache__`**；`power_level`/`NpcPower`/`PowerStore` 全仓非测试命中＝`models.py`(7)、`power_store.py`(14)、`0013_power_state.py`(5)、`fork.py`/`outbound_guard.py`/`fire_store.py`(各 1) ⇒ **全是存储·迁移·边界·出站面，零决策层消费点**。**主树本域施工第 2 项即「批次 C 接线（PowerStore→utility ＋ hooks 四步注入＝A3 关闭＋W-A 解除）」** | Claude 本域施工合入后 |

### 2.2 B 类项

| # | 项 | 终态 | 证据 |
|---|---|---|---|
| **B1** | P11 / W-D3 N 值 | ✅ 已关 | `m5-fire-budget.md`：**N=2 采认**＋定标机依据＋**N-F 耦合 `2F≤100⇒F≤50`**（F 更大须与坍塌共用摊还队列，不得调大 N） |
| **B2 / P5** | 措辞生成载体 | ✅ **按 codex S12 裁定销账（附口径）** | codex S12：「全仓零载体」挂账**已销账作废**，M6 触发点**几乎必然是物化诊断面的玩家可见文案**。**我复核**：① 物化诊断面**已落**（`fork_orchestration.py:84` `AnchorLoadUnavailable` ＋ `reason` 六码 ＋ A11 三套测试 `test_m5_materialization_{api,orchestration,package}.py`）⇒ 销账依据成立；② **但生产码仍无「因果未知不确定措辞」载体**（全仓非测试仅 `narrate.py`/`language.py` 等既有叙述管线）；③ **P5 探针已备**（`test_t4_probes.py:196` `_HEDGE_RE` ＋ P5 `soft_codes`，含 `test_report_written` 外 7 例相关断言）⇒ **措辞落地即可直接跑，无需改语料**。**⇒ 销账的是「零载体」条目，不是「P5 已实现」** |
| **B3** | 批次 E 物化单 | ✅ 已关 | `70ceaa7`：`anchor_package.py` ＋ 三套测试 |
| **B4** | R-4 复验 G1/G2/G3 | ✅ G1/G3 已关／🔧 G2 **在途** | K14：G1 按 R-4.1-S 回 `400+/errors/world-not-ready`，detail 写明「歧义不可能——部分唯一索引保证至多一个当前」⇒ **契约未破**；G3 opencode 改双态钉自解。**G2（钉 2 anchor-fork 落父＋另两种 0 行情形）由 kilo M5-K16 在途补钉** |
| **B5** | CHAOS / POWER 定标轮 | 🔧 在途 | pi **M5-P14**（soak 契约改法：只减不增＋有界＋BOUND 档位）＋ opencode **M5-A12**（soak 计数数据面核实）**本波在途**；P12/P13 性能复核已交（K13/P13 案） |
| **B6** | R-5③ / E-13 物化基准点判据 | 🔧 在途 | codex **M5-S13**（M6-P0 物化读档安规钉预研，真缺口三条 M-1/M-2/M-3）＋ kilo **M5-K16**（`load_outcomes` 死账本审计）**本波在途**；`fires` 已登记可重放族 ⇒「包不为火扩格式」成立 |

### 2.3 终版汇总

**真阻断只剩 A3 一项**（且在 Claude 本域施工中）；A2 为外部 key 依赖、主树已声明不阻收官；B 类六项**全部有主，其中四项本波在途施工**（K16/S13/P14/A12）。

---

## 3. 判机型巡检·首跑（零 yml 零凭据，承 C12 甲案）
---

## 4. 收官判据索引表（**判门时逐条引用本表即可**）

**用法**：每行＝一条判据 ＋ **证据出处**（可直接打开核对）＋ 终态。标「**本单亲测**」者为 cline 在 `2bd2bff` 实跑/实读所得。

### G1 台账（**不归本单**，Claude 自判）

| 判据 | 证据出处 | 终态 |
|---|---|---|
| §5.4 台账零 `⏳` | `docs/README.md` §5.4（29 行状态列） | 待 Claude 核 |
| C8 分节整理已落地 | `docs/README.md` §5.4.1–5.4.6 六组 | ✅ 已落地 |

### G2 全量（**本单亲测**）

| 判据 | 证据出处（命令／行号） | 结果 |
|---|---|---|
| CI 口径 0 failed | `uv run pytest -m "not bench" -q` @`2bd2bff` | ✅ **2213 passed / 120 skipped / 70 deselected / 0 failed**（158.66s） |
| bench 口径 0 failed | `uv run pytest -m bench -q` @`2bd2bff` | ✅ **67 passed / 3 skipped / 2333 deselected / 0 failed**（181.27s） |
| bench −2/+2 非回归 | `sim/tests/bench/test_bench_soak.py:192` `_skip_if_throttled()`（P7 `throttle_probe`，`PI_THROTTLE_SELFCHECK=0` 可关）；skip 文案自带「漂移比判据不受影响」 | ✅ **设计内自跳过**（自旋比 2.197/2.345 > 2.0，本机负载） |
| skip 分型稳定 | 本稿 §1.2（五型逐条对照 C11，合计 120 = 120） | ✅ **零变化**；+64 passed 全来自新用例 |
| lint / type | `uv run ruff check`／`uv run pyright` | ✅ `All checks passed`／`0 errors` |
| 协议生成物同步 | `gen-protocol --check` | ⚠️ **本树未复跑**（根 `node_modules` 缺失）；采 kilo K14 主树回执 **EXIT 0**；P13 案为**零 yml**不动物理快照 |

### G3 协议登记（**不归本单**，但状态已可核）

| 判据 | 证据出处 | 终态 |
|---|---|---|
| §7 有 M5 登记行 ＋ `_PROTOCOL_VERSION` 升 1.1 | kilo **K14**（`0fe7170`）：§7 三行 minor 登记 ＋ `ws.py:60` 1.0→1.1 ＋ 前端 `net/ws.ts` 同步 ＋ 8 例钉 `test_protocol_version.py` | ✅ **已执行**；主树记「协议版本 1.1」 |

### G4 挂账有主（**本单实测**）

| 判据 | 证据出处 | 终态 |
|---|---|---|
| A1 R-4 施工已关 ＋ **A6 skip 归零** | `anchors.py:264/:276/:267/:376`；A6 钉 `13 passed / 0 skipped` | ✅ |
| A2 T4 有主 ＋ 执行单就绪 | `docs/config/m5-t4-final-check.md`（40 行单页）；主树硬边界段「**不阻收官**」 | ⏸ **建议条件通过** |
| A3 关闭条件 | `sim/world/` 仅 `__pycache__`；power 命中仅存储/迁移/边界/出站面；Claude 本域施工第 2 项＝批次 C 接线 | 🔧 **真阻断·在途**；关闭判据见 §2.1 三条 |
| B1/B3 已关 | `m5-fire-budget.md`（N=2＋`2F≤100⇒F≤50`）；`70ceaa7` | ✅ |
| B2/P5 销账 | codex S12 裁定；`fork_orchestration.py:84` 诊断面已落；`test_t4_probes.py:196` P5 探针已备 | ✅ **附口径**（§2.2） |
| B4/B5/B6 有主在途 | K16（G2 补钉＋死账本审计）／P14＋A12（soak）／S13（M6-P0 安规钉） | 🔧 本波在途 |

### 判机型（**本单亲测首跑**）

| 判据 | 证据出处 | 终态 |
|---|---|---|
| 零凭据可判机型 | `GET /check-runs/{id}/annotations`（**P12 缺的就是这一跳**） | ✅ **首跑成功**，3 次 GET |
| 机型与基线一致 | run `37067388197` → cr `111038495916` → `notice 机型一致：AMD EPYC 7763 64-Core Processor` | ✅ **Xeon 未命中**，口径截至 10-02 |
| 配额按小时重置 | `rate_limit` core **57/60**（上轮 14/60，reset 20:51→23:23）；代理出口曾 `0/60` ⇒ 403 | ✅ 实测；**跑法必须直连** |

---

## 5. 本单变更清单与边界

| 文件 | 性质 |
|---|---|
| `docs/config/m5-c13-closure-precheck-final.md` | **新**：本终版预检稿 |
| `.orca/memory.md` | **+1 行**：②节本轮快照 |

**未做（刻意）**：改 `.github/workflows/`（**零 yml**）／改 `docs/perf/`、`docs/security/`、`docs/api/`、`docs/data/`（**他人域，只引用**）／改 `docs/README.md`（G1 归 Claude）／改 `sim/`、`client/`（跑测试只跑不改）／判 G1·G3（**派单明令不归本单**）／代关任何挂账。

**本单亲跑的门禁**：`pytest -m "not bench"` **2213/120/0**、`pytest -m bench` **67/3/0**、A6 钉 **13/0**、`ruff` **pass**、`pyright` **0 errors**、判机型巡检 **3 次 GET**（**零写请求·零凭据·零 gh**）。

**环境坑（复用 C11 记录）**：pytest 日志经 `cmd.exe` 重定向按**系统代码页 GBK/936** 解码（读 skip 原因须 `GetEncoding(936)`）；运行中读日志用 `File.Open`＋`FileShare.ReadWrite`；全量 142s+ **超工具 30s 上限** ⇒ 须 `Start-Process` 后台跑＋分次轮询。

| 项 | 结果 |
|---|---|
| 最新 nightly run | **`37067388197`（10-02 21:31 UTC，`76dd14a`，success）**——**10-03 的 run 尚未触发**（cron `0 18 * * *` UTC；巡检时本地约 20:30 ＝ 12:30 UTC，未到点）⇒ **台账口径截至 10-02** |
| check-run | `111038495916`（`pytest-benchmark（-m bench）`，success），共 **3 条 annotation** |
| 机型 | **`notice 机型一致：AMD EPYC 7763 64-Core Processor（本次 median 漂移可直接与基线比较）`** ⇒ **与 EPYC 基线一致，Xeon 未命中** |
| 配额 | 直连 core **57/60** remaining（C12 轮为 14/60，reset 20:51 → 本轮 reset **23:23**）⇒ **直接实测到「匿名配额按小时重置」**；且直连与代理出口是**两个不同 IP**（代理侧曾 `remaining=0` ⇒ 403） |
| 调用量 | 本轮 **3 次 GET**（步1 列表／步2 check-runs／步3 annotations）＋ 1 次 `rate_limit` 自查 |

