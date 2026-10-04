# M6-C5 · M6 收官预检骨架 ＋ 定标翻转 CI 侧影响面

> 维护：cline（依赖/配置/文档域）｜基线：**main `9857115`**｜单号：M6-C5（只读核对，**零代码零 yml**）
> **骨架性质**：M6 收官预检的**可增量骨架**——四道门预判 ＋ 挂账清点 ＋ 判据索引，后续轮次在原表上追加行。
> **翻转影响面为只读核对**：只回答「定标翻转后 not-bench 每提交面是否受影响」，**不起派、不改 yml、不改 thresholds**。

---

## 0. 结论速览

| 问 | 答 |
|---|---|
| **定标翻转会否影响 not-bench 每提交 CI 面？** | ✅ **零直接影响**（三条实测）——`thresholds.py` 的导入者**全部**是 bench 标记文件；全部 `assert_*` 调用点**全部**在 `sim/tests/bench/`；唯一未标记的 `test_bench_advisory_gate.py` 用 `monkeypatch` 确定性驱动、不读真实 env |
| **那有没有风险？** | ⚠️ **一个条件性风险**：翻转要新建 `sim/tests/bench/test_bench_fire.py`（**当前不存在**，P12 §2.3 规划 3 钉）。若**漏加 `@pytest.mark.bench`**，其**两条计时钉**（O(G) 形态、烧毁摊还）会**混进每提交面** ⇒ 共享 runner 假红。**N=2 语义钉与机器速度无关**，混进去无害 |
| M6 四道门预判 | G1 ⚠️（**1 处重复行致 1 行假 ⏳**）／G2 待跑（本轮只取收集基线）／G3 ✅（§7 已有 **1.2**）／G4 ⚠️（定标轮可派未派 ＋ 阶段 B 待值） |
| 收集恒等式（当前） | not-bench `2413 + 70 deselected = 2483`；bench `70 + 2413 deselected = 2483` ⇒ **两侧恒等 ✅** |

---

## 1. M6 版四道门预判

| 门 | 判据 | 当前实测（`9857115`） | 预判 |
|---|---|---|---|
| **G1 台账** | §5 台账零 `⏳`、零重复行 | §5 全 **113** 行，非 `✅` 者 **1 行**：`README.md:314` 的 **M5-C10 标「⏳ 待收编」**，而 `README.md:240` **同一单**已标「✅ main（收编 `74f869b`）」⇒ **重复行 ＋ 陈旧状态**。另：**M6-C1/C2/C4 我域三件在台账零登记** | ⚠️ **技术上不通过**（1 行假 `⏳`） |
| **G2 全量** | 双口径 0 failed ＋ 恒等式 | 本轮**只取收集基线**（未跑全量）：not-bench **2413/2483 collected（70 deselected）**；bench **70/2483（2413 deselected）** | ⏳ **待跑** |
| **G3 协议登记** | §7 有当期登记行 ＋ 版本号与 §3 分类一致 | §7 三行：**1.0** 基线／**1.1**（M5 三 minor，K14）／**1.2**（M6-K2 诊断面进快照，**新增端点** `GET /api/anchors/{anchor_id}/materialization`） | ✅ **通过** |
| **G4 挂账有主** | 剩余项有主、无「等外部条件」悬空 | 定标轮**两门均达可派未派**；soak **阶段 B 待生命面给值**；内容面收尾明细**未单独登记**；P9 遗留 `rng_state_persisted=False` 升硬错误**待随定标轮裁** | ⚠️ **待裁**（均有主，无悬空） |

### 1.1 G1 那一行的处置建议（**只报，`docs/README` 归 Claude**）

- **现象**：`M5-C10` 在台账出现**两行**——`README.md:240`（✅）与 `README.md:314`（⏳，位于 §5.4.5「写路径合流与本域配置」内）。同一交付 `088b38d` 被记两次，**后一行状态未随收编更新**。
- **风险**：G1 若按「零 `⏳`」机械核，会因这一行**假红**。
---

## 2. 挂账清点（M6 残余）

| # | 项 | 谁 | 依赖 | 状态 |
|---|---|---|---|---|
| H1 | **定标轮（翻转五步）** | pi ＋ Claude 派单 | 门 1 ✅（`fire.py` ＋ `npc/utility.py` 消费权力档）／门 2 ✅（C4 六笔回落健康簇） | 🟢 **可派未派** |
| H2 | **soak 契约阶段 B** | 生命面给值 ＋ pi | `SOAK_ENTITY_LOSS_PER_GAME_DAY` 按「每游戏日可接受净减上界」给值 | ⏳ 待值（阶段 A 已落且 CI 面绿） |
| H3 | **P9 遗留：`rng_state_persisted=False` 升硬错误** | opencode A2 ＋ pi | 「随定标轮一并裁」（P12 §2.5） | ⏳ 仍是 warning |
| H4 | **M6 内容面收尾** | Claude 域 | `9857115` 自记残余＝「定标机器门 ＋ M6 内容面」 | 🔧 **明细未单独登记（未核实）** |
| H5 | **T4 台账追平** | Claude（G1 域） | `05b8f28` 记「T4 真跑收官 hard_red=0」，README M5-C9 行仍记「未真跑」 | ⏳ 历史行未追改 |
| H6 | **M6-C1/C2/C4 台账登记** | cline 交／Claude 收编 | 我域三件已交，未进台账 | ⏳ **零登记** |

---

## 3. 定标翻转的 CI 侧影响面（**核心，只读核对**）

### 3.1 翻转要做什么（P12 §2.4 五步，顺序不可换）

| 步 | 动作 | 落在哪 |
|---|---|---|
| 1 | 接线/机制面已进 main（skip 自动解除） | — |
| 2 | 步骤 0 探针 `≤2.0` | — |
| 3 | 跑 `-m bench` 取实测中位，按 **×1.7** 得收口值；若 ≠ 提案值 ⇒ 报 Claude 裁 | — |
| 4 | **`thresholds.py` 追加常量 ＋ 注释**（依据三件套）＋ 同步 `docs/perf/budget.md` | `sim/tests/bench/thresholds.py`、`docs/perf/` |
| 5 | **`_record_proposal` → `assert_median_threshold`**（观察态转硬断言），复跑 bench 全绿 ＋ 双推 | **bench 测试文件** |

### 3.2 三条实测证据 ⇒ **not-bench 每提交面零直接影响**

| # | 证据 | 实测结果 |
|---|---|---|
| **E1** | `thresholds.py` 的**导入者** | 全仓扫描（`sim/`＋`client/`＋`tools/`）：命中 **12 个文件，`100%` 在 `sim/tests/bench/`**（apply/clock/fast_forward/l1_utility/perception/retrieval/rng/smell/soak/structure/willingness/chunk_invalidation）⇒ **零个非-bench 导入者** |
| **E2** | `assert_threshold(` / `assert_median_threshold(` 的**调用点** | 全仓调用点**全部**在 `sim/tests/bench/`（`harness.py` 为定义处 ＋ 各 `test_bench_*.py`）⇒ **非-bench 文件零调用**。`sim/tests/conftest.py` **不存在**（唯一 conftest 是 `sim/tests/bench/conftest.py`，只对 bench/ 生效） |
| **E3** | 未标记的 bench 文件 | 14 个 `test_bench_*.py` 中 **13 个有 `@pytest.mark.bench`**；唯一未标记的 **`test_bench_advisory_gate.py`** 用 `monkeypatch` 显式切换 `PI_BENCH_ADVISORY` ⇒ **确定性，不读真实 env、不受翻转影响** |

> **附带确认**：`ci.yml` **零** `PI_BENCH_ADVISORY`（只有 `nightly-bench.yml` 的 `:77`/`:158` 带 `"1"`）。这在今天**是正确配置**——每提交面本就没有阈值断言可断言；翻转后仍然如此，**不需要给 `ci.yml` 补 env**。

### 3.3 ⚠️ 唯一的条件性风险：**待建的 `test_bench_fire.py` 漏标记**

P12 §2.3 规划 FIRE 三条钉，落点 `sim/tests/bench/test_bench_fire.py`——**实测当前不存在**（翻转时才建）。逐条判其能否承受进每提交面：

| 钉 | 性质 | 若漏标 `@pytest.mark.bench` 的后果 |
|---|---|---|
| `test_fire_tick_event_budget`（**N=2**） | **语义钉**：测「同因连续 10 tick >2 即红」的**事件计数** | ✅ **安全**——P12 §2.3 明写「**测的是事件计数，与机器速度无关**」 |
| `test_fire_spread_is_linear`（**O(G)**） | **计时钉**：蔓延步 ≤ O(G) 上界 | ❌ **危险**——共享 runner（4 核、跨厂商池）比定标机慢 ⇒ **假红** |
| `test_fire_burnout_*`（**烧毁摊还**） | **计时钉**：`FIRE_REPATH_BUDGET_PER_FRAME` | ❌ **危险**——同上 |

**⇒ 建议写进翻转验收的前置检查项**：

1. `test_bench_fire.py` **必须**带 `@pytest.mark.bench`（或模块级 `pytestmark`），**与其余 13 个 bench 文件同体例**；
2. 建文件后**先跑一次 `-m "not bench" --collect-only`**，确认 **2413 + 70 = 2483** 的恒等式**未被打破**（若 not-bench 收集数增加 ⇒ 标记漏了，**当场可查**）；
3. 若确需让 N=2 语义钉进每提交面（它机速无关，值得），**建议单独放 bench 外**并**不要与两条计时钉混在同一文件**。

### 3.4 结论

> **定标翻转（advisory → 硬断言）对 not-bench 每提交 CI 面零直接影响**——翻转产物（`thresholds.py` 新常量 ＋ bench 文件内断言）**全部位于 bench 域**，每提交面无任何阈值断言消费者（E1/E2/E3 三重实证）。
> **唯一要盯的是 E3 的例外项**：待建的 `test_bench_fire.py` 若漏标记，会把两条**计时钉**带进每提交面 ⇒ **建议把「标记核对 ＋ 收集恒等式复核」列为翻转验收前置项**（§3.3）。

---

## 4. 收官判据索引（骨架，供后续轮次追加）

| 门 | 判据 | 证据出处 | 终态 |
|---|---|---|---|
| G1 | 台账零 `⏳` ＋ 零重复行 | `docs/README.md` §5（113 行；**`:314` 重复 `⏳`**） | ⚠️ |
| G2 | 双口径 0 failed ＋ 恒等式 | 收集基线 **2483 = 2413+70 = 70+2413**（本轮亲跑 `--collect-only`） | ⏳ 待跑 |
| G3 | §7 有当期登记行 | `versioning.md:63-65`＝**1.0／1.1／1.2** | ✅ |
| G4 | 剩余项有主无悬空 | §2 六项（H1–H6），**均有主** | ⚠️ 待裁 |
| 翻转 | not-bench 面零影响 | §3.2 三条实证（E1/E2/E3） | ✅ |
| 翻转 | 待建 bench 文件标记 | `sim/tests/bench/test_bench_fire.py` **不存在** ⇒ 翻转时核对（§3.3） | ⚠️ **前置项** |

---

## 5. 本单变更清单与边界

| 文件 | 性质 |
|---|---|
| `docs/config/m6-c5-closure-skeleton.md` | **新**：本骨架稿 |
| `.orca/memory.md` | **+1 行**：②节本轮快照 |

**未做（刻意）**：改 `.github/workflows/`（**零 yml**，含**不**给 `ci.yml` 补 `PI_BENCH_ADVISORY`）／改 `sim/`（含**不改** `thresholds.py`、**不建** `test_bench_fire.py`）／改 `docs/README.md`（G1 归 Claude）／起派定标轮（属 pi/Claude）／改 `docs/perf/`（pi 域，只读）。

**本轮亲跑的验证**：两口径 `--collect-only`（恒等式 2483）＋ 三条静态扫描（E1 导入者／E2 调用点／E3 标记状态）＋ README 台账行状态扫描（113 行/1 处非 ✅）＋ `versioning.md §7` 行核对。**未跑全量 pytest**（骨架不重复全量）。
- **建议**：删 `README.md:314`，或将其状态改为 `✅`（**建议删重复行**，保留已更新的 L240）。**属 G1/台账域，我未改。**

