"""T1 断言 5「历史不可销毁」的分叉口径钉子（M5-D2 第一刀，零迁移先行）。

DESIGN §16 六类不变量第 5 条的原始写法::

    before = world.all_event_seqs()
    world.load_anchor(anchor)
    assert before <= world.all_event_seqs()

**分叉下该写法恒真、不可证伪**（`docs/data/m5-fork-archive-preplan.md` §2.4 案 C /
§1.4）：`events` 的 seq 是**分支内**单调（PK `(branch_id, seq)`，见
`sim/core/persistence/store.py::SqlEventStore.append`），fork 后新分支的 seq 从 1
重新开始、与父分支 seq 空间重叠。于是「删掉父分支的 51-100、在新分支重写成 1-50」
这一真实破坏动作，在整数集合视角下 `before <= after` **照样成立**——断言没有鉴别力。

M5 裁决（`docs/arch/m5-rulings.md` §B 裁 2）：**不加 `global_seq`**，先落零迁移的
案 C 口径——比较对象从「seq 整数集合」改成「`(branch_id, seq)` 对集合」。复合主键
保证该对全局唯一且不可复用，故 `before <= after` 立刻变可证伪，**零 schema 改动**。

本文件锁死三件事：
1. 口径本身（对集合 + 跨分支读全部事件，而非只读当前分支）；
2. **可证伪性守卫**（二阶）：破坏动作下新口径必须红、旧口径必须绿——两者同时钉住，
   防止将来有人「为了让断言过」而把口径改回整数集合；
3. C6 的其余语义：分支标 `abandoned` 不删行、append 不改历史行、跨分支 seq 空间
   重叠不撞复合主键。

范围：fork 事务本身（建分支 + 克隆投影 + 标 abandoned）是后续件，本文件只用现存
原语（`SqlEventStore.append` + `branches` 行）**模拟** §12 的分叉步骤，只钉断言口径。
F3（向量召回分支隔离）不在本文件，见 `test_t1_m3_vec_governance.py::TestVecBranchIsolation`。
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.models import Branch, Event
from sim.core.persistence.store import SqlEventStore

BRANCH_PARENT = "main"
BRANCH_CHILD = "fork-a"


# ---------------------------------------------------------------------------
# 夹具：内存 SQLite（Base.metadata.create_all，与 test_persistence.py 同款）
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def store(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return SqlEventStore(sf)


@pytest.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# 断言口径（案 C 的 oracle）
# ---------------------------------------------------------------------------


async def world_event_keys(sf: async_sessionmaker[AsyncSession]) -> set[tuple[str, int]]:
    """全世界档的事件身份集合：``{(branch_id, seq)}``。

    口径要点（DESIGN §16 第 5 条 + 裁 2）：
    - **对**而非裸 seq：复合主键 `(branch_id, seq)` 保证全局唯一（fork 后两分支
      seq 空间重叠，裸 seq 会把两个不同事件混成一个）。
    - **跨全部分支**读，不是只读当前分支——「读档不破坏世界档」的对象是整个世界档
      （含全部已弃分支，§12）。
    """
    async with sf() as session:
        rows = (await session.execute(select(Event.branch_id, Event.seq))).all()
    return {(str(branch_id), int(seq)) for branch_id, seq in rows}


def naive_seq_set(keys: set[tuple[str, int]]) -> set[int]:
    """旧口径（DESIGN 原文的隐含实现）：只取 seq 整数——**恒真、不可证伪**。

    本文件不删它：它是对照组，用来证明新口径确有鉴别力（见
    ``test_falsifiability_guard_pair_keys_detects_delete_and_rewrite``）。
    """
    return {seq for _branch_id, seq in keys}


def _lod_event(tick: int, npc_id: str = "chenmo", *, to_lod: int = 2) -> dict:
    """一条**过生产校验**（``validate=True`` 默认）的合法事件行。

    用 ``npc.lod_change`` 而非合成 payload：本文件是 T1 不变量断言，走真实
    ``event_validation.validate_store_row`` 路径（M2-D3），不靠 ``validate=False``
    的低层旁路。
    """
    return {
        "tick": tick,
        "event_type": "npc.lod_change",
        "actor_id": npc_id,
        "target_id": None,
        "parent_seq": None,
        "payload": {
            "npc_id": npc_id,
            "from_lod": 1,
            "to_lod": to_lod,
            "reason": "enter_range",
        },
        "witnesses": [],
        "entropy_ref": None,
    }


async def _add_branch(sf: async_sessionmaker[AsyncSession], branch_id: str) -> None:
    async with sf() as session:
        session.add(Branch(id=branch_id, status="active"))
        await session.commit()


async def _mark_abandoned(sf: async_sessionmaker[AsyncSession], branch_id: str) -> None:
    async with sf() as session:
        await session.execute(
            update(Branch).where(Branch.id == branch_id).values(status="abandoned")
        )
        await session.commit()


# ---------------------------------------------------------------------------
# 契约 1：C6 正向——分叉只增不减
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestHistoryPreservedUnderFork:
    """T1 第 5 条：读档=分叉后，先前存在的事件身份一个都不能少。"""

    async def test_global_key_set_is_superset_after_fork(
        self,
        store: SqlEventStore,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """before ⊆ after（对集合口径）：父分支事件在读档后原封不动。

        模拟 §12 读档流程的「可观测部分」：父分支 5 条事件 → 建子分支 → 子分支
        追加 3 条 → 标父分支 abandoned。fork 事务（克隆投影）属后续件，不在本刀。
        """
        await _add_branch(session_factory, BRANCH_PARENT)
        await store.append(BRANCH_PARENT, [_lod_event(tick=i) for i in range(5)])
        before = await world_event_keys(session_factory)
        assert before == {(BRANCH_PARENT, i) for i in range(1, 6)}

        # 读档 = 分叉：新分支另起 seq（从 1 开始，与父分支空间重叠）。
        await _add_branch(session_factory, BRANCH_CHILD)
        await store.append(BRANCH_CHILD, [_lod_event(tick=5 + i) for i in range(3)])
        await _mark_abandoned(session_factory, BRANCH_PARENT)

        after = await world_event_keys(session_factory)
        assert before <= after, "读档后世界档事件身份减少（历史被销毁，T1 第 5 条）"
        assert len(after) == 8

    async def test_abandoned_branch_events_retained(
        self,
        store: SqlEventStore,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """§12：旧分支标 abandoned，**不删其事件**（废弃 ≠ 销毁）。"""
        await _add_branch(session_factory, BRANCH_PARENT)
        await store.append(BRANCH_PARENT, [_lod_event(tick=i) for i in range(3)])
        before = await world_event_keys(session_factory)

        await _add_branch(session_factory, BRANCH_CHILD)
        await store.append(BRANCH_CHILD, [_lod_event(tick=99)])
        await _mark_abandoned(session_factory, BRANCH_PARENT)

        async with session_factory() as session:
            status = (
                await session.execute(select(Branch.status).where(Branch.id == BRANCH_PARENT))
            ).scalar_one()
        assert status == "abandoned"
        assert (await world_event_keys(session_factory)) >= before

    async def test_append_does_not_mutate_existing_rows(
        self,
        store: SqlEventStore,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """append-only：后续 append（含另一分支）不改历史行的任何字段。"""
        await _add_branch(session_factory, BRANCH_PARENT)
        await store.append(BRANCH_PARENT, [_lod_event(tick=7), _lod_event(tick=8)])

        async with session_factory() as session:
            snapshot = [
                (r.branch_id, r.seq, r.tick, r.event_type, r.actor_id, r.payload)
                for r in (await session.execute(select(Event))).scalars()
            ]
        assert len(snapshot) == 2

        await _add_branch(session_factory, BRANCH_CHILD)
        await store.append(BRANCH_CHILD, [_lod_event(tick=9)] * 3)
        await store.append(BRANCH_PARENT, [_lod_event(tick=10)])

        async with session_factory() as session:
            after = [
                (r.branch_id, r.seq, r.tick, r.event_type, r.actor_id, r.payload)
                for r in (
                    await session.execute(select(Event).where(Event.branch_id == BRANCH_PARENT))
                ).scalars()
            ]
        assert after[:2] == snapshot, "后续 append 改写了历史行（违反 append-only）"


# ---------------------------------------------------------------------------
# 契约 2：可证伪性守卫（二阶）——新口径有鉴别力，旧口径没有
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestHistoryInvariantFalsifiability:
    """防「红灯被错误实现满足」：口径本身必须能抓到真实破坏动作。"""

    async def test_falsifiability_guard_pair_keys_detects_delete_and_rewrite(
        self,
        store: SqlEventStore,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """删父分支尾部 + 子分支补足同量事件：新口径红、旧口径绿（同时钉住）。

        这是本刀存在的**唯一理由**：若只钉正向（before ⊆ after），一个把比较对象
        换回裸 seq 的实现同样能全绿。

        破坏动作的形状很关键：**子分支必须补到不少于被删条数**。因为新分支的 seq
        从 1 重新分配，只要它继续推进（分叉后世界当然继续跑），同样的 seq 整数就
        会被重新占满——此时删掉父分支的事件行在裸 seq 视角下**完全不可见**。
        换言之旧口径的鉴别力是偶然的（子分支还没跑够时也许能抓到），且随分叉推进
        必然消失；只有 `(branch_id, seq)` 对口径是稳定的。
        """
        await _add_branch(session_factory, BRANCH_PARENT)
        await store.append(BRANCH_PARENT, [_lod_event(tick=i) for i in range(5)])
        before = await world_event_keys(session_factory)

        await _add_branch(session_factory, BRANCH_CHILD)
        # 破坏动作：删父分支最后 2 条（世界档被销毁），子分支补 5 条（同量重占 seq）。
        async with session_factory() as session:
            await session.execute(
                delete(Event).where(Event.branch_id == BRANCH_PARENT, Event.seq.in_([4, 5]))
            )
            await session.commit()
        await store.append(BRANCH_CHILD, [_lod_event(tick=50 + i) for i in range(5)])
        after = await world_event_keys(session_factory)

        # 新口径（对集合）：抓到了。
        assert not (before <= after), "对集合口径未抓到「删父补子」——口径已退化为恒真"
        assert (BRANCH_PARENT, 4) in before
        assert (BRANCH_PARENT, 4) not in after
        assert len(after) == 8  # 父 3 + 子 5

        # 旧口径（裸 seq）：同样的破坏动作它完全看不见——这正是要换口径的原因。
        assert naive_seq_set(before) == naive_seq_set(after) == {1, 2, 3, 4, 5}
        assert naive_seq_set(before) <= naive_seq_set(after), (
            "对照组前提被破坏：裸 seq 口径本应对该破坏动作恒真（否则对照组无意义）"
        )

    async def test_same_seq_in_two_branches_are_distinct_keys(
        self,
        store: SqlEventStore,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """跨分支同 seq 是**两个不同事件**：对集合 6 个键，裸 seq 集合塌成 3 个。"""
        await _add_branch(session_factory, BRANCH_PARENT)
        await _add_branch(session_factory, BRANCH_CHILD)
        await store.append(BRANCH_PARENT, [_lod_event(tick=i) for i in range(3)])
        await store.append(BRANCH_CHILD, [_lod_event(tick=i) for i in range(3)])

        keys = await world_event_keys(session_factory)
        assert keys == {
            (BRANCH_PARENT, 1),
            (BRANCH_PARENT, 2),
            (BRANCH_PARENT, 3),
            (BRANCH_CHILD, 1),
            (BRANCH_CHILD, 2),
            (BRANCH_CHILD, 3),
        }
        assert (BRANCH_PARENT, 1) != (BRANCH_CHILD, 1)
        # 对照：裸 seq 口径把 6 个事件看成 3 个（分叉后每次读档都发生）。
        assert len(naive_seq_set(keys)) == 3

    async def test_seq_ranges_overlap_without_collision(
        self,
        store: SqlEventStore,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """seq 分支内各自单调、跨分支可重叠：复合主键不撞，后续 append 各自续号。"""
        await _add_branch(session_factory, BRANCH_PARENT)
        await _add_branch(session_factory, BRANCH_CHILD)
        await store.append(BRANCH_PARENT, [_lod_event(tick=i) for i in range(3)])
        await store.append(BRANCH_CHILD, [_lod_event(tick=i) for i in range(3)])

        await store.append(BRANCH_PARENT, [_lod_event(tick=30)])
        await store.append(BRANCH_CHILD, [_lod_event(tick=31)])

        keys = await world_event_keys(session_factory)
        assert len(keys) == 8
        assert (BRANCH_PARENT, 4) in keys and (BRANCH_CHILD, 4) in keys
        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(Event.branch_id, func.max(Event.seq)).group_by(Event.branch_id)
                )
            ).all()
        max_seq_by_branch = {str(branch_id): int(max_seq) for branch_id, max_seq in rows}
        assert max_seq_by_branch == {BRANCH_PARENT: 4, BRANCH_CHILD: 4}
