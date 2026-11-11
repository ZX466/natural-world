"""LOD 升降必须真的出流：runtime 产出的事件不能在批处理里被静默丢弃。"""

from __future__ import annotations

import pytest

from sim.core.world import EntityState, WorldState
from sim.npc.model import Need, NpcProfileData
from sim.npc.runtime import NpcRuntime
from sim.npc.sim_exec import npc_events_for_tick
from sim.npc.utility import UtilityModel
from sim.world.map import Chunk, TileMap
from sim.world.pathfinding import Pathfinder


def _profile(npc_id: str, *, lod: int) -> NpcProfileData:
    return NpcProfileData(
        npc_id=npc_id,
        name=npc_id,
        needs=(Need("hunger", 0.3, 1.0),),
        lod=lod,
        identity_anchor=f"anchor-{npc_id}",
    )


def _runtime() -> NpcRuntime:
    return NpcRuntime(
        profiles={
            "chenmo": _profile("chenmo", lod=2),
            "villager_01": _profile("villager_01", lod=1),
        },
        utility=UtilityModel(n_npc=2),
    )


def _world() -> WorldState:
    return WorldState(
        world_seed=42,
        tick=0,
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(5, 5)),
            "villager_01": EntityState(entity_id="villager_01", pos=(5, 6)),
        },
    )


def _pathfinder() -> Pathfinder:
    return Pathfinder(
        TileMap(
            width=16,
            height=16,
            chunks={(0, 0): Chunk(cx=0, cy=0, ground=(1,) * 256, collision=(True,) * 256)},
        )
    )


def test_promotion_event_reaches_the_tick_batch() -> None:
    """升格事件必须随本拍批次出流，否则落库的 lod 永远停在旧值。"""
    runtime = _runtime()
    runtime.update_lod("villager_01", in_interaction=True, tick=0, allow_l2=True)
    assert runtime.profiles["villager_01"].lod == 2

    batch = npc_events_for_tick(runtime, _world(), 1, _pathfinder(), seed=42)

    lod_events = [e for e in batch if e.event_type.value == "npc.lod_change"]
    assert len(lod_events) == 1
    assert lod_events[0].payload["npc_id"] == "villager_01"
    assert lod_events[0].payload["from_lod"] == 1
    assert lod_events[0].payload["to_lod"] == 2


def test_demotion_event_reaches_the_tick_batch() -> None:
    """降格同理：丢事件等于库里的 lod 永远不会降回 1。"""
    runtime = _runtime()
    runtime.update_lod("villager_01", in_interaction=True, tick=0, allow_l2=True)
    npc_events_for_tick(runtime, _world(), 1, _pathfinder(), seed=42)

    runtime.update_lod("villager_01", in_interaction=False, tick=10, allow_l2=True)
    runtime.update_lod("villager_01", in_interaction=False, tick=40, allow_l2=True)
    assert runtime.profiles["villager_01"].lod == 1

    batch = npc_events_for_tick(runtime, _world(), 41, _pathfinder(), seed=42)

    lod_events = [e for e in batch if e.event_type.value == "npc.lod_change"]
    assert len(lod_events) == 1
    assert lod_events[0].payload["to_lod"] == 1


def test_lod_event_does_not_displace_the_action_or_its_move() -> None:
    """加 LOD 事件不能挤掉同一拍的 npc.act。"""
    runtime = _runtime()
    runtime.update_lod("villager_01", in_interaction=True, tick=0, allow_l2=True)

    batch = npc_events_for_tick(runtime, _world(), 1, _pathfinder(), seed=42)

    assert any(e.event_type.value == "npc.act" for e in batch)
    assert len({e.payload.get("npc_id") for e in batch if e.event_type.value == "npc.act"}) == 2


def test_replayed_tick_without_lod_change_emits_nothing_extra() -> None:
    """无升降时不得凭空造 LOD 事件（C5：同输入同输出）。"""
    runtime = _runtime()

    batch = npc_events_for_tick(runtime, _world(), 1, _pathfinder(), seed=42)

    assert not [e for e in batch if e.event_type.value == "npc.lod_change"]


@pytest.mark.parametrize("lod", [0, 1, 2])
def test_lod_events_are_valid_store_rows(lod: int) -> None:
    from sim.core.persistence.event_validation import validate_store_row

    runtime = _runtime()
    if lod != 1:
        runtime.update_lod("villager_01", in_interaction=lod == 2, tick=0, allow_l2=lod == 2)
    batch = npc_events_for_tick(runtime, _world(), 1, _pathfinder(), seed=42)
    for event in batch:
        validate_store_row(event.to_store_dict())
