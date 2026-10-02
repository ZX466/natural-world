# M5 fork 当前行交接口径稿（R-4.4 数据面裁决准备 · opencode）

**归属**：数据面口径（我域）＝ 本文；**施工**（`sim/core/persistence/fork.py` 改动）＝
Claude 的 R-4 施工单；条款出处 = `m5-r4-active-branch-contract.md`（R-4.1 / R-4.2.2 /
R-4.3 / R-4.4 / R-4.5）。本文只定「怎么交接才对」，不替施工单写码。

**背景**：A5 落了 `branches.is_current` + 部分唯一索引 `ux_branches_current`，并把
`append` 的按需开线收紧为「仅当无当前行才可开线」。**唯一未落项 = fork 的当前行交接**：
head-fork 之后当前行仍停在**已被封存**的父分支上。

---

## 0. 结论（TL;DR）

1. **head-fork 且父就是当前行** ⇒ **同一事务**内「先清父 `is_current` → 再置子 `is_current`」。
2. **父不是当前行**（从读档子线再分叉）⇒ **不交接**，子分支 `is_current=0`
   （否则一次读档就把玩家正在跑的线悄悄换掉）。
3. **anchor-fork（历史点回退，A3）** ⇒ **不交接**：父保持当前，子是读档线（`is_current=0`）。
4. **禁止**「一条 UPDATE 换手」——实测在本仓 SQLite 上**必然**撞唯一索引（§3）。
5. 交接失败 ⇒ 整批回滚（无子行、无克隆、父未封存）：**宁可不分，不留两个当前**（R-4.2.2）。

---

## 1. 现状与缺口（A5 遗留的具体形态）

`fork_from_anchor` 今天的写集：子行 `INSERT ... status='active'`（`is_current` 走
server_default 0）+ 父行 `UPDATE status='abandoned'`（**不碰 `is_current`**）。于是：

- 当前行 = **已封存的父分支**（`is_current=1` + `status='abandoned'`）；
- `current_branch_id()` 会返回这条**死线**（R-4.1 的读入口按 `is_current` 查，不加
  `status` 过滤——单一真源谓词）；
- 后果：POST 记档（施工后）会从被弃时间线取游标 ⇒ 又回到 R-4 的病；
  驱动若往父分支 append 会被闸门拒（`InactiveBranchError`，fail-closed，不污染）。

**不产生数据损坏**（闸门挡住了写入），但**读错**——所以交接必须落，且是施工单的一部分。

## 2. 事务边界

- 现有边界：`async with session_factory() as session, session.begin():`（`fork.py:317`）。
  交接**必须**落在这个事务内，与克隆同生共死。
- **禁止**「提交后补写」：那会开一个「零当前」窗口 ⇒ 读侧 `NoCurrentBranchError`，
  且窗口外的并发读者会看到没有世界线。
- 判据读取（父是否当前）**必须在同一事务内读**：事务外先查再写是 TOCTOU，两个并发
  fork（或 fork 与一次显式切档）会各拿到一个「我是当前行」的结论。
- 与 `preflush`（步 0，事务外先行，P1）无冲突：preflush 只冲父分支 in-flight 批次。

## 3. 部分唯一索引下「两步不得有中间态」的论证

索引 `ux_branches_current ON branches(is_current) WHERE is_current = 1` 的索引值恒为
1 ⇒ 两个 `is_current=1` 的行必然撞唯一约束。

| 写法 | 结果 | 依据 |
| --- | --- | --- |
| 两条 UPDATE、**同事务**、先清父后置子 | ✅ 通过 | 唯一性检查看得到本事务未提交的改动；读者在提交前只看到事务前的快照 |
| 两条 UPDATE、同事务、**先置子**后清父 | ✅ 也通过（实测） | 同上；但不建议——若日后有人拆成两个事务，它的失败模式是 IntegrityError 而非「零当前」，症状更难读 |
| 两条 UPDATE、**两个事务** | ❌ 中间态可见 | 清父与置子之间 = **零当前**窗口（读侧 fail-closed） |
| **一条** UPDATE 换手（`CASE WHEN id=:child THEN 1 ELSE 0 END WHERE id IN (:parent,:child)`） | ❌ **必然** IntegrityError | SQLite 在同一条语句内**逐行**改写并逐行校验唯一约束；子行先被改写时父行还是 1 → 撞索引。**行序未定义 = 不可依赖** |

> 实测（SQLite，行序对抗构造：父 id `z-parent` 排在子 `a-child` 之后）：单语句换手
> **3/3** 撞 `UNIQUE constraint failed: branches.is_current`；同事务两步两种次序均通过。

**结论**：**两步 + 同一事务 + 先清父**。单语句写法在本仓不可用，别再讨论。

## 4. 与开线闸（`CurrentBranchConflictError`）的次序

- fork **不走** `store.append`（直写 SQL，裁 6 (c)），因此**不触发**开线闸；
  闸门只约束 append 路径，两者没有先后耦合，不需要加锁。
- fork 之后的三种写入结果（期望态）：

| 场景 | 闸门反应 | 是否期望 |
| --- | --- | --- |
| 往**已封存父分支** append | `InactiveBranchError`（裁 5 原语义） | ✅ 分叉后父线封存 |
| 往**当前行（交接后的子分支）** append | 放行 | ✅ 世界继续 |
| 往**不存在的分支名** append（交接已落） | `CurrentBranchConflictError`（A5 收紧） | ✅ 分叉后不该再凭空开线 |
| 交接**未落**时往父分支 append | `InactiveBranchError` | ⚠️ 当前行的活线是子分支，父分支本就不该写；症状相同，根因是交接未落 |

## 5. 两种 fork 模式 × 归属对照（R-4.4）

| 模式 | 父是不是当前行 | 子 `is_current` | 父 `status` | 依据 |
| --- | --- | --- | --- | --- |
| head（现行读最近档） | 是 | **1**（交接） | `abandoned` | R-4.4 / R-4.2.2 |
| head（父非当前：从读档线再分叉） | 否 | **0**（不交接） | `abandoned` | R-4.5：不由时间戳或数量规则推断当前 |
| anchor（历史点回退，A3 未实现） | 是 | **0**（不交接） | **不动**（玩家还在跑它） | R-4.4 |

⇒「至多一个当前」与「多条读档子线并存」**不矛盾**：读档子线不是当前。

## 6. 施工清单（`fork.py`，供施工单照抄次序）

1. 事务内读父行当前位：`SELECT status, is_current FROM branches WHERE id = :pid`（并入现有
   步 1 的那次查询，**不加第二次往返**）。
2. 子行 `INSERT` **显式**写 `is_current`（不依赖 server_default）：head 且父是当前 ⇒ 1；
   否则 0。
3. head 且父是当前 ⇒ 同事务两条 UPDATE：`SET is_current=0 WHERE id=:pid` →
   `SET is_current=1 WHERE id=:cid`（次序即 §3 结论）。
4. anchor 模式 ⇒ **不动**父的 `is_current`。
5. `ForkResult` 加一个只读事实字段（如 `current_handover: bool`），编排侧与 D-6 告知帧
   可断言「当前行已交给子」，不必再查库。
6. **不改** `store.py`、**不新增迁移**（0012 已是 head）。

## 7. 钉子（哪些钉住本文）

| 钉 | 位置 | 钉什么 |
| --- | --- | --- |
| `test_switch_without_clearing_hits_index` | A5 `test_m5_branch_current.py` | 不清旧就置新 ⇒ IntegrityError（§3 同事务硬约束） |
| `test_handover_pattern_parent_clear_then_child_set` | 同上 | 载体能承载交接（同事务清父置子后真源即子） |
| `test_fork_from_current_line_keeps_single_current` | A6 `test_m5_anchors_branch_source.py` | 至多一个当前 + **交接前的现状记录**（父仍持当前位、子非当前） |
| `test_fork_from_archive_line_keeps_true_source` | 同上 | 从读档线分叉**不抢**当前行（§0.2） |
| `TestFailClosed` / `TestCursorTripleCoherence` | 同上（skip-locked，施工后转绿） | 交接后记档游标必须落在**活着的**当前线上 |

## 8. 风险与回滚

- 交接撞索引 ⇒ 整批回滚：无子分支行、无克隆行、父未封存（`ForkError` 语义，「宁可不分」）。
- **迁移回退纪律**：0012 的 downgrade 会 drop `is_current` 列与索引 ⇒ 回退后
  `fork.py` 里的 `is_current` 语句会直接报错 ⇒ **降 0012 必须同时回退 `fork.py`**
  （部署动作不是纯数据动作）。
- 与 R-4 施工的耦合：交接未落时，`current_branch_id()` 返回已封存分支；施工侧若先接读
  入口、后落 fork 交接，中间窗口内 POST 记档会读到死线的 seq。**建议同一次收编落两件**
  （或先落 fork 交接、再落 anchors 读路径）。