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
  mirror.applyVoxelEdits([{ x: 2, y: 1, action: 'place', gid: 0, height: 2 }]);
  expect(mirror.map!.collision).toBe(collision);
  expect(collision[6]).toBe(0);
  expect(mirror.map!.ground![6]).toBe(0);
  mirror.applyVoxelEdits([{ x: 1, y: 1, action: 'dig', gid: 7, height: 1 }]);
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
  mirror.applyVoxelEdits([{ x: 2, y: 1, action: 'place', gid: 0, height: 2 }], true);
  mirror.setMap(map());
  expect(mirror.map!.collision[6]).toBe(0);
  expect(mirror.map!.ground![6]).toBe(0);
  mirror.reset();
  expect(mirror.voxelEdits.size).toBe(0);
  expect(mirror.voxelDig).toBeNull();
});

it('shares the explicit edit height rule without hiding completed structures', () => {
  const structures = new Map<string, { phase: string; tiles: [number, number][] }>();
  const edits = new Map([
    ['2,1', { x: 2, y: 1, action: 'place' as 'place' | 'dig', gid: 0, height: 2 }],
  ]);
  expect(effectiveHeight(2, 1, () => 3, structures, edits)).toBe(2);
  edits.get('2,1')!.action = 'dig';
  edits.get('2,1')!.height = 1;
  expect(effectiveHeight(2, 1, () => 3, structures, edits)).toBe(1);
  structures.set('house', { phase: 'built', tiles: [[2, 1]] });
  expect(effectiveHeight(2, 1, () => 3, structures, edits)).toBe(2);
});

it('increments the terrain version for map, edit, structure and reset changes', () => {
  const mirror = new WorldMirror();
  expect(mirror.terrainVersion).toBe(0);
  mirror.setMap(map());
  const mapped = mirror.terrainVersion;
  expect(mapped).toBeGreaterThan(0);
  mirror.applyVoxelEdits([{ x: 2, y: 1, action: 'place', gid: 0, height: 2 }]);
  const edited = mirror.terrainVersion;
  expect(edited).toBeGreaterThan(mapped);
  mirror.applyStructures([{ rtoken: 'house', x: 1, y: 1, phase: 'built' }]);
  const built = mirror.terrainVersion;
  expect(built).toBeGreaterThan(edited);
  mirror.applyStructures([{ rtoken: 'house', x: 1, y: 1, phase: 'collapsing' }]);
  const collapsing = mirror.terrainVersion;
  expect(collapsing).toBeGreaterThan(built);
  mirror.applyStructures([{ rtoken: 'house', op: 'remove' }]);
  expect(mirror.terrainVersion).toBeGreaterThan(collapsing);
  const removed = mirror.terrainVersion;
  mirror.reset();
  expect(mirror.terrainVersion).toBeGreaterThan(removed);
});

it('keeps the terrain version stable for duplicate, invalid and progress-only updates', () => {
  const mirror = new WorldMirror();
  mirror.setMap(map());
  const row = { x: 2, y: 1, action: 'place' as const, gid: 0, height: 2 };
  mirror.applyVoxelEdits([row]);
  mirror.applyStructures([{ rtoken: 'house', x: 1, y: 1, phase: 'built' }]);
  const version = mirror.terrainVersion;
  mirror.applyVoxelEdits([row, { ...row, x: -1 }]);
  mirror.applyStructures([{ rtoken: 'house', x: 1, y: 1, phase: 'built' }]);
  mirror.applyStructures([{ rtoken: 'absent', op: 'remove' }]);
  mirror.applyVoxelState({ inventory: { earth: 2 }, dig: { x: 2, y: 1, progress: 0.5 } });
  mirror.applyActorDeltas([]);
  expect(mirror.terrainVersion).toBe(version);
});

it('invalidates the terrain for an empty edit snapshot that restores in-place ground', () => {
  const mirror = new WorldMirror();
  mirror.setMap(map());
  mirror.applyVoxelEdits([{ x: 2, y: 1, action: 'place', gid: 0, height: 2 }]);
  const version = mirror.terrainVersion;
  mirror.applyVoxelEdits([], true);
  expect(mirror.terrainVersion).toBeGreaterThan(version);
  expect(mirror.map!.ground![6]).toBe(7);
});

it('invalidates an empty structure snapshot independently of voxel snapshots', () => {
  const mirror = new WorldMirror();
  mirror.applyStructures([{ rtoken: 'house', x: 1, y: 1, phase: 'built' }]);
  const version = mirror.terrainVersion;
  mirror.applyStructures([], true);
  expect(mirror.structures.size).toBe(0);
  expect(mirror.terrainVersion).toBeGreaterThan(version);
});

it('accepts legacy earth-only stock and whole nonnegative stone/wood counts', () => {
  const mirror = new WorldMirror();
  expect(mirror.applyVoxelState({ inventory: { earth: 2 }, dig: null })).toBe(true);
  expect(
    mirror.applyVoxelState({
      inventory: { earth: 0, stone: 2, wood: 3 },
      dig: { x: 1, y: 1, progress: 0.5 },
    }),
  ).toBe(true);
  expect(mirror.voxelDig).toEqual({ x: 1, y: 1, progress: 0.5 });
});

it.each(['earth', 'stone', 'wood'] as const)(
  'rejects malformed %s stock without changing dig state',
  (material) => {
    const mirror = new WorldMirror();
    mirror.applyVoxelState({ inventory: { earth: 1 }, dig: { x: 1, y: 1, progress: 0.4 } });
    for (const value of [-1, 0.5, NaN, Infinity, '2', null, true]) {
      const state = {
        inventory: { earth: 1, stone: 2, wood: 3, [material]: value },
        dig: null,
      } as unknown as Parameters<WorldMirror['applyVoxelState']>[0];
      expect(mirror.applyVoxelState(state), `${material}: ${String(value)}`).toBe(false);
      expect(mirror.voxelDig).toEqual({ x: 1, y: 1, progress: 0.4 });
    }
  },
);

it('still requires earth when optional materials are supplied', () => {
  const mirror = new WorldMirror();
  expect(
    mirror.applyVoxelState({
      inventory: { stone: 1, wood: 1 },
      dig: null,
    } as unknown as Parameters<WorldMirror['applyVoxelState']>[0]),
  ).toBe(false);
});
