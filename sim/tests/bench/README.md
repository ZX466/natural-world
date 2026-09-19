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
| `test_bench_perception.py` | M1 感知传播：视觉分区剪枝（记录基线）/朴素 O(N²) 哨兵/听觉（≤3ms）+ 模型形状契约 |

## 阈值修订记录

- RNG 1M 逐调用聚合量纲实测 219ms（原 100ms 不可达且与每 tick 预算脱节）→
  回调为 300ms 警戒线，并新增「每 tick RNG 成本（L1 规模 200 draws ≤ 0.10ms）」
  作为真预算口径；详见 `thresholds.py` 头注与本树 `docs/perf/budget.md` §2.2。