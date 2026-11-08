import { expect, it } from 'vitest';
import {
  HISTORY_SAMPLES,
  MAX_HISTORY_SAMPLES,
  newestSample,
  pushSample,
  rampDelay,
  sampleAt,
  type TimedSample,
  type FlightSample,
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

it('retains the predecessor of a requested replay span when observations are dense', () => {
  let samples: readonly TimedSample[] = [];
  for (let time = 0; time <= 600; time += 20)
    samples = pushSample(samples, at(time, time / 100), 3, HISTORY_SAMPLES, 533);
  expect(samples.length).toBeGreaterThan(HISTORY_SAMPLES);
  expect(samples[0]!.at).toBe(60);
  expect(samples[1]!.at).toBe(80);
  expect(sampleAt(samples, 67).x).toBeCloseTo(0.67);
});

it('bounds dense history while retaining both sides of the replay instant', () => {
  let samples: readonly TimedSample[] = [];
  for (let time = 0; time <= 2000; time++)
    samples = pushSample(samples, at(time, time / 100), 3, HISTORY_SAMPLES, 533);
  expect(MAX_HISTORY_SAMPLES).toBe(128);
  expect(samples.length).toBeLessThanOrEqual(MAX_HISTORY_SAMPLES);
  expect(samples[0]!.at).toBeLessThanOrEqual(1467);
  expect(samples[1]!.at).toBeGreaterThan(1467);
  expect(newestSample(samples).at).toBe(2000);
  expect(sampleAt(samples, 1467).x).toBeCloseTo(14.67);
});

const flight: FlightSample = {
  id: 'jump-1',
  progress: 0,
  start: { x: 0, y: 0, z: 1 },
  end: { x: 2, y: 0, z: 3 },
  arc: { x: 0, y: 0, z: 1 },
};

it('interpolates certified flight progress and evaluates the arc between matching endpoints', () => {
  const samples = [
    { ...at(0, 0), flight },
    { ...at(600, 2, 0, 3), flight: { ...flight, progress: 1 } },
  ];
  expect(sampleAt(samples, 0)).toEqual({ x: 0, y: 0, z: 1, airborne: false });
  expect(sampleAt(samples, 150)).toEqual({ x: 0.5, y: 0, z: 2.25, airborne: true });
  expect(sampleAt(samples, 300)).toEqual({ x: 1, y: 0, z: 3, airborne: true });
  expect(sampleAt(samples, 600)).toEqual({ x: 2, y: 0, z: 3, airborne: false });
  expect(sampleAt(samples, 900)).toEqual({ x: 2, y: 0, z: 3, airborne: false });
});

it('uses the same arc math for projected pixel geometry', () => {
  const projected = {
    ...flight,
    start: { x: 0, y: 0, z: 0 },
    end: { x: 32, y: 0, z: 0 },
    arc: { x: 0, y: -24, z: 0 },
  };
  const samples = [
    { ...at(0, 0, 0, 0), flight: projected },
    { ...at(600, 32, 0, 0), flight: { ...projected, progress: 1 } },
  ];
  expect(sampleAt(samples, 150)).toEqual({ x: 8, y: -18, z: 0, airborne: true });
});

it.each([
  { ...flight, id: 'another-flight', progress: 1 },
  { ...flight, arc: { x: 0, y: 0, z: 2 }, progress: 1 },
])('does not join flights with different identities or geometry', (after) => {
  expect(
    sampleAt(
      [
        { ...at(0, 0), flight },
        { ...at(600, 2, 0, 3), flight: after },
      ],
      300,
    ),
  ).toEqual({ x: 1, y: 0, z: 2 });
});

it('holds received flight progress without extrapolating through a pause', () => {
  const samples = [
    { ...at(0, 0), flight },
    { ...at(300, 1, 0, 3), flight: { ...flight, progress: 0.5 } },
  ];
  expect(sampleAt(samples, 10000)).toEqual({ x: 1, y: 0, z: 3, airborne: true });
});
