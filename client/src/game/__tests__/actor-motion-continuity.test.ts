import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useUiStore } from '../../store/uiStore';
import { WorldMirror } from '../world-mirror';
import { TILE_CADENCE_MS_1X } from '../render/actor-motion';

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

const FRAME = 1000 / 60;

class Node {
  depth = 0;
  alpha = 1;
  displayWidth = 140;
  displayHeight = 32;
  setOrigin = vi.fn(() => this);
  setScrollFactor = vi.fn(() => this);
  setDepth = vi.fn((depth: number) => {
    this.depth = depth;
    return this;
  });
  setScale = vi.fn(() => this);
  setPosition = vi.fn((x: number, y: number) => {
    this.x = x;
    this.y = y;
    return this;
  });
  setAlpha = vi.fn((alpha: number) => {
    this.alpha = alpha;
    return this;
  });
  setVisible = vi.fn(() => this);
  setFrame = vi.fn(() => this);
  setText = vi.fn(() => this);
  clear = vi.fn(() => this);
  fillStyle = vi.fn(() => this);
  fillRect = vi.fn(() => this);
  setFillStyle = vi.fn(() => this);
  setSize = vi.fn(() => this);
  destroy = vi.fn();
  texture = { key: 'protagonist' };
  constructor(
    public x = 0,
    public y = 0,
    public width = 140,
    public height = 32,
  ) {}
}

beforeEach(() => {
  vi.useFakeTimers();
  useUiStore.setState({ speed: 1 });
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe.each(['flat', 'iso'] as const)('%s actor motion continuity', (mode) => {
  it('never freezes a walking actor between authoritative tiles', () => {
    const mirror = new WorldMirror();
    mirror.setMap({ w: 40, h: 40, tileset: 'grid', collision: new Uint8Array(1600).fill(1) });
    mirror.protagonist = 'hero';
    mirror.actors.set('hero', {
      rtoken: 'hero',
      x: 1,
      y: 1,
      facing: 's',
      sprite: 'protagonist',
      anim: 'idle',
      name: '陈默',
    });
    const scene = new WorldScene(mirror, mode);
    Object.assign(scene, {
      textures: { exists: () => true },
      cache: { json: { get: () => null } },
      scale: { width: 1200, height: 700, on: vi.fn() },
      input: { on: vi.fn() },
      events: { once: vi.fn() },
      game: { events: { on: vi.fn(), off: vi.fn() } },
      cameras: { main: { startFollow: vi.fn(), zoom: 1 } },
      add: {
        graphics: () => new Node(),
        rectangle: (x: number, y: number, w: number, h: number) => new Node(x, y, w, h),
        circle: (x: number, y: number) => new Node(x, y),
        sprite: (x: number, y: number) => new Node(x, y),
        ellipse: (x: number, y: number) => new Node(x, y),
        text: (x: number, y: number) => new Node(x, y),
      },
    });
    scene.create();
    const internal = scene as unknown as {
      views: Map<string, { sprite: Node }>;
      syncActorViews(delta: number, time: number): void;
    };
    const positions: number[] = [];
    let nextTile = TILE_CADENCE_MS_1X;
    let x = 1;
    for (let i = 0; i <= 400; i++) {
      const time = i * FRAME;
      if (time >= nextTile) {
        nextTile += TILE_CADENCE_MS_1X;
        x += 1;
        const actor = mirror.actors.get('hero')!;
        actor.x = x;
      }
      internal.syncActorViews(FRAME, time);
      positions.push(internal.views.get('hero')!.sprite.x);
    }
    const settled = positions.slice(Math.ceil(TILE_CADENCE_MS_1X / FRAME) + 1, 300);
    const steps = settled.slice(1).map((value, i) => value - settled[i]!);
    expect(steps.filter((step) => Math.abs(step) < 1e-9)).toHaveLength(0);
  });
});
