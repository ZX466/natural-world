"""DA-08：首启/重启均由 ChenmoDriver 独占主角控制权。"""

import asyncio

from sim.agent.driver import ChenmoDriver
from sim.api import main
from sim.content.protagonist import CHENMO_ID
from sim.core.events import EventKind


async def test_cold_start_and_restart_have_one_protagonist_controller(monkeypatch):
    async def idle_driver(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "run_world_driver", idle_driver)
    rosters = []
    utility_actors = []
    # 同一隔离临时库的首启+重启；换库只会重复首启，不能检出已持久化主角混入。
    for _ in range(2):
        async with main.lifespan(main.app):
            app = main.app
            runtime = app.state.npc_runtime
            rosters.append(set(runtime.profiles))
            assert isinstance(app.state.chenmo_driver, ChenmoDriver)
            assert CHENMO_ID in app.state.loop.state.entities
            assert runtime.utility.n_npc == len(runtime.profiles)
            events = runtime.tick(tick=app.state.loop.state.tick)
            utility_actors.append(
                {str(e.payload["npc_id"]) for e in events if e.event_type is EventKind.NPC_ACT}
            )
            await app.state.flush_for_anchor()

    assert rosters[0] == rosters[1], "controller ownership must not depend on startup timing"
    assert all(CHENMO_ID not in roster for roster in rosters)
    assert all(CHENMO_ID not in actors for actors in utility_actors)
    assert all(actors for actors in utility_actors), (
        "ordinary NPC utility control must remain active"
    )
