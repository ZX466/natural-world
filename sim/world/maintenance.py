"""Production maintenance loop for matter decay and support cascades."""

from dataclasses import dataclass, field

from sim.core.events import WorldEvent
from sim.world.matter import MatterLedger
from sim.world.structure import StructureSnapshot
from sim.world.support_graph import (
    CascadeState,
    advance_cascade,
    build_support_graph,
    start_cascade,
)


@dataclass
class WorldMaintenance:
    ledger: MatterLedger
    structures: dict[str, StructureSnapshot]
    _cascades: list[CascadeState] = field(default_factory=list)

    def tick(self, *, tick: int, seed: int) -> list[WorldEvent]:
        events = self.ledger.settle(tick=tick, seed=seed)
        collapsed = {
            str(event.payload["matter_id"])
            for event in events
            if event.event_type.value == "matter.collapse"
        }
        collapsed.update(
            sid
            for sid in self.structures
            if sid in self.ledger._items and self.ledger.state(sid).integrity <= 0.0
        )
        if not self.structures:
            return events
        graph = build_support_graph(("main", snapshot) for snapshot in self.structures.values())
        for seed_id in sorted(collapsed & set(graph.nodes)):
            self._cascades.append(start_cascade(graph, (seed_id,)))
        next_cascades: list[CascadeState] = []
        for cascade in self._cascades:
            step = advance_cascade(graph, cascade, tick=tick)
            events.extend(step.events)
            if not step.state.done:
                next_cascades.append(step.state)
        self._cascades = next_cascades
        return events
