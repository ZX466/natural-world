"""sim.npc.needs — 需求系统（M2-A1 §1.1；触发门控输入之一）。

每 tick 推进需求值；frozen：推进返回新元组。阈值触发只产出
「建议动作」候选，不做决策（决策在 utility.py）。
"""

from __future__ import annotations

from dataclasses import dataclass

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
