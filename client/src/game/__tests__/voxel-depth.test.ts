import { expect, it } from 'vitest';
import { WorldMirror, type VoxelEdit } from '../world-mirror';
import { effectiveHeight, isoProject, screenBounds } from '../render/iso';
import { pickGround } from '../render/voxel-picking';
import { canStep } from '../movement';

function row(height: number, gid = 0): VoxelEdit {
  return { x: 2, y: 1, action: 'dig', gid, height } as VoxelEdit;
}

function world() {
  const mirror = new WorldMirror();
  mirror.setMap({ w: 4, h: 4, tileset: 'grid', collision: new Uint8Array(16) });
  return mirror;
}

it('uses the committed result after repeated digs rather than static height minus one', () => {
  const mirror = world();
  mirror.applyVoxelEdits([row(1, 7)]);
  expect(effectiveHeight(2, 1, () => 3, mirror.structures, mirror.voxelEdits)).toBe(1);
});

it('invalidates height-only edits even when action and blocked gid have not changed', () => {
  const mirror = world();
  mirror.applyVoxelEdits([row(2)]);
  const version = mirror.terrainVersion;
  mirror.applyVoxelEdits([row(0)]);
  expect(mirror.terrainVersion).toBeGreaterThan(version);
  expect(effectiveHeight(2, 1, () => 3, mirror.structures, mirror.voxelEdits)).toBe(0);
});

it.each([0, 1, 2, 3])('admits mouse and cardinal keyboard at height %i only with valid collision', (height) => {
  const mirror = world();
  mirror.applyVoxelEdits([row(height, 7)]);
  const heightAt = (x: number, y: number) =>
    effectiveHeight(x, y, () => 3, mirror.structures, mirror.voxelEdits);
  const { sx, sy } = isoProject(2, 1, 1, screenBounds(4, 4));
  const walkable = (x: number, y: number) => mirror.map!.collision[y * 4 + x] === 1;
  expect(walkable(2, 1)).toBe(height === 1);
  expect(canStep(mirror.map!, { x: 1, y: 1 }, { x: 2, y: 1 })).toBe(height === 1);
  expect(pickGround(sx, sy, 4, 4, heightAt, walkable)).toEqual(height === 1 ? { x: 2, y: 1 } : null);
});

it.each([-1, 4, 1.5, true, '1', null, undefined, NaN])('rejects invalid wire height %s', (height) => {
  const mirror = world();
  mirror.applyVoxelEdits([{ ...row(1, 7), height } as unknown as VoxelEdit]);
  expect(mirror.voxelEdits.size).toBe(0);
  expect(mirror.map!.collision[6]).toBe(0);
});

it('retains blocked height-one earth banks without inventing walkability', () => {
  const mirror = world();
  mirror.applyVoxelEdits([row(1)]);
  expect(effectiveHeight(2, 1, () => 3, mirror.structures, mirror.voxelEdits)).toBe(1);
  expect(canStep(mirror.map!, { x: 1, y: 1 }, { x: 2, y: 1 })).toBe(false);
});
