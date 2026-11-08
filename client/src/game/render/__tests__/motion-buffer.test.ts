import { expect, it } from 'vitest';
import {
  HISTORY_SAMPLES,
  newestSample,
  pushSample,
  rampDelay,
  sampleAt,
  type TimedSample,
} from '../motion-buffer';

const at = (t: number, x: number, y = 0, z = 1): TimedSample => ({ at: t, x, y, z });

it('holds the first sample before the replay instant reaches it', () => {
  expect(sampleAt([at(0, 0), at(100, 1)], -50)).toEqual({ x: 0, y: 0, z: 1 });
});

it('interpolates between the two samples bracketing the instant', () => {
  const samples = [at(0, 0), at(100, 1)];
  expect(sampleAt(samples, 0).x).toBe(0);
  expect(sampleAt(samples, 25).x).toBeCloseTo(0.25);
  expect(sampleAt(samples, 50).x).toBeCloseTo(0.5);
  expect(sampleAt(samples, 100).x).toBe(1);
});

it('holds the newest sample when the instant is later than the data', () => {
  // A late arrival: the actor keeps the last known position rather than
  // extrapolating past it.
  expect(sampleAt([at(0, 0), at(100, 1)], 200)).toEqual({ x: 1, y: 0, z: 1 });
});

it('picks the right bracket out of a longer history', () => {
  const samples = [at(0, 0), at(100, 1), at(200, 2), at(300, 4)];
  expect(sampleAt(samples, 250).x).toBeCloseTo(3);
  expect(sampleAt(samples, 120).x).toBeCloseTo(1.2);
});

it('resolves duplicate timestamps to the later sample', () => {
  expect(sampleAt([at(0, 0), at(100, 1), at(100, 2)], 100).x).toBe(2);
});

it('appends samples in arrival order and keeps the newest last', () => {
  let samples: readonly TimedSample[] = [];
  samples = pushSample(samples, at(0, 0), 3);
  samples = pushSample(samples, at(100, 1), 3);
  expect(samples.map((s) => s.x)).toEqual([0, 1]);
  expect(newestSample(samples).x).toBe(1);
});

it('drops the history when the jump is too large to be walking', () => {
  let samples: readonly TimedSample[] = [];
  samples = pushSample(samples, at(0, 0), 3);
  samples = pushSample(samples, at(100, 1), 3);
  samples = pushSample(samples, at(200, 12), 3);
  expect(samples).toHaveLength(1);
  expect(newestSample(samples).x).toBe(12);
});

it('keeps the queue bounded no matter how fast the actor moves', () => {
  let samples: readonly TimedSample[] = [];
  for (let i = 0; i < 5000; i++) samples = pushSample(samples, at(i * 15.6, i), 3);
  expect(samples.length).toBeLessThanOrEqual(HISTORY_SAMPLES);
  expect(newestSample(samples).x).toBe(4999);
});

it('uses the caller units for the jump limit', () => {
  // Screen pixels: a 40px step is ordinary movement, not a teleport.
  let pixels: readonly TimedSample[] = [];
  pixels = pushSample(pixels, at(0, 0, 0, 0), 1000);
  pixels = pushSample(pixels, at(100, 40, 40, 0), 1000);
  expect(pixels).toHaveLength(2);
  // Tiles: the same numbers would be an impossible jump.
  let tiles: readonly TimedSample[] = [];
  tiles = pushSample(tiles, at(0, 0, 0, 0), 3);
  tiles = pushSample(tiles, at(100, 40, 40, 0), 3);
  expect(tiles).toHaveLength(1);
});

it('ramps the delay toward its nominal value without overshooting', () => {
  // Growing: a slowdown lengthens the lag one bounded step at a time.
  expect(rampDelay(50, 250, 16)).toBeGreaterThan(50);
  expect(rampDelay(50, 250, 16)).toBeLessThan(250);
  // Shrinking: a speed-up shortens it the same way.
  expect(rampDelay(250, 50, 16)).toBeLessThan(250);
  // Lands exactly once the gap is smaller than a step.
  expect(rampDelay(249, 250, 16)).toBe(250);
  // A zero-length frame changes nothing.
  expect(rampDelay(100, 250, 0)).toBe(100);
});
