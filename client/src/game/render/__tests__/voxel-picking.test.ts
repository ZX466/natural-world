import { expect, it } from 'vitest';
import { isoProject, screenBounds } from '../iso';
import { pickVoxel } from '../voxel-picking';

it('picks a visible three-high top and side rather than the offset ground-plane cell', () => {
  const height = (x: number, y: number) => (x === 5 && y === 5 ? 3 : 1);
  const top = isoProject(5, 5, 3, screenBounds(8, 8));
  expect(pickVoxel(top.sx, top.sy, 8, 8, height)).toEqual({ x: 5, y: 5 });
  const base = isoProject(5, 5, 0, screenBounds(8, 8));
  expect(pickVoxel(base.sx, base.sy - 4, 8, 8, height)).toEqual({ x: 5, y: 5 });
});

it('picks elevated ground for placement and rejects points outside the world', () => {
  const point = isoProject(2, 3, 1, screenBounds(8, 8));
  expect(pickVoxel(point.sx, point.sy, 8, 8, () => 1)).toEqual({ x: 2, y: 3 });
  expect(pickVoxel(-999, -999, 8, 8, () => 1)).toBeNull();
});
