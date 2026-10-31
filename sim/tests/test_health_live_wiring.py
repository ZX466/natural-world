"""真实 lifespan 的健康缓存、感知、入流及子分支冷启动接线。"""

import asyncio

from sqlalchemy import func, select

from sim.core.events import EventKind, npc_health_changed_event
from sim.core.persistence.models import Event, NpcProfile


async def stop_background(app):
    for name in ("driver", "chenmo_task"):
        getattr(app.state, name).cancel()
    await asyncio.gather(app.state.driver, app.state.chenmo_task, return_exceptions=True)
    app.state.loop.clock.set_speed(0)


async def test_lifespan_emerges_from_real_perception_and_refreshes_after_commit():
    from sim.api.main import app, lifespan

    async with lifespan(app):
        await stop_background(app)
        loop = app.state.loop
        await app.state.flush_for_anchor()
        # 感知是实际生产 hook；夜色来自 narrate_time，没有手工填触发词。
        loop.state = loop.state.model_copy(update={"tick": 23 * 3600})
        loop.clock.restore_tick(loop.state.tick)
        loop._run_perception()
        loop._run_npc_runtime()
        entered = [e for e in loop.pending_events if e.event_type is EventKind.NPC_HIDDEN_EMERGE]
        assert {e.payload["npc_id"] for e in entered} >= {"chenmo", "villager_02"}
        assert app.state.chenmo_driver._hidden_provider().triggered
        await app.state.flush_for_anchor()
        async with app.state.store.session_factory() as session:
            persisted = list(
                await session.scalars(
                    select(Event).where(Event.event_type == EventKind.NPC_HIDDEN_EMERGE.value)
                )
            )
        assert len(persisted) == len(entered)
        loop.enqueue(
            npc_health_changed_event(
                loop.state.tick,
                npc_id="chenmo",
                category="trauma",
                code="night_unease",
                severity=0.1,
                active=False,
                hidden=True,
            )
        )
        await app.state.flush_for_anchor()
        assert app.state.chenmo_driver._hidden_provider().profile is None


async def test_cold_start_uses_child_profiles_and_health():
    from sim.api.main import app, lifespan
    from sim.core.persistence.fork import fork_from_anchor
    from sim.core.persistence.npc_store import NpcStore

    async with lifespan(app):
        await stop_background(app)
        await app.state.flush_for_anchor()
        store = app.state.store
        async with store.session_factory() as session:
            seq = await session.scalar(select(func.max(Event.seq)).where(Event.branch_id == "main"))

        async def preflush():
            await app.state.flush_for_anchor()

        await fork_from_anchor(
            store.session_factory,
            parent_branch_id="main",
            fork_seq=seq,
            fork_tick=app.state.loop.state.tick,
            new_branch_id="health-child",
            preflush=preflush,
        )
        await NpcStore(store, branch_id="health-child").flush_tick(
            [
                npc_health_changed_event(
                    app.state.loop.state.tick,
                    npc_id="chenmo",
                    category="trauma",
                    code="child_only",
                    severity=0.3,
                    hidden=True,
                ),
            ]
        )
        async with store.session_factory.begin() as session:
            profile = await session.get(
                NpcProfile, {"branch_id": "health-child", "id": "villager_01"}
            )
            profile.name = "子线赵铁"
    async with lifespan(app):
        await stop_background(app)
        assert app.state.npc_runtime.profiles["villager_01"].name == "子线赵铁"
        hidden = app.state.chenmo_driver._hidden_provider()
        assert "chenmo.health_child_only" in {a.id for a in hidden.profile.attributes}


async def test_downgrade_writeback_sees_current_hidden_window():
    from sim.api.main import app, lifespan

    async with lifespan(app):
        await stop_background(app)
        loop = app.state.loop
        npc_id = "villager_01"
        runtime = app.state.npc_runtime
        runtime.profiles[npc_id] = runtime.profiles[npc_id].with_lod(2)
        app.state.hidden_states[npc_id] = app.state.hidden_states[npc_id].evaluate("伤处疼得厉害")
        seen = []
        runtime.on_downgrade = lambda nid: seen.append(
            (nid, app.state.hidden_states[nid].triggered)
        )
        loop.state = loop.state.model_copy(
            update={
                "tick": 12 * 3600,
                "entities": {
                    **loop.state.entities,
                    npc_id: loop.state.entities[npc_id].model_copy(update={"pos": (0, 0)}),
                },
            }
        )
        loop._run_perception()
        loop._run_npc_runtime()
        assert (npc_id, frozenset()) in seen
