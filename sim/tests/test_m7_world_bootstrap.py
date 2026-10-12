"""M7 世界引导：真实地图加载（fail-safe 回退）+ 创世实体落可走格。

设计：docs/arch/m7-render-art.md §2.3 R7（创世村民）；批次 B 扩容：
世界 = chenmo + 50 村民（villagers.py 名册），出生位确定性环形散布。
出生点搬运走**事件**（move 事件经 issue_move，C4 唯一写路径）——
创世 (0,0) → SPAWN 的路径段事件在 build_loop 创世后同 tick 入队。
"""

import pytest

pytestmark = pytest.mark.t1

SPAWN = (100, 53)  # 2026-10-12 D6-D8 换图：村广场（main.py SPAWN_TILE 同源）
ROSTER = 50


class TestDefaultMap:
    def test_loads_town_map(self):
        from sim.api.main import _default_map

        m = _default_map()
        assert m.width == 140 and m.height == 100  # D6-D8 桃花源整图
        assert m.is_walkable(*SPAWN)
        assert not m.is_walkable(0, 0)  # GOD 图西南角不可走带

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
    def test_build_loop_51_entities_scattered(self):
        """创世 51 实体：主角在 SPAWN，50 村民环形散布（全部错格、可走）。"""
        import asyncio

        from sim.api.main import build_loop

        loop, _store = asyncio.run(build_loop())
        assert len(loop.state.entities) == ROSTER + 4
        assert loop.state.entities["chenmo"].pos == SPAWN
        villager_ids = [k for k in loop.state.entities if k.startswith("villager_")]
        assert len(villager_ids) == ROSTER
        positions = [loop.state.entities[v].pos for v in villager_ids]
        assert len(set(positions)) == ROSTER, "村民必须错格"
        assert SPAWN not in positions, "村民不得与主角同格"
        # 全部落在可走格
        from sim.api.main import _default_map

        m = _default_map()
        for pos in [*positions, SPAWN]:
            assert m.is_walkable(*pos), f"{pos} 不可走"

    def test_spawn_tile_walkable(self):
        from sim.api.main import _default_map

        assert _default_map().is_walkable(*SPAWN)
