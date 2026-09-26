# M4-P3：意愿/独白热路径预算（B3 接线补数）
> 性能域（pi），2026-09-26。依据 `DESIGN.md` §10（意愿系统四档表现 + 公式）、
> M4-B3 实现（main `24eadb2`：`NpcRuntime.tick` 意愿注入缝）、`docs/perf/budget.md`
> §1/§2.4（tick 预算表与 L1 规模）、M4-P1/P2 先例（`m4-build-budget-preplan.md`）。
> 数据源：`sim/tests/bench/test_bench_willingness.py`（本件同批新增，13 用例）。
> 口径：与本仓 bench 同源 —— 本机暖态中位（`warmup_rounds=1` + median）、固定 seed、
> 50 NPC/tick（DESIGN §13 L1 规模）。**观察态**：阈值只记录不断言，硬断言待 nightly 后另裁。

## 0. 结论速览
| # | 问题 | 结论 |
|---|---|---|
| 1 | 意愿纯函数成本 | `willingness_expression` band=0 早退 **0.04µs/调用**（50 NPC = 2.2µs/tick）；band≥1 模板选取 **~0.4µs/调用**（50 NPC ≈ 20µs/tick）；`willingness_conflict` 合成 ~0.9µs/调用 |
| 2 | B3 注入缝本体 | band=0 **2.1µs/tick**（全早退）；band≥1 **~165µs/tick**（~3.4µs/NPC，独白事件构造主导） |
| 3 | runtime.tick 端到端增量 | None 基线 **0.720ms/tick**；band=0 +0.004ms；**band≥1 +0.20ms/tick**（~200µs = 表现面增量） |
| 4 | 提案红线 | `WILLINGNESS_TICK_LIMIT_MS = 0.35ms`（**只管注入增量**，不含 NpcRuntime 全量——后者走 `L1_UTILITY_TICK_LIMIT_MS=6.0`） |

## 1. 被测定路径（代码核对）
`sim/npc/runtime.py::NpcRuntime.tick`（50 NPC 装配）第 3 段：
```python
for nid, d in zip(active_ids, decisions, strict=True):
    events.append(npc_act_event(...))
    if self.willingness is not None:                      # M4-B3 注入缝
        expr = willingness_expression(self.willingness, npc_name=nid)
        if expr is not None:                              # band≥1 才有表现
            events.append(npc_monologue_event(
                tick=tick, npc_id=nid, form="thought", content=expr.monologue))
```
- `willingness` 是**全队共享**的注入对象（测试/接线缝）；真实运行由决策侧按 NPC 产 verdict。
- `willingness_expression`（`sim/agent/will.py`）纯函数：band=0 → `None`（零戏内产物）；
  band≥1 → 模板选取（`_TEMPLATES[band]`）+ `WillingnessExpression` frozen 构造。
- **表现面成本 = 每 NPC 每条独白事件**（band≥1），不是每动作（同 NPC 同 tick 一条）。
- 「最终都执行」：verdict 不回写效用分数、不拦截动作——**意愿系统只决定姿态**，
  所以新增成本全部落在事件构造侧（不在决策计算侧）。

## 2. 实测（本机暖态中位，2026-09-26）
### 2.1 意愿纯函数（50 NPC/tick 量级）
| 函数 | band | 实测/tick | 实测/调用 |
|---|---|---|---|
| `willingness_expression` ×50 | 0 | **2.2µs** | 0.044µs（早退） |
| `willingness_expression` ×50 | 1 | **18.9µs** | 0.378µs |
| `willingness_expression` ×50 | 2 | **20.6µs** | 0.412µs |
| `willingness_expression` ×50 | 3 | **20.4µs** | 0.408µs |
| `willingness_conflict` ×50 | — | **44.9µs** | 0.898µs |
- band 1/2/3 成本相当（差 <10%）：模板选取 + frozen 构造与 band 号无关。
- 纯函数侧合计（合成 + expression）≤ **65µs/tick**，远低任何红线。

### 2.2 B3 注入缝本体（expression + band≥1 独白事件）
| band | 实测/tick | 实测/NPC |
|---|---|---|
| 0 | **2.1µs** | 0.042µs（全早退，无事件） |
| 1 | **167.2µs** | 3.344µs |
| 2 | **161.4µs** | 3.228µs |
| 3 | **164.5µs** | 3.290µs |
- **成本主项 = `npc_monologue_event` 构造**（`NpcMonologuePayload` pydantic 校验 +
  `model_dump(mode="json")`）：50 条 ≈ 147µs（实测单测），占 band≥1 总成本的 **~88%**。
- expression 本身只贡献 ~20µs（§2.1）。

### 2.3 runtime.tick 端到端（None vs 注入，50 NPC 同 seed）
| 状态 | 实测中位 (ms/tick) | 增量 |
|---|---|---|
| None（基线） | **0.716** | — |
| 注入 band=0 | 0.701 | +0.004ms（~4µs；噪声级，实际零成本） |
| 注入 band=1 | **0.915** | **+0.200ms**（~200µs） |
| 注入 band=3 | **0.918** | **+0.206ms**（~206µs） |
- 增量与 §2.2 的注入缝本体（~165µs）一致（差值为 `active_ids` 过滤/事件列表增长）。
- 相对基线增幅 **27.9%**（0.200/0.716）——绝对量 ~0.2ms/tick，占 16.6ms tick 预算 **1.2%**。
- band=0 时增量落在测量噪声内（早退路径无事件），即**无表现 = 无成本**（§10 表语义纯）。

## 3. 提案红线（待裁）
### 3.1 `WILLINGNESS_TICK_LIMIT_MS = 0.35`（thresholds.py 已落，观察态）
| 项 | 值 | 依据 |
|---|---|---|
| 口径 | 注入态 `NpcRuntime.tick`（50 NPC，band≥1 最坏）**增量** | 不含 None 基线（后者走 `L1_UTILITY_TICK_LIMIT_MS=6.0`）|
| 实测 | 0.200ms | §2.3 band=1/3 |
| 建议阈值 | **0.35ms** | 0.200 × 1.7 ≈ 0.34 → 取整 0.35（裁 13 的 1.7x 慢机余量先例）|
| 破限排查 | ① 独白事件是否**表现面才产**（band≥1）而非每 tick 全量；② 独白事件构造是否退化（payload schema 膨胀 / 多次 dump）|  |
**为什么不吞 NpcRuntime 全量**：`NpcRuntime.tick` 整量已有 `L1_UTILITY_TICK_LIMIT_MS=6.0ms`
（budget §2.4）基线；本行**只管意愿缝插入的增量**，避免与 L1 行叠加双算。

### 3.2 不新增行（并入既有红线）
| 项 | 并入行 | 理由 |
|---|---|---|
| 独白事件 apply | `APPLY_P99_LIMIT_MS=0.04` + `test_apply_50_events_batch` | 走同一唯一写路径，无新机制；`NPC_MONOLOGUE` 入流后只需确保既有 apply bench 覆盖 |
| 独白帧投递（WS） | 无（uvicorn 边界，不进 tick） | `sim/api/ws.py` 在 `on_flush` 后投影投递，**不进 tick 固定序** |
| `willingness_conflict` 合成 | 本行（并入注入增量） | 决策侧调用，量级 ~0.9µs/调用 ≪ 红线 |

## 4. 观察项（不设红线，留预审核）
- **全队共享 verdict 是测试缝而非运行形态**：真实运行若「每 NPC 独立 verdict」，
  则 `willingness_conflict` 合成调用从 1 次/tick 变 50 次/tick（+45µs/tick，仍 ≪ 红线），
  但**独白事件数不变**（每 NPC 最多一条）——红线（0.35ms）对此形态仍有 ~1.6x 余量。
- **band≥1 是常态还是例外**：红线按「50 NPC 全部 band≥1」最坏取值。若真实运行中
  band≥1 是少数（如 10% NPC），实际增量 ~20µs/tick（10x 余量）；建议监控
  `npc.monologue` 事件率（可并入 M4 行为链观测）。
- **独白事件构造是唯一成本主项（~88%）**：若未来要压成本，路径是 payload/dump 优化
  （而非 expression）。当前量级（0.2ms/tick）无优化必要（YAGNI）。
- **16x 档**：4x/16x 下每 tick 预算降至 4.16/1.04ms，若独白每 tick 全量产（band≥1），
  0.2ms 占 4x 档 4.8%、16x 档 **19%**——建议独白**只在表现面渲染帧产**（客户端可见时），
  或按 `budget.md §4` 降采样（与 L1/感知同款）。
