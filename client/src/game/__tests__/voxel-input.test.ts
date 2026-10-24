import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { WorldMirror } from '../world-mirror';
import { createHeightLookup, isoProject, screenBounds } from '../render/iso';
vi.mock('phaser', () => ({ default: { Scene: class {} } }));
import { WorldScene } from '../scenes/WorldScene';

function setup() {
  const mirror = new WorldMirror();
  const collision = new Uint8Array(16).fill(1);
  collision[6] = 0;
  mirror.setMap({ w: 4, h: 4, tileset: 'grid', collision, ground: new Uint16Array(16).fill(7) });
  mirror.protagonist = 'hero';
  const heights = new Array<number>(16).fill(1);
  heights[6] = 3;
  const scene = new WorldScene(mirror, 'iso'),
    emit = vi.fn();
  Object.assign(scene, {
    game: { events: { emit } },
    heightAt: createHeightLookup({ w: 4, h: 4, h_values: heights }),
    goalMarker: null,
  });
  const input = scene as unknown as {
    handlePointerDown(p: unknown): void;
    handlePointerUp(p: unknown): void;
    cancelVoxelInput(): void;
  };
  const pointer = (x: number, y: number, height: number, button = 0) => {
    const point = isoProject(x, y, height, screenBounds(4, 4));
    return { worldX: point.sx, worldY: point.sy, button, id: 1 };
  };
  return { scene, input, emit, pointer };
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it('keeps a short left press as the existing move_request', () => {
  const { input, emit, pointer } = setup();
  const p = pointer(0, 3, 0);
  input.handlePointerDown(p);
  vi.advanceTimersByTime(100);
  input.handlePointerUp(p);
  expect(emit).toHaveBeenCalledTimes(1);
  expect(emit).toHaveBeenLastCalledWith('client:move_request', { x: 0, y: 3 });
});

it('starts dig only after 150ms on the visible blocked cell and cancels on release', () => {
  const { input, emit, pointer } = setup();
  const p = pointer(2, 1, 3);
  input.handlePointerDown(p);
  vi.advanceTimersByTime(149);
  expect(emit).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);
  expect(emit).toHaveBeenLastCalledWith('client:voxel_request', {
    action: 'dig_start',
    x: 2,
    y: 1,
  });
  input.handlePointerUp(p);
  expect(emit).toHaveBeenLastCalledWith('client:voxel_request', {
    action: 'dig_cancel',
    x: 2,
    y: 1,
  });
  expect(emit.mock.calls.some((call) => call[0] === 'client:move_request')).toBe(false);
});

it('maps right click to a visible walkable placement cell without movement', () => {
  const { input, emit, pointer } = setup();
  input.handlePointerDown(pointer(0, 3, 1, 2));
  expect(emit).toHaveBeenLastCalledWith('client:voxel_request', { action: 'place', x: 0, y: 3 });
});

it('does not dig walkable ground or turn a long hold into movement', () => {
  const { input, emit, pointer } = setup();
  const p = pointer(0, 3, 1);
  input.handlePointerDown(p);
  vi.advanceTimersByTime(200);
  input.handlePointerUp(p);
  expect(emit).not.toHaveBeenCalled();
});

it('clears a pending hold when the pointer leaves before the threshold', () => {
  const { input, emit, pointer } = setup();
  input.handlePointerDown(pointer(2, 1, 3));
  input.cancelVoxelInput();
  vi.advanceTimersByTime(200);
  expect(emit).not.toHaveBeenCalled();
});
