import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { WorldMirror } from '../world-mirror';
import { EventEmitter } from 'node:events';
import { useUiStore } from '../../store/uiStore';
vi.mock('phaser', () => ({ default: { Scene: class {} } }));
vi.mock('../render/fauna', () => ({ createFaunaTextures: vi.fn() }));
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
    syncVoxelPresentation(): void;
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

it('does not replace an unchanged keyboard goal after an unrelated terrain update', () => {
  const { input, key, mirror, emit } = setup();
  input.handleMovementKeyDown(key('KeyD'));
  mirror.applyStructures([{ rtoken: 'distant-house', x: 0, y: 0, phase: 'built' }]);
  input.syncMovementInput();
  expect(emit).toHaveBeenCalledTimes(1);
});

it.each(['pointer', 'keyboard'])(
  'gives local feedback for %s input before the world is ready',
  (kind) => {
    const { input, key, pointer, mirror, emit } = setup();
    mirror.map = null;
    if (kind === 'pointer') input.handlePointerDown(pointer(7, 4));
    else input.handleMovementKeyDown(key('KeyD'));
    expect(emit).not.toHaveBeenCalled();
    expect(useUiStore.getState().voxelError).toBe('这会儿走不了。');
  },
);

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

it('drops a rejected offline drag instead of resuming it after reconnect', () => {
  const { input, pointer, emit, accepted } = setup();
  accepted.value = false;
  useUiStore.setState({ wsStatus: 'closed' });
  input.handlePointerDown(pointer(7, 4));
  expect(emit).toHaveBeenCalledTimes(1);
  input.syncMovementInput();
  useUiStore.setState({ wsStatus: 'open' });
  accepted.value = true;
  vi.advanceTimersByTime(200);
  input.handlePointerMove(pointer(8, 4));
  input.syncMovementInput();
  expect(emit).toHaveBeenCalledTimes(1);
});

it('cancels an old walking goal before a right-click placement', () => {
  const { input, pointer, emit, marker } = setup();
  input.handlePointerDown(pointer(7, 4));
  input.handlePointerUp(pointer(7, 4));
  emit.mockClear();
  input.handlePointerDown({ ...pointer(5, 4), button: 2 });
  expect(emit.mock.calls[0]).toEqual(['client:move_request', { x: 4, y: 4 }, expect.any(Function)]);
  expect(emit).toHaveBeenLastCalledWith('client:voxel_request', { action: 'place', x: 5, y: 4 });
  expect(marker.setVisible).toHaveBeenLastCalledWith(false);
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

it('retains a valid drag through the first presentation update without a new snapshot', () => {
  const { input, pointer, hero, emit } = setup();
  input.handlePointerDown(pointer(7, 4));
  input.syncMovementInput();
  input.syncVoxelPresentation();
  vi.advanceTimersByTime(200);
  hero.x = 5;
  input.handlePointerMove(pointer(8, 4));
  expect(emit).toHaveBeenLastCalledWith(
    'client:move_request',
    { x: 8, y: 4 },
    expect.any(Function),
  );
});

it.each([
  { keys: ['ArrowUp'], x: 4, y: 3 },
  { keys: ['ArrowUp', 'ArrowRight'], x: 5, y: 3 },
  { keys: ['ArrowRight'], x: 5, y: 4 },
  { keys: ['ArrowDown', 'ArrowRight'], x: 5, y: 5 },
  { keys: ['ArrowDown'], x: 4, y: 5 },
  { keys: ['ArrowDown', 'ArrowLeft'], x: 3, y: 5 },
  { keys: ['ArrowLeft'], x: 3, y: 4 },
  { keys: ['ArrowUp', 'ArrowLeft'], x: 3, y: 3 },
])('supports grid direction $keys', ({ keys, x, y }) => {
  const { input, key, emit } = setup();
  for (const code of keys) input.handleMovementKeyDown(key(code));
  expect(emit).toHaveBeenLastCalledWith('client:move_request', { x, y }, expect.any(Function));
});

it('does not issue a new direction on keyup after focus enters a text box', () => {
  const { input, key, emit } = setup();
  input.handleMovementKeyDown(key('KeyW'));
  input.handleMovementKeyDown(key('KeyD'));
  vi.stubGlobal('document', { activeElement: { tagName: 'INPUT' } });
  input.handleMovementKeyUp(key('KeyD'));
  expect(emit).toHaveBeenLastCalledWith(
    'client:move_request',
    { x: 4, y: 4 },
    expect.any(Function),
  );
});

it('wires real input events, cancels on blur, and detaches keyboard listeners on shutdown', () => {
  const { mirror, key } = setup();
  const scene = new WorldScene(mirror, 'flat');
  const keyboard = new EventEmitter();
  const input = Object.assign(new EventEmitter(), {
    keyboard,
    mouse: { disableContextMenu: vi.fn() },
  });
  const events = new EventEmitter();
  const gameEvents = new EventEmitter();
  const moves: { x: number; y: number }[] = [];
  gameEvents.on('client:move_request', (target, result) => {
    moves.push(target);
    result(true);
  });
  const object = {
    setDepth: vi.fn().mockReturnThis(),
    setOrigin: vi.fn().mockReturnThis(),
    setScrollFactor: vi.fn().mockReturnThis(),
    setVisible: vi.fn().mockReturnThis(),
    setPosition: vi.fn().mockReturnThis(),
    clear: vi.fn(),
    fillStyle: vi.fn(),
    fillRect: vi.fn(),
  };
  Object.assign(scene, {
    input,
    events,
    game: { events: gameEvents },
    scale: Object.assign(new EventEmitter(), { width: 800, height: 600 }),
    add: { graphics: () => object, rectangle: () => object, circle: () => object },
  });
  scene.create();
  keyboard.emit('keydown', key('KeyD'));
  expect(moves.at(-1)).toEqual({ x: 5, y: 4 });
  gameEvents.emit('blur');
  expect(moves.at(-1)).toEqual({ x: 4, y: 4 });
  keyboard.emit('keydown', key('KeyW'));
  events.emit('shutdown');
  const count = moves.length;
  keyboard.emit('keydown', key('KeyD'));
  expect(moves).toHaveLength(count);
  expect(keyboard.listenerCount('keydown')).toBe(0);
  expect(keyboard.listenerCount('keyup')).toBe(0);
  expect(vi.getTimerCount()).toBe(0);
});

it('measures immediate client dispatch and the admitted drag rate with a 4Hz position feed', () => {
  const stamp = () => Date.now();
  const keyboard = setup();
  const keyAt = stamp();
  keyboard.input.handleMovementKeyDown(keyboard.key('KeyD'));
  expect(keyboard.emit).toHaveBeenCalledTimes(1);
  const keyDelay = stamp() - keyAt;
  const click = setup();
  const clickAt = stamp();
  click.input.handlePointerDown(click.pointer(6, 4));
  expect(click.emit).toHaveBeenCalledTimes(1);
  const clickDelay = stamp() - clickAt;
  const drag = setup();
  const start = stamp();
  drag.input.handlePointerDown(drag.pointer(6, 4));
  for (let frame = 1; frame < 125; frame++) {
    vi.advanceTimersByTime(8);
    drag.hero.x = 4 + Math.floor((stamp() - start) / 250);
    drag.input.handlePointerMove(drag.pointer(8 + (Math.floor(frame / 20) % 7), 4));
    drag.input.syncMovementInput();
  }
  const steadyFrames = drag.emit.mock.calls.length;
  vi.advanceTimersByTime(8);
  drag.input.handlePointerUp(drag.pointer(14, 4));
  expect(keyDelay).toBe(0);
  expect(clickDelay).toBe(0);
  expect(steadyFrames).toBe(4);
  expect(drag.emit.mock.calls.length - steadyFrames).toBe(1);
  console.info(
    'movement input timing',
    JSON.stringify({
      mode: 'fake-clock client, 4Hz authoritative-position fixture',
      key_to_request_ms: keyDelay,
      pointerdown_to_request_ms: clickDelay,
      pointermove_events_in_1000_ms: 124,
      admitted_moves_in_1000_ms: steadyFrames,
      extra_release_move: drag.emit.mock.calls.length - steadyFrames,
    }),
  );
});
