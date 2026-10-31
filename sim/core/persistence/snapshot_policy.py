"""Transaction-local snapshot retention; event history is never modified."""

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.core.persistence.models import Branch, Snapshot

HOT_SNAPSHOT_LIMIT = 8


async def prune_hot_snapshots(session: AsyncSession, branch_id: str) -> None:
    """Retain recent hot rows and one daily first; the caller owns the commit."""
    # Queries must see the new checkpoint even when the factory disables autoflush.
    await session.flush()
    recent = (
        select(Snapshot.seq)
        .where(Snapshot.branch_id == branch_id, Snapshot.is_cold.is_(False))
        .order_by(Snapshot.tick.desc(), Snapshot.seq.desc())
        .limit(HOT_SNAPSHOT_LIMIT)
    )
    ranked_days = (
        select(
            Snapshot.seq,
            func.row_number()
            .over(
                partition_by=Snapshot.tick // TICKS_PER_GAME_DAY,
                order_by=(Snapshot.tick.asc(), Snapshot.seq.asc()),
            )
            .label("day_rank"),
        )
        .where(Snapshot.branch_id == branch_id)
        .subquery()
    )
    daily_first = select(ranked_days.c.seq).where(ranked_days.c.day_rank == 1)
    # Missing/abandoned metadata is not permission to delete legacy snapshots.
    active = select(Branch.id).where(Branch.id == branch_id, Branch.status == "active")
    await session.execute(
        delete(Snapshot)
        .where(
            Snapshot.branch_id == branch_id,
            Snapshot.branch_id.in_(active),
            Snapshot.is_cold.is_(False),
            Snapshot.seq.not_in(recent),
            Snapshot.seq.not_in(daily_first),
        )
        .execution_options(synchronize_session=False)
    )


async def mark_branch_snapshots_cold(session: AsyncSession, branch_id: str) -> None:
    """Mark snapshots cold without deleting rows or changing payloads."""
    await session.flush()
    await session.execute(
        update(Snapshot)
        .where(Snapshot.branch_id == branch_id, Snapshot.is_cold.is_(False))
        .values(is_cold=True)
        .execution_options(synchronize_session=False)
    )
