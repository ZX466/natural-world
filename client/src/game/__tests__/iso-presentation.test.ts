import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorldMirror } from '../world-mirror';
import { depthKey } from '../render/iso';
import { useUiStore } from '../../store/uiStore';
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

class Node {
  depth = 0;
  alpha = 1;
  displayWidth = 140;
  displayHeight = 24;
  setOrigin = vi.fn(() => this);
  setScrollFactor = vi.fn(() => this);
  setDepth = vi.fn((depth: number) => {
    this.depth = depth;
    return this;
  });
  setScale = vi.fn((scale: number) => {
    this.displayWidth = this.width * scale;
    this.displayHeight = this.height * scale;
    return this;
  });
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
  setText = vi.fn((value: string) => {
    this.text = value;
    return this;
  });
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
    public height = 24,
    public text = '',
  ) {}
}

function setup(mode: 'flat' | 'iso') {
  const mirror = new WorldMirror();
  mirror.setMap({ w: 4, h: 4, tileset: 'grid', collision: new Uint8Array(16).fill(1) });
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
    cameras: { main: { startFollow: vi.fn() } },
    add: {
      graphics: () => new Node(),
      rectangle: (x: number, y: number, w: number, h: number) => new Node(x, y, w, h),
      circle: (x: number, y: number) => new Node(x, y),
      sprite: (x: number, y: number) => {
        const node = new Node(x, y, 16, 32);
        node.displayHeight = 32;
        return node;
      },
      ellipse: (x: number, y: number) => new Node(x, y),
      text: (x: number, y: number, value: string) => new Node(x, y, 140, 24, value),
    },
  });
  scene.create();
  const internal = scene as unknown as {
    rainLayer: Node;
    nightOverlay: Node;
    views: Map<string, { sprite: Node; label: Node }>;
    bubbleTexts: Map<string, Node>;
    syncActorViews(delta: number, time: number): void;
    syncBubbles(now: number): void;
  };
  return { scene, internal, mirror };
}

beforeEach(() => {
  vi.useFakeTimers();
  useUiStore.setState({ speed: 1 });
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe.each(['flat', 'iso'] as const)('%s presentation', (mode) => {
  it('keeps weather in screen space and places it over the matching depth pool', () => {
    const { internal } = setup(mode);
    expect(internal.rainLayer.setScrollFactor).toHaveBeenLastCalledWith(0);
    expect(internal.nightOverlay.setScrollFactor).toHaveBeenLastCalledWith(0);
    expect(internal.rainLayer.depth).toBe(mode === 'iso' ? 400000 : 99);
    expect(internal.nightOverlay.depth).toBe(mode === 'iso' ? 400001 : 100);
  });

  it('anchors readable names and bubbles above the actor at the right depth', () => {
    const { internal, mirror } = setup(mode);
    internal.syncActorViews(0, 1000);
    mirror.setBubble('陈默', '先去集市看看。', 4000, 0);
    internal.syncBubbles(1);
    const view = internal.views.get('hero')!,
      bubble = internal.bubbleTexts.get('陈默')!;
    if (mode === 'iso') {
      expect(view.label.depth).toBeGreaterThan(depthKey(139, 99) + 2);
      expect(bubble.depth).toBeGreaterThan(view.label.depth);
      expect(bubble.depth).toBeLessThan(internal.rainLayer.depth);
      expect(view.label.y).toBeCloseTo(view.sprite.y - 32 - 6 / 3.5);
      expect(bubble.y).toBeCloseTo(view.sprite.y - 32 - 20 / 3.5);
    } else {
      expect(view.label.depth).toBeLessThan(81);
      expect(bubble.depth).toBeLessThan(99);
      expect(bubble.y).toBe(view.sprite.y - 18);
    }
    expect(bubble.x).toBe(view.sprite.x);
  });
});
