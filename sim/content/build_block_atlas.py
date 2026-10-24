"""Deterministic V3 block atlas: four height roles x three 16px faces.

Run: uv run python -m sim.content.build_block_atlas [--check]
Only committed inputs are used. Colors are averages of the same central 4x4
gid samples as build_height_map.py. Detail is integer arithmetic, with no RNG
or clock. Faces are top 100%, left 75%, right 60%. The browser normalizes each
role to a luminance mask and tints it with the original per-cell sample color.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from sim.content.build_height_map import CHUNK, MAP_PATH, TILESET_PATH, classify_height, sample_rgb
from sim.content.png_codec import read_png_rgba, write_png_rgba

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "client/public/assets/tilesets"
ATLAS_PATH = OUT / "linhe-block-atlas.png"
META_PATH = OUT / "linhe-block-atlas.json"
ROLES = ("water", "ground", "building", "canopy")
FACE_SHADE = (100, 75, 60)
TILE = 16


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
    source = read_png_rgba(TILESET_PATH)
    if (len(source[0]), len(source)) != (2240, 1600):
        msg = "expected committed 2240x1600 god-town tileset"
        raise ValueError(msg)
    groups: list[list[tuple[int, int, int]]] = [[] for _ in ROLES]
    for y in range(document["height"]):
        for x in range(document["width"]):
            chunk = document["chunks"][f"{x // CHUNK},{y // CHUNK}"]
            gid = chunk["ground"][(y % CHUNK) * CHUNK + x % CHUNK]
            rgb = sample_rgb(source, gid)
            groups[1 if gid == 0 else classify_height(rgb)].append(rgb)
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
