"""波 E：主角动作即时结算、上轮真实结果和无效移动边界。"""

import asyncio
from typing import Any, cast

import pytest

from sim.agent.driver import ChenmoDriver
from sim.agent.intent import Intent, IntentAction
from sim.agent.self_needs import ProtagonistNeeds
from sim.content.protagonist import PHARMACY_POS, build_anchor
from sim.core.clock import GameClock
from sim.core.events import EventKind, WorldEvent, npc_monologue_event
from sim.core.persistence.event_validation import validate_store_row
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.llm.client import LlmClient, ProfileSnapshot
from sim.npc.contract import HiddenState
from sim.npc.hidden import HiddenAttribute, HiddenProfile
from sim.npc.model import Need
from sim.npc.needs import advance_needs, apply_remedy
from sim.npc.sim_exec import _SITE_ARRIVAL_RADIUS, _WAGE_AMOUNT, _wage_cooldown_ticks
from sim.tests.test_m4c_llm_driver import _FakeLlm, _FakeProfile
from sim.world.economy import CoinLedger, buy_price
from sim.world.map import Chunk, TileMap
from sim.world.pathfinding import Pathfinder

pytestmark = pytest.mark.t1

_REASON = "先把眼前的事做好。"


def _loop(*, pos: tuple[int, int] = PHARMACY_POS, tick: int = 0, seed: int = 42) -> TickLoop:
    return TickLoop(
        clock=GameClock(speed=1),
        bus=build_default_bus(),
        state=WorldState(
            tick=tick,
            world_seed=seed,
            entities={
                "chenmo": EntityState(entity_id="chenmo", pos=pos),
                "villager_01": EntityState(entity_id="villager_01", pos=(pos[0] + 4, pos[1])),
            },
        ),
    )


def _driver(
    *, ledger: CoinLedger | None = None, seed: int = 42, profile: bool = True, **kwargs: Any
) -> tuple[ChenmoDriver, _FakeLlm]:
    llm = _FakeLlm('{"action":"wait","reason":"在这里歇会儿。","confidence":0.9}')
    if ledger is not None:
        kwargs["economy_provider"] = lambda: (ledger, seed)
    return (
        ChenmoDriver(
            anchor=build_anchor(),
            llm=cast("LlmClient", llm),
            profile_provider=lambda: cast("ProfileSnapshot", _FakeProfile()) if profile else None,
            **kwargs,
        ),
        llm,
    )


def _execute(
    driver: ChenmoDriver, loop: TickLoop, action: IntentAction, **kwargs: Any
) -> list[WorldEvent]:
    driver._pending.append(Intent(action=action, reason=_REASON, **kwargs))
    assert driver.execute_pending(loop, pathfinder=None) == 1
    events = loop.drain_events()
    for event in events:
        validate_store_row(event.to_store_dict())
    return events


def _thoughts(events: list[WorldEvent]) -> list[str]:
    return [
        str(event.payload["content"])
        for event in events
        if event.event_type is EventKind.NPC_MONOLOGUE
        and event.payload["npc_id"] == "chenmo"
        and event.payload["form"] == "thought"
    ]


def _grants(events: list[WorldEvent]) -> list[WorldEvent]:
    return [event for event in events if event.event_type is EventKind.COIN_GRANT]


def test_work_emits_pose_wage_and_one_result_instead_of_reason() -> None:
    ledger = CoinLedger()
    driver, _ = _driver(ledger=ledger)
    loop = _loop()

    events = _execute(driver, loop, "work")

    acts = [event for event in events if event.event_type is EventKind.NPC_ACT]
    assert len(acts) == 1
    assert acts[0].payload == {"npc_id": "chenmo", "action": "work", "target": "", "params": {}}
    assert [(event.payload["delta"], event.payload["note"]) for event in _grants(events)] == [
        (_WAGE_AMOUNT, "wage:work")
    ]
    assert ledger.balance_of("chenmo") == _WAGE_AMOUNT
    assert len(_thoughts(events)) == 1
    assert _thoughts(events)[0] != _REASON
    assert driver.last_intent_result == _thoughts(events)[0]
    assert not any(event.event_type is EventKind.MOVE for event in events)


@pytest.mark.parametrize(
    ("offset", "paid"),
    [
        ((4, 0), True),
        ((-4, 0), True),
        ((0, 4), True),
        ((0, -4), True),
        ((2, 2), True),
        ((5, 0), False),
        ((3, 2), False),
    ],
)
def test_work_uses_pharmacy_manhattan_arrival_boundary(offset: tuple[int, int], paid: bool) -> None:
    assert _SITE_ARRIVAL_RADIUS == 4
    ledger = CoinLedger()
    wage_last: dict[str, int] = {}
    driver, _ = _driver(ledger=ledger, wage_last=wage_last)
    loop = _loop(pos=(PHARMACY_POS[0] + offset[0], PHARMACY_POS[1] + offset[1]), tick=12)

    events = _execute(driver, loop, "work")

    assert len(_grants(events)) == int(paid)
    assert ledger.balance_of("chenmo") == (_WAGE_AMOUNT if paid else 0)
    assert wage_last == ({"chenmo": 12} if paid else {})
    assert len(_thoughts(events)) == 1
    if not paid:
        assert "这儿没活可干" in _thoughts(events)[0]


@pytest.mark.parametrize(("offset", "paid"), [(-1, False), (0, True), (1, True)])
def test_work_cooldown_boundary_reads_shared_ledger(offset: int, paid: bool) -> None:
    ledger = CoinLedger()
    wage_last = {"chenmo": 100, "villager_01": 90}
    driver, _ = _driver(ledger=ledger, wage_last=wage_last)
    tick = 100 + _wage_cooldown_ticks("chenmo") + offset

    events = _execute(driver, _loop(tick=tick), "work")

    assert len(_grants(events)) == int(paid)
    assert wage_last == {"chenmo": tick if paid else 100, "villager_01": 90}
    assert ledger.balance_of("chenmo") == (_WAGE_AMOUNT if paid else 0)


def test_work_shared_dict_blocks_two_drivers_and_can_be_cleared_for_reload() -> None:
    ledger = CoinLedger()
    wage_last: dict[str, int] = {}
    first, _ = _driver(ledger=ledger, wage_last=wage_last)
    second, _ = _driver(ledger=ledger, wage_last=wage_last)
    loop = _loop(tick=20)

    assert len(_grants(_execute(first, loop, "work"))) == 1
    assert len(_grants(_execute(second, loop, "work"))) == 0
    wage_last.clear()
    assert len(_grants(_execute(second, loop, "work"))) == 1
    assert ledger.balance_of("chenmo") == 2 * _WAGE_AMOUNT


def test_default_wage_cooldown_dict_is_private_and_blocks_repeated_intents() -> None:
    ledger = CoinLedger()
    first, _ = _driver(ledger=ledger)
    second, _ = _driver(ledger=ledger)
    loop = _loop()
    first._pending.extend([Intent(action="work", reason=_REASON)] * 2)

    assert first.execute_pending(loop, pathfinder=None) == 2
    assert len(_grants(loop.drain_events())) == 1
    assert len(_grants(_execute(second, loop, "work"))) == 1


def test_zero_balance_can_work_twice_then_eat_without_seed_funding() -> None:
    ledger = CoinLedger()
    needs = ProtagonistNeeds(0)
    initial = needs.needs
    driver, _ = _driver(ledger=ledger, seed=0, needs_provider=lambda: needs)
    loop = _loop(seed=0)
    assert ledger.balance_of("chenmo") == 0

    first = _execute(driver, loop, "work")
    loop.state = loop.state.model_copy(update={"tick": _wage_cooldown_ticks("chenmo")})
    second = _execute(driver, loop, "work")
    before = advance_needs(initial, ticks=loop.state.tick)
    price = buy_price("meal", tick=loop.state.tick, seed=0)
    eaten = _execute(driver, loop, "eat")

    assert sum(cast("int", event.payload["delta"]) for event in _grants(first + second)) == 10
    assert ledger.balance_of("chenmo") == 10 - price
    assert needs.needs == apply_remedy(before, "eat")
    assert all(event.payload["note"] != "genesis:household" for event in _grants(first + second))
    assert len(_thoughts(eaten)) == 1


@pytest.mark.parametrize(("tick", "seed"), [(17, 42), (32000, 0), (400001, 773)])
def test_eat_settles_live_price_and_applies_remedy_at_execution(tick: int, seed: int) -> None:
    initial = (Need(name="hunger", value=0.8, weight=1), Need(name="energy", value=0.7, weight=1))
    needs = ProtagonistNeeds(tick - 5, needs=initial)
    ledger = CoinLedger()
    ledger.apply_grant("chenmo", 50, tick=0)
    driver, _ = _driver(ledger=ledger, seed=seed, needs_provider=lambda: needs)
    loop = _loop(tick=tick, seed=seed)

    events = _execute(driver, loop, "eat")

    price = buy_price("meal", tick=tick, seed=seed)
    assert [(event.payload["delta"], event.payload["note"]) for event in _grants(events)] == [
        (-price, "buy:meal")
    ]
    assert ledger.balance_of("chenmo") == 50 - price
    assert needs.needs == apply_remedy(advance_needs(initial, ticks=5), "eat")
    assert len(_thoughts(events)) == 1
    assert _thoughts(events)[0] != _REASON
    assert any(
        event.event_type is EventKind.NPC_ACT and event.payload["action"] == "eat"
        for event in events
    )


def test_eat_insufficient_funds_never_deducts_or_remedies() -> None:
    tick = 37
    needs = ProtagonistNeeds(tick)
    original = needs.needs
    ledger = CoinLedger()
    price = buy_price("meal", tick=tick, seed=42)
    ledger.apply_grant("chenmo", price - 1, tick=0)
    driver, _ = _driver(ledger=ledger, needs_provider=lambda: needs)

    events = _execute(driver, _loop(tick=tick), "eat")

    assert not _grants(events)
    assert ledger.balance_of("chenmo") == price - 1
    assert needs.needs == original
    assert len(_thoughts(events)) == 1
    assert "凑不齐" in _thoughts(events)[0]
    assert driver.last_intent_result == _thoughts(events)[0]


def test_eat_repeated_in_same_batch_cannot_spend_the_same_coins_twice() -> None:
    needs = ProtagonistNeeds(0)
    before = needs.needs
    ledger = CoinLedger()
    price = buy_price("meal", tick=0, seed=42)
    ledger.apply_grant("chenmo", price, tick=0)
    driver, _ = _driver(ledger=ledger, needs_provider=lambda: needs)
    driver._pending.extend([Intent(action="eat", reason=_REASON)] * 2)
    loop = _loop()

    assert driver.execute_pending(loop, pathfinder=None) == 2

    events = loop.drain_events()
    assert len(_grants(events)) == 1
    assert ledger.balance_of("chenmo") == 0
    assert needs.needs == apply_remedy(before, "eat")
    assert len(_thoughts(events)) == 2
    assert "凑不齐" in _thoughts(events)[-1]
    assert driver.last_intent_result == _thoughts(events)[-1]


def test_rest_is_free_and_uses_current_projection_getter() -> None:
    old = ProtagonistNeeds(0)
    current = ProtagonistNeeds(90, needs=(Need(name="energy", value=0.9, weight=1),))
    projection = old
    driver, _ = _driver(needs_provider=lambda: projection)
    projection = current

    events = _execute(driver, _loop(tick=100), "rest")

    assert old.needs == ProtagonistNeeds(0).needs
    expected = apply_remedy(
        advance_needs((Need(name="energy", value=0.9, weight=1),), ticks=10), "rest"
    )
    assert current.needs == expected
    assert not _grants(events)
    assert len(_thoughts(events)) == 1
    assert _thoughts(events)[0] != _REASON
    assert any(
        event.event_type is EventKind.NPC_ACT and event.payload["action"] == "rest"
        for event in events
    )


@pytest.mark.parametrize("action", ["work", "eat", "rest"])
def test_activity_without_optional_providers_is_safe(action: IntentAction) -> None:
    driver, _ = _driver()
    events = _execute(driver, _loop(), action)
    assert any(event.event_type is EventKind.NPC_ACT for event in events)
    assert len(_thoughts(events)) == 1
    assert not _grants(events)


def test_eat_without_needs_projection_does_not_charge_for_missing_remedy() -> None:
    ledger = CoinLedger()
    ledger.apply_grant("chenmo", 20, tick=0)
    driver, _ = _driver(ledger=ledger)

    events = _execute(driver, _loop(), "eat")

    assert ledger.balance_of("chenmo") == 20
    assert not _grants(events)


def test_trade_result_raw_text_enters_the_next_plan_and_clear_removes_it() -> None:
    ledger = CoinLedger()
    driver, llm = _driver(ledger=ledger)
    loop = _loop(tick=5)
    events = _execute(driver, loop, "buy", target_id="herb")
    result = _thoughts(events)[0]
    assert result != _REASON
    assert driver.last_intent_result == result

    assert asyncio.run(driver.decide_once(loop.state, 6)) is True
    assert llm.last_messages is not None
    assert f"上次的结果：{result}" in llm.last_messages[1]["content"]
    assert _REASON not in llm.last_messages[1]["content"]

    driver.clear_last_result()
    assert driver.last_intent_result == ""
    assert asyncio.run(driver.decide_once(loop.state, 7)) is True
    assert llm.last_messages is not None
    assert result not in llm.last_messages[1]["content"]


def test_result_capture_only_uses_this_handler_own_thought(monkeypatch) -> None:
    ledger = CoinLedger()
    driver, _ = _driver(ledger=ledger)
    loop = _loop()
    loop.enqueue(npc_monologue_event(tick=0, npc_id="chenmo", form="thought", content="旧事。"))

    def trade(current_loop: TickLoop, intent: Intent) -> None:
        current_loop.enqueue(
            npc_monologue_event(tick=0, npc_id="chenmo", form="thought", content="这回没买成。")
        )
        current_loop.enqueue(
            npc_monologue_event(tick=0, npc_id="chenmo", form="bubble", content="劳驾。")
        )
        current_loop.enqueue(
            npc_monologue_event(tick=0, npc_id="villager_01", form="thought", content="他的事。")
        )

    monkeypatch.setattr(driver, "_issue_trade", trade)
    _execute(driver, loop, "buy", target_id="herb")
    assert driver.last_intent_result == "这回没买成。"


def test_handler_without_result_does_not_reuse_old_queued_thought() -> None:
    driver, _ = _driver()
    loop = _loop()
    _execute(driver, loop, "wait")
    assert driver.last_intent_result == _REASON
    loop.enqueue(npc_monologue_event(tick=0, npc_id="chenmo", form="thought", content="旧事。"))

    _execute(driver, loop, "buy", target_id="herb")

    assert driver.last_intent_result == ""


def test_previous_result_is_rechecked_when_hidden_window_expires() -> None:
    attr = HiddenAttribute(
        id="old", category="old_injury", label="旧伤", descriptors=("旧伤",), triggers=("阴雨",)
    )
    profile = HiddenProfile(npc_id="chenmo", attributes=(attr,))
    hidden = HiddenState(profile=profile, triggered=frozenset({"old"}))
    driver, llm = _driver(hidden_provider=lambda: hidden)
    loop = _loop()
    reason = "旧伤又隐隐作痛。"
    driver._pending.append(Intent(action="wait", reason=reason))
    assert driver.execute_pending(loop, pathfinder=None) == 1
    assert driver.last_intent_result == reason
    assert asyncio.run(driver.decide_once(loop.state, 1)) is True
    assert llm.last_messages is not None
    assert reason in llm.last_messages[1]["content"]

    hidden = HiddenState(profile=profile, triggered=frozenset())
    assert asyncio.run(driver.decide_once(loop.state, 2)) is True
    assert llm.last_messages is not None
    assert "旧伤" not in llm.last_messages[1]["content"]


def test_banned_handler_thought_is_dropped_instead_of_poisoning_every_later_round(
    monkeypatch,
) -> None:
    """结果文本是持久 prompt 状态：能过闸门、过不了装配器的句子必须挡在写入侧。"""
    ledger = CoinLedger()
    driver, llm = _driver(ledger=ledger)
    loop = _loop()

    def trade(current_loop: TickLoop, intent: Intent) -> None:
        current_loop.enqueue(
            npc_monologue_event(tick=0, npc_id="chenmo", form="thought", content="这里是游戏。")
        )

    monkeypatch.setattr(driver, "_issue_trade", trade)
    _execute(driver, loop, "buy", target_id="herb")

    assert driver.last_intent_result == ""
    assert asyncio.run(driver.decide_once(loop.state, 1)) is True
    assert llm.calls == 1
    assert llm.last_messages is not None
    assert "游戏" not in llm.last_messages[1]["content"]


def test_gate_exempted_reason_cannot_freeze_every_later_decision() -> None:
    """闸门的引用式豁免比装配器宽：同一句在闸门放行、在装配器必炸。

    reason 进入 [计划] 段后是持久状态——若不在此处筛掉，之后每一轮装配
    都失败、LLM 零调用，陈默永久静默（波 E 新引入）。
    """
    from sim.agent.gate import IntentGate

    driver, llm = _driver()
    loop = _loop()
    poison = "游戏？我不过是个学徒。"
    assert (
        IntentGate().validate(Intent(action="wait", reason=poison), loop.state, "chenmo").accepted
    )

    driver._pending.append(Intent(action="wait", reason=poison))
    assert driver.execute_pending(loop, pathfinder=None) == 1

    assert driver.last_intent_result == ""
    for round_no in range(1, 4):
        assert asyncio.run(driver.decide_once(loop.state, round_no)) is True
    assert llm.calls == 3
    assert llm.last_messages is not None
    assert "游戏" not in llm.last_messages[1]["content"]
    assert "上次的结果" not in llm.last_messages[1]["content"]


def test_no_profile_keeps_zero_calls_even_with_a_previous_result() -> None:
    driver, llm = _driver(profile=False)
    loop = _loop()
    _execute(driver, loop, "wait")
    assert asyncio.run(driver.decide_once(loop.state, 1)) is False
    assert llm.calls == 0
    assert not driver._pending


def _pathfinder() -> Pathfinder:
    return Pathfinder(
        TileMap(
            width=16,
            height=16,
            chunks={
                (0, 0): Chunk(cx=0, cy=0, ground=(1,) * 256, collision=(True,) * 256),
            },
        )
    )


@pytest.mark.parametrize("action", ["move_to", "investigate", "talk_to", "flee"])
@pytest.mark.parametrize("shape", ["empty", "singleton", "return_to_start"])
def test_all_moving_arms_suppress_no_op_paths_without_losing_thoughts_or_chat(
    action: IntentAction, shape: str, monkeypatch
) -> None:
    driver, _ = _driver()
    loop = _loop(pos=(3, 3))
    prior_path = ((3, 3), (3, 4))
    actor = loop.state.entities["chenmo"].model_copy(update={"path": prior_path})
    loop.state = loop.state.model_copy(
        update={"entities": {**loop.state.entities, "chenmo": actor}}
    )
    path = {"empty": (), "singleton": ((3, 3),), "return_to_start": ((3, 3), (3, 4), (3, 3))}[shape]
    monkeypatch.setattr(Pathfinder, "find", lambda self, start, goal: path)
    kwargs: dict[str, Any] = (
        {"target_id": "villager_01"} if action in ("talk_to", "flee") else {"target_pos": (7, 3)}
    )
    driver._pending.append(Intent(action=action, reason=_REASON, **kwargs))

    assert driver.execute_pending(loop, pathfinder=_pathfinder()) == 1

    events = loop.drain_events()
    assert not any(event.event_type is EventKind.MOVE for event in events)
    assert loop.state.entities["chenmo"].path == prior_path
    assert _thoughts(events) == [_REASON]
    if action == "talk_to":
        assert any(event.event_type is EventKind.NPC_CHAT for event in events)


@pytest.mark.parametrize("action", ["move_to", "investigate", "flee"])
def test_current_goal_is_skipped_before_pathfinding(action: IntentAction, monkeypatch) -> None:
    driver, _ = _driver()
    loop = _loop(pos=(0, 0))

    def unexpected_find(self, start, goal):
        pytest.fail("Already at the goal: pathfinding must not run")

    monkeypatch.setattr(Pathfinder, "find", unexpected_find)
    kwargs: dict[str, Any] = (
        {"target_id": "villager_01"} if action == "flee" else {"target_pos": (0, 0)}
    )
    if action == "flee":
        target = EntityState(entity_id="villager_01", pos=(1, 1))
        loop.state = loop.state.model_copy(
            update={"entities": {**loop.state.entities, "villager_01": target}}
        )
    driver._pending.append(Intent(action=action, reason=_REASON, **kwargs))

    assert driver.execute_pending(loop, pathfinder=_pathfinder()) == 1

    events = loop.drain_events()
    assert not any(event.event_type is EventKind.MOVE for event in events)
    assert _thoughts(events) == [_REASON]


@pytest.mark.parametrize("action", ["move_to", "investigate", "talk_to", "flee"])
def test_real_movement_remains_available(action: IntentAction) -> None:
    driver, _ = _driver()
    loop = _loop(pos=(3, 3))
    kwargs: dict[str, Any] = (
        {"target_id": "villager_01"} if action in ("talk_to", "flee") else {"target_pos": (7, 3)}
    )
    driver._pending.append(Intent(action=action, reason=_REASON, **kwargs))

    assert driver.execute_pending(loop, pathfinder=_pathfinder()) == 1

    moves = [event for event in loop.drain_events() if event.event_type is EventKind.MOVE]
    assert len(moves) == 1
    assert moves[0].payload["goal"] != moves[0].payload["start"]
