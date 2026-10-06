"""sim.npc.needs — 需求系统（M2-A1 §1.1；触发门控输入之一）。

每 tick 推进需求值；frozen：推进返回新元组。阈值触发只产出
「建议动作」候选，不做决策（决策在 utility.py）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from sim.npc.model import Need


@dataclass(frozen=True)
class NeedDecay:
    """单项需求每游戏秒（tick）推进速率（正值=紧迫度上升）。"""

    name: str
    delta_per_tick: float
    # 阈值：达到后触发补救动作建议（如 hunger≥0.7 → eat）
    threshold: float = 0.7
    remedy_action: str = ""


DEFAULT_DECAYS: tuple[NeedDecay, ...] = (
    NeedDecay("hunger", 1.0 / 86400.0, 0.7, "eat"),  # 一天饿满（游戏日=86400 tick）
    NeedDecay("energy", 1.0 / 57600.0, 0.7, "rest"),  # 16h 消耗
    NeedDecay("social", 1.0 / 172800.0, 0.8, "request_chat"),  # 2 天
)


def advance_needs(
    needs: tuple[Need, ...], decays: tuple[NeedDecay, ...] = DEFAULT_DECAYS, ticks: int = 1
) -> tuple[Need, ...]:
    """按速率推进全部需求（缺省速率表之外的项不变）。"""
    rates = {d.name: d.delta_per_tick for d in decays}
    return tuple(n.advanced(rates.get(n.name, 0.0), ticks) for n in needs)


def threshold_hits(
    needs: tuple[Need, ...], decays: tuple[NeedDecay, ...] = DEFAULT_DECAYS
) -> tuple[str, ...]:
    """越过阈值的需求 → 建议动作（候选集输入，非强制）。"""
    hits: list[str] = []
    by_name = {n.name: n for n in needs}
    for d in decays:
        if d.remedy_action and d.name in by_name and by_name[d.name].value >= d.threshold:
            hits.append(d.remedy_action)
    return tuple(hits)


# ---------------------------------------------------------------------------
# 补救动作回写（批次 D3：eat/rest 生理闭环——到站消耗）
# ---------------------------------------------------------------------------

#: 补救动作 → 需求回写量（正值=紧迫度缓解量，value 直接减；clip 到 [0,1]）
REMEDY_RELIEF: dict[str, tuple[tuple[str, float], ...]] = {
    "eat": (("hunger", 0.3), ("energy", 0.15)),  # 吃饱（负=小幅提振social压力）
    "rest": (("energy", 0.3),),
}


def apply_remedy(needs: tuple[Need, ...], action: str) -> tuple[Need, ...]:
    """补救动作的需求回写（frozen：replace 生成新元组；clip 到 [0,1]）。

    实况执行面在动作**到站**时调用（未到站不回写——吃了才算吃）。
    未知动作 no-op。value 语义=紧迫度（1=最紧迫），「缓解」即减 value；
    负 relief=提振（吃饱心情好，energy 紧迫度降的更多面不在此表）。
    """
    relief = REMEDY_RELIEF.get(action)
    if not relief:
        return needs
    by_name = {n.name: n for n in needs}
    updated: dict[str, Need] = {}
    for name, amount in relief:
        need = by_name.get(name)
        if need is None:
            continue
        updated[name] = replace(need, value=min(1.0, max(0.0, need.value - amount)))
    return tuple(updated.get(n.name, n) for n in needs)
