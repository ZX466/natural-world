# R5 证据链契约稿（docs/security/m3-evidence-chain.md）

> 维护：Codex（安全/合规/风险域）· 依据：DESIGN.md §16（自我未知）/§13（五条真实感铁律）、
> self-unknown.md、m3-preplan.md §1/R5+§3/X8、m3-plan.md 批次 B4、schema.md §8、memory-scan.md §4 · 日期：2026-09-23
> 状态：M3-S2 交付稿（零代码）。批次 B4 的实现前置——Claude 可照 §4/§5 直接实现；
> §3/§5 含 schema/事件提案，按纪律走「提案 → Claude 裁决 → 再动代码」。

## 0. 一句话

他人隐藏属性进入「我的记忆/知识」的唯一合法路径 = **证据链**：
`witnessed`（目击浮现时刻，事件侧留痕）→ `told`（沿链传播，confidence 累积衰减，低于下限即断）；
`inferred` **写死禁止**产出他人隐藏属性。自身属性扫描面（hidden_leak_scan 按持有者 profile）不变。

## 1. 背景与问题

- R5（m3-preplan §1）：B 转述「C 有旧伤」——B 自身 profile 无该 descriptor，
  `MemoryWritePipeline` 的 hidden 扫描对 B 无效。文本面扫描（banned+hidden）管
  **出戏与自身直陈**；**他人属性的社会面准入**只能靠结构化证据链判定（本文件）。
- 分层口径：**记忆层**记「我听到了什么」（对话事实，B 确实经历了对话，无准入问题）；
  **知识层**记「我知道了什么」（关于世界的结构化主张）——证据链门设在
  **记忆 → 知识的抽取点**与传播写入点（B4/B5 接线处）。
- 现状锚点：`WorldEvent.witnesses: list[str]`（字段在、行级校验 list[str]，
  但**当前无任何装配方**）；triggered 窗口 = runtime 内存态（`HiddenState.evaluate`
  每 tick 重估，`runtime.tick` 原地替换 dict），**不落库**（l1-whitelist §2.1：
  直陈词面永不进事件）。

## 2. 三路判定规则

| source | 规则 | 证据要求 |
|---|---|---|
| `witnessed` | 他人隐藏属性成为知识的**前提**：在属性**浮现时刻**（emerge 事件 tick）目击 | 事件流中存在 `npc.hidden_emerge` 事件：`payload.npc_id == subject` 且 `attr_id ∈ payload.attr_ids` 且 `tick == observed_tick` 且 `holder ∈ witnesses` |
| `told` | 传播沿链衰减；**链必须完整**——teller 自己持有同一条有效知识 | teller 的 knowledge 行存在、未失效、`(subject_npc_id, subject_attr_id)` 一致；confidence = teller.confidence × TOLD_DECAY（累积乘法） |
| `inferred` | **禁止**产出他人隐藏属性——写死，无例外 | 结构化准入门直接拒绝（inferred + 第三方 subject + hidden attr → deny） |

**特例——自我披露**：C 主动告诉 B 自己的隐藏属性（teller == subject）：
走 `told` 但作为**链根**处理，confidence = WITNESSED_BASE_CONFIDENCE（第一手供述
与目击同级），无需 emerge 事件。除此之外 told 必须挂在有效链上。

**常量建议**：`WITNESSED_BASE_CONFIDENCE = 0.9`（目击/供述是第一手但非全知——
DESIGN §16「保留不可解释的间隙」）；`TOLD_DECAY = 0.6`（每跳乘法）；
`TOLD_FLOOR = 0.1`（低于即拒传）。链长效果：0.9 → 0.54 → 0.324 → 0.194 → 0.117 →
0.070（断）——50 人村落里一条目击最多传 4 跳，传播广度由衰减天然封顶。

## 3. 事件侧留痕形状（提案 E1，待裁决）

快照不落库（X4 修订见 §6），「目击即知」的判定留痕 = **新事件种类
`npc.hidden_emerge`**——浮现本身就是值得讲述的时刻（DESIGN §8：触发命中那一刻
才浮现），让它进事件流与 combat.scale_change 同类（审计/协调事件先例）。

```python
class HiddenEmergePayload(BaseModel):
    """隐藏属性浮现留痕（R5 证据链，M3-S2 提案）。attr_id 是戏外主键
    （f"{npc_id}.health_{row.id}"，非直陈词面），与 npc_id/matter_id 同纪律。"""
    model_config = ConfigDict(frozen=True, extra="forbid")
    npc_id: str                      # 属性主体
    attr_ids: tuple[str, ...]        # 本 tick **新进入**触发窗口的属性（delta，非全量）
```

- **发射纪律**（Claude 域接线，runtime.tick 第 0 步 evaluate 之后）：仅当
  `triggered_now − triggered_prev ≠ ∅`（新进窗口，含窗口退出后再进）才发一条；
  同 tick 多属性合并为一条（省事件量）。确定性（C5）：由 state+context 纯推导，
  与 settle_decay 产事件同构；重放时应用存量事件、不重新推导（同 MATTER_*）。
- **witnesses 装配纪律**：由感知层装配 =「该 tick 感知帧中含主体的观察者」
  （视/听通道命中；嗅觉不行——现状 narrate_smell 只有「有味道」无来源归属，
  闻到 ≠ 目击）。witnesses 永不接受 LLM/客户端传入（event_validation 已有
  list[str] 行级校验，装配侧约定归感知层）。
- **登记**：`EventKind.NPC_HIDDEN_EMERGE = "npc.hidden_emerge"` +
  `PAYLOAD_MODELS` 登记（event_validation.py，新 kind 纪律同现有）。

## 4. 判定函数签名（Claude B4 照此实现；建议落 `sim/npc/evidence.py`）

```python
@dataclass(frozen=True)
class EvidenceVerdict:
    admitted: bool
    confidence: float          # 0.0 = 拒绝
    reason: str                # 戏外诊断：ok_witnessed / ok_told / ok_self_disclosure /
                               # deny_inferred / deny_no_emerge_event / deny_not_witness /
                               # deny_chain_broken / deny_below_floor

def judge_third_party_hidden(
    *,
    source: Literal["witnessed", "told", "inferred"],
    holder_id: str,                      # 知识持有者（证人/受传者）
    subject_id: str,                     # 属性主体（第三方 NPC）
    attr_id: str,                        # f"{subject_id}.health_{row.id}"
    events: Sequence[dict],              # store.read_range 戏外行（含 payload/witnesses）
    observed_tick: int | None = None,    # witnessed 必填：声称的目击 tick
    teller_knowledge: "KnowledgeRow | None" = None,  # told 必填：teller 的有效知识行
) -> EvidenceVerdict:
    """他人隐藏属性知识的准入判定。纯函数、只读 events、可重放（C5）。"""
```

- 拒绝一律 `EvidenceVerdict(admitted=False, confidence=0.0, reason=...)`——
  结构化、可观测，与闸门拒绝原因同纪律（不含 LLM 原文/词面）。
- 判定只管**准入**；fact 文本仍过 banned 扫描（X7，写入门同工具）；attr_id
  永不进 prompt/戏内文本（只在戏外列）。

## 5. 数据需求（两要素之二）

**events 侧**（§3 提案 E1）：`npc.hidden_emerge` 事件 + witnesses 感知装配。

**knowledge 侧**（opencode，与 B3 合并提案，待裁决）：

| 列 | 类型 | 说明 |
|---|---|---|
| `subject_npc_id` | TEXT NULL | 他人属性知识：主体 npc_id；自身事实知识为 NULL |
| `subject_attr_id` | TEXT NULL | 属性主键（戏外）；同上 |
| `evidence_seq` | INTEGER NULL | witnessed：emerge 事件 seq（持久层分配后回填） |
| `source_knowledge_id` | INTEGER NULL | told：teller 的 knowledge 行 id（链上回溯键） |
| 治理列 | — | B3 已派：`invalidated`/`invalid_reason`/`source_memory`（R1 级联） |

- 自我披露（链根）行：`source=told`、`subject_npc_id=teller`、evidence 两列 NULL。
- 查询路径：级联失效沿 `source_knowledge_id` 递归（见 §6）。

## 6. 与 X8 / S5 / R1 的关系（对表）

| 项 | 对表结论 |
|---|---|
| X8 | **确认不变**：自身属性扫描面 = hidden_leak_scan(持有者 profile)，本契约不改变其输入输出；两防线正交——文本面管出戏/自身直陈，准入面（本文件）管他人属性 |
| X4 | **修订（CR）**：descriptors/label（直陈词面）与 triggered 全量快照仍永不入事件；`npc.hidden_emerge` 仅承载「新进窗口」的 **attr_id 清单**（最小留痕，事件流是戏外审计层，与 npc_id/matter_id 同纪律） |
| S5/R1 | knowledge **继承失效、不继承替代**：源记忆 supersede → 派生 knowledge 行置治理列失效（knowledge 无「替代行」语义，只失效）；级联沿 told 链 `source_knowledge_id` 向下传播，深度 = 传播深度。接口预留（opencode B3）：`KnowledgeStore.invalidate_by_source(entry_id)` / `invalidate_by_row(row_id)`；级联写法遵循 B1 双列口径终裁（R3） |
| R4 | knowledge 行本就带 branch_id；传播写入落当前分支（B2 落地口径一致） |

## 7. 边界（明确不做）

- **不做文本级他人属性扫描**：无 C 的 profile 时词面匹配在 B 侧不可实现——
  准入靠结构化证据链，这正是 R5 的解法而非缺陷。
- **不做窗口跨 tick 续期（v1）**：witnessed 锚定 emerge 事件 tick（浮现那一刻）；
  属性持续在窗口 ≠ 持续目击。若 M4 叙事需要「长期共处也知晓」，提案
  `hidden.emerge_sustain` 扩展事件再裁。
- **不对记忆层对话事实设准入门**：B 的对话记忆是经历事实；门在记忆→知识抽取点
  与传播写入点（B5 复制写）。
- **不改变写路径唯一入口**：知识写入同样过写入门（banned 扫描），S1 纪律延续。

## 8. B4 验收建议（T1 钉子清单，实现落地时各 1 条）

1. witnessed 正例：emerge 事件（witnesses 含 holder）→ 准入，confidence=0.9；
2. witnessed 反例 ×3：无 emerge 事件 / holder 不在 witnesses / tick 不对 → 全拒；
3. told 正例：链上 teller 行有效 → 准入，confidence=0.9×0.6；**级联**：teller 行失效 → deny_chain_broken；
4. told 下限：链尾 confidence < 0.1 → deny_below_floor；
5. 自我披露：teller == subject → 准入（0.9），无需 emerge 事件；
6. inferred：第三方 hidden 属性 → 一律 deny（无例外路径）；
7. 级联失效端到端：源记忆 supersede → knowledge 行失效 → 下游 told 行级联失效（R1/S5 对表）。

## 9. 责任分工

| 面 | 域 |
|---|---|
| 本契约 + 验收钉子（§8） | Codex（安全域 owner，CR） |
| `judge_third_party_hidden` / emerge 事件发射 / witnesses 装配 | Claude（批次 B4/B5） |
| knowledge 列扩展 + 治理级联接口 | opencode（与 B3 合并提案，先裁决后动 schema） |