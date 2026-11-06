import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createWorldInput, movementDirection } from '../three-input';

class Canvas extends EventTarget {
  setPointerCapture() {}
  getBoundingClientRect() {
    return { left: 0, top: 0, width: 800, height: 600 };
  }
}
function dispatch(target: EventTarget, name: string, fields: Record<string, unknown> = {}) {
  const event = new Event(name, { cancelable: true });
  for (const [key, value] of Object.entries(fields)) Object.defineProperty(event, key, { value });
  target.dispatchEvent(event);
}
function setup(blocked = false) {
  const canvas = new Canvas(),
    keyboard = new EventTarget();
  let stamp = '0',
    typing = false,
    enabled = true,
    allowed = true,
    revision = 0;
  let ground = { x: 3, y: 2 };
  const move = vi.fn(() => true),
    voxel = vi.fn(),
    rotate = vi.fn(),
    zoom = vi.fn();
  const ports = {
    move,
    voxel,
    rotate,
    zoom,
    error: vi.fn(),
    pickEdit: () => ({ x: 4, y: 3 }),
    pickGround: () => ground,
    blocked: () => blocked,
    hero: () => ({ x: 3, y: 3 }),
    step: () => allowed,
    revision: () => revision,
    enabled: () => enabled,
    typing: () => typing,
    epoch: () => stamp,
    azimuth: () => 0,
  };
  const input = createWorldInput(canvas as unknown as HTMLCanvasElement, ports, keyboard);
  const pointer = (button = 0, x = 100, y = 100) => ({
    button,
    pointerId: 1,
    clientX: x,
    clientY: y,
  });
  return {
    canvas,
    keyboard,
    input,
    move,
    voxel,
    rotate,
    zoom,
    pointer,
    error: ports.error,
    block() {
      allowed = false;
    },
    unblock() {
      allowed = true;
      revision++;
    },
    ground(point: { x: number; y: number }) {
      ground = point;
    },
    reset() {
      stamp = '1';
    },
    type() {
      typing = true;
    },
    close() {
      enabled = false;
    },
  };
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it('keeps a short press on a high block as movement on the independent ground ray', () => {
  const { canvas, input, move, voxel, pointer } = setup(true);
  dispatch(canvas, 'pointerdown', pointer());
  vi.advanceTimersByTime(100);
  dispatch(canvas, 'pointerup', pointer());
  expect(move).toHaveBeenCalledWith({ x: 3, y: 2 });
  expect(voxel).not.toHaveBeenCalled();
  input.dispose();
});

it('holds 150ms to dig the visible column and sends one cancellation on release', () => {
  const { canvas, input, move, voxel, pointer } = setup(true);
  dispatch(canvas, 'pointerdown', pointer());
  vi.advanceTimersByTime(149);
  expect(voxel).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);
  expect(voxel).toHaveBeenCalledWith('dig_start', { x: 4, y: 3 });
  dispatch(canvas, 'pointerup', pointer());
  expect(voxel).toHaveBeenLastCalledWith('dig_cancel', { x: 4, y: 3 });
  expect(move).not.toHaveBeenCalled();
  input.dispose();
});

it('places on a right click but right/middle drag only rotates the camera', () => {
  const { canvas, input, voxel, rotate, pointer } = setup();
  dispatch(canvas, 'pointerdown', pointer(2));
  dispatch(canvas, 'pointerup', pointer(2));
  expect(voxel).toHaveBeenCalledWith('place', { x: 4, y: 3 });
  voxel.mockClear();
  for (const button of [1, 2]) {
    dispatch(canvas, 'pointerdown', pointer(button));
    dispatch(canvas, 'pointermove', pointer(button, 150, 120));
    dispatch(canvas, 'pointerup', pointer(button, 150, 120));
  }
  expect(rotate).toHaveBeenCalled();
  expect(voxel).not.toHaveBeenCalled();
  input.dispose();
});

it('drops old gestures on snapshot replacement or disconnect without sending to a new world', () => {
  const fixture = setup(true);
  dispatch(fixture.canvas, 'pointerdown', fixture.pointer());
  vi.advanceTimersByTime(150);
  fixture.voxel.mockClear();
  fixture.reset();
  fixture.input.tick();
  dispatch(fixture.canvas, 'pointerup', fixture.pointer());
  expect(fixture.voxel).not.toHaveBeenCalled();
  fixture.close();
  dispatch(fixture.canvas, 'pointerdown', fixture.pointer());
  vi.advanceTimersByTime(200);
  expect(fixture.voxel).not.toHaveBeenCalled();
  fixture.input.dispose();
});

it('moves with camera-relative keys and stops when text input gains focus', () => {
  const fixture = setup();
  dispatch(fixture.keyboard, 'keydown', { code: 'KeyW', key: 'w' });
  expect(fixture.move).toHaveBeenLastCalledWith({ x: 3, y: 2 });
  fixture.type();
  fixture.input.tick();
  expect(fixture.move).toHaveBeenLastCalledWith({ x: 3, y: 3 });
  fixture.move.mockClear();
  dispatch(fixture.keyboard, 'keydown', { code: 'KeyD', key: 'd' });
  expect(fixture.move).not.toHaveBeenCalled();
  fixture.input.dispose();
});

it('does not spam a held blocked key and retries when collision changes', () => {
  const fixture = setup();
  fixture.block();
  dispatch(fixture.keyboard, 'keydown', { code: 'KeyW' });
  for (let i = 0; i < 4; i++) fixture.input.tick();
  expect(fixture.error).toHaveBeenCalledTimes(1);
  fixture.unblock();
  fixture.input.tick();
  expect(fixture.move).toHaveBeenCalledWith({ x: 3, y: 2 });
  fixture.input.dispose();
});

it('does not start a delayed dig if text input gained focus before the deadline', () => {
  const fixture = setup(true);
  dispatch(fixture.canvas, 'pointerdown', fixture.pointer());
  fixture.type();
  vi.advanceTimersByTime(150);
  expect(fixture.voxel).not.toHaveBeenCalled();
  fixture.input.dispose();
});

it('throttles drag movement and flushes its final destination on release', () => {
  const fixture = setup();
  dispatch(fixture.canvas, 'pointerdown', fixture.pointer());
  fixture.ground({ x: 4, y: 2 });
  dispatch(fixture.canvas, 'pointermove', fixture.pointer(0, 200));
  expect(fixture.move).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(100);
  fixture.input.tick();
  expect(fixture.move).toHaveBeenLastCalledWith({ x: 4, y: 2 });
  fixture.ground({ x: 5, y: 2 });
  dispatch(fixture.canvas, 'pointermove', fixture.pointer(0, 220));
  dispatch(fixture.canvas, 'pointerup', fixture.pointer(0, 220));
  expect(fixture.move).toHaveBeenCalledTimes(3);
  expect(fixture.move).toHaveBeenLastCalledWith({ x: 5, y: 2 });
  fixture.input.dispose();
});

it.each([
  [0, ['KeyW'], { x: 0, y: -1 }],
  [90, ['KeyW'], { x: -1, y: 0 }],
  [180, ['KeyW'], { x: 0, y: 1 }],
  [0, ['KeyW', 'KeyD'], { x: 1, y: -1 }],
] as const)('converts movement at yaw %i', (yaw, keys, expected) => {
  expect(movementDirection(new Set(keys), yaw)).toEqual(expected);
});
