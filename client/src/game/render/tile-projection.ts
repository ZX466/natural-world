/** Isometric tile projection: map a tileset gid onto the 2:1 diamond it occupies.
 *
 * The column count is derived from the source image's own width, exactly as
 * `sampleTileColor` does — hard-coding it would let the two drift apart and
 * shift every tile by one column (spec §3.1).
 */

const TILE = 16;

export interface SourceSize {
  readonly width: number;
  readonly height: number;
}

export interface FrameRect {
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
}

const NO_FRAME: FrameRect = { x: 0, y: 0, w: 0, h: 0 };

/** gid (1-based) → the source rect holding that tile. Invalid gids get a zero rect. */
export function frameOf(gid: number, source: SourceSize): FrameRect {
  const cols = Math.floor(source.width / TILE);
  const rows = Math.floor(source.height / TILE);
  if (!Number.isInteger(gid) || gid <= 0 || gid > cols * rows) return NO_FRAME;
  return {
    x: ((gid - 1) % cols) * TILE,
    y: Math.floor((gid - 1) / cols) * TILE,
    w: TILE,
    h: TILE,
  };
}

/** Draw one tileset cell as the top face of the diamond centred on (sx, sy).
 *
 * The affine is the same four-point transform `BlockAtlas.face()` derives for
 * the top face; solving (u,v) backwards from screen space instead would only
 * paint half the diamond (spec trap #1).
 *
 * Returns false without touching the context when the gid has no source pixels,
 * so the caller can fall back to `paintBlock`.
 */
export function paintTile(
  ctx: CanvasRenderingContext2D,
  image: CanvasImageSource,
  sx: number,
  sy: number,
  gid: number,
  source: SourceSize,
): boolean {
  const frame = frameOf(gid, source);
  if (frame.w === 0) return false;
  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.transform(1, 0.5, -1, 0.5, sx, sy - TILE / 2);
  ctx.drawImage(image, frame.x, frame.y, TILE, TILE, 0, 0, TILE, TILE);
  ctx.restore();
  return true;
}
