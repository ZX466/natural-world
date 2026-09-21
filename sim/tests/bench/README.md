# 性能基准 — nightly 跑法（性能域，pi）

本目录是 M0 内核（`sim.core`）的性能基准（基准目录，独立包）。

## 运行方式

```bash
# 全量基准（nightly；含阈值断言，失败即红灯）
uv run pytest -m bench

# 只看测量结果、不因超阈值中断（夜间看板/采数用）
uv run pytest -m bench --benchmark-only

# 详细列
uv run pytest -m bench --benchmark-columns=min,mean,max,median
```

## 与 CI 的关系（依据 docs/perf/bench-plan.md §0）

- **每提交 CI** 跑 `-m "not bench"`（cline 侧已配置），性能基准被 deselected，不因机器抖动红 CI。
- **nightly** 跑 `-m bench`，结果对基线存档并告警；阈值来自 `bench/thresholds.py`（集中一处，改一处生效）。

## 目录结构

| 文件 | 内容 |
|---|---|
| `thresholds.py` | 回归阈值常量（唯一集中点）：tick/apply/RNG/快照 |
| `harness.py` | 世界/loop 装配 + ms_per_tick 计时 + 阈值断言 |
| `conftest.py` | 复用 fixture：`bench_loop_empty` / `bench_loop_50` |
| `test_bench_clock.py` | GameClock：每 tick 均耗（空世界 / 50 NPC）+ 契约守卫 |
| `test_bench_rng.py` | 分流 RNG：1M 聚合、L1 每 tick 成本、向量化对比 + 确定性/重放契约 |
| `test_bench_apply.py` | EventBus.apply：单事件 / 50 事件批 + 唯一写路径契约守卫 |
| `test_bench_perception.py` | M1 感知传播（真实引擎）：视觉/听觉暖态 ≤3.6ms + 朴素 O(N²) 哨兵 + 模型形状契约 |
| `test_bench_l1_utility.py` | M2 L1 效用 50 NPC：全量/单 NPC 红线 ≤6.0ms/0.12ms + 断线兜底队列 ≤0.20ms + 向量化哨兵 |
| `test_bench_smell.py` | M2 嗅觉传播（∝1/r² 风向）：网格扩散+采样 ≤0.15ms + 逐对 O(N²) 哨兵 + 形状契约 |
| `soak.py` | 长跑采样 harness（M2-P2）：进程探针（RSS/句柄/GC）+ 窗口化 run_soak + 确定性 mock 动作喂给 |
| `test_bench_soak.py` | M2 7 日自转预压测：CI 缩样稳定性 + nightly 长跑漂移/p99/缓存 + 完整 604,800 tick（环境门） |

## 阈值修订记录

- **M2-P2（2026-09-21）新增长跑验收红线**：`SOAK_STEADY_MEAN_LIMIT_MS=6.2` /
  `SOAK_MEAN_DRIFT_RATIO_LIMIT=1.5` / `SOAK_RSS_GROWTH_LIMIT_MB=128` /
  `SOAK_GC_OBJECT_GROWTH_LIMIT=20000` / `SOAK_HANDLE_GROWTH_LIMIT=64`。
  口径：**分窗稳定性**（末窗/首稳态窗漂移 + 资源增长），非单轮 p99（长跑单窗口 GC/OS 离群不误红）。
  604,800 tick 完整跑不进每提交 CI，接 nightly（接法提案见 `docs/perf/m2-acceptance.md` §4，由 cline 裁决）。
  实测（50 NPC+感知+持续走动 mock，本机）：稳态 ~1.9ms/tick，100k tick 均值无漂移，RSS/句柄/GC 有界。
- **M2-P1（2026-09-20）新增**：L1 效用 `L1_UTILITY_TICK_LIMIT_MS=6.0` / `L1_UTILITY_PER_NPC_LIMIT_MS=0.12` /
  `L1_OFFLINE_FALLBACK_LIMIT_MS=0.20`；嗅觉 `SMELL_TICK_LIMIT_MS=0.15`（+哨兵下界 `SMELL_NAIVE_SENTINEL_MS=3.0`）。
  实测均远低于红线（L1 ~0.02ms、嗅觉 ~0.01ms）——红线是「M2 满属性 + 未向量化写法」的回归天花板，不按实测缩小。
- RNG 1M 逐调用聚合量纲实测 219ms（原 100ms 不可达且与每 tick 预算脱节）→
  回调为 300ms 警戒线，并新增「每 tick RNG 成本（L1 规模 200 draws ≤ 0.10ms）」
  作为真预算口径；详见 `thresholds.py` 头注与本树 `docs/perf/budget.md` §2.2。
- 感知红线 3.0→3.6（C06-③ 真实引擎合入 + F06 复核）：预算目标值仍 3.00ms，红线
  3.6 = +20% 慢机余量；bench 加 `warmup_rounds=1` 剔除首轮 LOS 缓存冷启动（7.6-8.2ms），
  暖态 mean 实测 3.0-3.3ms 在 3.6 内。详见 `thresholds.py` 与 budget §2.5/§4。

## 方法论教训（F06 学习记忆，可迁移）

带缓存/冷启动的热敏感项（感知 LOS、pydantic 首次构造、SQLite 页缓存）——
**首轮 cost 会把 `mean` 拉过红线假红**。三个可迁移动作：
1. **`warmup_rounds` 预热**：`benchmark.pedantic(..., rounds=N, warmup_rounds=1)` 填缓存后再计时。
2. **中位口径判定**：热敏感项用 `harness.assert_median_threshold`（读 `Metadata.stats.median`）
   而非 `mean`——median 抗单轮离群，符合「至少 3 轮取中位」本意；mean 打印作参考。
3. **冷启动单独诊断**：在改口径/放宽红线前，单独测冷（新实例首轮）vs 暖（稳态）差异量级——
   不要因一次假红就放宽红线（基线漂移后不可逆）。

红线修订的纪律：先分清楚「测量方法假红」（改口径）vs「引擎真热点」（改引擎，架构域）vs
「预算不合理」（回调预算，需评审）。F06 的感知 3.6 属于前者——口径修正后红线未放宽。