# 第十六轮复核（主树，2026-11-01）

**结论：不可收编。** 回执声称的 M3 社会层接线在生产路径上**不通**——
`witnesses` 恒空 ⇒ `knowledge` 表恒 0 行。18 条新测试全绿，但**没有一条跑真实 `lifespan`**，
全部用手造帧/事件，因此没照见这个断点。

## 一、根因（一条，堵死两条验收路）

`sim/perception/senses.py:271` 把 `Observation.subject` 设成**中文显示名**：

```python
label = display_name_of.get(eid, rtoken_of(eid)) if display_name_of is not None else rtoken_of(eid)
raw.append((Channel.VISION, label, desc, strength))
```

同一个 `label` 既用于叙事文本，也用作 `subject`。而 `witnesses_of_emerge`
（`sim/npc/evidence.py:114`）拿 `subject` 与 `rtoken_of(npc_id)` 比较：

```python
tokens = witnesses_of_emerge(latest, subject=rtoken_of(subject))
```

⇒ **永不匹配**。`sim/perception/frame.py:37` 的注释 `subject: str  # rtoken` 是过时的。

### 铁证（纯函数，无 IO）

| 帧形态 | `witnesses_of_entity_emerge(...)` 结果 |
|---|---|
| 生产形态（`subject="赵铁"`） | `([], 9)` |
| codex 测试形态（`subject=rtoken_of(...)`） | `(['villager_01'], 9)` |

复现：`PYTHONPATH=. uv run python .orca/audits/round16-review-2026-11-01/probe.py`

## 二、实况验证（真实 `lifespan`，零注入）

### 2.1 全新库（600 tick）

```
events: 0 → 3775
relationships: 0 → 25   ✅
knowledge:     0 → 0    ❌
npc.hidden_emerge: 2 条，witnesses 非空: 0 条
```

### 2.2 主树真实库副本（`world.db` 45MB，187857 events 的健康库）

> 主树库有且仅有 1 个 `world.create`，`restore_world` 可正常恢复（tick 36001 / 54 实体）。

```
events:        187857 → 191674  (+3817)
relationships: 0 → 37           ✅
knowledge:     0 → 0            ❌
```

**注**：codex 树的 `world.db` 有 **83 个 `world.create`**，`restore_world` 抛
`world history must contain exactly one genesis`。codex 回执说"演练无法启动"是**真的**，
但那是**该树库的历史缺陷**，与本轮无关。主树库健康，可直接演练。

## 三、验收面逐条判定

| # | 要求 | 结果 |
|---|---|---|
| 1 | 实况跑起来后 `knowledge`/`relationships` 有行 | **`relationships` ✅ / `knowledge` ❌**（半条） |
| 2 | `witnessed` 路可达，`evidence_seq` 指真实事件 | **❌ 不可达**（witnesses 恒空） |
| 3 | `told` 路可达，`source_knowledge_id` 指上行 | **❌ 不可达**（以 knowledge 行为源，同上被堵死） |
| 4 | 拒绝路径零副作用 | ✅ 有负向测试 |
| 5 | 关系漂移与 `chat_ledger` 一致 | ✅ 37 行落库，`restore_relations` 回灌 |
| 6 | `norms` 进 prompt 且非空 | ⚠ 已接线，但 `knowledge` 恒空 ⇒ `NormSlice` 恒空 |
| 7 | 全量门禁绿；协议 1.14；events 只增不减 | 见门禁节 |
| 8 | bench tick 预算不回归 | **2F 是既有基线**（主树无本轮代码同样 2F，单跑两条均通过） |

## 四、codex 回执与实测的差异

| 回执说法 | 实测 |
|---|---|
| "bench 2F … sound baseline passes" | 主树**无本轮代码**也 2F，且 `test_perception_sound_50npc` 同样失败；两条单跑均通过 ⇒ 抖动，非回归 |
| "Fresh persistent production lifespan rehearsal passes: knowledge2" | 那是 `verify_live.py` **手写注入** `HiddenState` + 伪造 `PerceptionFrame` 得来的；零注入实跑得 **0** |
| "M3 witness->knowledge->told->norms production wiring implemented" | 代码已接，但标识错配使其在生产恒不触发 |

## 五、次要问题（收编前应一并处理）

1. `main.py:373-376` 用 `loop.enqueue(retelling)` 后立刻 `loop.pending_events.pop()`，
   靠"入队再弹出"来获得 `bus.apply` 的状态更新——脆弱手法，注释应写清意图。
2. `prepare_retell_events` 的 `break` 在 `for row` 内层，每条 `npc.chat` 只产 1 条转述；
   这是有意（配 `reserved` 去重），但 docstring 没写。
3. `KnowledgeLearnedPayload.require_evidence` 在 validator 里跑 `MemoryWritePipeline().scan_fact`
   ——校验器里做业务判定，且每次构造 payload 都重建 pipeline。
4. `main.py:711-718` 构造的 `WorldEvent` **没传 `branch_id`**，而 `WorldEvent.branch_id`
   默认是 `"main"`（`events.py:611`）⇒ 在子分支上会把知识行写进 `main` 分支。
   当前因 witnesses 恒空而未触发；修好根因后这条会立刻暴露。
   （对比 `prepare_retell_events` 里是显式传了 `branch_id=branch_id` 的。）

## 六、修法建议（下一轮派单）

最小改动：在 `witnesses_of_entity_emerge` 里建立 **显示名 → entity_id** 的反查表，
或改用 `display_name_of` 双向映射；**不要**改 `Observation.subject` 的语义
（叙事要人话，改了会破 T1 叙事口径与既有感知测试）。

必须补一条**真跑 `lifespan` 的集成测试**——现有 18 条全是手造帧，这是本轮漏检的结构原因。
