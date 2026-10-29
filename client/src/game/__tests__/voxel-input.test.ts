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
    syncMovementInput(): void;
  };
  const pointer = (x: number, y: number, height: number, button = 0) => {
    const point = isoProject(x, y, height, screenBounds(4, 4));
    return { worldX: point.sx, worldY: point.sy, button, id: 1 };
  };
  return { scene, input, emit, pointer, mirror };
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it('keeps a short left press as the existing move_request', () => {
  const { input, emit, pointer } = setup();
  const p = pointer(0, 3, 1); // Click the intended visible surface, as for editing.
  input.handlePointerDown(p);
  vi.advanceTimersByTime(100);
  input.handlePointerUp(p);
  expect(emit).toHaveBeenCalledTimes(1);
  expect(emit).toHaveBeenLastCalledWith(
    'client:move_request',
    { x: 0, y: 3 },
    expect.any(Function),
  );
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

it('moves on a walkable press immediately even when held longer than 150ms', () => {
  const { input, emit, pointer } = setup();
  const p = pointer(0, 3, 1);
  input.handlePointerDown(p);
  expect(emit).toHaveBeenCalledWith('client:move_request', { x: 0, y: 3 }, expect.any(Function));
  vi.advanceTimersByTime(200);
  input.handlePointerUp(p);
  expect(emit.mock.calls.filter((call) => call[0] === 'client:move_request')).toHaveLength(1);
  expect(emit.mock.calls.some((call) => call[0] === 'client:voxel_request')).toBe(false);
});

it('clears a pending hold when the pointer leaves before the threshold', () => {
  const { input, emit, pointer } = setup();
  input.handlePointerDown(pointer(2, 1, 3));
  input.cancelVoxelInput();
  vi.advanceTimersByTime(200);
  expect(emit).not.toHaveBeenCalled();
});

it('drops an old dig gesture on snapshot replacement without sending into the new world', () => {
  const { input, emit, pointer, mirror } = setup();
  input.handlePointerDown(pointer(2, 1, 3));
  vi.advanceTimersByTime(150);
  expect(emit).toHaveBeenCalledTimes(1);
  mirror.applyVoxelEdits([], true);
  input.syncMovementInput();
  expect(emit).toHaveBeenCalledTimes(1);
});

it('moves when the clicked ground is overlapped on screen by a tall block', () => {
  // 2026-10-29「人物无法移动」回归钉。等距画面里 h=3 方块与**斜后方 2 格**的 h=1
  // 地面顶面菱形完全重合（x−y 相同、x+y 差 4、高度差 2 ⇒ 屏幕位置相同）。旧实现
  // 用编辑拾取器（高方块优先），把「点空地」判成「点房子」→ 本地可达性预检全拒
  // → 一个移动帧都发不出去。真实地图实测 19.3% 的可走格如此。
  const w = 5,
    h = 5;
  const collision = new Uint8Array(w * h).fill(1);
  collision[3 * w + 3] = 0; // (3,3) 阻挡 → 高方块
  const mirror = new WorldMirror();
  mirror.setMap({ w, h, tileset: 'grid', collision, ground: new Uint16Array(w * h).fill(7) });
  mirror.protagonist = 'hero';
  const heights = new Array<number>(w * h).fill(1);
  heights[3 * w + 3] = 3;
  const scene = new WorldScene(mirror, 'iso'),
    emit = vi.fn();
  Object.assign(scene, {
    game: { events: { emit } },
    heightAt: createHeightLookup({ w, h, h_values: heights }),
    goalMarker: null,
  });
  const input = scene as unknown as {
    handlePointerDown(p: unknown): void;
    handlePointerUp(p: unknown): void;
  };

  // (1,1) h=1 与 (3,3) h=3 在屏幕上重合：同一个像素点。
  const ground = isoProject(1, 1, 1, screenBounds(w, h));
  const block = isoProject(3, 3, 3, screenBounds(w, h));
  expect(block).toEqual(ground); // 前提钉：两格确实重合

  // 按下：两个拾取器给出不同格——编辑看到 (3,3)，移动看到 (1,1)。
  // 抬手早于 150ms 挖掘阈值 → 落回移动，且必须落在 (1,1) 而非 (3,3)。
  const p = { worldX: ground.sx, worldY: ground.sy, button: 0, id: 1 };
  input.handlePointerDown(p);
  vi.advanceTimersByTime(50);
  input.handlePointerUp(p);
  expect(emit).toHaveBeenCalledWith('client:move_request', { x: 1, y: 1 }, expect.any(Function));
  expect(emit.mock.calls.some((call) => call[0] === 'client:voxel_request')).toBe(false);
});
