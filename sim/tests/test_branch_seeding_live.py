"""Cold-start seeding must follow the current branch, without guessing main in a fault state."""

from sqlalchemy import delete, func, select, text

from sim.core.events import npc_death_event
from sim.core.persistence.fork import fork_from_anchor
from sim.core.persistence.models import Event, NpcProfile
from sim.core.persistence.npc_store import NpcStore
from sim.tests.test_health_live_wiring import stop_background


async def _counts(app):
    async with app.state.store.session_factory() as session:
        return dict(
            (
                await session.execute(
                    select(NpcProfile.branch_id, func.count()).group_by(NpcProfile.branch_id)
                )
            ).all()
        )


async def _fork_current(app):
    store = app.state.store
    async with store.session_factory() as session:
        seq = await session.scalar(select(func.max(Event.seq)).where(Event.branch_id == "main"))
    await fork_from_anchor(
        store.session_factory,
        parent_branch_id="main",
        fork_seq=seq,
        fork_tick=app.state.loop.state.tick,
        new_branch_id="child",
        preflush=app.state.flush_for_anchor,
    )


async def test_cold_child_fills_only_missing_living_profiles_for_all_three_seeders():
    from sim.api.main import app, lifespan

    async with lifespan(app):
        await stop_background(app)
        await app.state.flush_for_anchor()
        await _fork_current(app)
        tick = app.state.loop.state.tick
        await NpcStore(app.state.store, branch_id="child").flush_tick(
            [
                npc_death_event(tick, entity_id="villager_06"),
                npc_death_event(tick, entity_id="dog_black"),
            ]
        )
        async with app.state.store.session_factory.begin() as session:
            await session.execute(
                delete(NpcProfile).where(
                    NpcProfile.branch_id == "child",
                    NpcProfile.id.in_(("villager_05", "chenmo", "cat_grey")),
                )
            )
        assert await _counts(app) == {"main": 54, "child": 49}
    async with lifespan(app):
        await stop_background(app)
        assert await app.state.store.current_branch_id() == "child"
        assert await _counts(app) == {"main": 54, "child": 52}
        profiles = await NpcStore(app.state.store, branch_id="child").materialize()
        assert {"villager_05", "chenmo", "cat_grey"} <= profiles.keys()
        assert {"villager_06", "dog_black"}.isdisjoint(profiles)
        assert profiles["cat_grey"].species == "cat"
        assert profiles["cat_grey"].identity_anchor == "我叫灰。"


async def test_fault_startup_does_not_seed_a_guessed_main_branch():
    from sim.api.main import app, lifespan

    async with lifespan(app):
        await stop_background(app)
        await app.state.flush_for_anchor()
        await _fork_current(app)
        async with app.state.store.session_factory.begin() as session:
            await session.execute(text("UPDATE branches SET is_current=0"))
            await session.execute(delete(NpcProfile).where(NpcProfile.branch_id == "main"))
        assert await _counts(app) == {"child": 54}
    async with lifespan(app):
        await stop_background(app)
        assert not app.state.world_source_ready
        assert await _counts(app) == {"child": 54}


async def test_empty_database_still_seeds_main_genesis():
    from sim.api.main import app, lifespan

    async with lifespan(app):
        await stop_background(app)
        await app.state.flush_for_anchor()
        assert await app.state.store.current_branch_id() == "main"
        assert await _counts(app) == {"main": 54}
