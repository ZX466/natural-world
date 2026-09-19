"""T2 回放确定性 — 内核的试金石（DESIGN §16，m0-core.md §9）。

同一 seed + 同一事件流 → 状态哈希逐位一致。
覆盖：RNG 分流独立性 / 熵注入重放 / 路径确定性与缓存失效。
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from sim.core.calendar import game_time, is_market_day, phase_of_day
from sim.core.clock import GameClock, TimeScale
from sim.core.entropy import EntropyMixer
from sim.core.events import EventKind, WorldEvent, combat_scale_event, world_create_event
from sim.core.rng import RngRegistry
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.world.map import CHUNK_SIZE, Chunk, TileMap
from sim.world.pathfinding import Pathfinder

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def make_loop(seed: int = 42) -> TickLoop:
    clock = GameClock(speed=1.0)
    bus = build_default_bus()
    state = WorldState(world_seed=seed)
    loop = TickLoop(clock=clock, bus=bus, state=state)
    create = world_create_event(tick=0, seed=seed, entity_ids=("chenmo",))
    loop.enqueue(create)
    loop.drain_events()
    return loop


def make_open_map(w: int = 32, h: int = 32) -> TileMap:
    """无障碍开阔图。"""
    chunks = {}
    for cy in range((h + CHUNK_SIZE - 1) // CHUNK_SIZE):
        for cx in range((w + CHUNK_SIZE - 1) // CHUNK_SIZE):
            chunks[(cx, cy)] = Chunk(
                cx=cx,
                cy=cy,
                ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
    return TileMap(width=w, height=h, chunks=chunks)


# ---------------------------------------------------------------------------
# clock / calendar
# ---------------------------------------------------------------------------


class TestClock:
    def test_advance_accumulator_60tps(self):
        clock = GameClock(speed=1.0)
        n = clock.advance(1.0)  # 1 真实秒 @1x = 60 tick
        assert n == 60
        assert clock.tick == 60

    def test_speed_4x_and_pause(self):
        clock = GameClock(speed=4.0)
        assert clock.advance(0.5) == 120
        clock.set_speed(0.0)
        assert clock.advance(10.0) == 0

    def test_combat_timescale(self):
        clock = GameClock(speed=1.0)
        clock.advance(0.5)  # 30 ticks
        clock.enter_combat()
        assert clock.timescale is TimeScale.COMBAT
        assert clock.advance(2.0) == 2  # 战斗尺：1 tick = 1 真实秒
        clock.exit_combat()
        assert clock.advance(1.0) == 60

    def test_catchup_cap(self):
        clock = GameClock(speed=16.0)
        n = clock.advance(100.0)  # 请求 160000 tick，截到 4s=3840
        assert n == 4.0 * 60 * 16

    def test_invalid_speed_rejected(self):
        with pytest.raises(ValueError, match="非法倍速"):
            GameClock(speed=2.0)


class TestCalendar:
    def test_game_time_derivation(self):
        # tick 0 = 第 1 天 00:00:00；86399 = 第 1 天 23:59:59
        t0 = game_time(0)
        assert (t0.day, t0.hour, t0.minute, t0.second) == (1, 0, 0, 0)
        t1 = game_time(86_399)
        assert (t1.day, t1.hour, t1.minute, t1.second) == (1, 23, 59, 59)
        t2 = game_time(86_400)
        assert t2.day == 2

    def test_phase_boundaries(self):
        assert phase_of_day(6 * 3600) is not None
        from sim.core.calendar import DayPhase

        assert phase_of_day(0) is DayPhase.NIGHT
        assert phase_of_day(6 * 3600) is DayPhase.DAWN
        assert phase_of_day(12 * 3600) is DayPhase.DAY
        assert phase_of_day(18 * 3600) is DayPhase.DUSK
        assert phase_of_day(23 * 3600) is DayPhase.NIGHT

    def test_market_day(self):
        assert is_market_day(0)  # 第 1 天
        assert not is_market_day(86_400)  # 第 2 天
        assert is_market_day(5 * 86_400)  # 第 6 天（0 起算每 5 天）


# ---------------------------------------------------------------------------
# RNG 分流 + 熵
# ---------------------------------------------------------------------------


class TestRng:
    def test_streams_independent(self):
        """流 A 大量抽签不得改变流 B 的序列——回放一致性的根基。"""
        reg = RngRegistry(world_seed=42)

        def seq_b() -> list[float]:
            cache: dict = {}
            g = reg.generator("world.weather", cache)
            return [g.random() for _ in range(5)]

        baseline_b = seq_b()
        # 流 A 消耗大量抽签
        cache_a: dict = {}
        gen_a = reg.generator("combat.critical", cache_a)
        _ = [gen_a.random() for _ in range(10_000)]
        # 流 B 序列不受影响
        assert seq_b() == baseline_b

    def test_seeded_reproducible(self):
        reg = RngRegistry(world_seed=42)
        g1 = reg.generator("combat.critical", {})
        g2 = RngRegistry(world_seed=42).generator("combat.critical", {})
        assert [g1.random() for _ in range(4)] == [g2.random() for _ in range(4)]

    def test_reseed_changes_stream(self):
        reg = RngRegistry(world_seed=42)
        g1 = reg.generator("world.weather", {})
        before = g1.random()
        reg2 = reg.reseed("world.weather", b"\xff" * 16)
        g2 = reg2.generator("world.weather", {})
        assert g2.random() != before

    def test_entropy_roundtrip_replay(self):
        """注入 → 用事件材料重放 → 注册表一致。"""
        mixer = EntropyMixer(rng=RngRegistry(world_seed=7))
        mixer2, event = mixer.mix("world.weather", tick=10)
        assert event.event_type is EventKind.ENTROPY_INJECT
        replayed = mixer.replay_mix(
            stream=str(event.payload["stream"]),
            material_hex=str(event.payload["material"]),
        )
        assert replayed.rng.draw_key("world.weather") == mixer2.rng.draw_key("world.weather")


# ---------------------------------------------------------------------------
# 事件 / 唯一写路径
# ---------------------------------------------------------------------------


class TestEvents:
    def test_frozen_event(self):
        ev = WorldEvent(tick=1, event_type=EventKind.MOVE, payload={"entity_id": "x"})
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ev.tick = 5

    def test_unregistered_kind_rejected(self):
        from sim.core.world import EventBus as RealEventBus

        bus2 = RealEventBus()
        with pytest.raises(ValueError, match="未注册的事件种类"):
            bus2.apply(
                WorldState(),
                WorldEvent(tick=0, event_type=EventKind.MOVE),
                __import__("sim.core.world", fromlist=["TickContext"]).TickContext(),
            )

    def test_future_event_rejected(self):
        loop = make_loop()
        with pytest.raises(ValueError, match="事件来自未来"):
            loop.enqueue(
                WorldEvent(tick=999, event_type=EventKind.MOVE, payload={"entity_id": "chenmo"})
            )

    def test_create_only_on_blank(self):
        loop = make_loop()
        with pytest.raises(ValueError, match="创世事件只能作用于空白世界状态"):
            loop.enqueue(WorldEvent(tick=1, event_type=EventKind.WORLD_CREATE, payload={"seed": 1}))


# ---------------------------------------------------------------------------
# 地图 / 寻路
# ---------------------------------------------------------------------------


class TestMap:
    def test_walkable_bounds_and_chunk(self):
        tm = make_open_map()
        assert tm.is_walkable(0, 0)
        assert tm.is_walkable(31, 31)
        assert not tm.is_walkable(-1, 0)
        assert not tm.is_walkable(32, 0)
        empty = TileMap(width=1, height=1)  # 无 chunk
        assert not empty.is_walkable(0, 0)


class TestPathfinding:
    def test_straight_line(self):
        pf = Pathfinder(make_open_map())
        path = pf.find((0, 0), (5, 0))
        assert path[0] == (0, 0) and path[-1] == (5, 0)
        assert len(path) == 6

    def test_diagonal_no_corner_cutting(self):
        """对角穿角禁止：(0,0)→(1,1)，若 (1,0) 是墙则必须绕行。"""
        tm = make_open_map(4, 4)
        blocked = tm.chunks[(0, 0)]
        col = list(blocked.collision)
        col[0 * CHUNK_SIZE + 1] = False  # (1,0) 不可通行

        tm2 = tm.model_copy(
            update={
                "chunks": {
                    **tm.chunks,
                    (0, 0): blocked.model_copy(update={"collision": tuple(col)}),
                }
            }
        )
        pf = Pathfinder(tm2)
        path = pf.find((0, 0), (1, 1))
        # 不允许出现 (0,0)→(1,1) 直跳（穿角）；必然绕 (0,1)
        pairs = set(pairwise(path))
        assert ((0, 0), (1, 1)) not in pairs

    def test_cache_invalidate_by_chunk(self):
        tm = make_open_map()
        pf = Pathfinder(tm)
        pf.find((0, 0), (5, 5))
        assert len(pf.cache.entries) == 1
        # 失效一个不相关的 chunk → 不误伤
        far = (99, 99)
        assert pf.cache.invalidate(far) == 0
        # 失效路径途经的 chunk → 剔除
        chunk_of_path = tm.chunk_of(2, 2)
        assert pf.cache.invalidate(chunk_of_path) == 1

    def test_unreachable_raises(self):
        """目标在无 chunk 区域 → 不可达。"""
        pf = Pathfinder(make_open_map(4, 4))
        with pytest.raises(ValueError, match=r"\(100, 100\)"):
            pf.find((0, 0), (100, 100))


# ---------------------------------------------------------------------------
# T2 核心：回放逐位一致
# ---------------------------------------------------------------------------


def run_scenario(seed: int) -> str:
    """固定脚本：创世 → 移动 → 熵注入 → 继续移动 → N tick → 状态哈希。"""
    loop = make_loop(seed=seed)
    pf = Pathfinder(make_open_map())
    path = pf.find((2, 2), (10, 8))
    loop.issue_move("chenmo", list(path))
    mixer = EntropyMixer(rng=RngRegistry(world_seed=seed))
    _mixer2, ev = mixer.mix("world.weather", tick=loop.state.tick + 1)
    loop.enqueue(ev)
    loop.advance_frame(2.0)  # 120 tick @1x
    return loop.state.state_hash()


class TestReplay:
    def test_same_seed_same_hash(self):
        assert run_scenario(42) == run_scenario(42)

    def test_different_seed_different_hash(self):
        # 熵材料来自 os.urandom，不同运行材料必然不同 → 哈希应不同
        # （若相同说明熵注入没有进入确定性链路——C5 被破坏）
        assert run_scenario(42) != run_scenario(7)

    def test_full_tick_advance_deterministic(self):
        """无熵路径：同 seed 两次跑到相同 tick，哈希与 tick 均一致。"""

        def run() -> tuple[int, str]:
            loop = make_loop(seed=99)
            pf = Pathfinder(make_open_map())
            loop.issue_move("chenmo", list(pf.find((2, 2), (7, 9))))
            loop.advance_frame(1.5)
            return loop.state.tick, loop.state.state_hash()

        assert run() == run()


# ---------------------------------------------------------------------------
# codex 评审补强（2026-09-19）：payload schema 化 + 战斗尺事件
# ---------------------------------------------------------------------------


class TestPayloadSchema:
    def test_move_payload_rejects_extra_fields(self):
        """白名单外字段被拒绝（extra=forbid）——LLM/玩家不可夹带键值。"""
        from pydantic import ValidationError

        from sim.core.events import MovePayload

        with pytest.raises(ValidationError):
            MovePayload.model_validate(
                {
                    "entity_id": "chenmo",
                    "start": [0, 0],
                    "goal": [1, 1],
                    "path": [[0, 0], [1, 1]],
                    "speed_hack": 999,  # 白名单外
                }
            )

    def test_move_event_consistency(self):
        """path 首/末与 start/goal 不一致 → 工厂拒绝。"""
        from sim.core.events import move_event

        with pytest.raises(ValueError, match="路径与起终点不一致"):
            move_event(tick=1, actor_id="x", start=(0, 0), goal=(5, 5), path=((0, 0), (1, 1)))

    def test_combat_scale_event_registered(self):
        """战斗尺切换事件：入日志 + 状态层可 apply（codex 意见 1）。"""
        loop = make_loop()
        ev = combat_scale_event(tick=loop.state.tick + 1, entering=True)
        loop.enqueue(ev)
        loop.drain_events()
        assert ev.event_type is EventKind.COMBAT_SCALE_CHANGE

    def test_issue_combat_scale_switches_clock(self):
        """issue_combat_scale：clock 即时切 + 事件落 pending。"""
        loop = make_loop()
        loop.issue_combat_scale(entering=True)
        assert loop.clock.timescale is TimeScale.COMBAT
        assert loop.context.combat_active is True
        events = loop.drain_events()
        assert any(e.event_type is EventKind.COMBAT_SCALE_CHANGE for e in events)
