import { describe, expect, it } from 'vitest';
import { frameOf, paintTile } from '../tile-projection';

const TILE = 16;
const REAL = { width: 2240, height: 1600 }; // 140×100 个 16px 格
const SMALL = { width: 16, height: 16 }; // 测试夹具的 1×1 图

describe('frameOf', () => {
  it('maps gid to the same source rect the colour sampler reads', () => {
    expect(frameOf(1, REAL)).toEqual({ x: 0, y: 0, w: TILE, h: TILE });
    expect(frameOf(140, REAL)).toEqual({ x: 139 * TILE, y: 0, w: TILE, h: TILE });
    expect(frameOf(141, REAL)).toEqual({ x: 0, y: TILE, w: TILE, h: TILE });
    expect(frameOf(14000, REAL)).toEqual({ x: 139 * TILE, y: 99 * TILE, w: TILE, h: TILE });
  });

  it('derives the column count from the source image, not a hard-coded 140', () => {
    // 16×16 源图只有 1 列 1 行 ⇒ 只有 gid 1 有效
    expect(frameOf(1, SMALL)).toEqual({ x: 0, y: 0, w: TILE, h: TILE });
    expect(frameOf(2, SMALL)).toEqual({ x: 0, y: 0, w: 0, h: 0 });
  });

  it('returns a zero rect for gids that have no source pixels', () => {
    for (const gid of [0, -3, 14001, 1.5, Number.NaN]) {
      expect(frameOf(gid, REAL)).toEqual({ x: 0, y: 0, w: 0, h: 0 });
    }
  });
});

describe('paintTile', () => {
  it('draws the source cell through the exact iso projection and reports success', () => {
    const calls: unknown[] = [];
    const ctx = {
      imageSmoothingEnabled: true,
      save: () => calls.push('save'),
      restore: () => calls.push('restore'),
      transform: (...a: number[]) => calls.push(['transform', ...a]),
      drawImage: (...a: unknown[]) => calls.push(['drawImage', ...a]),
    } as unknown as CanvasRenderingContext2D;
    expect(paintTile(ctx, {} as CanvasImageSource, 100, 50, 141, REAL)).toBe(true);
    // 2:1 等距顶面：四点 (sx,sy-hh)(sx+hw,sy)(sx,sy+hh)(sx-hw,sy)
    // ⇒ transform(1, 0.5, -1, 0.5, sx, sy - 8)
    expect(calls).toContainEqual(['transform', 1, 0.5, -1, 0.5, 100, 42]);
    expect(calls).toContainEqual(['drawImage', {}, 0, 16, 16, 16, 0, 0, 16, 16]);
    expect(ctx.imageSmoothingEnabled).toBe(false);
  });

  it('returns false without touching the context when the gid has no pixels', () => {
    const calls: unknown[] = [];
    const ctx = {
      save: () => calls.push('save'),
      restore: () => calls.push('restore'),
      transform: () => calls.push('transform'),
      drawImage: () => calls.push('drawImage'),
    } as unknown as CanvasRenderingContext2D;
    expect(paintTile(ctx, {} as CanvasImageSource, 100, 50, 0, REAL)).toBe(false);
    expect(calls).toEqual([]);
  });
});
