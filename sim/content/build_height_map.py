"""Build V1's coordinate-indexed height map from the committed map and tileset.

Run: uv run python -m sim.content.build_height_map [--check]

Fixed HSV thresholds (degrees; saturation/value 0..1), evaluated in this order:
  water -> 0: H 165..245, S >= .30, V >= .24, B > 1.10*R
  peach/magenta canopy -> 3: H >= 300, S >= .18, V >= .34,
                           R > 1.20*G and B > 1.05*G
  dark green canopy -> 3: H 65..170, S >= .28, V <= .40
  grey roof/wall -> 2: S <= .26 and V .18.. .68
  dark timber/wall -> 2: H <= 65, S <= .60, V .18.. .49
  remaining vegetation, paths, soil -> 1; gid=0 -> 1 (deterministic fallback).

RGB = integer floor of the central 4x4 mean, matching the browser sampler.
This is a visual approximation, not collision or semantic truth. Pink flowers
and canopy share a color class; the 4x preview requires main-tree human review.
No random values, timestamps, ignored source packs, or third-party dependencies.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import textwrap
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from sim.content.png_codec import read_png_rgba, write_png_rgba

REPO = Path(__file__).resolve().parents[2]
MAP_PATH = REPO / "sim/content/linhe-town.json"
TILESET_PATH = REPO / "client/public/assets/tilesets/god-town-16.png"
HEIGHT_PATH = REPO / "client/public/assets/tilesets/linhe-height.json"
PREVIEW_PATH = REPO / "sim/content/linhe-height-preview.png"
TILE = 16
CHUNK = 16
SCALE = 4
FALLBACK_RGB = (107, 79, 42)  # Same gid=0 timber color as iso-terrain.ts.
PREVIEW_COLORS = ((66, 143, 166), (196, 181, 123), (127, 128, 139), (207, 107, 156))
type Pixels = list[list[tuple[int, int, int, int]]]


def classify_height(rgb: tuple[int, int, int]) -> int:
    """Fixed, ordered color classes; gameplay never consumes these heights."""
    r, g, b = rgb
    hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    hue *= 360
    if 165 <= hue <= 245 and saturation >= 0.30 and value >= 0.24 and b > 1.10 * r:
        return 0
    if hue >= 300 and saturation >= 0.18 and value >= 0.34 and r > 1.20 * g and b > 1.05 * g:
        return 3
    if 65 <= hue <= 170 and saturation >= 0.28 and value <= 0.40:
        return 3
    if saturation <= 0.26 and 0.18 <= value <= 0.68:
        return 2
    if hue <= 65 and saturation <= 0.60 and 0.18 <= value <= 0.49:
        return 2
    return 1


def sample_rgb(pixels: Pixels, gid: int) -> tuple[int, int, int]:
    """gid (1 based), not map coordinate, locates the tileset's central 4x4."""
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


def build(height_path: Path, preview_path: Path) -> Counter[int]:
    """Only visit in-bounds map cells; chunk-edge padding is never sampled."""
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    w, h = document["width"], document["height"]
    if not isinstance(w, int) or not isinstance(h, int) or w <= 0 or h <= 0:
        msg = "map dimensions must be positive integers"
        raise ValueError(msg)
    pixels = read_png_rgba(TILESET_PATH)
    if (len(pixels[0]), len(pixels)) != (2240, 1600):
        msg = "expected god-town-16.png at 2240x1600 (140 tileset columns)"
        raise ValueError(msg)
    heights: list[int] = []
    for y in range(h):
        for x in range(w):
            chunk = document["chunks"][f"{x // CHUNK},{y // CHUNK}"]
            gid = chunk["ground"][(y % CHUNK) * CHUNK + x % CHUNK]
            if not isinstance(gid, int):
                msg = f"invalid ground gid at ({x},{y})"
                raise ValueError(msg)
            heights.append(1 if gid == 0 else classify_height(sample_rgb(pixels, gid)))
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
    # Small contract probes live here, as requested; no additional sim/tests.
    assert classify_height((50, 120, 150)) == 0
    assert classify_height((190, 100, 150)) == 3
    assert classify_height((40, 70, 35)) == 3
    assert classify_height((90, 95, 100)) == 2
    assert classify_height((180, 160, 100)) == 1
    fixture = [[(0, 0, 0, 255)] * 32 for _ in range(16)]
    for y in range(6, 10):
        for x in range(22, 26):
            fixture[y][x] = (50, 120, 150, 255)
    assert sample_rgb(fixture, 2) == (50, 120, 150)
    assert sample_rgb(fixture, 0) == FALLBACK_RGB
    with TemporaryDirectory(prefix="linhe-height-") as scratch:
        root = Path(scratch)
        first, second = root / "first", root / "second"
        counts = build(first / "height.json", first / "preview.png")
        build(second / "height.json", second / "preview.png")
        for name, committed in (("height.json", HEIGHT_PATH), ("preview.png", PREVIEW_PATH)):
            expected = (first / name).read_bytes()
            if expected != (second / name).read_bytes():
                msg = f"nondeterministic output: {name}"
                raise ValueError(msg)
            if not committed.exists() or committed.read_bytes() != expected:
                msg = (
                    f"stale/missing artifact: {committed.relative_to(REPO)}; "
                    "rebuild without --check"
                )
                raise ValueError(msg)
        print(f"CHECK OK: byte-identical JSON/PNG; heights={dict(sorted(counts.items()))}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify contracts and exact rebuilt bytes"
    )
    args = parser.parse_args()
    if args.check:
        check()
    else:
        counts = build(HEIGHT_PATH, PREVIEW_PATH)
        print(
            f"BUILT: heights={dict(sorted(counts.items()))}; "
            f"preview={PREVIEW_PATH.relative_to(REPO)}"
        )


if __name__ == "__main__":
    main()
