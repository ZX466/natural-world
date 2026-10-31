"""健康档事件写入与人物执行的真实接缝回归；数据库均为测试夹具。"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from sim.core import events as ev
from sim.core.events import EventKind
from sim.core.persistence.models import Event, NpcHealth
from sim.core.persistence.npc_store import NpcStore, NpcStoreError
from sim.core.world import build_default_bus


def health_event(**overrides):
    values = dict(tick=1, npc_id="chenmo", category="old_injury", code="wrist", severity=0.4)
    values.update(overrides)
    return getattr(ev, "npc_health_changed_event")(**values)


async def seed_profiles(store):
    from sim.content.protagonist import seed_protagonist
    from sim.content.villagers import seed_villagers

    await seed_protagonist(store.session_factory)
    await seed_villagers(store.session_factory)


def test_default_bus_covers_all_enabled_event_kinds():
    assert set(EventKind) - set(build_default_bus()._handlers) <= {EventKind.SPEECH_SHIFT}


def test_health_payload_is_private_and_validated():
    payload_model = getattr(ev, "NpcHealthChangedPayload")
    event = health_event(hidden=True)
    assert event.event_type is list(EventKind)[-1]
    assert set(event.payload) <= {
        "npc_id",
        "category",
        "code",
        "severity",
        "active",
        "hidden",
        "notes",
    }
    for fields in (
        {"label": "旧伤"},
        {"descriptors": []},
        {"triggered": True},
        {"severity": float("nan")},
        {"severity": float("inf")},
        {"severity": -0.1},
        {"severity": 1.1},
        {"code": "不合法"},
        {"active": "true"},
        {"category": "guess"},
    ):
        with pytest.raises(ValidationError):
            payload_model.model_validate({**event.payload, **fields})


async def test_projection_upserts_in_one_branch_and_rolls_back_with_events(store, session):
    await seed_profiles(store)
    npc = NpcStore(store)
    await npc.flush_tick([health_event(), health_event(tick=2, severity=0.7, hidden=True)])
    rows = (await session.scalars(select(NpcHealth))).all()
    assert len(rows) == 1
    assert (rows[0].severity, rows[0].hidden, rows[0].created_at_tick) == (0.7, True, 1)
    assert json.loads(rows[0].descriptors)
    with pytest.raises(NpcStoreError):
        await npc.flush_tick([health_event(tick=3, severity=0.2), health_event(npc_id="missing")])
    session.expire_all()
    assert (await session.scalar(select(NpcHealth))).severity == 0.7
    assert len((await session.scalars(select(Event))).all()) == 2
    # 别的分支没有该人物：拒绝，不偷偷更新 main。
    with pytest.raises(NpcStoreError):
        await NpcStore(store, branch_id="other").flush_tick([health_event(severity=0.1)])
    session.expire_all()
    assert (await session.scalar(select(NpcHealth))).severity == 0.7


async def test_fork_preserves_hidden_attribute_id(store, session):
    from sim.core.persistence.fork import fork_from_anchor

    await seed_profiles(store)
    await store.append("main", [ev.world_create_event(1, 42, ("chenmo",)).to_store_dict()])
    row = NpcHealth(
        npc_id="chenmo",
        branch_id="main",
        category="trauma",
        label="心悸",
        hidden=True,
        descriptors='["心悸"]',
        trigger_conditions='["夜深了"]',
    )
    row.code = "night_fear"
    session.add(row)
    await session.commit()
    before = (await NpcStore(store).materialize_hidden())["chenmo"].profile

    async def preflush():
        pass

    await fork_from_anchor(
        store.session_factory,
        parent_branch_id="main",
        fork_seq=1,
        fork_tick=1,
        new_branch_id="child",
        preflush=preflush,
    )
    after = (await NpcStore(store, branch_id="child").materialize_hidden())["chenmo"].profile
    assert before.attributes[0].id == after.attributes[0].id
    assert before.attributes[0].id == "chenmo.health_night_fear"


def test_collapse_survivors_and_incapacitated_agent_get_health_but_dead_npc_does_not():
    from sim.agent.combat_exec import CombatLedger
    from sim.core.clock import GameClock
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState
    from sim.world.maintenance import collapse_injuries
    from sim.world.structure import StructurePhase, StructureSnapshot

    loop = TickLoop(clock=GameClock(), bus=build_default_bus(), state=WorldState(world_seed=42))
    loop.enqueue(ev.world_create_event(0, 42, ("chenmo", "survivor", "dead")))
    loop.drain_events()
    ledger = CombatLedger()
    ledger.apply_damage("chenmo", 95)
    ledger.apply_damage("dead", 95)
    structure = StructureSnapshot(
        structure_id="shed",
        tiles=((0, 0),),
        kind="shed",
        material="wood",
        phase=StructurePhase.ACTIVE,
        load_bearing=True,
        supported_by=(),
    )
    result = collapse_injuries(
        loop.state,
        [ev.structure_collapsed_event(2, structure_id="shed", cause="decay")],
        {"shed": structure},
        ledger,
    )
    health = [e for e in result if e.event_type.value == "npc.health.changed"]
    assert {e.payload["npc_id"] for e in health} == {"chenmo", "survivor"}
    assert all(0 < e.payload["severity"] <= 1 and not e.payload["hidden"] for e in health)


async def test_seed_health_is_idempotent_and_actual_narration_triggers(store, session):
    from sim.content import health
    from sim.npc.hidden import evaluate_triggers, hidden_leak_scan
    from sim.perception.frame import Channel, Observation, PerceptionFrame

    await seed_profiles(store)
    assert await health.seed_health(store.session_factory) == 6
    assert await health.seed_health(store.session_factory) == 0
    rows = (await session.scalars(select(NpcHealth))).all()
    assert sum(row.hidden for row in rows) == 4
    states = await NpcStore(store).materialize_hidden()
    for npc_id, state in states.items():
        calm = PerceptionFrame(observer=npc_id, tick=10).narrated()
        assert not evaluate_triggers(state.profile, calm)
        assert not hidden_leak_scan(calm, state.profile, frozenset())
        text = PerceptionFrame(
            observer=npc_id,
            tick=20,
            observations=(
                Observation(
                    channel=Channel.INTEROCEPTION,
                    subject=npc_id,
                    description="伤处疼得厉害。天色暗下来了。夜深了。",
                    strength=1.0,
                ),
            ),
        ).narrated()
        assert evaluate_triggers(state.profile, text)


def test_execution_bridge_keeps_hidden_emergence():
    from sim.api.main import _fallback_map
    from sim.content.villagers import build_roster
    from sim.core.world import WorldState
    from sim.npc.contract import HiddenState
    from sim.npc.hidden import HiddenAttribute, HiddenProfile
    from sim.npc.runtime import NpcRuntime
    from sim.npc.utility import UtilityModel
    from sim.npc.sim_exec import npc_events_for_tick
    from sim.world.pathfinding import Pathfinder

    npc_id = "villager_01"
    state = HiddenState(
        profile=HiddenProfile(
            npc_id=npc_id,
            attributes=(
                HiddenAttribute(
                    id=f"{npc_id}.health_shoulder",
                    category="old_injury",
                    label="肩伤",
                    descriptors=("肩伤",),
                    triggers=("疼得厉害",),
                ),
            ),
        ),
        triggered=frozenset(),
    )
    runtime = NpcRuntime(profiles={npc_id: build_roster()[0]}, utility=UtilityModel(n_npc=1))
    result = npc_events_for_tick(
        runtime,
        WorldState(world_seed=42),
        10,
        Pathfinder(_fallback_map()),
        seed=42,
        hidden_states={npc_id: state},
        context_of=lambda _: "伤处疼得厉害。",
    )
    emerge = [e for e in result if e.event_type is EventKind.NPC_HIDDEN_EMERGE]
    assert len(emerge) == 1
    assert emerge[0].payload["attr_ids"] == [f"{npc_id}.health_shoulder"]


async def test_combat_prompt_keeps_provider_perception():
    from sim.tests.test_m4c_llm_driver import TestChenmoDriver, _FakeLlm, _FakeProfile

    llm = _FakeLlm('{"action":"wait","reason":"先看清四周。"}')
    driver = TestChenmoDriver._driver(llm, profile=_FakeProfile())
    driver._perception_provider = lambda: "你看到：桥头有人招手。"
    driver._exchange = object()
    await driver.decide_once(TestChenmoDriver._loop_with_chenmo().state, 1)
    messages = str(llm.last_messages)
    assert "桥头有人招手" in messages
    assert "正在交手" in messages
