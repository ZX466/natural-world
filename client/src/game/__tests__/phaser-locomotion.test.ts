import { EventEmitter } from 'node:events';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useUiStore } from '../../store/uiStore';
import type { JumpVisual } from '../../net/protocol';
import { WorldMirror, type MirrorActor } from '../world-mirror';
import type { ActorMotion } from '../render/actor-motion';
import { isoProject, screenBounds } from '../render/iso';

vi.mock('phaser', () => ({ default: { Scene: class {} } }));
vi.mock('../render/fauna', () => ({ createFaunaTextures: vi.fn() }));
vi.mock('../render/iso-terrain', () => ({
  IsoTerrain: class {
    redraw() {}
    sync() {}
    advance() {}
    destroy() {}
  },
}));
import { WorldScene } from '../scenes/WorldScene';

class View {
  texture = { key: 'protagonist' };
  displayHeight = 32;
  setOrigin = vi.fn(() => this);
  setDepth = vi.fn(() => this);
  setFrame = vi.fn(() => this);
  setAlpha = vi.fn(() => this);
  setScale = vi.fn(() => this);
  setVisible = vi.fn(() => this);
  setScrollFactor = vi.fn(() => this);
  setPosition = vi.fn((x: number, y: number) => {
    this.x = x;
    this.y = y;
    return this;
  });
  clear = vi.fn(() => this);
  fillStyle = vi.fn(() => this);
  fillRect = vi.fn(() => this);
  destroy = vi.fn();
  constructor(
    public x = 0,
    public y = 0,
  ) {}
}

type SceneInput = {
  views: Map<string, { sprite: View; shadow: View; motion: ActorMotion }>;
  handleMovementKeyDown(event: KeyboardEvent): void;
  handleMovementKeyUp(event: KeyboardEvent): void;
  handlePointerDown(pointer: unknown): void;
  handlePointerUp(pointer: unknown): void;
  handlePointerMove(pointer: unknown): void;
  syncMovementInput(): void;
  syncActorViews(delta: number, time: number): void;
};

function setup(mode: 'flat' | 'iso' = 'flat') {
  const mirror = new WorldMirror();
  mirror.setMap({ w: 32, h: 32, tileset: 'grid', collision: new Uint8Array(1024).fill(1) });
  mirror.protagonist = 'hero';
  const hero: MirrorActor = {
    rtoken: 'hero',
    x: 4,
    y: 4,
    facing: 's',
    sprite: 'protagonist',
    anim: 'idle',
  };
  mirror.actors.set('hero', hero);
  const emit = vi.fn((_name: string, _target: unknown, result?: (accepted: boolean) => void) => {
    result?.(true);
    return true;
  });
  const events = new EventEmitter();
  const heights = new Array<number>(1024).fill(1);
  const scene = new WorldScene(mirror, mode);
  Object.assign(scene, {
    textures: { exists: () => true },
    cache: {
      json: {
        get: (key: string) => (key === 'linhe-height' ? { w: 32, h: 32, h_values: heights } : null),
      },
    },
    cameras: { main: { startFollow: vi.fn() } },
    game: { events: { emit, on: vi.fn(), off: vi.fn() } },
    input: { on: vi.fn() },
    events,
    scale: { width: 800, height: 600, on: vi.fn() },
    goalMarker: new View(),
    add: {
      sprite: (x: number, y: number) => new View(x, y),
      ellipse: (x: number, y: number) => new View(x, y),
      text: (x: number, y: number) => new View(x, y),
      graphics: () => new View(),
      rectangle: (x: number, y: number) => new View(x, y),
      circle: (x: number, y: number) => new View(x, y),
    },
  });
  const input = scene as unknown as SceneInput;
  const key = (code: string, options: Partial<KeyboardEvent> = {}) =>
    ({
      code,
      key: code === 'Space' ? ' ' : code,
      preventDefault: vi.fn(),
      ...options,
    }) as unknown as KeyboardEvent;
  const pointer = (x: number, y: number, button = 0) => ({
    worldX: x * 16 + 8,
    worldY: y * 16 + 8,
    id: 1,
    button,
  });
  return { scene, input, mirror, hero, emit, key, pointer, heights, events };
}

function jump(overrides: Partial<JumpVisual> = {}): JumpVisual {
  return {
    rtoken: 'flight',
    start_x: 4,
    start_y: 4,
    goal_x: 4,
    goal_y: 4,
    start_height: 1,
    target_height: 1,
    progress: 0.5,
    active: true,
    duration: 0.6,
    arc_height: 0.8,
    ...overrides,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('document', { activeElement: null });
  useUiStore.setState({ speed: 1, wsStatus: 'open', voxelError: null });
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('changes an active keyboard route to run and back to walk when Shift changes', () => {
  const { input, key, emit } = setup();
  input.handleMovementKeyDown(key('KeyD'));
  input.handleMovementKeyDown(key('ShiftLeft'));
  expect(emit).toHaveBeenLastCalledWith(
    'client:move_request',
    { x: 5, y: 4, gait: 'run' },
    expect.any(Function),
  );
  input.syncMovementInput();
  expect(emit).toHaveBeenCalledTimes(2);
  input.handleMovementKeyUp(key('ShiftLeft'));
  expect(emit).toHaveBeenLastCalledWith(
    'client:move_request',
    { x: 5, y: 4 },
    expect.any(Function),
  );
  expect(emit).toHaveBeenCalledTimes(3);
});

it('changes a pointer route gait without replacing its destination', () => {
  const { input, key, pointer, emit } = setup();
  input.handlePointerDown(pointer(10, 4));
  input.handlePointerUp(pointer(10, 4));
  input.handleMovementKeyDown(key('ShiftRight'));
  expect(emit).toHaveBeenLastCalledWith(
    'client:move_request',
    { x: 10, y: 4, gait: 'run' },
    expect.any(Function),
  );
  input.handleMovementKeyUp(key('ShiftRight'));
  expect(emit).toHaveBeenLastCalledWith(
    'client:move_request',
    { x: 10, y: 4 },
    expect.any(Function),
  );
});

it.each([
  { direction: false, running: false, x: 4, gait: 'walk' },
  { direction: true, running: false, x: 5, gait: 'walk' },
  { direction: true, running: true, x: 6, gait: 'run' },
  { direction: false, running: true, x: 4, gait: 'run' },
])(
  'requests one authoritative $gait jump to $x,4 per Space press',
  ({ direction, running, x, gait }) => {
    const { input, key, emit } = setup();
    if (running) input.handleMovementKeyDown(key('ShiftLeft'));
    if (direction) input.handleMovementKeyDown(key('KeyD'));
    emit.mockClear();
    const space = key('Space');
    input.handleMovementKeyDown(space);
    input.handleMovementKeyDown(key('Space', { repeat: true }));
    input.handleMovementKeyDown(space);
    expect(emit).toHaveBeenCalledTimes(1);
    expect(emit).toHaveBeenCalledWith(
      'client:jump_request',
      { x, y: 4, gait },
      expect.any(Function),
    );
    expect(space.preventDefault).toHaveBeenCalled();
    input.handleMovementKeyUp(space);
    input.handleMovementKeyDown(space);
    expect(emit).toHaveBeenCalledTimes(2);
  },
);

it('leaves Space and Shift available to a focused text control', () => {
  const { input, key, emit } = setup();
  vi.stubGlobal('document', { activeElement: { tagName: 'TEXTAREA' } });
  const space = key('Space');
  const shift = key('ShiftLeft');
  input.handleMovementKeyDown(space);
  input.handleMovementKeyDown(shift);
  expect(emit).not.toHaveBeenCalled();
  expect(space.preventDefault).not.toHaveBeenCalled();
  expect(shift.preventDefault).not.toHaveBeenCalled();
});

it('steps across the current high surface while keeping an adjacent h1 bank blocked', () => {
  const raised = setup();
  raised.hero.elevation = 2;
  raised.mirror.map!.collision.fill(0);
  raised.mirror.setHeightLookup(() => 2);
  raised.input.handleMovementKeyDown(raised.key('KeyD'));
  expect(raised.emit).toHaveBeenCalledWith(
    'client:move_request',
    { x: 5, y: 4 },
    expect.any(Function),
  );
  const bank = setup();
  bank.mirror.map!.collision[4 * 32 + 5] = 0;
  bank.mirror.setHeightLookup(() => 1);
  bank.input.handleMovementKeyDown(bank.key('KeyD'));
  expect(bank.emit).not.toHaveBeenCalled();
});

it.each(['flat', 'iso'] as const)('picks a same-height h2 walking target in %s mode', (mode) => {
  const { input, mirror, hero, scene, emit } = setup(mode);
  hero.elevation = 2;
  mirror.map!.collision.fill(0);
  mirror.setHeightLookup(() => 2);
  Object.assign(scene, { heightAt: () => 2 });
  const top = mode === 'iso' ? isoProject(5, 4, 2, screenBounds(32, 32)) : { sx: 88, sy: 72 };
  const pointer = { worldX: top.sx, worldY: top.sy, id: 1, button: 0 };
  input.handlePointerDown(pointer);
  input.handlePointerUp(pointer);
  expect(emit).toHaveBeenCalledWith('client:move_request', { x: 5, y: 4 }, expect.any(Function));
});

it('suppresses ground movement, repeat jumps and voxel input in flight, then resumes held direction after landing', () => {
  const { input, mirror, hero, emit, key, pointer } = setup();
  hero.jump = jump();
  input.handleMovementKeyDown(key('KeyD'));
  input.handleMovementKeyDown(key('Space'));
  input.handlePointerDown(pointer(7, 4, 2));
  mirror.map!.collision[4 * 32 + 7] = 0;
  input.handlePointerDown(pointer(7, 4));
  vi.advanceTimersByTime(200);
  input.handlePointerMove(pointer(8, 4));
  input.handlePointerUp(pointer(8, 4));
  input.syncMovementInput();
  expect(emit).not.toHaveBeenCalled();
  hero.jump = null;
  input.syncMovementInput();
  expect(emit).toHaveBeenCalledWith('client:move_request', { x: 5, y: 4 }, expect.any(Function));
});

describe.each(['flat', 'iso'] as const)('%s locomotion presentation', (mode) => {
  it('draws an authoritative in-place flight above a stationary support shadow', () => {
    const { input, hero } = setup(mode);
    hero.elevation = 1;
    hero.jump = jump();
    input.syncActorViews(0, 0);
    const { sprite, shadow, motion } = input.views.get('hero')!;
    const base = mode === 'iso' ? isoProject(4, 4, 1, screenBounds(32, 32)) : { sx: 72, sy: 72 };
    expect(sprite.x).toBeCloseTo(base.sx);
    expect(sprite.y).toBeCloseTo(base.sy - 12.8);
    expect(shadow.x).toBeCloseTo(base.sx);
    expect(shadow.y).toBeCloseTo(base.sy - (mode === 'flat' ? 1 : 0));
    expect(motion.airborne).toBe(true);
    expect(motion.animClock).toBe(-1);
  });

  it.each([1, 4, 16] as const)(
    'finishes a buffered jump on the server h2 surface at %sx',
    (speed) => {
      const { input, mirror, hero, scene } = setup(mode);
      useUiStore.setState({ speed });
      const base = (x: number, y: number) => (x === 5 && y === 4 ? 2 : 1);
      Object.assign(scene, { heightAt: base });
      mirror.setHeightLookup(base);
      hero.elevation = 1;
      hero.jump = jump({ goal_x: 5, target_height: 2 });
      input.syncActorViews(0, 0);
      hero.x = 5;
      hero.elevation = 2;
      hero.jump = jump({ goal_x: 5, target_height: 2, progress: 1, active: false });
      for (let frame = 1; frame <= 90; frame++)
        input.syncActorViews(1000 / 60, (frame * 1000) / 60);
      const { sprite, shadow, motion } = input.views.get('hero')!;
      const top = mode === 'iso' ? isoProject(5, 4, 2, screenBounds(32, 32)) : { sx: 88, sy: 72 };
      expect(sprite.x).toBeCloseTo(top.sx);
      expect(sprite.y).toBeCloseTo(top.sy);
      expect(shadow.y).toBeCloseTo(top.sy - (mode === 'flat' ? 1 : 0));
      expect(motion.airborne).not.toBe(true);
      expect(motion.animClock).toBe(-1);
    },
  );

  it('keeps a walk sample in replay for the 500ms walk cadence', () => {
    const { input, hero } = setup(mode);
    hero.gait = 'walk';
    input.syncActorViews(0, 0);
    for (let frame = 1; frame <= 45; frame++) {
      if (frame === 30) hero.x = 5;
      input.syncActorViews(1000 / 60, (frame * 1000) / 60);
    }
    const { sprite } = input.views.get('hero')!;
    const start = mode === 'iso' ? isoProject(4, 4, 1, screenBounds(32, 32)).sx : 72;
    expect(sprite.x).toBeGreaterThan(start);
    expect(sprite.x).toBeLessThan(start + 8);
  });
});

it('uses authoritative elevation when the observable terrain top differs', () => {
  const { input, hero, scene } = setup('iso');
  Object.assign(scene, { heightAt: () => 3 });
  hero.elevation = 2;
  input.syncActorViews(0, 0);
  const top = isoProject(4, 4, 2, screenBounds(32, 32));
  expect(input.views.get('hero')!.sprite.y).toBe(top.sy);
});

it('advances the same walk phase for equal logical distances along both iso diagonals', () => {
  const phases = [1, -1].map((dy) => {
    const { input, hero } = setup('iso');
    input.syncActorViews(0, 0);
    for (let frame = 1; frame <= 30; frame++) {
      if (frame === 15) {
        hero.x++;
        hero.y += dy;
      }
      input.syncActorViews(1000 / 60, (frame * 1000) / 60);
    }
    return input.views.get('hero')!.motion.animClock;
  });
  expect(phases[0]).toBeGreaterThan(0);
  expect(phases[0]).toBeCloseTo(phases[1]!, 6);
});

it('installs a terrain lookup that survives Scene disposal and follows current mirror edits', () => {
  const { scene, mirror, heights, events } = setup();
  heights[4 * 32 + 4] = 3;
  scene.create();
  expect(mirror.heightAt(4, 4)).toBe(3);
  events.emit('shutdown');
  Object.assign(scene, {
    heightAt: () => {
      throw new Error('disposed Scene');
    },
  });
  mirror.applyVoxelEdits([{ x: 4, y: 4, gid: 0, action: 'place', height: 2, material: 'stone' }]);
  expect(mirror.heightAt(4, 4)).toBe(2);
  mirror.applyVoxelEdits([{ x: 4, y: 4, gid: 1, action: 'dig', height: 1, material: 'stone' }]);
  expect(mirror.heightAt(4, 4)).toBe(1);
});
