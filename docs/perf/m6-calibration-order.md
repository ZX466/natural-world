# M6 定标执行单（可执行版）+ 三案 advisory 翻转条件核对
> 性能域（pi），2026-10-04。任务：M6-P1 第 2 件（**零代码文档**；第 1 件 soak 契约阶段 A 已施工，见 `m6-soak-contract-preplan.md` §2 与 commit）。
> 基线：main `48c9944`（= 本树 HEAD，开工前同头确认）。
> 依据：P12 台账 §2（runbook 终版）、P13 预研 §2（触发点重申）、P14 契约预研、裁 36-4（阶段 A 先落）、kilo M6-K1 回执（三条配置面结论）。
> **本档是「派单即用」的执行单**：派单方复制 §3 的命令即可执行，不需回读三案全文。

## 0. 结论速览
| # | 问题 | 结论 |
|---|---|---|
| 1 | 现在能派定标轮吗？ | **不能——门 1 未达**（本单实测：`thresholds.py` 零 `CHAOS/POWER/FIRE` 常量；`sim/world/fire*.py` 不存在；`sim/world/authority/` 不存在；`sim/npc/` 零 `PowerStore` 消费；世界循环无 `daily_reseed_due` 调用方）。门 2（机器）**本单实测 1.629 ≤ 2.0 ✓，但 kilo M6-K1 同轮实测 2.657 ✗** ⇒ **门 2 是瞬态量，必须派单时现测**。§1 |
| 2 | 三案翻转条件有变化吗？ | **无变化**（三案仍是 advisory，翻转条件仍是 P12 §2.3 那 8 行）⇒ 本档只做**核对 + 现状实测**，不新增判据（避免双真相源）。§4 |
| 3 | `MATERIALIZE_LIMIT_MS` 呢？ | **仍 advisory**，三条前置未齐（施工落盘 / 窗口上限 `W` 归架构裁 / 测真实触发路径）；**`W` 未定 ⇒ 数值不可先写死**（W=1000→14.8ms vs 10 日 1.728M 事件→1.28s，差 2 量级）。§5 |
| 4 | 派单方最容易踩的坑？ | **两条配置纪律**（kilo M6-K1 已提，本单采纳并落到命令）：①**跑前先跑探针并把 `throttle_ratio` 写进回执**（门 2 就是为此设的「步骤 0」）；②验证 CI 断言面**须带 `PI_THROTTLE_SELFCHECK=0`**，否则会把 soak 的 skip 误读成绿（或把降频误读成红）。§3.0 |

---

## 1. 两条硬门（缺一不派）与**本单实测**状态
| 门 | 内容 | 本单实测（2026-10-04，main `48c9944`） | 判定 |
|---|---|---|---|
| **门 1（内容）** | 批次 C 权力核心接线落 main **且** 批次 D 火灾机制面落盘 | `thresholds.py` 三案常量**零命中**；`sim/world/fire*.py` **不存在**；`sim/world/authority/` **不存在**；`sim/npc/` 零 `PowerStore`；世界循环无 `daily_reseed_due` 调用方 | ❌ **未达** |
| **门 2（机器）** | `throttle_probe` 比值 ≤ 2.0（**派单时现测**） | 本单实测 `{"throttle_ratio": 1.629, "throttled": false}` ⇒ 达；**同轮 kilo M6-K1 实测 2.657 ⇒ 未达** | ⚠ **瞬态**：本单 ✓、kilo ✗ ⇒ **必须现测，不得引用他人读数** |
⇒ **当前不派定标轮**（门 1 未达）；门 1 达标后按 §3 执行，**先跑 §3.0 步骤 0**。

---

## 2. 阶段 A 施工记录（第 1 件，**已落**）
- **改动**：`sim/tests/bench/soak.py`（`SoakResult` 增 `entity_ids_start/end` 快照 + `run_soak` 两处记录）；`sim/tests/bench/test_bench_soak.py`（新增契约常量 `SOAK_ENTITY_LOSS_PER_GAME_DAY = 0`、`_entity_loss_bound()`、共用判据 `_assert_entity_stable()`；两处断言改调共用判据；**结构判据前置到降频探针门之前**；新增契约钉 `test_soak_entity_loss_bound_is_zero_in_phase_a`）。
- **语义**：阶段 A 值=0 ⇒ `end <= start` **且** `start - end <= 0` ⇒ 与旧 `end == start` **等价**；另加 id 集合判据（③）与映射一致判据（④，L1 两测传 `profile_ids`）。
- **验证**：变异测试实证四侧判据**非空转**（净增/净减/换 id/映射分叉各判红，正常态不红）；`test_bench_soak.py` **12 passed / 1 skipped**（含 30k 两测真跑，探针 1.629 未降频）；`test_m5_soak_entity_count.py` **12 passed**（**含一处追改**，见 §6）；not-bench **2231 passed / 120 skipped / 0 failed**；collect-only **2421** = not-bench `2351 + 70`（恒等式 ✓）。
- **⚠ 一处如实说明**：「结构判据前置到门之前」在本仓**当前调用图下是防御性**的——`_assert_no_runaway` 的三个调用方（`:296`/`:357`/`:397`）与其 fixture（`:280`）都**在跑 soak 前**已调 `_skip_if_throttled()` ⇒ 降频夜这三条整段 skip，结构判据仍不会执行。**真正的每提交结构覆盖来自 `_assert_smoke`（无门，`:217`/`:416`）**。⇒ 若要让 nightly 长跑的结构面也免于降频门，需要「短结构冒烟」（另单），本单不擅自扩大范围。

---

## 3. 执行单（门 1 达标后按此执行）

### 3.0 步骤 0（**必做**，两条配置纪律）
```bash
# ① 探针（门 2）：比值必须 ≤ 2.0，且把结果原样写进回执
uv run python -m sim.tests.bench.throttle_probe
#   → 期望 {"throttle_ratio": ≤2.0, "throttled": false}
#   → >2.0 ⇒ 停止（跑了也不算数；绝对阈值必假红，P6 仲裁）

# ② 验证 CI 断言面时**必须**关掉降频自检，否则 soak 的 skip 会伪装成「通过」
PI_THROTTLE_SELFCHECK=0 uv run pytest -q -m "not bench"
#   → 本机降频波动下，带门跑会 skip soak 三测（P11 判例：passed 少 3、skipped 多 3）
#   → 关掉后 soak 结构面/CI 冒烟一律真跑（CI 冒烟本就无门）

# ③ 记录 HEAD（不同档位/不同代不混基线）
git -C <worktree> rev-parse --short HEAD
```

### 3.1 CHAOS（触发：批次 A 收口合入 = `EntropyMixer.mix` 有生产调用方 + 消费点落地）
| 项 | 内容 |
|---|---|
| 待测 | 每 tick 聚合抽签成本（`chaotic()`/`chaotic_at()` 实测 9.3µs/次 × 实际次数） |
| 命令 | `uv run pytest -m bench -k "rng"` + 新钉（见下） |
| 断言映射 | 聚合抽签 ≤ **0.05ms**；**总行兜底 `RNG_TICK_LIMIT_MS=0.10`**（混沌并入 RNG/熵行，不新造轴）；RNG 常规 draws 实测 >0.045ms ⇒ **收缩混沌份额，不放开总行** |
| 新增钉 | `test_bench_rng.py` 扩一行「混沌聚合抽签」断言（同文件既有 `RNG_TICK_LIMIT_MS`） |
| 接法红线（非数字） | 扰动只作用于 `find()` 输出；**禁进 `PathCache` 键 / 禁喂 A\***（账一-a 9.3µs vs 账一-b 494–647µs = **53–70x**）⇒ 白盒钉 |
| 契约常量 | `CHAOS_EMOTION_REGRESS_INTERVAL_TICKS=60`（区间推进，禁每 tick 每 NPC；N=1 时 0.465ms = RNG 上限 4.65x） |
| 收口 | 实测中位 × 1.7（裁 13 先例）；阈值落 `thresholds.py` + `budget.md` RNG/熵行注释 |

### 3.2 POWER（触发：批次 C 接线合入 = `PowerStore` → utility 权重传导）
| 项 | 内容 |
|---|---|
| 待测 | 权力列增量 + **动作分布漂移**（flip 率与**熵**） |
| 命令 | `uv run pytest -m bench -k "l1"` + 决策层新钉 |
| 断言映射 | `POWER_MAX_BIAS ≤ 0.2` 使 **flip ≤ 0.25**；**动作分布熵不得坍缩**（基线 2.52；0.2 档应停 ≥2.4；1.0 档越界样本 1.80）⇒ **与 codex S10 §5.3 红线 C 共用同一条断言，不另立第二条** |
| 红线行 | **并入 `L1_UTILITY_TICK_LIMIT_MS=6.0`，不新建 `POWER_TICK_LIMIT_MS`**（裁 32 待落项已记「采 pi 建议」）；权力列实测 +3.05µs/50 人（对照 `tick_vectorized(50)` 18.1µs） |
| 接法红线（非数字） | 权力只作 utility **额外列**；**禁逐人 `dataclasses.replace`（81µs）/ 逐人 `chaotic_at`（521µs）** |
| 契约常量 | `POWER_REGRESS_INTERVAL_TICKS=60` |
| 收口 | 同 3.1；间接账（flip 点亮冷 A*/检索：P=50 全 move = 26.4ms 破整 tick）只登记为**接法红线**，不设数字行 |

### 3.3 FIRE（触发：批次 D 机制面落盘 = `sim/world/fire*.py` 存在，S9 D-1 白盒扫自动生效）
| 项 | 内容 |
|---|---|
| 待测 | N=2 语义钉（**不需机器**）+ O(G) 形态 + 烧毁→重算摊还 |
| 命令 | `uv run pytest -q sim/tests/bench/test_bench_fire.py`（新建） |
| 断言映射 | ① **`FIRE_AGGREGATE_EVENT_N_PER_10TICK=2`**：同因（`parent_seq` 指同一 `fire.ignited`）连续 10 tick 聚合 damage >2 即红；② 蔓延步成本随 G **线性**（G=1024 合规 174.5µs vs 成对扫描 **39.1ms = 224x**）；③ 烧毁重算按帧摊还（实测 K=20 = 17.2ms 破整 tick；提案 `FIRE_REPATH_BUDGET_PER_FRAME=100`，复用坍塌按帧手法） |
| 红线行 | **不新建 `FIRE_TICK_LIMIT_MS`**，直接账并入既有 `APPLY_P99_LIMIT_MS=0.04` + `test_apply_50_events_batch`（`thresholds.py:175` 已注「走既有 apply 通路」） |
| 契约常量 | `FIRE_SPREAD_INTERVAL_TICKS=60` |
| 可先落项 | **N=2 语义钉**（不依赖接线/机器）——门 1 不必等，**只要裁 34 采认 N=2 即可落** |

### 3.4 翻转操作（五步，**顺序不可换**）
```
1. 门 1 满足（接线/机制面已进 main）；
2. 步骤 0 探针 ≤ 2.0（现测）；
3. 跑 -m bench 取实测中位，×1.7 得收口值；**收口值 ≠ 提案值 ⇒ 报 Claude 裁（不自行放宽）**；
4. thresholds.py 追加常量 + 注释（依据指针三件套：预算案 § + 裁决号 + 实测日期/比值）；
   同步 budget.md 对应批行；体例照 M4-P2 段（thresholds.py:155-180）；
5. `_record_proposal` → `assert_median_threshold`（观察态转硬断言），复跑 bench 全绿 + 双推。
```

---

## 4. 三案 advisory 翻转条件核对表（本单**实测**现状）
| 案 | 提案常量 | 进 `thresholds.py`？ | 门 1 前置 | 翻转条件（= P12 §2.3，**无变化**） | 当前状态 |
|---|---|---|---|---|---|
| CHAOS | `CHAOS_TICK_LIMIT_MS=0.05`（并入 RNG/熵行，兜底 0.10）+ `CHAOS_EMOTION_REGRESS_INTERVAL_TICKS=60` | ❌ **零命中**（实测 grep） | 批次 A 收口（inject 生产调用方 + 消费点） | 接线合入 → 探针 ≤2.0 → 实测中位 ×1.7 → 落行 | **advisory** |
| POWER | `POWER_MAX_BIAS ≤ 0.2`（flip ≤0.25 + 熵不坍）+ `POWER_REGRESS_INTERVAL_TICKS=60` | ❌ **零命中** | 批次 C 接线（`PowerStore`→utility） | 同上；**熵/flip 断言与 codex S10 §5.3 共用一条** | **advisory**（裁 32 待落） |
| FIRE | `FIRE_AGGREGATE_EVENT_N_PER_10TICK=2` + `FIRE_REPATH_BUDGET_PER_FRAME=100` + `FIRE_SPREAD_INTERVAL_TICKS=60` | ❌ **零命中** | 批次 D 机制面（`fire*.py`） | **N=2 语义钉可先落**（不依赖机器/接线）；摊还/区间常量待机制面 + 定标 | **advisory**（N=2 可先落） |
| （M5 唯一已入库） | `FAST_FORWARD_FRAME_LIMIT_MS=0.90` / `..._REQUEST_DURATION_LIMIT_S=42.0` | ✅（P3/P5 共担） | — | — | **硬断言** |
> 核对结论：**三案翻转条件与 P12 §2.3 逐条一致，无新增/无删减** ⇒ 本单只补「现状实测」列，**不新增判据**（防双真相源）。

---

## 5. `MATERIALIZE_LIMIT_MS = 50.0` 现状（三条前置）
| 前置 | 现状 |
|---|---|
| ① 批次 E 施工落盘（`anchor_packages` + 读档函数） | ❌ 未落（迁移号**勿先占 0015**，待 A9 后实际 head 定——cline C10 B3） |
| ② **窗口上限 `W` 归架构域裁** | ❌ 未裁 ⇒ **数值不可先写死**（W=1000→重放 14.8ms vs 10 日 1.728M 事件→**1.28s**，差 2 量级） |
| ③ 测**真实触发路径**（经 API/WS 读档入口，非内部折叠） | ❌ 无入口可测 |
⇒ **保持 advisory**；档别已定 = **一次性操作档**（比照 `SNAPSHOT_LIMIT_MS=500.0`），**绝不进 tick 预算**；收口 = 三条齐 + 探针 ≤2.0 + 实测 ×1.7（**不预支 50.0**）。

---

## 6. ⚠ 本单的一处**跨域追改**（如实报备）
- **现象**：施工阶段 A 后，`sim/tests/test_m5_soak_entity_count.py::TestBenchAssertionShape::test_both_no_runaway_and_smoke_assert_equality`（**A12/opencode 域**）判红——它断言旧形态 `assert result.entity_count_end == result.entity_count_start` 在 bench 文件里**恰出现 2 次**（`assert 0 == 2` 实测）。
- **性质**：**非回归，是 A12 钉的「前提」被阶段 A 按设计取代**（该钉本就是为 P14 派单背景而钉的绊线）。**这正是 P14 §3 预警的「双真相源」在跨域面上的实例。**
- **处置（最小追改，保留原意）**：该钉改为 `test_both_sites_use_structural_entity_guard`——断言 ①旧等式形态 **0 次**（已移入共用判据）②共用判据在 `_assert_no_runaway`/`_assert_smoke` 各 1 次（共 2 次）；docstring 记录过渡、指向契约预研 §2，并写明**阶段 A 不预设死亡**（值=0 ⇒ 与旧断言等价 ⇒ 与同文件「今天无死亡 kind」钉仍相容）。
- **请转**：**该文件属 opencode 域**，本域只做「使门禁转绿的最小追改」；**若 opencode/Claude 有更合适的钉形态，请直接覆盖本追改**（本域无异议）。
- **验证**：该文件 **12 passed**（改前 11 passed / 1 failed）。

---

## 7. 留痕（2026-10-04，本机）
| 动作 | 结果 |
|---|---|
| `grep -cE "CHAOS\|POWER\|FIRE_\|MAX_BIAS\|REGRESS" sim/tests/bench/thresholds.py` | **0** ⇒ 三案均未入库（§4 依据） |
| `ls sim/world/fire*.py` / `ls sim/world/authority/` / `grep -rl PowerStore sim/npc/` | 均**不存在/零命中** ⇒ 门 1 未达 |
| `grep -cE "death\|dead\|despawn" sim/core/events.py` | **0** ⇒ 生命落点仍无载体 |
| `uv run python -m sim.tests.bench.throttle_probe` | `{"throttle_ratio": 1.629, "throttled": false}` ⇒ 门 2 **本单达**（瞬态） |
| `uv run pytest -q sim/tests/bench/test_bench_soak.py` | **12 passed / 1 skipped**（skip = 7 日完整跑需 `PI_M2_FULL_SOAK=1`） |
| `uv run pytest -q sim/tests/test_m5_soak_entity_count.py` | **12 passed** |
| `uv run pytest -q -m "not bench"` | **2231 passed / 120 skipped / 70 deselected / 0 failed** |
| `--collect-only`（两口径） | 全量 **2421** = not-bench `2351 + 70` ✓（恒等式） |
| `uv run ruff check .` / `uv run pyright .` | All checks passed / 0 errors |
> 计数对账：派单板「main `48c9944` = 2296 passed / 123 skipped」= 2419；本单实测 **2421**（+2，其中 **+1 = 本单新增契约钉**，另 +1 未追——**非本单引入**，登记不猜）。
