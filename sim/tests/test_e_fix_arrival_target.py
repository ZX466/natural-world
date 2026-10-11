"""Review 修复验证：I1 到站开口目标 = 邻域最近者（与决策 tick 脱钩）。

修复前：开口用 _chat_target_of(新 tick) 重算——三实体场景会选中不在邻域的
第三人，走了全程说不上话。修复后：开口对象恒为到站邻域内最近者。
"""

from pathlib import Path

from sim.core.events import npc_act_event
from sim.core.world import EntityState, WorldState
from sim.npc.sim_exec import _nearest_other, npc_events_for_tick
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder

_TOWN = Path("sim/content/linhe-town.json")


def test_nearest_other_prefers_adjacent_over_far():
    state = WorldState(
        world_seed=42,
        entities={
            "villager_01": EntityState(entity_id="villager_01", pos=(30, 46)),
            "villager_02": EntityState(entity_id="villager_02", pos=(31, 46)),  # 贴身
            "villager_03": EntityState(entity_id="villager_03", pos=(40, 50)),  # 远
        },
    )
    entity = state.entities["villager_01"]
    assert _nearest_other(entity, state) == "villager_02"


def test_nearest_other_none_when_alone_in_radius():
    state = WorldState(
        world_seed=42,
        entities={
            "villager_01": EntityState(entity_id="villager_01", pos=(30, 46)),
            "villager_03": EntityState(entity_id="villager_03", pos=(40, 50)),
        },
    )
    assert _nearest_other(state.entities["villager_01"], state) is None


def test_opening_talks_to_whomever_is_present():
    """到站开口：邻域内有谁就说给谁（决策走向的第三人不在场也成立）。"""
    tile_map = TileMap.from_json_file(_TOWN)
    state = WorldState(
        world_seed=42,
        entities={
            "villager_01": EntityState(entity_id="villager_01", pos=(30, 46)),
            "villager_02": EntityState(entity_id="villager_02", pos=(31, 46)),
        },
    )
    rt_events = [npc_act_event(tick=0, npc_id="villager_01", action="request_chat")]

    class _FakeRuntime:
        def __init__(self) -> None:
            self.profiles: dict = {}

        def tick(self, tick, *, chat_cooldown_until=None):
            return list(rt_events)

    events = npc_events_for_tick(
        _FakeRuntime(),
        state,
        100,
        Pathfinder(tile_map),
        seed=42,
        chat_last={},
        retell_last={},
    )
    chats = [e for e in events if e.event_type.value == "npc.chat"]
    assert len(chats) == 1
    assert chats[0].payload["to_id"] == "villager_02"
