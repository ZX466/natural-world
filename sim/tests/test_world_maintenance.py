from sim.core.events import EventKind
from sim.world.maintenance import WorldMaintenance
from sim.world.matter import MatterLedger
from sim.world.structure import StructurePhase, StructureSnapshot


def _structure(sid: str, supported_by: tuple[str, ...] = ()) -> StructureSnapshot:
    return StructureSnapshot(
        structure_id=sid,
        tiles=((len(sid), 0),),
        kind="shed",
        material="wood",
        phase=StructurePhase.ACTIVE,
        load_bearing=True,
        supported_by=supported_by,
    )


def test_decay_is_production_event_source() -> None:
    ledger = MatterLedger()
    ledger.register("base", integrity=0.2, decay_rate=0.3)
    runtime = WorldMaintenance(ledger=ledger, structures={})

    events = runtime.tick(tick=1, seed=42)

    assert any(event.event_type is EventKind.MATTER_COLLAPSE for event in events)
    assert ledger.state("base").is_rubble is True


def test_support_loss_cascades_dependents() -> None:
    ledger = MatterLedger()
    ledger.register("base", integrity=0.0, decay_rate=0.0)
    ledger.register("roof", integrity=1.0, decay_rate=0.0)
    runtime = WorldMaintenance(
        ledger=ledger,
        structures={"base": _structure("base"), "roof": _structure("roof", ("base",))},
    )

    events = runtime.tick(tick=1, seed=42)

    assert [
        event.payload["structure_id"]
        for event in events
        if event.event_type is EventKind.STRUCTURE_COLLAPSED
    ] == ["base", "roof"]


def test_runtime_tracks_new_structures_and_cascade_does_not_repeat():
    from sim.core.events import structure_completed_event, structure_started_event

    ledger = MatterLedger()
    runtime = WorldMaintenance(ledger=ledger, structures={})
    started = structure_started_event(
        1,
        structure_id="base",
        tiles=((3, 2),),
        kind="shed",
        material="wood",
        planned_duration_ticks=100,
        recipe_id="shed",
        recipe_version="v1",
        build_rule_version="v1",
        load_bearing=True,
    )
    completed = structure_completed_event(2, structure_id="base", quality=0.8, integrity=1.0)
    runtime.observe((started, completed))
    assert runtime.structures["base"].phase is StructurePhase.ACTIVE
    ledger.register("base", integrity=0.0, decay_rate=0.0)
    assert [e.event_type for e in runtime.tick(tick=3, seed=42)] == [EventKind.STRUCTURE_COLLAPSED]
    assert not [
        e for e in runtime.tick(tick=4, seed=42) if e.event_type is EventKind.STRUCTURE_COLLAPSED
    ]
