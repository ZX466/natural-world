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
    # 转述只能传播**别人**的话，故记忆的说话人是 villager_02（不是本人）。
    ledger.remember("villager_01", "东边着火了", tick=90, speaker="villager_02")
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
    assert content == "听钱小满说，东边着火了"
    assert retells[0].payload["form"] == "bubble"
    # trust 漂移落账：villager_01 对听话人 trust 上升
    assert ledger.relations_of("villager_01")


def test_retell_attributes_original_speaker_not_reteller():
    """转述必须署**原说话人**的名字，不能拿转述者自己填模板。

    2026-11-04 实机验收发现：隔离库 3 分钟采样里 92/92 条「听X说」的 X 都是
    转述者本人（「听喻桶匠说，喻桶匠，我先去忙」）。根因是 `ChatLedger.remember`
    只落 (tick, content)，说话人没落，转述时无处可查。
    """
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
    # villager_01 听 **villager_02** 说过这句话（说话人是 02，不是 01 自己）。
    ledger.remember("villager_01", "东边着火了", tick=90, speaker="villager_02")
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
        display_name_of={"villager_01": "赵铁柱", "villager_02": "钱小满"},
        chat_ledger=ledger,
    )
    retells = [
        e
        for e in events
        if e.event_type.value == "npc.monologue"
        and str(e.payload.get("content", "")).startswith("听")
    ]
    assert len(retells) == 1
    assert retells[0].payload["content"] == "听钱小满说，东边着火了"


def test_retell_skips_own_words_picks_other_speaker():
    """转述只能传播**别人**的话：最新记忆若是自己刚说的，要往前找别人的。

    2026-11-04 修后实机复验仍 37/62 自指：`sim_exec.py` 会把说话人自己那句
    也落进自己的记忆（`speaker=npc_id`），于是 `_prior_mems[-1]` 常是本人台词
    ⇒ 「听奚船家说，韩书生，吃了没？」（奚船家转述自己）。
    """
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
    ledger.remember("villager_01", "东边着火了", tick=90, speaker="villager_02")
    # 最新一条是 villager_01 **自己**说的 —— 不能拿来当转述源。
    ledger.remember("villager_01", "我先去忙，回头聊", tick=95, speaker="villager_01")
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
        display_name_of={"villager_01": "赵铁柱", "villager_02": "钱小满"},
        chat_ledger=ledger,
    )
    retells = [
        e
        for e in events
        if e.event_type.value == "npc.monologue"
        and str(e.payload.get("content", "")).startswith("听")
    ]
    assert len(retells) == 1
    assert retells[0].payload["content"] == "听钱小满说，东边着火了"


def test_retell_skipped_when_only_own_words():
    """记忆里全是我自己说的话 ⇒ 没有可转述的别人内容，不出 retell。"""
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
    ledger.remember("villager_01", "我先去忙，回头聊", tick=95, speaker="villager_01")
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
        display_name_of={"villager_01": "赵铁柱", "villager_02": "钱小满"},
        chat_ledger=ledger,
    )
    retells = [
        e
        for e in events
        if e.event_type.value == "npc.monologue"
        and str(e.payload.get("content", "")).startswith("听")
    ]
    assert not retells


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
    # 有话可转述（说话人是别人），否则本测会因为「无外人之言」而假通过。
    ledger.remember("villager_01", "东边着火了", tick=90, speaker="villager_02")
    rt_events = [npc_act_event(tick=0, npc_id="villager_01", action="request_chat")]

    class _FakeRuntime:
        def __init__(self) -> None:
            self.profiles: dict = {}

        def tick(self, tick, *, chat_cooldown_until=None):
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
