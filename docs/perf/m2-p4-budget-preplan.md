# M2-P4 第三批预算预案（smell 接线 / flush 落库 / cognition 骨架）
> 性能域（pi）对账 main `19de630`（M2-A2 第三批：smell 接线感知步 / NpcRuntime 接
> NpcStore.flush_tick / cognition 六偏差骨架）。本文件给预算表拆分、异步口径断言方案
> 与 cognition 预算上界建议；**阈值真相源仍为 `sim/tests/bench/thresholds.py`**。
> 实测环境：本机（WSL 侧 uv 运行 Windows Python），2026-09-22，暖态中位口径
> （`perf_counter` 多轮取中位；与 bench 的 `warmup_rounds=1` 同精神）。
> 不动 sim 代码：本文件只作预算预案与测试方案，落地实现的两处优化建议
> （inject 向量化、others_max 预聚合）已标注「架构域改动，交 Claude 裁决」。

## 0. 结论速览（三项任务书要点逐一回答）

| # | 问题 | 结论 |
|---|---|---|
| 1 | smell 接线后 0.15ms 红线是否上浮 | **维持 0.15 不浮**，但**拆表**：把「场推进」与「接线增量」分成两行，各自独立红线；场推进实测 0.45ms > 0.15 → 红线按 1.0ms（见 §1.3），不是上浮旧行而是**补新行**（原 0.15 是纯网格口径，接线后源数从 K=20 变全体实体 50） |
| 2 | flush_tick 不进 tick 的断言方式 | 契约测试三件套（见 §2）：**计时器注入 + await 分发点审计 + 挂钟/帧预算对比**；不需要 bench，属「防隐性进 tick」回归守护 |
| 3 | cognition 骨架预算上界建议 | 检索缝两偏差 0.15ms/检索、效用缝四偏差 0.01ms/NPC/tick；**总增量 ≤0.20ms/tick @50 NPC**（进 L1 行不新增行，见 §3） |

## 1. smell 接线预算表（wire-in decomposition）

### 1.1 接线后的真实调用链
`run_perception_step`（每 2 tick 一次，`tick.py::_PERCEPTION_EVERY_N_TICKS=2`）固定序：
1. `_shared_engine` / `_shared_smell_world`（`id(tile_map)` 查表，命中即 O(1)）；
2. `_wind_for_tick(tick, world_seed)` —— **档位缓存**（`_WIND_CACHE` 键=(day,phase)+seed），
   档内零重算；冷键一次 `wind_at` + `RngRegistry` 构造；
3. `SmellWorld.step({全体实体: pos}, wind)` = `smell_propagate`（inject → advect →
   diffuse 8 邻域 → decay）+ `smell_sample_batch`；
4. 每 observer `engine.assemble(...)` 里嗅觉段：`others_max` 逐 observer 扫描 → 单条观测。

### 1.2 分量实测（64×64、wind=(0,1)、diffuse_rate=0.10、decay=0.98、暖态中位）

| 分量 | 20 源 | 50 源（=全体实体） | 100 源（上界） | 走势 |
|---|---|---|---|---|
| A inject（copy + 逐源 `np.clip` 累加） | 0.145ms | **0.330ms** | 0.717ms | ~7µs/源，Python 循环主导 |
| B advect `np.roll`（1 次全图） | 0.005 | 0.004 | 0.006 | O(grid²) 常数，与源数无关 |
| C diffuse 8 邻域（8 roll + 代数） | 0.061 | 0.056 | 0.098 | O(grid²) 常数 |
| D decay 乘系数 | 0.001 | 0.001 | 0.003 | 常数 |
| E `smell_sample_batch` | 0.009 | 0.011 | 0.044 | O(N_recv) |
| **场推进合计**（A+B+C+D+E） | **0.220ms** | **0.451ms** | **0.976ms** | inject 主导 |
| 接线增量：`others_max` 逐 observer 扫描 | — | 0.107ms | — | O(N_obs×N_src)，dict 扫描 |
| 接线增量：`_wind_for_tick` 冷键一次 | — | 0.018ms | — | 档内均摊 ≈ 0 |
| 感知步总量（视听 + smell，50 NPC，对照） | — | 1.513ms | — | 挖空 smell.step 后 0.854ms（组件单独一轮 1.58 vs 0.90，见 §1.3） |
| **→ smell 净增（含摊销，见下）** | — | **0.68ms/感知步** | — | 每 2 tick 一次 → **≈0.34ms/tick** |

### 1.3 预算表拆分（budget.md §2.9 补写口径）

| 行 | 名义 (ms) | 上限/红线 (ms) | 实测（50 源·暖态中位） | 判定 |
|---|---|---|---|---|
| 嗅觉传播（纯网格口径，M2-P1 原行） | 0.05 | 0.15 | ~0.01（K=20 活跃物质源，M3+ 语义） | 维持不变 |
| **嗅觉场推进（接线版，源=全体实体）** | 0.25 | **1.00** | 0.451（50 源）/ 0.976（100 源） | **新增行，红线不放 0.15** |
| 嗅觉接线增量（others_max + 风派生摊销） | 0.05 | 0.20 | ≈0.16ms/感知步 = 0.107（others_max）+ 0.018（风冷键）+ 组装 | 含在场推进行/感知行内 |

**净增二次核对**（同进程对照，挖空 `SmellWorld.step` 后其余不变）：含 smell
1.58ms vs 0.90ms → 净增 **0.68ms/感知步**（= 0.451 场推进 + 0.107 others_max +
0.018 风冷键 + dict 组装余量），与分量加总一致。

**对每 tick 合计的影响**（每 2 tick 一次感知步）：
- smell 净增 0.68ms/感知步 → **≈0.34ms/tick**；视听自身 0.90ms/步 → 0.45ms/tick。
- M2-P2 长跑实测 50 NPC 稳态 ~1.9ms/tick（含旧感知步不含 smell 接线）；加本项 ≈ 2.25ms/tick，
  **仍 ≪ 8.3ms 回归线**（余量 ~3.8x），1x 预算 16.6ms 无压力；4x 档（4.16ms）需把
  「感知每 2 tick」继续维持（smell 随感知步同节拍，天然不额外加压）。
- **提案裁决点**（交 Claude）：
  1. budget.md §1 表增一行「嗅觉场推进（接线版）」0.25/1.00，§2.9 补接线口径段；
  2. `thresholds.py` 新增 `SMELL_WIRED_TICK_LIMIT_MS = 1.0`（含 100 源余量 + 慢机余量），
     旧 `SMELL_TICK_LIMIT_MS=0.15` **保留**并改注释为「纯网格参考口径（K=20 物质源）」；
  3. bench 增两个用例（见 §1.5），口径=暖态中位，跑在 `SmellWorld.step` 真实实现上
     （不再是参考实现 `_SmellField`——原 bench 还停在 M2-P1 的参考实现）。

### 1.4 给架构域的两个优化点（实测支撑，均为 O(N)→O(1)/向量化，**不动语义**）
1. **`SmellField.inject` 的逐源 `np.clip` Python 循环是全场最大头**（50 源 0.330ms，
   占场推进 73%）。`np.add.at(out, (ys, xs), 1.0)` 实测 0.0024ms（**~140x**），
   且同格累加语义与现状逐字节等价（fancy `out[ys,xs]+=` 会丢同格累加，禁用）。
   clamp 可由调用方保证后省去（或在 ys/xs 上一次性 `np.clip`，0.002ms 内）。
   → 落地后场推进 50 源预计 ~0.12ms，100 源 ~0.65ms，1.00ms 红线余量回到 ~8x。
2. **`others_max` 逐 observer 全表扫描 O(N²)**（50×50 = 0.107ms）。可在
   `run_perception_step` 里一次算出 `others_max_all = max(concentrations.values())` 与
   次大值；observer 自己不是最大时直接用全局 max（O(1)），是最大时才扫一次。
   注意语义等价性：现状排除自己 → 需保留「自己恰为最大值」的次大分支，**建议由
   Claude/架构域裁决后改**（性能域不越界改引擎）。

### 1.5 建议的 bench 用例（`sim/tests/bench/test_bench_smell.py` 增补）
```python
@pytest.mark.bench
def test_smell_world_step_50_entities(benchmark) -> None:
    """SmellWorld.step（源=全体 50 实体，风+8 扩散+衰减+采样）≤ 1.0ms（暖态中位）。"""

@pytest.mark.bench
def test_smell_world_step_100_sources_headroom(benchmark) -> None:
    """100 源上界探测（L0 千人降采样前的余量哨兵；软断言/日志，不进硬门禁）。"""
```
- 口径：`benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=200)` +
  `assert_median_threshold`；与既有 smell/感知红线同源（`warmup_rounds=1` 剔冷启动）。
- 单测/契约侧另加（非 bench）：`test_m2_smell_wiring.py` 已有场推进+去重+零元信息；
  建议补「风档内两次 step 的位移一致」（`_WIND_CACHE` 命中口径），防缓存键漂移。

## 2. flush_tick 异步成本口径（不进 tick 的断言方案）

### 2.1 当前链路事实（代码核对）
- `TickLoop` 内**没有任何 I/O/await**：`_tick_once` = 移动 → 感知钩子 → tick 自增；
  `drain_events()` 只把 `pending_events` 列表交出，**不落库**。
- 落库在外层 `sim/api/ws.py::run_world_driver`：`advance_frame(real_dt)` → `drain_delta()`
  → `drain_events()` → `await on_flush(events)`（`main.py` 里 = `flush_events(store, ...)`；
  M2-A2 第三批后 runtime 侧的 `NpcStore.flush_tick` 是同一缝隙的另一调用方，签名不同但
  都在 driver 帧内 await，**不在 `advance_frame` 内**）。
- `SqlEventStore.append` 单事务：`SELECT max(seq)` → N×`session.add` → 投影回调 →
  `commit`；`NpcStore.flush_tick` = `flush_rows`（纯 CPU 序列化）+ `append(projection=...)`。
- 实测（内存 SQLite，50 条 NPC_ACT 批次）：flush_tick 中位 **~2.6ms**；文件库 **~7.8ms**。
  → 若一旦误进 tick，60 tick/s 下每次 7.8ms 直接吃掉半个帧预算，且会与 wal/锁耦合。

### 2.2 断言三件套（防「flush 隐性进 tick」回归）
写入 `sim/tests/bench/`（**测试方案，本次只给设计；实现交 Claude/架构域或我下一轮落地**）：

1. **await 分发点审计（结构断言，零抖动，每提交可跑）**：
   静态/运行期双重。运行期版：给 store 装一个 `flush 探针`（记录被调用的调用栈深度 +
   是否在 `asyncio` 事件循环的某任务里），断言 `TickLoop._tick_once` 的调用栈中**不出现**
   `flush_events` / `NpcStore.flush_tick` / `session.commit`。实现：monkeypatch
   `sim.core.flush.flush_events` 与 `NpcStore.flush_tick`，调 `advance_frame` 若干帧，
   断言探针 **0 次**触发；再直接调 `drain_events` + `await flush_events` 断言能触发
   （防止测试自己失灵）。
2. **tick 内部计时不含 flush（计时器注入）**：用与 soak 相同的窗化计时口径，跑
   `advance_frame` N 帧取每 tick 中位；把同一 loop 接上一个「每次调用 sleep(5ms) 的假
   flush」后再跑一遍，断言两版每 tick 中位差 < 0.5ms（sloppy 上界，防回归不挑刺）。
   这一条防的是「有人把 flush 搬进 `_tick_once`」这类结构退化。
3. **帧预算对比（墙钟口径）**：`run_world_driver` 循环里测「advance+drain 段」与
   「flush 段」两段墙钟分开累计，断言 flush 段不得计入 tick p99 统计（进观测字段
   `perf.flush_ms` 单独看）。nightly 汇总时若出现 `tick_ms` 与 `flush_ms` 同增，
   按「耦合回归」告警（budget.md §5 的字段清单已有时钟/各子系统，补一行 flush 即用）。

### 2.3 预算口径落 doc
- budget.md §2.3/§5 已声明「事件先入内存队列，SQLite 落盘批量」；补一句
  「**落库在 asyncio 帧循环（`run_world_driver`）内 await，不进 `advance_frame`；
  断言方式 = 探针零触发 + 计时器注入 + 分开累计，见 bench/test_bench_flush.py（方案）**」。
- 落库本身不设每 tick 预算（帧级异步），设**帧级警戒 20ms**（60fps 帧预算 16.6ms 的
  同源量级）：nightly 若 flush 段 p99 > 20ms/flush 告警（WAL + 批量 INSERT 足够便宜，
  超出通常是同步 fsync 或投影退化成逐事件查询）。
- flush 监管字段建议 `perf.flush_ms` / `perf.flush_batch_n`（进 structlog，budget.md §5）。

## 3. cognition 骨架成本预估（六偏差纯函数层）

### 3.1 已落地的两检索缝（`sim/agent/cognition.py`）
- 挂法：`CognitionParams(beliefs=...).retrieval_scorers()` → 两个 `Scorer(mode="mul")`
  注册进 `memory.retrieve(..., scorers=...)`（`sim/npc/memory.py` 的既有钩子缝）。
- 实测（64 候选条目、`top_k=8`、双钩子）：`retrieve` **0.128ms**；无 scorer 基线
  0.074ms → **两钩子净增 ~0.054ms/次检索**（每钩子 ~0.027ms；Python 闭包 + 子串扫描）。
- 检索频次口径：检索发生在 L2 LLM 决策装 prompt 时（DESIGN §8），**不是每 tick 每 NPC**；
  按 M2 稳态近似「L2 常驻少数 NPC + L1 断线兜底低频」估 ≤10 次/tick → 悲观 1.3ms/tick
  的墙钟量级，但它是**装配 prompt 的同步段**、发生在 LLM 预取调度内（budget §2.8 的
  LLM_SCHED 行），不占 L1 行。

### 3.2 未落地的四效用缝（`sunk_cost_bonus` / `habit_bonus` /
`trauma_avoidance_penalty` / `drunkenness_factor`，均纯函数）
- 单次实测各 ~0.0001ms；四项串联（M3 每 NPC 每 tick 预期调用形）**0.0004ms/NPC/tick**。
- 50 NPC 全量 = **0.02ms/tick** —— 相比如今 `NpcRuntime.tick` 实测 0.747ms 增量 ~2.7%。
- `HiddenState.evaluate`（runtime 第 0 步，50 NPC × 3 隐藏属性）实测 0.831−0.731 =
  **0.10ms/tick**（含上下文子串扫描；空上下文 0.001ms）。

### 3.3 预算上界建议（供 Claude 实现时对齐）
| 项 | 建议上界 | 依据 | 归属行 |
|---|---|---|---|
| 检索缝两偏差 | 0.15ms/次检索（50 候选） | 实测 0.054 + ~3x 慢机/更长条目余量 | LLM_SCHED_TICK_LIMIT_MS=0.20 内（prompt 装配段） |
| 效用缝四偏差 | 0.01ms/NPC/tick（=0.5ms/50 NPC） | 实测 0.0004 + ~20x 余量（M3 真接 A* 前不会超） | L1 行（`L1_UTILITY_TICK_LIMIT_MS=6.0` 远未触） |
| HiddenState.evaluate（第 0 步） | 0.30ms/tick @50 NPC×3 属性 | 实测 0.10 + 3x；属性数涨先砍扫描时机（事件驱动） | L1 行 |
| **cognition 合计增量** | **≤0.20ms/tick（L1 行内）+ ≤0.15ms/次检索（LLM 行内）** | 上表加总 | 不新增 tick 行 |

**给架构域的提醒**（不是红线，是防呆）：
- 检索缝若被改成「每 tick 每 NPC 全量检索」（而非决策驱动），10×50×0.054 ≈ 27ms/tick
  → **破 16.6ms 预算**。M3 接行为能力时检索频次必须维持「决策/装 prompt 驱动」。
- `habit_bonus` 里 `import math` 在函数体内（现状）：单次 0.0001ms 无感，但热路径建议
  提模块级（性能域仅提示，不动代码）。

## 4. 我阈值的改动清单（交 Claude 收编裁决）
### 4.0 已落地（M2-P5，2026-09-22，commit on ZX466/pi）
1. ~~`thresholds.py` 新增 `SMELL_WIRED_TICK_LIMIT_MS = 1.0`~~ **已落**；`SMELL_TICK_LIMIT_MS = 0.15` 保留、注释改「纯网格参考口径（K=20 物质源，M3+ 语义）」——两口径并存勿混用。
2. `test_bench_smell.py` 两个接线版 bench 用例已落（`test_smell_world_step_50_entities`
   硬红线 1.0ms / `test_smell_world_step_100_sources_headroom` 100 源上界哨兵）+
   非 bench 摊销契约（每 tick 摊销 ≤ 红线/2，对应感知每 2 tick 一次）。
   复测口径（inject 向量化 main `653d395` 后）：50 源 0.116 / 100 源 0.135 /
   200 源 0.151 / 500 源 0.335ms（暖态中位）—— 原 P4 的 0.451ms 数据已被向量化
   淘汰，红线 1.0ms 按原提案值保留（覆盖 ~10x L1 上界）。
### 4.1 仍未落地（等裁决/等 M3 接线时引用）
1. `thresholds.py` 注释性常量（不进断言，供架构域对齐）：
   `COGNITION_SEAM_PER_RETRIEVAL_LIMIT_MS = 0.15` /
   `COGNITION_UTILITY_SEAM_PER_NPC_LIMIT_MS = 0.01` /
   `HIDDEN_EVALUATE_TICK_LIMIT_MS = 0.30`。
2. `docs/perf/budget.md`：§1 表增行 + §2.9 补「接线口径」段 + §2.3/§5 补 flush 异步断言。
3. `docs/perf/bench-plan.md`：§3 阈值表增两行 smell 接线红线 + flush 帧级警戒 20ms。
4. `SMELL_WIRED_TICK_LIMIT_MS` 的机器缩放系数（nightly 数据回流后，见 talking.txt ②）。
