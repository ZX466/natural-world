import { expect, it } from 'vitest';
import type { MapStatic } from '../../world-mirror';
import { EDIT_COLORS, WATER_COLOR, cellAppearances } from '../cell-appearance';

const W = 2;
const H = 1;

function mapWith(): MapStatic {
  return {
    w: W,
    h: H,
    tileset: 'god',
    collision: new Uint8Array(W * H).fill(1),
    ground: new Uint16Array(W * H).fill(7),
  };
}

const identity = (gid: number) => gid;

/** Material a placed block of each kind carries, and the height it lands at.
 * `voxel_exec._HEIGHT_BY_MATERIAL` is the authority: earth=1, stone=2, wood=3. */
const PLACED: ReadonlyArray<readonly [material: 'earth' | 'stone' | 'wood', height: number]> = [
  ['earth', 1],
  ['stone', 2],
  ['wood', 3],
];

/** A dug cell loses one height level, so the material it still shows is the
 * one that was below it: wood(3) -> 2 is stone, stone(2) -> 1 is earth. */
it('a placed block is painted in its own material colour', () => {
  for (const [material, height] of PLACED) {
    const edits = new Map([[`0,0`, { height, action: 'place' as const, material }]]);
    const cells = cellAppearances(mapWith(), new Map(), edits, () => height, identity);
    expect(cells[0]!.color, `placed ${material}`).toBe(EDIT_COLORS[height]);
  }
});

it('a dug cell is painted in the material of the layer it now exposes', () => {
  // Digging a natural wood column (h=3) leaves h=2, which is stone.
  const woodToStone = cellAppearances(
    mapWith(),
    new Map(),
    new Map([['0,0', { height: 2, action: 'dig' as const, material: 'stone' }]]),
    () => 2,
    identity,
  );
  expect(woodToStone[0]!.color).toBe(EDIT_COLORS[2]);

  // Digging a natural stone column (h=2) leaves h=1, which is earth.
  const stoneToEarth = cellAppearances(
    mapWith(),
    new Map(),
    new Map([['0,0', { height: 1, action: 'dig' as const, material: 'earth' }]]),
    () => 1,
    identity,
  );
  expect(stoneToEarth[0]!.color).toBe(EDIT_COLORS[1]);
});

it('a dug-out cell (h=0) is painted as water, not as earth', () => {
  // h=0 means "nothing stands here any more". The renderer draws it as the thin
  // water slab, so giving it the earth tone makes a pit read as untouched ground
  // — the block appears to have gone see-through rather than been dug away.
  const cells = cellAppearances(
    mapWith(),
    new Map(),
    new Map([['0,0', { height: 0, action: 'dig' as const, material: 'earth' }]]),
    () => 0,
    identity,
  );
  expect(cells[0]!.h).toBe(0);
  expect(cells[0]!.color).not.toBe(EDIT_COLORS[1]);
  expect(cells[0]!.color).toBe(WATER_COLOR);
});
