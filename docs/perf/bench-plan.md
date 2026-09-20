# 基准测试方案（docs/perf/bench-plan.md）

> 依据：`DESIGN.md` §10/§16/§17 + 本树 `budget.md`。定义 M0 起哪些模块必须有 bench、用什么工具、回归阈值。

## 0. 与 CI 门禁的关系（§16）

- T1/T2/T3 一次性不变量 + 回放确定性是**每提交**的 CI 门槛（秒级）。
- **本条 bench 独立**：性能基准不进每提交红线（硬性机器抖动会把 CI 变红灯制造机），按 **nightly** 跑，对比基线存档；**关键回归线**（§3）可选择性进 CI（用相对上基线 ±% 判）。
- 确定性要求（C5）对 bench 同样适用：**所有 bench 用固定 seed**，跑在干净种子流上。

## 1. M0 必带 bench 清单（对齐 §17 M0 范围：地图/寻路/渲染/摄像机/RNG/时钟/apply）

| 模块 | 测什么 | 工具 | 量纲 |
|---|---|---|---|
| `core/clock` | tick 推进 + 昼夜/集市检查 | pytest-benchmark | ns/tick |
| `core/rng` | 多流确定性 RNG：1M draws 耗时；stream 间无串扰 | pytest-benchmark / timeit | ms/1M |
| `core/entropy` | `inject()` OS 熵 + reseed 日志写（高频？否，但最大值） | pytest-benchmark | ms/inject |
| `core/events` | `apply(event)` 单事件 p50/p99；批量 20/50/100 事件 | 真实内核 tick loop 计时 | ms/tick |
| `world/pathfinding` | A* 最坏：全图跨角 + 障碍密集；chunk 增量失效 | pytest-benchmark | ms/query |
| `persistence` | 批量 INSERT（WAL）：单事务 20/100 条；快照 5MB gzip 序列化 | 计时 harness | ms/batch |
| `perception`（M1 起） | 50 NPC 感知传播（视觉射线/听觉 1/r）全对 vs 分区后 | 计时 harness | ms/tick |
| **整个 tick loop** | 组合：clock+rng+apply+utility（L1）| **真实 tick loop 计时** | ms/tick，p99 |

**M0 的必测三件套**（任务指定）：`clock`、`rng`、`apply(event)`——这三个是 M0 里程碑（§17 M0：RNG/时钟/apply）且是确定性内核底座，C5/C4 的守卫。寻路与渲染从 M0 即有 bench，防止「地图大 → 每移动一下卡死」。

## 2. 工具选型

| 层 | 工具 | 用法 |
|---|---|---|
| 微基准 | `pytest-benchmark` | clock/rng/entropy/pathfinding 这类纯函数、可独立调用的单元 |
| 中/大基准 | 真实 tick loop 计时 harness | 直接驱动 `sim.core.tick()` 完整循环，`asyncio` 下测稳态吞吐与 p99；**不要**把微基准数字外推到系统级 |
| 统计与假随机 | `Hypothesis`（§4 已有） | 属性测试配固定 seed，保证 bench 输入分布稳定 |
| 报告 | pytest-benchmark `rounds`/`warmup` 参数 | 每次至少 3 轮取中位，防首轮 JIT/缓存热涨 |

**确定性**：bench 全部固定 `seed`，绝不用 `random.*`（C5）；每个测试 `--benchmark-disable` 时仍能当普通单测跑（不影响 CI 时长）。

## 3. 回归阈值（相对 budget.md §1 表）

| 指标 | 阈值 | 触发 | 动作 |
|---|---|---|---|
| tick p99（1x） | ≤ 8.3ms（预算 16.6ms 的 50%） | nightly | 超则告警 + 性能域接手定位 |
| tick p999 | ≤ 13ms | nightly | 抖动追踪（GC/快照/IO 峰值） |
| 各子系统占比 | clock+rng+apply+utility+perception+llm_sched ≤ 名义表 7.00ms 或 ≤ 上限表 12.35ms | nightly | 占比漂移 >20% 即查 |
| apply(event) 单事件 p99 | ≤ 0.04ms（50 事件 ≈ 2ms） | nightly | 超预算 §2.3 |
| L1 50 NPC utility | ≤ 6ms p99 | nightly（M2 起） | 破限先砍节拍再优化 |
| 感知传播 50 NPC（视觉/听觉） | 暖态 mean ≤ 3.6ms（红线，+20% 慢机余量；预算目标 3.00ms）。bench 已 `warmup_rounds=1` 剔除首轮 LOS 缓存冷启动（冷 7.6–8.2ms） | nightly | 超限查 LOS 缓存命中率/分区粒度；冷启动不计 |
| LLM 预取调度（M1） | ≤ 0.20ms/tick（触发门控+入队+二次校验） | nightly（M1 起） | 破限先查 L2 常驻 NPC 门控扫描 |
| RNG 每 tick 成本(200 draws, L1) | ≤ 0.10ms | nightly | 超限回退向量化批量抽取 |
| RNG 1M draws 聚合（警戒） | ≤ 300ms（先行实测 219ms） | nightly | 追查逐调用路径 |
| 快照 5MB gzip | ≤ 500ms 单次；≤ 0.5ms/tick 摊销 | nightly | 异步卸载失效检查 |
| WS 编码 增量 patch | ≤ 0.5ms/tick 编码 | nightly（M2 起） | 合并批次参数 |
| LLM 决策延迟 P95 | < 8000 ms（墙钟，独立看板） | 日汇总 | 见 docs/perf/llm-monitoring.md |
| LLM 单决策 tokens | < 2000 tok（sum 口径） | 日汇总 | 见 docs/perf/llm-monitoring.md |
| 4x / 16x | 各自 p99 ≤ 对应预算的一半（2.08ms / 0.52ms，L1 降采后口径） | nightly | 降采策略失效检查 |

**口径固定**：所有阈值绑定「机器档位」——记录 CPU 型号/核数/内存 + Python/uv 版本进基线头，跨机器对比按基线线性缩放，避免拿笔记本数据当服务器红线。

## 4. 执行节奏

- **每次提交附近**：仅 T1/T2/T3 + 单测（bench 关）。
- **每日 nightly**：全量 bench，出 `perf/<date>.json` 基线 + 对比昨日前瞻。
- **里程碑（M0/M1/M2）**：跑一次**正式基线**，黄金数字写进里程碑评审（对齐 §17 量化验收：决策延迟 P95<8s、单决策 <2k tok 属 LLM 侧，与 tick 侧分开呈现）。
- **回归处置**：谁改谁负责回退或证明阈值失效合理（性能域评审 + Claude（架构）复核）。

## 5. 具体 bench 用例示例（伪代码，非实现码）

```
# core/rng 确定性流
def test_rng_1m_draws(benchmark):
    rng = DeterministicRNG(seed=42)
    benchmark(lambda: [rng.next("walk") for _ in range(10**6)])

# core/events apply 批量
def test_apply_batch50(benchmark):
    world = build_test_world(seed=9)  # 固定 50 NPC 状态
    events = gen_events(50)
    benchmark(lambda: [world.apply(e) for e in events])

# 真实 tick loop（系统级，单独 harness）
def bench_tick_loop():
    world = make_world(seed=7, npc=50)
    loop = TickLoop(world, target_rate=60)   # 1x
    for _ in range(5): loop.step()
    with timer("tick_loop_p99") as t:
        while reproducible_1_game_minute(world): loop.step()
    assert t.p99_ms() <= 8.3
```

## 6. 已知不可测 / 待定项

- **LLM 延迟（P95<8s）与 tokens**：属异步外部依赖，bench 里**不做**（烧钱 + 抖动）。用 §15 监控（每次调用 log tokens/latency 到 structlog）单独建看板，与 tick 基准隔离。
- **Win 平台无 uvloop**（§4 硬约束）：asyncio 性能基准只能在标准事件循环上定阈值，不做 uvloop 对比假设。
- **4x/16x 降采节拍正确性**：由 T2 回放保证（同一 seed 不同倍率产出同一世界），bench 只测吞吐，不测语义。