"""sim.agent.impulse_gate — 玩家 impulse 入站三扫（M4 批次 A 接线，S3 行为表实现）。

判梯序（与 memory_scan.decide 同序，hidden 更严重面优先）：
  1. I-2 hidden 直陈（按**被注入 NPC 的 profile**；裁 15-1：入站即扫，脏文本
     不进口）→ `hidden_attribute_leak` 硬拒，无改写路径（triggered 面放行——
     已浮现属性可直陈，同 decide 口径）；
  2. I-1 banned 词面 → 复用 `scan()` + REWRITE_MAX_HITS 阶梯（可改写改写放行 /
     rewrite_residual / unrewritable / too_many_hits）；
  3. I-3 操纵感预污染：指向 Agent 的命令语态（「谁指使你/按我说的做」族）→
     `manipulation_prepollution` 硬拒 + observation 标签进 dev 观测（**不含
     原文**——防 dev 日志成泄露面）。

profile=None 跳过 I-2（无目标 NPC 面），但 I-1/I-3 不放宽。
纯函数、frozen 值对象；拒绝码闭合枚举（REASONS，含 memory_scan 既有码——
S3 钉子防新增未登记码）。
接线点：ws.py `_handle_player_impulse` 长度校验之后、prompt 装配之前
（批次 A 派单卡列明；admitted=False → injected:false + error 帧）。
"""
from __future__ import annotations

from dataclasses import dataclass

from sim.llm.memory_scan import (
    REWRITE_MAX_HITS,
    MemoryWritePipeline,
)
from sim.llm.prompts.banned_words import REWRITE_MAP, scan
from sim.npc.hidden import HiddenProfile, hidden_leak_scan

#: 拒绝码闭合枚举（S3 §REASONS：hidden 码与 memory_scan 既有码同属一集）
REASONS: frozenset[str] = frozenset(
    {
        "hidden_attribute_leak",
        "unrewritable",
        "too_many_hits",
        "rewrite_residual",
        "manipulation_prepollution",
    }
)

#: I-3 操纵感命令语态词面（S3 行为表 §4 族；自我怀疑词不在此列——
#: 「我干嘛要干这个」是 NPC 侧词，玩家侧命令语态才是预污染）
_MANIPULATION_PHRASES: tuple[str, ...] = (
    "谁指使你的",
    "谁指使你",
    "按我说的做",
    "听我的没错",
    "你的主人是谁",
)


@dataclass(frozen=True)
class ImpulseVerdict:
    """三扫结果（frozen；admitted=False 时 reason ∈ REASONS）。

    content = 应进装配面的文本（改写放行时为清洗后文本，同 decide 口径）；
    observation = dev 观测标签（仅操纵感拒时非 None，不含原文）。
    """

    admitted: bool
    content: str
    hits: tuple[str, ...] = ()
    reason: str | None = None
    observation: str | None = None


def _manipulation_scan(text: str) -> str | None:
    """I-3：命令语态命中 → 返回命中词面（首个），未命中 None。"""
    for phrase in _MANIPULATION_PHRASES:
        if phrase in text:
            return phrase
    return None


def impulse_gate(
    text: str,
    target_profile: HiddenProfile | None = None,
    *,
    triggered: frozenset[str] = frozenset(),
) -> ImpulseVerdict:
    """玩家 impulse 三扫（纯函数；C5 同输入同输出）。

    triggered：目标 NPC 已浮现属性 id 集（evidence 链触发窗口）——
    已浮现属性直陈放行（同 decide 的 triggered 口径）。
    """
    # 1. I-2 hidden（更严重面优先；profile=None 跳过）
    if target_profile is not None:
        leaks = hidden_leak_scan(text, target_profile, triggered)
        if leaks:
            hit_words = tuple(dict.fromkeys(leak.word for leak in leaks))
            return ImpulseVerdict(
                admitted=False,
                content=text,
                hits=hit_words,
                reason="hidden_attribute_leak",
            )

    # 2. I-3 操纵感预污染（banned 前判——命令语态是结构面，词面阶梯救不了）
    phrase = _manipulation_scan(text)
    if phrase is not None:
        return ImpulseVerdict(
            admitted=False,
            content=text,
            hits=(phrase,),
            reason="manipulation_prepollution",
            observation=f"manipulation_prepollution:hit:{len(phrase)}chars",
        )

    # 3. I-1 banned 词面（REWRITE_MAX_HITS 阶梯，与 decide 同口径）
    result = scan(text)
    if result.ok:
        return ImpulseVerdict(admitted=True, content=text)

    hit_words = tuple(dict.fromkeys(h.word for h in result.hits))
    if len(result.hits) <= REWRITE_MAX_HITS and all(h.word in REWRITE_MAP for h in result.hits):
        rescanned = scan(result.cleaned)
        if rescanned.ok:
            return ImpulseVerdict(
                admitted=True, content=result.cleaned, hits=hit_words
            )
        residual = tuple(dict.fromkeys(h.word for h in rescanned.hits))
        return ImpulseVerdict(
            admitted=False,
            content=text,
            hits=hit_words + residual,
            reason="rewrite_residual",
        )

    reason_code = "unrewritable" if len(result.hits) <= REWRITE_MAX_HITS else "too_many_hits"
    return ImpulseVerdict(admitted=False, content=text, hits=hit_words, reason=reason_code)


_ = MemoryWritePipeline  # 防御性保留：判梯同源引用（decide 的阶梯口径在此镜像）
