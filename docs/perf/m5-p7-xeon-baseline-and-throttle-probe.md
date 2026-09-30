# M5-P7：Xeon 8573C 档位基线评估 + 降频自检探针落地

> 性能域（pi），2026-09-30。任务（Claude M5-P7，裁 30 下一波）：①Xeon 档基线评估
> （baseline-epyc7763.json 的 `open_items`③：等 Xeon 全绿 run 或主动 dispatch 拿档；
> 被动收集 vs 主动 dispatch 攒档建议稿）；②降频自检探针（M5-P6 风险①）。
> 关联：`docs/perf/m5-p6-soak-arbitration.md`（§2.2 机理、§5-1 建议①）、
> `docs/perf/bench-plan.md` §4.1（八步）、`docs/arch/m5-rulings.md` §G（本单派发）。

---

## 0. 结论速览

| # | 问题 | 结论 |
|---|---|---|
| 1 | Xeon 档需要建基线吗？ | **需要**，但**不是紧急项**（P3 级）。证据：`median:25%` 是**总体中位**判定，Xeon 数据对 EPYC 基线曾**全绿**（run 36670751263）——门禁不会假红，但代价是 **17/59 行 \|drift\|>25% 被中位吃掉** ⇒ 门禁在该档**近乎无判别力**。 |
| 2 | 被动收集还是主动 dispatch？ | **被动收集为主、主动 dispatch 为辅**（最低成本）。理由见 §2：dispatch 不可控机位（P(Xeon)≈25%）、单轮 ~50min、且**非 Xeon 轮的产出是 0**。**已发一轮主动 dispatch 作数据点**：落 EPYC 未命中 ⇒ 实证「dispatch 不挑机位」，**不再追加**（§3）。 |
| 3 | 拿得到全绿 Xeon run 就预建吗？ | **是，按 §4.1 八步预建 `baseline-xeon8573c.json`**（零改 yml/门禁语义；§4）。 |
| 4 | 探针落了吗？ | **已落**：`sim/tests/bench/throttle_probe.py` + `test_bench_soak.py` 接住 ⇒ 降频本机 soak **skip 而非红**（实测：25.7s 内 skip，省 7 分钟空烧；§5）。 |

---

## 1. Xeon 档位基线：为什么需要建，为什么不紧急

### 1.1 已有硬数据（同一 run 的两种对照，M5-C6 实测）
run `36670751263`（Xeon 8573C，59 行，与 EPYC 基线行集逐字同构）：
- 对 **EPYC** 基线：**17/59 行 \|drift\|>25%**，中位 \|drift\| 21.7%，**59 行全部「Xeon 更快」**。
- 但该 step **success** ⇒ `--benchmark-compare-fail=median:25%` 是**总体中位比**判定，17 行离群被中位吸收。

### 1.2 推论：门禁在该档近乎无判别力
- **假红**没有（median 宽容）；**漏报真回归**有——Xeon 快 20%+ 的档位差把 25% 的回归窗口吃掉了：
  一个让某行慢 20% 的真回归，在 Xeon 上表现为「恢复 EPYC 水平」，drift 为负，**永不越线**。
- C6 的 `::warning::` + `::error title=基线不可比::` 已让它**可见**（不判红，裁 30-A3 维持）。
- ⇒ **建 Xeon 基线的收益**：把「不可比」变成「可比」，恢复 25% 窗口的判别力。
- ⇒ **不紧急的原因**：当前 nighty 落到 Xeon 的概率不高（近 14 轮仅 1 轮），且落到也不红。

## 2. 被动收集 vs 主动 dispatch：成本对比与结论

### 2.1 成本模型（均实测定标，非估计）

| 维度 | 被动收集（等 nightly 落 Xeon） | 主动 dispatch |
|---|---|---|
| 单轮成本 | **0**（本来每天跑） | **~50min/轮**（跑基准 ~4min + 7 日完整跑 ~31min + overhead；任务书也按此估） |
| 命中 P(Xeon) | **不可控**：近 14 轮 1 轮 ⇒ ≈**7%~25%**/轮 | 同（**机位由 GitHub 池定，dispatch 不指定机型**） |
| 单轮非命中产出 | **0** | 0（EPYC 轮与既有 baseline 重复，仅多一条 provenance） |
| 期望等待 | ≈4~14 个 nightly ≈ **4~14 天** | 命中 1 次期望 ≈4 轮 ≈ **3.3 小时 CI 墙钟**，但其中 3 轮白跑 |

### 2.2 一个关键事实：**dispatch 无法挑机位**
`workflow_dispatch` 只触发 workflow，`runs-on: ubuntu-latest` 的机位由 GitHub 分配。
实测同一 `ubuntu-latest` 池近 4 轮出现 EPYC×3 + Xeon×1 ⇒ **主动 dispatch 的命中率与被动完全相同**，
差别只在「不用等 nightly 排期」。⇒ **主动 dispatch 的唯一优势是省排期等待**（4~14 天 → 3.3 小时），
代价是 3/4 的轮次白烧 ~50min。

### 2.3 结论：被动为主、一伦主动为辅
- **主线 = 被动收集**： nightly 每天自动跑，落到 Xeon 且全绿即触发 §4 的八步预建。
  成本 0、无白烧；缺点只是等待。
- **辅线 = 一轮主动 dispatch**（本单已发，§3）：为「被动收集」先拿一个**当前 main tip 上**的
  Xeon 数据点，同时验证「dispatch 是否可命中 Xeon」。若命中且全绿 ⇒ 直接进 §4；
  若落 EPYC ⇒ 记一条 `cross_check`，等 nightly 被动命中（**不再追加 dispatch**，
  因为命中率不因 dispatch 上升，继续只是白烧）。
- **不采纳「连续 dispatch 到命中」**：3/4 白烧 ~50min/轮，且对 nightly 的长期信号无增量。

> **对 Claude 的请裁点（一句话）**：是否同意「被动为主 + 已发的这一伦主动为辅，**不再追加
> 主动 dispatch**」？若同意，本文件 §4 即触发条件（nightly 落 Xeon 且全绿）。

---

## 3. 已发的主动 dispatch（数据点）

- run **`36721350832`**（`workflow_dispatch`，ref=main，head `14aa57f`，2026-09-30T13:24Z）。
- 目的：拿当前 main tip 的机位/Xeon 可能性数据；若落 Xeon 且全绿 ⇒ 直接满足 §4 的「全绿 run」前提。
- **结果（已回填，2026-09-30 15:05Z）**：落 **AMD EPYC 7763**（**非 Xeon**）⇒ 未命中 Xeon。
  这正是 §2.2 的实证：**dispatch 不能挑机位**（`runs-on: ubuntu-latest` 的机位由 GitHub 池分配）。
  run **completed success（全步骤绿）**，并顺带产出一次高质量的 EPYC 交叉核对：
  - artifact 59 行与 baseline 59 行逐字同构，`median |drift|` **1.9%**、`max |drift|` **6.4%**、**0/59 >25%**；
  - soak-windows.jsonl：mock 30k 3.505→3.43ms 漂移 **0.9974**、L1 30k 2.176→2.13 漂移 **0.9812**、
    **604,800 tick 完整跑 3.427→3.39 漂移 0.9956** ⇒ **当前 main 无性能回归**，且 **CI 机无降频**
    （对照本机探针 8.39x：soak 红确系本机特有，见 §5.3）。
  - 记为 EPYC baseline 的 `cross_check`（**未改 baseline 本体**：C4 的 59 行来源纪律不变；
    是否据本轮重生成归 Claude/cline 裁，超出本单「Xeon 档基线」范围）。
- **结论：不再追加 dispatch**（命中率不因 dispatch 上升，继续只是白烧 ~50min/轮）；
  转**被动收集**——nightly 每晚自动跑，落到 Xeon 且全绿即触发 §4。
- 注：`sim/tests/bench/` 在 `ac0d559..14aa57f` 区间**零 diff**（§4.1 的「同一 bench 行集」
  前提自动满足），故 `36670751263` 的 Xeon 59 行与任何 main 代际的 bench 行集同构。

## 4. 预建 `baseline-xeon8573c.json` 的八步（触发条件满足时执行）

**触发条件（满足其一即执行）**：①本章 §3 的 dispatch run 落 Xeon 且**全步骤绿**；
②任一 nightly run 落 Xeon 且全步骤绿（被动收集命中）。

步骤（照 `bench-plan.md` §4.1，逐条标注本档位的实际做法）：
1. `gh run list --workflow nightly-bench.yml` 取该全绿 run id；
2. `gh run download <RUN_ID> -n bench-result -D <tmp>`（artifact 含 `perf/bench.json` + `docs/perf/runner.txt`）；
3. **五字段核对**（本档位期望值）：ubuntu-latest / nproc 4 / **INTEL(R) XEON(R) PLATINUM 8573C** / py3.12.3 / uv 同锁文件；
   **不一致就跑第二步重新取**（不同档位不能混基线）；
4. `cp <tmp>/perf/bench.json docs/perf/baseline-xeon8573c.json`，文件头补 `runner` 注释块（五字段 +
   `source_run: <RUN_ID>` + `note: "CI 档位基线（Xeon 8573C）；定标机绝对阈值见 sim/tests/bench/thresholds.py"`）；
5. 本地 sanity：`uv run pytest -m bench --benchmark-compare=docs/perf/baseline-xeon8573c.json --benchmark-compare-fail=median:25%`
   ——本机（Win11）对 Xeon 基线同样**可能 EXIT=0 或不 0**（M5-P6 已订正 step 5 措辞：判据是越线项集合能否由档位比解释）；
6. **不改 `nightly-bench.yml`**：判红仍是 `--benchmark-compare=docs/perf/baseline-epyc7763.json --benchmark-compare-fail=median:25%`。
   Xeon 档基线只是**离线参照物**（用 `--benchmark-compare=` 手工比），C6 的 warning 通道不变
   ⇒ 本步是「预建存档」而非「换门禁」；
7. commit + 在 `baseline-epyc7763.json` 的 `baseline_meta.open_items`③ **补记「Xeon 基线已建于
   `baseline-xeon8573c.json`（run <ID>）+ 离线用法」**（不是删条目——那是 cline C6 的登记物，按 §8 纪律不删他人登记）；
8. 回执留言板（run id + 五字段 + 行数 + 与 EPYC 的同口径对照）。

**纪律**：不改任何阈值（`thresholds.py` 零改动）；不用本机数造 baseline（本机是不同档，
且当前处于降频，见 §5）；**不把 25% 当新阈值**。

## 5. 降频自检探针（M5-P6 风险①收口）

### 5.1 落点与口径
`sim/tests/bench/throttle_probe.py`（新模块）+ `sim/tests/bench/test_bench_soak.py`（接线）。

| 项 | 值 | 依据 |
|---|---|---|
| 短冲程 | 500k 次整数自旋 ×5，取 **min** | 短负载让 CPU 短暂冲高频 ⇒ 本机最佳表现的代理 |
| 持续段 | 同 workload 跑满 **25s**（env `PI_THROTTLE_SUSTAIN_SECONDS` 可覆盖） | 需够长才触发功耗墙 |
| 判据 | `max(持续单样本)/短冲程基线 > 2.0` ⇒ `throttled` | M5-P6 实测：健康本机 1.2~1.5、降频本机 **6.6~7.9** |
| 成本 | ~25s + ~0.1s | 只在显式调用时发生 |
| 关闭 | `PI_THROTTLE_SELFCHECK=0` | CI 可完全关掉（nightly 不设该 env，默认开但 CI 机器不降频 ⇒ 不误 skip） |

### 5.2 接线点（`skip` 而非 `fail`）
- `nightly_soak_result` **fixture 体内**（先判再烧 7 分钟墙钟）；
- `test_soak_nightly_l1_feeder_stability`、`test_m2_full_7day_acceptance` **测试体首行**；
- `_assert_no_runaway` 也带前置（其它调用路径兜底）。
- 语义：降频是**环境事实**，不是代码回归 ⇒ `pytest.skip` 并给出「稍候重跑 / 直看 CI」指引；
  **漂移比判据天然免疫降频**（比值），资源判据（RSS/GC/句柄）同样免疫 ⇒ 不受影响的判据
  仍由 CI 覆盖，不因本机 skip 而漏检。

### 5.3 实测（本机，2026-09-30）
| 探针 | 输出 |
|---|---|
| CLI `python -m sim.tests.bench.throttle_probe` | `{"burst_base_ms": 16.434, "sustained_worst_ms": 137.928, "throttle_ratio": 8.393, "throttled": true, "samples": 371}` |
| 接线上 `test_soak_nightly_longrun_stability` | **`1 skipped in 25.70s`**（此前 `1 failed in 433.20s`） |
| 25s 持续段曲线 | first 3 样本比值 1.151/0.982/1.032 → last 3 1.345/**7.316**/7.877 |
| **CI 机（EPYC 7763）对照** | 同口径 soak-windows：mock 30k **3.505→3.43ms** 漂移 **0.9974**、L1 30k 2.176→2.13 漂移 **0.9812**、604,800 tick 完整跑 3.427→3.39 漂移 **0.9956** ⇒ **CI 无降频**（比值口径 ~1.0），本单 §3 dispatch run 实证。**推论：nightly 上探针不会误 skip**（专用 runner 稳定），且本机 soak 红确系本机特有。 |

## 6. 边界与门禁
- 本单落 `sim/tests/bench/`（1 新 + 1 改）+ `docs/perf/`（本文件）+ `.orca/`；**未动 `thresholds.py`
  一个字符**（任务书明令）；未改 `nightly-bench.yml`；未预建 baseline（等 Xeon 全绿 run，§4）。
- 探针**不进每提交 CI 的负担**：`-m "not bench"` 只跑 `test_throttle_probe_shape` 与
  `test_throttle_probe_selfcheck_off_short_circuits`（1s 持续段 + 短路用例，秒级）；
  25s 口径只在 nightly soak 路径。
- 已知局限：探针阈值 2.0 是**当前两台机器的观测分界**（1.5 vs 6.6），非全机型普适；
  若将来在别的开发机上运行，应先跑一次 CLI 看本机比值分布再定判据（docstring 已写明）。
