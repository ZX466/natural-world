"""build_god_town.py — GOD 桃花源整图替换转换器（2026-10-12 D6-D10 裁决兑现）。

裁决记录（docs/data/god-map-integration.md §4，用户逐项拍板）:
- D6=整图替换（方案 B）——14000/14000 全引用实测否定摘瓦片路径
- D7=压平单层起步
- D8=桃花源底图
- D9=选片区避开瑕疵区（太阳能板/信号塔在西南 signal_hill 带，锚点不选它）
- D10=旧 Zelda 底图退休出运行时，管线保留

实测数据形态（本会话探查，比文档假设更干净）:
- 渲染层只有 Bottom Ground 有内容（100%），其余 9 层全空——GOD 已预压平，
  层压合代码免写；D7 无分支必要
- Collisions 1=阻挡 / 0=可走（spawn 90/90 全 0 + 10 地标 anchor 全 0 实证；
  可走 820 格连片路网 795 连通，10 地标同块）
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

MAP_W = 140
MAP_H = 100
TILE = 16  # 临河镇运行时格尺寸（源 32px 缩半）
CHUNK = 16  # 内部格式 chunk 边长（build_town.py 同款）

# --- 常量：GOD 语义层名（实测唯一有内容的渲染层） ---------------------------

GROUND_LAYER = "Bottom Ground"
COLLISION_LAYER = "Collisions"  # 1=阻挡 / 0=可走
SPAWN_LAYER = "Spawning Blocks"  # 1=出生候选格


def load_tiled_map() -> dict:
    """读 Tiled JSON（原件区，只读）。"""
    with PACK_DIR.joinpath("tiled-map.json").open(encoding="utf-8") as f:
        return json.load(f)


def extract_ground(tiled: dict) -> list[list[int]]:
    """Bottom Ground → 140×100 gid 矩阵（行优先，-1 表示空）。"""
    data = next(ly for ly in tiled["layers"] if ly["name"] == GROUND_LAYER)["data"]
    return [[data[y * MAP_W + x] for x in range(MAP_W)] for y in range(MAP_H)]


def extract_collision(tiled: dict) -> list[list[int]]:
    """Collisions → 临河镇语义矩阵。

    GOD 语义：1=阻挡 / 0=可走（spawn 90/90 全 0 + 10 地标 anchor 全 0 实证）。
    临河镇语义（实测 sim/world/map.py::Chunk.is_walkable 直接返回
    collision[lx,ly]）：**collision=True=可走**——与 GOD 相反，取反直转。
    （2026-10-12 施工中发现：首版同向直转得全图 13180 可走=反转了，
    TileMap 加载实测抓出。）
    """
    data = next(ly for ly in tiled["layers"] if ly["name"] == COLLISION_LAYER)["data"]
    return [[1 - data[y * MAP_W + x] for x in range(MAP_W)] for y in range(MAP_H)]


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

    内部格式（build_town.py 同款）：chunk 键 "cx,cy"，
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


def main() -> None:
    tiled = load_tiled_map()
    ground = extract_ground(tiled)
    collision = extract_collision(tiled)
    spawn = extract_spawn(tiled)

    chunks = build_chunks(ground, collision)
    payload = {
        "width": MAP_W,
        "height": MAP_H,
        "tile_size": TILE,
        "source": "god-packs/taohuayuan-online (D6-D8 裁决 2026-10-12)",
        "spawn_candidates": [list(p) for p in spawn],
        "chunks": chunks,
        "_landmarks": {
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
        },
    }
    OUT_MAP.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    halve_tileset(PACK_DIR / "assets" / "tileset-0.png", OUT_TILESET)
    walkable = sum(r.count(0) for r in collision)
    print(f"地图: {OUT_MAP} ({MAP_W}x{MAP_H}, {len(chunks)} chunks, 可走 {walkable} 格)")
    print(f"tileset: {OUT_TILESET} (2240x1600)")
    print(f"出生候选: {len(spawn)} 格")


if __name__ == "__main__":
    main()
