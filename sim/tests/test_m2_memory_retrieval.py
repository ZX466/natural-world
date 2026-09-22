"""M2-D3 记忆检索打分缝（读侧）测试 + codex MEDIUM 回归。

覆盖（m2-npc-cognition §3.1/§3.2）：
- 候选来自 iter_visible（S5 过滤被取代条目）；
- 基础分 = 重要性 × 近因（纯函数，不含偏差）；
- RetrieveFn 钩子可注入（mul/add），本模块**不写死偏差逻辑**；
- top_k + 同分按 entry.id 稳定排序（C5 确定性）；
- scores_of 规约为 memory_scores 形；
- 读侧 only：retrieve 不改 store、不触发任何写/扫描。

codex MEDIUM 回归（review §给 opencode）：
- ①SqlEventStore.append(validate=True) 拒绝夹带 payload / 伪造 witnesses
  （test_m2_runtime_store.py 已覆盖投影；此处补事件校验）；
- ②NpcStore.materialize_hidden() 装配 npc_health 隐藏行（升格缺半边补齐）。
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.event_validation import EventValidationError
from sim.core.persistence.models import Event, NpcHealth, NpcProfile
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore
from sim.llm.memory_scan import InMemoryStore, MemoryEntry, MemoryWritePipeline, make_entry
from sim.npc.memory import (
    MemoryHit,
    MemoryQuery,
    RetrievalScorers,
    Scorer,
    base_score,
    recency_factor,
    retrieve,
    scores_of,
)

# ---------------------------------------------------------------------------
# 夹具：写入侧造可见记忆
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


def _seed(store: InMemoryStore, npc_id: str, *, n: int = 3) -> list[MemoryEntry]:
    """经唯一入口 MemoryWritePipeline 写入 n 条干净的可见记忆。"""
    pipeline = MemoryWritePipeline(store)
    out: list[MemoryEntry] = []
    for i in range(n):
        result = pipeline.write(
            npc_id=npc_id,
            content=f"他记得第 {i} 件事。",
            source="reason",
            event_seq=i + 1,
            importance=0.5 + 0.1 * i,
            emotion_tag=None,
        )
        assert result.entry is not None
        out.append(result.entry)
    return out


# ---------------------------------------------------------------------------
# 1. 候选与基础分
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestRetrieveBasics:
    def test_candidates_from_iter_visible_only(self, store: InMemoryStore) -> None:
        entries = _seed(store, "npc-00", n=3)
        # S5：取代一条 → 检索面应少一条（新条目同样经唯一入口写入）
        pipeline = MemoryWritePipeline(store)
        new_result = pipeline.write(
            npc_id="npc-00",
            content="替代记忆。",
            source="reason",
            event_seq=99,
            importance=0.9,
            emotion_tag=None,
        )
        assert new_result.entry is not None
        new = new_result.entry
        pipeline.supersede(entries[0].id, new.id, "banned_word")

        hits = retrieve(store, MemoryQuery(npc_id="npc-00", top_k=10))
        ids = {h.entry.id for h in hits}
        assert entries[0].id not in ids  # 被取代条目不在检索面
        assert new.id in ids

    def test_top_k_limits(self, store: InMemoryStore) -> None:
        _seed(store, "npc-00", n=5)
        hits = retrieve(store, MemoryQuery(npc_id="npc-00", top_k=2))
        assert len(hits) == 2

    def test_top_k_zero_means_unlimited(self, store: InMemoryStore) -> None:
        _seed(store, "npc-00", n=5)
        hits = retrieve(store, MemoryQuery(npc_id="npc-00", top_k=0))
        assert len(hits) == 5

    def test_sorted_by_score_desc(self, store: InMemoryStore) -> None:
        _seed(store, "npc-00", n=4)  # importance 递增 0.5..0.8
        hits = retrieve(store, MemoryQuery(npc_id="npc-00", top_k=10))
        scores = [h.score for h in hits]
        assert scores == sorted(scores, reverse=True)
        assert hits[0].entry.importance == pytest.approx(0.8)

    def test_accepts_bare_iterable(self) -> None:
        entries = [
            make_entry(
                entry_id="a",
                npc_id="npc-00",
                content="A",
                source="reason",
                event_seq=1,
                importance=0.3,
                emotion_tag=None,
            ),
            make_entry(
                entry_id="b",
                npc_id="npc-00",
                content="B",
                source="reason",
                event_seq=1,
                importance=0.7,
                emotion_tag=None,
            ),
        ]
        hits = retrieve(entries, MemoryQuery(npc_id="npc-00"))
        assert [h.entry.id for h in hits] == ["b", "a"]


@pytest.mark.t1
class TestBaseScorePure:
    def test_base_score_is_importance_times_recency(self) -> None:
        e = make_entry(
            entry_id="a",
            npc_id="npc-00",
            content="x",
            source="reason",
            event_seq=100,
            importance=0.6,
            emotion_tag=None,
        )
        # event_seq == now_tick → age 0 → recency 1.0
        assert recency_factor(e, 100) == pytest.approx(1.0)
        assert base_score(e, MemoryQuery(npc_id="npc-00", now_tick=100)) == pytest.approx(0.6)

    def test_recency_decays_with_age(self) -> None:
        e = make_entry(
            entry_id="a",
            npc_id="npc-00",
            content="x",
            source="reason",
            event_seq=0,
            importance=1.0,
            emotion_tag=None,
        )
        fresh = recency_factor(e, 0)
        old = recency_factor(e, 86_400)  # 一个半衰期
        assert fresh == pytest.approx(1.0)
        assert old == pytest.approx(0.5)

    def test_no_now_tick_disables_decay(self) -> None:
        e = make_entry(
            entry_id="a",
            npc_id="npc-00",
            content="x",
            source="reason",
            event_seq=0,
            importance=0.4,
            emotion_tag=None,
        )
        assert base_score(e, MemoryQuery(npc_id="npc-00")) == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# 2. 钩子缝：不写死偏差逻辑
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestScorerSeam:
    def test_no_scorers_is_pure_base(self, store: InMemoryStore) -> None:
        # 写两条等重要性、同近因 → 分相同；breakdown 只有 base
        _seed(store, "npc-00", n=2)
        hits = retrieve(store, MemoryQuery(npc_id="npc-00", now_tick=10))
        assert all(h.breakdown == (("base", h.score),) for h in hits)

    def test_mul_scorer_scales_score(self, store: InMemoryStore) -> None:
        _seed(store, "npc-00", n=2)
        bias = Scorer("confirmation_bias", lambda e, q: 2.0, mode="mul")
        plain = retrieve(store, MemoryQuery(npc_id="npc-00", now_tick=10))
        biased = retrieve(store, MemoryQuery(npc_id="npc-00", now_tick=10), scorers=[bias])
        by_id = {h.entry.id: h for h in plain}
        for h in biased:
            assert h.score == pytest.approx(by_id[h.entry.id].score * 2.0)
            assert ("confirmation_bias", 2.0) in h.breakdown

    def test_add_scorer_shifts_score(self, store: InMemoryStore) -> None:
        _seed(store, "npc-00", n=2)
        bias = Scorer("mood_congruence", lambda e, q: 0.25, mode="add")
        hits = retrieve(store, MemoryQuery(npc_id="npc-00", now_tick=10), scorers=[bias])
        for h in hits:
            assert h.score == pytest.approx(h.breakdown[0][1] + 0.25)

    def test_scorer_receives_query_context(self, store: InMemoryStore) -> None:
        _seed(store, "npc-00", n=1)
        seen: dict[str, object] = {}

        def spy(entry: MemoryEntry, query: MemoryQuery) -> float:
            seen["npc"] = query.npc_id
            seen["context"] = query.context
            seen["mood"] = query.mood
            return 1.0

        retrieve(
            store,
            MemoryQuery(npc_id="npc-00", context="水边的旧事", mood=(0.2, -0.1, 0.0)),
            scorers=[Scorer("spy", spy)],
        )
        assert seen == {"npc": "npc-00", "context": "水边的旧事", "mood": (0.2, -0.1, 0.0)}

    def test_empty_registry_matches_no_scorers(self, store: InMemoryStore) -> None:
        _seed(store, "npc-00", n=2)
        reg = RetrievalScorers()
        assert reg.as_sequence() == ()
        a = retrieve(store, MemoryQuery(npc_id="npc-00", now_tick=10))
        b = retrieve(store, MemoryQuery(npc_id="npc-00", now_tick=10), scorers=reg.as_sequence())
        assert [h.score for h in a] == [h.score for h in b]

    def test_registry_register_is_immutable(self) -> None:
        reg = RetrievalScorers()
        reg2 = reg.register(Scorer("x", lambda e, q: 1.0))
        assert reg.as_sequence() == ()
        assert [s.name for s in reg2.as_sequence()] == ["x"]


# ---------------------------------------------------------------------------
# 3. 确定性 + 规约
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestDeterminism:
    def test_tie_break_by_entry_id(self) -> None:
        def mk(eid: str) -> MemoryEntry:
            return make_entry(
                entry_id=eid,
                npc_id="npc-00",
                content=eid,
                source="reason",
                event_seq=1,
                importance=0.5,  # 全等 → 回退 id 序
                emotion_tag=None,
            )

        entries = [mk("zzz"), mk("aaa"), mk("mmm")]
        hits = retrieve(entries, MemoryQuery(npc_id="npc-00", now_tick=1))
        assert [h.entry.id for h in hits] == ["aaa", "mmm", "zzz"]

    def test_repeatable(self, store: InMemoryStore) -> None:
        _seed(store, "npc-00", n=4)
        q = MemoryQuery(npc_id="npc-00", now_tick=3)
        first = [(h.entry.id, h.score) for h in retrieve(store, q)]
        second = [(h.entry.id, h.score) for h in retrieve(store, q)]
        assert first == second

    def test_scores_of_projects_to_mapping(self, store: InMemoryStore) -> None:
        _seed(store, "npc-00", n=3)
        hits = retrieve(store, MemoryQuery(npc_id="npc-00", now_tick=5))
        mapping = scores_of(hits)
        assert set(mapping) == {h.entry.id for h in hits}
        assert all(isinstance(v, float) for v in mapping.values())


@pytest.mark.t1
class TestReadOnly:
    def test_retrieve_does_not_mutate_store(self, store: InMemoryStore) -> None:
        _seed(store, "npc-00", n=3)
        before = sorted(e.id for e in store.iter_visible("npc-00"))
        retrieve(store, MemoryQuery(npc_id="npc-00", top_k=1))
        after = sorted(e.id for e in store.iter_visible("npc-00"))
        assert before == after
        assert len(store) == 3

    def test_retrieve_returns_memory_hit_type(self, store: InMemoryStore) -> None:
        _seed(store, "npc-00", n=1)
        hits = retrieve(store, MemoryQuery(npc_id="npc-00"))
        assert all(isinstance(h, MemoryHit) for h in hits)


# ---------------------------------------------------------------------------
# 4. codex MEDIUM 回归
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def sql_store(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return SqlEventStore(sf)


@pytest.mark.t1
class TestAppendValidationRegression:
    """MEDIUM ①：append 默认校验，拒绝夹带 payload / 伪造 witnesses。"""

    async def test_rejects_smuggled_payload_key(self, sql_store) -> None:
        row = {
            "tick": 1,
            "event_type": "npc.act",
            "payload": {"npc_id": "npc-00", "action": "rest", "smuggled": "param"},
        }
        with pytest.raises(EventValidationError, match="payload"):
            await sql_store.append("main", [row])

    async def test_rejects_non_whitelist_action(self, sql_store) -> None:
        row = {
            "tick": 1,
            "event_type": "npc.act",
            "payload": {"npc_id": "npc-00", "action": "explode"},
        }
        with pytest.raises(EventValidationError, match="非白名单动作"):
            await sql_store.append("main", [row])

    async def test_rejects_offwhitelist_params_key(self, sql_store) -> None:
        row = {
            "tick": 1,
            "event_type": "npc.act",
            "payload": {"npc_id": "npc-00", "action": "rest", "params": {"evil": "1"}},
        }
        with pytest.raises(EventValidationError, match="params 键越界"):
            await sql_store.append("main", [row])

    async def test_rejects_forged_witnesses(self, sql_store) -> None:
        row = {
            "tick": 1,
            "event_type": "npc.lod_change",
            "payload": {"npc_id": "npc-00", "from_lod": 0, "to_lod": 1, "reason": "x"},
            "witnesses": "npc-99",  # 应为 list[str]
        }
        with pytest.raises(EventValidationError, match="witnesses"):
            await sql_store.append("main", [row])

    async def test_rejects_unknown_kind(self, sql_store) -> None:
        row = {"tick": 1, "event_type": "not.a.kind", "payload": {}}
        with pytest.raises(EventValidationError, match="未知事件种类"):
            await sql_store.append("main", [row])

    async def test_valid_row_passes(self, sql_store, engine) -> None:
        row = {
            "tick": 1,
            "event_type": "npc.act",
            "payload": {"npc_id": "npc-00", "action": "rest", "params": {"hours": "2"}},
            "witnesses": ["npc-01"],
        }
        await sql_store.append("main", [row])
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with sf() as s:
            events = (await s.execute(select(Event))).scalars().all()
        assert len(events) == 1

    async def test_validate_false_escape_hatch(self, sql_store, engine) -> None:
        row = {"tick": 1, "event_type": "move", "payload": {"synthetic": True}}
        await sql_store.append("main", [row], validate=False)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with sf() as s:
            events = (await s.execute(select(Event))).scalars().all()
        assert len(events) == 1

    async def test_rejection_leaves_no_partial_write(self, sql_store, engine) -> None:
        good = {"tick": 1, "event_type": "npc.act", "payload": {"npc_id": "n", "action": "eat"}}
        bad = {"tick": 2, "event_type": "npc.act", "payload": {"npc_id": "n", "action": "bogus"}}
        with pytest.raises(EventValidationError):
            await sql_store.append("main", [good, bad])
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with sf() as s:
            events = (await s.execute(select(Event))).scalars().all()
        assert events == []


@pytest.mark.t1
class TestMaterializeHiddenRegression:
    """MEDIUM ②：materialize_hidden 装配 npc_health 隐藏行 → HiddenState。"""

    async def test_assembles_hidden_rows(self, sql_store, engine) -> None:
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with sf() as s:
            s.add(
                NpcProfile(
                    id="npc-00",
                    branch_id="main",
                    name="陈默",
                    species="human",
                    lod=1,
                    needs="[]",
                    skills="{}",
                )
            )
            s.add(
                NpcHealth(
                    npc_id="npc-00",
                    branch_id="main",
                    category="trauma",
                    label="溺水的记忆",
                    severity=0.7,
                    hidden=True,
                    active=True,
                    descriptors=json.dumps(["溺水", "水"], ensure_ascii=False),
                    trigger_conditions=json.dumps(["水边", "渡水"], ensure_ascii=False),
                    created_at_tick=0,
                )
            )
            # 非隐藏（可见健康档）不应进 HiddenState
            s.add(
                NpcHealth(
                    npc_id="npc-00",
                    branch_id="main",
                    category="disease",
                    label="感冒",
                    hidden=False,
                    active=True,
                    created_at_tick=0,
                )
            )
            await s.commit()

        ns = NpcStore(sql_store)
        states = await ns.materialize_hidden()

        assert set(states) == {"npc-00"}
        profile = states["npc-00"].profile
        assert profile is not None
        assert len(profile.attributes) == 1  # 只隐藏行
        attr = profile.attributes[0]
        assert attr.category == "trauma"
        assert attr.label == "溺水的记忆"
        assert attr.descriptors == ("溺水", "水")
        assert attr.triggers == ("水边", "渡水")
        assert states["npc-00"].triggered == frozenset()

    async def test_subset_and_empty(self, sql_store, engine) -> None:
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with sf() as s:
            s.add(
                NpcHealth(
                    npc_id="npc-01",
                    branch_id="main",
                    category="addiction",
                    label="酒瘾",
                    hidden=True,
                    active=True,
                    descriptors=json.dumps(["酒"]),
                    trigger_conditions=json.dumps(["酒"]),
                    created_at_tick=0,
                )
            )
            await s.commit()
        ns = NpcStore(sql_store)
        assert await ns.materialize_hidden([]) == {}
        assert set(await ns.materialize_hidden(["npc-01", "npc-absent"])) == {"npc-01"}
        assert await ns.materialize_hidden(["npc-absent"]) == {}

    async def test_inactive_hidden_excluded(self, sql_store, engine) -> None:
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with sf() as s:
            s.add(
                NpcHealth(
                    npc_id="npc-02",
                    branch_id="main",
                    category="disability",
                    label="跛足",
                    hidden=True,
                    active=False,  # 失活不装配
                    created_at_tick=0,
                )
            )
            await s.commit()
        ns = NpcStore(sql_store)
        assert await ns.materialize_hidden() == {}


# ---------------------------------------------------------------------------
# 5. 挂账清偿：redact_sensitive 接入全局日志链（M2-D3 §任务 3）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestRedactSensitiveWired:
    def test_setup_logging_includes_redact_sensitive(self) -> None:
        """setup_logging() 的 processor 链必须含 redact_sensitive（K8 挂账核对）。"""
        import structlog

        from sim.core.logsetup import setup_logging
        from sim.core.persistence.crypto import redact_sensitive

        setup_logging()
        processors = structlog.get_config()["processors"]
        assert redact_sensitive in processors

    def test_redact_sensitive_masks_secret_nested(self) -> None:
        """嵌套敏感键 → ***（含大小写不敏感）。"""
        from sim.core.persistence.crypto import REDACTED, redact_sensitive

        event = {
            "event": "llm.call",
            "api_key": "sk-secret",
            "meta": {"Authorization": "Bearer x", "safe": 1},
        }
        out = redact_sensitive(None, "info", event)
        assert out["api_key"] == REDACTED
        assert out["meta"]["Authorization"] == REDACTED
        assert out["meta"]["safe"] == 1
