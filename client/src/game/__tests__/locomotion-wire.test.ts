import { expect, it } from 'vitest';
import * as THREE from 'three';
import { WorldMirror, type MapStatic } from '../world-mirror';
import { canStep, movementFailure } from '../movement';
import { groundFromRay } from '../render/three/three-picking';
import { worldOf } from '../render/three/three-projection';

const jump = {
  rtoken: 'flight-1',
  start_x: 0,
  start_y: 0,
  goal_x: 1,
  goal_y: 0,
  start_height: 1,
  target_height: 2,
  progress: 0.3,
  active: true,
  duration: 0.6,
  arc_height: 1.5,
};
const actor = { rtoken: 'hero', x: 0, y: 0, facing: 's', sprite: 'chenmo', anim: 'idle' } as const;
function map(): MapStatic {
  return {
    w: 4,
    h: 4,
    tileset: 'test',
    collision: Uint8Array.from([1, 0, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1]),
  };
}
const heightAt = (x: number, y: number) =>
  (y === 0 && (x === 1 || x === 2)) || (x === 1 && y === 1) ? 2 : 1;

it('applies authoritative gait/elevation/flight changes without losing sparse deltas', () => {
  const mirror = new WorldMirror();
  mirror.applySnapshot([{ ...actor, elevation: 1, gait: 'walk', jump }], []);
  const before = mirror.locomotionRevision;
  mirror.applyActorDeltas([
    { rtoken: 'hero', elevation: 2, gait: 'run', jump: { ...jump, active: false, progress: 1 } },
  ]);
  expect(mirror.actors.get('hero')).toMatchObject({
    x: 0,
    y: 0,
    elevation: 2,
    gait: 'run',
    jump: { active: false, progress: 1 },
  });
  expect(mirror.locomotionRevision).toBeGreaterThan(before);
  const completed = mirror.locomotionRevision;
  mirror.applyActorDeltas([{ rtoken: 'hero', jump: { ...jump, active: false, progress: 1 } }]);
  expect(mirror.locomotionRevision).toBe(completed);
  mirror.applyActorDeltas([{ rtoken: 'hero', jump: null }]);
  expect(mirror.actors.get('hero')?.jump).toBeNull();
});

it('drops malformed new pose fields instead of rendering NaN or retaining a stuck flight', () => {
  const mirror = new WorldMirror();
  mirror.applySnapshot([{ ...actor, jump: { ...jump, progress: Number.NaN }, elevation: 99 }], []);
  expect(mirror.actors.get('hero')?.jump).toBeNull();
  expect(mirror.actors.get('hero')?.elevation).toBeUndefined();
  mirror.applyActorDeltas([{ rtoken: 'hero', jump: { ...jump, duration: -1 } }]);
  expect(mirror.actors.get('hero')?.jump).toBeNull();
});

it('shares the installed terrain lookup with movement without changing collision flags', () => {
  const mirror = new WorldMirror();
  mirror.setMap(map());
  mirror.setHeightLookup(heightAt);
  expect(mirror.heightAt(1, 0)).toBe(2);
  const height = (x: number, y: number) => mirror.heightAt(x, y);
  expect(canStep(mirror.map!, { x: 1, y: 0 }, { x: 2, y: 0 }, height, 2)).toBe(true);
  expect(movementFailure(mirror.map!, { x: 1, y: 0 }, { x: 2, y: 0 }, height, 2)).toBeNull();
  expect(canStep(mirror.map!, { x: 0, y: 0 }, { x: 1, y: 0 })).toBe(false);
  expect(canStep(mirror.map!, { x: 2, y: 0 }, { x: 3, y: 0 }, height, 2)).toBe(false);
  expect(canStep(mirror.map!, { x: 2, y: 0 }, { x: 3, y: 0 }, height, 1)).toBe(false);
  expect(mirror.map!.collision[1]).toBe(0);
});

it('uses an independent movement plane at the standing height without editing ground topology', () => {
  const grid = map();
  const origin = worldOf(2, 0, 4, 4).setY(8);
  const ray = new THREE.Ray(origin, new THREE.Vector3(0, -1, 0));
  expect(groundFromRay(ray, grid, heightAt, 2)).toEqual({ x: 2, y: 0 });
  expect(groundFromRay(ray, grid, heightAt)).toBeNull();
  expect(grid.collision[2]).toBe(0);
});
