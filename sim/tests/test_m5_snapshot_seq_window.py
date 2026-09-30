"""M5-A4 T1 钉子 — `latest_snapshot(max_seq=…)` 快照 seq 判据（A3 §1.2 缝）

**缝**：`latest_snapshot` 原先只按 `tick <= before_tick` 选最新快照。同 tick 内多事件时
（批量 append / fold 一次落多条），快照点 `seq` 可能**已越界**于物化锚点的 `anchor.seq`
⇒ 重放窗口 `(snapshot_seq, anchor.seq]` 倒挂、事件被跳过 ⇒ 物化出的世界态 ≠ 锚点时刻。

**修**：`max_seq` 可选上界（按 `snapshots.seq` 过滤）；锚点物化路径必须传
`max_seq=anchor.seq`。不给 = 旧行为（既有调用方零影响）。

本文件钉：上界生效 / 越界快照被排除 / 无合格快照返回 None / 旧行为不变 / 排序不变。
"""

from __future__ import annotations

import gzip
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.store import SqlEventStore


@pytest.fixture
async def store():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(engine)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield SqlEventStore(sf)
    await engine.dispose()


def _blob(tick: int) -> bytes:
    return gzip.compress(json.dumps({"tick": tick}).encode())


@pytest.mark.t1
class TestLatestSnapshotSeqWindow:
    async def test_picks_latest_within_seq_bound(self, store: SqlEventStore) -> None:
        """上界内取 tick 最新（同 tick 多条时取 seq 大的）。"""
        await store.write_snapshot("main", 100, 10, _blob(100))
        await store.write_snapshot("main", 200, 20, _blob(200))

        got = await store.latest_snapshot("main", before_tick=300, max_seq=25)
        assert got is not None
        assert (got.tick, got.seq) == (200, 20)

    async def test_excludes_snapshot_beyond_seq_bound(self, store: SqlEventStore) -> None:
        """**核心钉**：同 tick 的越界快照必须被排除，退回较早且 seq 合法的快照。"""
        await store.write_snapshot("main", 100, 10, _blob(100))
        await store.write_snapshot("main", 200, 20, _blob(200))
        # tick 200、seq 40 已越界（anchor.seq=25）
        await store.write_snapshot("main", 200, 40, _blob(200))

        got = await store.latest_snapshot("main", before_tick=200, max_seq=25)
        assert got is not None
        assert (got.tick, got.seq) == (200, 20), "选到了 seq 越界的快照（窗口会倒挂）"

    async def test_only_out_of_bound_returns_none(self, store: SqlEventStore) -> None:
        """全部快照 seq 越界 ⇒ None（不是回退到越界快照）。"""
        await store.write_snapshot("main", 100, 40, _blob(100))
        assert await store.latest_snapshot("main", before_tick=200, max_seq=25) is None

    async def test_legacy_behavior_unchanged_without_max_seq(self, store: SqlEventStore) -> None:
        """不给 max_seq ⇒ 旧行为（纯 tick 口径，仍会选中 seq 较大的那条）。"""
        await store.write_snapshot("main", 100, 10, _blob(100))
        await store.write_snapshot("main", 200, 40, _blob(200))

        got = await store.latest_snapshot("main", before_tick=200)
        assert got is not None
        assert (got.tick, got.seq) == (200, 40)

    async def test_tick_bound_still_applied_with_max_seq(self, store: SqlEventStore) -> None:
        """两个上界同时生效：tick 晚的即便 seq 合法也不选。"""
        await store.write_snapshot("main", 100, 10, _blob(100))
        await store.write_snapshot("main", 300, 30, _blob(300))

        got = await store.latest_snapshot("main", before_tick=200, max_seq=25)
        assert got is not None
        assert (got.tick, got.seq) == (100, 10)

    async def test_branch_isolated(self, store: SqlEventStore) -> None:
        """上界是分支内口径（seq 是分支内引用），不跨分支取。"""
        await store.write_snapshot("other", 200, 20, _blob(200))
        assert await store.latest_snapshot("main", before_tick=300, max_seq=25) is None
