# M5-P8：Xeon 被动收集监控台账

> 性能域（pi），2026-10-01。任务（Claude M5-P8）：Xeon 档**被动收集**监控——
> 命中「落 Xeon 且全绿」的 nightly 即按 M5-P7 §4 八步预建 `baseline-xeon8573c.json`
> （离线参照物）；每次 run 出结论一句话登记（机型/结论）。**不再主动 dispatch**（裁 30-C 采被动策略）。
> 关联：`docs/perf/m5-p7-xeon-baseline-and-throttle-probe.md`（§4 八步）、
> `docs/perf/baseline-epyc7763.json`（`baseline_meta.open_items`③）。

---

## 0. 策略
- **被动收集**：每天 nightly 自动跑，**不主动 dispatch**（P7 §3 实证 dispatch 不挑机位，继续白烧）。
- **触发建基线**（任一即可）：①P7 §3 dispatch run 落 Xeon 且全绿；②任一 nightly run 落 Xeon 且全绿。
- **建基线后**：按 M5-P7 §4.1 step1–8 执行；**不改 `nightly-bench.yml`**（判红仍对 EPYC 基线，
  median:25%），Xeon 基线只是**离线参照物**；`thresholds.py` 零改动。

---

## 1. 台账（每 run 一行：机型 / 结论一句话）

| 日期 | run_id | 机型 | 结论（一句话） |
|---|---|---|---|
| 2026-09-30 | 36721350832 | AMD EPYC 7763 | 主动 dispatch 数据点，落 EPYC 未命中 Xeon ⇒ 实证「dispatch 不挑机位」，不再追加；全步骤绿（59 行），median\|drift\| 1.9%、0/59>25%，无回归。 |
| 2026-09-30 | 36670751263 | **Intel Xeon 8573C** | Xeon 全绿 run，但 17/59 行\|drift\|>25%（median 吃掉了，step success）；与 EPYC 不同档**不混基线**（C5 登记 cross_check），Xeon 基线未建。 |
| 2026-10-01 | 36793983148 | AMD EPYC 7763 | 经 GitHub Actions API 查证：nightly 成功，check 注释「机型一致：AMD EPYC 7763」（notice，非 mismatch）⇒ **未落 Xeon**，无新触发；不建基线。 |

> 备注：本单通过 GitHub Actions API（`actions/runs` + `check-runs` 注释）核对 nightly 机型，
> 最近一次（36793983148）为 EPYC。**自 P7 后无新 Xeon 全绿 run ⇒ 未预建 `baseline-xeon8573c.json`**。

---

## 2. 触发即用的八步（照 M5-P7 §4.1，勿改）
1. `gh run list --workflow nightly-bench.yml` 取该全绿 run id；
2. `gh run download <RUN_ID> -n bench-result -D <tmp>`（artifact 含 `perf/bench.json` + `docs/perf/runner.txt`）；
3. **五字段核对**（期望值）：ubuntu-latest / nproc 4 / **INTEL(R) XEON(R) PLATINUM 8573C** / py3.12.3 / uv 同锁文件；不一致则重取（不同档位不能混基线）；
4. `cp <tmp>/perf/bench.json docs/perf/baseline-xeon8573c.json`，文件头补 `runner` 注释块（五字段 + `source_run:<RUN_ID>` + note 定标机绝对阈值见 `thresholds.py`）；
5. 本地 sanity：`uv run pytest -m bench --benchmark-compare=docs/perf/baseline-xeon8573c.json --benchmark-compare-fail=median:25%`（判据 = 越线项集合能否由档位比解释，M5-P6 已订正）；
6. **不改 `nightly-bench.yml`**（Xeon 基线仅离线参照，C6 warning 通道不变）；
7. commit + 在 `baseline-epyc7763.json` 的 `baseline_meta.open_items`③ 补记「Xeon 基线已建于 `baseline-xeon8573c.json`（run <ID>）+ 离线用法」（不删既有条目——那是 C6 登记物，按纪律不删他人登记）；
8. 回执留言板（run id + 五字段 + 行数 + 与 EPYC 同口径对照）。

---

## 3. 现状
- **未预建 `baseline-xeon8573c.json`**：本单经 GitHub Actions API（`actions/runs`+`check-runs` 注释）
  核对 nightly，最近一次（36793983148，2026-10-01）为 **AMD EPYC 7763**⇒ 未落 Xeon；
  自 P7 后无新的「落 Xeon 且全绿」run。（注：无 `gh` CLI、无 token，故仅能读 check 注释判断机型，
  未能下载 artifact 本体；据此不预建基线。）
- **已知可作为触发源的 run**：`36670751263`（Xeon 全绿）——但为**回溯分析**用，其 artifact
  当时已不可再下载，且 P7 已将其作为 EPYC 基线的 `cross_check` 处理；按 step7 纪律**未擅动基线**。
- **下一步（网络可用 / 命中新 Xeon run 时）**：按 §2 八步建基线，并回填本台账 + open_items③。
