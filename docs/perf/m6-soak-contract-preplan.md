# M6 前置契约小单：soak 实体守恒断言改法预研（施工级方案）
> 性能域（pi），2026-10-03。任务：M5-P14（**零代码**：`sim/`、`thresholds.py`、既有 bench 文件、`docs/README` 零改动；**BOUND 提案值不先写进任何测试**）。
> 基线：main `2bd2bff`（= 本树 HEAD，开工前同头确认；2278 passed / 125 skipped 系主树口径）。
> 缘起：P13 `docs/perf/m6-perf-preplan.md` §3.2 前瞻——`test_bench_soak` 硬断言实体数恒等，而该断言诞生于「NPC 不会死」的世界 ⇒ M6「生命始终」有撞契约风险。
> **本单对该前瞻做两处诚实收窄**（先读 §1.3：DESIGN §11 明写「Agent 永不死」⇒「必红」是**条件性**判定；§1.2 实测实体集合**运行期零增删路径**）。
> 依据链：`test_bench_soak.py`（断言/调用面实测）、`soak.py`（计数来源实测）、`sim/core/world.py`（实体集合可变性实测）、`sim/npc/runtime.py`（LOD 实测）、`docs/perf/budget.md`、`thresholds.py:155-181`（cascade budget 体例）、DESIGN §11/§13/§17/§18。

## 0. 结论速览
| # | 问题 | 结论 |
|---|---|---|
| 1 | 改法精确形态？ | **两侧各一界，不要写成单侧 `end <= start + BOUND`**（那会把「净增 ≤ BOUND」合法化＝**部分放弃防泄漏**）。正确形态：`end <= start`（增侧界**恒 0**，硬断言）+ `start - end <= BOUND`（减侧界，随生命面定）。**两处断言同改**，且建议抽成**单一函数** `_assert_entity_stable(result, label)` 供两处调用（防双真相源）。§2 |
| 2 | BOUND 值/依据？ | **分两阶段**：阶段 A（现在可落）`BOUND = 0` ⇒ 与原断言**语义等价**、首跑必绿、零风险；阶段 B（生命施工同 CR）才把值提到生命面给的死界。**体例照 cascade budget**：`BOUND` 是**代码契约常量**（模块级 `Final`，落 `test_bench_soak.py` 顶部，**不进 `thresholds.py`**——它是 soak 语义参数不是性能阈值）+ 一条锁值契约钉（仿 `test_cascade_frame_budget_is_100_nodes`）+ 语义注释。**不分档硬编码**，用**单一真相源导出**：`bound = ceil(SOAK_ENTITY_LOSS_PER_GAME_DAY × ticks / TICKS_PER_GAME_DAY)` ⇒ CI(1200)/nightly(30k)/7日(604.8k) 自动给不同值。§2.3 |
| 3 | 防泄漏原意还保得住吗？（反证） | **保得住且更强**：净增侧界=0 ⇒ 任何 `end > start` 立红（原断言只报「漂移」分不清方向，改后报错可区分**净增=泄漏** vs **净减=衰减**）。**但反证出四类「`end <= start` 恒真却仍泄漏」**，其中**第 4 类是本改法必须补的洞**（实体集与 `runtime.profiles` 映射分叉）。⇒ 建议**同时补一条 id 集合判据**（`set(end) ⊆ set(start)`），比计数强。§3 |
| 4 | 现值下改后首跑绿吗？ | **全绿**（实测：运行期零增删路径 ⇒ 两侧界 0 都满足、id 子集恒真）⇒ **零风险改动，可在 M6 前独立落**。与降频门交互：`_assert_no_runaway` 首行就是 `_skip_if_throttled()` ⇒ 降频夜这几条整段 skip，而 `_assert_smoke`（CI 冒烟）**无探针门、每提交必跑** ⇒ 实体断言是 CI 面**唯一的结构判据**（该面没有 RSS/GC/句柄兜底）。⇒ 建议把结构断言**移到探针门之前**（结构判据不需要探针，且不该被降频掩盖）。§4 |
| 5 | 次序依据？ | 三条：①**归因成本**（同 CR 混改 ⇒ 红灯无法区分「机制正常但契约过期」vs「机制 bug」；M5 已两次踩计数误读）；②**契约可先落且零风险**（§4 实测）⇒ 不阻塞任何人，把契约改动从生命 CR 摘出去；③**保护 nightly 信噪比**（生命施工当晚若同时改两样，第一晚红无基线可比）。⇒ 次序：契约小单 → 生命机制 → BOUND 收口。§5 |
| 6 | 委托 opencode 核实？ | 3 问（**M5-A12 并行**）：Q1 生命落点（移出 entities / 加标志位 / 走 LOD / 被砍）；Q2 双记账是否原子同改（`entities` ↔ `runtime.profiles`）；Q3 事件面是否新增 kind 及其重放/克隆归属。§6 |

---

## 1. 现状实测（**所有数字均为本机亲验，非转述**）

### 1.1 断言与调用面
| 项 | 实测 |
|---|---|
| 断言本体 | `test_bench_soak.py:146`（`_assert_no_runaway`，定义 :103）与 `:163`（`_assert_smoke`，定义 :150），两处均为 `assert result.entity_count_end == result.entity_count_start` |
| 调用面（**5 处，不是 2 处**） | `_assert_no_runaway` ×3：`:296` nightly 30k（mock）/ `:357` **7 日完整跑 604,800 tick** / `:397` nightly L1 30k；`_assert_smoke` ×2：`:217` CI 冒烟（mock 1,200 tick）/ `:416` L1 CI 冒烟 |
| bench 标记 | CI 冒烟两测（`:202`/`:401`）**无** `@pytest.mark.bench` ⇒ **每提交 CI 跑**；nightly/完整跑（`:292`/`:300`/`:322`/`:339`/`:381`）带 bench 标记 ⇒ nightly/里程碑 |
| 规模常量 | `N_NPC = 50`、`_CI_SOAK_TICKS = 1_200`（窗 400）、`_NIGHTLY_SOAK_TICKS = 30_000`（窗 6,000）、`M2_ACCEPTANCE_TICKS = 604_800`（窗 = `TICKS_PER_GAME_DAY` = 86,400，7 窗） |
| 探针门 | `_skip_if_throttled()` 在 `_assert_no_runaway` **首行 :111** 与 nightly fixture `:280`；`_assert_smoke` **无门** |

⇒ **改动面 = 2 处断言 / 1 个可抽的公共函数 ⇒ 覆盖全部 5 个测试**。

### 1.2 计数来源与实体集合可变性（**决定改法的关键实测**）
- 计数 = `soak.py:312` `entity_count_start = len(loop.state.entities)` / `:335` `entity_count_end = len(...)` ⇒ **纯内存 `WorldState.entities` 的 len**，**不经 fold / 不经事件重放**。
- `WorldState.entities` 的**唯一建立点** = `world.py:112` `_apply_world_create`（且 `:111` 硬校验「只能作用于空白状态」，非空即 raise）。
- **运行期无删除路径**：全仓 `entities.pop` / `del …entities` / `entities.clear` **零命中**；`world.py:124-129` `_apply_move` 只 `{**state.entities, id: new}` 换 `path`，且 `:126` 未知 id **直接 raise `未知实体`**。
- ⇒ **今天该断言是「结构性恒真」**：它防的不是运行期漂移（无路径可漂），而是「**未来新增 handler 私自增删实体**」这一**契约**。
- 副产物：soak artifact 用 `dataclasses.asdict(result)` 落 `perf/soak-windows.jsonl` ⇒ `entity_count_start/end` **已在 artifact 里**（回归趋势可查，无需新增字段）。

### 1.3 ⚠ 对本域 P13 前瞻的两处诚实收窄
1. **「必红」是条件性的**：DESIGN **§11 L339 明写「Agent 永不死，只失能+时间跳跃（醒来时债涨了、朋友搬走了）」**——这是**分支内铁律**。而 §17 L482 的 M6 行含「生命始终」。⇒ **若「生命始终」遵守 §11（不死、只失能）⇒ 实体数不变 ⇒ 本契约根本不撞**；只有「死亡＝把 id 移出 `entities`」这一种落点才必红。
2. **「生命始终」可被砍**：§13 L388 把「生命始终」列在「**加内容六个（可增量，缩范围从这里砍）**」内；§18 L491 可砍序为「生态 → 火灾蔓延 → 语言阶层 → 空间迷雾 → 权力牙齿 → **生命始终** → 动物三只 → 节气」⇒ 它是**倒数第三个可砍位**（高可砍性）。
3. **今天事件面零实现**：`events.py` 内 `death` / `dead` / `disabled` / `失能` **零命中** ⇒ 生命始终在事件面尚无载体。
⇒ **所以本单的正确定位**：不改「M6 一定会撞」的结论，而是**把契约提前改成「两种落点都能容纳」的形态**（见 §2），并把**落点归属作为委托问题**交 opencode/Claude（§6）。**这正是「契约先于机制」的价值：不需要先知道机制，也能把断言改成安全形态。**

---

## 2. 改法精确形态（①）

### 2.1 推荐写法（两侧各一界 + 单一函数）
```python
# test_bench_soak.py 顶部（代码契约常量区，非 thresholds.py）
SOAK_ENTITY_LOSS_PER_GAME_DAY: Final[int] = 0   # 阶段 A：0 ⇒ 与原断言语义等价；阶段 B 由生命面给值

def _entity_loss_bound(ticks: int) -> int:
    """本 run 允许的实体净减上界（单一真相源导出，不按档硬编码）。

    体例对照 CASCADE_EVENT_BUDGET_PER_FRAME：规模由**代码契约常量**硬约束，
    耗时由 thresholds 红线覆盖，两者不混。此处同构：
      · 规模侧 = 本函数的返回值（契约常量导出）
      · 耗时侧 = SOAK_STEADY_MEAN_LIMIT_MS / 漂移比（既有红线，不动）
    """
    if SOAK_ENTITY_LOSS_PER_GAME_DAY <= 0:
        return 0
    days = ticks / TICKS_PER_GAME_DAY
    return math.ceil(SOAK_ENTITY_LOSS_PER_GAME_DAY * days)

def _assert_entity_stable(result, *, label: str) -> None:
    """实体守恒（两处断言共用，防双真相源）。"""
    start, end = result.entity_count_start, result.entity_count_end
    bound = _entity_loss_bound(result.total_ticks)
    # ① 增侧：净增必须为 0（防「凭空增多」= 原断言的原始意图，**不放宽**）
    assert end <= start, f"{label}: 实体净增（疑似泄漏/失控 spawn）{start} → {end}"
    # ② 减侧：净减必须有界（容纳 M6 死亡；阶段 A bound=0 ⇒ 等价恒等）
    assert start - end <= bound, f"{label}: 实体净减 {start - end} 超界（上界 {bound}，{start} → {end}）"
    # ③ id 集合：不得出现新 id（比计数强，抓「换 id 重造」，见 §3 反证）
    if result.entity_ids_start:
        new_ids = set(result.entity_ids_end) - set(result.entity_ids_start)
        assert not new_ids, f"{label}: 出现新实体 id（{sorted(new_ids)[:5]}…）"
```
- **两处调用点同改**：`_assert_no_runaway` 与 `_assert_smoke` 内原 `assert … == …` 两行 → 各替换为 `_assert_entity_stable(result, label=label)`。
- **③ 的落地成本**：`SoakResult` 需加 `entity_ids_start/end`（`tuple[str, ...]`），在 `soak.py:312/335` 顺带记 `tuple(loop.state.entities)`；artifact 自动带上（`asdict`）。**这是施工项，归 `soak.py`（本单零代码只出案）**。

### 2.2 为什么不写成单侧 `end <= start + BOUND`
- 单侧式把**净增**也纳入 BOUND 的宽容范围 ⇒ 「每 tick 加 1 个实体、共加 100 个」在 BOUND=100 时**合法** ⇒ **等于部分放弃原断言的全部价值**。
- 且方向混淆：净增是**泄漏**（无界 bug），净减是**设计**（生命）。**两者不该共用一个界**。
- ⇒ 采纳 **增侧 0 + 减侧 BOUND** 的**非对称**写法（这也是「只减不增+有界」的精确落地；P13 的口语表述在此固化为代码形态）。

### 2.3 BOUND 的值、体例与「是否分档」
| 项 | 方案 |
|---|---|
| 体例（对照 cascade budget） | `CASCADE_EVENT_BUDGET_PER_FRAME=100` = **模块级 Final 代码契约常量** + 锁值钉 `test_cascade_frame_budget_is_100_nodes`（`test_bench_structure.py:412`）+ 语义注释；**红线按耗时另设**（`COLLAPSE_FRAME_LIMIT_MS=0.85`），**规模与耗时分离**。⇒ 本单同构：`SOAK_ENTITY_LOSS_PER_GAME_DAY` 进 `test_bench_soak.py` 顶部 Final + 锁值钉 + 语义注释；**不进 `thresholds.py`**。 |
| 阶段 A 值（**现在可落**） | `= 0` ⇒ `bound = 0` ⇒ 断言 `end <= start` **且** `start - end <= 0` ⇒ **与原 `==` 完全等价**（只多出方向可读的报错）。**首跑必绿、零行为变化**（§4 实测支撑）。 |
| 阶段 B 值（生命施工同 CR） | 由生命面给「每游戏日可接受净减上界」；本域给**推导式**不拍数：`SOAK_ENTITY_LOSS_PER_GAME_DAY = ceil(N_NPC × 每游戏日死亡比例上界)`。示例（**仅说明量纲，非提案值**）：50 人 × 若「7 日累计死亡上界 10%」⇒ 3.5 人/7 日 ⇒ **0.5/日** ⇒ `ceil(0.5×days)` ⇒ CI(0.014日)=1、nightly(0.347日)=1、7日=4。 |
| **是否分档** | **不分档硬编码**（否则三处常量 = 双真相源）。用 §2.1 的 `_entity_loss_bound(ticks)` **从单一常量导出**；CI/nightly/7日 自动得不同值。 |
| 与「现行值是否绿」的关系 | 阶段 A 落地的**当夜**：`bound=0`、无增删 ⇒ 绿（§4）。阶段 B 落地**必须与生命机制同 CR**（否则机制先落 ⇒ 死界仍是 0 ⇒ 必红，正是我们要避免的）。 |

---

## 3. 防泄漏原意保留验证（②，含反证）

**原意**：抓「实体凭空增多」（无界增长）。
**改后**：净增侧界 **恒 0** ⇒ 任何 `end > start` 立红，且报错直指「净增（疑似泄漏/失控 spawn）」⇒ **判别力不降、可读性提升**（原断言只报「漂移」，方向不明）。

**反证：什么破坏会让 `end <= start` 恒真却仍泄漏？**（逐条给兜底）
| # | 反证场景 | 计数断言能抓？ | 兜底在哪 | 结论 |
|---|---|---|---|---|
| 1 | **同 key 覆盖型 churn**（每 tick 用新 `EntityState` 覆盖同 id，dict 覆盖不涨 len） | ❌ 抓不到（**原 `==` 断言同样抓不到**） | `_assert_no_runaway` 的 **GC 对象增长 ≤20,000 / RSS ≤128MB / 句柄 ≤64** 三条 | 非本改法引入的盲区；**但 CI 冒烟面没有这三条**（见 #4） |
| 2 | **增删配对（净零）**：每 tick 加 1 删 1（或「重生」机制） | ❌ 两侧界都过 | GC/RSS/句柄 + `pending_peak` | 同上；**原断言也盲**（只看净数） |
| 3 | **单实体内部膨胀**（如 `EntityState.path` 无界增长） | ❌ 计数不变 | GC/RSS | 同上；原断言同样盲 |
| 4 | **实体集 ↔ `runtime.profiles` 映射分叉**（`soak.py:198` 已立契约「id 必须同名」）：死亡只从 `entities` 移除、`profiles` 留着（或反之） | ❌ **净减合法**（在 BOUND 内）却留下不一致 | **目前无兜底** | ⚠ **本改法必须补的洞** ⇒ 见下 |
| 5 | 泄漏转移到**其他容器**（`pending_events` / DB 行 / 缓存） | ❌ 与实体数无关 | `pending_peak` + `test_soak_nightly_caches_bounded` | 已有独立钉 |

**#4 的修法（本单新增建议）**：加一条**映射一致性断言**——
```python
# _assert_entity_stable 内追加（若 result 带 runtime 侧 id 快照）
assert set(result.runtime_profile_ids_end) == set(result.entity_ids_end), \
    f"{label}: 实体集与 runtime.profiles 映射分叉（死一半=最坏状态）"
```
理由：**「死亡只改一半」比「两边都不改」更坏**——世界认为该 NPC 已不存在，而 runtime 仍按老 id 推进/产事件 ⇒ 后续 `_apply_move` 会撞 `未知实体` raise（`world.py:126` 实测路径），或产生**幽灵事件**。这条断言成本 = 一次 set 比较，**且现值恒真**（同源构造）。

**结论（给施工单的一句话）**：计数断言只能防「**净增**」一类；改法应**同时**落「id 集合无新增（③）」与「映射一致（#4）」，三者共同构成实体守恒面；**其余盲区（#1–#3）继续由既有 GC/RSS/句柄三条兜**，**并建议 CI 冒烟补一条便宜的 id 集合判据**（因该面没有资源三条，见 §4）。

---

## 4. 影响面（③）

### 4.1 现值下改后首跑预期：**全绿（零风险）**
- 阶段 A（`bound=0`）：实测运行期零增删 ⇒ `end == start` ⇒ `end <= start` ✓、`start - end = 0 <= 0` ✓、`new_ids = ∅` ✓。
- 因此**契约小单可独立合入且不改变任何现有行为** ⇒ 排期上**无阻力**（不阻塞其他任何单）。

### 4.2 五个调用面的落地顺序建议
| 面 | 测试 | 现值 | 改后 |
|---|---|---|---|
| CI 冒烟（mock 1,200t） | `test_soak_ci_smoke_stability`（**:217**，每提交） | 绿 | 绿（断言等价） |
| CI 冒烟（L1 1,200t） | `test_soak_l1_feeder_ci_smoke`（**:416**，每提交） | 绿 | 绿 |
| nightly 30k（mock） | `test_soak_nightly_longrun_stability`（**:296**） | 绿 | 绿 |
| nightly 30k（L1） | `test_soak_nightly_l1_feeder_stability`（**:397**） | 绿 | 绿 |
| **7 日完整跑** | `test_m2_full_7day_acceptance`（**:357**，需 `PI_M2_FULL_SOAK=1`，默认 skip） | 绿 | 绿（阶段 B 后仍绿，只要 BOUND 与机制同 CR） |

### 4.3 与 throttle 门级联 skip 的交互（P11 判例）
- `_assert_no_runaway` **首行 :111 就是 `_skip_if_throttled()`** ⇒ 降频夜 `:296`/`:357`/`:397` 三条**整段 skip**（含实体断言）；nightly fixture `:280` 同样带门。
- `_assert_smoke`（`:217`/`:416`）**无门** ⇒ **每提交 CI 必跑**，且该面**只有计数一条结构判据**（无 RSS/GC/句柄）⇒ **它是实体泄漏的唯一每提交网**。
- ⇒ **两条施工建议**：
  1. **实体断言位置移到探针门之前**：结构判据（实体数/ id 集合/映射一致）**不依赖机器速度**（是结构量、非计时量，天然免疫降频）⇒ 没理由被降频 skip 掉。现状把它排在 `_skip_if_throttled()` 之后 ⇒ **降频夜结构面静默不检**。
  2. **CI 冒烟补 id 集合判据**（§3 结论）：该面没有资源三条兜底，id 判据是**最便宜**的补强（一次 set 差）。
- 注：移动位置会让「降频夜 soak 也可能因结构问题判红」——这是**期望行为**（结构问题不该被降频掩盖）；与 P6/P7「降频 ⇒ skip 而非红」的**计时类**判据分工不冲突（计时仍 skip）。

---

## 5. 排期依赖声明（④，收官轮 M6 派单可直接引用）

**声明**：**「生命始终」施工单的前置 = soak 实体守恒契约小单已合入**（含两侧界写法 + id 集合判据 + 映射一致判据）；且**生命施工单须同时给出 `SOAK_ENTITY_LOSS_PER_GAME_DAY` 的值与依据**（否则契约停在 0，死亡一来即红）。

**次序依据（三条）**：
1. **归因成本**：契约与机制同 CR 混改 ⇒ 红灯时**无法区分**「机制按设计工作、只是契约过期」与「机制本身有 bug」。M5 已**两次**踩过这类计数误读：P11 的 `66/4`（降频门级联 skip 被疑为回归）、P12 的 `2267/2347`（口径差被疑为用例丢失）。
2. **契约可先落且零风险**（§4.1 实测：两侧界 0 均满足）⇒ 先落**不阻塞任何人**，并把「契约改动」从生命 CR 里摘出去，让生命 CR 只含机制。
3. **保护 nightly 信噪比**：nightly 是唯一全局回归网；若生命施工当晚同时改契约+机制，第一晚红**无基线可比**（不知道红是新机制还是契约）。

**次序**：① 契约小单（本单施工化，阶段 A）→ ② 生命机制施工（同 CR 把 BOUND 提到阶段 B 值）→ ③ 定标/收口（若 BOUND 需实测校准，按 P12 §2.4 五步）。

**反向风险（若不按此序）**：机制先落 ⇒ 死亡当晚 `_assert_no_runaway`（nightly 30k / 7 日）与 `_assert_smoke`（**每提交 CI**）同时红 ⇒ 按 P12 纪律「passed 少先查门/契约再怀疑代码」会被迫走一遍排查，且**CI 面会持续红到契约改完**（阻塞所有人）。

---

## 6. 数据面核实委托清单（⑤，给 opencode，M5-A12 并行）

> 本单已实测的事实作为**已答部分**附在问后（省对方重复劳动）。

**Q1（生命落点 = 契约是否撞的决定性问题）**：M6「生命始终」若落，**实体消失走哪条路**？
（a）从 `WorldState.entities` **移除 id**；（b）保留 id 但加「失能/死亡」标志位；（c）走 **LOD 降格**；（d）该功能被砍（§13/§18 可砍序靠后）。
**四者后果完全不同**：(a) 计数下降 ⇒ **必须**死界（本单阶段 B）；(b) 计数不变 ⇒ 本契约**不用改**，但需另立「存活/失能」判据；(c) 计数不变 ⇒ 本契约**不用改**（实测：`runtime.py:103` 的 lod 过滤**不动** `loop.state.entities`）；(d) 无影响。
**已答**：`entities` 唯一建立点是 `_apply_world_create`（限空白态）；运行期零删除路径（`entities.pop/del/clear` 全仓零命中）；`_apply_move` 对未知 id `raise 未知实体`。

**Q2（双记账一致性）**：`soak.py:198` 已立契约「`runtime.profiles` 的 id 必须与 `loop.state.entities` 同名」。生命施工后**两处是否原子同改**？若只改一处（entities 删、profiles 留）是否已有钉可抓？（本单建议加映射一致断言，见 §3 #4——请确认是否已存在等价钉，避免重复。）

**Q3（事件面与重放/克隆归属）**：今天 `events.py` **零** `death/disabled` kind（实测）。生命施工是否新增 kind？若新增：是否需同步 `PAYLOAD_MODELS` 闭合集（K11 P3 纪律）？死亡事件是否需进重放投影（`fold_*`）与 fork 克隆面（对照 A9 把 `fires` 登记进 `_BOUNDED_TABLES` 的体例）？「死亡」是否要进 `branches.rng_state` 之类的确定性载体（C5：死亡时刻必须 `(world_seed, 事件流, tick)` 可复现）？

**Q4（可选，LOD 语义）**：现状 LOD 降格**不移出** `entities`（只影响 runtime 的 active 过滤）。若 M6 想让「降格 = 离场」，是否需与实体守恒契约对齐？（若是，则 (c) 落点会变成 (a) 的变体。）

---

## 7. 提案值汇总（**遵卡片约束：不先写进任何测试**）
| 常量/判据 | 现值建议 | 阶段 B（生命同 CR） | 体例/落点 |
|---|---|---|---|
| `SOAK_ENTITY_LOSS_PER_GAME_DAY` | **0**（等价恒等，可先落） | 由生命面给（本域给推导式） | 代码契约常量 + 锁值钉；**落 `test_bench_soak.py` 顶部，不进 `thresholds.py`** |
| 增侧界（净增 ≤ 0） | **硬断言**（不进常量） | 不变（除非 M6 明确引入运行中入世 ⇒ 需**单独**的增侧常量与依据） | `_assert_entity_stable` |
| id 集合判据（无新 id） | **硬断言** | 不变 | `_assert_entity_stable`（需 `SoakResult` 加 id 快照） |
| 映射一致判据（`entities` ↔ `profiles`） | **硬断言**（现值恒真） | 不变 | `_assert_entity_stable` |
| 断言位置 | 建议**移到 `_skip_if_throttled()` 之前** | 不变 | `_assert_no_runaway` / `_assert_smoke` |
| `thresholds.py` | **零改动**（本契约不进红线表） | 零改动 | — |

---

## 8. 零改动留痕（2026-10-03，本机）
本单**只新增本文档**（+ 自树 `.orca/memory.md`）。`sim/`、`sim/tests/bench/`、`thresholds.py`、`docs/README.md` 零改动；**BOUND 提案值未写入任何测试**（卡片约束）。

| 动作 | 结果 |
|---|---|
| `grep -n "entity_count" sim/tests/bench/soak.py` | `:264/:265` 字段、`:312/:335` 赋值 = `len(loop.state.entities)` ⇒ **计数来源=内存 WorldState，不经 fold** |
| `grep -n "entity_count\|_assert_no_runaway\|_assert_smoke" sim/tests/bench/test_bench_soak.py` | 断言 `:146`/`:163`；调用面 **5 处**（`:217`/`:296`/`:357`/`:397`/`:416`） |
| `grep -n "@pytest.mark" …test_bench_soak.py` | CI 冒烟两测无 bench 标记 ⇒ 每提交跑（`:202`/`:401`） |
| `grep -rn "entities.pop\|del .*entities\|entities.clear" sim/` | **零命中** ⇒ 运行期无删除路径 |
| `sim/core/world.py:111-129` | 创世限空白态；`_apply_move` 未知 id raise ⇒ 无增删路径的代码依据 |
| `sim/npc/runtime.py:103` / `model.py:60` | LOD 只过滤 active / 落 `NpcProfileData` ⇒ **不动 `entities`** |
| `events.py` grep `death/dead/disabled/失能` | **零命中** ⇒ 生命始终今天事件面零载体 |
| DESIGN §11 L339 / §13 L388 / §17 L482 / §18 L491 | 「Agent 永不死」/ 生命始终∈可砍六 / M6 行 / 可砍序倒数第三 ⇒ §1.3 收窄依据 |
| `test_bench_structure.py:412` `test_cascade_frame_budget_is_100_nodes` | cascade 契约钉体例（锁值 + 语义注释 + 规模/耗时分离）⇒ §2.3 体例依据 |
| `uv run ruff check .` | **All checks passed** |
| `uv run pyright .` | **0 errors, 0 warnings, 0 informations** |
| `throttle_probe` | **未跑**：本单为契约形态预研，判据全部是**结构量/静态代码事实**（计数来源、调用图、可砍序、DESIGN 原文），**不含任何绝对耗时阈值** ⇒ 不受降频门影响（特此说明，非疏漏） |
