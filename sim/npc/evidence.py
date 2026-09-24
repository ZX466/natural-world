"""sim.npc.evidence — 证据链判定 + witnesses 装配（M3 批次 B4，m3-evidence-chain §3/§4/§8）。

R5 三路判定（judge_third_party_hidden）：他人隐藏属性进入「我的记忆/知识」的合法性——
- **witnessed**：目击浮现时刻（emerge 事件 tick/attr_id/witnesses 三要素齐）→ 0.9；
- **told**：沿链衰减 0.9×0.6^n（teller 知识行置信 × TOLD_DECAY，floor 0.1 断链）；
  自我披露特例（teller_is_subject=True）作链根不衰减；
- **inferred**：一律拒绝（写死无例外——推不出他人隐藏属性，社会面信息边界）。

witnesses_of_emerge：E1 事件的见证人装配 = 该 tick 感知帧含主体的观察者；
**嗅觉不计数**（narrate_smell 无来源归属——闻到 ≠ 目击，self-unknown §2）。

纯函数、只读、无 IO（C5 可重放；拒绝原因串不含 LLM 原文/词面，闸门同纪律）。
实现前由 codex M3-S3 钉子（test_t1_m3_hidden_emerge.py，26 用例）锁契约。
"""

from __future__ import annotations

from dataclasses import dataclass

#: witnessed 基准置信（§3：目击浮现时刻 = 最强证据）。
WITNESSED_CONFIDENCE = 0.9
#: told 单跳衰减系数（§3：confidence × TOLD_DECAY，累积乘法）。
TOLD_DECAY = 0.6
#: told 下限（低于即断链拒收——最远 4 跳：0.9×0.6⁴≈0.117，第 5 跳 0.07<0.1）。
TOLD_CONFIDENCE_FLOOR = 0.1
#: 自我披露链根置信（§2：teller==subject，无需 emerge 事件佐证）。
SELF_DISCLOSURE_CONFIDENCE = 0.9
#: 感知通道中可构成「目击」的通道（嗅觉除外——无来源归属）。
WITNESSING_CHANNELS = frozenset({"vision", "hearing", "touch"})


@dataclass(frozen=True)
class EvidenceVerdict:
    """结构化判定结果（E.拒绝纪律：reason 不含 LLM 原文/词面）。"""

    admitted: bool
    confidence: float
    reason: str


def _deny(reason: str) -> EvidenceVerdict:
    return EvidenceVerdict(admitted=False, confidence=0.0, reason=reason)


def judge_third_party_hidden(
    *,
    source: str,
    holder_id: str,
    subject_id: str,
    attr_id: str,
    events: list[dict],
    observed_tick: int | None = None,
    teller_knowledge: dict | None = None,
    teller_is_subject: bool = False,
) -> EvidenceVerdict:
    """他人隐藏属性的证据链三路判定（§3/§8；只读 events，纯函数）。

    - witnessed：events 中须存在 npc.hidden_emerge 行，payload.npc_id==subject、
      attr_id ∈ payload.attr_ids、row.tick==observed_tick 且 holder ∈ row.witnesses
      （tick/witnesses 任一错配 → deny，§8-2）；
    - told：teller_knowledge（teller 的同条知识行，B3 五列形的最小 dict）须存在、
      未失效、(subject_npc_id, subject_attr_id) 与本条一致；confidence =
      teller.confidence × TOLD_DECAY；低于 floor → deny（断链）；自我披露
      （teller_is_subject）作链根，不衰减直接取 SELF_DISCLOSURE_CONFIDENCE；
    - inferred：一律 deny（§8-6 写死）。
    """
    if source == "inferred":
        return _deny("inferred_not_allowed")

    if source == "witnessed":
        if observed_tick is None:
            return _deny("witnessed_missing_observed_tick")
        for row in events:
            if row.get("event_type") != "npc.hidden_emerge":
                continue
            payload = row.get("payload") or {}
            if payload.get("npc_id") != subject_id:
                continue
            if attr_id not in (payload.get("attr_ids") or []):
                continue
            if row.get("tick") != observed_tick:
                continue
            if holder_id not in (row.get("witnesses") or []):
                continue
            return EvidenceVerdict(
                admitted=True, confidence=WITNESSED_CONFIDENCE, reason="ok_witnessed"
            )
        return _deny("witnessed_no_matching_emerge")

    if source == "told":
        if teller_is_subject:
            # 自我披露：主体亲口告知 = 链根（§2），无需 emerge 佐证。
            return EvidenceVerdict(
                admitted=True, confidence=SELF_DISCLOSURE_CONFIDENCE, reason="ok_told"
            )
        if teller_knowledge is None:
            return _deny("told_missing_teller_knowledge")
        if teller_knowledge.get("invalidated"):
            return _deny("told_teller_knowledge_invalidated")
        if teller_knowledge.get("subject_npc_id") != subject_id:
            return _deny("told_subject_mismatch")
        if teller_knowledge.get("subject_attr_id") != attr_id:
            return _deny("told_attr_mismatch")
        base = float(teller_knowledge.get("confidence", 0.0))
        conf = base * TOLD_DECAY
        if conf < TOLD_CONFIDENCE_FLOOR:
            return _deny("told_below_floor")
        return EvidenceVerdict(admitted=True, confidence=conf, reason="ok_told")

    return _deny("unknown_source")


def witnesses_of_emerge(frames: dict[str, object], *, subject: str) -> list[str]:
    """E1 见证人装配：该 tick 感知帧含主体观测的观察者 id（排除主体自身）。

    嗅觉通道不计入（narrate_smell 无来源归属——闻到 ≠ 目击）。
    frames: observer_id -> 感知帧（鸭子类型：须有 observations 可迭代，元素为
    (channel, subject, strength) 三元组或等价有 channel/subject 属性的对象）。
    """
    witnesses: list[str] = []
    for observer_id, frame in frames.items():
        if observer_id == subject:
            continue
        for obs in getattr(frame, "observations", []) or []:
            channel = obs[0] if isinstance(obs, tuple) else getattr(obs, "channel", None)
            obs_subject = obs[1] if isinstance(obs, tuple) else getattr(obs, "subject", None)
            if obs_subject != subject:
                continue
            if channel in WITNESSING_CHANNELS and observer_id not in witnesses:
                witnesses.append(observer_id)
    return witnesses
