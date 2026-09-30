# M5-P6：soak 定标机仲裁 —— 本机持续负载降频，非真回归（裁 28-D 后续）

> 性能域（pi），2026-09-30。任务（Claude M5-P6）：M5-CRUD（main `12dbbb1`）收编轮
> nightly bench `36634414471` 一红，板上记「3 failed（唯一留痕 = soak l1_feeder；另 2 截断），
> 复跑被会话窗截断（`....FF.s`）」；**判「待仲裁」**。本单给**定论**：真回归 vs 本机/池抖动，
> 裁口径给处置；另含 CRUD 写路径 bench 补项**提案稿**（零代码）与两处文档订正。
> 关联：`docs/perf/m2-acceptance.md` §2/§3（判据与分级）、`docs/perf/m5-p5`（soak 窗口级
> artifact 上次交付）、`docs/perf/bench-plan.md` §4.1（baseline 八步，含本单订正）、
> `docs/arch/m5-rulings.md` 裁 28-D（硬断言只留定标机）。

---

## 0. 结论速览

| # | 问题 | 结论 |
|---|---|---|
| 1 | soak 红是**真回归**（代码/O(n) 累积）吗？ | **否**。CI 定档机 **3 形态全绿**（逐窗数字见 §1）；同代码在本机 **main 与 P5 两个 tip 复现同一失败**（7.04ms / 12.5ms）⇒ 与 `12dbbb1`/`0010` 无关；hot path `sim/perception` `sim/npc` `sim/core` 自 P5 起**零改动**（`git log --name-only` 实证，§2.1）。 |
| 2 | 那是**抖动**吗？ | **是，且已定位到机理**：本机 `i7-14650HX` **持续负载下降频**，实测 **6.6x**（短冲程 100ms/3M iter → 持续 90s 末 690ms/3M iter，§2.2）。30k soak = **约 15 分钟持续 CPU**，恰是最坏暴露面；而 `test_bench_fast_forward` 等短冲程基准**不受影响**。 |
| 3 | 板上「3 failed / `....FF.s`」与 run 实况一致吗？ | **不一致，板上结论需修正**：run `36634414471` 的 GitHub 留痕里「跑基准」step（advisory=1）soak 行是 `....s..`（2 skip / **0 failed**），全程 `69 passed, 1 skipped, 0 failed`；**唯一红 step 是「基线对比」**，红的 4 条是 apply×2 / perception_sound / rng_1m_draws —— 全是 M2-P6 已登记的 **CI 档绝对阈值越线**，成因是**该 step 当时还没有 `PI_BENCH_ADVISORY=1`**（fix `1d5d3c5` 尚未进 main，时间线 §3）。§1 |
| 4 | 处置 | **不 BLOCK**。soak 恢复为「CI 定档机判绿 / 本机 advisory 观察」口径；**连续红计数清零**。**建议**（未执行，待裁）：本机 soak 加**环境自检门**（见 §5）。§4 |
| 5 | 0.90ms 线 / thresholds 行值 | **本单不动**（任务书）：红线仍「硬断言只留定标机」（m5-fast-forward-budget.md §8 三条迁移条件不变）。§6 |

> **一句话**：本机 soak 红是**持续负载降频**（6.6x 实测）造成的**口径假象**，CI 定档机三形态
> （30k mock / 30k L1 / 604,800 tick 完整跑）**逐窗全绿**（drift 0.995–1.004，RSS/GC 增长 ≈0）。
> **无真回归、无 O(n) 累积。**

---

## 1. CI 定档机三形态逐窗全绿（本轮直接证据）

数据源：run **`36670751263`**（`workflow_dispatch`，ref=main，head `ac0d559`；
`docs/perf/runner.txt`：ubuntu-latest / nproc 4 / **INTEL XEON PLATINUM 8573C** / py3.12.3 /
uv 0.12.20）artifact `bench-result` 的 **`perf/soak-windows.jsonl`**——这正是 M5-P5 交付的
**窗口级 artifact**，第一次在仲裁中直接派上用场（M5-P4 §1.2「只能取绿/红二值」缺口已闭合）。

### 1.1 三形态逐窗统计（CI 档）

| 形态 | 窗数 | 逐窗均值 (ms) | 逐窗 p99 (ms) | 漂移比 | RSS 增长 | GC 对象增长 | 句柄 |
|---|---|---|---|---|---|---|---|
| nightly mock 30k | 5 × 6000 | 2.778 / 2.767 / 2.764 / 2.774 / 2.753 | 6.04 / 6.00 / 5.98 / 6.02 / 5.94 | **0.9951** | +1.5MB | +8 | -1 |
| nightly L1 feeder 30k | 5 × 6000 | 1.706 / 1.698 / 1.703 / 1.727 / 1.705 | 2.96 / 2.97 / 2.98 / 2.97 / 2.92 | **1.0043** | +0.2MB | +4 | -1 |
| **7 日完整跑 604,800** | 7 × 86,400 | 2.700 / 2.683 / 2.683 / 2.684 / 2.684 / 2.686 / 2.682 | 5.81 / 5.72 / 5.72 / 5.72 / 5.74 / 5.76 / 5.72 | **1.0000** | −0.1MB | **+44** | -1 |

**判读**：
- **无 O(n) 累积**：604,800 tick 逐窗均值** flat 在 2.683–2.700ms**（极差 0.6%），漂移 **1.0000**。
- **无泄漏**：RSS 增长 −0.1~+1.5MB、GC 对象 +4~+44（阈值 20,000）、句柄 -1（Linux 探测不可用，
  按契约自动跳过，非缺陷）。
- **绝对量**：mock 2.77ms / L1 1.70ms / 完整跑 2.68ms，全部远低于 `SOAK_STEADY_MEAN_LIMIT_MS=6.2`。
- **该 run 的 `-m bench` 两次全量都是 `69 passed, 1 skipped, 0 failed`（231.46s / 225.85s）**
  （1 skipped = env 门 `PI_M2_FULL_SOAK` 未置的那次；完整跑由**另一个 step** 单独跑，也绿）。

### 1.2 与 M5-P4 的一致性
M5-P4（golden-nightly `36503174990`，EPYC 7763，10 种子 × 864k tick）给的逐日漂移 0.982–1.008、
mean_tick 0.118–0.2335ms（**10 实体**口径，非 50 NPC soak 口径，勿混）。本轮 50 NPC 口径在
**另一档机器（Xeon 8573C）**上同样 flat ⇒ **「无 O(n) 累积」这一结论跨机型、跨 seed 口径稳固**。

---

## 2. 本机复现与机理定位（为什么本机红、CI 绿）

### 2.1 先排除代码回归（三条互证）
1. **同代码双 tip 同败**：在 **main `0133b40`** 与 **P5 `629a8f9`**（`git worktree` 各跑一次）
   上分别跑 `test_soak_nightly_l1_feeder_stability`，**都红且数字一致**
   （window @6000 = **7.0437ms / 7.039ms** > 6.2；364.59s / 364.61s）。
   `12dbbb1`（CRUD）与 `10f85d1`（0010 回填）夹在 P5 与 main 之间 ⇒ **若为代码回归，P5  tip 应绿**。
2. **hot path 零改动**：`git log --name-only 629a8f9..origin/main` 对 `sim/perception`（无提交）、
   `sim/npc`（无提交）、`sim/core`（仅 `persistence/alembic/versions/0010_protected_backfill.py`，
   与 soak 路径无关）⇒ 被测路径在两次复现之间**未变**。
3. **CI 绿**（§1）⇒ 代码本身不红。

### 2.2 机理：持续负载降频 6.6x（本机实测，决定性）

| 探针 | 结果 | 说明 |
|---|---|---|
| 短冲程自旋（3M iter，~0.1s） | 96.7 / 97.0 / 98.8 / 97.6 / 100.1 ms | 与历史一致；**短基准不暴露** |
| **持续 90s 自旋**（158 个 3M iter） | 首个 100.4ms → **末个 661.5ms**，max 689.7ms | **降频 6.6x** |
| 30k mock soak 逐窗均值 | [10.54, 12.78, 12.02, 12.51, 13.00] ms | 超 6.2 红线 |
| 30k L1 feeder soak 逐窗均值 | [5.43, 6.94, 6.95, 6.94, 7.08] ms | **窗口 1 起即越 6.2** |
| 1200 tick CI 形态（L1） | [1.06, 1.03, 1.00] ms | 短 ⇒ 不暴露降频 |

- **形态完全吻合**：soak 是**持续数分钟至数十分钟**的 CPU 密集负载（30k tick ≈ 15 分钟），
  恰落在降频曲线最深处；而 `SOAK_MEAN_DRIFT_RATIO_LIMIT`（比值）因降频是**整体**下移而
  **不受影响**（实测 drift 1.02 / 1.017，≤1.5）——**这正是「漂移比」判据设计上想要的抗扰**。
- **交叉印证（文档先例）**：`sim/tests/bench/test_bench_fast_forward.py` docstring 早已记录
  「同进程重负载后纯 CPU 自旋会 **6.7x** 变慢（热/功耗降频，非代码退化）」——本轮 6.6x 与之一致。
- **profile 归因（不含代码改动）**：88% 时间在 `sim/perception/senses.py::assemble`
  （LOS 射线追踪），`_line_blocked` 49 次/assemble；**成本在 ~2k tick 后从 2.1→14ms/tick 一步上升后
  flat**，对应 `los`/`walls` 实例缓存饱和（21,871 / 24,709 条，此后不再增长）⇒
  **不是泄漏型增长，是饱和台阶**（CI 因不降频，台阶停在 ~2.8ms 处）。

### 2.3 本机 vs CI 的同口径对照

| 形态 | CI（Xeon 8573C） | 本机（i7-14650HX，已降频） | 比值 |
|---|---|---|---|
| 30k mock 逐窗均值 | 2.75–2.78ms | 10.5–13.0ms | **~4.4x** |
| 30k L1 逐窗均值 | 1.70–1.73ms | 5.43–7.08ms | **~3.9x** |
| soak 漂移比 | 0.995 / 1.004 | 1.017 / 1.020 | **≈1（比值免疫降频）** |

> **门禁含义**：`SOAK_STEADY_MEAN_LIMIT_MS`（**绝对值，6.2ms**）在**持续负载降频的本机**上必然假红；
> `SOAK_MEAN_DRIFT_RATIO_LIMIT`（**比值，1.5x**）免疫。这与裁 1「硬断言只留定标机」的
> **定档机 = CI/EPYC 类**精神一致，本机 soak 只应作 advisory 观察。

---

## 3. 板上「红项清单」与 run 实况的差异（订正）

run `36634414471`（`schedule`，head `7af3927`，2026-09-29 21:36Z）真实留痕：

| step | advisory env | 结果 | soak 行 | 摘要 |
|---|---|---|---|---|
| 跑基准 | **有** | success | `....s..`（2 skip，**0 failed**） | `69 passed, 1 skipped, 0 failed / 282.03s` |
| M2 7 日完整跑 | `PI_M2_FULL_SOAK=1` | success | — | `1 passed`（39 分级） |
| 上传基线结果 | — | success（`if: always()`） | — | `perf/` + `runner.txt` 已归档 |
| **基线对比** | **无** ← 缺陷 | **failure** | `....s..` | **4 failed / 65 passed / 274.55s** |

- **红的 4 条全非 soak**：`apply(move) 单事件` 0.057>0.040、`apply 50 事件批` 2.541>2.000、
  `感知听觉 50 NPC` median 5.386>3.600、`RNG 1M draws` median 376.7>330 —— **M2-P6 §1/§5.3
  已登记的 CI 档绝对阈值越线**（档位差，非回归）。
- **成因 = advisory 缺失**（裁 28-E 授权 cline 修复的正是这条）：`1d5d3c5`「基线对比 step 补
  `env: PI_BENCH_ADVISORY: "1"`」的合并 `ac0d559` 迟到（2026-09-30 11:20 +0800）→ 该 step 在
  `7af3927` 头上**重跑 `-m bench` 时把定标机绝对阈值重新变成硬断言**。修复后 run
  `36580639759`/`36670751263` 同 step 转绿 ⇒ **该缺陷已闭环**。
- **「soak l1_feeder F / `....FF.s`」的来源**：是**本机复现**的输出（本单 §2.3 实测：
  `3 failed, 11 passed, 1 skipped / 942.94s`，红项 = `test_soak_nightly_longrun_stability`、
  `test_soak_nightly_steady_p99_below_tick_budget`、`test_soak_nightly_l1_feeder_stability`），
  不是 CI run 的 soak。**板上把它记成 CI 留痕，需按本节订正。**

---

## 4. 处置（本单执行）

1. **判定：本机持续负载降频（6.6x 实测）导致的口径假象；非真回归、非池抖动导致的功能退化。**
2. **不 BLOCK**；**连续红计数清零**（soak 连续 3 轮红的计数按裁 21-D/28-D 终止）。
3. **soak 门禁口径（建议稿，待裁，§5）**：本机 soak 走 advisory（与 fast_forward 的
   `_record_proposal` 同形态），CI 定档机维持 `_assert_no_runaway` 硬判。
4. **不动 thresholds 行值**（任务书明令）：`SOAK_STEADY_MEAN_LIMIT_MS=6.2` /
   `SOAK_MEAN_DRIFT_RATIO_LIMIT=1.5` / 0.90ms / 42.0s 全部原样。
5. 两处文档订正已落（任务书第 3 项，见 §6 与 commit）。

## 5. 建议（登记，待裁，本单不执行）

1. **给 soak 用例加「环境自检门」**（防再花一轮仲裁）：在 `_assert_no_runaway` 前先跑一个
   ~0.3s 短冲程自旋探针，与本机历史值（100ms/3M iter 量级）比对；**偏差 >2x ⇒ 判
   `pytest.skip("本机降频中，soak 绝对阈值不可信")`** 而非红。理由：`SOAK_STEADY_MEAN_LIMIT_MS`
   是**绝对值**判据，在降频本机上必然假红（§2.2）；漂移比判据已免疫，无需门。
   落地形态候选：`sim/tests/bench/soak.py` 加 `perf_ok_for_absolute_thresholds()` 纯探针 +
   `test_bench_soak.py` 三处 nightly/milestone 用例调用。**风险**：探针本身要短（否则叠加降频）；
   阈值需按机型登记（与 runner 档位同源）。**须 Claude 裁后另单**。
2. **机器档位入 nightly artifact 已成事实，建议把 `runner.txt` 的 `cpu:` 字段做成断言**
   （cline C5 已建议「brand_raw 不一致告警不判绿」；性能域补一句：**跨机相对漂移门禁
   （median:25%）在异构池上不可比，与 soak 的绝对阈值同理**）。
3. **`SOAK_STEADY_MEAN_LIMIT_MS` 的档位注释**：当前注释只说「6.2 = tick p99 红线 8.3 的 75%」，
   未声明「定档机口径」。建议补一句「CI/EPYC 类档位实测 2.7–2.8ms（§1.1），本机降频时可达 7–13ms
   ⇒ 本机 advisory」。**本单未改**（thresholds 行值+注释归裁，任务书只授权「本域两行」且要求不动行值）。

## 6. 本单的文档订正（任务书第 3 项，已执行）

- `docs/perf/bench-plan.md`：
  - §4.1 step 3「EPYC **9V74**」→「AMD **EPYC 7763**」（runner.txt + `baseline.json`
    `machine_info.cpu.brand_raw` 双证）；
  - §4.1 step 5「定标机跑 CI 基线必然越线……**预期非零退出**」→ 按实跑改写为
    「**EXIT=0 与非 0 都可能是正常结果**，判据是越线项集合能否由档位比/单轮离群解释」
    （M5-C4 sanity 实测 EXIT=0：69 passed / 1 skipped / 168s）；
  - §0 档位行同改 9V74→7763；§4.1 末补 M5-P6 订正注（并声明 C5 的 `open_items`②（runner 池
    跨厂商）**仍然有效**，与机型笔误无关）。
- `docs/perf/ci-calibration-m2p6.md`：标题与 §0 表 9V74 → 7763，并加订正块
  （**档位比数字全部不变**，本文核心结论与机型名无关）。
- `docs/perf/m4-p4-golden-runner-review.md`：行内 9V74 → 7763 + 订正注。
- **CRUD 写路径 bench 补项提案稿**：见 `docs/perf/m5-p6-anchors-write-bench-proposal.md`（零代码）。

## 7. 边界与门禁
- 本单只动 `docs/perf/`（三处订正 + 两份文档）+ `.orca/`；**不改 `sim/tests/bench/`**（仲裁未达
  「需钉子」门槛：结论是假象，钉子会固化错值）；**不改 thresholds 行值、不改生产代码、不改 yml、不重生成 baseline**。
- 本机数字**不用于定 baseline**（裁 21-D/M5-P4 纪律延续）。
- **未决风险**：①本机 soak 在本轮无法本地验证（降频），后续本机 soak 红需先跑 §5-1 探针或
  直接看 CI；②runner 池跨厂商（C5 open_items②）未裁——**跨机相对漂移门禁的根基问题**；
  ③`SOAK_STEADY_MEAN_LIMIT_MS` 档位注释缺「定档机口径」声明（§5-3）。
