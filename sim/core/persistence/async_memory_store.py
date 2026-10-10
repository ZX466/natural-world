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

    def attach_branch(self, branch_id: str | None) -> None:
        """重新绑定当前世界线；unbound→branch 空转水，branch→branch 硬清零。"""

        if branch_id is None:
            return
        if self.branch_id == branch_id:
            return
        was_unbound = self.branch_id == "unbound"
        self.branch_id = branch_id
        self.reset()
        if was_unbound:
            self._pending.clear()

    def reset(self) -> None:
        """读档=分叉：清空本分支进程态与待落库条目（C6：新分支从零起步）。"""

        super().reset()
        self._pending.clear()

    async def hydrate_if_empty(self, session: AsyncSession) -> None:
        """unbound→branch / 未知重启后的惰性水合（已有进程态绝不覆盖）。"""

        if self._entries or self.branch_id == "unbound":
            return
        await self.hydrate(session)

    async def hydrate(self, session: AsyncSession) -> None:
        rows = (
            await session.execute(select(NpcMemory).where(NpcMemory.branch_id == self.branch_id))
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
            source=row.source,  # type: ignore[arg-type]
            event_seq=row.event_seq,
            importance=row.importance,
            emotion_tag=row.emotion_tag,
            superseded_by=row.superseded_by,
            invalid_reason=row.invalid_reason,
        )
