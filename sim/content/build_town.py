"""sim/content/build_town.py — 临河镇 48×48 地图构建（M7-T3，R6 确定性）。

读调色板取 tile id（R5 单源：client/public/assets/tilesets/sprout-palette.json），
写内部格式 JSON（TileMap.from_json_file 可加载）。重跑幂等、产物可 diff——
**禁用 random**，草变体用确定性算式。

布局（48×48，格坐标 x→右 y→下，全部矩形具名可审）：
- 边界 2 格树墙（不可走）；
- 草地底（含确定性花/草丛变体）；
- 十字土路：横 y=23-24 全宽，纵 x=23-24 全高；
- 药铺（主角家）：(6,8)-(14,14)，屋顶 3 行 + 墙 4 行 + 门格 (10,14) 可走；
- 住宅×2：(30,6)-(38,12) 与 (30,32)-(38,38)，同构；
- 农田：(8,30)-(18,40)；
- 水塘：(36,20)-(45,28)（不可走）；
- 主角出生点 (8,8) 保证草地可走。
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIZE = 48
CHUNK = 16
SPAWN = (8, 8)

# 调色板角色名 → sprout-palette.json ground 键（改名先改调色板，本脚本报缺名即回改）
PALETTE_NAMES: dict[str, str] = {
    "grass": "grass_1",
    "grass_alt": "grass_2",
    "flower": "flower",
    "path": "path_dirt",
    "water": "water",
    "farm": "farm_soil",
    "wall": "house_wall",
    "roof": "house_roof",
    "door": "house_door",
    "tree": "tree",
    "stone": "stone",
}


def load_palette_ids() -> dict[str, int]:
    """调色板单源读取（R5）：角色名 → tile index。缺名即 fail-loud。"""
    palette = json.loads(
        (REPO / "client" / "public" / "assets" / "tilesets" / "sprout-palette.json")
        .read_text(encoding="utf-8")
    )
    missing = set(PALETTE_NAMES.values()) - set(palette["ground"])
    if missing:
        raise KeyError(f"调色板缺 tile: {missing}——先补 build_palette.py 的 TERRAIN")
    return {role: palette["ground"][name] for role, name in PALETTE_NAMES.items()}


def build() -> None:
    ids = load_palette_ids()
    ground = [[0] * SIZE for _ in range(SIZE)]
    collision = [[True] * SIZE for _ in range(SIZE)]

    # 草地底 + 确定性变体（算式选伪随机，产物 diff 稳定）
    for y in range(SIZE):
        for x in range(SIZE):
            h = (x * 7 + y * 13) % 23
            ground[y][x] = ids["flower"] if h == 0 else (
                ids["grass_alt"] if h % 11 == 0 else ids["grass"]
            )

    def fill(x0: int, y0: int, x1: int, y1: int, role: str, *, walkable: bool | None = None) -> None:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                ground[y][x] = ids[role]
                if walkable is not None:
                    collision[y][x] = walkable

    # 边界树墙（外 2 格）
    fill(0, 0, SIZE - 1, 1, "tree", walkable=False)
    fill(0, SIZE - 2, SIZE - 1, SIZE - 1, "tree", walkable=False)
    fill(0, 0, 1, SIZE - 1, "tree", walkable=False)
    fill(SIZE - 2, 0, SIZE - 1, SIZE - 1, "tree", walkable=False)

    # 十字路
    fill(2, 23, SIZE - 3, 24, "path")
    fill(23, 2, 24, SIZE - 3, "path")

    # 药铺（主角家）：屋顶 3 行 + 墙 4 行 + 门格
    def house(x0: int, y0: int, door_x: int) -> None:
        fill(x0, y0, x0 + 8, y0 + 2, "roof", walkable=False)
        fill(x0, y0 + 3, x0 + 8, y0 + 6, "wall", walkable=False)
        ground[y0 + 6][door_x] = ids["door"]
        collision[y0 + 6][door_x] = True

    house(6, 8, 10)    # 药铺
    house(30, 6, 34)   # 住宅一
    house(30, 32, 34)  # 住宅二

    # 农田与水塘
    fill(8, 30, 18, 40, "farm")
    fill(36, 20, 45, 28, "water", walkable=False)

    # 零散石头（确定性点位）
    for sx, sy in ((16, 17), (27, 30), (12, 20), (40, 12), (33, 42)):
        ground[sy][sx] = ids["stone"]

    # 出生点保证可走草地
    ground[SPAWN[1]][SPAWN[0]] = ids["grass"]
    collision[SPAWN[1]][SPAWN[0]] = True

    # 切 chunk（16×16，键格式与 TileMap.from_json_file 的 (int(cx), int(cy)) 解析对齐）
    chunks: dict[str, dict[str, list[int] | list[bool]]] = {}
    for cy in range(SIZE // CHUNK):
        for cx in range(SIZE // CHUNK):
            g: list[int] = []
            c: list[bool] = []
            for ly in range(CHUNK):
                for lx in range(CHUNK):
                    g.append(ground[cy * CHUNK + ly][cx * CHUNK + lx])
                    c.append(collision[cy * CHUNK + ly][cx * CHUNK + lx])
            chunks[f"{cx},{cy}"] = {"ground": g, "collision": c}

    out = {"width": SIZE, "height": SIZE, "tile_size": CHUNK, "chunks": chunks}
    path = REPO / "sim" / "content" / "linhe-town.json"
    path.write_text(json.dumps(out, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"written {path} ({len(chunks)} chunks)")


if __name__ == "__main__":
    build()
