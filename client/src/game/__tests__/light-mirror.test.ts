import { expect, it } from 'vitest';
import { WorldMirror } from '../world-mirror';
import type { components } from '@shared/protocol';

const light = { rtoken: 'lt-a', x: 11, y: 10, kind: 'fire', radius: 5, flicker: 0.4 };

it('applies light births, complete upserts and removals while keeping legacy patches', () => {
  const mirror = new WorldMirror();
  mirror.applyLightDeltas([{ op: 'add', ...light }]);
  expect(mirror.lights.get(light.rtoken)).toEqual(light);
  mirror.applyLightDeltas([{ rtoken: light.rtoken, flicker: 0.7 }]);
  expect(mirror.lights.get(light.rtoken)).toEqual({ ...light, flicker: 0.7 });
  mirror.applyLightDeltas([{ op: 'add', ...light, x: 12 }]);
  expect(mirror.lights.get(light.rtoken)?.x).toBe(12);
  mirror.applyLightDeltas([{ op: 'remove', rtoken: light.rtoken }]);
  expect(mirror.lights.size).toBe(0);
});

it('ignores incomplete and nonfinite new light rows without creating phantom emitters', () => {
  const mirror = new WorldMirror();
  mirror.applyLightDeltas([{ rtoken: 'unknown', flicker: 0.5 }]);
  mirror.applyLightDeltas([{ op: 'add', ...light, x: NaN }]);
  mirror.applyLightDeltas([{ op: 'add', ...light, radius: Infinity }]);
  mirror.applyLightDeltas([
    { ...light, op: 'unknown' } as unknown as components['schemas']['LightDelta'],
    { ...light, rtoken: null } as unknown as components['schemas']['LightDelta'],
  ]);
  expect(mirror.lights.size).toBe(0);
});

it('full snapshots and mirror reset clear lights from an earlier world', () => {
  const mirror = new WorldMirror();
  mirror.applySnapshot([], [light]);
  mirror.applySnapshot([], []);
  expect(mirror.lights.size).toBe(0);
  mirror.applyLightDeltas([{ op: 'add', ...light }]);
  mirror.reset();
  expect(mirror.lights.size).toBe(0);
});
