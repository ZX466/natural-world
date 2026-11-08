import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createWorldInput, movementDirection, type WorldInputPorts } from '../three-input';
import { canStep, type MovePoint } from '../../../movement';
import type { MapStatic } from '../../../world-mirror';

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
    revision = 0,
    azimuth = 0;
  let hero = { x: 3, y: 3 };
  let ground = { x: 3, y: 2 };
  const move = vi.fn<WorldInputPorts['move']>(() => true),
    step = vi.fn<WorldInputPorts['step']>(() => allowed),
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
    hero: () => hero,
    step,
    revision: () => revision,
    enabled: () => enabled,
    typing: () => typing,
    epoch: () => stamp,
    azimuth: () => azimuth,
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
    step,
    voxel,
    rotate,
    zoom,
    pointer,
    error: ports.error,
    get hero() {
      return hero;
    },
    arrive(point: MovePoint) {
      hero = point;
    },
    turn(degrees: number) {
      azimuth = degrees;
    },
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

function walkingMap(...walkable: MovePoint[]): MapStatic {
  const map = { w: 7, h: 7, tileset: 'test', collision: new Uint8Array(49) };
  for (const point of walkable) map.collision[point.y * map.w + point.x] = 1;
  return map;
}

const defaultDirections = [
  ['KeyW', { x: 1, y: 1 }],
  ['KeyS', { x: -1, y: -1 }],
  ['KeyA', { x: 1, y: -1 }],
  ['KeyD', { x: -1, y: 1 }],
] as const;

it.each(defaultDirections)(
  'slides %s horizontally when its default diagonal is blocked',
  (key, d) => {
    const fixture = setup();
    fixture.turn(225);
    expect(movementDirection(new Set([key]), 225)).toEqual(d);
    const horizontal = { x: 3 + d.x, y: 3 };
    const vertical = { x: 3, y: 3 + d.y };
    const map = walkingMap(fixture.hero, horizontal, vertical);
    fixture.step.mockImplementation((point) => canStep(map, fixture.hero, point));
    dispatch(fixture.keyboard, 'keydown', { code: key });
    expect(fixture.move).toHaveBeenCalledExactlyOnceWith(horizontal);
    expect(fixture.error).not.toHaveBeenCalled();
    fixture.input.dispose();
  },
);

it.each(defaultDirections)(
  'slides %s vertically without cutting a blocked diagonal corner',
  (key, d) => {
    const fixture = setup();
    fixture.turn(225);
    const diagonal = { x: 3 + d.x, y: 3 + d.y };
    const vertical = { x: 3, y: 3 + d.y };
    const map = walkingMap(fixture.hero, diagonal, vertical);
    expect(canStep(map, fixture.hero, diagonal)).toBe(false);
    fixture.step.mockImplementation((point) => canStep(map, fixture.hero, point));
    dispatch(fixture.keyboard, 'keydown', { code: key });
    expect(fixture.move).toHaveBeenCalledExactlyOnceWith(vertical);
    expect(fixture.error).not.toHaveBeenCalled();
    fixture.input.dispose();
  },
);

it('continues a held key for three acknowledged cells through a diagonal and axial corridor', () => {
  const fixture = setup();
  fixture.turn(225);
  const map = walkingMap(
    fixture.hero,
    { x: 2, y: 3 },
    { x: 3, y: 2 },
    { x: 2, y: 2 },
    { x: 2, y: 1 },
    { x: 2, y: 0 },
  );
  fixture.step.mockImplementation((point) => canStep(map, fixture.hero, point));
  dispatch(fixture.keyboard, 'keydown', { code: 'KeyS' });
  for (const [index, position] of [
    { x: 2, y: 2 },
    { x: 2, y: 1 },
  ].entries()) {
    for (let frame = 0; frame < 5; frame++) fixture.input.tick();
    expect(fixture.move).toHaveBeenCalledTimes(index + 1);
    fixture.arrive(position);
    fixture.input.tick();
  }
  expect(fixture.move.mock.calls).toEqual([[{ x: 2, y: 2 }], [{ x: 2, y: 1 }], [{ x: 2, y: 0 }]]);
  expect(fixture.error).not.toHaveBeenCalled();
  fixture.input.dispose();
});

it('reports a diagonal obstruction once only when both axes are blocked and retries a changed map', () => {
  const fixture = setup();
  fixture.turn(225);
  const map = walkingMap(fixture.hero, { x: 4, y: 4 });
  fixture.step.mockImplementation((point) => canStep(map, fixture.hero, point));
  dispatch(fixture.keyboard, 'keydown', { code: 'KeyW' });
  for (let frame = 0; frame < 20; frame++) fixture.input.tick();
  dispatch(fixture.keyboard, 'keydown', { code: 'KeyW', repeat: true });
  expect(fixture.error).toHaveBeenCalledTimes(1);
  expect(fixture.move).not.toHaveBeenCalled();
  map.collision[3 * map.w + 4] = 1;
  fixture.unblock();
  fixture.input.tick();
  expect(fixture.move).toHaveBeenCalledExactlyOnceWith({ x: 4, y: 3 });
  expect(fixture.error).toHaveBeenCalledTimes(1);
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

it.each([0, 149, 150, 180])(
  'ends a lost-capture gesture at %ims without a late dig or duplicate cancel',
  (elapsed) => {
    const fixture = setup(true);
    dispatch(fixture.canvas, 'pointerdown', fixture.pointer());
    vi.advanceTimersByTime(elapsed);
    dispatch(fixture.canvas, 'lostpointercapture', { pointerId: 1 });
    vi.advanceTimersByTime(200);
    const starts = fixture.voxel.mock.calls.filter(([action]) => action === 'dig_start');
    const cancellations = fixture.voxel.mock.calls.filter(([action]) => action === 'dig_cancel');
    expect(starts).toHaveLength(elapsed >= 150 ? 1 : 0);
    expect(cancellations).toHaveLength(elapsed >= 150 ? 1 : 0);
    dispatch(fixture.canvas, 'pointerup', fixture.pointer());
    dispatch(fixture.canvas, 'lostpointercapture', { pointerId: 1 });
    expect(fixture.voxel.mock.calls.filter(([action]) => action === 'dig_cancel')).toHaveLength(
      cancellations.length,
    );
    expect(fixture.move).not.toHaveBeenCalled();
    fixture.input.dispose();
  },
);

it('ignores another pointer capture loss and does not cancel twice on a normal release', () => {
  const fixture = setup(true);
  dispatch(fixture.canvas, 'pointerdown', fixture.pointer());
  dispatch(fixture.canvas, 'lostpointercapture', { pointerId: 2 });
  vi.advanceTimersByTime(150);
  expect(fixture.voxel).toHaveBeenCalledWith('dig_start', { x: 4, y: 3 });
  dispatch(fixture.canvas, 'pointerup', fixture.pointer());
  dispatch(fixture.canvas, 'lostpointercapture', { pointerId: 1 });
  expect(fixture.voxel.mock.calls.filter(([action]) => action === 'dig_cancel')).toHaveLength(1);
  fixture.input.dispose();
});

it('drops a keyup from the old world before any RAF has processed the snapshot', () => {
  const fixture = setup();
  dispatch(fixture.keyboard, 'keydown', { code: 'KeyW' });
  fixture.move.mockClear();
  fixture.reset();
  dispatch(fixture.keyboard, 'keyup', { code: 'KeyW' });
  expect(fixture.move).not.toHaveBeenCalled();
  fixture.input.dispose();
});

it('stops held keys when focus changes before keyup rather than driving the remaining key', () => {
  const fixture = setup();
  dispatch(fixture.keyboard, 'keydown', { code: 'KeyW' });
  dispatch(fixture.keyboard, 'keydown', { code: 'KeyD' });
  fixture.move.mockClear();
  fixture.type();
  dispatch(fixture.keyboard, 'keyup', { code: 'KeyD' });
  expect(fixture.move.mock.calls).toEqual([[{ x: 3, y: 3 }]]);
  dispatch(fixture.keyboard, 'keyup', { code: 'KeyW' });
  expect(fixture.move).toHaveBeenCalledTimes(1);
  fixture.input.dispose();
});

it.each([
  'cancel',
  'blur',
  'pointercancel',
  'pointerleave',
  'pointermove',
  'lostpointercapture',
  'pointerup',
  'keydown',
])('clears old digging locally on %s before RAF without an intent in the new world', (event) => {
  const fixture = setup(true);
  dispatch(fixture.canvas, 'pointerdown', fixture.pointer());
  vi.advanceTimersByTime(150);
  fixture.voxel.mockClear();
  fixture.move.mockClear();
  fixture.reset();
  if (event === 'cancel') fixture.input.cancel();
  else if (event === 'blur') dispatch(fixture.keyboard, event);
  else if (event === 'keydown') dispatch(fixture.keyboard, event, { code: 'KeyW' });
  else dispatch(fixture.canvas, event, fixture.pointer(0, 200, 120));
  expect(fixture.voxel).not.toHaveBeenCalled();
  expect(fixture.move).not.toHaveBeenCalled();
  fixture.input.dispose();
});

it('does not drag a move into a new world before the next RAF', () => {
  const fixture = setup();
  dispatch(fixture.canvas, 'pointerdown', fixture.pointer());
  vi.advanceTimersByTime(101);
  fixture.move.mockClear();
  fixture.reset();
  fixture.ground({ x: 4, y: 2 });
  dispatch(fixture.canvas, 'pointermove', fixture.pointer(0, 200));
  expect(fixture.move).not.toHaveBeenCalled();
  fixture.input.dispose();
});

it('cancels a dig after focus changes before a pointermove without starting movement', () => {
  const fixture = setup(true);
  dispatch(fixture.canvas, 'pointerdown', fixture.pointer());
  vi.advanceTimersByTime(150);
  fixture.voxel.mockClear();
  fixture.type();
  dispatch(fixture.canvas, 'pointermove', fixture.pointer(0, 200));
  expect(fixture.voxel.mock.calls).toEqual([['dig_cancel', { x: 4, y: 3 }]]);
  expect(fixture.move).not.toHaveBeenCalled();
  fixture.input.dispose();
});

it('releases an owned live dig on disposal', () => {
  const fixture = setup(true);
  dispatch(fixture.canvas, 'pointerdown', fixture.pointer());
  vi.advanceTimersByTime(150);
  fixture.voxel.mockClear();
  fixture.input.dispose();
  expect(fixture.voxel.mock.calls).toEqual([['dig_cancel', { x: 4, y: 3 }]]);
});

it('disposes an old-world dig locally without cancelling the new world', () => {
  const fixture = setup(true);
  dispatch(fixture.canvas, 'pointerdown', fixture.pointer());
  vi.advanceTimersByTime(150);
  fixture.voxel.mockClear();
  fixture.reset();
  fixture.input.dispose();
  expect(fixture.voxel).not.toHaveBeenCalled();
});

it.each([
  [0, ['KeyW'], { x: 0, y: -1 }],
  [90, ['KeyW'], { x: -1, y: 0 }],
  [180, ['KeyW'], { x: 0, y: 1 }],
  [0, ['KeyW', 'KeyD'], { x: 1, y: -1 }],
] as const)('converts movement at yaw %i', (yaw, keys, expected) => {
  expect(movementDirection(new Set(keys), yaw)).toEqual(expected);
});
