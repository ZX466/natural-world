"""主角专用需求内存投影，复用 NPC 的推进与补救纯函数。"""

from __future__ import annotations

from sim.content.protagonist import build_needs
from sim.npc.model import Need
from sim.npc.needs import DEFAULT_DECAYS, advance_needs, apply_remedy


class ProtagonistNeeds:
    """只消费正向 tick 差；重启或读档由调用方新建种子投影。"""

    def __init__(self, initial_tick: int, needs: tuple[Need, ...] | None = None) -> None:
        self._needs = build_needs() if needs is None else needs
        self._last_tick = initial_tick

    @property
    def needs(self) -> tuple[Need, ...]:
        """当前 frozen 需求元组，后续更新不修改已返回的快照。"""
        return self._needs

    @property
    def hunger(self) -> float:
        """饥饿紧迫度；定制种子没有该项时视为无饥饿。"""
        return next((n.value for n in self._needs if n.name == "hunger"), 0.0)

    def advance_to(self, tick: int) -> None:
        """按上次正向推进点到当前 tick 的差值推进；旧 tick 不改水位。"""
        if tick <= self._last_tick:
            return
        self._needs = advance_needs(
            self._needs, decays=DEFAULT_DECAYS, ticks=tick - self._last_tick
        )
        self._last_tick = tick

    def apply(self, action: str) -> None:
        """动作已生效后应用既有补救量，未知动作保持原值。"""
        self._needs = apply_remedy(self._needs, action)
