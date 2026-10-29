"""test_terrain_class.py — 地形单一真相源的行为钉。

背景（2026-10-28 用户报告四症状）: 障碍可穿过 / 移动局限 / 只挖不放，
根因是碰撞与渲染高度各自独立推导、互不一致。本模块把二者统一。
这些测试锁住「同源」这一不变量，防止回归。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim.content.terrain_class import (
    HEIGHT_EARTH,
    HEIGHT_STONE,
    HEIGHT_WATER,
    HEIGHT_WOOD,
    classify,
    neighbours,
    smooth,
    tile_features,
)

_REPO = Path(__file__).resolve().parents[2]
_PACK = _REPO / "sim" / "content" / "assets" / "god-packs" / "taohuayuan-online"


# --- 特征提取 ---------------------------------------------------------------


def _solid(rgba: tuple[int, int, int, int]) -> list[list[tuple[int, int, int, int]]]:
    return [[rgba] * 16 for _ in range(16)]


def test_tile_features_bright_tan_is_walk():
    """土路/铺地：亮、暖、低饱和 → walk 占比高。"""
    walk, canopy, water = tile_features(_solid((180, 160, 120, 255)))
    assert walk > 0.95
    assert canopy == 0.0
    assert water == 0.0


def test_tile_features_blue_is_water():
    walk, _canopy, water = tile_features(_solid((50, 120, 200, 255)))
    assert water > 0.95
    assert walk == 0.0


def test_tile_features_green_is_canopy():
    walk, canopy, _water = tile_features(_solid((40, 90, 30, 255)))
    assert canopy > 0.95
    assert walk == 0.0


def test_tile_features_dark_is_neither():
    """屋顶/木墙：暗 → 既不算可走也不算树冠。"""
    walk, canopy, water = tile_features(_solid((60, 50, 45, 255)))
    assert walk == 0.0
    assert canopy == 0.0
    assert water == 0.0


# --- 平滑 -------------------------------------------------------------------


def test_smooth_preserves_uniform_field():
    field = [0.5] * (5 * 5)
    out = smooth(field, 5, 5, rounds=3)
    assert all(abs(v - 0.5) < 1e-9 for v in out)


def test_smooth_is_deterministic():
    field = [float(i % 7) / 7 for i in range(6 * 4)]
    assert smooth(field, 6, 4) == smooth(field, 6, 4)


def test_smooth_removes_isolated_speck():
    """单点噪声在平滑后应被邻居稀释（画面语义是空间连贯的）。"""
    w = h = 9
    field = [0.0] * (w * h)
    field[4 * w + 4] = 1.0
    out = smooth(field, w, h, rounds=4)
    assert out[4 * w + 4] < 0.2


# --- 分类同源不变量（核心） -------------------------------------------------


def _toy_map() -> tuple[list[int], dict[int, tuple[float, float, float]], int, int]:
    """四象限玩具图：土 / 石 / 木 / 水，各占一个 8x8 象限。

    必须显著大于平滑窗口（5x5），否则四个象限会被均值混成一个值。
    """
    w = h = 16
    gids: list[int] = []
    samples = {
        1: (1.0, 0.0, 0.0),  # 全亮 → 土
        2: (0.0, 0.0, 0.0),  # 全暗 → 石
        3: (0.0, 1.0, 0.0),  # 全树冠 → 木
        4: (0.0, 0.0, 1.0),  # 全水 → 水
    }
    half = w // 2
    for y in range(h):
        for x in range(w):
            left, top = x < half, y < half
            gids.append(1 if left and top else 2 if not left and top else 3 if left else 4)
    return gids, samples, w, h


def test_walkable_is_always_earth_height():
    """核心不变量（单向）：可走格必是 EARTH——渲染高度不得高于可走面。

    反向不成立：土坎（阻挡但材质是土）也标 EARTH，它可挖不可走。
    这是 earth 的唯一来源，双向化会让 earth 永不产出 → 只挖不放。
    """
    gids, samples, w, h = _toy_map()
    heights, walkable, _stats = classify(gids, samples, w, h)
    for i in range(w * h):
        if walkable[i]:
            assert heights[i] == HEIGHT_EARTH, f"可走格 {i} 高度 {heights[i]} 会穿模"


def test_classify_produces_all_four_roles():
    gids, samples, w, h = _toy_map()
    heights, _walk, stats = classify(gids, samples, w, h)
    assert stats["earth"] > 0
    assert stats["stone"] > 0
    assert stats["wood"] > 0
    assert stats["water"] > 0
    assert set(heights) <= {HEIGHT_WATER, HEIGHT_EARTH, HEIGHT_STONE, HEIGHT_WOOD}


def test_water_never_walkable():
    """水面永不可走——即便被列为强制可走格。"""
    gids, samples, w, h = _toy_map()
    water_cells = tuple(i for i, g in enumerate(gids) if g == 4)
    _heights, walkable, _stats = classify(gids, samples, w, h, forced_walkable=water_cells)
    assert not any(walkable[i] for i in water_cells)


def test_forced_walkable_is_carved_and_connected():
    """强制可走格（作者标注的出生点/地标）必须真可走，且接回主网。"""
    gids, samples, w, h = _toy_map()
    # (12,4) 在右上象限（石），分类器判不可走；强制它可走须挖一条通道接回土区
    forced = (4 * w + 12,)
    heights, walkable, stats = classify(gids, samples, w, h, forced_walkable=forced)
    assert walkable[forced[0]], "强制格仍不可走"
    assert stats["carved"] >= 1, "未记录挖通格数"
    assert heights[forced[0]] == HEIGHT_EARTH


def test_earth_banks_exist_so_place_can_ever_succeed():
    """earth 必须有来源：阻挡格里要有「土坎」。

    `place` 消耗目标格材料，而可走格恒为 EARTH；earth 只能从阻挡的
    EARTH 格挖出。若土坎判成 STONE，行囊永远没有土 → place 永久缺料，
    玩家看到的就是「只挖不放」（2026-10-28 用户症状）。
    """
    w, h = 24, 24
    samples = {
        1: (1.0, 0.0, 0.0),  # 亮土面
        2: (0.0, 0.0, 0.0),  # 暗（屋顶/墙）
        3: (0.0, 1.0, 0.0),  # 树冠
        4: (0.0, 0.0, 1.0),  # 水
    }
    gids: list[int] = []
    for y in range(h):
        for x in range(w):
            if x < 8:
                gids.append(1)  # 左侧一整片土面 → 主可走区
            elif x < 16:
                gids.append(2)  # 中间暗区 → 石头
            else:
                gids.append(1 if (x + y) % 2 == 0 else 2)  # 右侧土/石交错
    heights, walkable, stats = classify(gids, samples, w, h)
    assert stats["earth_banks"] > 0, "没有土坎 → earth 无来源，place 必然缺料"
    banks = [i for i in range(w * h) if not walkable[i] and heights[i] == HEIGHT_EARTH]
    assert banks, "土坎未标成 EARTH"
    assert all(not walkable[i] for i in banks), "土坎不应可走"


def test_classify_is_deterministic():
    gids, samples, w, h = _toy_map()
    a = classify(gids, samples, w, h)
    b = classify(gids, samples, w, h)
    assert a == b


def test_neighbours_are_four_connected_and_in_bounds():
    w = h = 5
    for i in range(w * h):
        for j in neighbours(i, w, h):
            assert 0 <= j < w * h
            assert abs((j % w) - (i % w)) + abs((j // w) - (i // w)) == 1


# --- 真实地图契约（原件缺席则 skip） ----------------------------------------


@pytest.mark.skipif(not _PACK.is_dir(), reason="GOD 素材原件区缺席")
def test_real_map_all_landmarks_walkable():
    """真实地图：10 个地标锚点必须可走（LLM 计划文本直接引用这些坐标）。"""
    from sim.content.png_codec import read_png_rgba

    doc = json.loads((_REPO / "sim/content/linhe-town.json").read_text(encoding="utf-8"))
    w, h = doc["width"], doc["height"]
    pack = json.loads((_PACK / "map_pack.json").read_text(encoding="utf-8"))
    tiled = json.loads((_PACK / "tiled-map.json").read_text(encoding="utf-8"))
    layers = {ly["name"]: ly["data"] for ly in tiled["layers"] if ly.get("type") == "tilelayer"}

    gids = [0] * (w * h)
    for y in range(h):
        for x in range(w):
            gids[y * w + x] = doc["chunks"][f"{x // 16},{y // 16}"]["ground"][
                (y % 16) * 16 + x % 16
            ]

    source = read_png_rgba(_REPO / "client/public/assets/tilesets/god-town-16.png")
    cols = len(source[0]) // 16
    samples = {}
    for g in set(gids):
        if g == 0:
            samples[g] = (0.0, 0.0, 0.0)
            continue
        sx, sy = ((g - 1) % cols) * 16, ((g - 1) // cols) * 16
        samples[g] = tile_features([row[sx : sx + 16] for row in source[sy : sy + 16]])

    forced = tuple(i for i, v in enumerate(layers["Spawning Blocks"]) if v) + tuple(
        loc["anchor_tile"]["y"] * w + loc["anchor_tile"]["x"] for loc in pack["locations"]
    )
    _heights, walkable, stats = classify(gids, samples, w, h, forced_walkable=forced)

    for loc in pack["locations"]:
        ax, ay = loc["anchor_tile"]["x"], loc["anchor_tile"]["y"]
        assert walkable[ay * w + ax], f"{loc['id']} 锚点不可走"

    # 移动空间必须显著大于源包自带的三条直线带（820 格）
    assert stats["walkable"] > 2000, f"可走格过少: {stats['walkable']}"
    # 三种材料都必须存在（V4b 依赖 h=1/2/3）
    assert stats["earth"] > 0 and stats["stone"] > 0 and stats["wood"] > 0
