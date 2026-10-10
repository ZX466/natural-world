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
                await session.execute(__import__("sqlalchemy").select(NpcMemory))
            ).scalars().all()
            assert rows[0].entry_id == entry.id
        await engine.dispose()

    asyncio.run(run())
