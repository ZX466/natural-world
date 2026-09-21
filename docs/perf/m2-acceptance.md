# M2 验收口径 — 50 NPC × 7 游戏日自转无崩溃（M2-P2，性能域）

> 依据：DESIGN §10（1 tick = 1 游戏秒）/ §13（LOD、50 NPC 规模）/ §16（测试分级）/ §17（M2 量化验收）。
> 关联：`docs/perf/budget.md` §1.2/§2.4/§2.9（M2 预算）、`docs/perf/bench-plan.md` §3（回归阈值）、
> `sim/tests/bench/soak.py`（长跑采样 harness）、`sim/tests/bench/test_bench_soak.py`（预压测用例）。
> 架构接缝：`docs/arch/m2-npc-cognition.md` §6/§7（实施顺序第 8 步「7 日自转验收脚本」归性能域口径 + cline CI 接法）。

---

## 0. 验收目标与量纲

| 项 | 值 | 来源 |
|---|---|---|
| 1 tick | 1 游戏秒 | DESIGN §10 |
| 1 游戏日 | 86,400 tick | `sim/core/calendar.py::TICKS_PER_GAME_DAY` |
| 验收跨度 | 7 游戏日 = **604,800 tick** | DESIGN §17 M2 |
| 规模 | 50 NPC（L1 效用档常驻） | DESIGN §13 |
| 验收标准 | **自转无崩溃** + T1 信息边界 10k 采样通过（后者归 codex S 域） | DESIGN §17 |

「无崩溃」在性能域拆为四条可测判据（§2）：进程存活 / 资源不无界增长 / 状态不漂移 / 耗时稳态。

---

## 1. 为什么完整跑不进每提交 CI

- 1x 实时 = 60 tick/s ⇒ 604,800 tick = **10,080 真实秒 ≈ 2.8 真实小时**。逐提交 CI 不可接受。
- 加速（headless，不喂真实 dt、不 sleep、不广播 WS）实测内核 ~1.9ms/tick ⇒ 完整跑仍需
  **~20 分钟**（本机；CI runner 更慢）。仍超 cline 在 `ci.yml` M2 步骤设的 `timeout-minutes: 15` 护栏
  ——该护栏是刻意的，见 ci.yml 步骤注释。
- 结论：完整跑 **不属于每提交 CI**，走 nightly / 里程碑；每提交只跑**降采样断言**（§3）。

---

## 2. 崩溃判定与资源稳定性判据

长跑 harness（`soak.run_soak`）按窗口（默认每 1,000~10,000 tick）采样以下量；判据分窗（抗单窗 GC/OS 抖动）：

| # | 判据 | 观测 | 崩溃/失败判定 |
|---|---|---|---|
| C1 | 进程存活 | 长跑无未捕获异常 | 任一 tick 抛异常 = 崩溃（测试即红） |
| C2 | tick 不丢 | `state.tick` 终值 == 投入帧数（1x 每帧 1 tick） | 丢 tick = 时钟/封顶逻辑错（`_MAX_TICKS_PER_FRAME` 误伤） |
| C3 | 内存有界 | 末窗 RSS − 首窗 RSS（`SOAK_RSS_GROWTH_LIMIT_MB`） | 超限 = 泄漏；探测不可用（-1）则跳过，不误红 |
| C4 | GC 对象有界 | 末窗 − 首窗 `gc.get_objects()` 计数（`SOAK_GC_OBJECT_GROWTH_LIMIT`） | 超限 = Python 对象泄漏 |
| C5 | 句柄有界 | 末窗 − 首窗进程句柄数（`SOAK_HANDLE_GROWTH_LIMIT`；Windows 有效） | 超限 = 句柄泄漏（连接/文件未关） |
| C6 | 缓存有界 | LOS/walls/rtoken/sound_desc 缓存尺寸 | 无界增长 = 缓存未封顶（LOS 应 ≤ `_LOS_CACHE_MAX=65536`） |
| C7 | 实体稳定 | 终值 == 初值（50） | 漂移 = 实体被误删/重复物化 |
| C8 | 耗时稳态 | 末窗均值 / 首稳态窗均值（`SOAK_MEAN_DRIFT_RATIO_LIMIT`） | 超比 = O(n) 累积（单调变慢） |
| C9 | 确定性 | 同 seed 两轮 `state_hash()` 逐位一致 | 不一致 = C5 确定性破（回放必错） |
| C10 | 延迟红线 | 稳态窗口 p99 ≤ `TICK_P99_LIMIT_MS`（8.3ms） | 超限 = 性能回归 |

**首窗＝冷启动**：LOS/walls 缓存填充导致首窗均值偏高（一次性）。漂移基线取**第 2 窗**，不拿首窗比。

**为什么不用单轮 p99 作主判据**：长跑里单窗口离群来自 GC 分代回收 / OS 调度，非内核劣化。
把单点 p99 当门禁 = 用抖动噪声制造假红。故主判据是**分窗漂移 + 资源增长**，p99 作 C10 辅助线。

---

## 3. 降采样断言策略（604,800 tick 的分级）

完整跑太长，故「降采样」——不是少跑 tick，而是**分层跑 + 分窗断言**：

| 层 | 触发 | 规模 | 断言 | 用例 |
|---|---|---|---|---|
| L-CI（每提交） | `-m "not bench"` | 2,000~3,000 tick | C1/C7 + 探针契约 + 量纲守卫 | `test_bench_soak.py::test_soak_ci_smoke_stability` 等 |
| L-nightly | `-m bench`（nightly-bench.yml） | 30,000 tick（≈1/3 游戏日） | C1/C3~C10 全量 | `test_bench_soak.py::test_soak_nightly_*` |
| L-里程碑/手动 | 手动/里程碑 | **604,800 tick** | 同 nightly + 汇总量落盘 | 见 §4 接法 |

**采样段代表性**：L-nightly 的 30,000 tick 覆盖**多个昼夜相位**（30,000/86,400 ≈ 1/3 日 → 含若干相位切换）。
跨 7 日的相位全覆盖由 L-里程碑 完整跑补足。三段同 seed，故小段是完整段的**确定性前缀**（可外推趋势）。

**首窗预热**：所有层都把第 1 窗当预热（`measure_since_tick` / 基线取第 2 窗），剔除 LOS 冷启动。

**负载保真**（mock 动作集）：M2 utility/runtime 未落地前，用 `soak.make_mock_feeder` 的确定性
MOVE 喂给（对应 `sim/npc/actions.py` 的 `move`），**让 50 NPC 持续走动**——否则实体静止，
感知的 moving/sound 负载远低于真实，量出来的是空转内核，不能当验收基线。
M2-A2 落地后把 feeder 换成 `NpcRuntime.tick` 的 L1 决策输出，harness 接口不变。
（已落地：main `59ffd86`，接线设计见 §3.1；算法规格与对账见 `docs/perf/l1-spec.md`。）

### 3.1 feeder 升级方案（M2-P3：mock → 真实 L1）

**现状（M2-P2 交付）**：`soak.make_mock_feeder(grid_w, grid_h, path_len)` —— 每帧给路径耗尽的实体补一段短程
MOVE，保证 50 NPC 始终在走。它的定位是**内样负载上界**（全呗 move），不消耗真实 L1 的计算。

**升级后**：`soak.make_l1_feeder(runtime, grid_w, grid_h, path_len, translate=None)` —— 每帧调
`runtime.tick(state.tick + 1)`（真实 L1：needs 推进 + 效用向量化 + 事件产出），再把决策投递给内核。
**harness 接口不变**：仍是 `feeder(loop) -> 本帧入队事件数`，`run_soak(..., feeder=...)` 不改。

**接线事实（必須先对清）**：`NpcRuntime.tick` 产出 `EventKind.NPC_ACT` 事件，但当前
`build_default_bus()` **未注册 `NPC_ACT` handler**（架构第三批接 tick 固定序时注册）。故分两阶段：

| 阶段 | 触发条件 | feeder 行为 | 量到的负载 |
|---|---|---|---|
| **阶段 1（当前）** | `NPC_ACT` 未注册 | 只把内核已注册的动作（`move`/`wander`）折成 MOVE（`issue_move`，唯一写路径）；`eat`/`rest`/`work`/`request_chat` 无 handler → **丢弃**（不谈报事件） | **真实 L1 计算全量发生**（needs/效用/事件构造都跑）+ 当前内容常量下的动作分布 |
| **阶段 2（第三批接线）** | 架构在 `TickLoop._tick_once` 挂载点调 `runtime.tick` + 注册 `NPC_ACT` handler | 退化为「全部入队」：`translate=lambda _a: True`（或 feeder 置 `None`，因为内核自己调 runtime） | L1 + 内样 + 事件落库（真实验收形态） |

**约定（接线时必须满足）**：
1. `runtime.profiles` 的 npc_id 与 `loop.state.entities` 的 id **同名**（映射一致），否则 feeder 跳过该 NPC。
2. runtime 确定性、固定序（`_order` 排序）；feeder 不引入 stdlib random（C5）。
3. feeder 在 `advance_frame` **之前**调（`run_soak` 现行顺序），传 `tick = state.tick + 1`。
4. `translate` 是纯筛选器，不改事件内容；阶段 2 只换这个参数，不动 harness。

**两份 feeder 并存的定位（不要误读实测）**：
- `make_mock_feeder` = **内样负载上界**（50 全走，~1.9ms/tick）——永远保留作回归检查的最坏情形。
- `make_l1_feeder` = **真实 L1 计算**（~0.75ms/tick，见 `l1-spec.md` §4）+ 当剅内容常量下的动作分布
  （当剂量下 `hunger` 主导，`eat` 占多数 → move/wander 少 → 内样负载反而**低于** mock）。
  所以 L1 feeder 不能取代 mock feeder 当上界＋它两个测不同的事。
- 两者皆远低 `SOAK_STEADY_MEAN_LIMIT_MS=6.2`（mock ~1.9 / L1 ~0.9ms/tick）。

---

## 4. 接法（已裁决：方案 A，2026-09-21）

**判据：完整跑在哪个 job、超时多少、失败如何暴露。** 性能域建议如下，CI 改动由 cline（配置域）落地：

### 方案 A（✅ 已采纳）：nightly-bench.yml 内新增一个 step（分阶段，不新建 job）

- 在现有 `Nightly Bench` job 里，`-m bench` 之后加一步「M2 7 日自转完整跑」，
  跑 `uv run pytest sim/tests/bench/test_bench_soak.py::test_m2_full_7day_acceptance`（完整跑用例，见下），
  `timeout-minutes: 60`。
- 优点：复用现成 uv 缓存与 runner；阈值唯一真相源仍是 `thresholds.py`（不复制）。
- 代价：nightly 总时长 +~20-60 min；`-m bench` 与完整跑同 job，需明确 timeout 分层。
- **落地记录（Claude 裁决，main 收编批）**：nightly-bench.yml 已加该 step（env `PI_M2_FULL_SOAK=1`）。
  里程碑后转 B（周频独立 workflow）时由 cline 迁出。

**完整跑用例落点**：`test_bench_soak.py` 加 `@pytest.mark.bench` + 环境门
`PI_M2_FULL_SOAK=1` 才跑的 `test_m2_full_7day_acceptance`（默认 skip，避免 nightly 默认就烧 20 分钟）；
触发方式在接法确定后由 cline 写进 yml。

---

## 5. 已交付的预压测证据（M2-P2，2026-09-21，本机）

`sim/tests/bench/test_bench_soak.py` 全部通过；实测（50 NPC + 真实感知引擎 + 持续走动 mock，64×64）：

| 窗口 | 均值 ms | p99 ms | RSS MB | 句柄 | GC 对象 |
|---|---|---|---|---|---|
| 0–20k | 1.86 | 4.65 | 50.1 | 159 | 43,644 |
| 20k–40k | 1.87 | 4.65 | 49.9 | 159 | 43,678 |
| 40k–60k | 1.85 | 4.60 | 50.0 | 159 | 43,712 |
| 60k–80k | 1.86 | 4.58 | 50.0 | 159 | 43,746 |
| 80k–100k | 2.13 | 7.97 | 30.2 | 159 | 43,780 |

结论：**均值 100k tick 内无漂移（1.86→1.86，末窗 2.13 含 OS 抖动）；RSS/句柄/GC 对象有界；
缓存封顶（LOS 2828 / walls 3385 / rtoken 50）。未发现 O(n) 累积或泄漏。**
（GC 对象每窗 +34 ≈ 噪声；末窗 RSS 下降是 OS 回收工作集，非泄漏反向。）

**待回填**：L1 utility/smell 真实现落地后，nightly 实测值回填本节 + `thresholds.py` 的 `SOAK_*`
（当前 `SOAK_*` 已按 M0/M1 内核 + 感知定基线；M2 实现落地后按实测复核，不缩小余量）。

---

## 6. 与其它域的边界

- **感知/嗅觉/L1 引擎实现**：架构域（Claude M2-A2）；本域只给长跑口径与红线。
- **信息边界 10k 采样**（DESIGN §17 M2 另一半）：codex S 域；本域不重复。
- **CI/nightly 工作流改动**：cline 配置域；本域给接法提案（§4），不直接改 yml。
- **持久化/归档**（事件日志增长 → 主库 <2GB）：opencode 数据域 + DESIGN §12；长跑若含 flush
  需关注事件表体积，本域 harness 默认不落库（drain 后丢弃），完整跑的落库体积在 §4 接法时另议。
