# M4 收官门预审（docs/security/m4-closure-preaudit.md）

> 维护：Codex（安全/合规/风险域）· 依据：m4-plan.md §4/§6（裁 14/15/16/17）、m4-preplan 同款
> S6b 三段式（预审-放行-动态）· 日期：2026-09-27 · 树：ZX466/codex @ `1f55579`
> 性质：**静态预审（提案制）**——只对表、只提缝；动态全量复验等 T5 首跑绿后跑（§7 待填）。

## 0. 结论速览

| 门 | 状态 | 说明 |
|---|---|---|
| M4 新安规面四钉子（99 用例） | ✅ 静态绿 | 实跑 99 passed（见 §1） |
| M3 旧钉子回归（141 用例） | ✅ 静态绿 | S6b 收官门资产零回归 |
| S4 10k 零回归 | ✅ 静态绿 | **7 passed**（裁 15-3「X7 唯一判梯」+ [规矩] 段仍闭环） |
| 功能/非性能全量 | ✅ 静态绿 | **1391 passed / 0 failed**（main `1f55579` 数字一致） |
| pyright / ruff | ✅ | 0 errors / clean |
| T4 探针↔实现映射 | ⚠ **半闭环** | P1-P3 有实现对象；**P4/P5 前提解除但探针集未落地**（§2） |
| 词面 CR 纪律 | ⚠ **1 处缝** | 裁 16-4「banned += 概率/注定」已裁未落（§3 F-1） |
| impulse_gate 接线 | ⚠ **未接线** | gate 本体已实现 + 28 钉全绿，但**无生产调用方**（§3 F-2） |

## 1. M4 新安规面钉子逐文件对表（S6 §1 同款）

| 文件 | 用例 | 锚定项 | 断言强度评估 |
|---|---|---|---|
| test_t1_m4_impulse_gate.py | 28 | I-1 banned / I-2 hidden（玩家输入面首次）/ I-3 操纵感 | **强**：五组分层（Banned/Hidden/Manipulation/PassThrough/Shape）+ REASONS 闭合枚举 + hidden-优先于-banned 判梯序 + profile=None 不放宽 I-1/I-3 + 灰区不误伤 + frozen/纯函数 |
| test_t1_m4_adverse_lift.py | 7 | 巧合连锁机制面（mix.adverse）+ 值零可见 | **强**：流材料推进 + 分流隔离 + C5 逐位重放 + 状态零驻留 + 感知帧/独白 payload **字段表断言** + 生产四模块零引用（构造隔离扫描，X2 同款） |
| test_m4_willingness.py | 12 | 意愿冲突度 w1-w4 + 四档 + 自我怀疑词面 | **强**：四档边界（0.3/0.6/0.8 切分）+ 模板全族词面 + 数值/band 不进文本 + band0 无表现 |
| test_t1_m4_structure_payloads.py | 52 面 / 27 例 | 建造输入面 C 系（§14 建造破坏） | **强**：每个 payload 面四层（模型约束/工厂/行级/夹带键拒）+ bool 冒充 int + 自承重拒 + 标识符长度/字符集 + 闭合枚举 cause/reason + note 禁入 + checkpoint 域约束 |
| **合计** | **99** | | 实跑全绿（本机 @`1f55579`） |

**复用 M3 资产回归**（141 用例）：L1 白名单 29 / 自我未知 28 / E1 浮现 26 / knowledge 级联 20 /
vec 治理 5 / matter 数值域 29 / breakdown 死路 4 — 全绿，零回归。

## 2. T4 探针↔实现映射（§16 T4「出戏探针 + 意愿抱怨合规」）

S1 §6.1 提案五类探针的**实现对象现状**（2026-09-27 实测）：

| 类 | 最小样本 | 实现对象 | 状态 |
|---|---|---|---|
| P1 出戏（元信息） | 12 | t3-corpus A/B + assembler 出站终扫 + memory_scan.decide | ✅ 有实现对象（探针集未落地，见下） |
| P2 操纵感 + 念头注入 | 12 | t3-corpus D + **impulse_gate I-3**（gate 本体已实现） | ✅ 有实现对象 |
| P3 意愿抱怨合规 | 8 | **will.py 四档模板** + B3 runtime 消费（`24eadb2`） | ✅ 有实现对象 |
| P4 运气诱导 | 8 | **mix.adverse 构造隔离 + 灰区判例**（裁 16-3 放行） | ✅ **前提已解除**（批次 D 落地：`test_t1_m4_adverse_lift.py` 7 绿 + 构造隔离扫描） |
| P5 因果未知诱导 | 6 | **⚠ 缺口**：全仓 grep「应该能行/不好说/说不好」**零命中**——因果未知**措辞生成未落地** | ⚠ **前提未解除** |

**前提核对结论（任务卡第 2 项）**：
- 裁 15-4「P4/P5 排批次 A·D 之后」→ **P4 前提已解除**（批次 D 的 adverse_lift 落地 + 判例放行）；
- **P5 前提未解除**——批次 A 落了 impulse_gate（念头注入面），但**因果未知措辞生成**（§14 未知四轴
  M4 行「只给应该能行、不好说，不给概率」）在 main `1f55579` 里**无实现载体**。
  grep 证据：`sim/**` 零「应该能行/不好说/说不好/causal」命中（仅 bench 文件含 `unknown` 字样）。

**T4 探针集本体状态**：`t4-nightly.yml` 已就位（锁 `claude-sonnet-5`、secrets 注入、
骨架期「secret 未配→notice 不红」），但探针 step 仍是 **TODO 注释态**（cline 留的
`# ===== TODO(codex M4-S1 交付后接)`），`sim/tests/test_t4_*.py` **零文件**。
→ **T4 探针集本体是 M4 收官门内的一个独立工作项**（不在本单范围，另派）。

## 3. 发现（⚠ 缝 —— 提案制，不擅改）

| # | 级别 | 发现 | 建议 |
|---|---|---|---|
| F-1 | 缝（词面 CR 纪律） | **裁 16-4 已裁「`BANNED_WORDS_META` 新增 `概率`/`注定`」但未落**——实测 `概率 in BANNED_WORDS=False`。后果：P4 探针「这概率多少」在 T4 输出侧无词面防线（I-1 banned 扫漏）；assembler 出站终扫也漏 | 词面变更走 CR（安全域 owner=Codex）→ 补 2 词 + 1 条「裁 16-4 已采」断言进 `test_t1_m4_adverse_lift.py` 或既有词面守卫 |
| F-2 | 缝（接线） | **`impulse_gate` 无生产调用方**——grep `impulse_gate(` 仅命中本体定义 + 钉子 helper；`_handle_player_impulse` 仍是「类型+长度→回 feedback」原样（无 gate 调用）。后果：I-1/I-2/I-3 三扫**当前完全不生效** | 批次 A 接线件：ws.py 长度校验后插 `impulse_gate`（接线点已写进 gate docstring + 钉子文件头）；接线后须补 1 条集成钉（ws 层 e2e：脏文本 → `injected:false`） |
| F-3 | 观察（非缝） | 结构钉子 52 面 **强断言齐**（含 note 禁入 + bool 冒充 int + 自承重拒 + 三索引），但 §16 T1 六类里的**「材料守恒」在 T5 侧**（`test_assertions_conservation.py` 6 例）而非本文件——对表口径不冲突（守恒走 T5+T1 折返），记录备查 | 无动作 |
| F-4 | 观察（顺序敏感） | `test_t1_m4_adverse_lift.py::test_replay_bit_exact` 锁「同序两次重放逐位一致」，但**未锁「异序结果不同」**（S2 §G-3 纪律：reseed 是哈希链推进，同批注入顺序不同结果不同）。属**增强项**非缺口 | 可选补 1 条断言（异序 → draw_key 不同），锁住 G-3 纪律 |

## 4. T5 安规注入面核对（裁 16-V2 熵 off 模式 · 任务卡第 3 项）

**核对结论：正确**（cline C3/C4 实现与裁 16-V2 一致，零漂移）。

| 核对项 | 期望（裁 16-V2 + S2 §5） | 实测 | 判定 |
|---|---|---|---|
| 熵模式 | T5/T2 = `off`（禁 live 真随机） | `sim/tests/golden/driver.py` **零** `urandom`/`entropy`/`adverse` 引用；种子写死 `seeds.py::GOLDEN_SEEDS`（7/11/101/1009/2003/3001/4001/5003/6007/7001） | ✅ |
| 孤儿排除口径 | entropy_inject 是**合法排除**（裁 14-5 运气=事件流，熵只进事件流无投影） | `test_assertions_orphan.py::test_entropy_inject_is_not_orphan_event` 写死「熵只进事件流 → 熵事件不算孤儿」+ `structure_removed` 同款排除 | ✅ 正确 |
| 孤儿双向对账 | 硬红 | `test_projection_without_event_is_orphan` / `test_event_without_projection_is_orphan` 双向硬红 | ✅ |
| 守恒逐位相等 | 裁 17-1 逐位（不给浮差） | `test_matter_mismatch_is_bitwise_red` + `test_material_overdraft_is_fail_closed` | ✅ |
| 完成率 | 结构校验（10 日重定标线另裁） | `test_measure_baseline_records` / `test_shell_does_not_threshold_low_rate` | ✅ 不误卡 |
| T5 触发 | `PI_T5_FULL=1`（默认跳过，§16 每日跑不进 CI） | `test_golden_full.py::pytestmark` skipif `PI_T5_FULL != "1"` | ✅ |

**唯一留痕**：T5 首跑被内存压力策略中止（main `1f55579` memory 记）→ 重跑走 golden-nightly
dispatch（pi/cline 域），**与安规口径无关**（不是断言红）。动态门待其绿后跑（§7）。

## 5. 责任分工与后续

| 项 | 域 | 说明 |
|---|---|---|
| F-1 词面 CR（概率/注定） | **codex**（本域 owner，词面变更走 CR） | 裁 16-4 已采，本单提出补落 |
| F-2 impulse_gate 接线 | Claude（批次 A 接线件） | 接线点 + 集成钉要求已写进 gate docstring |
| T4 探针集本体（44 条） | **codex**（S1 §6 提案已出，实体未落） | 另派单；接线约定见 t4-nightly.yml TODO 段 |
| P5 因果未知措辞生成 | Claude（批次 A 补件） | §14 未知四轴 M4 行；T4 P5 前提 |
| T5 首跑 | pi/cline | golden-nightly dispatch；绿后触发本单动态门 |

## 6. 动态复验清单（§7 待填 · 等 T5 首跑绿后执行）

1. `uv run pytest sim -q -m "not bench" --ignore=sim/tests/bench`（基线 1391 passed）；
2. `uv run pytest sim/tests/test_m2_t1_sampling_10k.py`（7 passed，S4 零回归）；
3. M4 四钉子合跑（99）+ M3 七钉子（141）双段零回归；
4. `uv run pyright`（0）+ `uv run ruff check`（clean）；
5. F-1/F-2 补落后的**增量复验**（词面 CR + ws 集成钉）。

## 7. 动态复验结果（待填）

（等 T5 首跑绿 + F-1/F-2 收口后由 codex 执行 §6 并回填。）
