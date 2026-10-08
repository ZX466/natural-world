"""sim/content/build_town.py — 临河镇 96×96 地图构建（M7-T3 起家，D16 扩图）。

读调色板取 tile id（R5 单源：client/public/assets/tilesets/sprout-palette.json），
写内部格式 JSON（TileMap.from_json_file 可加载）。重跑幂等、产物可 diff——
**禁用 random**，草变体用确定性算式。

布局（96×96，D16：面积 ×4 + 五片区——「每 npc 固定区域」的空间底座，
格坐标 x→右 y→下，全部矩形具名可审）：
- 边界 2 格树墙（不可走）；
- 草地底（含确定性花/草丛变体）；
- 十字土路：横 y=47-48 全宽，纵 x=47-48 全高（中心镇集）；
- 药铺（主角家）：(12,16)-(20,22)，屋顶 3 行 + 墙 4 行 + 门格 (16,22) 可走；
- 中心片区：住宅 (24,34)-(32,40)（镇集南）；
- 西村片区：住宅 (10,60)-(18,66)；
- 东村片区：住宅 (78,30)-(86,36)（水塘上方）；
- 南村片区：农田 (16,72)-(36,88)、住宅 (44,78)-(52,84)；
- 北村片区：水塘 (72,40)-(90,45) 与 (72,54)-(90,61)（不可走）、住宅 (74,66)-(82,72)；
- 零散石头（确定性点位）。

片区锚点（sim/npc/sim_exec.HOME_BASES 同源——定籍制空间底座，五区，
每区一宅：rest=自家门前）：
中心 (28,42) / 西村 (14,68) / 东村 (82,38) / 南村 (46,86) / 北村 (78,75)
——锚点自身必须可走（`_scatter_near` 锚点兜底依赖）。
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIZE = 96
CHUNK = 16
SPAWN = (16, 32)  # 药铺屋前空地（屋体 y=16-22，出生点必须屋外开阔草）

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
    """调色板 JSON → 角色名 → tile id（缺名即 KeyError——管线报缺回改）。"""
    palette_path = REPO / "client" / "public" / "assets" / "tilesets" / "sprout-palette.json"
    palette = json.loads(palette_path.read_text(encoding="utf-8"))
    return {role: palette["ground"][name] for role, name in PALETTE_NAMES.items()}


def build() -> None:
    ids = load_palette_ids()
    ground = [[0] * SIZE for _ in range(SIZE)]
    collision = [[True] * SIZE for _ in range(SIZE)]

    # 草地底 + 确定性变体（算式选伪随机，产物 diff 稳定）。
    # D10：花变体降频 1/23 → 1/53（满地小蓝花抢戏，用户截图定罪）；泥土斑
    # grass_alt 保持 1/11（目视低调，与底草同族）。
    for y in range(SIZE):
        for x in range(SIZE):
            h = (x * 7 + y * 13) % 53
            ground[y][x] = ids["flower"] if h == 0 else (
                ids["grass_alt"] if (x * 7 + y * 13) % 11 == 0 else ids["grass"]
            )

    def fill(
        x0: int, y0: int, x1: int, y1: int, role: str, *, walkable: bool | None = None
    ) -> None:
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

    # 十字路（中心镇集：横纵各 2 格宽）
    fill(2, 47, SIZE - 3, 48, "path")
    fill(47, 2, 48, SIZE - 3, "path")

    # 药铺（主角家）：屋顶 3 行 + 墙 4 行 + 门格
    def house(x0: int, y0: int, door_x: int) -> None:
        fill(x0, y0, x0 + 8, y0 + 2, "roof", walkable=False)
        fill(x0, y0 + 3, x0 + 8, y0 + 6, "wall", walkable=False)
        ground[y0 + 6][door_x] = ids["door"]
        collision[y0 + 6][door_x] = True

    house(12, 16, 16)  # 药铺（主角家）
    house(24, 34, 28)  # 中心片区住宅（镇集南）
    house(10, 60, 14)  # 西村住宅
    house(78, 30, 82)  # 东村住宅（水塘上方）
    house(44, 78, 48)  # 南村住宅
    house(74, 66, 78)  # 北村住宅（水塘下方）

    # 农田（南村）与水塘两块（北村；避开十字路 y=47-48 与东村宅 y=30-36）
    fill(16, 72, 36, 88, "farm")
    fill(72, 40, 90, 45, "water", walkable=False)
    fill(72, 54, 90, 61, "water", walkable=False)

    # 零散石头（确定性点位）
    for sx, sy in ((30, 30), (56, 24), (24, 56), (68, 72), (84, 20), (12, 40), (52, 44)):
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
