"""Async L2 work cannot hold the world lock or survive a range/branch change."""

import asyncio
import json
from dataclasses import replace

import pytest

from sim.agent.npc_l2 import L2Policy, NpcL2Service
from sim.core.events import npc_chat_event, npc_monologue_event
from sim.core.world import EntityState, WorldState
from sim.llm.client import ProfileSnapshot
from sim.npc.contract import HiddenState
from sim.npc.model import NpcProfileData
from sim.npc.runtime import NpcRuntime
from sim.npc.utility import UtilityModel
from sim.tests.test_m4c_llm_driver import _fake_result


class FakeLlm:
    def __init__(self, *, blocked=False):
        self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        if not blocked:
            self.release.set()

    async def complete(self, *args, **kwargs):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return _fake_result(
            json.dumps(
                {
                    "action": "request_chat",
                    "thought": "该把旧事说清楚。",
                    "line": "陈默，今儿可还顺当？",
                }
            )
        )


def setup(*, blocked=False, active=True, budget=4, hidden=None):
    from sim.agent.npc_l2_runtime import NpcL2Coordinator

    llm = FakeLlm(blocked=blocked)
    active_profile = ProfileSnapshot("fake", "http://invalid.local", "fake", 0, 192, "fixture")

    def provider():
        return active_profile if active else None

    profile = NpcProfileData(
        npc_id="villager_01", name="阿青", lod=2, identity_anchor="我是阿青，在河边做活。"
    )
    runtimes = [NpcRuntime({profile.npc_id: profile}, UtilityModel(1))]
    states = [
        WorldState(
            tick=10,
            entities={
                "chenmo": EntityState(entity_id="chenmo", pos=(0, 0)),
                "villager_01": EntityState(entity_id="villager_01", pos=(1, 0)),
            },
        )
    ]
    revision = [0]
    lock = asyncio.Lock()
    service = NpcL2Service(
        llm=llm,
        profile_provider=provider,
        policy=L2Policy(min_interval_seconds=0, max_calls_per_minute=budget, timeout_seconds=1),
        clock=lambda: 0,
    )
    coordinator = NpcL2Coordinator(
        service=service,
        profile_provider=provider,
        runtime=lambda: runtimes[0],
        state=lambda: states[0],
        revision=lambda: revision[0],
        is_live=lambda: True,
        context_of=lambda _: "河风轻轻吹着，陈默就在眼前。",
        hidden_of=lambda _: hidden[0] if hidden is not None else HiddenState.empty(),
        memory_of=lambda _: (),
        names={"chenmo": "陈默", "villager_01": "阿青"},
        write_lock=lock,
    )
    return coordinator, llm, states, runtimes, revision, lock


async def test_async_result_is_ready_only_for_current_nearby_l2():
    coordinator, llm, *_ = setup()
    await coordinator.step()
    ready = coordinator.take_ready()
    assert llm.calls == 1
    assert ready["villager_01"].line == "陈默，今儿可还顺当？"
    assert ready["villager_01"].listener_id == "chenmo"
    assert coordinator.take_ready() == {}


@pytest.mark.parametrize("change", ["range", "revision", "runtime", "death", "episode", "identity"])
async def test_delayed_result_is_discarded_after_world_changes(change):
    coordinator, llm, states, runtimes, revision, lock = setup(blocked=True)
    task = asyncio.create_task(coordinator.step())
    await asyncio.wait_for(llm.entered.wait(), timeout=1)
    # The actual call is suspended, but the simulation writer remains available.
    assert not lock.locked()
    async with lock:
        if change == "revision":
            revision[0] += 1
        elif change == "runtime":
            runtimes[0] = NpcRuntime(dict(runtimes[0].profiles), UtilityModel(1))
        elif change == "episode":
            runtimes[0].update_lod("villager_01", in_interaction=False, tick=10, allow_l2=False)
            runtimes[0].update_lod("villager_01", in_interaction=True, tick=20)
        elif change == "identity":
            runtimes[0].profiles["villager_01"] = replace(
                runtimes[0].profiles["villager_01"], identity_anchor="我如今另有打算。"
            )
        else:
            entities = dict(states[0].entities)
            if change == "death":
                del entities["villager_01"]
            else:
                entities["villager_01"] = entities["villager_01"].model_copy(update={"pos": (8, 0)})
            states[0] = states[0].model_copy(update={"entities": entities})
    llm.release.set()
    await task
    assert coordinator.take_ready() == {}


async def test_missing_active_profile_and_downgraded_npc_do_not_call_model():
    coordinator, llm, *_ = setup(active=False)
    await coordinator.step()
    assert llm.calls == 0
    assert not coordinator.available
    coordinator, llm, _, runtimes, *_ = setup()
    runtimes[0].profiles["villager_01"] = replace(runtimes[0].profiles["villager_01"], lod=1)
    await coordinator.step()
    assert llm.calls == 0


async def test_downgrade_summary_contains_accepted_conclusions_and_is_consumed_once():
    coordinator, _, *_ = setup()
    await coordinator.step()
    ready = coordinator.take_ready()
    events = [
        npc_monologue_event(10, "villager_01", "thought", "该把旧事说清楚。"),
        npc_chat_event(10, "villager_01", "chenmo", "陈默，今儿可还顺当？"),
    ]
    coordinator.record(ready, events)
    summary = coordinator.take_summary("villager_01")
    assert summary is not None
    assert "该把旧事说清楚" in summary
    assert "陈默，今儿可还顺当" in summary
    assert coordinator.take_summary("villager_01") is None


async def test_reset_discards_old_work_without_resetting_the_global_model_budget():
    coordinator, llm, *_ = setup(budget=1)
    await coordinator.step()
    coordinator.reset()
    assert coordinator.take_ready() == {}
    await coordinator.step()
    assert llm.calls == 1
    assert coordinator.take_ready() == {}


async def test_a_pending_dialogue_cannot_change_its_recipient():
    coordinator, _, states, *_ = setup()
    await coordinator.step()
    entities = dict(states[0].entities)
    entities["other"] = EntityState(entity_id="other", pos=(1, 0))
    states[0] = states[0].model_copy(update={"entities": entities})
    assert coordinator.take_ready() == {}


async def test_committed_incoming_speech_extends_the_dialogue_grace_period():
    coordinator, _, _, runtimes, *_ = setup()
    runtime = runtimes[0]
    runtime.update_lod("villager_01", in_interaction=False, tick=10)
    coordinator.observe([npc_chat_event(20, "chenmo", "villager_01", "回头再聊。")])
    runtime.update_lod("villager_01", in_interaction=False, tick=49)
    assert runtime.profiles["villager_01"].lod == 2
    runtime.update_lod("villager_01", in_interaction=False, tick=50)
    assert runtime.profiles["villager_01"].lod == 1


async def test_ready_conclusion_is_rechecked_against_the_current_hidden_window():
    from sim.npc.hidden import HiddenAttribute, HiddenProfile

    hidden = [HiddenState.empty()]
    coordinator, _, *_ = setup(hidden=hidden)
    await coordinator.step()
    hidden[0] = HiddenState(
        HiddenProfile(
            npc_id="villager_01",
            attributes=(
                HiddenAttribute(
                    id="villager_01.h",
                    category="trauma",
                    label="旧事",
                    descriptors=("旧事",),
                    triggers=("下雨了",),
                ),
            ),
        ),
        frozenset(),
    )
    assert coordinator.take_ready() == {}
