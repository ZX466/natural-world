"""E3：work 到站计酬——wage grant + 冷却防刷。"""

from pathlib import Path

from sim.core.events import npc_act_event
from sim.core.world import EntityState, WorldState
from sim.npc.sim_exec import npc_events_for_tick
from sim.world.economy import CoinLedger
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder

_TOWN = Path("sim/content/linhe-town.json")


class _FakeRuntime:
    def __init__(self, events, profiles=None):
        self._events = events
        self.profiles = profiles or {}

    def tick(self, tick):
        return list(self._events)


def _state_work_at_site() -> WorldState:
    """villager_10 的定籍 work 锚点邻域（定籍制：锚点由 home_base_of 派生——
    西村→农田北缘 (26,76)；夹具按真实锚点放人，与 D14 到站判定同口径）。"""
    from sim.npc.sim_exec import _site_anchor_of

    anchor = _site_anchor_of("work", "villager_10")
    ax, ay = anchor
    return WorldState(
        world_seed=42,
        entities={"villager_10": EntityState(entity_id="villager_10", pos=(ax, ay))},
    )


def _act_work():
    return npc_act_event(tick=0, npc_id="villager_10", action="work")


def test_work_at_site_pays_wage_once():
    led = CoinLedger()
    rt = _FakeRuntime([_act_work()])
    events = npc_events_for_tick(
        rt,
        _state_work_at_site(),
        1000,
        Pathfinder(_TOWN_MAP()),
        seed=42,
        wage_last={},
        coin_ledger=led,
    )
    grants = [e for e in events if e.event_type.value == "coin.grant"]
    assert len(grants) == 1
    assert grants[0].payload["delta"] == 5
    assert grants[0].payload["note"] == "wage:work"
    assert led.balance_of("villager_10") == 5


def test_wage_cooldown_blocks_double_pay():
    led = CoinLedger()
    rt = _FakeRuntime([_act_work()])
    wage_last = {"villager_10": 1000}  # 刚领过（tick=1010 距上次 10 < 冷却下限）
    events = npc_events_for_tick(
        rt,
        _state_work_at_site(),
        1010,
        Pathfinder(_TOWN_MAP()),
        seed=42,
        wage_last=wage_last,
        coin_ledger=led,
    )
    assert not [e for e in events if e.event_type.value == "coin.grant"]


def test_wage_off_site_no_pay():
    """不在本人 work 锚点邻域（没到田里）不发工钱——到站才计酬（D3 口径）。"""
    led = CoinLedger()
    rt = _FakeRuntime([_act_work()])
    # 东村宅前 (82,38)：远离 villager_10 的西村农田北缘锚点（距离 > 散点半径）
    far_state = WorldState(
        world_seed=42,
        entities={"villager_10": EntityState(entity_id="villager_10", pos=(82, 38))},
    )
    events = npc_events_for_tick(
        rt,
        far_state,
        1000,
        Pathfinder(_TOWN_MAP()),
        seed=42,
        wage_last={},
        coin_ledger=led,
    )
    assert not [e for e in events if e.event_type.value == "coin.grant"]
    assert led.balance_of("villager_10") == 0


def _TOWN_MAP() -> TileMap:
    return TileMap.from_json_file(_TOWN)
