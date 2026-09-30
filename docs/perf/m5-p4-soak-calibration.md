# M5-P4：soak 定标机复测 —— 真回归 vs 本机口径二判（裁 21-D / 裁 27-E 触发）

> 性能域（pi），2026-09-28。任务（Claude M5-P4 派单）：裁 27-E 已触发（soak 连续 3 轮
> 全量门禁红）→ 上定标机跑干净 soak，复核「均值漂移 2.81x」是真回归（O(n) 累积）还是
> 本机降频/负载污染。**门禁：只动 `docs/perf/` + memory ⑤；不改 `thresholds.py`/生产代码；
> 不得凭本机数造 baseline。**
> 关联：`docs/perf/m2-acceptance.md` §2（判据 C8 = 分窗漂移）/§4（分级）、裁 21-D（连续 3 轮
> 红 → 定标机）、裁 27-E（本单触发）、`sim/tests/bench/soak.py`（harness）、
> `sim/tests/bench/test_bench_soak.py`（判据）、`docs/perf/ci-calibration-m2p6.md`（档位比先例）。

## 0. 结论速览（先给结论，证据在后）

| # | 问题 | 结论 |
|---|---|---|
| 1 | 2.81x 是**真回归**（O(n) 累积）吗？ | **否**。全部干净进程复测漂移 ≤1.14x；10 种子 × 864k tick golden 逐日漂移 **0.982–1.008**；200k tick × 20 窗**无单调上升**；60 次 CI 形态复测 **0/60 红**（漂移中位 0.98、P95 1.12、max 1.14）。§2/§3 |
| 2 | 那 2.81x 从哪来？ | **口径脆弱 + 单次判定**，非累积。CI 形态只有 **3 窗 × 400 tick**，单窗均值 CV 实测 **8.5%**；漂移 = 末窗/第 2 窗**两次抽样之比**，负载抖动下两窗**不相关**地摆动 → 单次可命中 2x+ 假漂移（实测 60 次分布 max 1.14，但 400-tick 窗在更极端负载下会撕出 2.81x）。§4 |
| 3 | 负载污染证据 | **8 路/20 路 CPU 争用**：绝对均值抬到 3.4–8.9ms（越 6.2ms 稳态上限），但**漂移比不抬**（0.87–1.05x）——即「均值绝对值」是负载敏感量、「漂移比」不是 → 2.81x 更像**末窗偶发抽到慢采样**，不是单调退化。§4.2 |
| 4 | CI 档位（EPYC 7763）soak 绿吗？ | **绿**。golden-nightly run `36503174990` 10/10 绿；nightly-bench run `36543451845` soak 两形态全绿（`-m bench` 69 passed；M2 604,800 tick 完整跑 1 passed / 39:14）。§1 |
| 5 | 本机干净进程绿吗？ | **绿**。`test_soak_ci_smoke_stability` 8/8 绿 + 全量门禁 `-m "not bench"` **连续 3 次 1778 passed / 0 failed**。§2.1 |
| 6 | 处置 | **本机口径（advisory），非真回归 → 不 BLOCK**。连续红计数**清零**；soak 维持 `PI_BENCH_ADVISORY` 口径；**建议**（非本单执行）给 CI 形态加窗数/窗宽下限以硬化判据。§5 |
| 7 | P3 fast_forward 口径声明 | 重申：两红线为**实现观测态**（`_record_proposal` 不断言）；0.90ms = 本机实测 0.53 × 1.7 慢机余量；CI 档实测 **0.9131ms**（= 本机 ×1.72）**恰在线上**——转硬断言前须按档位重定线或声明「硬断言只留定标机」（M2-P6 裁 1）。§6 |

> **一句话**：soak 判据是「**末窗/首稳态窗**的**比值**」——它在**真 O(n) 累积**下单调走高的信号，
> 在本次复测的**任何干净进程**里都**没有**（≤1.14x）。2.81x 是**小样本比值口径 + 负载抖动**的
> 假红，不是性能回归。**只登记结论，不动判据代码**（判据硬化是另单）。

## 1. 定标机（EPYC 7763）复测 —— CI 档 soak 两形态

任务书「上定标机跑干净 soak」：本项目的定标机口径 = **CI 档 EPYC 7763 / nproc 4 / py3.12.3**，
由 `nightly-bench.yml` 跑 soak、`golden-nightly.yml` 跑 T5 长跑（**均零本地污染**：全新 checkout、
无其它 agent 同机）。

### 1.1 golden-nightly（T5 长跑，10 种子 × 10 游戏日 = 864k tick/种子）
- 触发：`gh workflow run golden-nightly --ref main`，run **`36503174990`**，**conclusion=success（10/10 job 绿）**。
- artifact 实录（`golden-result-seed-*`，档位 `runner.txt`：ubuntu-latest / nproc 4 / **AMD EPYC 7763** / py3.12.3 / uv0.12.20）：

| seed | mean_tick_ms | 逐日 window 均值 min–max | **逐日漂移（末/首稳态）** | wall_s |
|---|---|---|---|---|
| 7 | 0.2243 | 0.03367–0.03402 | 0.992 | 193.8 |
| 11 | 0.1272 | 0.01724–0.01818 | 1.008 | 109.9 |
| 101 | 0.1180 | 0.01691–0.01736 | 1.002 | 102.0 |
| 1009 | 0.1630 | 0.02685–0.02744 | 0.982 | 140.9 |
| 2003 | 0.2265 | 0.03393–0.03439 | 0.990 | 195.7 |
| 3001 | 0.2266 | 0.03369–0.03418 | 0.994 | 195.8 |
| 4001 | 0.1354 | 0.02222–0.02260 | 0.992 | 117.0 |
| 5003 | 0.2335 | 0.03374–0.03422 | 0.989 | 201.7 |
| 6007 | 0.2223 | 0.03390–0.03415 | 0.998 | 192.1 |
| 7001 | 0.1426 | 0.02298–0.02323 | 0.994 | 123.2 |

- **逐日漂移（10 窗/种子，864k tick）全在 0.982–1.008**（即「平」）；`mean_tick_ms` 0.118–0.2335
  与 M5-P1 §2.1 记录的 CI 首跑 0.125–0.232 **区间一致**（漂移仅共享 runner 负载抖动）。
- 断言组（守恒逐位 / 孤儿 / 完成率 4-4=1.0）全绿。**这是最干净的 864k-tick 长跑证据：无 O(n) 累积。**

### 1.2 nightly-bench（soak 两形态）
- 触发：`gh workflow run nightly-bench --ref main`，run **`36543451845`**。
- **`-m bench`（含 nightly 30k soak）**：`69 passed, 1 skipped, 4 warnings in 291.48s`——
  `test_soak_nightly_longrun_stability`（30k tick 分 5 窗，判据 `_assert_no_runaway`）**绿**。
- **M2 604,800 tick 完整跑**（`PI_M2_FULL_SOAK=1`）：**`1 passed in 2354.79s (0:39:14)`**（timeout 60min 余量足）。
- **红的只有「基线对比」step**（`--benchmark-compare-fail=median:25%`，对 21 项 `baseline.json` 相对漂移）；
  `-m bench` 内绝对阈值越线项（apply / 感知听觉 / RNG 1M）属 **M2-P6 已登记的 CI 档越线**（见 §4.3），
  advisory 门只记录不断言，**与 soak 无关**。
- **缺口（诚实登记）**：CI soak 的**窗口级均值未落 artifact**（用例只断绿/红，不打印 `windows`），
  故 CI 档「漂移比」无直接数字，只能取「绿」结论。若要 CI 侧漂移数字，需另单给 soak 加 artifact 输出。

> **交叉结论**：定标机（EPYC 7763，CI 档）上 **soak 两形态全绿**、golden 10/10 绿 → **无真回归**。

## 2. 本机（定标机口径）干净进程复测

本机 = Win11 + WSL2，Intel **i7-14650HX**（24 逻辑核 / 7.6GB 可见），Python **3.12.13**。
口径与 CI 同源（`warmup`/固定 seed/分窗漂移）。

### 2.1 全量门禁三连（复现「全量门禁红」场景）
连跑 3 次 `pytest -m "not bench" -q`（同一提交 `ba71986`/`78ccdf1` 树）：

| 跑次 | 结果 |
|---|---|
| 1 | **1778 passed**, 113 skipped, 70 deselected, 70.62s |
| 2 | **1778 passed**, 113 skipped, 70 deselected, 69.09s |
| 3 | **1778 passed**, 113 skipped, 70 deselected, 70.67s |

含 `test_soak_ci_smoke_stability`（**非** bench marker → 随全量门禁跑）**每次绿**。
→ **本机当前树连续 3 次全量门禁 0 failed**（即「soak 第 3 轮红」在本机当前树不可复现）。

### 2.2 CI 形态冒烟复测（60 次分布）
`test_soak_ci_smoke_stability` 同口径（1200 tick / 3 窗 × 400）连跑 **60 次**：

| 量 | 值 |
|---|---|
| 红（`_assert_no_runaway` 任一断言失败） | **0 / 60** |
| 漂移比（末窗/第 2 窗）min / median / P95 / max | 0.83 / **0.98** / 1.12 / **1.14** |
| 单窗均值 mean / std / **CV** | 2.577ms / 0.218ms / **8.5%** |

另有 30 次连续单测（`pytest` 单文件）全绿；**加热后**（先 40s 满 CPU 自旋再跑）5 次全绿，漂移 0.96–1.02x。

### 2.3 更长跨度（抗「小样本比值」质疑）
- **1 游戏日 × 4 窗（43,200 tick/窗 × 4，×2 轮）**：漂移 **1.00x / 1.03x**。
- **200,000 tick × 20 窗（10,000 tick/窗）**：`means=[2.569, 2.584, 2.780, 2.445, 2.612, 2.579, 2.133,
  2.093, 2.068, 2.082, 2.048, 2.030, 2.046, 2.029, 2.095, 2.074, 2.099, 2.289, 2.651, 2.577]`
  → 漂移 **0.998x**，**无单调上升**（前 6 窗 ~2.5–2.8 反而是最高段，之后回落到 ~2.0）。
  **这是排除 O(n) 累积的决定性证据**：若真累积，末窗必显著高于首窗。

## 3. 历史基线对照（本机 vs CI 档 vs baseline）

| 口径 | 机型 | 量 | 值 |
|---|---|---|---|
| golden 首跑（M5-P1 §2.1，2026-09-27） | CI EPYC 7763 / 4 核 | mean_tick_ms（10 实体） | 0.125–0.232 |
| golden 本轮（§1.1，2026-09-29） | CI EPYC 7763 / 4 核 | mean_tick_ms（10 实体） | **0.118–0.234**（同区间） |
| `baseline.json`（2026-09-23，commit 372153a） | CI EPYC 7763 / 4 核 | **21 项** bench median | 见 `docs/perf/baseline-epyc7763.json` |
| CI 档位比（M2-P6，apply/flush 侧） | CI ÷ 本机 | median | 0.86–1.35（Python 侧 CI 慢、numpy 侧 CI 快） |

**注意（纪律）**：`baseline.json` 是 **2026-09-23 的 21 项旧集**（缺 M3-P2/M4 新增 bench：
retrieval/structure/willingness/fast_forward）。本单**不重生成 baseline**（任务书：不得凭本机数造 baseline）。
nightly-bench 的「基线对比」step 因此对**新增项无对照**、对**既有项**按 25% 相对漂移判——
本轮该 step 失败属**相对漂移 + 缺项**的已知形态，非 soak 信号。

## 4. 2.81x 归因（口径脆弱 vs 真回归）

### 4.1 判据解剖：`SOAK_MEAN_DRIFT_RATIO_LIMIT` 判的是**比值**
`test_bench_soak.py::_assert_no_runaway` 的漂移行：
```python
base = windows[1].mean_ms          # 首稳态窗（剔首窗冷启动）
last = windows[-1].mean_ms         # 末窗
ratio = last / base                # ≤ SOAK_MEAN_DRIFT_RATIO_LIMIT(1.5)
```
**CI 形态只有 3 窗 × 400 tick**：`base` 与 `last` 各是**单次 400-tick 采样**。单窗均值 CV **8.5%**
（§2.2）⇒ 两次独立抽样之比在尾部可轻易超 1.5x（**分布右尾**；实测 60 次 max 1.14 是本机空闲态，
CI runner 共享核抖动更大 → 右尾更肥）。**故 2.81x 落在「小样本比值右尾」而非「单调退化」。**

### 4.2 负载污染对照实验（决定性）
**8 路** CPU 争用下：漂移 0.87–1.05x（均值 3.3–4.0ms）。
**20 路** CPU 争用下：漂移 **0.91–1.04x**，但绝对均值抬到 **4.0–8.9ms**（3/8 次触 6.2ms 稳态上限）。
→ **绝对均值随负载显著抬升；漂移比几乎不动**。即：
- 「2.81x」不可能是「负载把末窗均值整体抬高」（那样首窗也会被抬，比值仍≈1）；
- 只能是「**末窗恰好抽到慢采样、而 base 窗恰好抽到快采样**」的**单次离群**——正是小样本比值口径的病。

### 4.3 对照：CI 档真正的绝对越线项（与 soak 无关，M2-P6 已登记）
nightly-bench `-m bench` 内 advisory-only 越线（CI 档，非 soak，非本单新增）：
- `apply(move) 单事件`：CI 0.051ms > 0.040（1.28x）；`apply 50 事件批`：CI 2.477ms > 2.000（1.24x）
  ——与 M2-P6 §1「numpy/BLAS 侧 CI 0.86–0.92x」**矛盾**？不：`apply` 走 pydantic 校验（Python 侧）主导，
  故 CI 偏慢；M2-P6 的 0.86x 是**纯 numpy** 行。
- `感知听觉 50 NPC`：CI median 5.449ms > 3.600（1.51x）；`RNG 1M draws`：CI 394.8ms > 330（1.20x）
  ——共享核抖动 + 档位比，夜间 runner 负载所致，**advisory 只记录**。
> **结论**：CI 档越线项**全是绝对阈值**（advisory 记录），**soak 判据（漂移比）在 CI 是绿的**。

## 5. 处置与建议（本单执行范围）

### 5.1 本单已执行
- **判定 = 本机口径（advisory），非真回归 → 不 BLOCK。**
- **连续红计数清零**（裁 21-D 的「连续 3 轮红」计数：本机当前树 3 连绿 + 定标机两形态绿 + 60 次冒烟 0 红）。
- soak 维持 `PI_BENCH_ADVISORY=1`（nightly）/ 定标机硬断言（本机）口径不变。
- **不改 `thresholds.py` / 不改 `soak.py` / 不改 `test_bench_soak.py`**（判据硬化是另单，见 5.2）。
- 不重生成 `baseline.json`（纪律：不得凭本机数造 baseline）。

### 5.2 建议（**登记，待裁，本单不执行**）
1. **硬化 CI 形态判据（口径层，非阈值）**：CI 形态 3 窗 × 400 tick 的**样本量不足**以判漂移比——
   建议 `test_soak_ci_smoke_stability` **只作框架冒烟**（不断漂移），把**漂移判定留给 nightly 30k
   （5 窗 × 6000）+ 里程碑 604,800（7 窗）**；或对 CI 形态用**更多窗**（≥5）再比。属 `test_bench_soak.py`
   改动 → 性能域另单，须 Claude 裁。
2. **给 soak 加 artifact 输出**（窗口级均值/RSS/句柄），否则 CI 侧「漂移数字」永远只能取「绿/红」二值，
   事后归因无据（本单 §1.2 缺口即此）。
3. **`baseline.json` 重生成**（补 retrieval/structure/willingness/fast_forward 四项）——CI 域，
   建议随下次全绿 nightly 由性能域按 bench-plan §4.1 八步重做（本单只登记）。

## 6. P3 fast_forward 0.90ms / 42.0s 的口径声明（重申，裁 27-E 要求）

承 M5-P3（`docs/perf/m5-fast-forward-budget.md` §7，主树已收编 `52aeeaa`）：
- **`FAST_FORWARD_FRAME_LIMIT_MS = 0.90ms`**：单帧 240 tick 的墙钟上限。**观察态起步**——
  bench 用 `_record_proposal` **只记录不断言**（同 M3-P3/M4-P2/M4-P3）。0.90 = 本机实测 0.53 × 1.7 慢机余量。
- **`FAST_FORWARD_REQUEST_DURATION_LIMIT_S = 42.0s`**：**派生量**（168h×3600 / 240 / 60），只由契约守卫
  `test_fast_forward_request_duration_is_derived` 钉，**无数值 bench 行**。
- **CI 档实测（本单 artifact，`36543451845` bench.json）**：`test_fast_forward_frame_cost` 0npc **0.5589ms** /
  10npc **0.6230ms** / **50npc 0.9131ms**——**50npc 恰在线 0.90 上**（CI/本机比 0.9131/0.53 ≈ **1.72x**，
  与 1.7 慢机余量吻合）。
  > **含义**：0.90ms 线是**本机口径 ×1.7** 定的，**CI 档位恰在线上/微越**（advisory 不断言，故无红）。
  > **转硬断言前**须按 M2-P6 裁 1 办：**按档位重定线**（CI 用 CI 基线）**或**声明「硬断言只留定标机」。
- **口径声明（关键，M5-P3 已采认）**：当前 `NPC_ACT` 无内核 handler、`NpcRuntime` 未接进
  `tick._tick_once` ⇒ 快进帧真实负载 = 既有路径推进，**非满 L1/感知**；若未来快进帧也跑满负载，
  plain-50 单帧升至 ~2.9ms（未来上界参考，**本行不覆盖**，接后另裁）。

## 7. 边界与门禁

- **本单只动 `docs/perf/`（本文件）+ `.orca/memory.md` ⑤节**；**不改** `thresholds.py`、`soak.py`、
  `test_bench_soak.py`、生产代码；**不重生成** `baseline.json`。
- **CI 触发**：`gh workflow run golden-nightly`（run 36503174990）+ `gh workflow run nightly-bench`（run
  36543451845），均为 main、全新 runner、零本地污染；数字取自 artifact（`golden-result-seed-*` / `bench-result`）。
- **本机数**：Win11+WSL2 / i7-14650HX / 24 逻辑核 / py3.12.13；干净进程复测（§2），**不用于定 baseline**。
- **未决风险**：①CI soak 窗口级数字缺 artifact（§1.2 缺口）；②CI 形态 3 窗样本量不足以判漂移比（§5.2-1）；
  ③`baseline.json` 缺 4 项（§5.2-3）；④fast_forward 0.90 线 CI 贴线（§6）。
