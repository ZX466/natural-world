"""Async single-writer adapter for MemoryWritePipeline."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sim.core.persistence.models import NpcMemory
from sim.llm.memory_scan import InMemoryStore, MemoryEntry


class AsyncMemoryStore(InMemoryStore):
    def __init__(self, *, branch_id: str = "main", created_at_tick: int = 0) -> None:
        super().__init__()
        self.branch_id = branch_id
        self.created_at_tick = created_at_tick
        self._pending: list[MemoryEntry] = []

    def persist(self, **kwargs: object) -> MemoryEntry:
        entry = super().persist(**kwargs)  # type: ignore[arg-type]
        self._pending.append(entry)
        return entry

    async def hydrate(self, session: AsyncSession) -> None:
        rows = (
            await session.execute(
                select(NpcMemory).where(NpcMemory.branch_id == self.branch_id)
            )
        ).scalars()
        for row in rows:
            entry = self._make_entry_from_row(row)
            self._entries[entry.id] = entry

    async def flush(self, session: AsyncSession) -> None:
        for entry in self._pending:
            exists = await session.scalar(
                select(NpcMemory.id).where(NpcMemory.entry_id == entry.id)
            )
            if exists is not None:
                continue
            session.add(
                NpcMemory(
                    entry_id=entry.id,
                    npc_id=entry.npc_id,
                    event_seq=entry.event_seq,
                    branch_id=self.branch_id,
                    content=entry.content,
                    source=entry.source,
                    importance=entry.importance,
                    emotion_tag=entry.emotion_tag,
                    created_at_tick=self.created_at_tick,
                )
            )
        self._pending.clear()

    @staticmethod
    def _make_entry_from_row(row: NpcMemory) -> MemoryEntry:
        from sim.llm.memory_scan import make_entry

        return make_entry(
            entry_id=row.entry_id,
            npc_id=row.npc_id,
            content=row.content,
            source=row.source,
            event_seq=row.event_seq,
            importance=row.importance,
            emotion_tag=row.emotion_tag,
            superseded_by=row.superseded_by,
            invalid_reason=row.invalid_reason,
        )
