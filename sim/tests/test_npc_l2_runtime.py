"""A ready model action affects L2 only; downgrade waits for the dialogue grace period."""

from sim.core.events import EventKind
from sim.npc.model import Need, NpcProfileData
from sim.npc.runtime import NpcRuntime
from sim.npc.utility import UtilityModel


def _runtime(lod=2):
    profile = NpcProfileData(
        npc_id="villager",
        name="阿青",
        lod=lod,
        needs=(Need("hunger", 0.9, 1), Need("energy", 0.2, 1)),
    )
    return NpcRuntime({profile.npc_id: profile}, UtilityModel(1))


def test_ready_model_action_overrides_utility_only_for_l2():
    l2 = _runtime()
    event = next(
        event
        for event in l2.tick(36000, action_overrides={"villager": "rest"})
        if event.event_type is EventKind.NPC_ACT
    )
    assert event.payload["action"] == "rest"
    assert event.payload["params"] == {}
    l1 = _runtime(lod=1)
    event = next(
        event
        for event in l1.tick(36000, action_overrides={"villager": "rest"})
        if event.event_type is EventKind.NPC_ACT
    )
    assert event.payload["action"] == "eat"


def test_l2_downgrade_waits_thirty_game_seconds_outside_range():
    runtime = _runtime(lod=1)
    written = []
    runtime.on_downgrade = written.append
    runtime.update_lod("villager", in_interaction=True, tick=10)
    assert runtime.profiles["villager"].lod == 2
    runtime.update_lod("villager", in_interaction=False, tick=20)
    runtime.update_lod("villager", in_interaction=False, tick=49)
    assert runtime.profiles["villager"].lod == 2
    assert written == []
    runtime.update_lod("villager", in_interaction=False, tick=50)
    assert runtime.profiles["villager"].lod == 1
    assert written == ["villager"]


def test_dialogue_and_returning_to_range_restart_downgrade_grace():
    runtime = _runtime()
    runtime.update_lod("villager", in_interaction=False, tick=10)
    runtime.note_dialogue("villager", tick=30)
    runtime.update_lod("villager", in_interaction=False, tick=59)
    assert runtime.profiles["villager"].lod == 2
    runtime.update_lod("villager", in_interaction=True, tick=60)
    runtime.update_lod("villager", in_interaction=False, tick=70)
    runtime.update_lod("villager", in_interaction=False, tick=99)
    assert runtime.profiles["villager"].lod == 2
    runtime.update_lod("villager", in_interaction=False, tick=100)
    assert runtime.profiles["villager"].lod == 1


def test_unavailable_model_returns_to_l1_without_waiting_or_promoting():
    runtime = _runtime()
    runtime.update_lod("villager", in_interaction=True, tick=10, allow_l2=False)
    assert runtime.profiles["villager"].lod == 1
    runtime.update_lod("villager", in_interaction=True, tick=20, allow_l2=False)
    assert runtime.profiles["villager"].lod == 1
