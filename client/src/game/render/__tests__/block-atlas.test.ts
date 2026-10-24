import { describe, expect, it } from 'vitest';
import { atlasFrame, neutralizeAtlas } from '../block-atlas';

describe('fixed block atlas', () => {
  it('selects the four height roles and three distinct 16×16 face rows', () => {
    for (let height = 0; height < 4; height++)
      for (const [row, face] of ['top', 'left', 'right'].entries()) {
        expect(atlasFrame(height, face as 'top' | 'left' | 'right')).toEqual({
          x: height * 16,
          y: row * 16,
          width: 16,
          height: 16,
        });
      }
    expect(atlasFrame(NaN, 'top')).toEqual(atlasFrame(1, 'top'));
  });

  it('normalizes role colors to tint masks while keeping side shading and detail', () => {
    const pixels = new Uint8ClampedArray(64 * 48 * 4);
    for (let y = 0; y < 48; y++)
      for (let x = 0; x < 64; x++) {
        const value = y < 16 ? 100 : y < 32 ? 75 : 60;
        pixels.set([value, value / 2, 0, 255], (y * 64 + x) * 4);
      }
    const mask = neutralizeAtlas(pixels, [0x643200, 0x643200, 0x643200, 0x643200]);
    expect([...mask.slice(0, 4)]).toEqual([255, 255, 255, 255]);
    expect([...mask.slice(16 * 64 * 4, 16 * 64 * 4 + 4)]).toEqual([191, 191, 191, 255]);
    expect([...mask.slice(32 * 64 * 4, 32 * 64 * 4 + 4)]).toEqual([153, 153, 153, 255]);
    expect(pixels[0]).toBe(100);
  });
});
