# M2-P6②：CI 档位基线定标提案（EPYC 9V74 / 4 核 vs 本机）
> 性能域（pi），2026-09-23。数据源：nightly run **35816437844** artifact
> （`perf/bench.json` 38,597B + `docs/perf/runner.txt`）对照本机同 commit 全量 bench
> （`-m bench` 31 passed/1 skipped）。本文件只出**数据与提案**，不动 thresholds 正文
> （裁 1 已定：硬断言只留定标机；本文件给的是 baseline.json 的取值依据）。

## 0. 两档机器
| 档位 | 机型 | nproc | Python | 说明 |
|---|---|---|---|---|
| 本机（定标机） | Win11 + WSL2 转发 | — | 3.12.13 | 硬断言跑这里（advisory 缺省 off） |
| CI（nightly） | AMD EPYC 9V74 80-Core（共享切片） | 4 | 3.12.3 | `PI_BENCH_ADVISORY=1`；同机同核同时段被其他 job 抢 |

## 1. 档位比（CI median ÷ 本机 median，同一 commit 同 seed）
| 项 | CI (ms) | 本机 (ms) | CI/本机 | 判读 |
|---|---|---|---|---|
| 视觉分区 50 NPC | 1.9945 | 1.6206 | **1.23** | 重负载稳定复现 |
| `NpcRuntime.tick` 50 NPC | 0.9296 | 0.7699 | **1.21** | 含 Python 侧大头 → 稳定复现 |
| `evaluate_batch` | 0.3374 | 0.2921 | 1.16 | |
| `utility_scores_matrix` | 0.2529 | 0.2234 | 1.13 | |
| 时钟 50 NPC/tick | 2.1858 | 1.6238 | 1.35 | |
| RNG 每 tick（L1 200 draws） | 0.0513 | 0.0458 | 1.12 | |
| apply 50 事件批 | 1.5936 | 1.7876 | **0.89** | CI 更快（numpy/BLAS 路径） |
| apply 单事件 | 1.6236 | 1.8860 | **0.86** | 同上 |
| L1 断线兜底队列 | 0.0008 | 0.0006 | 1.51 | 亚毫秒项，比率噪声大（ICMN 级） |
| 嗅觉扩散（K=20 参考实现） | 0.0101 | 0.0092 | 1.10 | |

**稳定档结论（长负载、未越线、非亚毫秒项 8 个）**：CI/本机 比值
**median 1.14，区间 0.86–1.35**。分两类：
- **Python 解释器侧主导**（L1/感知帧装配/时钟）：CI 慢 **1.13–1.35x**（共享核 + WSL2
  虚拟化开销方向一致）；
- **numpy/BLAS 侧主导**（apply/flush_rows/向量化 RNG）：CI **0.86–0.92x**（本机 WSL2
  走 Linux 原生库，反更快）。

## 2. 越线项复核（run 35816437844 唯一红项）
| 红项 | CI median | 红线 | 超幅 | 复查 |
|---|---|---|---|---|
| 感知听觉 50 NPC | 3.9319 | 3.60 | **+9.2%** | CI/本机 = 1.24（落在稳定档区间内，非异常），但同 run **mean 11.546ms = median 2.9x** → 单轮被邻居 job 抢断；**中位口径已如实反映负载噪声** |
| smell 哨兵（上轮 run 35816176126） | 2.939 | 3.0 | +2% | 临界抖动；本轮 0.0101（0.07x 红线）无问题 |

→ 与 cline 5 轮取证结论一致：**失败集合轮换 + 均边缘 2–9% + mean/median 2.9–4x**，
是共享 runner 负载噪声，不是代码回归。裁 1 的 advisory 门已消除其红灯效应。

## 3. 提案（报 Claude 裁决；本次不动 thresholds）

**P-A（主提案）**：建 `docs/perf/baseline.json`（pytest-benchmark 的
`--benchmark-json` 产物可直接当基线），头部带机器档位，nightly「基线对比」step 改用
`--benchmark-compare=docs/perf/baseline.json --benchmark-compare-fail=median:25%`：
- 25% 而非 20%：CI 档位比稳定档 median 1.14 且有单轮 2.9x 的负载离群；25% 覆盖
  「1.24 档位差 + 少量抖动」而不误红。
- 建立时机：等 advisory 门（P6①）合入 + 首个 **advisory=1 全绿 run** 的 JSON，
  由 pi 审阅后提交入库（同 C4/C5 既有约定）。
- 入库时把 runner.txt 的 5 字段抄进 baseline 头（date/runner/nproc/cpu/python/uv）。

**P-B（备选，若不愿维护第二文件）**：nightly 不做任何红/绿判定，只归档 + 用
`perf.flush_ms` 之外的观测字段出「相对上次 run 漂移摘要」进 artifact；回归完全靠
定标机硬断言。成本低但 nightly 提前预警能力弱。

**共同前提**：`thresholds.py` 保持定标机口径**不放宽**（CI 慢 1.14x 也不把 3.6 改成
4.5——那是放红线自缩防线）。CI 的回归检出交给**相对基线漂移**（bench-plan §0 原意），
不与绝对阈值混用。

## 4. 不需要做的事（显式记录，防返工）
- ❌ 不给 CI 单独缩放 thresholds（两条真相源必漂移，历史教训：codex S03 假门禁）。
- ❌ 不用 mean 判 CI（本 run 已证 mean 被抢断放大 2.9x）。
- ❌ 不把感知红线 3.6 → 4.5（CI 中位 3.93 是负载噪声非真实退化；本机暖态 3.17ms）。
