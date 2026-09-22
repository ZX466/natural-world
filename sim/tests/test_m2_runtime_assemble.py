"""M2-A2 第三批第 2 项：NpcRuntime 接 NpcStore + HiddenState 每 tick 重估。

契约（m2-npc-cognition §1.3 + l1-whitelist §3 + soak.py 阶段 2 注记）：
- assemble_runtime：async 物化（NpcStore.materialize + materialize_hidden）→
  NpcRuntime + {npc_id: HiddenState}（一次查询，禁逐 NPC）；
- HiddenState.evaluate 每 tick：runtime.tick 前按感知处境文本重估触发窗口
  （hidden.py §2）；无 profile → 恒等值零分支透传；
- tick(tick, context_of)：context_of(npc_id) -> str 缺省恒空（无感知输入时
  触发窗口照旧）；窗口随内存态传递，不落库（升格时随 HiddenState 传）；
- 落库端到端：runtime.tick 产出 NPC_ACT → flush_tick 落库（NPC_ACT 走
  validation 白名单；事件与投影同事务）。
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore
from sim.npc.assemble import assemble_runtime
from sim.npc.contract import HiddenState
from sim.npc.hidden import HiddenAttribute, HiddenProfile
from sim.npc.model import Need, NpcProfileData
from sim.npc.runtime import NpcRuntime
from sim.npc.utility import UtilityModel


def _profile_row(npc_id: str) -> dict:
    """npc_profiles 最小行（同 test_m2_runtime_store 夹具口径）。"""
    return {
        "id": npc_id,
        "branch_id": "main",
        "name": f"NPC-{npc_id}",
        "species": "human",
        "gender": "female",
        "age": 30,
        "occupation": "零工",
        "identity_anchor": "我叫陈默。",
        "ocean_openness": 45,
        "ocean_conscientiousness": 55,
        "ocean_extraversion": 40,
        "ocean_agreeableness": 60,
        "ocean_neuroticism": 75,
        "pad_pleasure": -0.2,
        "pad_arousal": 0.1,
        "pad_dominance": -0.3,
        "emotion_updated_tick": 10,
        "needs": json.dumps(
            [
                {"name": "hunger", "value": 0.8, "weight": 1.0},
                {"name": "energy", "value": 0.4, "weight": 0.8},
                {"name": "social", "value": 0.3, "weight": 0.6},
            ]
        ),
        "skills": json.dumps({"木工": 3}),
        "lod": 1,
    }


def _health_row(npc_id: str, *, trigger: str) -> dict:
    return {
        "npc_id": npc_id,
        "branch_id": "main",
        "category": "old_injury",
        "label": "旧伤",
        "severity": 0.5,
        "active": True,
        "hidden": True,
        "descriptors": json.dumps(["旧伤"]),
        "trigger_conditions": json.dumps([trigger]),
        "notes": None,
        "created_at_tick": 0,
    }


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        yield s


async def _seed(session, profiles: list[dict], health: list[dict]) -> None:
    from sim.core.persistence.models import NpcHealth, NpcProfile

    for p in profiles:
        session.add(NpcProfile(**p))
    for h in health:
        session.add(NpcHealth(**h))
    await session.commit()


class TestAssembleRuntime:
    async def test_assembles_profiles_and_hidden(self, session) -> None:
        await _seed(
            session,
            [_profile_row("npc:01"), _profile_row("npc:02")],
            [_health_row("npc:01", trigger="雨")],
        )
        store = NpcStore(SqlEventStore(
            async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        ))
        runtime, hidden = await assemble_runtime(store)
        assert isinstance(runtime, NpcRuntime)
        assert set(runtime.profiles) == {"npc:01", "npc:02"}
        assert isinstance(hidden["npc:01"], HiddenState)
        assert hidden["npc:01"].profile is not None
        # npc:02 无隐藏行 → 恒等值（零分支透传）
        assert hidden["npc:02"] == HiddenState.empty()

    async def test_profile_fields_survive_roundtrip(self, session) -> None:
        await _seed(session, [_profile_row("npc:01")], [])
        store = NpcStore(SqlEventStore(
            async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        ))
        runtime, _ = await assemble_runtime(store)
        p = runtime.profiles["npc:01"]
        assert isinstance(p, NpcProfileData)
        assert p.name == "NPC-npc:01"
        assert p.ocean == (45.0, 55.0, 40.0, 60.0, 75.0)
        assert p.needs[0] == Need(name="hunger", value=0.8, weight=1.0)
        assert p.lod == 1


class TestHiddenEvalPerTick:
    """HiddenState.evaluate 每 tick 重估（runtime.tick 固定序第 0 步）。"""

    def _runtime(self) -> tuple[NpcRuntime, dict[str, HiddenState]]:
        from sim.npc.model import Need, NpcProfileData

        profile = HiddenProfile(
            npc_id="npc:01",
            attributes=(
                HiddenAttribute(
                    id="npc:01.health_1",
                    category="old_injury",
                    label="旧伤",
                    descriptors=("旧伤",),
                    triggers=("阴雨", "变天"),
                ),
            ),
        )
        p = NpcProfileData(
            npc_id="npc:01",
            name="甲",
            needs=(Need(name="hunger", value=0.5, weight=1.0),),
        )
        runtime = NpcRuntime(profiles={"npc:01": p}, utility=UtilityModel(n_npc=1))
        hidden = {"npc:01": HiddenState(profile=profile, triggered=frozenset())}
        return runtime, hidden

    def test_tick_without_context_keeps_window_empty(self) -> None:
        runtime, hidden = self._runtime()
        runtime.tick(1, hidden_states=hidden)
        assert hidden["npc:01"].triggered == frozenset()

    def test_tick_context_triggers_window(self) -> None:
        runtime, hidden = self._runtime()
        runtime.tick(
            1,
            hidden_states=hidden,
            context_of=lambda nid: "阴雨绵绵，浑身发沉。" if nid == "npc:01" else "",
        )
        assert "npc:01.health_1" in hidden["npc:01"].triggered

    def test_empty_state_zero_branch(self) -> None:
        """无隐藏档 NPC：evaluate 恒等透传，tick 不炸。"""
        p = NpcProfileData(
            npc_id="npc:02",
            name="乙",
            needs=(Need(name="hunger", value=0.5, weight=1.0),),
        )
        runtime = NpcRuntime(profiles={"npc:02": p}, utility=UtilityModel(n_npc=1))
        hidden = {"npc:02": HiddenState.empty()}
        runtime.tick(1, hidden_states=hidden, context_of=lambda _nid: "阴雨")
        assert hidden["npc:02"] == HiddenState.empty()

    def test_replay_same_context_same_window(self) -> None:
        """C5：同输入两次重估窗口一致（evaluate 纯函数）。"""
        r1, h1 = self._runtime()
        r2, h2 = self._runtime()
        ctx = lambda nid: "阴雨"  # noqa: E731
        r1.tick(1, hidden_states=h1, context_of=ctx)
        r2.tick(2, hidden_states=h2, context_of=ctx)
        assert h1["npc:01"].triggered == h2["npc:01"].triggered


class TestFlushEndToEnd:
    """runtime.tick 产出 NPC_ACT → flush_tick 落库（validation 白名单拦非法动作）。"""

    async def test_npc_act_enqueued_and_flushed(self, session) -> None:
        await _seed(session, [_profile_row("npc:01")], [])
        sf = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        store = NpcStore(SqlEventStore(sf))
        runtime, hidden = await assemble_runtime(store)
        events = runtime.tick(1, hidden_states=hidden)
        assert events, "hunger 0.8 → 必产出 eat/wander 等动作事件"
        # 落库不炸（NPC_ACT 过 validation 白名单）
        await store.flush_tick(events)

    async def test_npc_act_payload_whitelisted(self, session) -> None:
        await _seed(session, [_profile_row("npc:01")], [])
        sf = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        store = NpcStore(SqlEventStore(sf))
        runtime, hidden = await assemble_runtime(store)
        events = runtime.tick(1, hidden_states=hidden)
        from sim.npc.actions import ACTION_PAYLOAD_KEYS, ACTION_WHITELIST

        for ev in events:
            assert ev.payload["action"] in ACTION_WHITELIST
            allowed = ACTION_PAYLOAD_KEYS[ev.payload["action"]]
            # payload 形状（NpcActPayload）：{npc_id, action, target, params}
            assert set(ev.payload) <= {"npc_id", "action", "target", "params"}
            assert set(ev.payload.get("params", {})) <= allowed
