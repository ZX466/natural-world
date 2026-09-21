# L1 动作白名单与升格隐藏属性契约（docs/security/l1-whitelist.md）

> 维护：Codex（安全/合规/风险域）· 依据：DESIGN.md v2.1 §16、m2-npc-cognition.md §1.2/§2.2、
> self-unknown.md §2/§4 · 日期：2026-09-21
> 状态：M2-S2 交付稿。审查对象：`sim/npc/actions.py`（Claude 架构域初版草案）；
> 契约实现：`sim/npc/contract.py` + `sim/tests/test_t1_l1_whitelist.py`。
> 评审：cline。本文件是 M2-S2 的验收口径与运行时接缝说明。

## 0. 一句话

L1 效用 AI 的动作面收窄为六项白名单（`NpcActPayload` params 逐动作白名单键），
防 payload 夹带越权字段；NPC 升降格（L1↔L2）时隐藏创伤属性（自我未知）的
`hidden`/`triggered` 状态**随事件流传递**——L1 期间触发的属性升格后仍可提，
触发窗口外直陈仍被 `hidden_leak_scan` 拒绝（闸门 + 记忆写入双防线）。

## 1. L1 动作白名单（对 `sim/npc/actions.py` 草案的审查）

### 1.1 白名单常量（架构域已落，本节为审查结论）

- `ACTION_WHITELIST`：`move` / `work` / `eat` / `rest` / `wander` / `request_chat`——
  与 m2-npc-cognition §2.1「六项」一致（移动/工作/进食/休息/闲逛/交谈请求）。
- `ACTION_PAYLOAD_KEYS`：逐动作白名单键（`move: path`、`work: site`、`eat: food_id`、
  `rest: hours`、`wander: radius`、`request_chat: to_npc`）——`NpcActPayload.params` 是
  自由 dict，扩展时防夹带字段靠这层。
- `is_action_allowed(action)` / `payload_keys_allowed(action, keys)`：纯函数判定。

### 1.2 语义一致性审查（安全口径）

| # | 审查点 | 结论 |
|---|---|---|
| W1 | 动作集与架构稿一致 | ✅ 六项逐一对照 §2.1 |
| W2 | 每动作有 payload schema | ✅（测试断言 `ACTION_PAYLOAD_KEYS` 覆盖白名单全集） |
| W3 | `payload_keys_allowed` 对未知动作拒绝 | ✅ `is_action_allowed` 先行短路 |
| W4 | `request_chat` 是升格触发器之一 | ✅（m2-npc-cognition §1.2 L1→L2 三触发条件含「发起对话」） |
| W5 | `params` 值类型 `dict[str, str]` | ✅（`NpcActPayload` pydantic `extra=forbid` + 类型约束） |
| W6 | 值域校验（如 `hours`/`radius` 数值） | ⚠ 不在白名单层做——值域归 utility/引擎消费侧校验，白名单只管「键是否允许」 |
| W7 | 白名单是安全边界还是功能约定 | **功能约定**：L1 是确定性代码，无 LLM 注入面（架构稿 §2.2）；白名单防「扩展时无意识夹带」，不是防对抗样本 |

### 1.3 与 M1 闸门的关系（沿用架构稿 §2.2）

L1 决策**不走 IntentGate**（效用函数是确定性代码）；L1 产出的 `request_chat`
升格 L2 后，其 LLM 输出照常过闸门（`revalidate_at_execution`，M2-S1 口径）。
白名单是 L1 层的「动作枚举」，不是 LLM 输出边界——两者职责不同，不合并。

## 2. 升格隐藏属性契约（runtime 接缝，本树实现）

### 2.1 状态传递

升格（L1→L2）与降格（L2→L1）由事件流表达（`EventKind.NPC_LOD_CHANGE`，
C4 唯一写路径）。隐藏属性状态不进事件 payload（事件流是戏外层，直陈词面
进事件会永久落库——违反 S1「唯一入口」），而是 runtime 内存态传递：

- runtime 每 tick 对活跃 NPC 调 `evaluate_triggers(profile, context_text)`，
  产出该 NPC 的 `triggered: frozenset[str]`（浮现窗口按 tick 重估）；
- 升格 L2 时：runtime 把当前 `triggered` 集合传给 LLM 装配（处境/内感受叙事
  只含已触发属性）与闸门（`revalidate_at_execution(hidden, triggered)`）；
- 降格 L1 时：runtime 把 LLM 期间最后已知 `triggered` 集合传给
  `MemoryWritePipeline.write(hidden, triggered)`——LLM 结论压缩写回记忆时，
  未触发属性直陈仍拒写（降格不降防线）。

### 2.2 本树实现（`sim/npc/contract.py`）

`HiddenState`：一个 NPC 在某 tick 的隐藏属性快照（`profile` + `triggered`），
携带三个消费侧方法（全部纯函数，可重放）：

- `evaluate(context_text) -> HiddenState`：tick 重估触发窗口（self-unknown §2）；
- `check_reason(reason) -> bool`：`reason` 是否含未触发属性直陈
  （供闸门/降格写回前的降级检查，`hidden_leak_scan` 同口径）；
- `gate_kwargs() -> dict`：传给 `IntentGate.revalidate_at_execution` 的参数形
  （`hidden=..., triggered=...`）；
- `memory_kwargs() -> dict`：传给 `MemoryWritePipeline.write` 的参数形（同上）。

`HiddenState.empty()`：无隐藏属性 NPC 的恒等值（`profile=None, triggered=frozenset()`），
各消费点零分支透传。

### 2.3 防线一致性（T1 测试断言口径，`test_t1_l1_whitelist.py`）

| 路径 | 断言 |
|---|---|
| L1 白名单 | 六动作全集锁定；payload 键逐动作白名单；未知动作/未知键拒绝；`request_chat` 在白名单内（升格触发器语义） |
| 升格传递 | `HiddenState.evaluate` 触发窗口重估正确；`gate_kwargs`/`memory_kwargs` 形状正确；触发中的属性直陈放行、未触发直陈拒绝 |
| 降格不降防线 | 降格写回走 `memory_kwargs`，未触发属性直陈 → `REASON_HIDDEN_LEAK` 拒写 |
| 降级检查 | `check_reason` 与闸门拒绝原因一致（未触发直陈 → True）；行为暗示可议（走路瘸不命中） |
| 恒等值 | `HiddenState.empty()` 下闸门/记忆写入行为与 M1 一致（零回归） |

CI：`test_t1_l1_whitelist.py` 按文件路径独立红灯信号（`.github/workflows/ci.yml`，
沿用 `test_t1_self_unknown.py` 做法）。

## 3. runtime 调用点契约（给 Claude 架构域，M2-A2/A3 落地时对齐）

```python
# runtime 每 tick（伪代码，落地在 sim/npc/runtime.py，归 Claude 架构域）：
hidden_state = hidden_state.evaluate(context_text)          # ① 重估触发窗口
if npc.lod == 2:
    prompt = assemble(..., hidden=hidden_state.gate_kwargs())  # ② LLM 装配只含已触发
    verdict = IntentGate().revalidate_at_execution(
        intent, state, npc_id, planned_tick, **hidden_state.gate_kwargs())
else:
    # L1 产出的对话请求升格 L2 后照常过闸门（架构稿 §2.2）
    ...
# 降格写回（L2→L1）：
result = MemoryWritePipeline().write(
    npc_id, compressed_reason, source="reason", ...,
    **hidden_state.memory_kwargs(),
)
```

- runtime 持有 `HiddenState`，不持有 `HiddenProfile` 的构造权（profile 来自
  `NpcHealth` ORM 行 → `HiddenAttribute` 映射，opencode 持久化侧已对齐 §6 self-unknown.md）；
- 本树不实现 runtime（不越界到 Claude 架构域），只交付状态契约与测试口径；
- 若 runtime 侧调用形与本契约不一致，以本文件 §2.2/§3 为准（安全域 owner：Codex，CR）。

## 4. 维护与责任

- 白名单常量（`actions.py`）变更走 Claude 架构域 CR，安全域（Codex）复核动作语义与 payload 键；
- 本契约（`contract.py` / 本文件 / 测试）变更走 Codex CR；
- 测试文件无专属 marker（随 `-m "not bench"` 全量跑），CI 按文件路径独立信号防静默排除。