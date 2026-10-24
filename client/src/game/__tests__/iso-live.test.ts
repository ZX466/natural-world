import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorldMirror } from '../world-mirror';
import { createHeightLookup, depthKey, isoProject, screenBounds } from '../render/iso';
import { actorDepth, labelY, aboveSurface } from '../render/presentation';
import { facingRow, walkFrame } from '../render/actors';
import { useUiStore } from '../../store/uiStore';

vi.mock('phaser', () => ({ default: { Scene: class {} } }));
import { WorldScene } from '../scenes/WorldScene';

class View {
  texture: { key: string };
  destroyed = false;
  setOrigin = vi.fn(() => this);
  setDepth = vi.fn(() => this);
  setFrame = vi.fn(() => this);
  setAlpha = vi.fn(() => this);
  setScale = vi.fn(() => this);
  setVisible = vi.fn(() => this);
  setPosition = vi.fn((x: number, y: number) => {
    this.x = x;
    this.y = y;
    return this;
  });
  destroy() {
    this.destroyed = true;
  }
  constructor(
    public x: number,
    public y: number,
    key = '',
    public width = 0,
    public height = 0,
  ) {
    this.texture = { key };
  }
}

type ActorView = {
  sprite: View;
  shadow: View;
  label: View;
  lastFacing: string;
  animClockMs: number;
};

function setup(mode: 'flat' | 'iso' = 'iso') {
  const mirror = new WorldMirror();
  mirror.setMap({ w: 4, h: 4, tileset: 'grid', collision: new Uint8Array(16).fill(1) });
  mirror.protagonist = 'hero';
  mirror.actors.set('hero', {
    rtoken: 'hero',
    x: 2,
    y: 1,
    facing: 's',
    sprite: 'protagonist',
    anim: 'idle',
    name: '陈默',
  });
  const heights = new Array<number>(16).fill(1);
  heights[6] = 3;
  const camera = {
    setBounds: vi.fn().mockReturnThis(),
    setZoom: vi.fn().mockReturnThis(),
    startFollow: vi.fn().mockReturnThis(),
    stopFollow: vi.fn(),
  };
  const marker = new View(0, 0);
  const emit = vi.fn();
  const scene = new WorldScene(mirror, mode);
  Object.assign(scene, {
    heightAt: createHeightLookup({ w: 4, h: 4, h_values: heights }),
    textures: { exists: () => true },
    cameras: { main: camera },
    game: { events: { emit } },
    goalMarker: marker,
    add: {
      sprite: (x: number, y: number, key: string) => new View(x, y, key),
      ellipse: (x: number, y: number, w: number, h: number) => new View(x, y, '', w, h),
      text: (x: number, y: number) => new View(x, y),
    },
  });
  const internal = scene as unknown as {
    views: Map<string, ActorView>;
    syncActorViews(delta: number, time: number): void;
    syncCamera(): void;
    handlePointer(pointer: { worldX: number; worldY: number }): void;
  };
  return { scene, internal, mirror, camera, marker, emit };
}

beforeEach(() => useUiStore.setState({ speed: 1 }));

it('spawns billboard feet at the effective top with a shared depth and contact shadow', () => {
  const { internal } = setup();
  internal.syncActorViews(0, 0);
  const { sprite, shadow, label } = internal.views.get('hero')!;
  const top = isoProject(2, 1, 3, screenBounds(4, 4));
  expect({ x: sprite.x, y: sprite.y }).toEqual({ x: top.sx, y: top.sy });
  expect(sprite.setOrigin).toHaveBeenLastCalledWith(0.5, 1);
  expect(sprite.setDepth).toHaveBeenLastCalledWith(depthKey(2, 1) + 1);
  expect({ x: shadow.x, y: shadow.y, w: shadow.width, h: shadow.height }).toEqual({
    x: top.sx,
    y: top.sy,
    w: 16,
    h: 4,
  });
  expect(shadow.setDepth).toHaveBeenLastCalledWith(depthKey(2, 1) + 0.5);
  expect(label.setPosition).toHaveBeenLastCalledWith(top.sx, aboveSurface(top.sy, 32, 6, 3.5));
});

it('uses the same built/collapsing/rubble height changes for actor feet and camera', () => {
  const { internal, mirror, camera } = setup();
  mirror.applyStructures([{ rtoken: 'house', x: 2, y: 1, phase: 'built' }]);
  internal.syncActorViews(0, 1000);
  internal.syncCamera();
  const built = isoProject(2, 1, 2, screenBounds(4, 4));
  expect(internal.views.get('hero')!.sprite.y).toBe(built.sy);
  expect(camera.startFollow.mock.calls.at(-1)?.[0]).toMatchObject({ x: built.sx, y: built.sy });
  mirror.applyStructures([{ rtoken: 'house', x: 2, y: 1, phase: 'collapsing' }]);
  internal.syncActorViews(0, 1100);
  internal.syncCamera();
  expect(internal.views.get('hero')!.sprite.y).toBe(built.sy);
  mirror.applyStructures([{ rtoken: 'house', x: 2, y: 1, phase: 'rubble' }]);
  internal.syncActorViews(0, 1200);
  internal.syncCamera();
  expect(internal.views.get('hero')!.sprite.y).toBe(isoProject(2, 1, 3, screenBounds(4, 4)).sy);
  expect(camera.startFollow.mock.calls.at(-1)?.[0].y).toBe(internal.views.get('hero')!.sprite.y);
});

it('follows the logical top without crowd offsets and pads the diamond bounds by 64', () => {
  const { internal, mirror, camera } = setup();
  mirror.actors.set('a-neighbour', {
    rtoken: 'a-neighbour',
    x: 2,
    y: 1,
    facing: 's',
    sprite: 'villager',
    anim: 'idle',
  });
  internal.syncActorViews(0, 1000);
  internal.syncCamera();
  const top = isoProject(2, 1, 3, screenBounds(4, 4));
  const target = camera.startFollow.mock.calls.at(-1)?.[0];
  expect(target).toMatchObject({ x: top.sx, y: top.sy });
  expect(target).not.toBe(internal.views.get('hero')!.sprite);
  const bounds = screenBounds(4, 4);
  expect(camera.setBounds).toHaveBeenLastCalledWith(
    -64,
    -64,
    bounds.width + 128,
    bounds.height + 128,
  );
  internal.syncCamera();
  expect(camera.startFollow).toHaveBeenCalledTimes(1);
  mirror.actors.delete('hero');
  internal.syncCamera();
  expect(camera.stopFollow).toHaveBeenCalledTimes(1);
});

it('cleans reset views and recreates them directly at the projected surface', () => {
  const { internal, mirror } = setup();
  internal.syncActorViews(0, 0);
  const previous = internal.views.get('hero')!.sprite;
  mirror.reset();
  mirror.protagonist = 'hero';
  mirror.actors.set('hero', {
    rtoken: 'hero',
    x: 0,
    y: 0,
    facing: 's',
    sprite: 'protagonist',
    anim: 'idle',
  });
  internal.syncActorViews(0, 0);
  expect(previous.destroyed).toBe(true);
  const next = internal.views.get('hero')!.sprite;
  const top = isoProject(0, 0, 1, screenBounds(4, 4));
  expect({ x: next.x, y: next.y }).toEqual({ x: top.sx, y: top.sy });
});

describe.each(['flat', 'iso'] as const)('%s interaction and movement', (mode) => {
  it('keeps move requests/collision guards and positions the target marker on its surface', () => {
    const { internal, mirror, marker, emit } = setup(mode);
    const hit = mode === 'iso' ? isoProject(2, 1, 0, screenBounds(4, 4)) : { sx: 40, sy: 24 };
    internal.handlePointer({ worldX: hit.sx, worldY: hit.sy });
    expect(emit).toHaveBeenLastCalledWith('client:move_request', { x: 2, y: 1 });
    const markerPos = mode === 'iso' ? isoProject(2, 1, 3, screenBounds(4, 4)) : hit;
    expect(marker.setPosition).toHaveBeenLastCalledWith(markerPos.sx, markerPos.sy);
    if (mode === 'iso') {
      expect(marker.setDepth).toHaveBeenLastCalledWith(depthKey(2, 1) + 1.5);
    } else {
      expect(marker.setDepth).not.toHaveBeenCalled(); // flat keeps the depth chosen at create().
    }
    emit.mockClear();
    mirror.map!.collision[6] = 0;
    internal.handlePointer({ worldX: hit.sx, worldY: hit.sy });
    internal.handlePointer({ worldX: -10000, worldY: -10000 });
    expect(emit).not.toHaveBeenCalled();
  });

  it('preserves four-way facing, the existing walk clock, and animation frames', () => {
    const { internal, mirror } = setup(mode);
    internal.syncActorViews(0, 0);
    mirror.actors.get('hero')!.x = 3;
    internal.syncActorViews(16, 100);
    internal.syncActorViews(0, 350);
    const view = internal.views.get('hero')!;
    expect(view.lastFacing).toBe('e');
    expect(view.sprite.setFrame).toHaveBeenCalledWith(walkFrame(facingRow('e'), 0));
    const target = mode === 'iso' ? isoProject(3, 1, 1, screenBounds(4, 4)) : { sx: 56, sy: 24 };
    expect({ x: view.sprite.x, y: view.sprite.y }).toEqual({ x: target.sx, y: target.sy });
  });
});

it('preserves flat sprite, shadow, and camera formulas', () => {
  const { internal, camera } = setup('flat');
  internal.syncActorViews(0, 1000);
  internal.syncCamera();
  const { sprite, shadow } = internal.views.get('hero')!;
  expect({ x: sprite.x, y: sprite.y }).toEqual({ x: 40, y: 24 });
  expect(sprite.setDepth).toHaveBeenLastCalledWith(actorDepth(24));
  expect({ x: shadow.x, y: shadow.y, w: shadow.width, h: shadow.height }).toEqual({
    x: 40,
    y: 23,
    w: 10,
    h: 4,
  });
  expect(camera.startFollow).toHaveBeenLastCalledWith(sprite, true, 0.12, 0.12);
  expect(camera.setBounds).toHaveBeenLastCalledWith(0, 0, 64, 64);
  expect(camera.setZoom).toHaveBeenLastCalledWith(3.5);
  expect(internal.views.get('hero')!.label.setPosition).toHaveBeenLastCalledWith(
    sprite.x,
    labelY(sprite.y),
  );
});
