"""E1：talk_to/investigate 执行面——闸门放行的对话/张望终于落地成事件。"""

from sim.agent.dialogue import template_line
from sim.agent.driver import ChenmoDriver
from sim.content.protagonist import build_anchor
from sim.core.clock import GameClock
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.llm.prompts.banned_words import scan
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder


def _state_pair() -> WorldState:
    """陈默与村民相邻（贴脸距离），真实 96×96 图上可走。"""
    return WorldState(
        world_seed=42,
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(30, 46)),
            "villager_01": EntityState(entity_id="villager_01", pos=(31, 46)),
        },
    )


def _town_map() -> TileMap:
    from pathlib import Path

    return TileMap.from_json_file(Path("sim/content/linhe-town.json"))


class _NullLlm:
    """driver 不走 decide_once（直接塞 pending），llm 桩不需要 complete。"""


def _driver(**kwargs) -> ChenmoDriver:
    defaults: dict = {
        "anchor": build_anchor(),
        "llm": _NullLlm(),
        "profile_provider": lambda: None,
    }
    defaults.update(kwargs)
    return ChenmoDriver(**defaults)


def _loop(state: WorldState) -> TickLoop:
    return TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)


def test_execute_talk_to_produces_chat_and_monologue():
    loop = _loop(_state_pair())
    driver = _driver(display_name_of={"villager_01": "赵铁柱"}.get)
    from sim.agent.intent import Intent

    driver._pending.append(
        Intent(action="talk_to", target_id="villager_01", reason="我想问问行情", confidence=0.9)
    )
    executed = driver.execute_pending(loop, pathfinder=Pathfinder(_town_map()))
    assert executed == 1
    kinds = [e.event_type.value for e in loop.drain_events()]
    assert "npc.chat" in kinds
    assert "npc.monologue" in kinds


def test_chat_line_uses_display_name_and_passes_banned_scan():
    loop = _loop(_state_pair())
    driver = _driver(display_name_of={"villager_01": "赵铁柱"}.get)
    from sim.agent.intent import Intent

    driver._pending.append(
        Intent(action="talk_to", target_id="villager_01", reason="问问行情", confidence=0.9)
    )
    driver.execute_pending(loop, pathfinder=Pathfinder(_town_map()))
    events = loop.drain_events()
    chats = [e for e in events if e.event_type.value == "npc.chat"]
    assert len(chats) == 1
    line = chats[0].payload["line"]
    assert "赵铁柱" in line  # 称呼用戏内名（非 entity_id 出站）
    assert not scan(line).hits


def test_talk_line_deterministic_per_tick():
    # C5：同 (speaker, listener, tick) 恒同句
    a = template_line("chenmo", "赵铁柱", 777)
    b = template_line("chenmo", "赵铁柱", 777)
    assert a == b
    assert "{listener}" not in a  # 占位符已填


def test_investigate_moves_toward_target_pos():
    from sim.agent.intent import Intent

    # 隔 5 格的直线可走区（药铺前空地一带）
    state = WorldState(
        world_seed=42,
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(30, 46)),
        },
    )
    loop = _loop(state)
    driver = _driver()
    driver._pending.append(
        Intent(action="investigate", target_pos=(34, 46), reason="那边有动静", confidence=0.9)
    )
    pf = Pathfinder(_town_map())
    driver.execute_pending(loop, pathfinder=pf)
    events = loop.drain_events()
    moves = [e for e in events if e.event_type.value == "move"]
    assert len(moves) == 1
    assert moves[0].payload["goal"] == [34, 46]


def test_template_pool_all_clean():
    for tick in range(0, 50):
        line = template_line("chenmo", "张三", tick)
        assert not scan(line).hits, f"tick={tick} 模板词面违规: {line}"
