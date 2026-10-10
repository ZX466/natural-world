"""M7 小镇地图：调色板值域钉 + 可加载性 + 结构判据。

设计：docs/arch/m7-render-art.md §3（R5 调色板单源 / R6 确定性构建）。
"""

import json
from pathlib import Path

import pytest

from sim.world.map import TileMap

pytestmark = pytest.mark.t1

REPO = Path(__file__).resolve().parents[2]
TOWN_JSON = REPO / "sim" / "content" / "linhe-town.json"
PALETTE = REPO / "client" / "public" / "assets" / "tilesets" / "sprout-palette.json"


@pytest.fixture(scope="module")
def town() -> TileMap:
    return TileMap.from_json_file(TOWN_JSON)


@pytest.fixture(scope="module")
def palette_ground_ids() -> set[int]:
    return set(json.loads(PALETTE.read_text(encoding="utf-8"))["ground"].values())


class TestTownMap:
    def test_dimensions_96(self, town: TileMap):
        assert town.width == 96 and town.height == 96

    def test_ground_ids_within_palette(self, town: TileMap, palette_ground_ids: set[int]):
        """R5 防漂移钉：地图引用的每个 tile id 必须在调色板值域内。"""
        used: set[int] = set()
        for chunk in town.chunks.values():
            used.update(chunk.ground)
        unknown = used - palette_ground_ids
        assert not unknown, f"地图使用了调色板外的 tile id: {sorted(unknown)}"

    def test_spawn_walkable(self, town: TileMap):
        """主角出生点 (16,32) 可通行（build_town SPAWN 同源依赖，D16 扩图）。"""
        assert town.is_walkable(16, 32)

    def test_border_impassable(self, town: TileMap):
        """四周树林墙：边界格不可走（防走出图）。"""
        for i in range(96):
            assert not town.is_walkable(i, 0)
            assert not town.is_walkable(i, 95)
            assert not town.is_walkable(0, i)
            assert not town.is_walkable(95, i)

    def test_has_variety(self, town: TileMap):
        """至少 6 种不同 tile（草变体+路+水+农田+建筑，防「全草地」退化）。"""
        seen: set[int] = set()
        for chunk in town.chunks.values():
            seen.update(chunk.ground)
        assert len(seen) >= 6

    def test_deterministic_build(self):
        """R6：重跑构建产物逐字节一致（确定性）。"""
        import subprocess
        import sys

        before = TOWN_JSON.read_bytes()
        subprocess.run(
            [sys.executable, str(REPO / "sim" / "content" / "build_town.py")],
            capture_output=True,
            check=True,
        )
        assert TOWN_JSON.read_bytes() == before, "build_town.py 重跑产物漂移"
