/** One tileset cell's representative colour, shared by every renderer.
 *
 * Extracted from `iso-terrain.ts` so the three.js path can sample colours
 * without pulling the Phaser module graph. The sampling rule is identical to
 * `build_block_atlas.py`: the cell's central 4×4 RGB mean, integer floor.
 */

export const TILE = 16;

/** Structures may replace their ground gid with 0. No source pixels exist then;
 * use the same deterministic timber fallback as `build_height_map.py`. */
export const FALLBACK_COLOR = 0x6b4f2a;

export function sampleTileColor(
  data: Uint8ClampedArray,
  w: number,
  h: number,
  gid: number,
): number {
  const cols = Math.floor(w / TILE);
  if (!Number.isInteger(gid) || gid <= 0 || gid > cols * Math.floor(h / TILE))
    return FALLBACK_COLOR;
  const sx = ((gid - 1) % cols) * TILE + 6;
  const sy = Math.floor((gid - 1) / cols) * TILE + 6;
  let r = 0,
    g = 0,
    b = 0;
  for (let y = sy; y < sy + 4; y++) {
    for (let x = sx; x < sx + 4; x++) {
      const i = (y * w + x) * 4;
      r += data[i]!;
      g += data[i + 1]!;
      b += data[i + 2]!;
    }
  }
  return (Math.floor(r / 16) << 16) | (Math.floor(g / 16) << 8) | Math.floor(b / 16);
}

/** Per-gid memo over one sampled tileset image. */
export function createColorSampler(
  pixels: Uint8ClampedArray,
  w: number,
  h: number,
): (gid: number) => number {
  const cache = new Map<number, number>();
  return (gid) => {
    let color = cache.get(gid);
    if (color === undefined) {
      color = sampleTileColor(pixels, w, h, gid);
      cache.set(gid, color);
    }
    return color;
  };
}
