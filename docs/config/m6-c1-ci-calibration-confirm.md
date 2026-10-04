# M6-C1 · CI 面确认 ＋ 定标轮探针门确认

> 维护：cline（依赖/配置/文档域）｜基线：**main `48c9944`**｜单号：M6-C1（只读确认，**零代码零 yml**）
> 两件都是**确认**，不是施工：①**soak 契约阶段 A 的 CI 冒烟面**（无 bench 标记·每提交跑）；②**定标轮 runner 探针门**（P13 runbook 门 2）。
> 依据文档（**他人域，只读不改**）：pi **P14** `docs/perf/m6-soak-contract-preplan.md`（211 行）、pi **P13** `docs/perf/m6-perf-preplan.md` §2。

---

## 0. 结论速览

| 问 | 答 |
|---|---|
| soak CI 冒烟面每提交跑吗 | ✅ **是**——`test_bench_soak.py::test_soak_ci_smoke_stability`（`:202`）**无 `bench` 标记**，随 `ci.yml:58` 的 `uv run pytest -m "not bench"` **每提交执行** |
| 该面当前是绿的吗 | ✅ **绿**——以「健康 runner」模拟（`PI_THROTTLE_SELFCHECK=0`）实跑：**`1 passed in 4.56s`** |
| 阶段 A（`BOUND=0`）动 CI 面有风险吗 | ✅ **零风险**——`BOUND=0` ⇒ `end<=start` ∧ `start-end<=0` ⇒ 与原 `==` **完全等价**，只多出方向可读的报错；P14 §4.1 实测支撑 |
| 定标轮探针门（门 2）过了吗 | ❌ **未过**——`uv run python -m sim.tests.bench.throttle_probe` 实测 **`throttle_ratio 2.657 > 2.0`**、`throttled: true` |
| 能派定标轮吗 | ❌ **不能**——P13 §2.1「两条硬门**缺一不派**」，且**门 1 内容面亦未达**（`fire*.py` 缺、`sim/npc` 零 power 消费）⇒ **两条门都没过** |

---

## 1. soak 契约阶段 A —— CI 冒烟面确认

### 1.1 面在哪、每提交是否真跑（**确认**）

| 判据 | 证据 | 结论 |
|---|---|---|
| 冒烟测试本体 | `sim/tests/bench/test_bench_soak.py:202` `test_soak_ci_smoke_stability` | 文件在 `bench/` 目录但**测试函数无 `@pytest.mark.bench`** |
| 冒烟断言面 | 同文件 `:217` → `_assert_smoke(result, label="M2 长跑 CI 冒烟", expected_ticks=_CI_SOAK_TICKS)`；`:150` 定义处注释：**「只验『窗口非空 + 总 tick 到位 + 实体集稳定』」**（旧口径的漂移/稳态/RSS/GC/句柄全量已归 nightly） | 冒烟面**只含实体集稳定**，正是阶段 A 的作用面 |
| 每提交执行 | `.github/workflows/ci.yml:51` step 名「pytest（T1/T2/T3；排除 bench——性能基准进 nightly）」→ **`:58` `uv run pytest -m "not bench"`** | ✅ **每提交跑** |
| marker 纪律 | `pytest.ini`：`bench: …nightly 跑 -m bench，每提交 CI 跑 -m "not bench"` | 与 ci.yml 实际一致 |

### 1.2 当前是否绿（**本机实跑，健康 runner 模拟**）

> ⚠ 本机当前**降频**（见 §2），冒烟测试会被**设计内自跳过** ⇒ 直接跑只得到 skip，**证明不了断言面是绿**。须关掉自检看真实断言。

```
$env:PI_THROTTLE_SELFCHECK='0'
$ uv run pytest sim/tests/bench/test_bench_soak.py::test_soak_ci_smoke_stability -q
1 passed in 4.56s
```
⇒ **CI 冒烟面当前为绿**；**本机默认跑法会 skip**（降频门，`test_bench_soak.py:200`），二者**不矛盾**，判读时勿混。

### 1.3 阶段 A 对 CI 面的影响（**结论：零风险**）

| 项 | 阶段 A（`BOUND = 0`） | 依据 |
|---|---|---|
| 改法 | 两侧界 + 单一函数：`end <= start` **且** `start - end <= BOUND` | P14 §2.1 |
| 阶段 A 值 | `SOAK_ENTITY_LOSS_PER_GAME_DAY: Final[int] = 0`（**代码契约常量**，落 `test_bench_soak.py` 顶部，**非 `thresholds.py`**） | P14 §2.1 代码块 |
| 与原断言关系 | `bound=0` ⇒ 两式合起来**恰为**原 `end == start` ⇒ **语义等价、首跑必绿、零行为变化**（只多方向可读报错） | P14 §2.3 表 |
| 实测支撑 | 运行期零增删 ⇒ `end == start` ⇒ 两界均满足、`new_ids = ∅` | P14 §4.1 |

### 1.4 ⚠ 一条**次序**红线（P14 §5，必须照抄给派单方）

**「生命始终」施工单的前置 = 契约小单已合入**；且生命施工单须**同时**给出 `SOAK_ENTITY_LOSS_PER_GAME_DAY` 的值与依据。
**反向风险（若不按此序）**：机制先落 ⇒ 死亡当晚 `_assert_no_runaway`（nightly 30k／7 日）**与 `_assert_smoke`（每提交 CI）同时红** ⇒ 按 P12 纪律「passed 少先查门/契约再怀疑代码」会被迫排查，且 **CI 面会持续红到契约改完 ⇒ 阻塞所有人**。
⇒ **正确次序：① 契约小单（阶段 A）→ ② 生命机制施工（同 CR 提 BOUND 到阶段 B）→ ③ 定标/收口**。阶段 B **必须与生命机制同 CR**，否则机制先落而死界仍是 0 ⇒ 必红。

---

## 2. 定标轮 runner 探针门确认（P13 runbook 门 2）

### 2.1 探针可跑性（**确认**）

| 判据 | 证据 | 结论 |
|---|---|---|
| 模块存在 | `sim/tests/bench/throttle_probe.py` | ✅ 存在 |
| 命令可跑 | `uv run python -m sim.tests.bench.throttle_probe` | ✅ **本轮实跑成功**，输出单行 JSON |
| 门限 | P13 §2.1 门 2：`throttle_ratio ≤ 2.0` 才派定标；**未达 ⇒ 不跑**（「跑了也不算数，绝对阈值必假红，P6 仲裁」） | 判据明确 |

### 2.2 本轮实测结果（**门 2 未达**）

```json
{"burst_base_ms": 15.536, "sustained_worst_ms": 41.278, "throttle_ratio": 2.657,
 "ratio_limit": 2.0, "throttled": true, "samples": 1244, "iters": 500000}
```

⇒ **`throttle_ratio 2.657 > 2.0` ⇒ `throttled: true` ⇒ 门 2 未过**。
**与 C13 观测同源**：C13 的 bench 全量里 soak 降频自检两次自跳过，自旋比 **2.197 / 2.345**；本轮 **2.657** ⇒ **本机持续降频是跨轮持续态，不是偶发**。

### 2.3 门 1（内容面）一并核——**同样未达**

| 判据 | 实测 | 结论 |
|---|---|---|
| 批次 D 火灾机制面落盘 | `sim/world/fire*.py` → **不存在**；`sim/world/` 下仅 `__pycache__` | ❌ 未达 |
| 批次 C 权力接线（PowerStore→utility） | `sim/npc/*.py` **零 `power` 命中**；`sim/world/authority/` **不存在** | ❌ 未达 |
| 结论 | P13 §2.1「**两条硬门，缺一不派**」 | ❌ **两条都没过 ⇒ 不派 M6-P1** |

> **口径提醒**：`MATERIALIZE_LIMIT_MS = 50.0` 提案按 P13 §2.2 **当前判定仍是 advisory**，收口须三条前置齐 ＋ 本探针 ≤2.0，且按「实测 ×1.7」给值、**不预支 50.0**；窗口上限 `W` 归架构域裁，`W` 若改该线立即失效。（P13 §2.2 另注：迁移号「勿先占 0015」已由批次 E 落地消解。）

---

## 3. 计数恒等式核对（纪律：pi 口径）

用 C13 终版（`2bd2bff`）两口径**独立对账**：

| 口径 | passed | skipped | deselected | 合计 |
|---|---|---|---|---|
| `-m "not bench"` | 2213 | 120 | 70 | **2403** |
| `-m bench` | 67 | 3 | 2333 | **2403** |
| 全量 | **2280** | **123** | 2403 | — |

**两侧独立合计恒等于 2403** ⇒ 无用例丢失/重复；**skipped 合计 123 与主树记「123 skipped」逐字一致** ✓。

---

## 4. 给 M6 首波派单的三条配置面结论（**只报**）

1. **soak 阶段 A 施工许可**：CI 冒烟面当前绿、阶段 A 与原断言语义等价 ⇒ **CI 面零风险**，可按 P14 §2.1 施工，**但须与「生命始终」同 CR 提阶段 B**（§1.4 次序红线）。
2. **定标轮暂不派**：两条硬门均未达——门 2 本机 `2.657 > 2.0`（**本机持续降频**）、门 1 内容面 `fire*.py` 缺 ＋ `sim/npc` 零 power 消费 ⇒ **缺一不派**。
3. **派单时须带的两条配置纪律**：① 定标轮跑前**先跑探针**并把 `throttle_ratio` 写进回执（P13 门 2 就是为此设的「步骤 0」）；② 本机冒烟测试默认会因降频 skip，**验证 CI 断言面须带 `PI_THROTTLE_SELFCHECK=0`**，否则把 skip 误读成绿或误读成红。

---

## 5. 本单变更清单与边界

| 文件 | 性质 |
|---|---|
| `docs/config/m6-c1-ci-calibration-confirm.md` | **新**：本确认稿 |
| `.orca/memory.md` | **+1 行**：②节本轮快照 |

**未做（刻意）**：改 `.github/workflows/*.yml`（**零 yml**）／改 `sim/`（跑测试与探针**只跑不改**）／改 `docs/perf/`（**pi 域**：P13/P14 只读）／改 `docs/README.md`／派定标轮（**两门未达，属 pi/Claude 决策**）。

**本单亲跑的验证**：`throttle_probe` **1 次**（输出 JSON 见 §2.2）＋ `test_soak_ci_smoke_stability` **1 次**（`PI_THROTTLE_SELFCHECK=0` ⇒ `1 passed`）＋ 计数恒等式核对。**未跑全量 pytest**（本单为定向确认，不重复 C13 的 158s 全量）。
