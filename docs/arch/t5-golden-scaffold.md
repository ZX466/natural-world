# T5 golden 脚手架提案（M4-C3 · 配置/文档域 = cline）

> 状态：**提案**（D 批行为链落地后按此填断言组）。纪律：本轮**不写断言组本体**。
> 依据：DESIGN §16 T5 行（10 种子 × 10 游戏日 · 断言宏观结果：守恒成立 / 差事完成率 / 无孤儿变更 · fixture 优先 · 每日）+ §10 时间锁定（1 tick = 1 游戏秒，1x = 60 tick/s）+ 裁 14-6（D 批担 T5）+ `m4-plan.md` §3 批次 D / §4 T4 口径。
> 引用纪律：本文每条都能追到代码/文档原文（EventKind 枚举、`run_world_driver`、`fixtures/errands.py`、`thresholds.py` 实测数）；追不到的进 §6 待裁，不写成结论。

## 0. 一句话形态

**虚拟时钟 + 有界帧驱动 + 录制 fixture 回放**：把生产驱动 `sim/api/ws.py::run_world_driver` 的帧序搬到测试侧，去掉真实时钟与无限循环，加上「10 种子 × 10 游戏日」确定矩阵；三断言组**只从驱动器吐出的 `GoldenRun` 取数**，不自己驱动世界。

## 1. 形态提案：与生产驱动的差异只有两处

| 维度 | 生产 `run_world_driver` | golden 驱动器（本轮已落 `driver.py`） | 为什么这样分 |
|---|---|---|---|
| 时钟 | 真实 dt（`asyncio.sleep` + `time.monotonic`） | **虚拟时钟**：固定 `frame_s=1/60` 直接推进 | 1 游戏日 = 24 真实分钟 → 10 游戏日 = 4 小时真实时间，不可进自动化验收 |
| 循环 | `while True` 常驻（WS 网关） | **有界**：跑满 `ticks` 即返回 | 测试需要终止条件与可断言的返回体 |
| 帧序 | `advance_frame` → `drain_delta` → `drain_events` → `on_flush` → `on_day_switch` → 广播 | **同序**，略去广播/落库（断言组要落库时自行挂 `on_events`） | golden 只关心事件与投影，不关心 WS 观察者 |
| 日切 | 跨越判定 `prev_day != new_day` 逐日回调 | 同口径（复用 `game_time(state.tick).day`） | 等值点判定在帧驱动下会整天丢失（实测丢 75–94%） |
| 喂给器 | 生产 LLM 决策缝（真 profile） | 录制 fixture 回放（`sim/tests/fixtures/*.py` 的 `scripted_reply`）+ soak feeder 造负载 | §16「fixture 优先」；真模型只进 T4/nightly（烧钱且抖动） |
| 确定性 | seed + 事件流可重放 | 同（C5：种子写死常量，不用 `random.*`/`time`） | golden 的可复现性是断言组的前提 |

## 2. 文件布局提案

```text
sim/tests/golden/
├─ __init__.py            # 【已落】包说明 + 纪律（断言组不在本包）
├─ seeds.py               # 【已落】10 种子写死清单 + TICKS_PER_SEED = 864,000
├─ driver.py              # 【已落】run_golden / DayWindow / GoldenRun + smoke_loop / mock_feeder
├─ test_golden_smoke.py   # 【已落】1 种子 × 1 游戏日冒烟（env 门 PI_GOLDEN_SMOKE=1）
├─ assertions/            # 【待 D 批】三断言组
│  ├─ conservation.py     #   物质总量不变式（§3.1）
│  ├─ errands_rate.py    #   差事完成率（§3.2）
│  └─ orphan_changes.py  #   投影 ↔ 事件源双向对账（§3.3）
└─ snapshots/             # 【待】期望快照：宏观指标基线 JSON（按种子分文件）
docs/arch/t5-golden-scaffold.md      # 本提案
.github/workflows/golden-nightly.yml # 【待】跑法落地（§4 案 A），断言组就位后再建
```

## 3. 三断言组可测化（**只给口径，不写断言**）

### 3.1 材料守恒（物质总量不变式）

可测化前提：**每个物质面都有事件源 + 投影落库**（§19：一切走 `apply(event)`，不得直赋值）。现有物质面（`sim/core/events.py` EventKind 枚举实证）：

| 面 | 事件源 | 投影 | 守恒写法（建议） |
|---|---|---|---|
| matter 存量 | `MATTER_BUILD` / `MATTER_DECAY` / `MATTER_DAMAGE` / `MATTER_COLLAPSE` | `matter_state`（opencode 投影缝；`materialize_matter` 快照路径） | 按 kind 分组 `Σ(matter_state)` ＝ 事件流重放折叠值，**逐位相等**（与 T2 回放同款口径，不用浮点容差） |
| 材料转移 | `MATERIAL_MOVED`（带 `quantity`） | structures 材料投影 | 转移守恒 `Σsource − Σdest = 0`；同事务回滚（裁 14 第 2 条⑦） |
| tile 变更 | `TILE_CHANGED` | `TileMap` 投影（M3 chunk 失效通路） | 投影 tile 集合 **⊆** 事件重放结果（差集为空） |
| 结构本体 | `STRUCTURE_STARTED/CHECKPOINT/COMPLETED/COLLAPSED/REMOVED` | structures 投影 | 同上「投影 ⊆ 事件」；`rubble` 是 tombstone（不删行，裁 14②） |

注意：M4 已把 `integrity/quality/decay_rate/is_rubble` 等**熵态列移出 structures**（m4-plan §6 第 2 条：熵态真相在事件流）→ 守恒只在 matter 面计，structures 面只做「投影 ⊆ 事件」。

### 3.2 差事完成率

- **素材已存在**：`sim/tests/fixtures/errands.py` 20 条脚本差事（`scripted_reply` 脚本化应答、`expected_actions`、`expected_keywords`）。
- **M1 口径**（`sim/tests/test_m1_metrics.py`）：全链路 20 条，**≥80%（16/20）过线**；另卡 P95 < 8s 与 prompt 预算。
- **golden 口径建议（待裁）**：10 日累计「可完成差事」分母 = 期间注入且未被阻塞的差事数；分子 = 过「装配 → 闸门 → 动作 ∈ expected → reason 含关键词」的次数。**阈值不在 golden 里写死**：或沿用 M1 的 80% 线，或按 10 日重定标——须 Claude 裁（§6-1）。
- **fixture 缺口（已识别，D 批任务）**：现 20 条是**单决策场景**；10 日长跑需要**多决策续接**的差事流（同一 NPC 连续多轮 / 计划跨日），否则完成率退化成 M1 的单轮口径，测不到「跨日计划是否完成」。

### 3.3 无孤儿变更

判据：**两个方向都要查**——有投影无事件源（孤儿投影）、有事件无投影（孤儿事件）。对账 SQL 骨架（`<projection>` 按面分表：map tiles / structures / matter_state；实表名待 opencode 投影定稿后替换）：

```sql
-- A. 孤儿投影：投影行记了 (last_event_kind, last_event_seq)，事件日志里找不到
SELECT p.kind, p.rowid
FROM <projection> p
LEFT JOIN events e
  ON e.kind = p.last_event_kind AND e.seq = p.last_event_seq
WHERE e.seq IS NULL;

-- B. 孤儿事件：事件已落，投影没有对应行
SELECT e.kind, e.seq, e.payload
FROM events e
LEFT JOIN <projection> p ON p.last_event_seq = e.seq
WHERE e.kind IN ('tile.changed', 'structure.started', 'structure.checkpoint',
                 'structure.completed', 'structure.collapsed', 'structure.removed',
                 'matter.build', 'matter.decay', 'matter.damage', 'matter.collapse',
                 'material.moved')
  AND p.rowid IS NULL;
```

**已知口径坑（必须写进断言，否则必假红）**：熵注入只进事件流、world state 不留痕（§11 + 裁 14-5）→ 方向 B **必须排除 `entropy_inject`**，否则每个熵事件都会被判成孤儿。

## 4. 跑法：两案 + 主张（**每提交 CI 不跑**，§16 T5 每日）

**runtime 实测（本轮实测 + 既有记录）**：

| 口径 | tick 成本 | 1 游戏日 | **10 游戏日 / 种子** | 10 种子串行 |
|---|---|---|---|---|
| 本轮冒烟口径（10 实体 + mock feeder，**实测 53.4s / 86,400 tick**） | 0.62 ms | 53 s | **≈ 8.9 min** | ≈ 1.5 h |
| soak 口径（50 NPC，`thresholds.py` 记录：mock ~1.9ms / l1 ~0.9ms） | 0.9–1.9 ms | 1.4–2.7 min | **≈ 13–27 min** | **≈ 2.2–4.5 h** |

量纲锚点：`TICKS_PER_GAME_DAY = 86,400`（1 tick = 1 游戏秒）→ 10 游戏日 = **864,000 tick / 种子**。

**案 A（主张）独立 `golden-nightly.yml` + 种子分片 matrix**
- 10 个种子 → `strategy.matrix`（每 job 1 种子，`timeout-minutes: 90`），artifact 归档每种子的 `GoldenRun` JSON + 机器档位（照 `nightly-bench.yml` 已有的「记录机器档位」步）。
- 优点：①种子间并行 → 墙钟 ≈ 单种子时长（13–27 min），不是 2.2–4.5 h 串行；②失败可定位到具体种子；③T5（fixture、免 secret）与 T4（真模型、锁版本、烧钱）**性质不同，不混一个 job**；④T4 的 `timeout-minutes: 30` 护栏不适配 T5 的 13–27 min/种子。
- 代价：多一个 workflow（我域成本低，`t4-nightly.yml` 可直接抄结构）。

**案 B 并入 `t4-nightly.yml` 同一 job**：省一个文件，但 T4 红灯会带倒 T5、矩阵并行要额外 `max-parallel` 编排、且两者的超时/secret 口径不同质 → **不主张**。

**每提交 CI**：T5 不跑。脚手架已用 env 门默认跳过（`PI_GOLDEN_SMOKE` 未置即 skip），**无需改 `ci.yml`**；`golden-nightly.yml` 等断言组就位后再建（不先建空跑 workflow）。

## 5. 本轮已落的最小可跑骨架（1 种子 × 1 游戏日）

- `sim/tests/golden/test_golden_smoke.py`：env 门 `PI_GOLDEN_SMOKE=1` + `GOLDEN_SMOKE_TICKS` 切片；**只断言 harness 自身**：跑满 tick 数、`state.tick` 对齐、事件流非空、逐日窗口可取数、`mean_tick_ms` 已记录——**不接三断言组**。
- 实测：满一日 `1 passed in 53.98s`（本机 10 实体口径）；秒级切片（3,600 tick）`1 passed in 0.55s`。
- 未置 env 时整文件 skip → 每提交 CI 秒过（§16「T5 每日跑」纪律落到代码层）。

## 6. 待裁 / 遗留

1. **三断言组的阈值与容差**：守恒容差（建议逐位相等、不给浮差）、完成率线（沿用 M1 80% 还是按 10 日重定标）、孤儿分级（硬红 vs 告警）——按纪律**不先写死**。
2. **种子清单**：`GOLDEN_SEEDS = (7, 11, 101, 1009, 2003, 3001, 4001, 5003, 6007, 7001)` 是否照此（**改种子 = 改验收口径**，须显式裁决）。
3. **差事 fixture 补「多决策续接」**：D 批任务（否则完成率退化为 M1 单轮口径）。
4. **投影表定稿**后把 §3.3 的 `<projection>` 换成实表名（opencode 域）。
5. **`golden-nightly.yml` 落地时机**：断言组就位后（不先建空跑）。
6. **耦合提示**：`driver.py` import 性能域 `sim/tests/bench/{harness,soak}.py`（**只读不改**）；若 pi 改签名需同步。备选：把共用 builder 上提到 `sim/tests/_builders.py`（提案，本轮未做——跨域重构须先请裁）。