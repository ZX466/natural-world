"""sim/content/build_palette.py — 从 CC0 素材包生成调色板与运行时副本（M7-T1）。

素材：ArMM1998 "Zelda-like tilesets and sprites"（OpenGameArt，CC0 零限制）。
  https://opengameart.org/content/zelda-like-tilesets-and-sprites
（原计划 Sprout Lands 免费版需手动购买页操作且仅非商用；用户裁定换 CC0 直链包。
 Ruling 记录于 .superpowers ledger：素材源 Sprout Lands → Zelda-like CC0。）

职责：
  1. 复制 Overworld.png → client/public/assets/tilesets/（运行时副本）
  2. 复制 character.png/NPC_test.png → client/public/assets/actors/
  3. 生成 sprout-palette.json（键名沿用计划契约，值域=Overworld 40 列行主序 index）

帧布局实测（pillow 逐像素分析，见 .superpowers ledger）：
  - Overworld.png 640×576 = 40×36 tiles @16px；
  - character.png 272×256：主角块 gx0-2 gy0-3，行序 下/上/右/左 × 3 帧（步/站/步）；
  - NPC_test.png 64×128：4×8 tiles，村民站立帧取 (0,0)。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PKG = REPO / "sim" / "content" / "assets" / "zelda-like" / "pkg" / "gfx"
TS_OUT = REPO / "client" / "public" / "assets" / "tilesets"
ACTOR_OUT = REPO / "client" / "public" / "assets" / "actors"

TILE = 16
OVERWORLD_COLS = 40  # 640/16

# 地形名 → Overworld 图集 (gx, gy)。
# 批次 D8 视觉纠错（2026-10-06）：首版盲猜大面积错位（grass_3 指到水纹瓦、
# water 指到田垄、tree 指到深柱、path 指到藤蔓墙……）——像素统计+图集总览
# 人工目视重裁定（对照表见 tileset_overview.png / palette_fix_compare.png，
# 用户批准「按顺序完成」后执行）。裁定点：
#   grass_1=(0,0) 素草 / grass_2=(1,0) 泥土斑点草变体 / water=(16,0) 纯水 /
#   tree=(0,5) 圆树冠 / farm_soil=(16,5) 田垄 / path_dirt=(22,4) 石板路 /
#   house_wall=(8,2) 木墙白窗 / house_roof=(8,0) 棕横纹顶 / house_door=(15,3) 拱门 /
#   stone=(30,1) 灰石堆 / flower=(0,7) 花草变体（grass_3 废弃——0,3 亮斑过艳）
# 批次 D10（2026-10-07 用户截图定罪）：旧 grass_2=(2,0) 实为**蓝色圆环水泡瓦**
# （视觉上像水洼/机关标记，散布全图当草变体用 = 满地灰白椭圆的根因），
# 改裁 (1,0) 泥土斑点草——目视核对 zoom 裁片后定案。
TERRAIN: dict[str, tuple[int, int]] = {
    "grass_1": (0, 0),
    "grass_2": (1, 0),
    "water": (16, 0),
    "tree": (0, 5),
    "farm_soil": (16, 5),
    "path_dirt": (22, 4),
    "house_wall": (8, 2),
    "house_roof": (8, 0),
    "house_door": (15, 3),
    "stone": (30, 1),
    "flower": (0, 7),
}


def main() -> None:
    TS_OUT.mkdir(parents=True, exist_ok=True)
    ACTOR_OUT.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(PKG / "Overworld.png", TS_OUT / "sprout-tileset.png")
    shutil.copyfile(PKG / "character.png", ACTOR_OUT / "chenmo.png")
    shutil.copyfile(PKG / "NPC_test.png", ACTOR_OUT / "villager.png")

    palette = {
        "tileset": "zelda_like_v1",
        "image": "sprout-tileset.png",
        "image_size": [640, 576],
        "tile_size": TILE,
        "cols": OVERWORLD_COLS,
        "ground": {name: gy * OVERWORLD_COLS + gx for name, (gx, gy) in TERRAIN.items()},
        "actors": {
            "chenmo": {
                "image": "chenmo.png",
                "frame_size": [16, 16],
                # 主角块：列 0-2 × 行 0-3；行序 down/up/right/left，每行 3 帧
                "rows": {"down": 0, "up": 1, "right": 2, "left": 3},
                "frames_per_row": 3,
                "frame_layout": "step-stand-step",
            },
            "villager": {
                "image": "villager.png",
                "frame_size": [16, 16],
                "standing_frame": 0,
            },
        },
    }
    out = TS_OUT / "sprout-palette.json"
    out.write_text(json.dumps(palette, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"palette: {out} ({len(palette['ground'])} ground tiles)")


if __name__ == "__main__":
    main()
