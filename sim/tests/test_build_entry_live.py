"""S4: 建造入口、入站拒绝与执行到站/资金边界。"""

from pathlib import Path

import pytest

from sim.agent.build_exec import BuildRuntime
from sim.api import ws
from sim.core.events import EventKind, npc_act_event
from sim.core.world import EntityState, WorldState
from sim.npc.actions import payload_keys_allowed
from sim.npc.sim_exec import npc_events_for_tick
from sim.world.economy import CoinLedger
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder


def town_and_site():
    town = TileMap.from_json_file(Path(__file__).resolve().parents[1] / "content/linhe-town.json")
    pos = next(
        (x, y)
        for y in range(town.height - 1)
        for x in range(town.width - 1)
        if all(town.is_walkable(x + dx, y + dy) for dx in (0, 1) for dy in (0, 1))
    )
    return town, pos


def test_build_whitelist_and_player_impulse_translate_to_thought(monkeypatch):
    assert payload_keys_allowed("build", {"x", "y"})
    assert not payload_keys_allowed("build", {"x", "y", "cost"})
    thoughts = []
    monkeypatch.setattr(ws, "_IMPULSE_TRIGGER", thoughts.append)
    response = ws._handle_player_impulse(
        {"text": "搭个木棚", "action": "build", "target_pos": [72, 52]}
    )
    assert response["injected"] is True
    assert thoughts and "72" in thoughts[0] and "52" in thoughts[0]


@pytest.mark.parametrize("target", [None, [True, 2], [1.2, 2], [-1, 2], [1], "1,2"])
def test_malformed_build_impulse_is_rejected(target, monkeypatch):
    thoughts = []
    monkeypatch.setattr(ws, "_IMPULSE_TRIGGER", thoughts.append)
    response = ws._handle_player_impulse(
        {"text": "搭棚子", "action": "build", "target_pos": target}
    )
    assert response["type"] == "error" and not thoughts


@pytest.mark.parametrize(
    ("at_site", "money", "started"), [(True, 40, True), (False, 40, False), (True, 39, False)]
)
def test_build_execution_respects_arrival_and_funds(at_site, money, started):
    town, pos = town_and_site()
    actor_pos = pos if at_site else (pos[0] + 10, pos[1] + 10)
    state = WorldState(entities={"builder": EntityState(entity_id="builder", pos=actor_pos)})
    ledger = CoinLedger()
    ledger.apply_grant("builder", money, tick=0)
    build = BuildRuntime(town, seed=42)

    class Runtime:
        def tick(self, tick, **kwargs):
            return [
                npc_act_event(tick, "builder", "build", params={"x": str(pos[0]), "y": str(pos[1])})
            ]

    events = npc_events_for_tick(
        Runtime(), state, 0, Pathfinder(town), seed=42, coin_ledger=ledger, build_runtime=build
    )
    assert any(e.event_type is EventKind.STRUCTURE_STARTED for e in events) is started
    assert ledger.balance_of("builder") == money - (40 if started else 0)
