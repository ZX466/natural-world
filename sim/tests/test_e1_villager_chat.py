"""E1：村民 request_chat 到站开口——npc.chat 落流 + 冷却节流。"""

from pathlib import Path

from sim.core.events import npc_act_event
from sim.core.world import EntityState, WorldState
from sim.npc.sim_exec import npc_events_for_tick
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder

_TOWN = Path("sim/content/linhe-town.json")


class _FakeRuntime:
    """最小 runtime 替身：直接给出一批 npc.act(request_chat)。"""

    def __init__(self, events):
        self._events = events
        self.profiles: dict = {}

    def tick(self, tick):
        return list(self._events)


def _two_villagers_adjacent() -> WorldState:
    """两村民在中心区食摊散点半径内相邻（(30,46) 锚点一带可走）。"""
    return WorldState(
        world_seed=42,
        entities={
            "villager_01": EntityState(entity_id="villager_01", pos=(30, 46)),
            "villager_02": EntityState(entity_id="villager_02", pos=(31, 46)),
        },
    )


def test_arrival_produces_chat_once():
    state = _two_villagers_adjacent()
    rt = _FakeRuntime([npc_act_event(tick=0, npc_id="villager_01", action="request_chat")])
    events = npc_events_for_tick(rt, state, 100, Pathfinder(_TOWN_MAP()), seed=42, chat_last={})
    chats = [e for e in events if e.event_type.value == "npc.chat"]
    assert len(chats) == 1
    assert chats[0].payload["npc_id"] == "villager_01"
    assert chats[0].payload["to_id"] == "villager_02"  # 两实体场景必互指


def test_chat_cooldown_blocks_second():
    state = _two_villagers_adjacent()
    rt = _FakeRuntime([npc_act_event(tick=0, npc_id="villager_01", action="request_chat")])
    chat_last = {"villager_01": 100}  # 刚说过（tick=110 距上次仅 10 < 冷却下限）
    events = npc_events_for_tick(
        rt, state, 110, Pathfinder(_TOWN_MAP()), seed=42, chat_last=chat_last
    )
    assert not [e for e in events if e.event_type.value == "npc.chat"]


def test_chat_last_is_updated_by_producer():
    """开口成功后账本必须刷新（调用方持有的跨拍记忆态）。"""
    state = _two_villagers_adjacent()
    rt = _FakeRuntime([npc_act_event(tick=0, npc_id="villager_01", action="request_chat")])
    chat_last: dict[str, int] = {}
    npc_events_for_tick(rt, state, 100, Pathfinder(_TOWN_MAP()), seed=42, chat_last=chat_last)
    assert chat_last.get("villager_01") == 100


def _TOWN_MAP() -> TileMap:
    return TileMap.from_json_file(_TOWN)
