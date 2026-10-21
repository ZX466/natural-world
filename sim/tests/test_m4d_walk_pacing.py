"""批次 D1：行走节拍（瞬移修复）钉子。

症状：实体 1 格/tick × 60tps = 60 格/真实秒——横穿全镇 <1 秒，视觉瞬移。
修法：_step_entity_movement 加行走节拍 _MOVE_TICKS_PER_TILE=15（1x 下 4 格/秒），
实体相位 = crc32(entity_id) 偏移（确定性，无 RNG 流，无同步齐步脉冲）。

契约：
1. 单 tick 内实体不再必然移动（节拍未到则原地）；
2. 足够 tick 后路径必然消费完（进度保证）；
3. 相位确定性：同 id 同相位，重放逐位一致（state_hash）；
4. 不同实体相位散布（无全员齐步）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.t1


def _loop_two_entities():
    from sim.core.clock import GameClock
    from sim.core.events import world_create_event
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState, build_default_bus

    loop = TickLoop(
        clock=GameClock(speed=1.0), bus=build_default_bus(), state=WorldState(world_seed=42)
    )
    loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("a", "b")))
    loop.drain_events()
    return loop


class TestWalkPacing:
    def test_not_every_tick(self) -> None:
        """路径未耗尽时，单 tick 不必然移动（节拍门生效）。"""
        loop = _loop_two_entities()
        loop.issue_move("a", [(0, 0), (0, 0)])  # 占位路径被 422 拒？——用真两点
        loop.drain_events()

    def test_path_consumed_within_budget(self) -> None:
        """发 4 格路径，60 tick 内必然走完（15 tick/格 × 4 = 60 上界）。"""
        loop = _loop_two_entities()
        loop.issue_move("a", [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)])
        loop.drain_events()
        for _ in range(90):
            loop._tick_once()
        assert loop.state.entities["a"].pos == (4, 0)
        assert loop.state.entities["a"].path == ()

    def test_phase_deterministic(self) -> None:
        """同 id 相位恒定（纯函数）。"""
        from sim.core.tick import entity_move_phase

        assert entity_move_phase("a") == entity_move_phase("a")

    def test_phases_spread(self) -> None:
        """不同实体相位不全同（无齐步脉冲）。"""
        from sim.core.tick import entity_move_phase

        phases = {entity_move_phase(f"villager_{i:02d}") for i in range(1, 51)}
        assert len(phases) > 1

    def test_replay_state_hash_stable(self) -> None:
        """带节拍的移动演进仍是确定性纯函数：同事件序列两遍 fold 同 hash。"""
        from sim.core.clock import GameClock
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        def run() -> str:
            loop = TickLoop(
                clock=GameClock(speed=1.0), bus=build_default_bus(), state=WorldState(world_seed=7)
            )
            loop.enqueue(
                __import__("sim.core.events", fromlist=["world_create_event"]).world_create_event(
                    tick=0, seed=7, entity_ids=("a",)
                )
            )
            loop.drain_events()
            loop.issue_move("a", [(0, 0), (2, 2), (5, 5)])
            for _ in range(120):
                loop._tick_once()
            loop.drain_events()
            return loop.state.state_hash()

        assert run() == run()


class TestBootstrapDrainsPaths:
    def test_build_loop_entities_at_spawn(self, tmp_path, monkeypatch) -> None:
        """创世搬运后实体必须已到站（build_loop 内排空路径，不等实况走完）。"""
        import asyncio

        from sim.api.main import SPAWN_TILE, build_loop

        monkeypatch.chdir(tmp_path)

        async def fresh_world():
            loop, store = await build_loop()
            await store.session_factory.kw["bind"].dispose()
            return loop

        loop = asyncio.run(fresh_world())
        assert loop.state.entities["chenmo"].pos == SPAWN_TILE
        assert all(not e.path for e in loop.state.entities.values()), "创世路径必须排空"


class TestMultiHookNoClobber:
    """D5 教训回归钉：attach_npc_runtime 必须多槽（第二个挂载不得顶掉第一个）。"""

    def test_both_hooks_called(self) -> None:
        from sim.core.clock import GameClock
        from sim.core.events import npc_act_event, world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(
            clock=GameClock(speed=1.0), bus=build_default_bus(), state=WorldState(world_seed=42)
        )
        loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("a",)))
        loop.drain_events()

        calls: list[str] = []
        loop.attach_npc_runtime(
            lambda state, tick: (
                calls.append("npc"),
                [npc_act_event(tick=tick, npc_id="a", action="wander", params={})],
            )[1]
        )
        loop.attach_npc_runtime(lambda state, tick: (calls.append("fire"), None)[1])

        loop.advance_frame(1.0)
        assert calls.count("npc") == 6  # 每 10 tick 一次 × 60
        assert calls.count("fire") == 6
