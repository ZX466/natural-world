"""批次 B（NPC 装配进实况世界）钉子。

四个面：
1. build_default_bus 注册 NPC_ACT no-op handler（同 ENTROPY_INJECT 口径：
   决策记录进日志、状态层 no-op——含 NPC_ACT 与不含 NPC_ACT 的序列 fold 出
   同一 state_hash，重放安全）。
2. sim/npc/sim_exec.py 确定性闲逛执行面：wander_goal 确定性哈希目标 +
   plan_npc_move（可走性约束 + 剩余 path 防抖 + 不可达静默跳过）+
   npc_events_for_tick（决策批次 → NPC_ACT + MOVE 交错入流）。
3. sim/content/villagers.py 确定性播种：50 村民名册 + 环形出生散布 + 幂等落库。
4. TickLoop.attach_npc_runtime 挂载：每 _NPC_DECISION_INTERVAL tick 一轮钩子，
   返回事件批次经 enqueue 进流（C4 唯一写路径）。
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.t1

# ---------------------------------------------------------------------------
# 1. bus NPC_ACT no-op handler
# ---------------------------------------------------------------------------


class TestBusNpcActHandler:
    def test_npc_act_registered_and_noop(self) -> None:
        """NPC_ACT 已注册且 apply 不改状态（no-op，同 ENTROPY_INJECT 口径）。"""
        from sim.core.events import EventKind, npc_act_event
        from sim.core.world import TickContext, WorldState, build_default_bus

        bus = build_default_bus()
        # 白盒哨兵：修复前 NPC_ACT 未注册，本断言红
        assert EventKind.NPC_ACT in bus._handlers  # noqa: SLF001
        state = WorldState(world_seed=42)
        ev = npc_act_event(tick=1, npc_id="npc_01", action="wander", params={})
        result = bus.apply(state, ev, TickContext())
        assert result.state == state
        assert result.derived == ()

    def test_npc_act_is_state_transparent_for_replay(self) -> None:
        """含/不含 NPC_ACT 的事件序列 fold 出同一 state_hash（no-op 的重放语义）。"""
        from sim.core.events import move_event, npc_act_event, world_create_event
        from sim.core.world import TickContext, WorldState, build_default_bus

        def fold(with_act: bool) -> str:
            bus = build_default_bus()
            state = WorldState(world_seed=42)
            ctx = TickContext()
            for ev in [
                world_create_event(tick=0, seed=42, entity_ids=("npc_01",)),
                move_event(tick=1, actor_id="npc_01", start=(0, 0), goal=(5, 5), path=((0, 0), (5, 5))),
                *(
                    [npc_act_event(tick=1, npc_id="npc_01", action="wander", params={})]
                    if with_act
                    else []
                ),
            ]:
                state = bus.apply(state, ev, ctx).state
            return state.state_hash()

        assert fold(True) == fold(False)


# ---------------------------------------------------------------------------
# 2. 确定性闲逛执行面（sim/npc/sim_exec.py）
# ---------------------------------------------------------------------------


class TestWanderGoal:
    def test_deterministic(self) -> None:
        from sim.npc.sim_exec import wander_goal

        assert wander_goal(42, 100, "npc_01", 48, 48) == wander_goal(42, 100, "npc_01", 48, 48)

    def test_differs_across_npcs(self) -> None:
        from sim.npc.sim_exec import wander_goal

        goals = {wander_goal(42, 100, f"npc_{i:02d}", 48, 48) for i in range(1, 21)}
        assert len(goals) > 1, "不同 NPC 同 tick 目标全同 = 散布失效"

    def test_within_bounds(self) -> None:
        from sim.npc.sim_exec import wander_goal

        for i in range(1, 51):
            gx, gy = wander_goal(42, 100 + i, f"npc_{i:02d}", 48, 48)
            assert 0 <= gx < 48 and 0 <= gy < 48


class TestPlanNpcMove:
    @staticmethod
    def _wired_loop():
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(
            clock=GameClock(speed=1.0), bus=build_default_bus(), state=WorldState(world_seed=42)
        )
        loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("npc_01",)))
        loop.drain_events()
        loop.issue_move("npc_01", [(0, 0), (5, 5)])
        loop.advance_frame(1.0)  # 60 tick：路径耗尽，实体停在 (5,5)
        loop.drain_events()
        return loop

    def test_wander_produces_move_event(self) -> None:
        from sim.core.events import EventKind
        from sim.npc.sim_exec import plan_npc_move
        from sim.world.pathfinding import Pathfinder

        from sim.api.main import _fallback_map

        loop = self._wired_loop()
        pf = Pathfinder(_fallback_map())
        mv = plan_npc_move(loop.state, "npc_01", "wander", pf, seed=42, tick=100)
        assert mv is not None and mv.event_type is EventKind.MOVE
        assert mv.payload["entity_id"] == "npc_01"
        path = mv.payload["path"]
        assert tuple(path[0]) == (5, 5)  # 起点即实体当前位置（model_dump 后 list）
        goal = tuple(path[-1])
        assert _fallback_map().is_walkable(goal[0], goal[1])

    def test_non_locomotion_actions_return_none(self) -> None:
        from sim.npc.sim_exec import plan_npc_move
        from sim.world.pathfinding import Pathfinder

        from sim.api.main import _fallback_map

        loop = self._wired_loop()
        pf = Pathfinder(_fallback_map())
        for action in ("eat", "rest", "work", "request_chat"):
            assert plan_npc_move(loop.state, "npc_01", action, pf, seed=42, tick=100) is None

    def test_in_flight_path_blocks_new_move(self) -> None:
        """剩余 path 未耗尽 → 不再发 move（防抖）。"""
        from sim.npc.sim_exec import plan_npc_move
        from sim.world.pathfinding import Pathfinder

        from sim.api.main import _fallback_map

        loop = self._wired_loop()
        loop.issue_move("npc_01", [(5, 5), (9, 9)])  # 在途
        pf = Pathfinder(_fallback_map())
        assert plan_npc_move(loop.state, "npc_01", "wander", pf, seed=42, tick=100) is None

    def test_unknown_entity_returns_none(self) -> None:
        from sim.npc.sim_exec import plan_npc_move
        from sim.world.pathfinding import Pathfinder

        from sim.api.main import _fallback_map

        loop = self._wired_loop()
        pf = Pathfinder(_fallback_map())
        assert plan_npc_move(loop.state, "ghost", "wander", pf, seed=42, tick=100) is None


class TestNpcEventsForTick:
    def _bare_runtime(self):
        from sim.npc.model import Need, NpcProfileData
        from sim.npc.runtime import NpcRuntime
        from sim.npc.utility import UtilityModel

        def _profile(nid: str) -> NpcProfileData:
            return NpcProfileData(
                npc_id=nid, name=nid, lod=1, needs=(Need(name="hunger", value=0.8, weight=1.0),)
            )

        return NpcRuntime(
            profiles={"npc_01": _profile("npc_01"), "npc_02": _profile("npc_02")},
            utility=UtilityModel(n_npc=2),
        )

    def test_batch_contains_act_per_active_npc(self) -> None:
        from sim.core.events import EventKind
        from sim.npc.sim_exec import npc_events_for_tick
        from sim.world.pathfinding import Pathfinder

        from sim.api.main import _fallback_map

        loop = TestPlanNpcMove._wired_loop()
        acts = [
            e
            for e in npc_events_for_tick(
                runtime=self._bare_runtime(),
                state=loop.state,
                tick=100,
                pathfinder=Pathfinder(_fallback_map()),
                seed=42,
            )
            if e.event_type is EventKind.NPC_ACT
        ]
        assert {e.payload["npc_id"] for e in acts} == {"npc_01", "npc_02"}

    def test_move_follows_its_own_act(self) -> None:
        """若产出 MOVE，必须紧跟同 NPC 的 NPC_ACT 之后（日志可读序）。"""
        from sim.core.events import EventKind
        from sim.npc.sim_exec import npc_events_for_tick
        from sim.world.pathfinding import Pathfinder

        from sim.api.main import _fallback_map

        loop = TestPlanNpcMove._wired_loop()
        batch = npc_events_for_tick(
            runtime=self._bare_runtime(),
            state=loop.state,
            tick=100,
            pathfinder=Pathfinder(_fallback_map()),
            seed=42,
        )
        act_idx: dict[str, int] = {}
        for i, e in enumerate(batch):
            if e.event_type is EventKind.NPC_ACT:
                act_idx[str(e.payload["npc_id"])] = i
            elif e.event_type is EventKind.MOVE:
                npc = str(e.payload["entity_id"])
                assert npc in act_idx, "MOVE 出现在其 NPC_ACT 之前"
                assert act_idx[npc] < i


class TestRuntimeTicksParam:
    def test_ticks_advances_needs_multiplied(self) -> None:
        """runtime.tick(ticks=N) 需求按 N tick 推进（决策节拍 10 时窗口对齐）。"""
        from sim.npc.model import Need, NpcProfileData
        from sim.npc.runtime import NpcRuntime
        from sim.npc.utility import UtilityModel

        p = NpcProfileData(
            npc_id="npc_01", name="x", lod=1, needs=(Need(name="hunger", value=0.0, weight=1.0),)
        )
        rt = NpcRuntime(profiles={"npc_01": p}, utility=UtilityModel(n_npc=1))
        rt.tick(1, ticks=10)
        hunger = rt.profiles["npc_01"].needs[0].value
        assert hunger == pytest.approx(10.0 / 86400.0)


# ---------------------------------------------------------------------------
# 3. 播种（sim/content/villagers.py）
# ---------------------------------------------------------------------------


class TestVillagerRoster:
    def test_50_unique_ids(self) -> None:
        from sim.content.villagers import VILLAGER_IDS, build_roster

        assert len(VILLAGER_IDS) == 50
        assert len(set(VILLAGER_IDS)) == 50
        roster = build_roster()
        assert tuple(p.npc_id for p in roster) == VILLAGER_IDS

    def test_roster_deterministic(self) -> None:
        from sim.content.villagers import build_roster

        assert build_roster() == build_roster()

    def test_profiles_shape(self) -> None:
        from sim.content.villagers import build_roster

        for p in build_roster():
            assert p.name and p.occupation
            assert p.lod == 1
            need_names = {n.name for n in p.needs}
            assert {"hunger", "energy", "social"} <= need_names
            assert all(0.0 <= n.value <= 1.0 and n.weight > 0 for n in p.needs)


class TestSpawnPositions:
    def test_50_unique_walkable_not_on_base(self) -> None:
        from sim.api.main import _default_map
        from sim.content.villagers import SPAWN_BASE, spawn_positions

        m = _default_map()
        positions = spawn_positions(m, base=SPAWN_BASE, count=50)
        assert len(positions) == 50
        assert len(set(positions)) == 50
        assert SPAWN_BASE not in positions
        for x, y in positions:
            assert m.is_walkable(x, y), f"{x},{y} 不可走"

    def test_deterministic(self) -> None:
        from sim.api.main import _default_map
        from sim.content.villagers import SPAWN_BASE, spawn_positions

        assert spawn_positions(_default_map(), base=SPAWN_BASE, count=50) == spawn_positions(
            _default_map(), base=SPAWN_BASE, count=50
        )


class TestSeedVillagers:
    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def _fresh_sf(self):
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import StaticPool

        from sim.core.persistence.database import create_session_factory, init_database

        async def _make():
            engine = create_async_engine(
                "sqlite+aiosqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            await init_database(engine)
            return create_session_factory(engine)

        return self._run(_make())

    def test_seed_inserts_50_and_idempotent(self) -> None:
        from sim.content.villagers import seed_villagers

        sf = self._fresh_sf()
        assert self._run(seed_villagers(sf)) == 50
        assert self._run(seed_villagers(sf)) == 0  # 已有 profile → 幂等跳过
        from sim.core.persistence.npc_store import NpcStore
        from sim.core.persistence.store import SqlEventStore

        store = NpcStore(SqlEventStore(sf))
        profiles = self._run(store.materialize(None))
        assert len(profiles) == 50

    def test_seeded_profiles_materialize(self) -> None:
        from sim.content.villagers import VILLAGER_IDS, seed_villagers

        sf = self._fresh_sf()
        self._run(seed_villagers(sf))
        from sim.core.persistence.npc_store import NpcStore
        from sim.core.persistence.store import SqlEventStore

        store = NpcStore(SqlEventStore(sf))
        profiles = self._run(store.materialize(None))
        assert set(profiles) == set(VILLAGER_IDS)
        for nid, p in profiles.items():
            assert p.name
            assert p.lod == 1
            assert {n.name for n in p.needs} == {"hunger", "energy", "social"}


# ---------------------------------------------------------------------------
# 4. TickLoop 挂载
# ---------------------------------------------------------------------------


class TestAttachNpcRuntime:
    @staticmethod
    def _loop_with_chenmo():
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(
            clock=GameClock(speed=1.0), bus=build_default_bus(), state=WorldState(world_seed=42)
        )
        loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
        loop.drain_events()
        return loop

    def test_no_hook_baseline_silent(self) -> None:
        from sim.core.events import EventKind

        loop = self._loop_with_chenmo()
        loop.advance_frame(1.0)
        events = loop.drain_events()
        assert all(e.event_type is not EventKind.NPC_ACT for e in events)

    def test_hook_called_at_interval_and_events_enqueued(self) -> None:
        """每 10 tick 调一次钩子（tick 0,10,…,50 = 6 次/60tick），返回事件经 enqueue 进流。"""
        from sim.core.events import npc_act_event

        loop = self._loop_with_chenmo()
        calls: list[int] = []

        def hook(state, tick):
            calls.append(tick)
            return [npc_act_event(tick=tick, npc_id="npc_01", action="wander", params={})]

        loop.attach_npc_runtime(hook)
        loop.advance_frame(1.0)  # 60 tick
        assert calls == [0, 10, 20, 30, 40, 50]
        events = loop.drain_events()
        acts = [e for e in events if e.event_type.value == "npc.act"]
        assert {e.tick for e in acts} == {0, 10, 20, 30, 40, 50}

    def test_hook_events_replay_safe(self) -> None:
        """钩子返回的 NPC_ACT 入流后，世界状态与无钩子时逐位一致（no-op 面）。"""
        from sim.core.events import npc_act_event

        def run(with_hook: bool) -> str:
            loop = self._loop_with_chenmo()
            if with_hook:
                loop.attach_npc_runtime(
                    lambda state, tick: [
                        npc_act_event(tick=tick, npc_id="npc_01", action="wander", params={})
                    ]
                )
            loop.advance_frame(1.0)
            loop.drain_events()
            return loop.state.state_hash()

        assert run(True) == run(False)
