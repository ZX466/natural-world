import { describe, expect, it } from 'vitest';
import { rasterContext } from './raster-context';

function ctxOf(w: number, h: number) {
  const canvas = { width: w, height: h };
  return rasterContext(() => canvas);
}

describe('rasterContext drawImage', () => {
  it('maps a 16×16 source cell through the iso affine and lands pixels', () => {
    const ctx = ctxOf(64, 64);
    const src = { width: 16, height: 16, pixels: new Uint32Array(256).fill(0xff00ff00) };
    ctx.save();
    ctx.transform(1, 0.5, -1, 0.5, 32, 24); // 顶面：中心 (32,32)
    ctx.drawImage(src, 0, 0, 16, 16, 0, 0, 16, 16);
    ctx.restore();
    const px = ctx.pixels();
    expect(px[32 * 64 + 32]).toBe(0xff00ff00); // 中心被覆盖
    expect(px[0]).toBe(0); // 远处不受影响
  });

  it('respects save/restore of the transform stack', () => {
    const ctx = ctxOf(64, 64);
    const src = { width: 16, height: 16, pixels: new Uint32Array(256).fill(0xffff0000) };
    ctx.save();
    ctx.transform(1, 0.5, -1, 0.5, 32, 24);
    ctx.restore();
    ctx.drawImage(src, 0, 0, 16, 16, 0, 0, 16, 16); // 恒等变换 ⇒ 画在左上角
    const px = ctx.pixels();
    expect(px[4 * 64 + 4]).toBe(0xffff0000);
    expect(px[32 * 64 + 32]).toBe(0);
  });
});
