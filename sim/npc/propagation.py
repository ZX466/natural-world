"""sim.npc.propagation — 记忆传播 = 复制写（M3 批次 B-B1，m3-plan §3；R5/R6 落地）。

R6 架构约定：检索 API 永远以持有者 npc_id 为键，**不开放跨人读**；传播只经
「写入门」复制——A 告诉 B = 在 B 侧走一次 MemoryWritePipeline.write()，
B 的 banned+hidden 扫描按 B 的 profile 自动生效（本模块不绕门、不改管线本体）。

retell 流程（§3 B-B1）：证据链判定（evidence.judge_third_party_hidden）→
判定通过才 write(source="dialogue")，importance=判定置信（told 衰减已含）；
判定拒绝 → 返回 None（结构化拒绝，无副作用——传播失败是常态路径非错误）；
管线拒写（banned 等）→ 同样返回 None。

纯同步、无 IO（除管线落库）；C5：同输入同输出（判定纯函数 + 管线确定性）。
"""

from __future__ import annotations

from typing import Any

from sim.llm.memory_scan import MemoryWritePipeline
from sim.npc.evidence import judge_third_party_hidden


def retell(
    *,
    pipeline: MemoryWritePipeline,
    to_npc: str,
    source: str,
    subject_id: str,
    attr_id: str,
    events: list[dict[str, Any]],
    content: str,
    tick: int,
    observed_tick: int | None = None,
    teller_knowledge: dict[str, Any] | None = None,
    teller_is_subject: bool = False,
    emotion_tag: str | None = None,
):
    """把「他人隐藏属性知识」复制写到 to_npc 的记忆（走 B 的写入门）。

    - 判定（judge_third_party_hidden）不通过 → 返回 None，零副作用；
    - 判定通过 → pipeline.write(source="dialogue", importance=verdict.confidence)；
      write 被拒（banned/hidden 扫描）→ 返回 None（门是最后一道，retell 不翻越）；
    - 返回 MemoryEntry（写入成功）。

    事件流读取只在 witnessed 路（events 参数）；told 路读 teller 的知识行
    （B3 五列形最小 dict），均由调用方传入——本模块不做 IO 查询。
    """
    verdict = judge_third_party_hidden(
        source=source,
        holder_id=to_npc,
        subject_id=subject_id,
        attr_id=attr_id,
        events=events,
        observed_tick=observed_tick,
        teller_knowledge=teller_knowledge,
        teller_is_subject=teller_is_subject,
    )
    if not verdict.admitted:
        return None
    result = pipeline.write(
        npc_id=to_npc,
        content=content,
        source="dialogue",
        event_seq=None,
        importance=verdict.confidence,
        emotion_tag=emotion_tag,
    )
    if not result.accepted or result.entry is None:
        return None
    return result.entry
