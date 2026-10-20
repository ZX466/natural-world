"""S3: 日程必须改变真实效用候选，并把集市目标传到移动执行。"""

from pathlib import Path
from typing import cast

import numpy as np
import pytest

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.core.events import EventKind
from sim.core.world import EntityState, WorldState
from sim.npc.model import Need, NpcProfileData
from sim.npc.runtime import NpcRuntime
from sim.npc.schedule import current_slot
from sim.npc.sim_exec import npc_events_for_tick
from sim.npc.utility import UtilityModel, utility_scores_matrix
from sim.world.economy import CoinLedger
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder

DAY = 12 * 3600


def profile(nid: str, occupation: str) -> NpcProfileData:
    return NpcProfileData(nid, nid, occupation=occupation, ocean=(0, 0, 0, 0, 0))


def test_personal_routine_changes_runtime_decisions():
    people = {"farmer": profile("farmer", "农人"), "artist": profile("artist", "艺人")}
    runtime = NpcRuntime(profiles=people, utility=UtilityModel(2))
    acts = runtime.tick(TICKS_PER_GAME_DAY + DAY)
    actions = {e.payload["npc_id"]: e.payload["action"] for e in acts}
    assert actions == {"farmer": "work", "artist": "request_chat"}


def test_slot_bonus_is_bounded_and_survival_is_unchanged():
    people = [profile("farmer", "农人")]
    model = UtilityModel(1)
    base = utility_scores_matrix(people, model)
    slots = [current_slot(TICKS_PER_GAME_DAY + DAY, people[0])]
    actual = utility_scores_matrix(people, model, schedule_slots=slots)
    expected = np.zeros_like(base)
    expected[0, model.action_index["work"]] = 0.18
    np.testing.assert_allclose(actual - base, expected, atol=1e-7)
    with pytest.raises(ValueError):
        utility_scores_matrix(people, model, schedule_slots=[])
    hungry = people[0].with_needs((Need("hunger", 1.0, 1.0),))
    runtime = NpcRuntime(profiles={hungry.npc_id: hungry}, utility=UtilityModel(1))
    hungry_act = runtime.tick(DAY)[0].payload
    assert hungry_act["action"] == "eat" and hungry_act["target"] == ""


def test_market_day_reaches_the_market_in_execution():
    merchant = profile("merchant", "商贩")
    runtime = NpcRuntime(profiles={merchant.npc_id: merchant}, utility=UtilityModel(1))
    town = TileMap.from_json_file(Path(__file__).resolve().parents[1] / "content/linhe-town.json")
    state = WorldState(entities={"merchant": EntityState(entity_id="merchant", pos=(44, 53))})
    events = npc_events_for_tick(runtime, state, DAY, Pathfinder(town), seed=42)
    act = next(e for e in events if e.event_type is EventKind.NPC_ACT)
    assert act.payload["action"] == "work" and act.payload["target"] == "market"
    move = next(e for e in events if e.event_type is EventKind.MOVE)
    x, y = cast("tuple[int, int]", move.payload["goal"])
    assert abs(x - 72) + abs(y - 52) <= 4
    assert current_slot(TICKS_PER_GAME_DAY + DAY, merchant).target == ""
    assert current_slot(3 * 3600, merchant).target == ""


def test_market_work_pays_only_after_market_arrival():
    merchant = profile("merchant", "商贩")
    runtime = NpcRuntime(profiles={merchant.npc_id: merchant}, utility=UtilityModel(1))
    town = TileMap.from_json_file(Path(__file__).resolve().parents[1] / "content/linhe-town.json")
    ledger = CoinLedger()
    for pos, paid in [((44, 53), False), ((72, 52), True)]:
        state = WorldState(entities={"merchant": EntityState(entity_id="merchant", pos=pos)})
        npc_events_for_tick(
            runtime, state, DAY, Pathfinder(town), seed=42, wage_last={}, coin_ledger=ledger
        )
        assert (ledger.balance_of("merchant") > 0) is paid
