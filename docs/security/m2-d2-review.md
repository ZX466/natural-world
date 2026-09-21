# M2-D2 安全评审（docs/security/m2-d2-review.md）

> 维护：Codex（安全/合规/风险域）· 对象：opencode M2-D2（main `7d0cabc`）· 日期：2026-09-21
> 结论：**通过（含 2 条 MEDIUM 建议、2 条观察记录、4 条正面确认）**。无 CRITICAL/HIGH。
> 评审范围：`sim/core/persistence/npc_store.py`（materialize/flush_tick/writeback_downgrade_memory）、
> `sim/tests/test_m2_runtime_store.py`（15→18 用例，本评审增补 3 条）、`docs/data/schema.md` §14/§15。
> 评审基线：`memory-scan.md`（S1-S6）、`self-unknown.md`（§2/§4）、`l1-whitelist.md`（§2/§3）、m2-npc-cognition.md §1.2/§2.2。

## 1. 逐项核验（任务书三点）

### 1.1 writeback_downgrade_memory → MemoryWritePipeline.write(source="reason")：S1 防线在降格路径不破 ✅

| # | 核验点 | 结论 |
|---|---|---|
| W1 | 调用形与 self-unknown.md §2.3 一致：`hidden`/`triggered` 参数透传 `MemoryWritePipeline.write`，source 硬编码 `"reason"` | ✅ npc_store.py:168-194 |
| W2 | 拒写返回结构化 `reason="hidden_attribute_leak"` + 命中词面 `hits`（供观测/重规划，不含 LLM 原文） | ✅ 本评审增补测试 `test_writeback_reject_returns_reason_and_hits` |
| W3 | 触发窗口内属性直陈 → 正常写回；混入未触发属性仍拒写（防线不过严也不过松） | ✅ 增补 `test_writeback_triggered_attribute_allowed` / `test_writeback_triggered_mixed_still_rejects_other` |
| W4 | 拒写不落库（S1 守卫）：拒写结果 entry=None，无任何持久化旁路 | ✅ 既有测试 `test_writeback_rejects_hidden_leak`（D2 原有）+ Pipeline 逻辑 |
| W5 | event_seq 缺省 None（推理转述语义，memory-scan.md §4） | ✅ docstring + 默认值 |

### 1.2 npc_store materialize/flush_tick 投影：payload 校验 / SQL 参数化 / 无日志泄密 ⚠ 2 条 MEDIUM

**通过的核验点：**

- **投影 payload 边界校验**：`_project_lod_change` 对 `npc_id` 非空 + `to_lod ∈ {0,1,2}` 显式校验，
  非法即抛 `NpcStoreError` 且整批回滚（测试 `test_lod_change_unknown_npc_rolls_back_events`）；
  `_project_matter` 对 `matter_id` 非空校验。✅
- **SQL 全参数化**：`materialize` 用 `select(NpcProfile).where(NpcProfile.id.in_(ids))`
  （SQLAlchemy 参数化），无字符串拼接 SQL；flush_tick 全部走 ORM session。✅
- **无日志/异常旁路泄隐藏属性**：npc_store.py 全模块零 logger/print；异常消息只含
  结构化 payload 的 npc_id/matter_id（`{payload!r}`——payload 本身不含隐藏属性词面，
  见 O1 观察），不落 compressed content。✅
- **降格写回不在 flush_tick 事务内**：writeback 是独立的 MemoryWritePipeline 调用，
  与事件投影解耦（正确的关注点分离；降格判定事件化，写回上游触发）。✅

**MEDIUM（建议下轮修正，不阻断）：**

| # | 发现 | 影响 | 建议 |
|---|---|---|---|
| M1 | `SqlEventStore.append()` 接受裸 dict（`events: list[dict]`），payload/actor/witnesses 不经
  `NpcActPayload`/`NpcLodChangePayload`/`MatterPayload`（extra=forbid）二次校验——实测可写入
  `smuggled` params、伪造 actor_id/witnesses（评审时已实测验证）。flush_tick 主路径经
  `flush_rows(event_list)`（WorldEvent → to_store_dict）收窄，但 `append` 的协议面未收窄。 | 数据域内部误用可绕过
  payload 白名单；测试已直接用裸 dict（test_m2_runtime_store.py:234）。 | ①`append` 增加按
  event_type 的 payload 模型校验（复用 events.py 的 pydantic 模型，reject extra）；②或把
  `append` 签名收窄为 `Sequence[WorldEvent]`（走 flush_rows）。归 opencode（数据域），改动小。 |
| M2 | `materialize()` 只查 `npc_profiles`，不加载 `npc_health` 隐藏行 → runtime 升格 L2 时
  `HiddenState` 无法从 store 侧装配（self-unknown §2.2 契约的持久化半边缺位）。M2 内无 L2 调用
  故不构成现网泄露，但 M2-A3 升格落地时会卡在这。 | 升格路径无法拿到 HiddenProfile →
  要么全量直陈闸门误拒，要么无检查裸奔。 | 补 `materialize_hidden(npc_ids) -> dict[str, HiddenProfile]`
  （或 materialize 返回聚合对象），映射 npc_health.hidden=1 行 → HiddenAttribute。归 opencode +
  Claude（M2-A3 runtime 接线）。 |

**观察（记录，不要求动作）：**

| # | 观察 | 说明 |
|---|---|---|
| O1 | `MATTER_*` payload 的 `note` 字段（世界内语言，如「耐久归零坍塌」）随事件落 events 表，但不投影进
  matter_state（该表无 note 列）。事件流是戏外层，note 不进感知帧/独白 prompt——当前无泄露面。 | 若未来把 matter
  事件 note 转译进感知叙事，需先过 banned_words/hidden_leak_scan（感知层归 Claude 域）。 |
| O2 | `NPC_LOD_CHANGE.payload.reason` 同理落事件流（O(1) 戏外字段，枚举值 leave_range 等）。 | 同 O1：若
  reason 语义扩展为自由文本，需约束词面或过扫描。 |

### 1.3 结论落 docs/security/ ✅

本文件即评审存档；CRITICAL/HIGH：无。测试增补 3 条已随本评审提交（18 用例全绿）。

## 2. 正面确认（值得保留的设计）

1. **投影同事务**：flush_tick 把事件落库与 LOD/matter 投影绑在同一事务，投影抛异常整批回滚
   （无半写）——与 entropy_log 原子性同构，测试覆盖到位。
2. **writeback 走唯一入口**：降格写回不绕过 MemoryWritePipeline（S1 守卫在数据层被正确复用，
   而不是在 store 层重写一遍扫描——避免了「同一防线两处维护」的漂移风险）。
3. **materialize 一次查询**：50 NPC 批量物化单 SELECT + `id.in_()` 子集过滤，符合 §1.3
   禁逐 NPC 查询。
4. **extra=forbid 全覆盖**：NpcLodChangePayload/NpcActPayload/MatterPayload 三模型都
   `extra="forbid"`，工厂是构造唯一入口（问题只在 M1 的 append 协议面）。

## 3. 评审后动作

| 动作 | 责任 | 状态 |
|---|---|---|
| 增补 3 条测试（W2/W3 覆盖） | codex | ✅ 本次提交 |
| M1 append 协议面校验 | opencode | 建议下轮（MEDIUM） |
| M2 materialize_hidden / 升格装配 | opencode + Claude | M2-A3 前落地（MEDIUM） |
| O1/O2 事件 note/reason 进叙事前的扫描 | Claude（感知层） | 记录在案 |
