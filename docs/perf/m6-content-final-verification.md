# M6-P8 内容面性能终验执行记录（Claude 域代执行，2026-10-05）

> 依据：M6-P8 派单 + pi P4 §6.2 清单 + P13 runbook 步骤 0 ·基线 main `b9eb875`。
> 内容面四模块已合入 `d1d287e`——本记录为 P4 §6.2「合入后待实测项」的实测回执。

## 0. 步骤 0 双探针（P5 新纪律：跑前+跑后）

| 时点 | throttle_ratio | throttled | 判定 |
| --- | --- | --- | --- |
| 跑前 | **1.536** | false | ≤2.0 健康，终验有效 |
| 跑后 | **1.342** | false | ≤2.0 健康（窗口稳定，非临界带） |

**结论：本轮终验读数可信**（双探针均健康簇；P6「单次读数不可信」由双点一致缓解）。

## 1. 三行 bench 终验（P4 §6.2 归属行）

| 模块 | 命令 | 结果 | 归属行 | 结论 |
| --- | --- | --- | --- | --- |
| 动物（感知面） | `pytest sim/tests/bench -k "perception or smell or utility"` | **25 passed** | `PERCEPTION 3.6`/`SMELL_WIRED 1.0`/`L1_UTILITY 6.0` | ✅ 零越界 |
| 生态/迷雾（apply 面） | `pytest sim/tests/bench/test_bench_apply.py` | **4 passed** | `APPLY_P99 0.04` | ✅ |
| 全量 not-bench | `pytest -q -m "not bench"` | **2347 passed / 121 skipped / 0 failed** | — | ✅ |

## 2. P4 红线终验

| 红线 | grep/实测 | 结论 |
| --- | --- | --- |
| **零新行**（`^ECOLOGY_/^FAUNA_/^SPEECH_/^FOG_` 于 thresholds.py） | **零命中** | ✅ PASS（出现新行=实现违规，未发生） |
| 生态「每 tick 全量扫」反例 | 到期桶形态（`ecology_phase_at` O(1) 每查询——**规模外推钉** `test_m6_content_mechanics.py` 远 tick 派生耗时无放大） | ✅ 全量扫形态未发生 |
| 动物零新通道（P13 红线） | 无动物专用 bench 通道（复用既有三行） | ✅ |
| 语言前缀缓存 | `messages[0]` 结构未动（speech 派生不进 prompt 装配——本波零投影，K4 判定） | ✅ |
| 迷雾脏 chunk 批处理 | 揭示不触发全表 invalidate（v0 无钩子——P4 判定维持，耦合须 `invalidate_dirty()` 的约束已登记） | ✅ |

## 3. 结论

内容面四模块性能终验**全过**：零新行、零越界、反例形态未发生。
三案（CHAOS/FIRE/MATERIALIZE）维持 advisory（重派判据=连续 3 次 ≤1.8，
本机当前 1.536/1.342 健康——**pi 观测序列若确认可即派定标**）。
