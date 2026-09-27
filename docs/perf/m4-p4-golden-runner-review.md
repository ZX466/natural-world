# M4-P4：golden runner 档位复核（nightly 前置）
> 性能域（pi），2026-09-27。任务：golden-nightly（cline C5，`.github/workflows/golden-nightly.yml`，
> 每 job 单种子 × 864,000 tick）`timeout-minutes: 90` 的余量复核 + 与 M4-P2 红线无冲突确认。
> 依据：C3 本机口径（`docs/arch/t5-golden-scaffold.md` §4，0.62ms/tick @10 实体）、
> C5 workflow（cline ZX466/cline `53175ca`）、**nightly-bench CI artifact**
> run `36269054118`（2026-09-26，ubuntu-latest / EPYC 9V74 4 核 / Python 3.12.3，
> `perf/bench.json` 56 bench + `docs/perf/runner.txt`）。
> 本机复核口径：Win11 + WSL2（24 核逻辑 / 7GB 可见内存），Python 3.12.13。
> **纪律：只读 + 文档**；不动 sim/、不动 thresholds.py。

> **前置状态（本单提交时）**：`golden-nightly.yml` **尚未收编进 main**（cline ZX466/cline
> `53175ca`，因 GitHub `workflow_dispatch` 要求工作流存在于默认分支，首跑被 404 阻塞）。
> 故本单的 §2 timeout 复核是**基于 CI bench artifact 的档位外推**（非 golden 首跑实测）；
> cline dispatch 首跑绿后，其各种子 `golden-<seed>.json::wall_s/mean_tick_ms` 应回填本件
> §2.2 复核真值——**若首跑实测与 §2.2 外推偏差 >2x，以首跑为准重判 timeout**（§2.2 表给的是判据框架）。

## 0. 结论速览
| # | 问题 | 结论 |
|---|---|---|
| 1 | golden-nightly 会否撞 M4-P2/P3 红线 | **不撞**。golden 与 bench 的 pytest 选择集**互斥**：CI 跑 `-m "not bench"`，nightly-bench 跑 `-m bench`；golden 两文件**无 `bench` marker 且不 import `thresholds`/`harness` 断言**（已核）。三条 M4 红线只在 `test_bench_*.py` 的 `_record_proposal`（本身不断言）与 nightly advisory 档位运行 |
| 2 | `timeout-minutes: 90` 是否合理（runner 档位） | **合理，余量充足**。CI 档位实测外推：单种子 10 日 **≈6.2 min**（10 实体）/ **≈35 min**（50 实体）→ timeout 90 = **14.5x / 2.6x 余量**。见 §2 |
| 3 | 本机口径与 C3 记录的差 | C3 记 53.4s/日 @10 实体 = 0.62ms/tick；本机复测 **驱动墙钟 ~4.8-5.6s/日**。差因：C3 读的是**全墙钟**（含 pytest 收集/落库/日志），`mean_tick_ms` 只计 `advance_frame` 段。**真 test_golden_full[7] 实跑 ~138s**（10 日，含事件累积 1.7M 条）≈ 13.8s/日。见 §3 |
| 4 | 潜在风险（非 timeout） | **内存**：test 收集全事件（`all_events.extend`）→ 1.728M 条 ≈ **3.4GB**；50 实体口径 ≈ **17GB**。当前 `n_entities=10` 安全，但 **30k+ 实体或 50 实体口径会撞 runner 7GB**。见 §4 |
| 5 | M4-P3 意愿红线跨档位余量 | CI 档位意愿增量 **+0.334-0.361ms** vs 线 0.35ms → **余量仅 0.97-1.05x（贴线）**；M4-P2 施工推进 CI 0.337ms vs 线 0.30ms → **0.89x（越线）**。见 §5 |

## 1. 名目冲突核对（任务书第 1 项）
### 1.1 选择集互斥（证据）
| 工作流 | pytest 选择 | golden 是否入选 |
|---|---|---|
| `ci.yml` 每提交 | `-m "not bench"` | 否（golden 有 `PI_T5_FULL`/`PI_GOLDEN_SMOKE` env 门，默认 skip）|
| `nightly-bench.yml` | `-m bench` | **否**（golden 两文件无 `bench` marker）|
| `golden-nightly.yml`（陈） | `test_golden_full.py::test_golden_seed_full[seed]` | 是（唯一入选）|
核验：`git grep -n "bench\|thresholds\|harness" origin/main -- sim/tests/golden/` → **零命中**
（golden 只 `import sim.tests.bench.harness.make_state` / `soak.make_mock_feeder` 两个**建世界函数**，
不读阈值、不跑断言组）。
### 1.2 三条 M4 红线落点
| 红线 | 落点 | golden 影响 |
|---|---|---|
| `BUILD_PROGRESS_TICK_LIMIT_MS=0.30` | `test_bench_structure.py::test_build_progress_advance_100_sites` | 无（不入选 golden）|
| `COLLAPSE_FRAME_LIMIT_MS=0.85` | `test_bench_structure.py::test_collapse_cascade_frame[*]` | 无 |
| `WILLINGNESS_TICK_LIMIT_MS=0.35` | `test_bench_willingness.py::test_tick_overhead_injected_50npc` | 无 |
→ **golden-nightly 的 job 不会撞 pi 域任何红线断言**（选择集互斥 + golden 不 import 阈值）。

## 2. timeout 90 复核（任务书第 2 项，CI 档位外推）
### 2.1 档位换算（CI ÷ 本机）
本机 P2/P3 定标 bench 与 CI artifact（run `36269054118`）同 bench 对照：
| bench（同代码） | CI (ms) | 本机 (ms) | CI/本机 |
|---|---|---|---|
| `build_progress_advance_100_sites` | 0.3371 | 0.1743 | 1.93 |
| `collapse_cascade_frame[10k]` | 0.7748 | 0.4810 | 1.61 |
| `support_graph_materialize[10k]` | 11.3736 | 6.1128 | 1.86 |
| `fold_replay_core_1000` | 3.1416 | 1.6856 | 1.86 |
| `tick_baseline_none_50npc` | 1.2187 | 0.7161 | 1.70 |
| `tick_overhead_injected_50npc[band1]` | 1.5793 | 0.9153 | 1.73 |
**稳定档结论**：Python 侧主导负载 CI/本机 **1.55-1.93x**（中位 **~1.7x**）。与
`docs/perf/ci-calibration-m2p6.md` 的 M2 档位（1.13-1.35x）相比**更高**——因本轮 bench
多为**小对象/短帧高频构造**（pydantic/dataclass/JSON），共享 4 核下解释器开销放大更明显。
### 2.2 golden 单种子时长外推
本机 golden 驱动墙钟（§3）：
| 口径 | 本机 mean_tick_ms | CI 外推（×1.7） | 10 日/种子（CI） | timeout 90 余量 |
|---|---|---|---|---|
| 10 实体（golden 当前口径） | 0.055-0.065 | ~0.10 | **≈0.86 min** | **105x** |
| 10 实体（含事件累积，真 test 口径） | 0.120 | ~0.20 | **≈1.7 min** | **53x** |
| 50 实体（`make_state(50)`，M2 口径） | 0.313 | ~0.53 | **≈4.6 min** | **19.5x** |
| 100 实体（外推线性） | 0.632 | ~1.07 | **≈9.3 min** | **9.7x** |
**判读**：golden 当前 `n_entities=10` 口径下，CI 单种子 **≈1-2 min**，timeout 90 = **50-100x 余量**
（远超 C5 注释里「C3 实测 13-27 min/种子」的估——那是 50 NPC 口径，且是**本机全墙钟**）。
即使升到 100 实体口径，90 仍留 **~10x**。**timeout 90 合理，无需调整。**
### 2.3 C5 注释与实测的差（澄清）
C5 workflow 头注「C3 实测 13-27 min/种子」，实际对应 50 NPC 口径的**本机全墙钟**外推
（0.9-1.9ms/tick × 864,000 = 13-27 min）。真 test_golden_full 是 **10 实体**口径 →
本机 ~2.3 min/种子（实测 138s）。**90min 是按最坏（50 NPC）留的 3x 余量**，
对当前 10 实体口径是 ~50x——**偏保守但无害**（护栏宜松不宜紧）。

## 3. 本机 golden 实测（复核 C3 口径）
| 口径 | 实测 | mean_tick_ms | 说明 |
|---|---|---|---|
| driver 1 日（10 实体，无累积） | 4.72-5.62s | 0.055-0.065 | 纯 `run_golden`，`drain=True` 每帧清 |
| driver 1 日（10 实体，累积事件） | ~10.5s | 0.121 | `on_events=extend` + **structlog 未抑制**（debug 逐事件打日志）|
| **真 test `test_golden_seed_full[7]`** | **138s**（10 日） | — | 2 次复测 137-139s，稳定 |
| driver 10 日（10 实体，无累积） | 58.2s | 0.067 | |
| driver 10 日（10 实体，累积） | 71.6s | 0.083 | |
- **C3 记录 53.4s/日 vs 本机 driver 4.7s/日**：差 ~11x。C3 的 53.4s 是 **pytest 全墙钟**
  （含 collect + 测试 setup + 大量 structlog debug I/O）；本机 `mean_tick_ms` 只计
  `advance_frame`。**真 test 10 日 = 138s** 介于两者之间（含事件累积 1.7M 条 + 断言组）。
- 建议统一口径：**以真 test 墙钟为准**（138s 本机 / 外推 CI ~4 min），C3 的 53.4s/日
  口径应标注「含 I/O 全墙钟」。

## 4. 内存风险（本单新增观察项）
`test_golden_full` 把**全事件流**累积进 `all_events`（`on_events=all_events.extend`）供守恒断言：
| 口径 | 事件数 | 保留内存（tracemalloc 实测） |
|---|---|---|
| 1 日（10 实体） | 172,800 | **338MB**（~1954B/事件深拷贝）|
| 10 日（10 实体，= 真 test） | 1,728,000 | **≈3.4GB** |
| 10 日（50 实体，外推） | 8,640,000 | **≈17GB** |
- 本机 7GB 可见内存：10 实体口径 **3.4GB 已占 ~半**；50 实体口径**必 OOM**。
- CI ubuntu-latest **7GB RAM**：10 实体 3.4GB **可跑但吃紧**。注：memory 记的「T5 首跑
  在 ~95min 处被系统（Claude Code 会话）内存中止」是**开发会话**内存，与此处**测试进程**
  事件累积内存是两件事——后者由本单 tracemalloc 实测确认（1.7M 事件 ≈ 3.4GB）。
- **建议（给 T5 数据面/行为链）**：守恒断言不必全量累积——可在 `on_events` 里**增量折叠**
  （只留 matter/structure/material 终态 + id 集），内存降到 O(状态) 而非 O(事件)。
  当前 10 实体口径可接受，但**升 50 实体前必须改为增量折叠**。

## 5. M4-P2/P3 红线跨档位余量（新增数据）
CI artifact（run `36269054118`）含 M4-P2/P3 全部 bench（本域已随 main 收编）：
| 红线 | 本机 median | **CI median** | CI/本机 | 线值 | CI 余量 |
|---|---|---|---|---|---|
| 施工推进（100 点） | 0.1743 | **0.3371** | 1.93 | 0.30 | **0.89x ❌ 越线** |
| 坍塌单帧（10k） | 0.4810 | **0.7748** | 1.61 | 0.85 | 1.10x |
| 意愿注入增量（band1） | 0.200 | **0.361** | 1.80 | 0.35 | **0.97x ⚠ 贴线** |
| 意愿注入增量（band3） | 0.206 | **0.334** | 1.62 | 0.35 | 1.05x |
- **观察态无红**：本域 bench 用 `_record_proposal` 只记录不断言，nightly advisory 门
  （`PI_BENCH_ADVISORY=1`）亦不致红——**当前不影响 CI**。
- 但**一旦转硬断言**（裁后）：施工推进 **0.30 线在 CI 档位即越线（0.89x）**、意愿
  band1 **0.97x 贴线**。→ 建议裁定时**按 CI 档位定线**（实测 × 1.7 应基于**档位对应值**，
  或显式声明「硬断言只在定标机」——与 M2-P6 裁 1 口径一致）。
- 坍塌单帧 0.85 在 CI 1.10x，**安全**。

## 6. T5 完成率基线与 m4-willingness 观察项（任务书第 3 项）
- **errands_rate 基线归档口径**（`golden-<seed>.json::errands_baseline` = `{cases, passed, rate}`，
  只记录不设阈值）：与 `m4-willingness-hotpath.md` 观察项**无冲突**——后者管的是
  **表现面成本**（band≥1 才产独白），完成率管的是**行为面结果**（差事是否走通），
  两者不共享路径也不共享取值。
- 交叉点：若未来「表现面才产独白」引入**帧级节流**（如只在渲染帧产），会不会影响差事？
  不会——独白事件**不参与** `run_all_chains`（执行器只走 `parse_intent`/`IntentGate`/
  `apply(MOVE)`），故降采样独白对 errands_rate **零影响**。
- 建议：把 `band≥1 NPC 占比` 作为可选监控并入 golden 报告（当前报告无此字段；
  若要，属行为链/数据面增列，本域不擅自加）。

## 7. 给裁定的输入（本单不含断言/不改码）
1. `timeout-minutes: 90` **维持**（对当前 10 实体口径 ~50x 余量，对 50 实体 ~20x）。
2. **内存是本单第一风险**（非 timeout）：10 实体 3.4GB 可跑，**升 50 实体前**须把
   `all_events` 改增量折叠（属 T5 数据面/行为链域）。
3. M4-P2/P3 三条红线**跨档位余量**已量（§5）：**转硬断言前**需按档位重定线或声明
   「硬断言只留定标机」（M2-P6 裁 1 口径）。
4. C3「53.4s/日」口径建议标注为**含 I/O 全墙钟**，避免与 `mean_tick_ms`（纯 advance_frame）
   混比；真 test 墙钟（本机 138s/10 日）才是 runner 估算基准。
