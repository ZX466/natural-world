"""test_build_god_town.py — GOD 桃花源整图替换转换器回归钉（2026-10-12 D6-D10 兑现）。

裁决（GOD 地图集成裁决记录 §4 已归档）: D6=整图替换 / D7=压平单层 /
D8=桃花源 / D9=选片区避开瑕疵区 / D10=旧 Zelda 退休出运行时管线保留。

2026-10-28 变更：可走性不再取源包 `Collisions` 层（那只是三条贯穿建筑与河道
的直线带，820 格 = 5.9%），改由 `terrain_class.classify` 从画面推导，与渲染
高度同源。故「可走 820」的旧钉换成不变量钉：地标/出生点必须可走、可走面
显著大于直线带、walkable ⇔ height==EARTH。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim.content.build_god_town import (
    CHUNK,
    MAP_H,
    MAP_W,
    OUT_TILESET,
    build_chunks,
    derive_terrain,
    extract_ground,
    extract_spawn,
    load_landmarks,
    load_tiled_map,
)
from sim.content.terrain_class import HEIGHT_EARTH
from sim.world.map import TileMap

_REPO = Path(__file__).resolve().parents[2]
_PACK = _REPO / "sim" / "content" / "assets" / "god-packs" / "taohuayuan-online"

#: 旧源包直线带的可走格数——新可走面必须远超它（回归护栏）。
LEGACY_BAND_CELLS = 820

#: 10 地标 anchor（map_pack.json 实测；转换器 _landmarks 同源）
LANDMARK_ANCHORS = {
    "peach_gate": (15, 18),
    "ancestral_hall": (40, 18),
    "stream_bridge": (66, 19),
    "old_school": (93, 19),
    "terraced_fields": (122, 19),
    "signal_hill": (18, 52),
    "guest_yard": (44, 53),
    "craft_market": (72, 52),
    "village_square": (100, 52),
    "archive_room": (124, 52),
}

#: D9 瑕疵区（太阳能板/信号塔）——片区锚点禁选五处（anchor 不落在该角）
D9_EXCLUDED = "signal_hill"


def _tiled() -> dict:
    """原件区 Tiled JSON（缺席 = skip，gitignore 资产 CI 无目录）。"""
    if not _PACK.is_dir():
        pytest.skip("GOD 素材原件区缺席")
    return load_tiled_map()


@pytest.fixture(scope="module")
def terrain() -> tuple[list[list[int]], list[int], dict[str, int]]:
    """同源推导一次（collision, heights, stats）；缺素材/产物则 skip。"""
    if not _PACK.is_dir():
        pytest.skip("GOD 素材原件区缺席")
    if not OUT_TILESET.exists():
        pytest.skip("god-town-16.png 未产出（先跑 build_god_town）")
    tiled = load_tiled_map()
    return derive_terrain(extract_ground(tiled), extract_spawn(tiled), load_landmarks())


# --- 提取层语义钉 ------------------------------------------------------------


def test_ground_layer_full_coverage():
    """Bottom Ground 100% 覆盖（GOD 预压平实证；空格=0 出现即红）。"""
    ground = extract_ground(_tiled())
    assert len(ground) == MAP_H and len(ground[0]) == MAP_W
    assert all(gid > 0 for row in ground for gid in row), "ground 出现空格"


def test_collision_polarity(terrain):
    """极性钉（施工中抓过反转 bug）：临河镇语义 collision=1 才是可走。
    10 地标 anchor 全可走；可走面远超旧直线带。"""
    collision, _heights, stats = terrain
    for name, (x, y) in LANDMARK_ANCHORS.items():
        assert collision[y][x] == 1, f"{name} anchor 不可走"
    assert stats["walkable"] > LEGACY_BAND_CELLS * 2, f"可走面过小: {stats['walkable']}"


def test_walkable_is_always_earth_height(terrain):
    """同源不变量（单向）：可走格高度必为 EARTH，否则渲染出现「高方块却可穿过」。

    反向不成立：土坎是阻挡的 EARTH 格（earth 的唯一来源），故不能双向断言。
    """
    collision, heights, stats = terrain
    for y in range(MAP_H):
        for x in range(MAP_W):
            if collision[y][x] == 1:
                assert heights[y * MAP_W + x] == HEIGHT_EARTH, f"({x},{y}) 可走却画成高块"
    assert stats["earth_banks"] > 0, "没有土坎 → earth 无来源，place 必然缺料"


def test_spawn_candidates(terrain):
    """spawn 候选 90 格且全可走。"""
    collision, _heights, _stats = terrain
    spawn = extract_spawn(_tiled())
    assert len(spawn) == 90
    assert all(collision[y][x] == 1 for x, y in spawn)


# --- chunk 组装钉 ------------------------------------------------------------


def test_build_chunks_covers_full_map(terrain):
    """63 chunks（ceil 除法）覆盖 140×100 全图；边缘 chunk 越界格
    ground=0 + collision=0（不可走）。"""
    ground = extract_ground(_tiled())
    collision, _heights, _stats = terrain
    chunks = build_chunks(ground, collision)
    assert len(chunks) == 63  # ceil(140/16)=9 x ceil(100/16)=7
    assert all(len(c["ground"]) == CHUNK * CHUNK for c in chunks.values())
    assert all(len(c["collision"]) == CHUNK * CHUNK for c in chunks.values())
    # 越界格：chunk (8,0) 的 x=136..143 中 140..143 是越界
    edge = chunks["8,0"]
    for ly in range(CHUNK):
        for lx in range(4):  # 140-136=4..15 越界段
            i = ly * CHUNK + (12 + lx)
            assert edge["ground"][i] == 0
            assert edge["collision"][i] == 0  # 不可走


# --- 产物钉（linhe-town.json 已由 main() 产出；原件缺席时验证既有产物） ------

_PRODUCED = _REPO / "sim" / "content" / "linhe-town.json"


def _tilemap() -> TileMap:
    if not _PRODUCED.exists():
        pytest.skip("linhe-town.json 未产出（先跑 uv run python -m sim.content.build_god_town）")
    return TileMap.from_json_file(_PRODUCED)


def test_tilemap_loads_god_town():
    """转换产物可直接加载：140×100 / 63 chunks / tile_size 16。"""
    m = _tilemap()
    assert (m.width, m.height) == (MAP_W, MAP_H)
    assert len(m.chunks) == 63
    assert m.tile_size == 16


def test_tilemap_walkable_semantics():
    """加载后语义自洽：地标可走 / 可走面显著大于旧直线带 / 越界拒行。"""
    m = _tilemap()
    for name, (x, y) in LANDMARK_ANCHORS.items():
        assert m.is_walkable(x, y), f"{name} 不可走"
    total = sum(1 for x in range(MAP_W) for y in range(MAP_H) if m.is_walkable(x, y))
    assert total > LEGACY_BAND_CELLS * 2, f"可走面过小: {total}"
    assert not m.is_walkable(MAP_W, 50)
    assert not m.is_walkable(-1, 50)


def test_landmarks_pinned_in_json():
    """_landmarks 与 map_pack.json 同源（差事重映射的选点库）。"""
    if not _PRODUCED.exists():
        pytest.skip("产物未生成")
    data = json.loads(_PRODUCED.read_text(encoding="utf-8"))
    assert data["_landmarks"] == {k: list(v) for k, v in LANDMARK_ANCHORS.items()}
    assert D9_EXCLUDED in data["_landmarks"]  # 地标登记≠片区锚点选用（D9 只管锚点）


def test_spawn_candidates_in_json():
    """产物带 spawn_candidates（90 格，与源层一致）。"""
    if not _PRODUCED.exists():
        pytest.skip("产物未生成")
    data = json.loads(_PRODUCED.read_text(encoding="utf-8"))
    assert len(data["spawn_candidates"]) == 90


def test_tileset_halved():
    """缩半 tileset 产物 2240×1600（IHDR 实读）。"""
    if not OUT_TILESET.exists():
        pytest.skip("tileset 产物未生成")
    import struct

    data = OUT_TILESET.open("rb").read(33)
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (2240, 1600)


# --- 确定性钉（C5） ----------------------------------------------------------


def test_conversion_deterministic(terrain):
    """同输入重跑 → chunks 逐字节一致（无随机/无时间依赖）。"""
    ground = extract_ground(_tiled())
    collision, _heights, _stats = terrain
    c1 = build_chunks(ground, collision)
    c2 = build_chunks(ground, collision)
    assert json.dumps(c1, sort_keys=True) == json.dumps(c2, sort_keys=True)
