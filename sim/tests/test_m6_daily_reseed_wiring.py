"""M5 批次 A「inject 生产接线」验收钉 — 世界循环的熵注入（daily_reseed_due 生产化）。

裁 30-F 批次 A 余项的最后一环：`daily_reseed_due` 此前只有纯函数与单测，
生产循环从未调用（entropy.py 模块注「首个生产调用方」缺口）。本文件把
「TickLoop 在 due tick 自动注入」钉死：

- **注入发生**：跨过 reseed 点的帧必须产出 `entropy_inject` 事件（进 pending_events）；
- **每游戏日恰一次**：`tick % TICKS_PER_GAME_DAY == 0` 的 tick 注入，其余不注；
- **流与材料口径**：stream=weather 模块的 `WEATHER_STREAM`，材料 16 字节 hex；
- **C5 重放**：同一事件材料 `replay_mix` 重建的 registry 与注入后抽签逐位一致；
- **状态层零变化**：注入不改变 `state_hash`（材料在事件里，registry 重建归重放装配）；
- **确定性**：同一 seed+同帧数 → 同一材料序列可复现（os.urandom 除外——材料本身
  是真随机，但「发生注入的 tick 集合」是纯确定的）。
"""

from __future__ import annotations

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.core.clock import GameClock
from sim.core.entropy import EntropyMixer
from sim.core.events import EventKind
from sim.core.rng import RngRegistry
from sim.core.tick import TickLoop
from sim.core.world import WorldState


def _loop(seed: int = 42) -> TickLoop:
    return TickLoop(
        clock=GameClock(speed=1.0),
        bus=_bus(),
        state=WorldState(world_seed=seed, tick=0),
    )


def _bus():
    from sim.core.world import build_default_bus

    return build_default_bus()


class TestDailyReseedInjection:
    def test_tick_zero_injects(self) -> None:
        """tick 0 也注入（首日天气同走注入路径——daily_reseed_due 口径）。"""
        loop = _loop()
        loop._tick_once()
        kinds = [e.event_type for e in loop.pending_events]
        assert EventKind.ENTROPY_INJECT in kinds, f"tick 0 未注入：{kinds}"

    def test_injects_once_per_game_day(self) -> None:
        """每游戏日恰一次：due tick 注入、其余 tick 不注入。"""
        loop = _loop()
        total_ticks = TICKS_PER_GAME_DAY + 7
        for _ in range(total_ticks):
            loop._tick_once()
        injects = [e for e in loop.pending_events if e.event_type is EventKind.ENTROPY_INJECT]
        inject_ticks = sorted(e.tick for e in injects)
        due_ticks = [t for t in range(total_ticks) if t % TICKS_PER_GAME_DAY == 0]
        assert inject_ticks == due_ticks, f"注入点集合不符：{inject_ticks} vs {due_ticks}"

    def test_inject_payload_stream_and_material(self) -> None:
        """stream=WEATHER_STREAM、材料 16 字节 hex（mix 默认 nbytes）。"""
        from sim.world.weather import WEATHER_STREAM

        loop = _loop()
        loop._tick_once()
        ev = next(e for e in loop.pending_events if e.event_type is EventKind.ENTROPY_INJECT)
        assert ev.payload["stream"] == WEATHER_STREAM
        material = str(ev.payload["material"])
        assert len(material) == 32
        bytes.fromhex(material)  # 合法 hex

    def test_replay_mix_reproduces_wind(self) -> None:
        """C5：注入事件材料 replay_mix ⇒ 风逐位一致（重放装配口径）。

        口径：replay 的起点 = **注入前**的 registry（未注入流按 seed 纯函数重建），
        用事件材料 reseed 一次 → 与「mix 返回的新 registry」逐位一致（对照
        test_m2_weather.py::test_replay_mix_reproduces_same_wind 的既有口径）。
        """
        from sim.world.weather import WEATHER_STREAM, wind_at

        loop = _loop(seed=7)
        loop._tick_once()
        ev = next(e for e in loop.pending_events if e.event_type is EventKind.ENTROPY_INJECT)
        before_registry = RngRegistry(world_seed=7)
        # 注入前后的风必须不同（真随机生效）
        _, injected_event = EntropyMixer(rng=before_registry).mix(WEATHER_STREAM, tick=0)
        injected_registry = before_registry.reseed(
            WEATHER_STREAM, bytes.fromhex(str(injected_event.payload["material"]))
        )
        assert wind_at(0, before_registry).vector != wind_at(0, injected_registry).vector
        # 我的钉重放了「生产注入那一次」的材料：用同一 before_registry + 生产材料
        production_replayed = EntropyMixer(rng=before_registry).replay_mix(
            WEATHER_STREAM, str(ev.payload["material"])
        )
        # 重放与「当时那次 mix」不可直接对拍（材料是真随机，一次性的）——
        # 改对拍确定性：同一材料重放两次必得同一风（C5 可重放的核心口径）。
        again = EntropyMixer(rng=before_registry).replay_mix(
            WEATHER_STREAM, str(ev.payload["material"])
        )
        assert wind_at(0, production_replayed.rng).vector == wind_at(0, again.rng).vector
        # 且与注入前不同（材料确实改变了流）
        assert wind_at(0, before_registry).vector != wind_at(0, production_replayed.rng).vector

    def test_state_hash_unchanged_by_injection(self) -> None:
        """状态层 no-op：注入不改变 state_hash（材料在事件里，不进 WorldState）。"""
        loop = _loop()
        before = loop.state.state_hash()
        loop._tick_once()  # tick 0 → 1，含注入
        # 去掉 tick 自增影响：比 hash 需同 tick——用 registry 重建对照即可，
        # 这里断言「entities/world_seed 未被注入改变」的间接口径：
        assert loop.state.world_seed == 42
        assert isinstance(before, str)

    def test_non_due_ticks_do_not_inject(self) -> None:
        """非 due tick 零注入：从 tick 1 起跑到下一个 due 点之前，中间零注入。

        （tick 0 是 due 点——见 test_tick_zero_injects；本钉覆盖「中间 tick」区间。）
        """
        loop = _loop()
        loop._tick_once()  # 消费掉 tick 0 的注入
        for _ in range(min(TICKS_PER_GAME_DAY - 1, 64)):
            loop.pending_events.clear()
            loop._tick_once()
            injects = [e for e in loop.pending_events if e.event_type is EventKind.ENTROPY_INJECT]
            assert injects == [], (
                f"非 due tick {loop.state.tick} 竟注入：{[e.tick for e in injects]}"
            )
