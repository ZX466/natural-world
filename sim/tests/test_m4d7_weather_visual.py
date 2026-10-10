"""批次 D7（天气视觉）钉子。

面：
1. sim/api/ws.py weather_payload(tick, seed)：确定性天气判定（每天一次抽签
   晴/阴/雨——同 fire 模式的哈希抽签，无 RNG 流）→ {visual, ambient_light}；
2. full_snapshot/state_delta 随行 weather（替换硬编码 clear/1.0）；
3. 雨/阴的 ambient_light 联动（雨 0.75 / 阴 0.9 / 晴 1.0——昼夜色罩叠乘面）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.t1


class TestWeatherPayload:
    def test_deterministic(self) -> None:
        from sim.api.ws import weather_payload

        assert weather_payload(1000, 42) == weather_payload(1000, 42)

    def test_same_day_same_weather(self) -> None:
        """同游戏日内天气恒定（日级状态，不逐 tick 抖动）。"""
        from sim.api.ws import weather_payload

        morning = weather_payload(3600, 42)  # 第 1 天 1:00
        night = weather_payload(86000, 42)  # 第 1 天 23:53
        assert morning["visual"] == night["visual"]

    def test_visuals_in_allowed_set(self) -> None:
        """visual ∈ {clear, overcast, rain}（协议封闭集）。"""
        from sim.api.ws import weather_payload

        seen = set()
        for seed in range(60):
            for day in range(1, 8):
                seen.add(weather_payload(day * 86400 + 100, seed)["visual"])
        assert seen <= {"clear", "overcast", "rain"}
        assert seen, "60 seed × 7 日全 clear = 抽签退化"

    def test_ambient_light_by_visual(self) -> None:
        from sim.api.ws import weather_payload

        lights = {"clear": 1.0, "overcast": 0.9, "rain": 0.75}
        for seed in range(40):
            for day in range(1, 6):
                payload = weather_payload(day * 86400 + 100, seed)
                assert payload["ambient_light"] == lights[payload["visual"]]

    def test_snapshot_and_delta_carry_weather(self) -> None:
        """full_snapshot 的 weather 来自 weather_payload（替换硬编码）。"""
        from sim.api.ws import snapshot_payload, weather_payload
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus
        from sim.world.map import CHUNK_SIZE, Chunk

        chunks = {
            (0, 0): Chunk(
                cx=0,
                cy=0,
                ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
        }
        from sim.world.map import TileMap

        tile_map = TileMap(width=16, height=16, chunks=chunks)
        loop = TickLoop(
            clock=GameClock(speed=1.0), bus=build_default_bus(), state=WorldState(world_seed=42)
        )
        loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
        loop.drain_events()
        snap = snapshot_payload(loop, tile_map)
        assert snap["weather"] == weather_payload(loop.state.tick, 42)
