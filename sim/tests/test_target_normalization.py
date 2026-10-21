"""DA-04：戏内目标通过真实决策/闸门/执行链，内部键不进入模型消息。"""

import json
import re
from typing import cast

import pytest
import structlog
from structlog.testing import capture_logs

from sim.agent.driver import ChenmoDriver
from sim.content.protagonist import build_anchor
from sim.core.clock import GameClock
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.llm.client import LlmClient, ProfileSnapshot
from sim.tests.test_m4c_llm_driver import _FakeLlm, _FakeProfile
from sim.world.economy import CoinLedger


@pytest.fixture(autouse=True)
def current_logging_configuration(monkeypatch):
    # 真实 lifespan 会重新装配 processors；旧缓存代理不能绑定到前一轮的链。
    from sim.agent import driver as driver_module

    monkeypatch.setattr(driver_module, "logger", structlog.get_logger())


class RecordingLlm(_FakeLlm):
    def __init__(self, content):
        super().__init__(content)
        self.prompts = []

    async def complete(self, profile, messages, decision=None, *, max_tokens_override=None):
        self.prompts.append(messages)
        return await super().complete(
            profile, messages, decision, max_tokens_override=max_tokens_override
        )


def decision(action, target=None, *, positions=None, names=None):
    positions = positions or {"chenmo": (10, 10), "villager_01": (11, 10)}
    names = names if names is not None else {"chenmo": "陈默", "villager_01": "赵铁柱"}
    state = WorldState(
        world_seed=42,
        entities={
            actor_id: EntityState(entity_id=actor_id, pos=pos)
            for actor_id, pos in positions.items()
        },
    )
    loop = TickLoop(GameClock(), build_default_bus(), state)
    ledger = CoinLedger()
    assert ledger.apply_grant("chenmo", 100, tick=0)
    llm = RecordingLlm(
        json.dumps(
            {"action": action, "target_id": target, "reason": "我想去问个好。", "confidence": 0.9},
            ensure_ascii=False,
        )
    )
    driver = ChenmoDriver(
        anchor=build_anchor(),
        llm=cast(LlmClient, llm),
        profile_provider=lambda: cast(ProfileSnapshot, _FakeProfile()),
        display_name_of=names.get,
        economy_provider=lambda: (ledger, 42),
    )
    return driver, loop, ledger, llm


async def test_talk_to_inworld_name_resolves_to_entity():
    driver, loop, _, _ = decision("talk_to", "赵铁柱")
    assert await driver.decide_once(loop.state, 0)
    assert len(driver._pending) == 1
    assert driver._pending[0].target_id == "villager_01"
    assert driver.execute_pending(loop, pathfinder=None) == 1
    chats = [event for event in loop.drain_events() if event.event_type == "npc.chat"]
    assert len(chats) == 1
    assert chats[0].payload["to_id"] == "villager_01"


async def test_buy_chinese_good_name_produces_coin_grant():
    driver, loop, ledger, _ = decision("buy", "草药")
    assert await driver.decide_once(loop.state, 0)
    assert driver.execute_pending(loop, pathfinder=None) == 1
    events = loop.drain_events()
    assert ledger.balance_of("chenmo") < 100
    assert len([event for event in events if event.event_type == "coin.grant"]) == 1
    assert any(
        event.event_type == "npc.monologue" and "草药" in str(event.payload["content"])
        for event in events
    )


async def test_buy_internal_id_still_works():
    driver, loop, ledger, _ = decision("buy", "herb")
    assert await driver.decide_once(loop.state, 0)
    assert driver.execute_pending(loop, pathfinder=None) == 1
    assert ledger.balance_of("chenmo") < 100
    assert any(event.event_type == "coin.grant" for event in loop.drain_events())


async def test_unknown_person_still_rejected():
    driver, loop, _, _ = decision("talk_to", "张无忌")
    with capture_logs() as logs:
        assert await driver.decide_once(loop.state, 0)
    assert not driver._pending
    assert loop.drain_events() == []
    assert any(
        row.get("event") == "chenmo.gate_rejected" and row["reason"] == "unknown_target"
        for row in logs
    )


async def test_unknown_good_rejected_with_log():
    driver, loop, ledger, _ = decision("buy", "假药")
    with capture_logs() as logs:
        assert await driver.decide_once(loop.state, 0)
        assert driver.execute_pending(loop, pathfinder=None) == 0
    assert ledger.balance_of("chenmo") == 100
    assert loop.drain_events() == []
    assert any(
        row.get("event") == "chenmo.trade_rejected" and row["reason"] == "unknown_good"
        for row in logs
    )


@pytest.mark.parametrize("second_position", [(12, 10), (100, 100)])
async def test_ambiguous_name_rejected(second_position):
    driver, loop, _, _ = decision(
        "talk_to",
        "赵铁柱",
        positions={"chenmo": (10, 10), "villager_01": (11, 10), "villager_02": second_position},
        names={"chenmo": "陈默", "villager_01": "赵铁柱", "villager_02": "赵铁柱"},
    )
    with capture_logs() as logs:
        await driver.decide_once(loop.state, 0)
    assert not driver._pending
    assert any(
        row.get("event") == "chenmo.gate_rejected" and row["reason"] == "unknown_target"
        for row in logs
    )


async def test_machine_id_never_leaks_into_prompt():
    driver, loop, _, llm = decision("wait")
    assert await driver.decide_once(loop.state, 0, landmarks_text="药铺就在这条街上。")
    messages = llm.prompts[0]
    assert "你认得这些人：赵铁柱" in messages[1]["content"]
    assert "药铺就在这条街上。" in messages[1]["content"]
    assert not re.search(r"villager_\d+", json.dumps(messages, ensure_ascii=False))


async def test_candidate_people_are_nearest_twelve_by_manhattan_distance():
    labels = (
        "路人一",
        "路人二",
        "路人三",
        "路人四",
        "路人五",
        "路人六",
        "路人七",
        "路人八",
        "路人九",
        "路人十",
        "路人十一",
        "路人十二",
        "路人十三",
    )
    positions = {"chenmo": (10, 10), "villager_99": (18, 18)}
    names = {"chenmo": "陈默", "villager_99": "远处的人"}
    for number, name in enumerate(labels, 1):
        actor_id = f"villager_{number:02}"
        positions[actor_id] = (10 + number % 5, 10 + number // 5)
        names[actor_id] = name
    driver, loop, _, llm = decision("wait", positions=positions, names=names)
    await driver.decide_once(loop.state, 0)
    body = llm.prompts[0][1]["content"]
    assert (
        "你认得这些人：路人一、路人五、路人二、路人六、路人十、路人三、路人七、"
        "路人十一、路人四、路人八、路人十二、路人九" in body
    )
    assert "路人十三" not in body
    assert "远处的人" not in body
    assert not re.search(r"villager_\d+", body)


@pytest.mark.parametrize("action", ["buy", "sell"])
@pytest.mark.parametrize(
    "name, good_id",
    [
        ("草药", "herb"),
        ("药膏", "salve"),
        ("饭食", "meal"),
        ("米酒", "wine"),
    ],
)
async def test_all_chinese_goods_resolve_for_buy_and_sell(action, name, good_id):
    driver, loop, ledger, _ = decision(action, name)
    await driver.decide_once(loop.state, 0)
    assert len(driver._pending) == 1 and driver._pending[0].target_id == good_id
    assert driver.execute_pending(loop, pathfinder=None) == 1
    events = loop.drain_events()
    grants = [event for event in events if event.event_type == "coin.grant"]
    assert len(grants) == 1
    assert (cast(int, grants[0].payload["delta"]) < 0) == (action == "buy")
    assert ledger.balance_of("chenmo") != 100
    assert any(
        event.event_type == "npc.monologue" and name in event.payload["content"] for event in events
    )


async def test_known_name_outside_manhattan_range_is_not_resolved():
    driver, loop, _, _ = decision(
        "talk_to", "赵铁柱", positions={"chenmo": (10, 10), "villager_01": (18, 18)}
    )
    with capture_logs() as logs:
        await driver.decide_once(loop.state, 0)
    assert not driver._pending
    assert any(
        row.get("event") == "chenmo.gate_rejected" and row["reason"] == "unknown_target"
        for row in logs
    )


async def test_named_target_moving_out_of_execution_range_is_revalidated():
    driver, loop, _, _ = decision("talk_to", "赵铁柱")
    await driver.decide_once(loop.state, 0)
    target = loop.state.entities["villager_01"].model_copy(update={"pos": (23, 10)})
    loop.state = loop.state.model_copy(
        update={
            "entities": {**loop.state.entities, "villager_01": target},
        }
    )
    with capture_logs() as logs:
        assert driver.execute_pending(loop, pathfinder=None) == 0
    assert loop.drain_events() == []
    assert any(
        row.get("event") == "chenmo.revalidate_rejected" and row["reason"] == "target_out_of_range"
        for row in logs
    )


async def test_named_target_disappearing_before_execution_stays_rejected():
    driver, loop, _, _ = decision("talk_to", "赵铁柱")
    await driver.decide_once(loop.state, 0)
    loop.state = loop.state.model_copy(
        update={"entities": {"chenmo": loop.state.entities["chenmo"]}}
    )
    with capture_logs() as logs:
        assert driver.execute_pending(loop, pathfinder=None) == 0
    assert loop.drain_events() == []
    assert any(
        row.get("event") == "chenmo.revalidate_rejected" and row["reason"] == "target_gone"
        for row in logs
    )


async def test_internal_actor_id_without_display_name_never_enters_dialogue_prompt():
    driver, loop, _, llm = decision("talk_to", "villager_01", names={})
    await driver.decide_once(loop.state, 0)
    assert len(driver._pending) == 1
    assert not re.search(r"villager_\d+", json.dumps(llm.prompts, ensure_ascii=False))
    assert driver.execute_pending(loop, pathfinder=None) == 1


async def test_candidates_change_only_variable_prompt_message():
    driver, loop, _, llm = decision("wait")
    await driver.decide_once(loop.state, 0)
    loop.state = loop.state.model_copy(
        update={"entities": {"chenmo": loop.state.entities["chenmo"]}}
    )
    await driver.decide_once(loop.state, 1)
    assert llm.prompts[0][0] == llm.prompts[1][0]
    assert "你认得这些人：赵铁柱" in llm.prompts[0][1]["content"]
    assert "你认得这些人" not in llm.prompts[1][1]["content"]


async def test_trade_catalog_change_before_execution_is_structurally_rejected(monkeypatch):
    from sim.world import economy

    driver, loop, ledger, _ = decision("buy", "草药")
    await driver.decide_once(loop.state, 0)
    assert len(driver._pending) == 1
    monkeypatch.setattr(
        economy,
        "_GOOD_INDEX",
        {key: good for key, good in economy._GOOD_INDEX.items() if key != "herb"},
    )
    with capture_logs() as logs:
        assert driver.execute_pending(loop, pathfinder=None) == 0
    assert ledger.balance_of("chenmo") == 100
    assert loop.drain_events() == []
    assert any(
        row.get("event") == "chenmo.trade_rejected" and row["reason"] == "unknown_good"
        for row in logs
    )


async def test_same_name_as_observer_is_ambiguous_and_not_offered():
    driver, loop, _, llm = decision(
        "talk_to", "陈默", names={"chenmo": "陈默", "villager_01": "陈默"}
    )
    with capture_logs() as logs:
        await driver.decide_once(loop.state, 0)
    assert not driver._pending
    assert "你认得这些人" not in llm.prompts[0][1]["content"]
    assert any(
        row.get("event") == "chenmo.gate_rejected" and row["reason"] == "unknown_target"
        for row in logs
    )


async def test_people_candidates_exclude_animals_and_internal_identifier_labels():
    driver, loop, _, llm = decision(
        "wait",
        positions={
            "chenmo": (10, 10),
            "cat_grey": (10, 10),
            "villager_01": (11, 10),
            "villager_02": (10, 11),
        },
        names={
            "chenmo": "陈默",
            "cat_grey": "灰猫",
            "villager_01": "赵铁柱",
            "villager_02": "villager_99",
        },
    )
    await driver.decide_once(loop.state, 0)
    body = llm.prompts[0][1]["content"]
    assert "你认得这些人：赵铁柱。" in body
    assert "灰猫" not in body
    assert not re.search(r"villager_\d+", body)


async def test_ambiguous_good_name_rejected_without_losing_id_compatibility(monkeypatch):
    from sim.world import economy

    monkeypatch.setattr(
        economy,
        "_GOOD_INDEX",
        {
            "herb": economy.Good("herb", "草药", 12),
            "salve": economy.Good("salve", "草药", 30),
        },
    )
    driver, loop, _, _ = decision("buy", "草药")
    with capture_logs() as logs:
        await driver.decide_once(loop.state, 0)
    assert not driver._pending
    assert any(
        row.get("event") == "chenmo.trade_rejected" and row["reason"] == "unknown_good"
        for row in logs
    )
    driver, loop, ledger, _ = decision("buy", "herb")
    await driver.decide_once(loop.state, 0)
    assert driver.execute_pending(loop, pathfinder=None) == 1
    assert ledger.balance_of("chenmo") < 100
