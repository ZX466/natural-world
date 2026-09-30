"""M5-D3-c T1 钉子 — R2 三断言（分叉重放）+ RNG 连续（D）+ 可比字段集守卫

DESIGN §16 T2「回放确定性」在**读档 = 分叉**下的口径（`m5-fork-archive-preplan.md`
§6.2）。三种重放：

- **R1** 同分支重放（现状，M3-C2 已钉）：`fold(events[b], 1..N)` == `materialize(b)`；
- **R2** 分叉重放（本文件）：`fold(events[父], 1..F)` 接 `fold(events[子], 1..M)`；
- **R3** 克隆 vs 纯重放对照：子分支「克隆所得」与「纯重放所得」逐位相等。

R2 的三条断言（= 本文件的 A/B/C）：

| 断言 | 内容 | 抓什么 |
|---|---|---|
| **A 接缝一致** | 克隆所得子分支物化态 == `fold(父分支事件, 1..F)` | 克隆漏表/漏列/错截断 |
| **B 段内一致** | 子分支后续事件：在线投影 == R2 复合折叠 | 折叠规则分叉（两套语义） |
| **C 前缀无关** | 父分支在 F 之后再追加事件/记忆/知识/向量 | **泄漏照妖镜**：读面跨了分支就会变 |

C 是 D3-b 遗留面的照妖镜：裁 5 之后父分支被封存（`append` 拒写），所以测试**直接往
父分支硬塞**事件/语料行——模拟「未封存的历史实现」或任何未来「父分支仍可推进」的形态，
验证子分支的读面**确实只看自己**。

**断言 D（RNG 连续）**：分叉点两侧的随机流必须**承接抽签进度**，否则接缝处
「确定性混沌」行为跳变（预研稿 §6.3）。本文件钉住承接机制
（`sim/core/rng_state.py`：捕获 registry + 每流 PCG64 状态 → 恢复 → **后续抽签逐位一致**），
并用一条**二阶守卫**钉住反面：只承接 registry（= seed 语义）**必然跳变**——
防止将来把承接退化成「存一个 seed」（实测 PCG64 进度不在 seed 里）。

**可比字段集**（预研稿 §6.4）：逐位一致不可能覆盖 `autoinc` id / 落库时钟 / 向量 /
归档标记等，必须**显式排除且有名字**——`fork_replay.COMPARABLE_*` + `EXCLUDED_FIELDS`
（键=ORM 列名，值=排除理由），钉子 C3 守卫「新增列不得静默进入比较」。
"""

from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import (
    EventKind,
    WorldEvent,
    material_moved_event,
    matter_event,
    npc_lod_change_event,
    structure_started_event,
)
from sim.core.persistence.database import init_database
from sim.core.persistence.fork import fork_from_anchor
from sim.core.persistence.fork_replay import (
    COMPARABLE_KNOWLEDGE_FIELDS,
    COMPARABLE_MEMORY_FIELDS,
    EXCLUDED_FIELDS,
    comparable_knowledge,
    comparable_memory,
)
from sim.core.persistence.models import (
    Branch,
    Event,
    Knowledge,
    MaterialBalance,
    MatterState,
    NpcMemory,
    NpcProfile,
    Structure,
)
from sim.core.persistence.npc_store import NpcStore, fold_matter_snapshot
from sim.core.persistence.store import SqlEventStore
from sim.core.persistence.vector import VEC_TABLE, VecCandidateSource, create_memory_vec_table
from sim.core.rng import RngRegistry
from sim.core.rng_state import RngStateError, capture_rng_state, restore_rng_state
from sim.world.matter import MatterSnapshot

PARENT = "main"
CHILD = "fork-b"
STREAMS = ("world.weather", "combat.critical", "npc.decide")
VEC_DIM = 8


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
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


async def _noop_preflush() -> None:
    return None


def _lod(tick: int, npc_id: str = "chenmo", *, to_lod: int = 2) -> WorldEvent:
    return npc_lod_change_event(tick, npc_id, 1, to_lod, "enter_range")


def _matter(tick: int, matter_id: str, durability: float) -> WorldEvent:
    return matter_event(tick, EventKind.MATTER_BUILD, matter_id, durability=durability, note="test")


def _material(tick: int, frm: str, to: str, material: str, qty: float) -> WorldEvent:
    return material_moved_event(
        tick,
        transfer_id=f"t{tick}",
        material_id=material,
        quantity=qty,
        from_ref=frm,
        to_ref=to,
        reason="build_consumed",
    )


def _structure(tick: int, structure_id: str) -> WorldEvent:
    return structure_started_event(
        tick,
        structure_id=structure_id,
        tiles=((0, 0),),
        kind="wood_hut",
        material="wood",
        planned_duration_ticks=100,
        recipe_id="r-wood-hut",
        recipe_version="1",
        build_rule_version="v1",
    )


def _memory(
    entry_id: str,
    *,
    branch_id: str = PARENT,
    content: str = "内容",
    event_seq: int | None = 1,
) -> NpcMemory:
    return NpcMemory(
        entry_id=entry_id,
        npc_id="chenmo",
        branch_id=branch_id,
        content=content,
        source="event",
        importance=0.5,
        created_at_tick=0,
        event_seq=event_seq,
    )


def _blob(vals: list[float]) -> bytes:
    return struct.pack(f"{len(vals)}f", *vals)


async def _seed_world(store, session: AsyncSession) -> None:
    """父分支跑到 6 tick：3 个 matter + 1 次材料转移 + 1 个结构 + 1 条记忆 + 1 条知识。"""
    events = [
        _lod(1),
        _matter(2, "hut-1", 0.9),
        _material(3, "world:supply", "structure:hut-1", "wood", 3.0),
        _structure(4, "hut-1"),
        _matter(5, "tool-1", 0.5),
        _lod(6, to_lod=1),
    ]
    # 先立 profile（LOD 投影要按 (branch_id, id) 找它），再走生产路径：
    # flush_tick = 事件 + 投影同事务（投影不落库则「克隆 vs 重放」无从比起）
    session.add(
        NpcProfile(id="chenmo", branch_id=PARENT, name="陈默", identity_anchor="我叫陈默。")
    )
    await session.commit()
    await NpcStore(store, branch_id=PARENT).flush_tick(events)
    session.add(_memory("e-1", content="主线记忆"))
    session.add(
        Knowledge(
            holder_id="chenmo",
            fact="他知道井在哪",
            confidence=0.6,
            source="witnessed",
            learned_at=1,
            branch_id=PARENT,
            evidence_seq=1,
        )
    )
    await session.commit()


def _fold_matter_events(base: dict[str, object], events: list[dict]) -> dict[str, object]:
    """把一批 ``matter.*`` 事件折叠到给定基线之上（R2 重放的组合子）。

    复用 store 的**同一批** fold 函数（`fold_matter_snapshot`）——这是 C2「折叠规则单一
    来源」的检验点：若重放另写一套规则，本用例会红。
    """
    states = dict(base)
    for ev in sorted(events, key=lambda e: int(e["seq"])):
        kind = str(ev["event_type"])
        if not kind.startswith("matter."):
            continue
        payload = ev.get("payload") or {}
        matter_id = str(payload.get("matter_id", ""))
        states[matter_id] = fold_matter_snapshot(
            cast(MatterSnapshot, states.get(matter_id)),
            matter_id=matter_id,
            durability=float(payload.get("durability", -1.0)),
            decay_rate=float(payload.get("decay_rate", -1.0)),
            is_collapse=kind == "matter.collapse",
        )
    return states


# ---------------------------------------------------------------------------
# A | 接缝一致：克隆所得 == 父分支前缀折叠
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestR2SeamConsistency:
    """A：接缝两侧必须逐位相等（有 fold 器的四张表 + 语料行集）。"""

    async def test_A_matter_seam_equal(self, store, session: AsyncSession) -> None:
        await _seed_world(store, session)
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=6,
            fork_tick=6,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        child_snap = await NpcStore(store, branch_id=CHILD).materialize_matter()
        parent_replay = await NpcStore(store, branch_id=PARENT).materialize_matter_replay()
        assert child_snap._items == parent_replay._items, "接缝处 matter 物化态不等"
        assert set(child_snap._items) == {"hut-1", "tool-1"}
        assert result.forked_from_seq == 6

    async def test_A_structures_and_balances_seam_equal(self, store, session: AsyncSession) -> None:
        await _seed_world(store, session)
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=6,
            fork_tick=6,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        child = NpcStore(store, branch_id=CHILD)
        parent = NpcStore(store, branch_id=PARENT)
        assert await child.materialize_structures() == await parent.materialize_structures_replay()
        assert await child.materialize_material_balances() == (
            await parent.materialize_material_balances_replay()
        )

    async def test_A_corpus_rows_equal_by_comparable_fields(
        self, store, session: AsyncSession
    ) -> None:
        """语料行集：按可比字段集逐行相等（id/entry_id 已重映射，故不比）。"""
        await _seed_world(store, session)
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=6,
            fork_tick=6,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        parent_mem = (
            (await session.execute(select(NpcMemory).where(NpcMemory.branch_id == PARENT)))
            .scalars()
            .all()
        )
        child_mem = (
            (await session.execute(select(NpcMemory).where(NpcMemory.branch_id == CHILD)))
            .scalars()
            .all()
        )
        assert [comparable_memory(r) for r in child_mem] == [
            comparable_memory(r) for r in parent_mem
        ]
        assert child_mem[0].entry_id == result.entry_id_map["e-1"]

        parent_know = (
            (await session.execute(select(Knowledge).where(Knowledge.branch_id == PARENT)))
            .scalars()
            .all()
        )
        child_know = (
            (await session.execute(select(Knowledge).where(Knowledge.branch_id == CHILD)))
            .scalars()
            .all()
        )
        assert [comparable_knowledge(r) for r in child_know] == [
            comparable_knowledge(r) for r in parent_know
        ]


# ---------------------------------------------------------------------------
# B | 段内一致：子分支后续事件，投影 == 重放
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestR2SegmentConsistency:
    """B：接缝之后，子分支的在线投影与重放折叠必须逐位相等。"""

    async def test_B_child_events_projection_equals_replay(
        self, store, session: AsyncSession
    ) -> None:
        """B：R2 重放 = **父分支前缀折叠 ∘ 子分支自身事件折叠**，结果 == 子分支物化态。

        口径要点（D3-c 才想清楚的）：子分支的 `events` **只含自己的事件**（事件不克隆），
        而它继承的投影行（`hut-1` 等）的事件住在**父分支** ⇒ 单独重放子分支事件流**必然
        少一半**。所以 R2 的定义是「沿 branch 链回放」，不是「重放本分支事件」。
        """
        await _seed_world(store, session)
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=6,
            fork_tick=6,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        child = NpcStore(store, branch_id=CHILD)
        await child.flush_tick(
            [
                _matter(7, "tool-1", 0.2),
                _matter(7, "hut-1", 0.4),
                _matter(7, "new-1", 1.0),
            ]
        )

        parent_base = (await NpcStore(store, branch_id=PARENT).materialize_matter_replay())._items
        r2 = _fold_matter_events(dict(parent_base), await store.read_range(CHILD, 0, 2**62 - 1))
        assert (await child.materialize_matter())._items == r2
        assert set(r2) == {"hut-1", "tool-1", "new-1"}

    async def test_B_child_projection_does_not_touch_parent(
        self, store, session: AsyncSession
    ) -> None:
        """子分支的投影只写子分支行（父分支投影逐字段不变）。"""
        await _seed_world(store, session)
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=6,
            fork_tick=6,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        before = {
            (r.branch_id, r.subject_id): (r.integrity, r.updated_at_tick)
            for r in (await session.execute(select(MatterState))).scalars().all()
        }
        await NpcStore(store, branch_id=CHILD).flush_tick([_matter(7, "tool-1", 0.2)])
        session.expire_all()
        session.expire_all()
        parent_rows = (
            (await session.execute(select(MatterState).where(MatterState.branch_id == PARENT)))
            .scalars()
            .all()
        )
        after_parent = {r.subject_id: (r.integrity, r.updated_at_tick) for r in parent_rows}
        assert after_parent == {k[1]: v for k, v in before.items() if k[0] == PARENT}


# ---------------------------------------------------------------------------
# C | 前缀无关：父分支后续变化不得影响子分支（跨分支泄漏照妖镜）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestR2PrefixIndependence:
    """C：往父分支硬塞新数据（裁 5 封存后的历史形态），子分支必须逐位不变。"""

    async def _snapshot_child(self, store) -> dict[str, object]:
        child = NpcStore(store, branch_id=CHILD)
        return {
            "matter": (await child.materialize_matter())._items,
            "matter_replay": (await child.materialize_matter_replay())._items,
            "structures": await child.materialize_structures(),
            "balances": await child.materialize_material_balances(),
        }

    async def _hard_append_parent(self, store, session: AsyncSession) -> None:
        """绕过裁 5 闸门直写父分支（模拟「未封存」历史实现 / 任何未来继续推进）。"""
        await session.execute(
            insert(Event).values(
                [
                    {
                        "branch_id": PARENT,
                        "seq": 7,
                        "tick": 7,
                        "event_type": "matter.build",
                        "actor_id": "chenmo",
                        "target_id": "ghost-1",
                        "parent_seq": None,
                        "parent_branch_id": None,
                        "payload": json.dumps(
                            {
                                "matter_id": "ghost-1",
                                "amount": 0.0,
                                "durability": 0.7,
                                "note": "parent-only",
                            },
                            ensure_ascii=False,
                        ),
                        "witnesses": "[]",
                        "entropy_ref": None,
                        "created_at": 0.0,
                    }
                ]
            )
        )
        session.add(_memory("e-parent-late", content="父分支后来的记忆", event_seq=7))
        session.add(
            Knowledge(
                holder_id="chenmo",
                fact="父分支后来才知道的",
                confidence=0.4,
                source="inferred",
                learned_at=7,
                branch_id=PARENT,
            )
        )
        await session.commit()

    async def test_C_child_state_invariant_to_parent_growth(
        self, store, session: AsyncSession
    ) -> None:
        await _seed_world(store, session)
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=6,
            fork_tick=6,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        before = await self._snapshot_child(store)

        await self._hard_append_parent(store, session)
        after = await self._snapshot_child(store)
        assert before == after, "父分支后续推进改变了子分支的重放结果（跨分支泄漏）"

    async def test_C_parent_governance_does_not_leak_into_child(
        self, store, session: AsyncSession
    ) -> None:
        """父分支的治理动作（supersede / 级联失效）不得改到子分支行。"""
        await _seed_world(store, session)
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=6,
            fork_tick=6,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        child_old = result.entry_id_map["e-1"]
        await session.execute(
            update(NpcMemory)
            .where(NpcMemory.branch_id == PARENT, NpcMemory.entry_id == "e-1")
            .values(superseded_by="e-new", invalid_reason="banned_word")
        )
        await session.execute(
            update(Knowledge)
            .where(Knowledge.branch_id == PARENT)
            .values(invalidated=True, invalid_reason="manual_review")
        )
        session.add(_memory("e-new", content="父分支的替代记忆", event_seq=7))
        await session.commit()

        child_rows = (
            (await session.execute(select(NpcMemory).where(NpcMemory.branch_id == CHILD)))
            .scalars()
            .all()
        )
        assert len(child_rows) == 1 and child_rows[0].entry_id == child_old
        assert child_rows[0].superseded_by is None
        assert child_rows[0].invalid_reason is None
        child_know = (
            (await session.execute(select(Knowledge).where(Knowledge.branch_id == CHILD)))
            .scalars()
            .all()
        )
        assert child_know[0].invalidated is False
        assert child_know[0].invalid_reason is None

    async def test_C_child_vec_recall_invariant_to_parent_vectors(self, tmp_path: Path) -> None:
        """向量面同理：父分支新增记忆 + 向量后，子分支的候选集必须不变（F3 分支谓词）。"""
        db = tmp_path / "fork_replay_vec.db"
        eng = create_async_engine(f"sqlite+aiosqlite:///{db}", echo=False)
        await init_database(eng)
        sf = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        store = SqlEventStore(sf)
        vec = sqlite3.connect(str(db))
        try:
            create_memory_vec_table(vec, dim=VEC_DIM)
            await store.append(PARENT, [_lod(1).to_store_dict()])
            async with sf() as session:
                session.add(_memory("e-1", content="主线记忆"))
                await session.commit()
                parent_id = (
                    (await session.execute(select(NpcMemory).where(NpcMemory.branch_id == PARENT)))
                    .scalar_one()
                    .id
                )
            q = _blob([1.0, 0, 0, 0, 0, 0, 0, 0])
            vec.execute(f"INSERT INTO {VEC_TABLE}(rowid, embedding) VALUES (?, ?)", (parent_id, q))
            vec.commit()

            await fork_from_anchor(
                sf,
                parent_branch_id=PARENT,
                fork_seq=1,
                fork_tick=1,
                new_branch_id=CHILD,
                preflush=_noop_preflush,
                vec_conn=vec,
            )
            before = {c.id for c in VecCandidateSource(vec, branch_id=CHILD).candidates(q, 10)}
            assert before

            async with sf() as session:
                session.add(
                    NpcMemory(
                        entry_id="e-parent-late",
                        npc_id="chenmo",
                        branch_id=PARENT,
                        content="父分支后来的记忆",
                        source="event",
                        importance=0.9,
                        created_at_tick=2,
                        event_seq=2,
                    )
                )
                await session.commit()
                late_id = (
                    (
                        await session.execute(
                            select(NpcMemory).where(NpcMemory.entry_id == "e-parent-late")
                        )
                    )
                    .scalar_one()
                    .id
                )
            vec.execute(f"INSERT INTO {VEC_TABLE}(rowid, embedding) VALUES (?, ?)", (late_id, q))
            vec.commit()

            after = {c.id for c in VecCandidateSource(vec, branch_id=CHILD).candidates(q, 10)}
            assert after == before, "父分支新增向量改变了子分支候选集（F3 漏）"
        finally:
            vec.close()
            await eng.dispose()


# ---------------------------------------------------------------------------
# 可比字段集守卫（预研稿 §6.4：排除项必须有名字）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestComparableFieldSet:
    def test_C3_excluded_fields_are_named_and_exist_in_orm(self) -> None:
        mem_cols = set(cast(type[NpcMemory], NpcMemory).__table__.columns.keys())
        know_cols = set(cast(type[Knowledge], Knowledge).__table__.columns.keys())
        for name, reason in EXCLUDED_FIELDS.items():
            assert reason.strip(), f"排除项 {name} 没有写理由"
            assert name in mem_cols | know_cols, f"排除项 {name} 不是 ORM 列名（拼错了？）"

    def test_C3_comparable_sets_exclude_every_excluded_field(self) -> None:
        assert not (set(COMPARABLE_MEMORY_FIELDS) & set(EXCLUDED_FIELDS))
        assert not (set(COMPARABLE_KNOWLEDGE_FIELDS) & set(EXCLUDED_FIELDS))

    def test_C3_comparators_return_only_declared_fields(self) -> None:
        row = _memory("e-1")
        assert set(comparable_memory(row)) == set(COMPARABLE_MEMORY_FIELDS)
        know = Knowledge(
            holder_id="h",
            fact="f",
            confidence=0.5,
            source="inferred",
            learned_at=1,
            branch_id=PARENT,
        )
        assert set(comparable_knowledge(know)) == set(COMPARABLE_KNOWLEDGE_FIELDS)

    def test_C3_comparators_ignore_branch_and_identity(self) -> None:
        """比较跨分支语料时必须忽略 branch_id 与 id/entry_id（克隆已重映射）。"""
        a = _memory("e-1", branch_id=PARENT, content="同一段")
        b = _memory("e-2", branch_id=CHILD, content="同一段")
        b.id = 999
        assert comparable_memory(a) == comparable_memory(b)


# ---------------------------------------------------------------------------
# D | RNG 连续：承接抽签进度（不是承接一个 seed）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestRngContinuity:
    """D：分叉点两侧的随机流承接**进度**（预研稿 §6.3；实测 seed 语义必然跳变）。"""

    def test_D_capture_restore_keeps_next_draws_identical(self) -> None:
        reg = RngRegistry(world_seed=7)
        cache: dict[str, np.random.Generator] = {}
        for name in STREAMS:
            reg.generator(name, cache).random(11)

        blob = capture_rng_state(reg, cache, STREAMS)
        restored_cache: dict[str, np.random.Generator] = {}
        reg2 = restore_rng_state(blob, restored_cache, STREAMS)

        for name in STREAMS:
            assert reg2.draw_key(name) == reg.draw_key(name), "材料指纹未承接"
            assert np.array_equal(
                cache[reg.draw_key(name)].random(8),
                restored_cache[reg2.draw_key(name)].random(8),
            ), f"流 {name} 承接后抽签跳变"

    def test_D_seed_only_resume_diverges(self) -> None:
        """二阶守卫：只承接 registry（seed 语义）**必然**跳变——钉住反面，防退化。"""
        reg = RngRegistry(world_seed=7)
        cache: dict[str, np.random.Generator] = {}
        for name in STREAMS:
            reg.generator(name, cache).random(11)

        # 反面：新建 cache（模拟「只存 seed、进度从头开始」）
        naive_cache: dict[str, np.random.Generator] = {}
        naive = RngRegistry(world_seed=reg.world_seed, materials=dict(reg.materials))
        diverged = any(
            not np.array_equal(
                cache[reg.draw_key(name)].random(8), naive.generator(name, naive_cache).random(8)
            )
            for name in STREAMS
        )
        assert diverged, "seed 语义竟然也逐位一致？那 (a) 方案可行，请重估 §6.3 建议"

    def test_D_entropy_inject_material_is_carried(self) -> None:
        """熵注入后的材料必须随状态包承接（否则子分支会用回注入前的确定性流）。"""
        reg = RngRegistry(world_seed=7)
        reg = reg.reseed("combat.critical", b"\x01\x02\x03")
        cache: dict[str, np.random.Generator] = {}
        reg.generator("combat.critical", cache).random(3)

        blob = capture_rng_state(reg, cache, ("combat.critical",))
        restored_cache: dict[str, np.random.Generator] = {}
        reg2 = restore_rng_state(blob, restored_cache, ("combat.critical",))
        assert reg2.materials == reg.materials
        assert np.array_equal(
            cache[reg.draw_key("combat.critical")].random(5),
            restored_cache[reg2.draw_key("combat.critical")].random(5),
        )

    def test_D_unknown_version_fails_closed(self) -> None:
        reg = RngRegistry(world_seed=7)
        cache: dict[str, np.random.Generator] = {}
        reg.generator("a", cache).random(2)
        blob = json.loads(capture_rng_state(reg, cache, ("a",)))
        blob["v"] = 999
        with pytest.raises(RngStateError, match="版本"):
            restore_rng_state(json.dumps(blob), {}, ("a",))

    def test_D_material_fingerprint_mismatch_fails_closed(self) -> None:
        """捕获的 key 与 registry 不匹配（registry 被换过）→ fail-closed，不静默续跑。"""
        reg = RngRegistry(world_seed=7)
        cache: dict[str, np.random.Generator] = {}
        reg.generator("a", cache).random(2)
        blob = json.loads(capture_rng_state(reg, cache, ("a",)))
        blob["streams"]["a"]["key"] = "0" * 64
        with pytest.raises(RngStateError, match="指纹"):
            restore_rng_state(json.dumps(blob), {}, ("a",))

    async def test_D_fork_persists_rng_state(self, store, session: AsyncSession) -> None:
        """`fork_from_anchor` 把 rng_state **原样落进**子分支行（不吞、不改写）。

        裁 27-B b2 之后：状态进 `branches.rng_state`（0009，与克隆同事务），
        `rng_state_persisted` 随「是否真落库」翻转。落库细节与往返验证的钉子在
        `sim/tests/test_m5_branches_rng_state.py`。
        """
        await _seed_world(store, session)
        reg = RngRegistry(world_seed=7)
        cache: dict[str, np.random.Generator] = {}
        for name in STREAMS:
            reg.generator(name, cache).random(4)
        blob = capture_rng_state(reg, cache, STREAMS)

        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=6,
            fork_tick=6,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
            rng_state=blob,
        )
        assert result.rng_state == blob
        assert result.rng_state_persisted is True
        session.expire_all()
        child = await session.get(Branch, CHILD)
        assert child is not None and child.rng_state == blob


# ---------------------------------------------------------------------------
# 辅助：分叉后子分支行的存在性（避免 C 组用例因行缺失而假绿）
# ---------------------------------------------------------------------------


@pytest.mark.t1
async def test_child_branch_row_exists_after_fork(store, session: AsyncSession) -> None:
    await _seed_world(store, session)
    await fork_from_anchor(
        store.session_factory,
        parent_branch_id=PARENT,
        fork_seq=6,
        fork_tick=6,
        new_branch_id=CHILD,
        preflush=_noop_preflush,
    )
    assert await session.get(Branch, CHILD) is not None
    assert (
        await session.execute(
            select(func.count()).select_from(Structure).where(Structure.branch_id == CHILD)
        )
    ).scalar_one() == 1
    # 一次转移给 from/to 两个 ref 各落一行（fold_material_balance 的双边语义）
    assert (
        await session.execute(
            select(func.count())
            .select_from(MaterialBalance)
            .where(MaterialBalance.branch_id == CHILD)
        )
    ).scalar_one() == 2
    assert (
        await session.execute(
            select(func.count()).select_from(NpcProfile).where(NpcProfile.branch_id == CHILD)
        )
    ).scalar_one() == 1
