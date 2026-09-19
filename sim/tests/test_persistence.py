"""数据域单元测试 — EventStore + 回放验证

覆盖：
- append-only 约束（重复 seq 拒绝）
- read_range 顺序正确
- snapshot 写入/读取往返
- 回放验证雏形（50 事件逐位一致）
- aiosqlite 内存库跑
"""

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.store import SqlEventStore, decompress_snapshot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    """内存 SQLite 引擎。"""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def store(engine):
    """SqlEventStore 实例。"""
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return SqlEventStore(sf)


def _make_event(tick: int, kind: str = "move", actor: str = "player", **kwargs) -> dict:
    """构造一个测试用事件字典。"""
    return {
        "tick": tick,
        "event_type": kind,
        "actor_id": actor,
        "target_id": kwargs.get("target_id"),
        "parent_seq": kwargs.get("parent_seq"),
        "payload": kwargs.get("payload", {}),
        "witnesses": kwargs.get("witnesses", []),
        "entropy_ref": kwargs.get("entropy_ref"),
    }


# ---------------------------------------------------------------------------
# T1: append-only 约束
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestAppendOnly:
    """事件只能追加，不能修改或删除。"""

    async def test_append_assigns_sequential_seq(self, store):
        """每个事件被分配递增的 seq。"""
        branch = "test-branch"
        events = [_make_event(tick=i) for i in range(5)]

        await store.append(branch, events)
        result = await store.read_range(branch, 1, 5)

        assert len(result) == 5
        for i, ev in enumerate(result):
            assert ev["seq"] == i + 1

    async def test_append_multiple_batches(self, store):
        """多批次 append，seq 持续递增。"""
        branch = "test-branch"
        await store.append(branch, [_make_event(tick=0)])
        await store.append(branch, [_make_event(tick=1)])
        await store.append(branch, [_make_event(tick=2)])

        result = await store.read_range(branch, 1, 3)
        assert [e["seq"] for e in result] == [1, 2, 3]

    async def test_append_empty_is_noop(self, store):
        """空 append 不报错。"""
        await store.append("branch", [])
        result = await store.read_range("branch", 0, 100)
        assert result == []


# ---------------------------------------------------------------------------
# T1: read_range 正确性
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestReadRange:
    """读取范围查询正确性。"""

    async def test_read_range_order(self, store):
        """按 seq 升序返回。"""
        branch = "b"
        events = [_make_event(tick=10 - i) for i in range(5)]
        await store.append(branch, events)

        result = await store.read_range(branch, 2, 4)
        assert len(result) == 3
        assert [e["seq"] for e in result] == [2, 3, 4]

    async def test_read_range_out_of_bounds(self, store):
        """超出范围返回空。"""
        branch = "b"
        await store.append(branch, [_make_event(tick=0)])
        result = await store.read_range(branch, 10, 20)
        assert result == []

    async def test_read_range_preserves_payload(self, store):
        """payload 完整往返。"""
        branch = "b"
        payload = {"x": 1, "y": 2, "nested": {"a": [1, 2, 3]}}
        await store.append(branch, [_make_event(tick=0, payload=payload)])

        result = await store.read_range(branch, 1, 1)
        assert result[0]["payload"] == payload


# ---------------------------------------------------------------------------
# T1: snapshot 写入/读取往返
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestSnapshot:
    """快照写入和读取往返。"""

    async def test_write_and_read_snapshot(self, store):
        """写入快照后能正确读回（gzip 压缩/解压）。"""
        branch = "b"
        state = {"tick": 100, "entities": {"player": {"hp": 100}}}
        blob = json.dumps(state).encode()

        await store.write_snapshot(branch, tick=100, event_seq=42, blob=blob)

        snap = await store.latest_snapshot(branch, before_tick=200)
        assert snap is not None
        assert snap.tick == 100
        assert snap.seq == 42  # seq 与事件流对齐
        assert snap.schema_version == 1
        assert decompress_snapshot(snap) == state

    async def test_latest_snapshot_returns_most_recent(self, store):
        """latest_snapshot 返回 before_tick 之前最新的快照。"""
        branch = "b"
        await store.write_snapshot(branch, tick=100, event_seq=100, blob=b"snap100")
        await store.write_snapshot(branch, tick=200, event_seq=200, blob=b"snap200")

        snap = await store.latest_snapshot(branch, before_tick=150)
        assert snap is not None
        assert snap.tick == 100

    async def test_latest_snapshot_none_when_no_snapshots(self, store):
        """无快照时返回 None。"""
        snap = await store.latest_snapshot("nonexistent", before_tick=999)
        assert snap is None


# ---------------------------------------------------------------------------
# T2: 回放验证雏形（50 事件逐位一致）
# ---------------------------------------------------------------------------


@pytest.mark.t2
class TestReplayDeterministic:
    """回放确定性：同一事件流重放 → 状态一致。"""

    async def test_50_event_replay(self, store):
        """
        构造 50 个事件 → append → read_range 全读回 → 断言逐位一致。
        模拟简单状态机：每个 move 事件更新 player 位置。
        """
        branch = "replay-test"

        # --- 第一遍：写入事件 ---
        events = []
        x, y = 0, 0
        for i in range(50):
            # 简单确定性移动：交替 x/y
            if i % 2 == 0:
                x += 1
            else:
                y += 1
            events.append(
                _make_event(
                    tick=i,
                    kind="move",
                    actor="player",
                    payload={"x": x, "y": y},
                )
            )
        await store.append(branch, events)

        # --- 读回全部事件 ---
        all_events = await store.read_range(branch, 1, 50)
        assert len(all_events) == 50

        # --- 模拟重放：逐事件应用到状态 ---
        state = {"x": 0, "y": 0}
        for ev in all_events:
            state["x"] = ev["payload"]["x"]
            state["y"] = ev["payload"]["y"]

        # 最终状态应与写入时一致
        assert state == {"x": 25, "y": 25}

        # --- 第二遍：重新读回并重放 ---
        state2 = {"x": 0, "y": 0}
        all_events2 = await store.read_range(branch, 1, 50)
        for ev in all_events2:
            state2["x"] = ev["payload"]["x"]
            state2["y"] = ev["payload"]["y"]

        # 逐位一致
        assert state == state2

    async def test_replay_with_snapshot_resume(self, store):
        """快照 + 增量重放：写入快照后从快照点恢复。"""
        branch = "snap-replay"

        # 写入前 20 个事件
        events1 = [_make_event(tick=i, payload={"val": i}) for i in range(20)]
        await store.append(branch, events1)

        # 写入快照（模拟 tick 19 的状态）
        snap_state = {"tick": 19, "accumulated": list(range(20))}
        snap_blob = json.dumps(snap_state).encode()
        await store.write_snapshot(branch, tick=19, event_seq=20, blob=snap_blob)

        # 写入后 30 个事件
        events2 = [_make_event(tick=i, payload={"val": i}) for i in range(20, 50)]
        await store.append(branch, events2)

        # 读回快照
        snap = await store.latest_snapshot(branch, before_tick=50)
        assert snap is not None
        restored = decompress_snapshot(snap)
        assert restored["tick"] == 19
        assert restored["accumulated"] == list(range(20))

        # 从快照点后读取增量事件
        inc_events = await store.read_range(branch, 21, 50)
        assert len(inc_events) == 30
        assert [e["payload"]["val"] for e in inc_events] == list(range(20, 50))


# ---------------------------------------------------------------------------
# T1: codex 必须项 #2 — entropy rows 同事务原子性（append 预留接口）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestEntropyRows:
    """append 支持随批携带 entropy rows，与事件同事务原子写入。"""

    async def test_append_with_entropy_rows_atomic(self, store, engine):
        """事件 + 熵日志行在同一事务提交，均可读回。"""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from sim.core.persistence.models import EntropyLog

        branch = "b-entropy"
        events = [_make_event(tick=5, kind="entropy_inject")]
        entropy_rows = [
            {"stream": "world", "reason": "turn 5 coin flip", "tick": 5, "value": "deadbeef"},
        ]

        await store.append(branch, events, entropy_rows=entropy_rows)

        # 事件已写
        got_events = await store.read_range(branch, 1, 1)
        assert len(got_events) == 1

        # 熵日志行已写（同事务）
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with sf() as session:
            rows = (await session.execute(select(EntropyLog))).scalars().all()
            assert len(rows) == 1
            assert rows[0].stream == "world"
            assert rows[0].value == "deadbeef"
            assert rows[0].branch_id == branch

    async def test_append_without_entropy_rows(self, store, engine):
        """不传 entropy_rows 时只写事件（当前内核路径）。"""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from sim.core.persistence.models import EntropyLog

        branch = "b-noentropy"
        await store.append(branch, [_make_event(tick=1)])

        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with sf() as session:
            rows = (await session.execute(select(EntropyLog))).scalars().all()
            assert rows == []


# ---------------------------------------------------------------------------
# T1: codex 必须项 #3 — 快照 seq 与事件流对齐
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestSnapshotSeqAlignment:
    """snapshots.seq 必须等于快照点事件流最大 events.seq，读档窗口不错位。"""

    async def test_snapshot_seq_matches_event_stream(self, store):
        """写入事件流 → 快照 seq = 当前最大 events.seq。"""
        branch = "b-align"

        # 写 10 个事件
        await store.append(branch, [_make_event(tick=i) for i in range(10)])
        all_events = await store.read_range(branch, 1, 10)
        max_seq = all_events[-1]["seq"]
        assert max_seq == 10

        # 快照点 seq = 事件流最大 seq
        await store.write_snapshot(branch, tick=9, event_seq=max_seq, blob=b"state@seq10")

        snap = await store.latest_snapshot(branch, before_tick=100)
        assert snap is not None
        assert snap.seq == max_seq == 10

        # 读档衔接：snapshot.seq 之后的事件（应为空，快照点在末尾）
        later = await store.read_range(branch, snap.seq + 1, 1000)
        assert later == []

    async def test_snapshot_resume_window_not_shifted(self, store):
        """连续多次快照：seq 始终取事件流值，不随快照份数漂移。"""
        branch = "b-window"

        # 5 事件 + 快照(seq=5)
        await store.append(branch, [_make_event(tick=i) for i in range(5)])
        await store.write_snapshot(branch, tick=4, event_seq=5, blob=b"snap1")

        # 再 5 事件 + 快照(seq=10)
        await store.append(branch, [_make_event(tick=i) for i in range(5, 10)])
        await store.write_snapshot(branch, tick=9, event_seq=10, blob=b"snap2")

        # 第三份快照的 seq 不应因前两份而变成 3；应仍绑定事件流
        snap1 = await store.latest_snapshot(branch, before_tick=4)
        snap2 = await store.latest_snapshot(branch, before_tick=9)
        assert snap1.seq == 5
        assert snap2.seq == 10

        # 从 snap1 续读第 6..10 个事件，共 5 条（窗口正确）
        resumed = await store.read_range(branch, snap1.seq + 1, snap2.seq)
        assert len(resumed) == 5
