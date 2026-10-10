import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.async_memory_store import AsyncMemoryStore
from sim.core.persistence.database import init_database
from sim.core.persistence.models import NpcMemory


def test_async_memory_store_hydrates_and_flushes() -> None:
    async def run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        await init_database(engine)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        store = AsyncMemoryStore(branch_id="main")
        entry = store.persist(
            npc_id="chenmo",
            content="在药铺学会辨认草药。",
            source="event",
            event_seq=1,
            importance=0.5,
            emotion_tag=None,
        )
        async with factory() as session:
            await store.flush(session)
            await session.commit()
            rows = (
                (await session.execute(__import__("sqlalchemy").select(NpcMemory))).scalars().all()
            )
            assert rows[0].entry_id == entry.id
        await engine.dispose()

    asyncio.run(run())


def test_async_memory_store_branch_reset_and_lazy_hydrate() -> None:
    async def run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        await init_database(engine)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        store = AsyncMemoryStore(branch_id="unbound")
        store.persist(
            npc_id="chenmo",
            content="旧分支残留",
            source="event",
            event_seq=1,
            importance=0.5,
            emotion_tag=None,
        )
        store.attach_branch("child")
        assert len(store) == 0
        assert store._pending == []
        async with factory() as session:
            session.add(
                NpcMemory(
                    entry_id="seeded",
                    npc_id="chenmo",
                    event_seq=1,
                    branch_id="child",
                    content="子分支历史",
                    source="event",
                    importance=0.5,
                    emotion_tag=None,
                    created_at_tick=0,
                )
            )
            await session.commit()
            await store.hydrate_if_empty(session)
        assert {entry.id for entry in store.iter_visible("chenmo")} == {"seeded"}
        await engine.dispose()

    asyncio.run(run())
