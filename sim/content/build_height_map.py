"""Write/verify V1's coordinate-indexed height map.

Run: uv run python -m sim.content.build_height_map [--check]

## Single source of truth

Heights are **not** derived here. They come from
`sim.content.build_god_town.derive_terrain`, the same call that produces the
collision bits in `linhe-town.json`. That function runs
`sim.content.terrain_class.classify`, which classifies each 16x16 source tile by
its pixel mix (bright paving vs. dark roof vs. canopy vs. water) and then applies
a 5x5 mean filter, because the source pack is a 1:1 slice of a single painting
with no tile semantics.

Keeping one derivation is a hard requirement: when collision and render height
were derived independently, the two disagreed and the player could walk through
blocks that were drawn as solid (2026-10-28 report).

This module therefore exists to (a) emit the height JSON plus a 4x visual
preview for human review, and (b) `--check` that the committed artifacts are
byte-identical to a fresh derivation. It never introduces a second classifier.

No random values, timestamps, ignored source packs, or third-party dependencies.
"""

from __future__ import annotations

import argparse
import json
import textwrap
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from sim.content.png_codec import write_png_rgba

REPO = Path(__file__).resolve().parents[2]
MAP_PATH = REPO / "sim/content/linhe-town.json"
HEIGHT_PATH = REPO / "client/public/assets/tilesets/linhe-height.json"
PREVIEW_PATH = REPO / "sim/content/linhe-height-preview.png"
CHUNK = 16
SCALE = 4
PREVIEW_COLORS = ((66, 143, 166), (196, 181, 123), (127, 128, 139), (207, 107, 156))


def _load_ground() -> tuple[int, int, list[int]]:
    """行主序 gid 清单（来自已提交的 linhe-town.json）。"""
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    w, h = document["width"], document["height"]
    if not isinstance(w, int) or not isinstance(h, int) or w <= 0 or h <= 0:
        msg = "map dimensions must be positive integers"
        raise ValueError(msg)
    gids = [0] * (w * h)
    for y in range(h):
        for x in range(w):
            chunk = document["chunks"][f"{x // CHUNK},{y // CHUNK}"]
            gid = chunk["ground"][(y % CHUNK) * CHUNK + x % CHUNK]
            if not isinstance(gid, int):
                msg = f"invalid ground gid at ({x},{y})"
                raise ValueError(msg)
            gids[y * w + x] = gid
    return w, h, gids


def derive() -> tuple[int, int, list[int]]:
    """同源推导：直接复用 build_god_town 的那一次分类，不另起炉灶。"""
    from sim.content.build_god_town import (
        MAP_H,
        MAP_W,
        derive_terrain,
        extract_ground,
        extract_spawn,
        load_landmarks,
        load_tiled_map,
    )

    tiled = load_tiled_map()
    ground = extract_ground(tiled)
    spawn = extract_spawn(tiled)
    _collision, heights, _stats = derive_terrain(ground, spawn, load_landmarks())
    if (_load_ground()[0], _load_ground()[1]) != (MAP_W, MAP_H):
        msg = "map dimensions disagree between source pack and committed product"
        raise ValueError(msg)
    return MAP_W, MAP_H, heights


def render(w: int, h: int, heights: list[int], height_path: Path, preview_path: Path) -> Counter:
    """写出高度 JSON + 4x 预览图（唯一写出路径，build_god_town 也复用它）。"""
    height_path.parent.mkdir(parents=True, exist_ok=True)
    # Match the client's Prettier printWidth=100 without adding a Node dependency.
    values = textwrap.fill(
        ", ".join(map(str, heights)), width=100, initial_indent="    ", subsequent_indent="    "
    )
    height_path.write_text(
        f'{{\n  "w": {w},\n  "h": {h},\n  "h_values": [\n{values}\n  ]\n}}\n',
        encoding="utf-8",
        newline="\n",
    )
    preview = [
        [(*PREVIEW_COLORS[heights[(y // SCALE) * w + x // SCALE]], 255) for x in range(w * SCALE)]
        for y in range(h * SCALE)
    ]
    write_png_rgba(preview_path, w * SCALE, h * SCALE, preview)
    return Counter(heights)


def check() -> None:
    """Rebuild twice without changing committed artifacts; compare exact bytes."""
    with TemporaryDirectory(prefix="linhe-height-") as scratch:
        root = Path(scratch)
        first, second = root / "first", root / "second"
        w, h, heights = derive()
        counts = render(w, h, heights, first / "height.json", first / "preview.png")
        render(w, h, heights, second / "height.json", second / "preview.png")
        for name, committed in (("height.json", HEIGHT_PATH), ("preview.png", PREVIEW_PATH)):
            expected = (first / name).read_bytes()
            if expected != (second / name).read_bytes():
                msg = f"nondeterministic output: {name}"
                raise ValueError(msg)
            if not committed.exists() or committed.read_bytes() != expected:
                msg = (
                    f"stale/missing artifact: {committed.relative_to(REPO)}; "
                    "run `uv run python -m sim.content.build_god_town` then rebuild without --check"
                )
                raise ValueError(msg)
        print(f"CHECK OK: byte-identical JSON/PNG; heights={dict(sorted(counts.items()))}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify exact rebuilt bytes against committed artifacts",
    )
    args = parser.parse_args()
    if args.check:
        check()
        return
    w, h, heights = derive()
    counts = render(w, h, heights, HEIGHT_PATH, PREVIEW_PATH)
    print(
        f"BUILT: heights={dict(sorted(counts.items()))}; preview={PREVIEW_PATH.relative_to(REPO)}"
    )


if __name__ == "__main__":
    main()
