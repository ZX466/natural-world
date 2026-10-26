"""M7 小镇地图：尺寸/可走性 + 可加载性 + 结构判据 + 确定性构建。

设计：docs/arch/m7-render-art.md §3（R6 确定性构建）。
2026-10-12 D6-D10 换图：真相源 = build_god_town.py（桃花源整图 140×100）。
Zelda-like 旧图管线（build_town.py / sprout 调色板）已于 2026-10-26 删除，
完整实现可从 git 历史找回；旧 96×96 断言随图退休。
"""

from pathlib import Path

import pytest

from sim.world.map import TileMap

pytestmark = pytest.mark.t1

REPO = Path(__file__).resolve().parents[2]
TOWN_JSON = REPO / "sim" / "content" / "linhe-town.json"
TOWN_SPAWN = (100, 53)  # main.py SPAWN_TILE 同源


@pytest.fixture(scope="module")
def town() -> TileMap:
    return TileMap.from_json_file(TOWN_JSON)


class TestTownMap:
    def test_dimensions_140x100(self, town: TileMap):
        assert town.width == 140 and town.height == 100

    def test_spawn_walkable(self, town: TileMap):
        """主角出生点可通行（main.py SPAWN_TILE 同源依赖）。"""
        assert town.is_walkable(*TOWN_SPAWN)

    def test_ground_no_zero_in_mainland(self, town: TileMap):
        """主图区（140×100 内）ground 无 0 哨兵（Bottom Ground 100% 覆盖实证；
        0 只允许出现在边缘 chunk 的越界兜底格）。"""
        for (cx, cy), chunk in town.chunks.items():
            for ly in range(16):
                for lx in range(16):
                    gx, gy = cx * 16 + lx, cy * 16 + ly
                    if gx < town.width and gy < town.height:
                        assert chunk.ground[ly * 16 + lx] > 0, f"主图区 ({gx},{gy}) ground=0"

    def test_has_variety(self, town: TileMap):
        """至少 6 种不同 tile（整图切片天然满足，防「全同格」退化）。"""
        seen: set[int] = set()
        for chunk in town.chunks.values():
            seen.update(chunk.ground)
        assert len(seen) >= 6

    def test_deterministic_build(self):
        """R6：重跑构建产物逐字节一致（确定性；换图后真相源=build_god_town）。"""
        import subprocess
        import sys

        before = TOWN_JSON.read_bytes()
        subprocess.run(
            [sys.executable, "-m", "sim.content.build_god_town"],
            capture_output=True,
            check=True,
            cwd=REPO,
        )
        assert TOWN_JSON.read_bytes() == before, "build_god_town.py 重跑产物漂移"
