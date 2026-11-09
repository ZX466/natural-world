import { expect, it } from 'vitest';
import {
  STAND_FOOTPRINT_H,
  STAND_FOOTPRINT_W,
  findStandPlot,
  landmarkFromSearch,
  standFootprint,
} from '../landmark-lre';

/** 17×15（x 从 cx-8 到 cx+8，y 从 cy-7 到 cy+7）——与 vendored 模块
 *  `getOccupiedTiles()` 的取整范围一致，不是规格文档写的 16×14。 */
it('footprint constants match the vendored occupied-tile loop', () => {
  expect(STAND_FOOTPRINT_W).toBe(17);
  expect(STAND_FOOTPRINT_H).toBe(15);
});

it('finds the northernmost flat plot, deterministically', () => {
  const w = 40;
  const h = 40;
  // 除一块 17×15 的平地（高度 1）外全是高度 2，只有这一块可用。
  const heights = new Uint8Array(w * h).fill(2);
  for (let y = 12; y < 27; y++) for (let x = 10; x < 27; x++) heights[y * w + x] = 1;
  const heightOf = (x: number, y: number): number => heights[y * w + x]!;
  expect(findStandPlot(w, h, heightOf)).toEqual({
    tileX: -1.5,
    tileZ: -0.5,
    gridX: 18,
    gridY: 19,
    groundY: 1,
  });
  // 再调用一次必须给出同一个点（确定性，不随 Map 迭代序漂移）。
  expect(findStandPlot(w, h, heightOf)).toEqual(findStandPlot(w, h, heightOf));
});

it('returns null when no flat plot fits', () => {
  const w = 10;
  const h = 10;
  const heights = new Uint8Array(w * h).fill(2);
  const heightOf = (x: number, y: number): number => heights[y * w + x]!;
  expect(findStandPlot(w, h, heightOf)).toBeNull();
});

it('never selects a plot that would hang off the map', () => {
  const w = 17;
  const h = 15;
  const heights = new Uint8Array(w * h).fill(1);
  const heightOf = (x: number, y: number): number => heights[y * w + x]!;
  // 只有整张图刚好等于占地面时中心才是 (8,7)；任何偏移都会越界。
  expect(findStandPlot(w, h, heightOf)).toEqual({
    tileX: 0,
    tileZ: 0,
    gridX: 8,
    gridY: 7,
    groundY: 1,
  });
});

it('footprint covers every occupied tile at the concrete deck height', () => {
  const tiles = standFootprint({ tileX: 0, tileZ: 0, gridX: 20, gridY: 30, groundY: 1 });
  expect(tiles).toHaveLength(STAND_FOOTPRINT_W * STAND_FOOTPRINT_H);
  expect(tiles[0]).toEqual({ gx: 12, gz: 23, topY: 1.52 });
  expect(tiles.at(-1)).toEqual({ gx: 28, gz: 37, topY: 1.52 });
  expect(new Set(tiles.map((t) => `${t.gx}:${t.gz}`)).size).toBe(tiles.length);
});

it('is on by default and only an exact "0" rolls it back', () => {
  expect(landmarkFromSearch('')).toBe(true);
  expect(landmarkFromSearch('?landmark=0')).toBe(false);
  expect(landmarkFromSearch('?landmark=false')).toBe(true);
  expect(landmarkFromSearch('?landmark=1')).toBe(true);
  expect(landmarkFromSearch('?avatar3d=0&landmark=0')).toBe(false);
});
