# M4 巧合连锁安规预审（docs/security/m4-coincidence-preaudit.md）

> 维护：Codex（安全/合规/风险域）· 依据：DESIGN.md v2.1 §11（巧合连锁/不可预测性）、§14（建造）、
> §16（T1 六类+T2/T5 + 补充断言「luck 不出现在感知帧字段」）、§19（禁止事项一/三/四/九）、
> m4-plan.md 批次 D（裁 14-5/14-6）、m4-security-preplan.md §4 L 系（裁 15 已定稿）· 日期：2026-09-26
> 树：ZX466/codex @ `240f9f7` · 状态：**提案制**——不动码；词面面（L-1/L-2/L-3）已在 M4-S1 定稿不重复。
> 本文覆盖**机制面**：状态存哪、值往哪不可见、体验 vs 归因、T5 熵流种子边界。

## 0. 一句话

巧合连锁的安规双判据是「**Agent 不可见 + 重放可重建**」：抬升状态的真相只能在
**事件流**（重放可折叠重建），其值在任何 Agent 可见面（感知帧/prompt/独白/WS）零字段零词面；
Agent 只能说「今天不顺」（体验），不能说「运气差/概率低/有人在整我」（机制归因/操纵感）。

## 1. 现状锚点（2026-09-26 实测）

| 件 | 实测 | 缺口 |
|---|---|---|
| `sim/core/entropy.py` | `EntropyMixer.mix`（采 `os.urandom` → 产 `ENTROPY_INJECT` 事件）/ `replay_mix`（事件材料重建）齐备 | **无生产调用方**（grep：仅 `entropy.py` 自引用）——M2-P1 留的「M1 EntropyMixer 接线回填」至今未做 |
| `sim/core/rng.py` | `RngRegistry.reseed` 是哈希链推进（`sha256(材料+熵)`）；未注入流按 `sha256(world_seed:name)` 纯函数派生；`draw_key`=材料指纹 | 巧合链**专用流尚不存在**（生产无 `generator()` 调用点，matter 走独立的 `np.random.default_rng(seed)`） |
| `sim/core/world.py` | `_apply_entropy_inject` = **状态层 no-op**，注释「registry 重建由重放装配层做」 | 重建装配层**未实现**（D 批必建，见 §2 方案 A） |
| `TickContext.rng_cache` | 抽签缓存**不入快照**（键=材料指纹，材料变则缓存自然失效） | 内存态 = 不可重建 → 只能做缓存，不能做真相 |
| `WorldState.state_hash()` | T2 逐位一致断言对象已就位（`world_seed` 在状态里） | 巧合链的 fold 结果若不进 `state_hash` 覆盖范围，T2 断言会漏 |
| 词面面 | `BANNED_WORDS_META` 已含 `运气/luck/随机数`；白名单 `棋子运气/手气好/模特儿` | 无 `概率/注定`（V4 待裁） |
| T5 | 无 10 种子×10 游戏日 harness（仅 `test_m3_retell_golden.py` 2 例） | 熵流种子边界未定（本单 §4） |

## 2. 抬升状态存哪：方案对比（双判据 = Agent 不可见 + 重放可重建）

| 方案 | Agent 不可见 | 重放可重建 | 判定 |
|---|---|---|---|
| **A. 事件流为唯一真相 + fold 派生**（新小事件族，如 `coincidence_lift`，payload 载 `npc/scope`、`opened_tick`、`window_ticks`、`magnitude`；实时值 = fold(事件前缀)） | ✅ 天然：事件 payload 不进 prompt（裁 15 已定「dev 日志留痕 OK / prompt·戏内 UI 禁入」） | ✅ 纯函数 fold 两次同序 = 逐位相等（同 `fold_matter_snapshot` 先例，M3-C2/D3 已落） | **主张采纳** |
| B. 内存 registry（照 `rng_cache` 形态：抬升表挂 TickContext/缓存层） | ✅ | ❌ **进程内才在**——读档/重放丢失；`rng_cache` 能这么干是因为材料可由 `(world_seed, name)` 纯函数重建，抬升值不是 | 否决（违反 C5/T2） |
| C. 新表（`coincidence_state` 或 `npc_luck` 列） | ⚠ 需额外护栏防物化面泄漏 | ✅ | 否决：①真相双写（事件 + 列）→ 漂移面；②违 §19-1「世界状态不走直接赋值」仍要事件驱动，白担一层；③M3 已定「熵态真相在事件流、投影瘦身」同款纪律（裁 14-2） |

**A 的具体形态**（供 Claude 施工参考）：
- 事件族最小集：`COINCIDENCE_LIFT_OPEN`（开窗）/ `COINCIDENCE_LIFT_CLOSE`（关窗；或按 `opened_tick+window_ticks` 纯派生不需显式关）；
- `magnitude` 数值**允许进 payload**（裁 15 先例：熵流材料/流名同属元信息，dev 留痕 OK）；
- 实时抬升 = `fold(events[:seq])` 派生缓存，缓存键 = 最后一个 lift 事件 `seq`（材料指纹同款思路）；
- **流名卫生**：建议用 `mix.adverse`（中性）而非 `luck.*`——dev 面也不必自曝玄学语义。

## 3. T1 钉子建议（S1 L 系 → 「值本身」层）

S1 §7 已建议 `test_t1_m4_entropy_invisibility.py`；本单**不另开文件**，建议在同一文件补四条：

| # | 断言 | 判据来源 |
|---|---|---|
| M-1 | lift 事件的 `stream`/`magnitude`/`window_ticks` **值**不出现在 `assemble_prompt` 产物（逐 Slice 断言：Situation/Input/Monologue 三面） | §19-三（禁元信息词进 prompt/日志/UI）+ L-1 延伸 |
| M-2 | `Observation`/`PerceptionFrame` **无 luck/lift 字段**（字段表断言，frozen model 的 `model_fields` 集合比对） | DESIGN §16 补充断言明写「luck 不出现在感知帧字段」 |
| M-3 | WS `state_delta`/`full_snapshot` 文本**无 lift 数值/流名** | §19-三（戏内 UI 面）+ 裁 15 |
| M-4 | fold 纯函数性：同事件序列 fold 两次**逐位相等**；与 `WorldState.state_hash()` 的覆盖关系写进断言 | C5/T2 |

> 断言类标注：M-1~M-4 全部 **[T1]**（无 LLM、秒级、每提交）。

## 4. 「只觉得今天不顺」：体验 vs 归因 合规口径

DESIGN §11 原文是「运气状态对 Agent 完全不可见——**它只觉得今天不顺**」：
「不顺」是** phenomenological 体验**（可），「运气差」是**机制归因**（不可）。
现 banned_words 已含 `运气`（白名单仅棋牌/手气），故「我运气不好」已被词表拦——
合规口径与词表天然同向，提案只补**判例三档**：

| 档 | 表述族 | 判定 | 理由 |
|---|---|---|---|
| ✅ 体验 + 自我归因 | 「今儿诸事不顺」「手头总不凑巧」「我这两日心慌」 | 允许 | 第一人称 phenomenological，无机制词、无外部意志体 |
| ⚠ 灰区（待裁 V3） | 「这镇子近来邪门」「老盯着我」「净赶在我头上」 | **建议放行** | 被动感受表述；巧合连锁不是命令源，不触 §19-四 |
| ❌ 机制归因 / 操纵感 / 元信息 | 「我运气差」「八成要倒霉」「概率对我不利」「有人在整我」「老天的骰子」「被系统调了」 | 硬拒 | 前四命中 banned 词面；「有人在整我」= 指向外部意志体 = §19-四禁令同族（操纵感） |

**执行面**：T4 探针 P4（运气诱导，8 条，M4-S1 §6.1）在批次 D 落地后按此判例表判定；
判例表变更走 CR（安全域 owner=Codex，同 self-unknown §7 纪律）。

## 5. T5 golden 的安规注入面：熵流种子边界

**问题**：`EntropyMixer.mix` 采 `os.urandom` = 真随机（§11「确定性给开发者，不可预测给玩家/Agent」）。
若 golden 跑带真随机注入，「守恒/完成率/无孤儿变更」断言在两次跑之间漂移 → **T5 不可重放 = 失效**。

**提案（三条边界）**：

| # | 边界 | 判定 |
|---|---|---|
| G-1 | **熵模式分档**：T2/T5 用 `entropy_mode=fixture|off`（**禁 live 真随机**）；nightly 可 live 但只断言「不崩 + 无孤儿变更」，**不做逐位/比率断言** | 硬红线 |
| G-2 | **种子基线**：无注入流的材料 = `sha256(world_seed:stream)` 纯函数（现状已如此）；巧合链专用流 `mix.adverse` 走同纪律——golden 档只由 `world_seed` 定，不注入 | 硬红线（现状已满足） |
| G-3 | **注入顺序敏感**：`reseed` 是哈希链推进（`sha256(材料+熵)`）→ 同一批注入**顺序不同则结果不同**。故重放必须按 `events.seq` 序 fold；同 stream **禁并发注入**（单写者纪律） | 硬红线（新造点必须遵守） |

**fixture 形态**（若 golden 要真随机味道）：每个 seed 预生成 `entropy_fixtures.json`
（seed → [{tick, stream, material_hex}]），跑时按序 `replay_mix` 注入 → 既真随机又可重放；
**本单主张先用 `off`**（YAGNI，§11「确定性混沌」覆盖日常演化），fixture 留 M5。

## 6. 责任分工与验收类标注

| 面 | 实现域 | 本域职责 | 验收类 |
|---|---|---|---|
| 巧合事件族 + fold 重建层（§2 方案 A） | Claude（D 批主体） | 方案主张 + 形态参考 + 钉子口径 | [T1] M-4 |
| 值零可见（§3） | Claude（接线） | 四条断言（本单出，Claude 落钉子） | [T1] M-1~M-4 |
| 体验 vs 归因（§4） | Claude（独白措辞）+ codex（判例 CR） | 判例表 owner | [T4] P4 / [T1] 词面扫描 |
| 熵流种子边界（§5） | Claude（熵模式开关）+ cline（CI/T5 harness 配置） | 边界口径 | [T1] M-4 / [T5] golden |

## 7. 待裁决点（报主树）

1. **V1**：巧合 lift 事件族命名 + payload 字段集；`magnitude` 数值是否允许进 payload
   （我主张允许，裁 15「dev 日志留痕 OK」先例）。流名建议 `mix.adverse`（中性）。
2. **V2**：T5/T2 熵模式 = `off`（我主张，YAGNI）vs `fixture` 重放。
3. **V3**：灰区表述「老盯着我/净赶在我头上」是否放行（我主张放行；不放行则巧合体验
   只剩纯情绪表述，§11「只觉得今天不顺」的实现面会很窄）。
4. **V4**：`BANNED_WORDS_META` 是否新增 `概率`/`注定`（我主张加「概率/注定」；
   **「命中/骰」不建议加**——战斗语境「命中」是自然词，误报面大，走白名单兜）。