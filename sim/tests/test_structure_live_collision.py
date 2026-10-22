"""DA-06：结构终态落库后，在线碰撞必须立即与重建结果一致。"""

import pytest

from sim.api import main
from sim.core.events import structure_collapsed_event, structure_removed_event
from sim.core.persistence.npc_store import NpcStore
from sim.tests.test_build_restore import branch_world as branch_world


@pytest.mark.parametrize("terminal", ["collapsed", "removed"])
async def test_structure_terminal_restores_live_collision(branch_world, terminal):
    store, pos, _ = branch_world
    async with main.lifespan(main.app):
        app = main.app
        old_map = app.state.tile_map
        pathfinder = app.state.pathfinder
        assert not old_map.is_walkable(*pos)
        sid = next(iter(await NpcStore(store).materialize_structures()))
        # 填入真实路径缓存：结构还原后即使该路径不穿建筑，也按派单清空。
        open_pos = next(
            (x, y)
            for y in range(old_map.height)
            for x in range(old_map.width - 1)
            if old_map.is_walkable(x, y) and old_map.is_walkable(x + 1, y)
        )
        assert pathfinder.find(open_pos, (open_pos[0] + 1, open_pos[1]))
        assert pathfinder.cache.entries
        event = (
            structure_collapsed_event(app.state.loop.state.tick, structure_id=sid, cause="decay")
            if terminal == "collapsed"
            else structure_removed_event(
                app.state.loop.state.tick, structure_id=sid, reason="demolished"
            )
        )
        app.state.loop.enqueue(event)
        await app.state.flush_for_anchor()

        online = app.state.tile_map
        assert online.is_walkable(*pos), "persisted tile restoration must update live collision"
        assert app.state.build_runtime.tile_map is online
        assert pathfinder.tile_map is online
        assert not pathfinder.cache.entries
        goal = (pos[0] + 1, pos[1])
        assert pathfinder.find(pos, goal) == (pos, goal)
        rebuilt = await main.rebuild_tile_map(NpcStore(store))
        assert [
            online.is_walkable(x, y) for y in range(online.height) for x in range(online.width)
        ] == [
            rebuilt.is_walkable(x, y) for y in range(rebuilt.height) for x in range(rebuilt.width)
        ]


async def test_unrelated_flush_preserves_live_map(branch_world):
    async with main.lifespan(main.app):
        original = main.app.state.tile_map
        await main.app.state.flush_for_anchor()
        assert main.app.state.tile_map is original
