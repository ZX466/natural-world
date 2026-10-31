"""模型延迟期间的隐藏窗口、对白、回忆及记忆写入防线。"""

from __future__ import annotations

import json

from sim.npc.contract import HiddenState, advance_hidden_window, refresh_hidden_states
from sim.npc.hidden import HiddenAttribute, HiddenProfile
from sim.tests.test_m4c_llm_driver import TestChenmoDriver as _DriverFixture
from sim.tests.test_m4c_llm_driver import _FakeLlm, _FakeProfile


def hidden_state(*, triggered=False):
    attr = HiddenAttribute(
        id="chenmo.health_night_unease",
        category="trauma",
        label="入夜心悸",
        descriptors=("入夜心悸",),
        triggers=("夜深了",),
    )
    return HiddenState(
        HiddenProfile(npc_id="chenmo", attributes=(attr,)),
        frozenset({attr.id}) if triggered else frozenset(),
    )


async def test_closed_window_blocks_model_reason_and_filters_private_memories():
    llm = _FakeLlm(json.dumps({"action": "wait", "reason": "我有入夜心悸。"}, ensure_ascii=False))
    driver = _DriverFixture._driver(llm, profile=_FakeProfile())
    driver._hidden_provider = lambda: hidden_state()
    loop = _DriverFixture._loop_with_chenmo()
    assert await driver.decide_once(
        loop.state, 10, memory_entries=("我有入夜心悸。", "街上很安静。")
    )
    assert not driver._pending
    assert "入夜心悸" not in str(llm.last_messages)
    assert "街上很安静" in str(llm.last_messages)


async def test_window_is_rechecked_after_model_await_and_again_before_execution():
    window = hidden_state(triggered=True)

    class ClosingLlm(_FakeLlm):
        async def complete(self, *args, **kwargs):
            nonlocal window
            window = hidden_state()
            return await super().complete(*args, **kwargs)

    content = json.dumps({"action": "wait", "reason": "我有入夜心悸。"}, ensure_ascii=False)
    llm = ClosingLlm(content)
    driver = _DriverFixture._driver(llm, profile=_FakeProfile())
    driver._hidden_provider = lambda: window
    loop = _DriverFixture._loop_with_chenmo()
    await driver.decide_once(loop.state, 10)
    assert not driver._pending

    window = hidden_state(triggered=True)
    driver._llm = _FakeLlm(content)
    await driver.decide_once(loop.state, 20)
    assert driver._pending
    window = hidden_state()
    assert driver.execute_pending(loop, pathfinder=object()) == 0
    assert not driver._pending


def test_cached_dialogue_cannot_leak_private_attribute_at_execution():
    from sim.agent.intent import Intent
    from sim.core.world import EntityState

    driver = _DriverFixture._driver(_FakeLlm(), profile=_FakeProfile())
    driver._hidden_provider = lambda: hidden_state()
    loop = _DriverFixture._loop_with_chenmo()
    loop.state = loop.state.model_copy(
        update={
            "entities": {
                **loop.state.entities,
                "villager_01": EntityState(entity_id="villager_01", pos=(8, 16)),
            }
        }
    )
    intent = Intent(action="talk_to", target_id="villager_01", reason="问问近况。")
    driver._pending.append(intent)
    driver._chat_lines[id(intent)] = "我有入夜心悸。"
    assert driver.execute_pending(loop, pathfinder=object()) == 1
    events = loop.drain_events()
    assert any(e.event_type.value == "npc.chat" for e in events)
    assert all("入夜心悸" not in str(e.payload) for e in events)
    assert not driver._chat_lines


def test_observe_uses_hidden_guard_and_allows_current_trigger_window():
    from sim.agent.chenmo_memory import observe
    from sim.llm.memory_scan import MemoryWritePipeline

    pipeline = MemoryWritePipeline()
    assert not observe(
        pipeline, "我有入夜心悸。", tick=1, **hidden_state().memory_kwargs()
    ).accepted
    assert observe(
        pipeline, "我有入夜心悸。", tick=2, **hidden_state(triggered=True).memory_kwargs()
    ).accepted


def test_refresh_keeps_live_window_but_load_resets_it_and_removed_attributes_disappear():
    states = {"chenmo": hidden_state(triggered=True)}
    loaded = {"chenmo": hidden_state()}
    refresh_hidden_states(states, loaded)
    assert states["chenmo"].triggered
    refresh_hidden_states(states, loaded, reset=True)
    assert not states["chenmo"].triggered
    refresh_hidden_states(states, {})
    assert states == {}


def test_empty_profiles_do_not_narrate_and_emergence_emits_only_on_entry():
    def forbidden(_):
        raise AssertionError("空档不应调用 narrated")

    states = {"plain": HiddenState.empty()}
    assert advance_hidden_window("plain", states, tick=10, context_of=forbidden) is None
    states["chenmo"] = hidden_state()
    assert advance_hidden_window("chenmo", states, tick=20, context_of=lambda _: "夜深了")
    assert advance_hidden_window("chenmo", states, tick=30, context_of=lambda _: "夜深了") is None
    assert advance_hidden_window("chenmo", states, tick=40, context_of=lambda _: "日头正好") is None
    assert advance_hidden_window("chenmo", states, tick=50, context_of=lambda _: "夜深了")
