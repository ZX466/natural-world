"""E2：retell——有记忆的村民会向别人学舌（bubble + trust 漂移 + 冷却）。"""

from sim.llm.prompts.banned_words import scan
from sim.npc.chat_ledger import ChatLedger
from sim.npc.sim_exec import retell_template


def test_retell_template_format():
    assert retell_template("赵铁柱", "东边着火了") == "听赵铁柱说，东边着火了"


def test_ledger_retell_moves_trust():
    led = ChatLedger()
    led.adjust("a", "b", kind="retell")
    assert led.relations_of("a")["b"]["trust"] > 0.0


def test_retell_text_passes_banned_scan():
    line = retell_template("赵铁柱", "东边着火了")
    assert not scan(line).hits


def test_villager_with_memory_retells_on_chat_beat():
    """有记忆的村民开口同拍产 retell bubble（学舌自己记忆里最新一条）。"""
    from pathlib import Path

    from sim.core.events import npc_act_event
    from sim.core.world import EntityState, WorldState
    from sim.npc.sim_exec import npc_events_for_tick
    from sim.world.map import TileMap
    from sim.world.pathfinding import Pathfinder

    tile_map = TileMap.from_json_file(Path("sim/content/linhe-town.json"))
    state = WorldState(
        world_seed=42,
        entities={
            "villager_01": EntityState(entity_id="villager_01", pos=(30, 46)),
            "villager_02": EntityState(entity_id="villager_02", pos=(31, 46)),
        },
    )
    ledger = ChatLedger()
    ledger.remember("villager_01", "东边着火了", tick=90)
    rt_events = [npc_act_event(tick=0, npc_id="villager_01", action="request_chat")]

    class _FakeRuntime:
        def __init__(self) -> None:
            self.profiles: dict = {}

        def tick(self, tick):
            return list(rt_events)

    events = npc_events_for_tick(
        _FakeRuntime(),
        state,
        100,
        Pathfinder(tile_map),
        seed=42,
        chat_last={},
        retell_last={},
        display_name_of={"villager_01": "赵铁柱", "villager_02": "钱小满"},
        chat_ledger=ledger,
    )

    def _is_retell(e) -> bool:
        if e.event_type.value != "npc.monologue":
            return False
        content = str(e.payload.get("content", ""))
        return content.startswith("听") and "听说" not in content

    retells = [e for e in events if _is_retell(e)]
    assert len(retells) == 1
    content = retells[0].payload["content"]
    assert content == "听赵铁柱说，东边着火了"
    assert retells[0].payload["form"] == "bubble"
    # trust 漂移落账：villager_01 对听话人 trust 上升
    assert ledger.relations_of("villager_01")


def test_retell_cooldown_blocks_repeat():
    from pathlib import Path

    from sim.core.events import npc_act_event
    from sim.core.world import EntityState, WorldState
    from sim.npc.sim_exec import npc_events_for_tick
    from sim.world.map import TileMap
    from sim.world.pathfinding import Pathfinder

    tile_map = TileMap.from_json_file(Path("sim/content/linhe-town.json"))
    state = WorldState(
        world_seed=42,
        entities={
            "villager_01": EntityState(entity_id="villager_01", pos=(30, 46)),
            "villager_02": EntityState(entity_id="villager_02", pos=(31, 46)),
        },
    )
    ledger = ChatLedger()
    ledger.remember("villager_01", "东边着火了", tick=90)
    rt_events = [npc_act_event(tick=0, npc_id="villager_01", action="request_chat")]

    class _FakeRuntime:
        def __init__(self) -> None:
            self.profiles: dict = {}

        def tick(self, tick):
            return list(rt_events)

    # 刚学过（tick=100 刚 retell，tick=110 再试——距上次 10 tick < 冷却下限）
    retell_last = {"villager_01": 100}
    events = npc_events_for_tick(
        _FakeRuntime(),
        state,
        110,
        Pathfinder(tile_map),
        seed=42,
        chat_last={"villager_01": 100},
        retell_last=retell_last,
        chat_ledger=ledger,
    )
    retells = [
        e
        for e in events
        if e.event_type.value == "npc.monologue"
        and str(e.payload.get("content", "")).startswith("听")
    ]
    assert not retells
