import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorldMirror } from '../../world-mirror';
import { useUiStore } from '../../../store/uiStore';

vi.mock('phaser', () => ({ default: { Scene: class {} } }));
import { WorldScene } from '../../scenes/WorldScene';

class Node {
  visible = true;
  scale = 1;
  depth = 0;
  destroyed = false;
  texture = { key: 'villager' };
  constructor(
    public x: number,
    public y: number,
    public width: number,
    public height: number,
    public text = '',
  ) {}
  get displayWidth() {
    return this.width * this.scale;
  }
  get displayHeight() {
    return this.height * this.scale;
  }
  setOrigin() {
    return this;
  }
  setDepth(depth: number) {
    this.depth = depth;
    return this;
  }
  setScale(scale: number) {
    this.scale = scale;
    return this;
  }
  setPosition(x: number, y: number) {
    this.x = x;
    this.y = y;
    return this;
  }
  setVisible(visible: boolean) {
    this.visible = visible;
    return this;
  }
  setFrame() {
    return this;
  }
  setAlpha() {
    return this;
  }
  destroy() {
    this.destroyed = true;
  }
}

type View = { sprite: Node; label: Node | null; shadow: Node };
type Actor = { token: string; name?: string; x: number; y: number };
const HERO: Actor = { token: 'hero', name: '陈默', x: 5, y: 5 };
const CROWD: Actor[] = [
  { token: 'a', name: '吴秀才', x: 5, y: 5 },
  { token: 'b', name: '陶罐匠', x: 5, y: 5 },
  { token: 'c', name: '李阿婆', x: 5, y: 5 },
  { token: 'd', name: '周木匠', x: 5, y: 5 },
  HERO,
];

function setup(mode: 'flat' | 'iso', actors: readonly Actor[]) {
  const mirror = new WorldMirror();
  mirror.setMap({ w: 24, h: 24, tileset: 'grid', collision: new Uint8Array(24 * 24).fill(1) });
  mirror.protagonist = HERO.token;
  for (const actor of actors) {
    mirror.actors.set(actor.token, {
      rtoken: actor.token,
      x: actor.x,
      y: actor.y,
      facing: 's',
      sprite: actor.token === HERO.token ? 'protagonist' : 'villager',
      anim: 'idle',
      ...(actor.name === undefined ? {} : { name: actor.name }),
    });
  }
  const camera = {
    zoom: 1,
    setZoom(zoom: number) {
      this.zoom = zoom;
    },
    setBounds() {},
    startFollow() {},
    stopFollow() {},
  };
  const scene = new WorldScene(mirror, mode);
  Object.assign(scene, {
    textures: { exists: () => true },
    cameras: { main: camera },
    // Run the real frame, actor interpolation and camera zoom; unrelated layers
    // need a canvas / input devices and are outside the name-layout boundary.
    syncMovementInput() {},
    syncVoxelPresentation() {},
    syncOverlay() {},
    syncRain() {},
    syncBubbles() {},
    syncStructures() {},
    add: {
      sprite: (x: number, y: number) => new Node(x, y, 16, 32),
      ellipse: (x: number, y: number, w: number, h: number) => new Node(x, y, w, h),
      // Deterministic measured Text dimensions, including stroke. The long
      // name fixture is deliberately wider than one logical tile on screen.
      text: (x: number, y: number, text: string) =>
        new Node(x, y, text === '远道而来的卖陶器人' ? 132 : text === '陈默' ? 30 : 42, 18, text),
    },
  });
  const internal = scene as unknown as {
    views: Map<string, View>;
    syncCamera(): void;
  };
  return { scene, internal, mirror, camera };
}

function visibleLabels(views: Map<string, View>): Node[] {
  return [...views.values()].flatMap(({ label }) => (label?.visible ? [label] : []));
}

function expectNoOverlap(labels: readonly Node[], zoom: number) {
  for (let i = 0; i < labels.length; i += 1) {
    const a = labels[i]!;
    for (const b of labels.slice(i + 1)) {
      // Independent rectangle intersection for Text origin (0.5, 1).
      const horizontal =
        Math.abs(a.x - b.x) * zoom < ((a.displayWidth + b.displayWidth) * zoom) / 2;
      const vertical = a.y > b.y - b.displayHeight && a.y - a.displayHeight < b.y;
      expect(horizontal && vertical, `${a.text} overlaps ${b.text}`).toBe(false);
    }
  }
}

beforeEach(() => useUiStore.setState({ speed: 1 }));

describe.each(['flat', 'iso'] as const)('%s name layout', (mode) => {
  it('keeps two same-cell names readable with the protagonist at its own head', () => {
    const { scene, internal, camera } = setup(mode, [CROWD[0]!, HERO]);
    scene.update(1000, 16);
    const hero = internal.views.get(HERO.token)!;
    expect(hero.label!.visible).toBe(true);
    expect(hero.label!.x).toBe(hero.sprite.x);
    expect(hero.label!.y).toBeCloseTo(hero.sprite.y - 32 - (mode === 'iso' ? 6 / camera.zoom : 2));
    const labels = visibleLabels(internal.views);
    expect(labels).toHaveLength(2);
    expectNoOverlap(labels, camera.zoom);
    expect(labels.map((label) => label.text).sort()).toEqual(['吴秀才', '陈默'].sort());
  });

  it('bounds five same-cell labels and hides overflow while preserving every actor', () => {
    const { scene, internal, camera } = setup(mode, CROWD);
    scene.update(1000, 16);
    const labels = visibleLabels(internal.views);
    expect(labels.length).toBeGreaterThan(1);
    expect(labels.length).toBeLessThan(5);
    expectNoOverlap(labels, camera.zoom);
    expect(internal.views.get(HERO.token)!.label!.visible).toBe(true);
    for (const { sprite, shadow, label } of internal.views.values()) {
      expect(sprite.visible).toBe(true);
      expect(shadow.visible).toBe(true);
      expect(sprite.destroyed).toBe(false);
      const anchor = sprite.y - 32 - (mode === 'iso' ? 6 / camera.zoom : 2);
      if (label?.visible) {
        expect((anchor - label.y) * camera.zoom).toBeGreaterThanOrEqual(-1e-9);
        expect((anchor - label.y) * camera.zoom).toBeLessThanOrEqual(36 + 1e-9);
      }
    }
    expect(internal.views.size).toBe(5);
  });

  it('detects collisions across different cells using the measured long-name width', () => {
    const { scene, internal, camera } = setup(mode, [
      HERO,
      { token: 'seller', name: '远道而来的卖陶器人', x: 6, y: mode === 'iso' ? 4 : 5 },
      { token: 'potter', name: '远道而来的卖陶器人', x: 7, y: mode === 'iso' ? 3 : 5 },
    ]);
    scene.update(1000, 16);
    const labels = visibleLabels(internal.views);
    expect(labels).toHaveLength(3);
    expectNoOverlap(labels, camera.zoom);
  });

  it('leaves separated names at their head anchors', () => {
    const { scene, internal, camera } = setup(mode, [
      HERO,
      { token: 'neighbor', name: '周木匠', x: 9, y: 5 },
    ]);
    scene.update(1000, 16);
    expect(visibleLabels(internal.views)).toHaveLength(2);
    for (const { label, sprite } of internal.views.values()) {
      expect(label!.x).toBe(sprite.x);
      expect(label!.y).toBeCloseTo(sprite.y - 32 - (mode === 'iso' ? 6 / camera.zoom : 2));
    }
  });

  it('produces the same layout when actor arrival order changes', () => {
    const forward = setup(mode, CROWD);
    const reverse = setup(mode, [...CROWD].reverse());
    forward.scene.update(1000, 16);
    reverse.scene.update(1000, 16);
    for (const actor of CROWD) {
      const a = forward.internal.views.get(actor.token)!.label!;
      const b = reverse.internal.views.get(actor.token)!.label!;
      expect({ x: a.x, y: a.y, visible: a.visible }).toEqual({
        x: b.x,
        y: b.y,
        visible: b.visible,
      });
    }
  });

  it('recomputes layout during movement and restores the name once actors separate', () => {
    const { scene, internal, mirror, camera } = setup(mode, CROWD);
    scene.update(1000, 16);
    const [hiddenToken, hiddenView] = [...internal.views].find(([, view]) => !view.label!.visible)!;
    expect(hiddenView.label!.visible).toBe(false);
    mirror.actors.get(hiddenToken)!.x = 10;
    for (const time of [1016, 1050, 1100, 1150, 1216]) {
      scene.update(time, 16);
      expectNoOverlap(visibleLabels(internal.views), camera.zoom);
    }
    const neighbor = internal.views.get(hiddenToken)!;
    expect(neighbor.label!.visible).toBe(true);
    expect(neighbor.label!.x).toBe(neighbor.sprite.x);
    expect(neighbor.label!.y).toBeCloseTo(
      neighbor.sprite.y - 32 - (mode === 'iso' ? 6 / camera.zoom : 2),
    );
  });

  it('uses the current camera zoom for fixed-size text and collision checks', () => {
    const { scene, internal, camera } = setup(mode, [
      HERO,
      { token: 'seller', name: '远道而来的卖陶器人', x: 6, y: mode === 'iso' ? 4 : 5 },
    ]);
    // The layout also works when a camera controller changes the zoom.
    internal.syncCamera = () => {};
    for (const zoom of [1, 2, 5]) {
      camera.zoom = zoom;
      scene.update(1000, 16);
      const labels = visibleLabels(internal.views);
      expect(labels).toHaveLength(2);
      expectNoOverlap(labels, zoom);
      expect(internal.views.get(HERO.token)!.label!.displayWidth * zoom).toBeCloseTo(30);
      expect(internal.views.get('seller')!.label!.displayWidth * zoom).toBeCloseTo(132);
    }
  });

  it('keeps distant and unnamed actors out of the name-layout budget', () => {
    const { scene, internal, camera } = setup(mode, [
      HERO,
      { token: 'far', name: '周木匠', x: 20, y: 5 },
      { token: 'unnamed', x: 5, y: 5 },
    ]);
    scene.update(1000, 16);
    expect(visibleLabels(internal.views).map((label) => label.text)).toEqual(['陈默']);
    expect(internal.views.get('far')!.label!.visible).toBe(false);
    expect(internal.views.get('unnamed')!.label).toBeNull();
    expectNoOverlap(visibleLabels(internal.views), camera.zoom);
  });
});
