"""build_god_town.py — GOD 桃花源整图替换转换器（2026-10-12 D6-D10 裁决兑现）。

裁决记录（GOD 地图集成裁决记录 §4 已归档至 git 历史；用户逐项拍板）:
- D6=整图替换（方案 B）——14000/14000 全引用实测否定摘瓦片路径
- D7=压平单层起步
- D8=桃花源底图
- D9=选片区避开瑕疵区（太阳能板/信号塔在西南 signal_hill 带，锚点不选它）
- D10=旧 Zelda 底图退休出运行时，管线保留

实测数据形态（本会话探查，比文档假设更干净）:
- 渲染层只有 Bottom Ground 有内容（100%），其余 9 层全空——GOD 已预压平，
  层压合代码免写；D7 无分支必要
- Collisions 1=阻挡 / 0=可走，但该层与 World Blocks 逐字节相同，只是三条
  贯穿建筑与河道的直线带（820/14000 = 5.9%）——2026-10-28 起不再采用，
  改由 terrain_class 从画面推导（见 extract_collision 文档）
- Spawning Blocks 90 格两簇（行 17-20 / 51-54）

输出:
- sim/content/linhe-town.json（内部格式 140×100 = 70 chunks，TileMap 可加载）
- client/public/assets/tilesets/god-town-16.png（4480×3200 → 2240×1600 缩半）
- 确定性：无随机/无时间依赖，重跑逐字节一致（C5）

零 Pillow 依赖（同 build_god_characters.py——zlib+struct 解 PNG，最近邻缩半）。
"""

from __future__ import annotations

import json
from pathlib import Path

from sim.content.png_codec import read_png_rgba, write_png_rgba

REPO = Path(__file__).resolve().parents[2]
PACK_DIR = REPO / "sim" / "content" / "assets" / "god-packs" / "taohuayuan-online"
OUT_MAP = REPO / "sim" / "content" / "linhe-town.json"
OUT_TILESET = REPO / "client" / "public" / "assets" / "tilesets" / "god-town-16.png"
#: 高度图产物（等距渲染高度 + V4b 材料档；与碰撞同源，见 derive_terrain）
HEIGHT_OUT = REPO / "client" / "public" / "assets" / "tilesets" / "linhe-height.json"

MAP_W = 140
MAP_H = 100
TILE = 16  # 临河镇运行时格尺寸（源 32px 缩半）
CHUNK = 16  # 内部格式 chunk 边长（TileMap.from_json_file 约定）

# --- 常量：GOD 语义层名（实测唯一有内容的渲染层） ---------------------------

GROUND_LAYER = "Bottom Ground"
SPAWN_LAYER = "Spawning Blocks"  # 1=出生候选格
#: 地标锚点来源（10 个地点的 anchor_tile；LLM 计划文本直接引用这些坐标）
PACK_META = "map_pack.json"


def load_tiled_map() -> dict:
    """读 Tiled JSON（原件区，只读）。"""
    with PACK_DIR.joinpath("tiled-map.json").open(encoding="utf-8") as f:
        return json.load(f)


def extract_ground(tiled: dict) -> list[list[int]]:
    """Bottom Ground → 140×100 gid 矩阵（行优先，-1 表示空）。"""
    data = next(ly for ly in tiled["layers"] if ly["name"] == GROUND_LAYER)["data"]
    return [[data[y * MAP_W + x] for x in range(MAP_W)] for y in range(MAP_H)]


def extract_collision(walkable_flat: list[bool]) -> list[list[int]]:
    """可走性 → 临河镇语义矩阵（1=可走 / 0=阻挡）。

    **不读源包 `Collisions` 层。** 该层与 `World Blocks` 逐字节相同，只画了
    三条贯穿建筑与河道的直线带（820/14000 格），既不是美术对齐的碰撞，也不是
    可行走区域——2026-10-28 用户报告的「障碍物可以穿过 / 移动特别局限 /
    只挖不放」三个症状都由它派生。

    真正的可走性由 `sim.content.terrain_class.classify` 从画面推导，与渲染高度
    同源；本函数只做形状转换。`walkable_flat` 为行主序 w*h 布尔。
    """
    return [[1 if walkable_flat[y * MAP_W + x] else 0 for x in range(MAP_W)] for y in range(MAP_H)]


def extract_spawn(tiled: dict) -> list[tuple[int, int]]:
    """Spawning Blocks → 出生候选格列表（确定性升序）。"""
    data = next(ly for ly in tiled["layers"] if ly["name"] == SPAWN_LAYER)["data"]
    return [(i % MAP_W, i // MAP_W) for i, t in enumerate(data) if t]


def halve_tileset(png_path: Path, out_path: Path) -> None:
    """tileset-0.png 4480×3200 @32px → 2240×1600 @16px（最近邻缩半）。"""
    pixels = read_png_rgba(png_path)
    h = len(pixels)
    w = len(pixels[0])
    if (w, h) != (4480, 3200):
        msg = f"tileset 尺寸异常: {(w, h)}"
        raise ValueError(msg)
    out_w, out_h = w // 2, h // 2
    canvas = [[pixels[y * 2][x * 2] for x in range(out_w)] for y in range(out_h)]
    write_png_rgba(out_path, out_w, out_h, canvas)


def build_chunks(
    ground: list[list[int]],
    collision: list[list[int]],
) -> dict[str, dict]:
    """140×100 → 内部格式 chunks（ceil 除法：9×7 = 63 个 16×16 chunk）。

    内部格式（TileMap.from_json_file 约定）：chunk 键 "cx,cy"，
    ground = 逐 chunk 16×16 的 gid 拼接行（256 项），
    collision = 16×16 布尔平铺（256 项，True=阻挡）。
    gid 保持 1-based（Tiled 语义，0=空）。
    140/100 非 16 整除：边缘 chunk 越界格 ground=0（哨兵）+ collision=阻挡
    （TileMap.is_walkable 对越界格本就拒行——语义一致，边界兜底双保险）。
    """
    import math

    chunks: dict[str, dict] = {}
    n_cx = math.ceil(MAP_W / CHUNK)
    n_cy = math.ceil(MAP_H / CHUNK)
    for cy in range(n_cy):
        for cx in range(n_cx):
            ground_flat: list[int] = []
            collision_flat: list[int] = []
            for y in range(cy * CHUNK, (cy + 1) * CHUNK):
                for x in range(cx * CHUNK, (cx + 1) * CHUNK):
                    if x < MAP_W and y < MAP_H:
                        ground_flat.append(ground[y][x])
                        collision_flat.append(collision[y][x])
                    else:
                        # 越界格：ground=0（哨兵）+ collision=0（临河镇语义
                        # 0=不可走——2026-10-12 极性翻转后的兜底同步修正）
                        ground_flat.append(0)
                        collision_flat.append(0)
            chunks[f"{cx},{cy}"] = {
                "ground": ground_flat,
                "collision": collision_flat,
            }
    return chunks


def load_landmarks() -> dict[str, tuple[int, int]]:
    """map_pack.json 的 10 个地点锚点（与 _landmarks 字段同源）。"""
    with PACK_DIR.joinpath(PACK_META).open(encoding="utf-8") as f:
        pack = json.load(f)
    return {
        str(loc["id"]): (int(loc["anchor_tile"]["x"]), int(loc["anchor_tile"]["y"]))
        for loc in pack["locations"]
    }


def tile_samples_from_source() -> dict[int, tuple[float, float, float]]:
    """图集每格 16x16 → terrain_class 特征（只采样实际用到的 gid）。"""
    from sim.content.png_codec import read_png_rgba
    from sim.content.terrain_class import tile_features

    source = read_png_rgba(OUT_TILESET)
    if (len(source[0]), len(source)) != (2240, 1600):
        msg = f"expected halved tileset 2240x1600, got {(len(source[0]), len(source))}"
        raise ValueError(msg)
    cols = len(source[0]) // TILE
    samples: dict[int, tuple[float, float, float]] = {0: (0.0, 0.0, 0.0)}
    for gid in range(1, cols * (len(source) // TILE) + 1):
        sx, sy = ((gid - 1) % cols) * TILE, ((gid - 1) // cols) * TILE
        samples[gid] = tile_features([row[sx : sx + TILE] for row in source[sy : sy + TILE]])
    return samples


def derive_terrain(
    ground: list[list[int]],
    spawn: list[tuple[int, int]],
    landmarks: dict[str, tuple[int, int]],
) -> tuple[list[list[int]], list[int], dict[str, int]]:
    """单一真相源：一次分类同时产出 collision 与 heights。"""
    from sim.content.terrain_class import classify

    flat_gids = [ground[y][x] for y in range(MAP_H) for x in range(MAP_W)]
    forced = tuple(y * MAP_W + x for x, y in spawn) + tuple(
        y * MAP_W + x for x, y in landmarks.values()
    )
    heights, walkable, stats = classify(
        flat_gids, tile_samples_from_source(), MAP_W, MAP_H, forced_walkable=forced
    )
    return extract_collision(walkable), heights, stats


def main() -> None:
    tiled = load_tiled_map()
    ground = extract_ground(tiled)
    spawn = extract_spawn(tiled)
    landmarks = load_landmarks()

    halve_tileset(PACK_DIR / "assets" / "tileset-0.png", OUT_TILESET)

    collision, heights, stats = derive_terrain(ground, spawn, landmarks)
    chunks = build_chunks(ground, collision)
    payload = {
        "width": MAP_W,
        "height": MAP_H,
        "tile_size": TILE,
        "source": "god-packs/taohuayuan-online (D6-D8 裁决 2026-10-12)",
        "spawn_candidates": [list(p) for p in spawn],
        "chunks": chunks,
        "_landmarks": {name: list(pos) for name, pos in landmarks.items()},
    }
    OUT_MAP.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    # 高度图与碰撞同源（terrain_class 一次分类的两个投影）。写出格式只有一份，
    # 由 build_height_map.render 提供，避免两处格式漂移导致 --check 失配。
    from sim.content.build_height_map import PREVIEW_PATH, render

    render(MAP_W, MAP_H, heights, HEIGHT_OUT, PREVIEW_PATH)

    print(f"地图: {OUT_MAP} ({MAP_W}x{MAP_H}, {len(chunks)} chunks)")
    print(f"高度: {HEIGHT_OUT}")
    print(f"tileset: {OUT_TILESET} (2240x1600)")
    print(f"出生候选: {len(spawn)} 格")
    print(
        f"地形: 可走 {stats['walkable']} / 土 {stats['earth']} / 石 {stats['stone']} / "
        f"木 {stats['wood']} / 水 {stats['water']} / 挖通 {stats['carved']}"
    )


if __name__ == "__main__":
    main()
