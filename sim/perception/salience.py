"""显著性 — 只报告值得注意的（DESIGN §7 模块划分）。

阈值排序 + 截断都在这一层完成：传播层给强度，显著性层决定
「哪些进入帧、以什么顺序」。M1 规则简单：
1. 强度 ≥ floor（视觉已在传播层硬过滤，听觉在此过滤）
2. 按 (通道优先级, 强度降序) 取 max_observations 条
3. 视觉/听觉的组内去重：同一 subject 同一 tick 只保留最强一条
"""

from __future__ import annotations

from sim.perception.frame import Channel, Observation
from sim.perception.profiles.base import PerceptionProfile

_CHANNEL_PRIORITY: dict[Channel, int] = {
    Channel.INTEROCEPTION: 0,  # 身体永远最重要（铁律 7）
    Channel.TOUCH: 1,
    Channel.VISION: 2,
    Channel.HEARING: 3,
}


def select_observations(
    candidates: list[Observation], profile: PerceptionProfile
) -> tuple[Observation, ...]:
    """显著性筛选：floor 过滤 → subject 去重 → 排序截断。

    纯函数；输入顺序影响同强度 tie-break，装配端保证传入顺序确定。
    """
    kept = [ob for ob in candidates if ob.strength >= profile.vision_floor]
    best_by_subject: dict[str, Observation] = {}
    for ob in kept:  # 先到者优先（同 subject 同强度取先到，顺序确定）
        prev = best_by_subject.get(ob.subject)
        if prev is None or ob.strength > prev.strength:
            best_by_subject[ob.subject] = ob
    deduped = list(best_by_subject.values())
    deduped.sort(key=lambda ob: (_CHANNEL_PRIORITY[ob.channel], -ob.strength, ob.subject))
    return tuple(deduped[: profile.max_observations])


def _select_raw(
    raw: list[tuple[Channel, str, str, float]], profile: PerceptionProfile
) -> tuple[Observation, ...]:
    """原始元组版显著性（热路径）：截断发生在 pydantic 构造之前。

    与 select_observations 同规则：floor 过滤 → subject 去重（保最强）
    → (通道优先级, 强度降序, subject) 排序 → 截断 → 才构造 Observation。
    """
    vision_floor = profile.vision_floor
    best_by_subject: dict[str, tuple[Channel, str, str, float]] = {}
    for cand in raw:
        _, subject, _, strength = cand
        if strength < vision_floor:
            continue
        prev = best_by_subject.get(subject)
        if prev is None or strength > prev[3]:
            best_by_subject[subject] = cand
    deduped = sorted(
        best_by_subject.values(),
        key=lambda c: (_CHANNEL_PRIORITY[c[0]], -c[3], c[1]),
    )
    return tuple(
        Observation(channel=ch, subject=sub, description=desc, strength=st)
        for ch, sub, desc, st in deduped[: profile.max_observations]
    )
