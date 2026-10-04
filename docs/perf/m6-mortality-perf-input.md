# M6 生命始终（落点 a）性能输入 + 定标轮待命复核
> 性能域（pi），2026-10-04。任务：M6-P2（①定标轮待命确认：两门复核，未达即如实报不跑；②**落点 a 的性能判据建议**）。
> 基线：main `48c9944`（= 本树 HEAD；本单开工复核同）。
> **性质**：预研/输入档（**零代码**；判据建议**不先写进任何测试**）。生命机制本体归 Claude/生命面。
> 依据链：A12/M6-A1 钉（落点 a 已定：移出 `entities`、死亡必须是事件）；P14 契约预研；P12 台账 §2；P13 预研 §3.2；`m6-calibration-order.md`（上单执行单）。

## 0. 结论速览
| # | 问题 | 结论 |
|---|---|---|
| 1 | 定标轮能跑吗？ | **不能——门 1（内容）仍未达**（本单实测：`fire*.py`/`authority/` 不存在、`thresholds` 三案常量零命中、`EntropyMixer.mix` 无生产调用方）。**门 2（降频）本单实测 1.547 ≤2.0 ✓，但是瞬态量**（kilo M6-K1 同轮 2.657 ✗）⇒ **不跑**（如实报）。§1 |
| 2 | 落点 a 的真实性能风险在哪？ | **不在事件成本，而在两处「存量结构不兼容 + 一处潜伏的口径」**：①`_RTOKEN_CACHE` 按 `entity_id` 键且**无淘汰** ⇒ 死亡只**移除** id、不新增 ⇒ 缓存停在 50 ⇒ **既有钉 `rtoken ≤ N_NPC` 不会红（纠偏见 §2.3-1：红只会来自新增 id，即新生/动物入世）**；②`NpcRuntime` 侧 `utility.n_npc` 构造期硬绑、运行期摘除**不会 raise**（实测：49 profiles+n_npc=50 ⇒ 矩阵 (49,6) 静默缩形）——**这是潜伏项，L1 与死亡接线时才会触发**；③实测 **死亡无稳态红利**（50 人 211.75µs vs 49 人 214.40µs）⇒ **判据的写法应是「死亡不得抬升成本」，不是「死亡应降本」**。§2 |
> **⚠ 前提变更（2026-10-04，落档时补记）**：本档成稿于 M6 内容波之前；其后 main **`ae67985` 已落地「生命始终落点 a」**（`_apply_npc_death`：`world.py:147`，只删 `entities`、`npc_profiles` 行由投影对称删除 §24、C5 纯函数）。§2 三条**按已落地实现复核**：① rtoken **仍无 evict**（`senses.py` 无 evict/forget/pop 函数）⇒ 残留有界、不泄漏，但**新增 id 会顶红**（见 §2.3-1 纠偏）；② `UtilityModel` 构造**不在 core**，L1 runtime `:59` 仅构造期预检 ⇒ 潜伏项未爆发（L1 未接死亡）；③ 无红利结论不变。
| 3 | 要不要为死亡新建红线行？ | **不要——全部并入既有行/既有钉**：事件密度→`APPLY_P99_LIMIT_MS`+`test_apply_50_events_batch`（最坏=50 人同 tick 全灭 = 一行 50 事件批，**正好被既有行覆盖**）；内存/缓存→`SOAK_GC/RSS`+`caches_bounded`；冷重算→`PERCEPTION_TICK_LIMIT_MS` 余量 + "禁批量扫"规约。§4 |
| 4 | 契约常量要不要新的？ | **一个（且属结构面）**：`SOAK_ENTITY_LOSS_PER_GAME_DAY` 阶段 B 值（P14 已备，值由生命面给，本域只给推导式）；**外加一条"死亡频率"必须由生命面给**（否则密度上界无从核定）。§5 |

---

## 1. 定标轮待命复核（两门，**本单实测**，2026-10-04）
| 门 | 复核动作与结果 | 判定 |
|---|---|---|
| **门 1（内容）** | `ls sim/world/fire*.py` → **不存在**；`ls sim/world/authority/` → **不存在**；`grep -cE "CHAOS\|POWER\|FIRE_\|MAX_BIAS" sim/tests/bench/thresholds.py` → **0**；`grep -rl PowerStore sim/npc/` → **零命中**；`grep -rn "\.mix(" sim/` 非测试域 → **无生产调用方**（`weather.py:15-16` 只是 docstring，`daily_reseed_due` 仅为 helper 于 `weather.py:133`，世界循环未接） | ❌ **未达** |
| **门 2（降频）** | `uv run python -m sim.tests.bench.throttle_probe` → `{"throttle_ratio": 1.547, "throttled": false, "burst_base_ms": 15.523, "sustained_worst_ms": 24.014}` | ✅ 本机当前**达** |
| **门 2 性质** | 上单 M6-P1 本域实测 1.629、kilo M6-K1 同轮 2.657 ⇒ **门 2 是环境瞬态量，逐次现测** | ⚠ 不作数他人读数 |
⇒ **执行单判定：定标轮暂不派（门 1 未达）**；门 1 达标后按 `docs/perf/m6-calibration-order.md` §3 执行，**先跑其 §3.0 步骤 0**（探针写进回执 + `PI_THROTTLE_SELFCHECK=0`）。
**"待命"的最小可执行定义**（换机/降频解除即跑）：跑 §3.0 步骤 0 → 跑 §3.1/§3.2/§3.3 对应用例取中位 → ×1.7 收口；**门 1 不齐则任何一列都不得收口**。

---

## 2. 落点 a：存量结构的真实成本与不兼容（**全部为实测**）
> 落点 a 已由裁/A12 定：**死亡=移出 `WorldState.entities`**，且死亡**必须是事件**（进 `pending_events` ⇒ 可重放/可快照）。
> 本域只问一件事：**把一个人从世界里删掉，现存结构要付多少、有没有东西会坏。**

### 2.1 事件密度（直接账）——最坏形态=既有行已覆盖
- 死亡就一个事件：走既有 `apply` 通路（`_apply_*`），成本与 `move` 同级。
- **最坏同 tick 全灭（50 人）** = 一行 50 事件批 = **`test_apply_50_events_batch` 的既有形态** ⇒ **已被 `APPLY_P99_LIMIT_MS=0.04` 覆盖，无需新行**。
- 真实分布极稀疏：7 日跑期死个位数 ⇒ 对 nightly 稳态均值/漂移的影响在噪声内。
- ⇒ **判据：死亡事件不设独立行**；只要求"同 tick 批内累计 ≤ 50"（否则说明批量死亡没走按帧摊还，见 §4）。

### 2.2 「删人」的静态成本（实测：**无红利、不免费**）
| 结构 | 成本/后果 |
|---|---|
| `WorldState.entities` | 重建 dict O(n)=50 ⇒ µs 级（同 `move` 既有路径，`world.py:92`） |
| **`UtilityModel` 矩阵** | 实测中位：**n=50 → 211.75µs**；n=49 → **214.40µs**；n=40 → 182.15µs；n=30 → 131.80µs；n=10 → 53.60µs ⇒ **少 1 人几乎不省（−1.3%，在噪声内）**，50→40 才省 14% |
| ⇒ 结论 | 「死亡能省 L1 开销」**不成立**（少一个 NPC 的收益被矩阵重建/批量开销吃掉）⇒ **性能判据只能写「不得抬升」，不能写「应降本」** |

### 2.3 三处「结构不兼容/钉子口径」（**本单新增发现，建议随生命施工同 CR 处理**）
1. **`_RTOKEN_CACHE` 按 `entity_id` 且无淘汰**（`sim/perception/senses.py:65`，`rtoken_of()` 只写不删），而 **既有 nightly 钉** `test_soak_nightly_caches_bounded` 断言 `sizes.get("rtoken",0) <= N_NPC`（`test_bench_soak.py:395`）。
   **纠偏（2026-10-04，按已落地的 `ae67985` 复核）**：死亡于落点 a 只**移除**实体、不新增 id ⇒ 缓存停在 50 ⇒ `50 ≤ 50` **仍绿**。**本档初稿把这一点写错成「第一个死人即顶红」，现更正**：顶红需要**新增 id**，来源有二——①「生命始终」若含**新生/入世**；②**M6-P4 的「动物三只」若在 world.create 之后才加入**（三只=3 个新 id ⇒ 53 > 50 ⇒ 红）。
   ⇒ 结论改写为：**该钉是「实体集合上限」的结构量钉子**（`_assert_smoke` 无门、每提交必跑，降频不能 skip 它）；死亡本身**无害**，**新增实体**才需同步：要么机制侧把新实体纳入 N_NPC 口径的等价物，要么把钉改成「≤ 历史最大并发实体数」的自适应口径（体例同 `_entity_loss_bound` 的派生式，不写死常数）。
   ⇒ **正确动作仍是机制侧同步，不许为它放宽钉子**；但**放宽触发条件是新增 id，不是死亡**。
2. **`UtilityModel.n_npc` 构造期硬绑，运行期摘除静默缩形**（`runtime.py:59` 预检 `n_npc == len(profiles)`；`UtilityModel.__init__` 固定 `n_npc`；`_needs_matrix`/`_weights_matrix` 按 `len(profiles)` 建矩阵 ⇒ **实测：49 profiles + `n_npc=50` 的模型 ⇒ 矩阵 (49,6)，不 raise**）。
   ⇒ 后果不是 Rust 意义上的 UB，但 `n_npc` 变成**过期声明**（谁再用它做容量/方差/断言都会错）⇒ 判据要求：**死亡必须同步重建 `UtilityModel(n_npc=新值)`（或改为 active-mask），不得只摘 `profiles`**。
   （核过一项安全疑虑：`utility_scores_matrix` **无 seeded noise**（矩阵=需求加权 + 固定 bias）⇒ 位置前移**不构成 C5 随机数串位**；`evaluate_batch` 用 `zip(active_ids, decisions, strict=True)` 单次调用内对位一致 ⇒ 此路径无 C5 风险。）
3. **`_SOUND_DESC_CACHE` 键 = `(kind, src_label)`**（`senses.py:49-59`），**有 4096 满清兜底** ⇒ 死人 tag 残留**有界**、不泄漏上千 ⇒ **只作登记项，不设判据**（如实说明边界）。

---

## 3. 间接账（P9/P10/P11 三案教训的第四案：死亡面）
P9/P10/P11 的教训形状一致：**直接成本可忽略，间接链才是真风险**（P10：幂等一处 521µs vs 整通路 227µs 决定 MAX_BIAS 取值；P11：30,000 事件/blazepack 被误认开销实为口径）。
| 间接链（死亡后可能被触发） | 量级判断 | 归口（**并入既有行，不新建**） |
|---|---|---|
| 感知：别人对死者的 LOS/sound 观测 | 下一 tick 照常算，**死亡只是少一个对象** ⇒ 不增反降 | `PERCEPTION_TICK_LIMIT_MS=3.6`（P9 50 人×全感知 3.2µs/人） |
| 寻路：以死者为目标/邻居的 A\* | 只有显式请求才跑；**禁"死亡→全图失效"**（那才是 O(n²)） | 无独立行；**规约**：失效只清受影响条目（`world/pathfinding.py` 现有局部缓存） |
| 关系/记忆：`npc_profiles` 整表克隆 | A1 实证不对称源：`entities` 不克隆、`npc_profiles` 整表克隆 ⇒ 死亡若同步删行 ⇒ **读档子分支反而少一份** | 数据面账（schema 登记），**非性能行** |
| 「死亡→叙事/LLM 复盘」若接线物化/LLM | 单次读档面 = 同 `MATERIALIZE_LIMIT_MS` 一次性档（**不进 tick**） | 物化档 advisory（W 未定，见 calibration-order §5） |
| **批量死亡风暴**（若未来有"群体猝死/清算"） | 一次 O(n) 扫 = 走 apply 批 ⇒ 已在 §2.1 覆盖；但**若实现自带 O(n) 全量重算**（如全员改目标） | 必须**按帧摊还**（体例同 `CASCADE_EVENT_BUDGET_PER_FRAME` / `FIRE_REPATH_BUDGET_PER_FRAME=100`）⇒ **契约常量，不进 thresholds** |

⇒ **教训应用（本单给生命面的规约一条）**：**"死亡不得触发每 tick O(n) 批量扫"**——把间接账用规约挡住，而不是用阈值量它（与 P11 收口形状一致：优先砍垃圾规约）。

---

## 4. 合并后的判据台账建议（**全部并入，零新行**）
| 效应 | 判据落点 | 现值 | 状态 |
|---|---|---|---|
| 死亡事件成本 | `APPLY_P99_LIMIT_MS=0.04` + `test_apply_50_events_batch` | 已有 | ✅ **不新行** |
| 同 tick 批量死亡规模 | 规约 + 按帧摊还契约常量（若未来群体死亡） | `CASCADE/FIRE_REPATH=100` 体例 | 登记 |
| 稳态 L1 成本 | `L1_UTILITY_TICK_LIMIT_MS=6.0`（P10 已留 0.29ms 余量） | 已有 | ✅ **不新行** |
| 感知 | `PERCEPTION_TICK_LIMIT_MS=3.6`（P9） | 已有 | ✅ **不新行** |
| 内存/对象/句柄 | `SOAK_GC_OBJECT_GROWTH_LIMIT`、`SOAK_RSS_GROWTH_LIMIT_MB`、`SOAK_HANDLE_GROWTH_LIMIT` | 已有 | ✅ **不新行** |
| 缓存有界（**rtoken 钉子**） | `test_soak_nightly_caches_bounded`（含 `rtoken ≤ N_NPC`） | 已有 | ⚠ **机制须同步失效 rtoken/sound_desc**，否则顶红 |
| 死亡频次/净减上界 | `SOAK_ENTITY_LOSS_PER_GAME_DAY`（阶段 B） | 0（阶段 A） | 值由生命面给（§5） |
| 确定性（C5） | 死亡时刻 `(world_seed, 事件流, tick)` 派生 + **死亡走事件**（A1/A12 钉） | 已钉 | 机制合规项 |
| `n_npc` 一致性 | 死亡同步重建 `UtilityModel` 或改 active-mask | **现无保障** | ⚠ §2.3-2 新增发现 |

---

## 5. 阶段 B 接值与待裁清单（**归 Claude/生命面**）
- **BOUND 推导式（不变）**：`SOAK_ENTITY_LOSS_PER_GAME_DAY = ceil(N_NPC × 每游戏日死亡比例上界)`；阶段 B 与生命施工**同 CR** 提值（P14 §2.3、`m6-calibration-order.md` §2）。
- **须由生命面给的两个数**：①每游戏日死亡上界（否则 BOUND 无从核定）；②同 tick 批量死亡上界（否则按帧摊还常量无从定；同族见 `FIRE_SPREAD_INTERVAL_TICKS=60`）。
- **须由生命面定的两个结构**：①rtoken/sound_desc 的失效路径（`senses.py` 进程级缓存的 evict 由谁负责，建议死亡 handler 直接 evict，勿引入扫描）；②`UtilityModel.n_npc` 的重建时机与 active-mask 形态。
- **建议给施工单的一句话**：**"死亡事件走既有 apply 通路；稳态成本不得抬升；任何 O(n) 重算按帧摊还；rtoken 必须同步失效。"**

---

## 6. 留痕（2026-10-04，本机）
| 动作 | 结果 |
|---|---|
| `throttle_probe` | `1.547` ≤2.0 ✓（瞬态；上轮 1.629、kilo 2.657） |
| `ls fire*.py` / `authority/` / thresholds grep / `PowerStore` / `mix(` | 全**未达/零命中** ⇒ 门 1 ❌ |
| `sed -n '58,105p' sim/npc/utility.py` + `runtime.py:95,140p` | 矩阵按 `len(profiles)` 建、无 seeded noise；`zip(...,strict=True)` 单次对位一致 |
| `n_npc=50` + 49 profiles 实测 | **不 raise**，矩阵 (49,6) ⇒ §2.3-2 依据 |
| `utility_scores_matrix` 中位（µs） | 50→211.75 / 49→214.40 / 40→182.15 / 30→131.80 / 10→53.60 ⇒ §2.2「无红利」 |
| `senses.py:49-59,65-81` | sound_desc 键=(kind,src_label)+4096 满清（有界）；`_RTOKEN_CACHE` 按 entity_id 无淘汰 |
| `test_bench_soak.py:395` | 既有钉 `rtoken ≤ N_NPC` ⇒ 死亡不清即顶红 |
| `ruff check .` / `pyright .` | All checks passed / 0 errors |
