# M5-P6：CRUD 写路径（POST/DELETE /api/anchors）bench 补项提案稿（零代码）

> 性能域（pi），2026-09-30。任务（Claude M5-P6 第 2 项）：判断 CRUD 写路径是否**需要** bench 行，
> **提案稿先行、零代码**。对照：`docs/api/anchors-api.md` §6.1 **A2 锁**与「写路径低频」契约、
> `docs/perf/bench-plan.md` §0（bench 定位：性能回归进检，**不是功能门禁**）+ §1 清单现行形态。
> 关联：`docs/perf/m5-p6-soak-arbitration.md`（本单仲裁结论）。

---

## 0. 结论速览

| # | 问题 | 结论 |
|---|---|---|
| 1 | **要不要新增 bench 行？** | **本轮不加，只登记为预备行**（`bench-plan.md` §1 已预留 `persistence` 行但从未有实现；把它算「补上」而非「新增」）。 |
| 2 | 主要理由 | ①写路径是**玩家手动触发**（一次按键 / 一次点击），**低频**（数量级：一个游戏会话 0–几十次）——bench 的价值在「高频回归线」，低频路径的红线会变成**永远不红的装饰**；②A2 `asyncio.Lock` 串行化的本质代价已在 §2 量化（≈微秒级，**锁本身不是热点**）；③CRUD 已交付的功能回归（正确性/保险丝）由 `test_m5_anchors_crud.py` 21 钉覆盖，bench **不替代**也不重复。 |
| 3 | 何时必须升级为真 bench 行？ | 触发条件明确（§3）：**任一条满足即立项**。首个候选触发点是「世界档导入（orchestrate_load_anchor）在生产定时化」而非玩家手动。 |
| 4 | 红线归属（若立项） | **观察态起步**（`_record_proposal` 形态，与 `test_bench_fast_forward.py` 一致），**不写 `thresholds.py` 常量**；定标后按 m5-fast-forward-budget.md §8 三条件转硬断言。 |

---

## 1. 事实清点（不猜，全部有出处）

### 1.1 写路径的真实频度
- `POST /api/anchors`：**玩家主动创建存档点**（`docs/api/anchors-api.md` §6.2 B1：「DESIGN §12 玩家档是玩家**主动**存的**少量**进度点，与无限增长的数据集不同性质」）。
- `DELETE /api/anchors`：玩家主动删除，同样低频。
- `orchestrate_load_anchor`（CRUD driver 生产挂载）：**由 anchor load 流触发**，目前是**操作驱动**，非每 tick / 每帧。
- 对冲面：一次写 = 一次 SQLite 事务（`anchors` INSERT + `profiles` UPDATE 清旧）——**单条量级**，
  和 `bench-plan.md` §1 `persistence` 行设计的「批量 INSERT 20/100 条」不是同一个形状。

### 1.2 A2 锁的真实代价（§6.1）
- `AnchorStore` 挂 `asyncio.Lock` 包 `create`/`delete`；读不加锁（单 worker 部署匹配）。
- 锁的竞争者 = **同事件循环里并发到 anchor 写路径的协程**。玩家手动触发 ⇒ **竞争实际为 0**。
- 结论：**锁不是热点**；拿 bench 去量一把没人抢的锁，量到的是 `asyncio.Lock` + 事务本身的开销
  （微秒—百微秒级），**没有回归信息量**。

### 1.3 现有可对照的形态
| 现成 bench | 形态 | 与 CRUD 写路径的关系 |
|---|---|---|
| `test_bench_structure.py`（sqlite session factory / `SqlEventStore`） | **事件/结构存储写入** | 已覆盖「SQLite 写入」的高频子路径；CRUD 走同一 `ProfileStore` 层 |
| `test_bench_retrieval.py` | 检索读路径 | 读侧已覆盖 |
| `bench-plan.md` §1 `persistence` 行 | 「批量 INSERT（WAL）20/100 条；快照 5MB gzip」 | **清单有行、实现无例**——这本身就是「低频不该建红线」的历史证据 |

---

## 2. 若立项，测什么 / 不测什么（§3 触发后才用）

### 2.1 测（三条，都是**回归检出**而非绝对红线）
1. **`POST /api/anchors` 端到端（单条）**：name 合法 → 同事务「清旧 protected + 写新档」→ 返回 cursor。口径 = 单次 p50/p99（**非**每 tick 预算行——写路径不占 tick 预算）。
2. **批量 N 条顺序 POST 的摊销**（`N ∈ {1, 10, 50}`，单玩家会话上限量级）：验证**无 O(n²)**（清旧 protected 若退化成全表扫描，N 增大会露出来）。这是 A3「清旧」最值得 bench 的一刀。
3. **DELETE 409 判据读 + 硬删**：单次 p50/p99。

### 2.2 不测（防跑偏）
- **不加锁 vs 加锁的对比**（那是 A1/A2 的**功能选择**，已由 `test_m5_anchors_crud.py` 的并发钉覆盖；bench 比锁开销是空转）。
- **不加 tick 预算行**：写路径不进 `_tick_once`，与 16.6ms / 8.3ms 红线无关。
- **不覆盖 FastAPI 路由层开销本身**（那是框架常数，非项目回归面）。
- **不用它替代 CRUD 的 21 钉**（正确性/保险丝/ProblemDetail 都归功能钉）。

---

## 3. 升级触发条件（**任一满足 → 立项**，否则维持「预备行」）

1. **anchor load 在生产定时化**：`orchestrate_load_anchor` 从「操作驱动」变成**每帧/每 tick/定时器驱动**（例：自动回退、checkpoint 恢复）——**频度从 0–几十次/会话跳到 ≥60 次/秒**，此时每次写都吃事件循环预算，必须建红线。
2. **出现写侧批量入口**：如「一次导入 N 个世界档」、初始化预置档、恢复后补写——`N` 是变量，O(n) 风险真实存在（§2.1-2 的摊销行才真正有意义）。
3. **CRUD 写路径实测跨档发散**：`bench-plan.md` §4.1 的相对漂移（median:25%）在 CI 轮次间对 anchors 相关行 >25%（**当前 baseline.json 无 anchors 行，本项实际按 §1.3 记「待建」**）。
4. **出现并发写竞争者**：多 worker 部署 / WS 驱动与 HTTP 同时写（届时 A2 的单进程锁假设破产，**锁/事务语义变更**先于性能立项）。

> **反过来说**：以上都不满足时，给 CRUD 写路径建 bench 行 = **给一个永不执行的分支上红线**，
> 违反 `bench-plan.md` §0 的定位（bench 是回归检出，不是覆盖率）。

---

## 4. 若立项的实现形态（供后续单参考，**本单零代码**）

- 文件：`sim/tests/bench/test_bench_anchors_write.py`（新）。
- 口径：**定标机暖态中位**（`harness.assert_median_threshold` 的先例：`test_bench_perception.py`），
  fixture = 临时目录 SQLite + `init_database` + `AnchorStore`（与 `test_bench_structure.py` 同手法，
  `tmp_path` 隔离，**不碰开发者库**）。
- 起点：**`_record_proposal` 观察态**（`test_bench_fast_forward.py` 先例：只记录实测 vs 建议阈值，
  不断言）——CI 档位比未定标前不进硬断言（裁 1「硬断言只留定标机」）。
- 阈值常量：**不预先写 `thresholds.py`**；等首轮实测 + 定档后按 `m5-fast-forward-budget.md` §8
  三条件（3 次 nightly 全绿 + 只留定标机 + CI 档独立基线）转硬断言。
- 副作用控制：写 bench 会落盘（SQLite 文件）——**必须 `tmp_path`**，禁 `saves/`（`.gitignore` 已有）。

## 5. 边界与门禁
- **本单零代码**：不动 `sim/`、不动 `thresholds.py`、不动 yml、不动 `baseline.json`。
- 归界：**A2/A3 锁的语义选型属安全域/架构域**（`test_m5_anchors_crud.py` 已钉）；本单只从性能侧
  回答「要不要 bench」。**写路径的正确性回归不进 bench**（§2.2）。
- 未决：若 §3-1 触发（load 定时化），**应与触发它的架构单联动**，不要性能域单独立项。
