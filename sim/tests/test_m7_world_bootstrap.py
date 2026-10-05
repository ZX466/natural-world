"""M7 世界引导：真实地图加载（fail-safe 回退）+ 创世 4 实体落可走格。

设计：docs/arch/m7-render-art.md §2.3 R7（创世村民）。
出生点搬运走**事件**（move 事件经 issue_move，C4 唯一写路径）——
创世 (0,0) → SPAWN (8,8) 的路径段事件在 build_loop 创世后同 tick 入队。
"""

import pytest

pytestmark = pytest.mark.t1

SPAWN = (8, 8)
GENESIS = {"chenmo", "villager_1", "villager_2", "villager_3"}


class TestDefaultMap:
    def test_loads_town_map(self):
        from sim.api.main import _default_map

        m = _default_map()
        assert m.width == 48 and m.height == 48
        assert m.is_walkable(*SPAWN)
        assert not m.is_walkable(0, 0)  # 树林墙

    def test_fallback_on_missing_file(self, monkeypatch, tmp_path):
        """文件缺失回退 32×32 占位（fail-safe：启动不炸）。"""
        import sim.api.main as main_mod

        monkeypatch.setattr(main_mod, "TOWN_MAP_PATH", tmp_path / "nonexistent.json")
        m = main_mod._default_map()
        assert m.width == 32  # 占位图

    def test_fallback_on_corrupt_file(self, monkeypatch, tmp_path):
        """文件损坏（非法 JSON）同样回退占位。"""
        import sim.api.main as main_mod

        bad = tmp_path / "broken.json"
        bad.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(main_mod, "TOWN_MAP_PATH", bad)
        m = main_mod._default_map()
        assert m.width == 32


class TestGenesis:
    def test_build_loop_four_entities_on_spawn(self):
        """创世 4 实体、全部落在 SPAWN（事件搬运后）。"""
        import asyncio

        from sim.api.main import build_loop

        loop, _store = asyncio.run(build_loop())
        assert set(loop.state.entities.keys()) == GENESIS
        for eid in GENESIS:
            assert loop.state.entities[eid].pos == SPAWN, f"{eid} 未落出生点"

    def test_spawn_tile_walkable(self):
        from sim.api.main import _default_map

        assert _default_map().is_walkable(*SPAWN)
