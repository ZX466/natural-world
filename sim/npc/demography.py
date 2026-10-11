"""L0：周边四村 1200 人，货源和行旅按分钟统计推进。"""

from __future__ import annotations

import hashlib

from sim.core.events import DemographyPayload, EventKind, WorldEvent


class Demography:
    def __init__(self, *, seed: int) -> None:
        self.seed = seed
        self.population = (300, 300, 300, 300)
        self.grain = (600, 600, 600, 600)
        self.traders = 0
        self._last_tick = 0

    def tick(self, tick: int) -> list[WorldEvent]:
        if tick % 60 or tick <= self._last_tick:
            return []
        minute = tick // 60
        values = hashlib.sha256(f"demography:{self.seed}:{minute}".encode()).digest()
        self.grain = tuple(
            max(0, amount + values[i] % 7 - 3) for i, amount in enumerate(self.grain)
        )
        self.traders = values[4] % 12 + 1
        if tick % 86_400 == 0:
            self.population = tuple(
                max(250, min(375, amount + values[i + 5] % 3 - 1))
                for i, amount in enumerate(self.population)
            )
        self._last_tick = tick
        payload = DemographyPayload.model_validate(
            {"population": self.population, "grain": self.grain, "traders": self.traders}
        )
        return [
            WorldEvent(
                tick=tick,
                event_type=EventKind.DEMOGRAPHY_TICK,
                payload=payload.model_dump(mode="json"),
            )
        ]

    def observe(self, events) -> None:
        for event in events:
            if event.event_type is EventKind.DEMOGRAPHY_TICK:
                payload = DemographyPayload.model_validate(event.payload)
                self.population, self.grain, self.traders = (
                    payload.population,
                    payload.grain,
                    payload.traders,
                )
                self._last_tick = event.tick
