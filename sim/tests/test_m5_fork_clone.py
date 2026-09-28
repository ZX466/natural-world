"""M5-D3-b T1 钉子 — 读档 = 分叉的事务与克隆（裁 6 (c) / 裁 10 (i) + R-1 / R-2）

DESIGN §12：读档 = 分叉——定位 anchor 的 `(branch_id, seq)` → 建新分支 → 旧分支标
abandoned → 世界继续；**不删除/回退原世界线**（§19 禁止事项，C6）。

本文件钉住的事务契约（`sim/core/persistence/fork.py`）：

1. **八张表一次事务**（裁 6 (c)：async 引擎直写，冷路径字节复制，不过 store 类、
   不触 S1）：6 张有界表换 `branch_id` 值 + 2 张语料表按分叉点截断克隆；
2. **P1 前置条件做成动作**（不是断言）：`preflush` 钩子必填——fork 第一步先强制
   flush 父分支的 in-flight 批次，投影不追平就没资格分叉；
3. **裁 10 (i)：`entry_id` 重映射**（`UNIQUE(entry_id)` 是**全局**唯一，同 id 跨
   分支共存被索引挡住）；重映射按 `uuid5(父entry_id, 新分支)` **确定性**派生——
   随机 uuid 会让「同一 anchor 载入两次」不可逐位一致（T2）；
4. **R-2（codex S1 复核红线）**：`superseded_by` 在子分支**零悬空**——重映射到子行，
   或（替换者写在分叉点之后、本就不该克隆）**置 NULL**（那正是该分支时间线里的
   「还没被取代」状态，置 NULL 才对；保留指针=悬空，悬空=治理污染）；
5. **R-1**：clone 后记忆 `content`（及其余文本列）**逐字节不变**；vec 行按字节拷贝
   （V4 vec 表为准，重新 embed = 红线禁）；
6. **分叉点只在父分支头部**（见下），其余一律 fail-closed。

**为什么只支持头部（重要缺口，回执已上报）**：投影表的当前值 == 分叉点状态，
**仅当父分支在分叉点之后没有再推进**。历史点分叉（如「回到昨天的存档」）时，
`npc_memories`/`knowledge` 的**治理列**（`invalidated`/`superseded_by`）与
`relationships` 的累计值都已被父分支的「未来」改写，而这三张表**没有事件源**
（F2，`m5-fork-archive-preplan.md` §3.2）⇒ 历史状态**不可重建**。要支持历史点，
需要裁 7 的 `*.written` 事件、或 anchor 世界态物化/快照展开路径（M5 均未落）。
本轮按 fail-closed 处理，绝不用「近似重置治理列」糊过去。
"""

from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.fork import (
    ForkError,
    derive_child_entry_id,
    fork_from_anchor,
)
from sim.core.persistence.models import (
    Branch,
    Event,
    Knowledge,
    MaterialBalance,
    MatterState,
    NpcHealth,
    NpcMemory,
    NpcProfile,
    Relationship,
    Structure,
)
from sim.core.persistence.store import InactiveBranchError, SqlEventStore
from sim.core.persistence.vector import VEC_TABLE, create_memory_vec_table

PARENT = "main"
CHILD = "fork-b"
VEC_DIM = 8


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine(tmp_path: Path):
    """内存引擎（多数用例）；vec 用例另用文件库以便同步连接共享。"""
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


def _profile(npc_id: str, *, branch_id: str = PARENT, lod: int = 1) -> NpcProfile:
    return NpcProfile(id=npc_id, branch_id=branch_id, name=f"NPC-{npc_id}", lod=lod)


def _lod_event(tick: int, npc_id: str = "chenmo") -> dict:
    return {
        "tick": tick,
        "event_type": "npc.lod_change",
        "actor_id": npc_id,
        "target_id": None,
        "parent_seq": None,
        "payload": {"npc_id": npc_id, "from_lod": 1, "to_lod": 2, "reason": "enter_range"},
        "witnesses": [],
        "entropy_ref": None,
    }


def _memory(
    entry_id: str,
    *,
    branch_id: str = PARENT,
    content: str = "内容",
    event_seq: int | None = 1,
    created_at_tick: int = 0,
    superseded_by: str | None = None,
) -> NpcMemory:
    return NpcMemory(
        entry_id=entry_id,
        npc_id="chenmo",
        branch_id=branch_id,
        content=content,
        source="event",
        importance=0.5,
        created_at_tick=created_at_tick,
        event_seq=event_seq,
        superseded_by=superseded_by,
    )


def _blob(vals: list[float]) -> bytes:
    return struct.pack(f"{len(vals)}f", *vals)


async def _seed_bounded(session: AsyncSession, *, branch_id: str = PARENT) -> None:
    """六张有界表各一行（形态对齐生产列）。"""
    session.add_all(
        [
            _profile("chenmo", branch_id=branch_id),
            NpcHealth(npc_id="chenmo", branch_id=branch_id, category="disease", label="旧伤"),
            Relationship(owner_id="chenmo", other_id="xiaoman", trust=0.5, branch_id=branch_id),
            MatterState(subject_id="hut-1", branch_id=branch_id, integrity=0.8),
            Structure(
                branch_id=branch_id,
                structure_id="hut-1",
                tiles=json.dumps([[0, 0]]),
                kind="wood_hut",
                material="wood",
            ),
            MaterialBalance(branch_id=branch_id, ref="hut-1", material_id="wood", quantity=3.0),
        ]
    )
    await session.commit()


# ---------------------------------------------------------------------------
# 1. 事务形状：建线 + 八表克隆 + 旧分支封存
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestForkTransaction:
    async def test_fork_clones_eight_tables_in_one_go(self, store, session: AsyncSession) -> None:
        await store.append(PARENT, [_lod_event(tick=1)])
        await _seed_bounded(session)
        session.add_all([_memory("e-1"), _memory("e-2", event_seq=1, created_at_tick=0)])
        session.add(
            Knowledge(
                holder_id="chenmo",
                fact="他知道井在哪",
                confidence=0.6,
                source="witnessed",
                learned_at=0,
                branch_id=PARENT,
                evidence_seq=1,
            )
        )
        await session.commit()

        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        assert result.new_branch_id == CHILD

        # 六张有界表 + 两张语料表：子分支各有行，父分支行**仍在**（克隆非搬移）。
        for model, child_n, parent_n in (
            (NpcProfile, 1, 1),
            (NpcHealth, 1, 1),
            (Relationship, 1, 1),
            (MatterState, 1, 1),
            (Structure, 1, 1),
            (MaterialBalance, 1, 1),
            (NpcMemory, 2, 2),
            (Knowledge, 1, 1),
        ):
            counts: dict[str, int] = {}
            for branch in (PARENT, CHILD):
                counts[branch] = (
                    await session.execute(
                        select(func.count()).select_from(model).where(model.branch_id == branch)
                    )
                ).scalar_one()
            assert counts[CHILD] == child_n, f"{model.__tablename__} 子分支克隆行数不对"
            assert counts[PARENT] == parent_n, f"{model.__tablename__} 父分支行被搬走了"

    async def test_fork_abandons_parent_and_activates_child(
        self, store, session: AsyncSession
    ) -> None:
        await store.append(PARENT, [_lod_event(tick=1)])
        await _seed_bounded(session)

        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        assert result.forked_from_branch == PARENT
        assert result.forked_from_seq == 1

        session.expire_all()
        child = await session.get(Branch, CHILD)
        parent = await session.get(Branch, PARENT)
        assert child is not None and child.status == "active"
        assert child.forked_from_branch == PARENT and child.forked_from_seq == 1
        assert parent is not None and parent.status == "abandoned"
        assert parent.abandoned_at is not None

    async def test_fork_does_not_touch_events_or_snapshot_rows(
        self, store, session: AsyncSession
    ) -> None:
        """事件不克隆、不删（世界档 append-only，C6）：分叉只增。"""
        await store.append(PARENT, [_lod_event(tick=1), _lod_event(tick=2)])
        before = (await session.execute(select(Event.branch_id, Event.seq))).all()

        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=2,
            fork_tick=2,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        after = (await session.execute(select(Event.branch_id, Event.seq))).all()
        assert sorted(after) == sorted(before), "分叉改动了 events 行（C6 红线）"
        assert len(after) == 2

    async def test_preflush_runs_before_clone(self, store, session: AsyncSession) -> None:
        """P1 做成动作：`preflush` 必填且在克隆前跑（投影不追平就没资格分叉）。"""
        calls: list[str] = []

        async def preflush() -> None:
            calls.append("flush")
            # 模拟 driver 冲掉 in-flight 批次：克隆必须看见冲完后的投影
            session.add(MatterState(subject_id="late", branch_id=PARENT, integrity=0.4))
            await session.commit()

        await store.append(PARENT, [_lod_event(tick=1)])
        await _seed_bounded(session)

        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=preflush,
        )
        assert calls == ["flush"]
        child_rows = (
            (await session.execute(select(MatterState).where(MatterState.branch_id == CHILD)))
            .scalars()
            .all()
        )
        assert {r.subject_id for r in child_rows} == {"hut-1", "late"}


# ---------------------------------------------------------------------------
# 2. 截断：分叉点之后的语料不得进新时间线
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestForkCorpusTruncation:
    async def test_rows_after_fork_point_excluded(self, store, session: AsyncSession) -> None:
        await store.append(PARENT, [_lod_event(tick=1)])
        await _seed_bounded(session)
        session.add_all(
            [
                _memory("e-in", event_seq=1, created_at_tick=0),
                # event_seq NULL（推理转述）但写在下界之后 → 分叉点之后 → 排除
                _memory("e-late", event_seq=None, created_at_tick=9),
            ]
        )
        session.add_all(
            [
                Knowledge(
                    holder_id="chenmo",
                    fact="分叉点前学的",
                    confidence=0.5,
                    source="inferred",
                    learned_at=0,
                    branch_id=PARENT,
                ),
                Knowledge(
                    holder_id="chenmo",
                    fact="分叉点后学的",
                    confidence=0.5,
                    source="inferred",
                    learned_at=9,
                    branch_id=PARENT,
                ),
            ]
        )
        await session.commit()

        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        session.expire_all()

        child_mem = (
            (await session.execute(select(NpcMemory).where(NpcMemory.branch_id == CHILD)))
            .scalars()
            .all()
        )
        assert len(child_mem) == 1, "分叉点之后写入的记忆进了新时间线"
        child_know = (
            (await session.execute(select(Knowledge).where(Knowledge.branch_id == CHILD)))
            .scalars()
            .all()
        )
        assert [k.fact for k in child_know] == ["分叉点前学的"]


# ---------------------------------------------------------------------------
# 3. 指针重映射（裁 10 (i)）+ R-2
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestForkPointerRemap:
    async def test_entry_ids_remapped_and_deterministic(self, store, session: AsyncSession) -> None:
        """裁 10 (i)：`entry_id` 必须重映射，且映射是 (父 entry, 子分支) 的**纯函数**。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        session.add(_memory("e-1"))
        await session.commit()

        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        assert "e-1" in result.entry_id_map
        child_id = result.entry_id_map["e-1"]
        assert child_id != "e-1", "裁 10 (i)：entry_id 必须重映射（UNIQUE 是全局的）"
        # 纯函数 + 分支作用域：同输入同输出（重算可复现，T2），跨分支不撞（T2 可比字段集）
        assert derive_child_entry_id("e-1", CHILD) == child_id
        assert derive_child_entry_id("e-1", CHILD) == derive_child_entry_id("e-1", CHILD)
        assert derive_child_entry_id("e-1", "fork-c") != child_id

    async def test_fork_into_existing_branch_rejected(self, store, session: AsyncSession) -> None:
        """分支 id 不可复用（否则 T2 的「重算同一分支」无从谈起）。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        await store.append(CHILD, [_lod_event(tick=2)])
        with pytest.raises(ForkError, match="已存在"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=1,
                fork_tick=1,
                new_branch_id=CHILD,
                preflush=_noop_preflush,
            )

    async def test_R2_superseded_by_never_dangles(self, store, session: AsyncSession) -> None:
        """R-2：子分支的 `superseded_by` 必须落在子分支内（零跨分支悬空）。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        session.add_all(
            [
                _memory("e-old", superseded_by="e-new"),
                _memory("e-new"),
            ]
        )
        await session.commit()

        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        assert result.superseded_rewritten == 1

        session.expire_all()
        child_mem = {
            r.entry_id: r
            for r in (
                (await session.execute(select(NpcMemory).where(NpcMemory.branch_id == CHILD)))
                .scalars()
                .all()
            )
        }
        old = next(r for r in child_mem.values() if r.event_seq == 1 and r.superseded_by)
        new_id = result.entry_id_map["e-new"]
        assert old.superseded_by == new_id, "superseded_by 未重映射到子分支行"
        assert new_id in child_mem
        # 父分支行不被改写
        parent_old = (
            await session.execute(select(NpcMemory).where(NpcMemory.entry_id == "e-old"))
        ).scalar_one()
        assert parent_old.superseded_by == "e-new"

    async def test_future_replacement_pointer_becomes_null(
        self, store, session: AsyncSession
    ) -> None:
        """替换者写在分叉点之后 → 不克隆；旧记忆的指针置 NULL（该分支「还没被取代」）。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        session.add_all(
            [
                _memory("e-old", event_seq=1, created_at_tick=0, superseded_by="e-future"),
                _memory("e-future", event_seq=None, created_at_tick=9),
            ]
        )
        await session.commit()

        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        assert result.superseded_cleared == 1
        session.expire_all()
        child = (
            (await session.execute(select(NpcMemory).where(NpcMemory.branch_id == CHILD)))
            .scalars()
            .all()
        )
        assert [r.entry_id for r in child] == [result.entry_id_map["e-old"]]
        assert child[0].superseded_by is None, "指向未克隆行的指针未清空（R-2 悬空）"

    async def test_knowledge_chain_and_source_memory_remapped(
        self, store, session: AsyncSession
    ) -> None:
        await store.append(PARENT, [_lod_event(tick=1)])
        session.add_all(
            [
                _memory("e-1"),
                Knowledge(
                    holder_id="chenmo",
                    fact="源头",
                    confidence=0.6,
                    source="witnessed",
                    learned_at=0,
                    branch_id=PARENT,
                    evidence_seq=1,
                ),
            ]
        )
        await session.commit()
        parent_src = (
            await session.execute(select(Knowledge).where(Knowledge.holder_id == "chenmo"))
        ).scalar_one()
        parent_src_id = int(parent_src.id)
        # told 派生：teller 指源头行，源记忆指 e-1
        session.add(
            Knowledge(
                holder_id="xiaoman",
                fact="他转述的",
                confidence=0.4,
                source="told",
                learned_at=0,
                branch_id=PARENT,
                source_knowledge_id=parent_src.id,
                source_memory="e-1",
            )
        )
        await session.commit()

        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        session.expire_all()
        child = {
            k.holder_id: k
            for k in (
                (await session.execute(select(Knowledge).where(Knowledge.branch_id == CHILD)))
                .scalars()
                .all()
            )
        }
        told = child["xiaoman"]
        assert told.source_memory == result.entry_id_map["e-1"]
        assert told.source_knowledge_id in result.knowledge_id_map.values()
        assert told.source_knowledge_id != parent_src_id

    async def test_evidence_branch_rewritten_to_parent(self, store, session: AsyncSession) -> None:
        """0008-d 的用处：克隆后证据事件住在父分支 → `evidence_branch_id` 必须改写。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        session.add(
            Knowledge(
                holder_id="chenmo",
                fact="他手上有伤",
                confidence=0.7,
                source="witnessed",
                learned_at=0,
                branch_id=PARENT,
                evidence_seq=1,
                evidence_branch_id=None,  # 父分支视角：证据在本分支
            )
        )
        await session.commit()

        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        session.expire_all()
        child = (
            await session.execute(select(Knowledge).where(Knowledge.branch_id == CHILD))
        ).scalar_one()
        assert child.evidence_branch_id == PARENT, "证据分支未改写 → 子分支内悬空"
        assert child.evidence_seq == 1


# ---------------------------------------------------------------------------
# 4. R-1：逐字节不变（记忆文本 + vec 向量）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestR1ByteExactClone:
    async def test_memory_content_bytes_identical(self, store, session: AsyncSession) -> None:
        """R-1：克隆是**字节复制**——不重写、不清洗、不截断文本。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        tricky = [
            "第一行\n第二行\r\n制表\t",
            '引号"与反斜杠\\与JSON {"k": [1, 2]}',
            "全角「」（缓一缓）——省略号…",
            " 前后空格  ",
            "重复重复重复" * 50,
        ]
        for i, text in enumerate(tricky):
            session.add(_memory(f"e-{i}", content=text))
        await session.commit()

        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        session.expire_all()
        parent_rows = {
            r.entry_id: r
            for r in (await session.execute(select(NpcMemory))).scalars().all()
            if r.branch_id == PARENT
        }
        child_rows = {
            r.entry_id: r
            for r in (await session.execute(select(NpcMemory))).scalars().all()
            if r.branch_id == CHILD
        }
        assert len(child_rows) == len(tricky)
        for old_id, text in zip([f"e-{i}" for i in range(len(tricky))], tricky, strict=True):
            child = child_rows[result.entry_id_map[old_id]]
            assert child.content.encode("utf-8") == text.encode("utf-8")
            assert child.content == parent_rows[old_id].content

    async def test_vec_rows_copied_bytewise_without_llm(self, tmp_path: Path) -> None:
        """R-1 向量面：vec 行按字节重键拷贝（V4 vec 表为准，**零 LLM 调用**）。"""
        db = tmp_path / "fork_vec.db"
        eng = create_async_engine(f"sqlite+aiosqlite:///{db}", echo=False)
        await init_database(eng)
        sf = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        store = SqlEventStore(sf)
        vec_conn = sqlite3.connect(str(db))
        try:
            create_memory_vec_table(vec_conn, dim=VEC_DIM)
            await store.append(PARENT, [_lod_event(tick=1)])
            async with sf() as session:
                session.add(_memory("e-1"))
                session.add(_memory("e-2"))
                await session.commit()
                parent_ids = [
                    r.id
                    for r in (
                        await session.execute(
                            select(NpcMemory).where(NpcMemory.branch_id == PARENT)
                        )
                    )
                    .scalars()
                    .all()
                ]
            vectors = {
                rid: _blob([float(rid), 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]) for rid in parent_ids
            }
            for rid, blob in vectors.items():
                vec_conn.execute(
                    f"INSERT INTO {VEC_TABLE}(rowid, embedding) VALUES (?, ?)", (rid, blob)
                )
            vec_conn.commit()

            result = await fork_from_anchor(
                sf,
                parent_branch_id=PARENT,
                fork_seq=1,
                fork_tick=1,
                new_branch_id=CHILD,
                preflush=_noop_preflush,
                vec_conn=vec_conn,
            )
            assert result.vec_rows_copied == 2, "vec 行未按字节拷贝（R-1）"

            async with sf() as session:
                child_ids = [
                    r.id
                    for r in (
                        await session.execute(select(NpcMemory).where(NpcMemory.branch_id == CHILD))
                    )
                    .scalars()
                    .all()
                ]
            copied = dict(vec_conn.execute(f"SELECT rowid, embedding FROM {VEC_TABLE}").fetchall())
            assert set(child_ids) <= set(copied), "子分支行没有对应的 vec 行"
            for old_id, new_id in zip(parent_ids, child_ids, strict=True):
                assert copied[new_id] == vectors[old_id], "向量字节不一致（R-1）"
        finally:
            vec_conn.close()
            await eng.dispose()

    async def test_missing_vec_conn_reports_pending_not_silent(
        self, store, session: AsyncSession
    ) -> None:
        """未给 vec 连接 → 结果显式记 `vec_pending`（降级不泄漏），不静默。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        session.add(_memory("e-1"))
        await session.commit()

        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        assert result.vec_pending is True
        assert result.vec_rows_copied == 0
        assert any("vec" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 5. fail-closed：分叉点、原子性、完整性
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestForkFailClosed:
    async def test_non_head_fork_point_rejected(self, store, session: AsyncSession) -> None:
        """历史点分叉 fail-closed（投影当前值 ≠ 分叉点状态；语料/关系无事件源不可重建）。"""
        await store.append(PARENT, [_lod_event(tick=1), _lod_event(tick=2), _lod_event(tick=3)])
        await _seed_bounded(session)

        with pytest.raises(ForkError, match="头部"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=1,
                fork_tick=1,
                new_branch_id=CHILD,
                preflush=_noop_preflush,
            )
        assert await session.get(Branch, CHILD) is None, "拒绝后仍建了分支（半写）"

    async def test_fork_point_beyond_head_rejected(self, store, session: AsyncSession) -> None:
        await store.append(PARENT, [_lod_event(tick=1)])
        with pytest.raises(ForkError):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=9,
                fork_tick=9,
                new_branch_id=CHILD,
                preflush=_noop_preflush,
            )

    async def test_unknown_parent_branch_rejected(self, store, session: AsyncSession) -> None:
        with pytest.raises(ForkError, match="分支"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id="ghost",
                fork_seq=0,
                fork_tick=0,
                new_branch_id=CHILD,
                preflush=_noop_preflush,
            )

    async def test_dangling_knowledge_source_rolls_back_whole_fork(
        self, store, session: AsyncSession
    ) -> None:
        """指针悬空 = 完整性违规 → 抛错**且整批回滚**（无半写：分支/克隆全无）。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        await _seed_bounded(session)
        session.add_all(
            [
                _memory("e-1"),
                Knowledge(
                    holder_id="xiaoman",
                    fact="teller 不存在",
                    confidence=0.4,
                    source="told",
                    learned_at=0,
                    branch_id=PARENT,
                    source_knowledge_id=9999,
                ),
            ]
        )
        await session.commit()

        with pytest.raises(ForkError, match="source_knowledge_id"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=1,
                fork_tick=1,
                new_branch_id=CHILD,
                preflush=_noop_preflush,
            )
        assert await session.get(Branch, CHILD) is None, "失败后仍留了子分支行（半写）"
        assert (
            await session.execute(select(NpcProfile).where(NpcProfile.branch_id == CHILD))
        ).scalars().all() == []
        parent_row = await session.get(Branch, PARENT)
        assert parent_row is not None
        assert parent_row.status == "active", "父分支被误封"


# ---------------------------------------------------------------------------
# 6. 裁 5：append 校验 status='active'（防 fork 后误写父分支）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestAppendActiveBranchOnly:
    async def test_append_to_abandoned_branch_rejected(self, store, session: AsyncSession) -> None:
        await store.append(PARENT, [_lod_event(tick=1)])
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        with pytest.raises(InactiveBranchError):
            await store.append(PARENT, [_lod_event(tick=2)])

    async def test_append_auto_provisions_missing_branch(
        self, store, session: AsyncSession
    ) -> None:
        """分支行不存在 → 按需开线（世界从第一条事件长出来），存在但非 active 才拒。"""
        await store.append("brand-new", [_lod_event(tick=1)])
        row = await session.get(Branch, "brand-new")
        assert row is not None and row.status == "active"

    async def test_parent_history_intact_after_rejected_append(
        self, store, session: AsyncSession
    ) -> None:
        """被拒的 append 不得留下半行（C6）。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        before = (await session.execute(select(Event.branch_id, Event.seq))).all()
        with pytest.raises(InactiveBranchError):
            await store.append(PARENT, [_lod_event(tick=2)])
        after = (await session.execute(select(Event.branch_id, Event.seq))).all()
        assert sorted(after) == sorted(before)

    async def test_seq_not_consumed_by_rejected_append(self, store, session: AsyncSession) -> None:
        """被拒的 append 不得吃掉 seq 号（否则子分支续号错位）。"""
        await store.append(PARENT, [_lod_event(tick=1)])
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        with pytest.raises(InactiveBranchError):
            await store.append(PARENT, [_lod_event(tick=2)])
        max_seq = (
            await session.execute(select(func.max(Event.seq)).where(Event.branch_id == PARENT))
        ).scalar()
        assert max_seq == 1
