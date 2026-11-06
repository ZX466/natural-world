import { expect, it } from 'vitest';
import { createColorSampler, FALLBACK_COLOR, sampleTileColor } from '../tile-color';

function pixels(w: number, h: number, paint: (x: number, y: number) => number): Uint8ClampedArray {
  const data = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const value = paint(x, y);
      const i = (y * w + x) * 4;
      data[i] = (value >> 16) & 255;
      data[i + 1] = (value >> 8) & 255;
      data[i + 2] = value & 255;
      data[i + 3] = 255;
    }
  }
  return data;
}

it('averages the central 4x4 of the requested cell', () => {
  // Cell 2 occupies x=16..31; its 4x4 sample window is x=22..25, y=6..9.
  const data = pixels(32, 16, (x, y) => (x >= 22 && x <= 25 && y >= 6 && y <= 9 ? 0x327896 : 0));
  expect(sampleTileColor(data, 32, 16, 2)).toBe(0x327896);
});

it('falls back to timber for gids that name no source cell', () => {
  const data = pixels(32, 16, () => 0xffffff);
  expect(sampleTileColor(data, 32, 16, 0)).toBe(FALLBACK_COLOR);
  expect(sampleTileColor(data, 32, 16, 3)).toBe(FALLBACK_COLOR);
  expect(sampleTileColor(data, 32, 16, 1.5)).toBe(FALLBACK_COLOR);
});

it('memoizes per gid but keeps distinct cells distinct', () => {
  const data = pixels(32, 16, (x) => (x < 16 ? 0x112233 : 0x445566));
  const sampler = createColorSampler(data, 32, 16);
  expect(sampler(1)).toBe(0x112233);
  expect(sampler(2)).toBe(0x445566);
  expect(sampler(1)).toBe(0x112233);
  expect(sampler(9)).toBe(FALLBACK_COLOR);
});
