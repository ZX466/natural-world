import { expect, it } from 'vitest';
import { WorldMirror, type MapStatic } from '../world-mirror';
import { effectiveHeight } from '../render/iso';

function map(): MapStatic {
  const collision = new Uint8Array(16).fill(1);
  collision[5] = 0;
  return { w: 4, h: 4, tileset: 'grid', collision, ground: new Uint16Array(16).fill(7) };
}

it('applies edit deltas in place to ground and collision and replaces an empty snapshot', () => {
  const mirror = new WorldMirror();
  mirror.setMap(map());
  const collision = mirror.map!.collision;
  mirror.applyVoxelEdits([{ x: 2, y: 1, action: 'place', gid: 0 }]);
  expect(mirror.map!.collision).toBe(collision);
  expect(collision[6]).toBe(0);
  expect(mirror.map!.ground![6]).toBe(0);
  mirror.applyVoxelEdits([{ x: 1, y: 1, action: 'dig', gid: 7 }]);
  expect(collision[5]).toBe(1);
  expect(mirror.voxelEdits.get('1,1')?.action).toBe('dig');
  mirror.applyVoxelEdits([], true);
  expect(mirror.voxelEdits.size).toBe(0);
  expect(collision[5]).toBe(0);
  expect(collision[6]).toBe(1);
  expect(mirror.map!.ground![6]).toBe(7);
});

it('keeps edits received before the asynchronous map and reapplies them when it arrives', () => {
  const mirror = new WorldMirror();
  mirror.applyVoxelEdits([{ x: 2, y: 1, action: 'place', gid: 0 }], true);
  mirror.setMap(map());
  expect(mirror.map!.collision[6]).toBe(0);
  expect(mirror.map!.ground![6]).toBe(0);
  mirror.reset();
  expect(mirror.voxelEdits.size).toBe(0);
  expect(mirror.voxelDig).toBeNull();
});

it('shares the explicit edit height rule without hiding completed structures', () => {
  const structures = new Map<string, { phase: string; tiles: [number, number][] }>();
  const edits = new Map([['2,1', { x: 2, y: 1, action: 'place' as 'place' | 'dig', gid: 0 }]]);
  expect(effectiveHeight(2, 1, () => 3, structures, edits)).toBe(2);
  edits.get('2,1')!.action = 'dig';
  expect(effectiveHeight(2, 1, () => 3, structures, edits)).toBe(3);
  structures.set('house', { phase: 'built', tiles: [[2, 1]] });
  expect(effectiveHeight(2, 1, () => 3, structures, edits)).toBe(2);
});
