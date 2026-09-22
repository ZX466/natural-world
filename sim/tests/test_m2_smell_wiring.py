"""M2-A2 第三批：嗅觉通道接线进感知步（m2-npc-cognition §5.1 挂载点）。

契约：
- Channel.SMELL 进感知帧；narrated() 嗅觉分组「你闻到：…」；
- smell_propagate 补 8 邻域扩散（arch §5.1 算法第 2 步；静风时浓度可离开源格）；
- SmellWorld：跨 tick 场持有者（推进 + 批量采样），源=实体持续源（占位常量，
  matter 源 M3 接 MatterLedger），风=weather.wind_at 纯函数派生（档内缓存）；
- 挂载：run_perception_step 视听之后（arch §5.1），TickLoop 零改动（走既有
  attach_perception 钩子）；
- 零元信息：嗅觉描述零数值零系统词；strength 只用于显著性排序。
"""

from __future__ import annotations

import numpy as np

from sim.core.rng import RngRegistry
from sim.core.world import WorldState
from sim.perception import Channel
from sim.perception.frame import Observation, PerceptionFrame
from sim.perception.smell import SmellField, smell_propagate
from sim.perception.smell_world import SMELL_SOURCE_STRENGTH, SmellWorld

GRID = 64
DECAY = np.float32(0.98)
DIFFUSE = 0.1


class TestDiffusion:
    """arch §5.1 算法第 2 步补齐：平流 + 8 邻域扩散。"""

    def test_diffuse_spreads_without_wind(self) -> None:
        """静风 + 扩散：邻格浓度 > 0（无扩散时 roll(0) no-op，浓度困在源格）。"""
        f = SmellField.zeros(grid=GRID).inject(sources=[(32, 32)], strength=10.0)
        f2 = smell_propagate(
            f, sources=[(32, 32)], wind=(0.0, 0.0), strength=10.0,
            decay=DECAY, diffuse_rate=DIFFUSE,
        )
        assert f2.sample((31, 32)) > 0.0
        assert f2.sample((33, 32)) > 0.0

    def test_diffuse_preserves_downwind_order(self) -> None:
        """风 (0,+1)：下风邻格浓度 > 上风邻格（扩散不改变平流方向性）。"""
        f = SmellField.zeros(grid=GRID).inject(sources=[(32, 10)], strength=10.0)
        f2 = smell_propagate(
            f, sources=[(32, 10)], wind=(0.0, 1.0), strength=10.0,
            decay=DECAY, diffuse_rate=DIFFUSE,
        )
        assert f2.sample((32, 11)) > f2.sample((32, 9))

    def test_no_diffuse_by_default(self) -> None:
        """diffuse_rate 缺省 0：既有调用方（pi bench 参考口径）行为不变。"""
        f = SmellField.zeros(grid=GRID).inject(sources=[(32, 32)], strength=10.0)
        f2 = smell_propagate(
            f, sources=[(32, 32)], wind=(0.0, 0.0), strength=10.0, decay=DECAY
        )
        assert f2.sample((31, 32)) == 0.0


class TestSmellWorld:
    """跨 tick 场持有者：推进 + 批量采样（C5 可重放）。"""

    def test_step_advances_field(self) -> None:
        w = SmellWorld(height=GRID, width=GRID)
        s1 = w.step({}, wind=(0.0, 0.0))
        assert s1 == {}
        # 无实体无源：场保持零
        assert float(np.abs(w.field.grid).sum()) == 0.0

    def test_entities_are_sources(self) -> None:
        """源=实体持续源（占位；matter 源 M3 接 MatterLedger）。"""
        w = SmellWorld(height=GRID, width=GRID)
        w.step({"npc:a": (32, 32)}, wind=(0.0, 0.0))
        near = w.field.sample((32, 32))
        far = w.field.sample((5, 5))
        assert near > far
        assert near > 0.0

    def test_sample_maps_entity_ids(self) -> None:
        w = SmellWorld(height=GRID, width=GRID)
        out = w.step({"npc:a": (10, 10), "npc:b": (50, 50)}, wind=(0.0, 0.0))
        assert set(out) == {"npc:a", "npc:b"}
        assert out["npc:a"] > 0.0
        assert out["npc:b"] > 0.0

    def test_replay_same_tick_sequence(self) -> None:
        """C5：同实体序列同风逐步推进 → 场逐位一致。"""
        a = SmellWorld(height=GRID, width=GRID)
        b = SmellWorld(height=GRID, width=GRID)
        ents = {"npc:a": (20, 20), "npc:b": (40, 40)}
        for tick in range(5):
            wind = (1.0, 0.0) if tick % 2 else (0.0, 0.0)
            a.step(ents, wind=wind)
            b.step(ents, wind=wind)
        assert np.array_equal(a.field.grid, b.field.grid)

    def test_field_not_aliased_by_caller(self) -> None:
        """场内部持有；step 返回采样 dict，不暴露可变场引用。"""
        w = SmellWorld(height=GRID, width=GRID)
        out = w.step({"npc:a": (10, 10)}, wind=(0.0, 0.0))
        assert isinstance(out, dict)
        assert "field" not in out


class TestWiring:
    """挂载：run_perception_step 视听之后；帧含 SMELL 观测。"""

    def _state(self, tick: int = 100) -> WorldState:
        from sim.core.world import EntityState

        ents = {
            "alice": EntityState(entity_id="alice", pos=(10, 10)),
            "bob": EntityState(entity_id="bob", pos=(11, 10)),
        }
        return WorldState(world_seed=7, tick=tick, entities=ents)

    def _step(self, state: WorldState):
        from sim.perception.senses import run_perception_step
        from sim.world.map import Chunk, TileMap

        chunks = {
            (0, 0): Chunk(
                cx=0, cy=0,
                ground=(1,) * (GRID * GRID),
                collision=(True,) * (GRID * GRID),
            )
        }
        tile_map = TileMap(width=GRID, height=GRID, chunks=chunks)
        return run_perception_step(state, tile_map, []), tile_map

    def test_frame_contains_smell_observation(self) -> None:
        frames, _ = self._step(self._state())
        frame = frames["rt-" + __import__("hashlib").sha256(b"alice").hexdigest()[:12]]
        smell_obs = [ob for ob in frame.observations if ob.channel is Channel.SMELL]
        assert smell_obs, "帧里应有嗅觉观测（他人贴身，浓度必超地板）"
        assert len(smell_obs) == 1  # subject="smell" 去重：一帧最多一条

    def test_smell_description_zero_meta(self) -> None:
        """零元信息：嗅觉描述零数字、无 rtoken/entity_id 泄漏。"""
        from sim.perception.narrate import narrate_smell

        for conc in (0.2, 1.0, 5.0, 50.0):
            text = narrate_smell(conc)
            assert not any(ch.isdigit() for ch in text), f"嗅觉叙事漏数字: {text}"
            assert "rt-" not in text and "npc" not in text

    def test_smell_no_self_persistence_across_maps(self) -> None:
        """不同 tile_map 实例 = 不同场（测试隔离；生产中图常驻）。"""
        frames1, m1 = self._step(self._state(tick=100))
        frames2, m2 = self._step(self._state(tick=100))
        assert m1 is not m2
        a = frames1[next(iter(frames1))]
        b = frames2[next(iter(frames2))]
        assert isinstance(a, PerceptionFrame) and isinstance(b, PerceptionFrame)


class TestChannelSmell:
    def test_channel_exists(self) -> None:
        assert Channel.SMELL == "smell"

    def test_narrated_groups_smell_last(self) -> None:
        from sim.perception.frame import Channel as C

        frame = PerceptionFrame(
            observer="rt-x",
            tick=0,
            observations=(
                Observation(
                    channel=C.SMELL, subject="smell",
                    description="空气里飘着一股说不清的味道。", strength=0.5,
                ),
                Observation(
                    channel=C.VISION, subject="rt-y",
                    description="rt-y就在不远处。", strength=0.9,
                ),
            ),
        )
        text = frame.narrated()
        assert "你闻到：" in text
        assert text.index("你看到：") < text.index("你闻到：")  # 嗅觉在视听之后


class TestConstants:
    def test_source_strength_positive(self) -> None:
        assert SMELL_SOURCE_STRENGTH > 0.0

    def test_smell_world_accepts_registry_wind(self) -> None:
        """风 = weather.wind_at(rng) 纯派生（档内缓存）；rng 显式传入。"""
        from sim.world.weather import wind_at

        rng = RngRegistry(world_seed=7)
        wind = wind_at(100, rng)
        w = SmellWorld(height=GRID, width=GRID)
        out = w.step({"npc:a": (32, 32)}, wind=wind.vector)
        assert out["npc:a"] > 0.0
