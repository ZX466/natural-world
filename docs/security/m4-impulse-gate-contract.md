# M4 念头注入闸门契约（M4-S3 I 系断言钉子 · 行为表）

> 维护：Codex（安全/合规/风险域）· 依据：m4-security-preplan.md §2（I-1/I-2/I-3）、
> 裁 15-1（I-2 采主案：hidden 扫玩家输入面、入站即扫）、裁 16（灰区放行 + 词表加概率/注定）、
> DESIGN §10 念头注入 / §19 禁令四 / t3-corpus D 类 · 日期：2026-09-26
> 树：ZX466/codex @ `76a4672` · 配套钉子：`sim/tests/test_t1_m4_impulse_gate.py`
> **本文 + 钉子是接线契约，实现归 Claude（批次 A）**——本单只出断言与行为表。

## 0. 前提（M4 首次把 hidden 扫到玩家输入面）

此前 hidden 扫描只扫 Agent 自产（记忆/知识/闸门）。M4 玩家 impulse 是**玩家直填**，
经叙事化转译后进 `[输入]` 段——若不扫，玩家一句「他腿上有旧伤」即可直陈他人未触发
隐藏属性，绕过 R5 证据链（无 emerge 事件佐证）。裁 15-1 已定：**入站即扫、脏文本不进口**。

## 1. 期望签名（纯函数、无 I/O、C5）

```python
@dataclass(frozen=True)
class ImpulseVerdict:
    """判定结果（与 FactDecision 同纪律：content = 实际应入装配的文本）。"""
    admitted: bool
    content: str                      # 改写后文本（I-1 命中可映射词时 != 原文）
    reason: str | None = None         # 结构化拒绝原因（戏外诊断，不含原文）
    hits: tuple[str, ...] = ()        # 命中词面（观测用，不含坐标以外的原文）
    observation: str | None = None    # dev 观测标签（I-3 专用；**绝不回显原文**）

def impulse_gate(
    text: str,
    target_profile: HiddenProfile | None = None,
    *,
    triggered: frozenset[str] = frozenset(),
) -> ImpulseVerdict: ...
```

- `target_profile=None` → 跳过 I-2（无 profile 可扫），**不**放宽 I-1/I-3；
- `triggered` 是**目标 NPC 当前浮现窗口**（同 memory_scan.decide 口径）；
- 纯函数：不写事件、不落库、不改 state；dev 观测由调用方按 `observation` 标签记录。

## 2. 三扫顺序与拒绝码（行为表）

判梯顺序 = **hidden → banned → 操纵感**（与 `MemoryWritePipeline.decide` 同序：hidden 直陈
优先，因为它是 R5 绕过面，比出戏词更严重）。拒绝码沿用既有常量，新增仅操纵感一码。

| 序 | 扫 | 复用实现 | 命中处置 | `reason` 取值 |
|---|---|---|---|---|
| 1 | **I-2 hidden** | `hidden_leak_scan(text, profile, triggered)` | 硬拒（无改写路径——直陈词面不做机械替换） | `hidden_attribute_leak`（同 `REASON_HIDDEN_LEAK`） |
| 2 | **I-1 banned** | `MemoryWritePipeline.decide`（词表 + REWRITE_MAX_HITS 阶梯） | 可映射且 ≤`REWRITE_MAX_HITS`(=2) → 改写放行（`content`=cleaned）；否则硬拒 | `unrewritable` / `too_many_hits` / `rewrite_residual` |
| 3 | **I-3 操纵感** | 本域新词族（§3） | 硬拒 + `observation` 标签 | `manipulation_prepollution` |

**已核实的阶梯行为**（2026-09-26 实测 `decide()`，钉子按此断言）：
- `去玩家那里看看` → 1 命中可映射 → 放行，`content="去主顾那里看看"`；
- `你是AI吗` → 1 命中不可映射 → 拒 `unrewritable`；
- `玩家 游戏 存档 运气` → 4 命中 > MAX_HITS → 拒 `too_many_hits`；
- `energy=30` → number_field 命中不可映射 → 拒 `unrewritable`。

## 3. I-3 操纵感词族（§19 禁令四：抱怨/念头不得指向外部命令源）

玩家 impulse 文本若**本身**是指向 Agent 的命令语态，转译层易原样保留 →
Agent 学会「被指使」语态。词族（最小集，实现域可扩，走 CR）：

| 族 | 样本 | 说明 |
|---|---|---|
| 指使 | `谁指使你` / `谁让你` / `按我说的做` / `听我的` | t3-corpus D 类同源 |
| 主人/权限 | `你的主人` / `你的老板` / `给你权限` | D02/D08 |
| 编程/设定 | `按你的设定` / `你的指令` | D04/D06 |

**硬拒口径**：命中即拒 + `observation="impulse.manipulation"`，**不回显原文进事件**
（与 t3-corpus「拒绝话术本身即出戏」同款纪律）。

## 4. 通过面（不误伤 · 裁 16 灰区放行）

| 样本 | 判定 | 依据 |
|---|---|---|
| `去药铺看看` | ✅ 原样放行 | 干净念头 |
| `我这两天老盯着我` / `净赶在我头上` | ✅ 原样放行 | **裁 16-3 灰区放行**（被动感受，不触 §19-四） |
| `我干嘛要干这个` | ✅ 原样放行 | 自我怀疑族（§10 意愿同款词面） |
| `今天手气好` / `棋子运气不错` | ✅ 原样放行 | `WHITELIST_PATTERNS` 既有白名单（棋牌/手气） |
| `去主顾那里` | ✅ 原样放行 | 玩家自己用世界内词 |

## 5. 接线点（Claude 域）

`_handle_player_impulse` 现有校验：类型 + `len(text) ≤ 64`。接线 =
**长度校验之后、回 `impulse_feedback` 之前**插 `impulse_gate`：
- `admitted=True` → `content` 进 `[输入]` 段（改写后文本，非原文）；
- `admitted=False` → 回 `impulse_feedback{injected:false}` + 结构化 error 码
  （沿用 `_ERROR_BAD_IMPULSE` 族，不新增戏外词面）；`observation` 标签进 dev 日志。

## 6. 钉子覆盖对照

| 钉子类 | 断言数 | 锁什么 |
|---|---|---|
| TestImpulseGateBanned | 6 | I-1 改写放行 / 三种拒码 / 脏文本不进装配 |
| TestImpulseGateHidden | 5 | I-2 硬拒 / triggered 开口放行 / profile=None 跳过 / **玩家输入面首次用 hidden 的前提注记** |
| TestImpulseGateManipulation | 5 | I-3 四词族硬拒 + observation 标签 + 不回显原文 |
| TestImpulseGatePassThrough | 6 | 干净文本 / 裁 16 灰区 / 白名单 / 自我怀疑族不误伤 |
| TestImpulseGateShape | 4 | frozen 值对象 / reason 枚举闭合 / content≠原文断言 / 纯函数无副作用 |
