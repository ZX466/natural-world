"""20 个可执行委托：村民发布、主角抵达目标、单次事件报酬。"""

from __future__ import annotations

from dataclasses import dataclass

from sim.core.events import WorldEvent, coin_grant_event, npc_chat_event, npc_monologue_event
from sim.core.world import WorldState
from sim.world.economy import CoinLedger

# 复用已有镇上站点；目标按距离展开，且每一项 issuer/target 组合唯一。
_DESTINATIONS = (
    (10, 15),
    (28, 42),
    (14, 68),
    (82, 38),
    (46, 86),
    (78, 75),
    (16, 22),
    (34, 39),
    (13, 35),
    (34, 13),
)


@dataclass(frozen=True)
class Errand:
    issuer: str
    target: tuple[int, int]
    number: int


def errand_cases() -> tuple[Errand, ...]:
    return tuple(
        Errand(f"villager_{i + 1:02d}", _DESTINATIONS[i % len(_DESTINATIONS)], i + 1)
        for i in range(20)
    )


class ErrandRuntime:
    """至多一个活跃委托；接单、完成都由事件入流（C4）。"""

    def __init__(self, *, seed: int, coin_ledger: CoinLedger) -> None:
        self.seed = seed
        self.coin_ledger = coin_ledger
        self.reset()

    def reset(self) -> None:
        self.active: Errand | None = None
        self._next = 0
        self._return_due = False
        self._last_offered_tick = -600

    def tick(self, state: WorldState, tick: int) -> list[WorldEvent]:
        chenmo = state.entities.get("chenmo")
        if chenmo is None:
            return []
        if self.active is not None:
            job = self.active
            issuer = state.entities.get(job.issuer)
            if issuer is None:
                self.active = None
                self._return_due = False
                return []
            if not self._return_due:
                if chenmo.pos != job.target or chenmo.path:
                    return []
                self._return_due = True
                return [
                    npc_monologue_event(
                        tick=tick,
                        npc_id="chenmo",
                        form="thought",
                        content="地方已经走到了，得回去交差。",
                    )
                ]
            if (
                chenmo.path
                or abs(issuer.pos[0] - chenmo.pos[0]) + abs(issuer.pos[1] - chenmo.pos[1]) > 2
            ):
                return []
            self.active = None
            self._return_due = False
            self.coin_ledger.apply_grant("chenmo", 5, tick=tick)
            return [
                npc_chat_event(
                    tick=tick,
                    npc_id=job.issuer,
                    to_id="chenmo",
                    line="辛苦你跑这一趟，这份工钱收好。",
                ),
                coin_grant_event(
                    tick=tick, owner_id="chenmo", delta=5, note=f"errand:{job.number:02d}"
                ),
            ]
        if tick - self._last_offered_tick < 600:
            return []
        cases = errand_cases()
        for offset in range(len(cases)):
            i = (self._next + offset) % len(cases)
            job = cases[i]
            issuer = state.entities.get(job.issuer)
            if issuer is None or job.target == chenmo.pos:
                continue
            dist = abs(issuer.pos[0] - chenmo.pos[0]) + abs(issuer.pos[1] - chenmo.pos[1])
            if dist > 2:
                continue
            self.active = job
            self._next = (i + 1) % len(cases)
            self._last_offered_tick = tick
            x, y = job.target
            return [
                npc_chat_event(
                    tick=tick,
                    npc_id=job.issuer,
                    to_id="chenmo",
                    line=f"帮我跑一趟，到镇上东{x}、南{y}的地方看看，回来给你工钱。",
                )
            ]
        return []
