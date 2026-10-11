"""Production maintenance loop for matter decay and support cascades."""

from dataclasses import dataclass, field

from sim.core.events import EventKind, WorldEvent
from sim.core.persistence.npc_store import _structure_event_fields, fold_structure_snapshot
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
    _collapsed: set[str] = field(default_factory=set)

    def observe(self, events: tuple[WorldEvent, ...] | list[WorldEvent]) -> None:
        """已落事件流的结构变更刷新运行态；拓扑折叠复用数据库单一规则。"""
        kinds = {
            EventKind.STRUCTURE_STARTED,
            EventKind.STRUCTURE_COMPLETED,
            EventKind.STRUCTURE_COLLAPSED,
            EventKind.STRUCTURE_REMOVED,
        }
        for event in events:
            if event.event_type not in kinds:
                continue
            fields = _structure_event_fields(event)
            updated = fold_structure_snapshot(
                self.structures.get(fields.structure_id),
                event_type=event.event_type,
                structure_id=fields.structure_id,
                tick=event.tick,
                tiles=fields.tiles,
                kind=fields.kind,
                material=fields.material,
                load_bearing=fields.load_bearing,
                supported_by=fields.supported_by,
                owner_id=fields.owner_id,
                built_by=fields.built_by,
            )
            if updated is None:
                self.structures.pop(fields.structure_id, None)
            else:
                self.structures[fields.structure_id] = updated
            if event.event_type in {EventKind.STRUCTURE_STARTED, EventKind.STRUCTURE_REMOVED}:
                self._collapsed.discard(fields.structure_id)
            if event.event_type is EventKind.STRUCTURE_COLLAPSED:
                self._collapsed.add(fields.structure_id)

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
        for seed_id in sorted((collapsed & set(graph.nodes)) - self._collapsed):
            self._cascades.append(start_cascade(graph, (seed_id,)))
        next_cascades: list[CascadeState] = []
        for cascade in self._cascades:
            step = advance_cascade(graph, cascade, tick=tick)
            events.extend(step.events)
            self._collapsed.update(str(e.payload["structure_id"]) for e in step.events)
            if not step.state.done:
                next_cascades.append(step.state)
        self._cascades = next_cascades
        return events


def collapse_injuries(state, events, structures, combat_ledger):
    """坍塌结构瓦片附近实体受伤；死亡仍只经 npc.death 事件。"""
    from sim.core.events import EventKind, npc_death_event

    deaths = []
    for event in events:
        if event.event_type is not EventKind.STRUCTURE_COLLAPSED:
            continue
        snapshot = structures.get(str(event.payload["structure_id"]))
        if snapshot is None:
            continue
        for entity_id, entity in sorted(state.entities.items()):
            near = any(
                abs(entity.pos[0] - tile[0]) + abs(entity.pos[1] - tile[1]) <= 3
                for tile in snapshot.tiles
            )
            if near and combat_ledger.apply_damage(entity_id, 10):
                deaths.append(npc_death_event(tick=event.tick, entity_id=entity_id))
    return deaths
