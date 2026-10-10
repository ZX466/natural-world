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
