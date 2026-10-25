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


def test_collapse_incapacitates_protagonist_instead_of_killing() -> None:
    """DA-07：坍塌致死对主角只失能，普通 NPC 仍死亡。"""
    from sim.agent.combat_exec import CombatLedger
    from sim.core.events import structure_collapsed_event
    from sim.core.world import EntityState, WorldState
    from sim.world.maintenance import collapse_injuries

    ledger = CombatLedger()
    state = WorldState(
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(4, 0)),
            "near": EntityState(entity_id="near", pos=(4, 0)),
        }
    )
    events = [structure_collapsed_event(5, structure_id="base", cause="support_lost")]
    injuries = collapse_injuries(state, events, {"base": _structure("base")}, ledger)

    by_entity = {str(e.payload["entity_id"]): e for e in injuries}
    assert by_entity["chenmo"].event_type is EventKind.AGENT_INCAPACITATED
    assert by_entity["near"].event_type is EventKind.NPC_DEATH
    assert ledger.hp_of("chenmo") == 0 and ledger.hp_of("near") == 0


def test_collapse_does_not_reincapacitate_protagonist() -> None:
    """已经失能的主角不再重复产失能事件（否则每拍刷一条）。"""
    from sim.agent.combat_exec import CombatLedger
    from sim.core.events import structure_collapsed_event
    from sim.core.world import EntityState, WorldState
    from sim.world.maintenance import collapse_injuries

    ledger = CombatLedger()
    ledger.apply_damage("chenmo", 10)
    state = WorldState(
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(4, 0), incapacitated_until=100),
        }
    )
    events = [structure_collapsed_event(5, structure_id="base", cause="support_lost")]
    injuries = collapse_injuries(state, events, {"base": _structure("base")}, ledger)

    assert injuries == []


def test_one_entity_is_injured_once_per_collapse_batch() -> None:
    """同批多次坍塌：同一实体只产一条伤害事件（重复 npc.death 会 fail-closed 崩帧）。"""
    from sim.agent.combat_exec import CombatLedger
    from sim.core.events import structure_collapsed_event
    from sim.core.world import EntityState, WorldState
    from sim.world.maintenance import collapse_injuries

    state = WorldState(
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(4, 0)),
            "near": EntityState(entity_id="near", pos=(4, 0)),
        }
    )
    structures = {"base": _structure("base"), "shed": _structure("shed")}
    events = [
        structure_collapsed_event(5, structure_id="base", cause="support_lost"),
        structure_collapsed_event(5, structure_id="shed", cause="support_lost"),
    ]
    injuries = collapse_injuries(state, events, structures, CombatLedger())

    assert [str(e.payload["entity_id"]) for e in injuries].count("chenmo") == 1
    assert [str(e.payload["entity_id"]) for e in injuries].count("near") == 1


def test_ticks_with_injuries_report_collapse_and_incapacitation() -> None:
    """生产维护入口：衰减致塌 → 同批事件带坍塌致伤（不是只塌不伤人）。"""
    from sim.agent.combat_exec import CombatLedger
    from sim.core.world import EntityState, WorldState
    from sim.world.maintenance import tick_with_injuries

    ledger = MatterLedger()
    ledger.register("base", integrity=0.0, decay_rate=0.0)
    runtime = WorldMaintenance(ledger=ledger, structures={"base": _structure("base")})
    state = WorldState(
        entities={"chenmo": EntityState(entity_id="chenmo", pos=(4, 0))},
    )

    events = tick_with_injuries(state, runtime, CombatLedger(), tick=1, seed=42)

    kinds = [event.event_type for event in events]
    assert EventKind.STRUCTURE_COLLAPSED in kinds
    assert EventKind.AGENT_INCAPACITATED in kinds


def test_collapse_hurts_only_nearby_living_entities():
    from sim.agent.combat_exec import CombatLedger
    from sim.core.events import structure_collapsed_event
    from sim.core.world import EntityState, WorldState
    from sim.world.maintenance import collapse_injuries

    ledger = CombatLedger()
    state = WorldState(
        entities={
            "near": EntityState(entity_id="near", pos=(4, 0)),
            "far": EntityState(entity_id="far", pos=(20, 20)),
        }
    )
    events = [structure_collapsed_event(0, structure_id="base", cause="support_lost")]
    deaths = collapse_injuries(state, events, {"base": _structure("base")}, ledger)
    assert [e.payload["entity_id"] for e in deaths] == ["near"]
    assert ledger.hp_of("near") == 0 and ledger.hp_of("far") == 10
