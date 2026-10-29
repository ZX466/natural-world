import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { WorldMirror } from '../world-mirror';
import { useUiStore } from '../../store/uiStore';
vi.mock('phaser', () => ({ default: { Scene: class {} } }));
import { WorldScene } from '../scenes/WorldScene';

function setup() {
  const mirror = new WorldMirror();
  mirror.setMap({ w: 16, h: 16, tileset: 'grid', collision: new Uint8Array(256).fill(1) });
  mirror.protagonist = 'hero';
  const hero = { rtoken: 'hero', x: 4, y: 4, facing: 's', sprite: 'protagonist', anim: 'idle' };
  mirror.actors.set('hero', hero);
  const marker = {
    setVisible: vi.fn().mockReturnThis(),
    setPosition: vi.fn().mockReturnThis(),
    setDepth: vi.fn().mockReturnThis(),
  };
  const accepted = { value: true };
  const emit = vi.fn((_name: string, _target: unknown, result?: (value: boolean) => void) => {
    result?.(accepted.value);
    return true;
  });
  const scene = new WorldScene(mirror, 'flat');
  Object.assign(scene, { game: { events: { emit } }, goalMarker: marker });
  const input = scene as unknown as {
    handleMovementKeyDown(event: unknown): void;
    handleMovementKeyUp(event: unknown): void;
    syncMovementInput(): void;
    cancelMovement(): void;
    handlePointerDown(pointer: unknown): void;
    handlePointerMove(pointer: unknown): void;
    handlePointerUp(pointer: unknown): void;
  };
  const key = (code: string) => ({ code, key: code, preventDefault: vi.fn() });
  const pointer = (x: number, y: number) => ({
    worldX: x * 16 + 8,
    worldY: y * 16 + 8,
    button: 0,
    id: 1,
  });
  return { mirror, hero, marker, emit, input, key, pointer, accepted };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(1000);
  vi.stubGlobal('document', { activeElement: null });
  useUiStore.setState({ voxelError: null, wsStatus: 'open' });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('starts toward an adjacent tile, repeats after progress, and cancels on key release', () => {
  const { input, key, hero, emit, marker } = setup();
  const event = key('ArrowRight');
  input.handleMovementKeyDown(event);
  expect(emit).toHaveBeenLastCalledWith(
    'client:move_request',
    { x: 5, y: 4 },
    expect.any(Function),
  );
  expect(event.preventDefault).toHaveBeenCalled();
  input.handleMovementKeyDown(event); // OS auto-repeat must not resend the route.
  for (let i = 0; i < 60; i++) input.syncMovementInput();
  expect(emit).toHaveBeenCalledTimes(1);
  hero.x = 5;
  input.syncMovementInput();
  expect(emit).toHaveBeenLastCalledWith(
    'client:move_request',
    { x: 6, y: 4 },
    expect.any(Function),
  );
  input.handleMovementKeyUp(event);
  expect(emit).toHaveBeenLastCalledWith(
    'client:move_request',
    { x: 5, y: 4 },
    expect.any(Function),
  );
  expect(marker.setVisible).toHaveBeenLastCalledWith(false);
  const count = emit.mock.calls.length;
  input.syncMovementInput();
  expect(emit).toHaveBeenCalledTimes(count);
});

it.each(['INPUT', 'TEXTAREA', 'SELECT'])(
  'does not capture keys while a %s is focused',
  (tagName) => {
    const { input, key, emit } = setup();
    vi.stubGlobal('document', { activeElement: { tagName } });
    const event = key('KeyW');
    input.handleMovementKeyDown(event);
    input.syncMovementInput();
    expect(emit).not.toHaveBeenCalled();
    expect(event.preventDefault).not.toHaveBeenCalled();
  },
);

it('stops held movement when focus enters an editable element', () => {
  const { input, key, emit, hero } = setup();
  input.handleMovementKeyDown(key('KeyW'));
  vi.stubGlobal('document', { activeElement: { tagName: 'DIV', isContentEditable: true } });
  input.syncMovementInput();
  expect(emit).toHaveBeenLastCalledWith(
    'client:move_request',
    { x: hero.x, y: hero.y },
    expect.any(Function),
  );
  const count = emit.mock.calls.length;
  vi.stubGlobal('document', { activeElement: null });
  input.syncMovementInput();
  expect(emit).toHaveBeenCalledTimes(count);
});

it('checks both orthogonal cells before diagonal movement instead of allowing a detour', () => {
  const { input, key, mirror, emit } = setup();
  mirror.map!.collision[3 * 16 + 4] = 0;
  input.handleMovementKeyDown(key('KeyW')); // north wall
  input.handleMovementKeyDown(key('KeyD')); // northeast must not cut its corner
  expect(emit).not.toHaveBeenCalled();
  expect(useUiStore.getState().voxelError).toBe('那处挡着路。');
});

it('clears a goal on arrival, replacement, escape and world reset', () => {
  const { input, pointer, hero, marker, key, emit, mirror } = setup();
  input.handlePointerDown(pointer(6, 4));
  input.handlePointerUp(pointer(6, 4));
  expect(marker.setVisible).toHaveBeenLastCalledWith(true);
  hero.x = 6;
  input.syncMovementInput();
  expect(marker.setVisible).toHaveBeenLastCalledWith(false);
  marker.setVisible.mockClear();
  input.handlePointerDown(pointer(7, 4));
  input.handlePointerUp(pointer(7, 4));
  expect(marker.setVisible.mock.calls.map(([value]) => value)).toEqual([false, true]);
  input.handleMovementKeyDown(key('Escape'));
  expect(marker.setVisible).toHaveBeenLastCalledWith(false);
  input.handleMovementKeyDown(key('KeyD'));
  mirror.reset();
  const count = emit.mock.calls.length;
  input.syncMovementInput();
  expect(marker.setVisible).toHaveBeenLastCalledWith(false);
  expect(emit).toHaveBeenCalledTimes(count); // reset must not issue a command into the new branch
});

it('keeps rejected goals hidden', () => {
  const { input, pointer, accepted, marker } = setup();
  accepted.value = false;
  input.handlePointerDown(pointer(7, 4));
  input.handlePointerUp(pointer(7, 4));
  expect(marker.setVisible).not.toHaveBeenCalledWith(true);
});

it('coalesces a fast drag and does not replace an active path before the actor progresses', () => {
  const { input, pointer, emit, hero } = setup();
  input.handlePointerDown(pointer(6, 4));
  for (let i = 0; i < 60; i++) {
    vi.advanceTimersByTime(16);
    input.handlePointerMove(pointer(7 + (i % 8), 4));
    input.syncMovementInput();
  }
  expect(emit).toHaveBeenCalledTimes(1);
  hero.x = 5;
  input.syncMovementInput();
  expect(emit.mock.calls.length).toBe(2);
  input.handlePointerUp(pointer(14, 4));
  expect(emit.mock.calls.length).toBeLessThanOrEqual(3);
});
