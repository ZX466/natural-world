"""Deterministic V3 block atlas: four height roles x three 16px faces.

Run: uv run python -m sim.content.build_block_atlas [--check]

Roles come from `linhe-height.json`, the single-source terrain product, so the
atlas can never disagree with collision or with the isometric renderer. Base
colors are the mean of the tileset's central 4x4 sample over every cell in that
role. Detail is integer arithmetic, with no RNG or clock. Faces are top 100%,
left 75%, right 60%. The browser normalizes each role to a luminance mask and
tints it with the original per-cell sample color.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from sim.content.png_codec import read_png_rgba, write_png_rgba

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "client/public/assets/tilesets"
ATLAS_PATH = OUT / "linhe-block-atlas.png"
META_PATH = OUT / "linhe-block-atlas.json"
MAP_PATH = REPO / "sim/content/linhe-town.json"
TILESET_PATH = OUT / "god-town-16.png"
HEIGHT_PATH = OUT / "linhe-height.json"
ROLES = ("water", "ground", "building", "canopy")
FACE_SHADE = (100, 75, 60)
TILE = 16
CHUNK = 16
#: 与 iso-terrain.ts 的 gid=0 木色兜底一致。
FALLBACK_RGB = (107, 79, 42)
type Pixels = list[list[tuple[int, int, int, int]]]


def sample_rgb(pixels: Pixels, gid: int) -> tuple[int, int, int]:
    """gid（1 起，非地图坐标）定位图集中心 4x4 采样块。"""
    if gid == 0:
        return FALLBACK_RGB
    cols = len(pixels[0]) // TILE
    if gid < 0 or gid > cols * (len(pixels) // TILE):
        msg = f"ground gid outside tileset: {gid}"
        raise ValueError(msg)
    sx, sy = ((gid - 1) % cols) * TILE + 6, ((gid - 1) // cols) * TILE + 6
    samples = [pixels[y][x] for y in range(sy, sy + 4) for x in range(sx, sx + 4)]
    return (
        sum(pixel[0] for pixel in samples) // 16,
        sum(pixel[1] for pixel in samples) // 16,
        sum(pixel[2] for pixel in samples) // 16,
    )


def tone(role: int, x: int, y: int) -> int:
    """Small reproducible streaks, grain, mortar, and leaf clusters."""
    grain = (x * 17 + y * 29 + (x * y) * 3 + role * 11) % 7
    if role == 0:
        return 90 + grain if y % 6 == 0 else 100 - grain
    if role == 2 and (y % 8 == 0 or (x + (y // 8) * 4) % 8 == 0):
        return 87
    if role == 3:
        return 93 + ((x // 3 + y // 3 + grain) % 8)
    return 100 - grain


def build(png_path: Path, meta_path: Path) -> dict:
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    heights_doc = json.loads(HEIGHT_PATH.read_text(encoding="utf-8"))
    w, h = document["width"], document["height"]
    if (heights_doc["w"], heights_doc["h"]) != (w, h):
        msg = "linhe-height.json 与 linhe-town.json 尺寸不一致"
        raise ValueError(msg)
    heights = heights_doc["h_values"]
    source = read_png_rgba(TILESET_PATH)
    if (len(source[0]), len(source)) != (2240, 1600):
        msg = "expected committed 2240x1600 god-town tileset"
        raise ValueError(msg)
    groups: list[list[tuple[int, int, int]]] = [[] for _ in ROLES]
    for y in range(h):
        for x in range(w):
            chunk = document["chunks"][f"{x // CHUNK},{y // CHUNK}"]
            gid = chunk["ground"][(y % CHUNK) * CHUNK + x % CHUNK]
            role = heights[y * w + x]
            if not 0 <= role < len(ROLES):
                msg = f"height role out of range at ({x},{y}): {role}"
                raise ValueError(msg)
            groups[role].append(sample_rgb(source, gid))
    colors: list[tuple[int, int, int]] = []
    for samples in groups:
        if not samples:
            msg = "all four height roles must have source samples"
            raise ValueError(msg)
        mean = [sum(p[c] for p in samples) // len(samples) for c in range(3)]
        colors.append((mean[0], mean[1], mean[2]))
    pixels = [[(0, 0, 0, 255) for _ in range(TILE * 4)] for _ in range(TILE * 3)]
    for role, rgb in enumerate(colors):
        for face, shade in enumerate(FACE_SHADE):
            for y in range(TILE):
                for x in range(TILE):
                    factor = tone(role, x, y) * shade
                    r, g, b = rgb
                    pixels[face * TILE + y][role * TILE + x] = (
                        r * factor // 10000,
                        g * factor // 10000,
                        b * factor // 10000,
                        255,
                    )
    write_png_rgba(png_path, TILE * 4, TILE * 3, pixels)
    meta = {
        "tile_size": TILE,
        "columns": 4,
        "rows": 3,
        "source_tileset": "god-town-16.png",
        "source_map": "linhe-town.json",
        "source_heights": "linhe-height.json",
        "sampling": "ground gid central 4x4 RGB mean, integer floor",
        "base_colors": {
            name: (r << 16) | (g << 8) | b for name, (r, g, b) in zip(ROLES, colors, strict=True)
        },
        "sample_counts": {name: len(group) for name, group in zip(ROLES, groups, strict=True)},
        "faces": {"top": 0, "left": 1, "right": 2},
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
    return meta


def check() -> None:
    """Byte-compare two fresh builds and both committed outputs."""
    with TemporaryDirectory(prefix="linhe-block-atlas-") as scratch:
        root = Path(scratch)
        first, second = root / "first", root / "second"
        meta = build(first / "atlas.png", first / "atlas.json")
        build(second / "atlas.png", second / "atlas.json")
        assert sum(meta["sample_counts"].values()) == 14000
        assert all(
            87 <= tone(role, x, y) <= 100 for role in range(4) for x in range(16) for y in range(16)
        )
        for name, committed in (("atlas.png", ATLAS_PATH), ("atlas.json", META_PATH)):
            expected = (first / name).read_bytes()
            if expected != (second / name).read_bytes():
                msg = f"nondeterministic atlas output: {name}"
                raise ValueError(msg)
            if not committed.exists() or committed.read_bytes() != expected:
                msg = f"stale/missing atlas output: {committed.relative_to(REPO)}"
                raise ValueError(msg)
        print(f"CHECK OK: byte-identical PNG/JSON; frames=12; counts={meta['sample_counts']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        meta = build(ATLAS_PATH, META_PATH)
        print(f"BUILT: 64x48, 12 faces; colors={meta['base_colors']}")


if __name__ == "__main__":
    main()
