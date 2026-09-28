"""driver fork 编排钉子（M5 批次 B 行为面，裁 25-B②/裁 26-A⑥）。

fork_orchestration 是持久层（D3-b fork_from_anchor）与网关/路由之间的编排缝：
- 定位：anchor 表行 → (branch_id, seq, tick)（tick 由事件流回查）；
- preflush：P1 必填动作透传（漏传不可分叉——动作不是断言）；
- 登记回调：编排层不 import 网关（依赖方向网关→编排单向）；
- 分叉点只支持父分支头部（fail-closed 语义由 fork_from_anchor 守，本层透传错误）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.fork import ForkError, fork_from_anchor
from sim.core.persistence.fork_orchestration import (
    AnchorLocation,
    OrchestrationError,
    locate_anchor,
    orchestrate_load_anchor,
)


async def _seed_world(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """最小世界线：branches(main, head seq=3 tick=300) + events 三条 + anchor 行。

    created_at 有 NOT NULL（TimestampMixin）——ORM 级 default 不作用于裸 SQL，
    裸 INSERT 须显式给（time.time() 同款语义）。
    """
    import time as _time

    now = _time.time()
    async with session_factory() as session, session.begin():
        await session.execute(
            text("INSERT INTO branches (id, status, created_at) VALUES ('main', 'active', :ts)"),
            {"ts": now},
        )
        for seq, tick in ((1, 100), (2, 200), (3, 300)):
            await session.execute(
                text(
                    "INSERT INTO events (branch_id, seq, tick, event_type, actor_id, payload,"
                    " witnesses, created_at)"
                    " VALUES ('main', :seq, :tick, 'world.tick', '', '{}', '[]', :ts)"
                ),
                {"seq": seq, "tick": tick, "ts": now},
            )
        await session.execute(
            text(
                "INSERT INTO player_anchors (id, name, branch_id, seq, tick, agent_override,"
                " protected, created_at, updated_at)"
                " VALUES ('anc-1', '初到临河', 'main', 3, 300, '{}', 0, :ts, :ts)"
            ),
            {"ts": now},
        )


@pytest.fixture()
async def session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/fork_orch.db")
    await init_database(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await _seed_world(factory)
    yield factory
    await engine.dispose()


class TestLocateAnchor:
    async def test_returns_branch_seq_and_tick(self, session_factory):
        loc = await locate_anchor(session_factory, "anc-1")
        assert loc == AnchorLocation(branch_id="main", seq=3, tick=300)

    async def test_missing_anchor_raises(self, session_factory):
        with pytest.raises(OrchestrationError, match="anchor 不存在"):
            await locate_anchor(session_factory, "ghost")

    async def test_dangling_seq_raises(self, session_factory):
        import time as _time

        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO player_anchors (id, name, branch_id, seq, tick,"
                    " agent_override, protected, created_at, updated_at)"
                    " VALUES ('anc-bad', '悬空档', 'main', 99, 999, '{}', 0, :ts, :ts)"
                ),
                {"ts": _time.time()},
            )
        with pytest.raises(OrchestrationError, match="指向的事件不存在"):
            await locate_anchor(session_factory, "anc-bad")


class TestOrchestrateLoadAnchor:
    async def test_happy_path_forks_and_registers_child(self, session_factory):
        """定位→preflush→fork→登记：返回 ForkResult，子分支行落库。"""
        preflush_calls: list[int] = []

        async def preflush() -> None:
            preflush_calls.append(1)

        registered: list[str] = []
        result = await orchestrate_load_anchor(
            session_factory,
            anchor_id="anc-1",
            flush_in_flight=preflush,
            register_child=registered.append,
        )
        assert preflush_calls == [1]  # P1 动作先于事务
        assert result.parent_branch_id == "main"
        assert result.forked_from_seq == 3
        assert registered == [result.new_branch_id]
        async with session_factory() as session:
            child_status = (
                await session.execute(
                    text("SELECT status FROM branches WHERE id = :b"),
                    {"b": result.new_branch_id},
                )
            ).scalar_one_or_none()
            parent_status = (
                await session.execute(
                    text("SELECT status FROM branches WHERE id = 'main'")
                )
            ).scalar_one()
        assert child_status == "active"
        assert parent_status == "abandoned"

    async def test_missing_anchor_fails_without_forking(self, session_factory):
        """定位失败 → 不进事务、不产生任何分支。"""
        async def preflush() -> None:
            pytest.fail("定位失败不得触发 preflush")

        with pytest.raises(OrchestrationError, match="anchor 不存在"):
            await orchestrate_load_anchor(
                session_factory,
                anchor_id="ghost",
                flush_in_flight=preflush,
            )
        async with session_factory() as session:
            count = (
                await session.execute(text("SELECT COUNT(*) FROM branches"))
            ).scalar_one()
        assert count == 1  # 只有 main

    async def test_fork_error_propagates_untouched(self, session_factory):
        """事务层 ForkError（分叉点不在头部）原样穿透——编排层不吞不转译。"""
        import time as _time

        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO events (branch_id, seq, tick, event_type, actor_id, payload,"
                    " witnesses, created_at)"
                    " VALUES ('main', 4, 400, 'world.tick', '', '{}', '[]', :ts)"
                ),
                {"ts": _time.time()},
            )
        async def preflush() -> None:
            return None

        with pytest.raises(ForkError):
            await orchestrate_load_anchor(
                session_factory,
                anchor_id="anc-1",
                flush_in_flight=preflush,
            )


class TestForkHeadOnlyStillHolds:
    async def test_fork_from_head_succeeds_directly(self, session_factory):
        """分叉点=父分支头部才可分叉（fork.py fail-closed）——本例是合法形态。"""
        async def preflush() -> None:
            return None

        result = await fork_from_anchor(
            session_factory,
            parent_branch_id="main",
            fork_seq=3,
            fork_tick=300,
            preflush=preflush,
        )
        assert result.forked_from_branch == "main"
        assert result.vec_pending is True  # 未给 vec_conn：降级不泄漏
