"""test_build_god_town.py — GOD 桃花源整图替换转换器回归钉（2026-10-12 D6-D10 兑现）。

裁决（GOD 地图集成裁决记录 §4 已归档）: D6=整图替换 / D7=压平单层 /
D8=桃花源 / D9=选片区避开瑕疵区 / D10=旧 Zelda 退休出运行时管线保留。

实测数据形态（止损门探查 + 人审通过 2026-10-12）:
- 渲染层唯一有内容 = Bottom Ground（GOD 已预压平，D7 无分支）
- Collisions: 1=阻挡 / 0=可走；临河镇语义 collision=True=可走（取反直转）
- 可走 820 格 / 795 连片 / 10 地标同连通块 / spawn 候选 90 格
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
    extract_collision,
    extract_ground,
    extract_spawn,
    load_tiled_map,
)
from sim.world.map import TileMap

_REPO = Path(__file__).resolve().parents[2]
_PACK = _REPO / "sim" / "content" / "assets" / "god-packs" / "taohuayuan-online"

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


# --- 提取层语义钉 ------------------------------------------------------------


def test_ground_layer_full_coverage():
    """Bottom Ground 100% 覆盖（GOD 预压平实证；空格=0 出现即红）。"""
    ground = extract_ground(_tiled())
    assert len(ground) == MAP_H and len(ground[0]) == MAP_W
    assert all(gid > 0 for row in ground for gid in row), "ground 出现空格"


def test_collision_polarity():
    """极性钉（施工中抓过反转 bug）：临河镇语义 collision=True=可走。
    10 地标 anchor 全可走；全图可走 820。"""
    collision = extract_collision(_tiled())
    walkable = sum(r.count(1) for r in collision)
    assert walkable == 820
    for name, (x, y) in LANDMARK_ANCHORS.items():
        assert collision[y][x] == 1, f"{name} anchor 不可走"


def test_spawn_candidates():
    """spawn 候选 90 格且全可走。"""
    tiled = _tiled()
    spawn = extract_spawn(tiled)
    collision = extract_collision(tiled)
    assert len(spawn) == 90
    assert all(collision[y][x] == 1 for x, y in spawn)


# --- chunk 组装钉 ------------------------------------------------------------


def test_build_chunks_covers_full_map():
    """63 chunks（ceil 除法）覆盖 140×100 全图；边缘 chunk 越界格
    ground=0 + collision=0（不可走）。"""
    tiled = _tiled()
    ground = extract_ground(tiled)
    collision = extract_collision(tiled)
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
    """加载后语义自洽：地标可走 / 可走总数 820 / 越界拒行。"""
    m = _tilemap()
    for name, (x, y) in LANDMARK_ANCHORS.items():
        assert m.is_walkable(x, y), f"{name} 不可走"
    total = sum(1 for x in range(MAP_W) for y in range(MAP_H) if m.is_walkable(x, y))
    assert total == 820
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


def test_conversion_deterministic(tmp_path):
    """同输入重跑 → chunks 逐字节一致（无随机/无时间依赖）。"""
    tiled = _tiled()
    ground = extract_ground(tiled)
    collision = extract_collision(tiled)
    c1 = build_chunks(ground, collision)
    c2 = build_chunks(ground, collision)
    assert json.dumps(c1, sort_keys=True) == json.dumps(c2, sort_keys=True)
