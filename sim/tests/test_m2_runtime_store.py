"""M2-D2 数据层测试 — LOD 事件持久化投影 + runtime 数据访问层。

覆盖（m2-npc-cognition §1.2/§1.3/§4.1）：
- NpcStore.materialize：50 NPC 批量物化（L0→L1）一次查询、子集、未知 id；
- NpcStore.flush_tick：NPC_LOD_CHANGE → npc_profiles.lod 投影 + 事件落库；
  MATTER_* → matter_state UPSERT（含 COLLAPSE→rubble）；
- 同事务：投影抛异常 → 事件整批回滚（无半写）；
- SqlEventStore.append(projection=...) 扩展缝：同事务 + seq 映射；
- 降格记忆压缩写回：writeback_downgrade_memory → MemoryWritePipeline(source=reason)，
  S1 隐藏属性直陈 → 拒写不落库；
- 回归：原 flush_events（无投影）行为不变。
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import (
    EventKind,
    matter_event,
    npc_act_event,
    npc_lod_change_event,
)
from sim.core.flush import flush_events
from sim.core.persistence.database import init_database
from sim.core.persistence.models import Event, MatterState, NpcProfile
from sim.core.persistence.npc_store import NpcStore, NpcStoreError
from sim.core.persistence.store import SqlEventStore
from sim.llm.memory_scan import REASON_HIDDEN_LEAK
from sim.npc.hidden import HiddenAttribute, HiddenProfile
from sim.npc.model import NpcProfileData


@pytest.fixture
async def engine():
    """内存 SQLite 库（Base.metadata.create_all，含 M2 表）。"""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def store(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return SqlEventStore(sf)


@pytest.fixture
async def session(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        yield s


def _profile(npc_id: str, **overrides) -> NpcProfile:
    base: dict = {
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
        "needs": json.dumps([{"name": "hunger", "value": 0.8, "weight": 1.0}]),
        "skills": json.dumps({"木工": 3}),
        "goals": json.dumps({"short": "找活", "long": "活下去"}),
        "inventory": json.dumps(["旧布包"]),
        "knowledge_boundary": json.dumps({"literacy": 0.5}),
        "lod": 1,
        "created_at_tick": 0,
        "updated_at_tick": 10,
    }
    base.update(overrides)
    return NpcProfile(**base)


# ---------------------------------------------------------------------------
# 1. 批量物化（L0→L1）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestMaterialize:
    async def test_materialize_fifty_npcs(self, store, session: AsyncSession) -> None:
        session.add_all([_profile(f"npc-{i:02d}") for i in range(50)])
        await session.commit()
        ns = NpcStore(store)

        profiles = await ns.materialize()

        assert len(profiles) == 50
        assert all(isinstance(p, NpcProfileData) for p in profiles.values())
        chen = profiles["npc-00"]
        assert chen.needs[0].name == "hunger"
        assert chen.skills == {"木工": 3}
        assert chen.ocean[4] == 75.0  # neuroticism
        assert chen.lod == 1

    async def test_materialize_subset_by_ids(self, store, session: AsyncSession) -> None:
        session.add_all([_profile(f"npc-{i:02d}") for i in range(5)])
        await session.commit()
        ns = NpcStore(store)

        profiles = await ns.materialize(["npc-01", "npc-03", "npc-missing"])

        assert set(profiles) == {"npc-01", "npc-03"}

    async def test_materialize_empty_subset_returns_empty(self, store) -> None:
        ns = NpcStore(store)
        assert await ns.materialize([]) == {}


# ---------------------------------------------------------------------------
# 2. tick 批次 flush + LOD/MATTER 投影（同事务）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestFlushLodProjection:
    async def test_lod_change_projects_to_profile_column(
        self, store, session: AsyncSession
    ) -> None:
        session.add(_profile("npc-00", lod=1))
        await session.commit()
        ns = NpcStore(store)

        await ns.flush_tick([npc_lod_change_event(5, "npc-00", 1, 2, "enter_range")])

        session.expire_all()
        row = await session.get(NpcProfile, "npc-00")
        assert row is not None
        assert row.lod == 2
        assert row.updated_at_tick == 5
        # 事件已落库（唯一写路径）
        events = (await session.execute(select(Event))).scalars().all()
        assert len(events) == 1
        assert events[0].event_type == EventKind.NPC_LOD_CHANGE.value
        assert json.loads(events[0].payload)["to_lod"] == 2

    async def test_lod_change_unknown_npc_rolls_back_events(
        self, store, session: AsyncSession
    ) -> None:
        ns = NpcStore(store)

        with pytest.raises(NpcStoreError, match="未知 NPC"):
            await ns.flush_tick([npc_lod_change_event(5, "ghost", 0, 1, "enter_range")])

        # 投影失败 → 事件同事务回滚（无半写）
        events = (await session.execute(select(Event))).scalars().all()
        assert events == []

    async def test_flush_empty_events_is_noop(self, store) -> None:
        ns = NpcStore(store)
        await ns.flush_tick([])  # 不抛

    async def test_non_m2_events_pass_through_without_projection(
        self, store, session: AsyncSession
    ) -> None:
        ns = NpcStore(store)
        await ns.flush_tick([npc_act_event(3, "npc-00", "move", target="market")])
        events = (await session.execute(select(Event))).scalars().all()
        assert len(events) == 1
        assert events[0].event_type == EventKind.NPC_ACT.value


@pytest.mark.t1
class TestFlushMatterProjection:
    async def test_matter_decay_creates_state(self, store, session: AsyncSession) -> None:
        ns = NpcStore(store)

        await ns.flush_tick([matter_event(7, EventKind.MATTER_DECAY, "wall-1", amount=-0.1)])

        row = await session.get(MatterState, ("main", "wall-1"))
        assert row is not None
        assert row.branch_id == "main"
        assert row.integrity == pytest.approx(1.0)
        assert row.is_rubble is False

    async def test_matter_damage_updates_integrity(self, store, session: AsyncSession) -> None:
        ns = NpcStore(store)
        await ns.flush_tick([matter_event(1, EventKind.MATTER_BUILD, "wall-1", durability=0.9)])
        await ns.flush_tick([matter_event(2, EventKind.MATTER_DAMAGE, "wall-1", durability=0.4)])

        row = await session.get(MatterState, ("main", "wall-1"))
        assert row is not None
        assert row.integrity == pytest.approx(0.4)
        assert row.is_rubble is False

    async def test_matter_collapse_sets_rubble_terminal(self, store, session: AsyncSession) -> None:
        ns = NpcStore(store)
        await ns.flush_tick([matter_event(1, EventKind.MATTER_BUILD, "wall-1", durability=0.3)])
        await ns.flush_tick([matter_event(2, EventKind.MATTER_COLLAPSE, "wall-1", durability=0.0)])

        row = await session.get(MatterState, ("main", "wall-1"))
        assert row is not None
        assert row.is_rubble is True
        assert row.integrity == 0.0


# ---------------------------------------------------------------------------
# 3. SqlEventStore.append(projection=...) 扩展缝
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestAppendProjectionHook:
    async def test_projection_runs_in_same_txn_and_commits(
        self, store, session: AsyncSession
    ) -> None:
        session.add(_profile("npc-00", lod=0))
        await session.commit()
        seen: dict[str, object] = {}

        async def project(sess: AsyncSession, seq_by_index: dict[int, int]) -> None:
            seen["seq"] = dict(seq_by_index)
            row = await sess.get(NpcProfile, "npc-00")
            assert row is not None
            row.lod = 2

        await store.append(
            "main",
            [
                {
                    "tick": 1,
                    "event_type": EventKind.NPC_LOD_CHANGE.value,
                    "payload": {
                        "npc_id": "npc-00",
                        "from_lod": 0,
                        "to_lod": 2,
                        "reason": "enter_range",
                    },
                }
            ],
            projection=project,
        )

        assert seen["seq"] == {0: 1}
        session.expire_all()
        row = await session.get(NpcProfile, "npc-00")
        assert row is not None
        assert row.lod == 2

    async def test_projection_exception_rolls_back_whole_batch(
        self, store, session: AsyncSession
    ) -> None:
        async def boom(sess: AsyncSession, seq_by_index: dict[int, int]) -> None:
            raise RuntimeError("projection failed")

        with pytest.raises(RuntimeError, match="projection failed"):
            await store.append(
                "main",
                [
                    {
                        "tick": 1,
                        "event_type": EventKind.NPC_ACT.value,
                        "payload": {"npc_id": "npc-00", "action": "rest"},
                    }
                ],
                projection=boom,
            )

        events = (await session.execute(select(Event))).scalars().all()
        assert events == []


# ---------------------------------------------------------------------------
# 4. 降格记忆压缩写回（L2→L1）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestDowngradeMemoryWriteback:
    async def test_writeback_uses_reason_source(self, store) -> None:
        ns = NpcStore(store)

        result = ns.writeback_downgrade_memory("npc-00", "他还在想刚才那笔没谈成的买卖。")

        assert result.accepted is True
        assert result.entry is not None
        assert result.entry.source == "reason"
        assert result.entry.npc_id == "npc-00"
        assert result.entry.event_seq is None  # 推理转述

    async def test_writeback_rejects_hidden_leak(self, store) -> None:
        ns = NpcStore(store)
        hidden = HiddenProfile(
            npc_id="npc-00",
            attributes=(
                HiddenAttribute(
                    id="h1",
                    category="trauma",
                    label="旧伤",
                    descriptors=("断过的肋骨",),
                    triggers=(),
                ),
            ),
        )

        result = ns.writeback_downgrade_memory(
            "npc-00",
            "他想起断过的肋骨，隐隐作痛。",
            hidden=hidden,
        )

        assert result.accepted is False
        assert result.action == "rejected"

    async def test_writeback_reject_returns_reason_and_hits(self, store) -> None:
        """M2-S2 评审 W2：拒写结果必须带结构化 reason + 命中词面（供观测/重规划）。"""
        ns = NpcStore(store)
        hidden = HiddenProfile(
            npc_id="npc-00",
            attributes=(
                HiddenAttribute(
                    id="h1",
                    category="trauma",
                    label="旧伤",
                    descriptors=("断过的肋骨",),
                    triggers=(),
                ),
            ),
        )

        result = ns.writeback_downgrade_memory(
            "npc-00",
            "他想起断过的肋骨，隐隐作痛。",
            hidden=hidden,
        )

        assert result.accepted is False
        assert result.reason == REASON_HIDDEN_LEAK
        assert result.hits == ("断过的肋骨",)

    async def test_writeback_triggered_attribute_allowed(self, store) -> None:
        """M2-S2 评审 W3：触发窗口内属性直陈 → 正常写回（防线不过严）。"""
        ns = NpcStore(store)
        hidden = HiddenProfile(
            npc_id="npc-00",
            attributes=(
                HiddenAttribute(
                    id="h1",
                    category="trauma",
                    label="旧伤",
                    descriptors=("断过的肋骨",),
                    triggers=("阴雨天",),
                ),
            ),
        )

        result = ns.writeback_downgrade_memory(
            "npc-00",
            "他想起断过的肋骨，隐隐作痛。",
            hidden=hidden,
            triggered=frozenset({"h1"}),
        )

        assert result.accepted is True
        assert result.entry is not None
        assert result.entry.content == "他想起断过的肋骨，隐隐作痛。"

    async def test_writeback_triggered_mixed_still_rejects_other(self, store) -> None:
        """M2-S2 评审 W3：触发 h1 放行其词面，未触发的 h2 混入仍拒写。"""
        ns = NpcStore(store)
        hidden = HiddenProfile(
            npc_id="npc-00",
            attributes=(
                HiddenAttribute(
                    id="h1",
                    category="trauma",
                    label="旧伤",
                    descriptors=("断过的肋骨",),
                    triggers=("阴雨天",),
                ),
                HiddenAttribute(
                    id="h2",
                    category="addiction",
                    label="酒瘾",
                    descriptors=("戒不掉的酒",),
                    triggers=(),
                ),
            ),
        )

        result = ns.writeback_downgrade_memory(
            "npc-00",
            "断过的肋骨还在疼，那戒不掉的酒也停了。",
            hidden=hidden,
            triggered=frozenset({"h1"}),
        )

        assert result.accepted is False
        assert result.reason == REASON_HIDDEN_LEAK
        assert result.hits == ("戒不掉的酒",)


# ---------------------------------------------------------------------------
# 5. 回归：无投影的 flush_events 行为不变
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestFlushEventsRegression:
    async def test_flush_events_without_projection(self, store, session: AsyncSession) -> None:
        await flush_events(store, [npc_act_event(1, "npc-00", "work")])
        events = (await session.execute(select(Event))).scalars().all()
        assert len(events) == 1
        assert events[0].event_type == EventKind.NPC_ACT.value
