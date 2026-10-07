"""M7 协议 1.3：time 块与 ground_b64。

设计：docs/arch/m7-render-art.md §2.2（R1 地面走 HTTP / R3 时钟权威帧）。
出戏边界：time 只含戏内事实五键；禁键（tick/seed/branch）照旧零出站。
"""

import base64
import json
import struct

import pytest

from sim.api.ws import (
    _PROTOCOL_VERSION,
    delta_payload,
    map_static_payload,
    session_state_payload,
    snapshot_payload,
)
from sim.world.map import CHUNK_SIZE, Chunk, TileMap

pytestmark = pytest.mark.t1


@pytest.fixture()
def tile_map() -> TileMap:
    chunks = {
        (0, 0): Chunk(
            cx=0,
            cy=0,
            ground=tuple(range(CHUNK_SIZE * CHUNK_SIZE)),
            collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
        ),
    }
    return TileMap(width=CHUNK_SIZE, height=CHUNK_SIZE, chunks=chunks)


@pytest.fixture()
def loop():
    from sim.api.main import _make_clock
    from sim.core.events import world_create_event
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState, build_default_bus

    lp = TickLoop(clock=_make_clock(), bus=build_default_bus(), state=WorldState(world_seed=42))
    lp.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
    lp.drain_events()
    return lp


class TestTimePayload:
    def test_time_payload_shape(self):
        from sim.api.ws import _time_payload

        # tick = 6h30m = 6*3600 + 30*60 = 23400 → day 1, 06:30, dawn；day1=集市日
        t = _time_payload(23_400)
        assert t == {
            "day": 1,
            "hour": 6,
            "minute": 30,
            "phase": "dawn",
            "is_market_day": True,
        }

    def test_time_phases(self):
        from sim.api.ws import _time_payload

        assert _time_payload(7 * 3600)["phase"] == "day"
        assert _time_payload(17 * 3600)["phase"] == "dusk"
        assert _time_payload(23 * 3600)["phase"] == "night"
        assert _time_payload(0)["phase"] == "night"

    def test_market_day_interval(self):
        from sim.api.ws import _time_payload

        # day = floor(tick/86400)+1；集市日 (day-1)%5==0 → day1/6/11
        assert _time_payload(0)["is_market_day"] is True  # day 1
        assert _time_payload(86_400)["is_market_day"] is False  # day 2
        assert _time_payload(5 * 86_400)["is_market_day"] is True  # day 6


class TestSnapshotTime:
    def test_snapshot_has_time(self, loop, tile_map):
        payload = snapshot_payload(loop, tile_map)
        assert payload["time"] == {
            "day": 1,
            "hour": 0,
            "minute": 0,
            "phase": "night",
            "is_market_day": True,
        }

    def test_delta_has_time(self, loop):
        loop.issue_move("chenmo", [(1, 0), (2, 0)])
        loop.advance_frame(1.0)
        payload = delta_payload(loop, loop.drain_delta())
        assert set(payload["time"].keys()) == {"day", "hour", "minute", "phase", "is_market_day"}

    def test_session_state_has_time(self):
        payload = session_state_payload(speed=1, paused=False, tick=0)
        assert set(payload["time"].keys()) == {"day", "hour", "minute", "phase", "is_market_day"}

    def test_session_state_without_tick_no_time(self):
        """tick=None（旧调用点）不带 time 键——可选字段不制造噪声。"""
        payload = session_state_payload(speed=1, paused=False)
        assert "time" not in payload


class TestOutboundClean:
    """time 块不触禁键；禁键照旧零出现（文本扫描）。"""

    def test_time_block_clean(self, loop, tile_map):
        text = json.dumps(snapshot_payload(loop, tile_map))
        assert "tick" not in text
        assert "seed" not in text
        assert "branch" not in text
        assert '"time"' in text  # 剥除闸没把 time 吃掉

    def test_version_at_least_13(self):
        """1.3 = M7 time 块与 ground_b64 引入版；后续 minor（1.4=D10 actor.name）
        向后兼容——钉「不得回退到 1.3 之前」，不钉死具体版号（升版免改本钉）。"""
        major, minor = (int(p) for p in _PROTOCOL_VERSION.split("."))
        assert (major, minor) >= (1, 3)


class TestGroundB64:
    def test_ground_b64_u16le(self, tile_map):
        raw = map_static_payload(tile_map)
        chunk = raw["chunks"][0]
        data = base64.b64decode(chunk["ground_b64"])
        assert len(data) == CHUNK_SIZE * CHUNK_SIZE * 2  # u16
        first = struct.unpack_from("<H", data, 0)[0]
        assert first == 0  # ground=tuple(range(...)) 首格
        second = struct.unpack_from("<H", data, 2)[0]
        assert second == 1

    def test_collision_b64_unchanged(self, tile_map):
        """碰撞位口径不变（M0 既有契约不回退）。"""
        raw = map_static_payload(tile_map)
        chunk = raw["chunks"][0]
        bits = base64.b64decode(chunk["collision_b64"])
        assert len(bits) == CHUNK_SIZE * CHUNK_SIZE
        assert all(b == 1 for b in bits)

    def test_world_map_response_schema_has_ground(self):
        from sim.api.main import MapChunk, WorldMapResponse

        assert "ground_b64" in MapChunk.model_fields
        assert "collision_b64" in MapChunk.model_fields
        wm_props = WorldMapResponse.model_json_schema()["$defs"]["MapChunk"]["properties"]
        assert "ground_b64" in wm_props


class TestTilesetName:
    """C-1 回归钉：真实图带图集名（前端瓦片渲染开关），占位图恒 grid。"""

    def test_town_map_carries_tileset_name(self):
        from sim.api.main import _default_map
        from sim.api.ws import map_static_payload

        raw = map_static_payload(_default_map())
        assert raw["tileset"] == "zelda_like_v1"

    def test_fallback_map_stays_grid(self, monkeypatch, tmp_path):
        import sim.api.main as main_mod
        from sim.api.ws import map_static_payload

        monkeypatch.setattr(main_mod, "TOWN_MAP_PATH", tmp_path / "no.json")
        raw = map_static_payload(main_mod._default_map())
        assert raw["tileset"] == "grid"

    def test_tileset_name_by_size(self):
        from sim.api.ws import _tileset_name
        from sim.world.map import TileMap

        assert _tileset_name(TileMap(width=48, height=48)) == "zelda_like_v1"
        assert _tileset_name(TileMap(width=32, height=32)) == "grid"
