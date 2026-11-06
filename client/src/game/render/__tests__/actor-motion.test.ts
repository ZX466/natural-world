import { expect, it } from 'vitest';
import { advanceMotion, cameraFacing } from '../actor-motion';

it('interpolates each snapshot over 200ms and keeps facing when standing', () => {
  const a = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, 16, 1);
  const b = advanceMotion(a, { x: 1, y: 0, height: 1 }, 100, 16, 1);
  expect(b.x).toBe(0);
  const half = advanceMotion(b, { x: 1, y: 0, height: 1 }, 200, 16, 1);
  expect(half.x).toBeCloseTo(0.5);
  expect(half.facing).toBe('e');
  expect(half.animClock).toBeGreaterThanOrEqual(0);
  const end = advanceMotion(half, { x: 1, y: 0, height: 1 }, 300, 16, 1);
  expect(end.x).toBe(1);
  expect(end.animClock).toBe(-1);
  expect(end.facing).toBe('e');
});

it('starts a new snapshot at the current visual position and scales the window with speed', () => {
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, 16, 1);
  state = advanceMotion(state, { x: 1, y: 0, height: 1 }, 10, 16, 1);
  state = advanceMotion(state, { x: 1, y: 0, height: 1 }, 110, 16, 1);
  const redirected = advanceMotion(state, { x: 2, y: 0, height: 1 }, 110, 16, 16);
  expect(redirected.x).toBeCloseTo(0.5);
  expect(advanceMotion(redirected, { x: 2, y: 0, height: 1 }, 130, 16, 16).x).toBe(2);
});

it.each([
  ['s', 0, 's'],
  ['n', 0, 'n'],
  ['e', 0, 'e'],
  ['s', 180, 'n'],
  ['n', 180, 's'],
  ['e', 90, 's'],
] as const)('selects the camera-relative %s frame at yaw %i', (facing, yaw, expected) => {
  expect(cameraFacing(facing, yaw)).toBe(expected);
});
