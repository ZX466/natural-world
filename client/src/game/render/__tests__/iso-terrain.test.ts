import type Phaser from 'phaser';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createHeightLookup, depthKey, isoProject, screenBounds } from '../iso';
import { IsoTerrain, sampleTileColor } from '../iso-terrain';
import { WorldMirror, type MapStatic } from '../../world-mirror';
import { rasterContext } from './raster-context';

class Image {
  destroyed = false;
  alpha = 1;
  setOrigin = vi.fn(() => this);
  setDepth = vi.fn(() => this);
  setTint = vi.fn(() => this);
  setAlpha = vi.fn((alpha: number) => {
    this.alpha = alpha;
    return this;
  });
  setPosition = vi.fn((x: number, y: number) => {
    this.x = x;
    this.y = y;
    return this;
  });
  setDisplaySize = vi.fn(() => this);
  setTexture = vi.fn((key: string) => {
    this.key = key;
    return this;
  });
  destroy() {
    this.destroyed = true;
  }
  constructor(
    public x: number,
    public y: number,
    public key: string,
  ) {}
}

function setup(heights = [0, 1, 2, 3], w = 2, h = 2, raster = false) {
  const pixels = new Uint8ClampedArray(16 * 16 * 4);
  for (let i = 0; i < pixels.length; i += 4) pixels.set([100, 150, 200, 255], i);
  const canvases: { width: number; height: number; ctx: ReturnType<typeof context> }[] = [];
  function context(
    size: () => { width: number; height: number } = () => ({ width: 0, height: 0 }),
  ) {
    const software = rasterContext(size);
    const ctx = {
      beginPath: vi.fn(software.beginPath),
      moveTo: vi.fn(software.moveTo),
      lineTo: vi.fn(software.lineTo),
      closePath: vi.fn(software.closePath),
      fill: vi.fn(() => {
        if (raster) software.fill();
      }),
      fillStyle: '',
      drawImage: vi.fn(),
      clearRect: vi.fn((x: number, y: number, width: number, height: number) => {
        if (raster) software.clearRect(x, y, width, height);
      }),
      save: vi.fn(software.save),
      restore: vi.fn(software.restore),
      rect: vi.fn(software.rect),
      clip: vi.fn(software.clip),
      getImageData: () => ({ data: pixels }),
      pixels: software.pixels,
    };
    Object.defineProperty(ctx, 'fillStyle', {
      get: () => software.fillStyle,
      set: (color: string) => {
        software.fillStyle = color;
      },
    });
    return ctx;
  }
  vi.stubGlobal('document', {
    createElement: () => {
      const canvas = { width: 0, height: 0, ctx: context(), getContext: () => canvas.ctx };
      canvas.ctx = context(() => canvas);
      canvases.push(canvas);
      return canvas;
    },
  });
  const textures = new Map<string, unknown>();
  textures.set('god-town-16', { width: 16, height: 16 });
  const images: Image[] = [];
  const refresh = vi.fn();
  const graphics: {
    destroyed: boolean;
    alpha: number;
    setAlpha: ReturnType<typeof vi.fn>;
    x: number;
    y: number;
    depth: number;
    clear: ReturnType<typeof vi.fn>;
    fillStyle: ReturnType<typeof vi.fn>;
    fillPoints: ReturnType<typeof vi.fn>;
  }[] = [];
  const scene = {
    textures: {
      exists: (key: string) => textures.has(key),
      get: (key: string) => ({ getSourceImage: () => textures.get(key) }),
      addCanvas: vi.fn((key: string, canvas: unknown) => {
        textures.set(key, canvas);
        return { refresh };
      }),
      remove: vi.fn((key: string) => {
        textures.delete(key);
      }),
    },
    add: {
      graphics: () => {
        const marker = {
          destroyed: false,
          alpha: 1,
          setAlpha: vi.fn((alpha: number) => {
            marker.alpha = alpha;
            return marker;
          }),
          x: 0,
          y: 0,
          depth: 0,
          clear: vi.fn().mockReturnThis(),
          fillStyle: vi.fn().mockReturnThis(),
          fillPoints: vi.fn().mockReturnThis(),
          setPosition(x: number, y: number) {
            marker.x = x;
            marker.y = y;
            return marker;
          },
          setDepth(depth: number) {
            marker.depth = depth;
            return marker;
          },
          destroy() {
            marker.destroyed = true;
          },
        };
        graphics.push(marker);
        return marker;
      },
      image: (x: number, y: number, key: string) => {
        const image = new Image(x, y, key);
        images.push(image);
        return image;
      },
    },
  };
  const map: MapStatic = {
    w,
    h,
    tileset: 'god-town-16',
    collision: new Uint8Array(w * h).fill(1),
    ground: new Uint16Array(w * h).fill(1),
  };
  const structures = new Map<string, { tiles: [number, number][]; phase: string }>();
  const terrain = new IsoTerrain(
    scene as unknown as Phaser.Scene,
    createHeightLookup({ w, h, h_values: heights }),
  );
  return { terrain, map, structures, images, textures, canvases, graphics, scene, refresh };
}

beforeEach(() => vi.restoreAllMocks());
afterEach(() => vi.unstubAllGlobals());

it('samples the gid central 4×4 mean and uses a deterministic gid=0 fallback', () => {
  const pixels = new Uint8ClampedArray(32 * 16 * 4);
  for (let y = 6; y < 10; y++)
    for (let x = 22; x < 26; x++) {
      pixels.set([50, 120, 150, 255], (y * 32 + x) * 4);
    }
  expect(sampleTileColor(pixels, 32, 16, 2)).toBe(0x327896);
  expect(sampleTileColor(pixels, 32, 16, 1)).toBe(0);
  expect(sampleTileColor(pixels, 32, 16, 0)).toBe(0x6b4f2a);
  expect(sampleTileColor(pixels, 32, 16, 3)).toBe(0x6b4f2a);
});

it('bakes low blocks and gives high images the exact base anchor, size, and depth', () => {
  const { terrain, map, structures, images, textures, canvases } = setup();
  terrain.redraw(map, structures);
  expect(textures.get('iso-ground-composite')).toMatchObject({ width: 64, height: 152 });
  expect(images).toHaveLength(3); // One low canvas, exactly two high images.
  for (const [x, y, height] of [
    [0, 1, 2],
    [1, 1, 3],
  ]) {
    const p = isoProject(x!, y!, 0, screenBounds(2, 2));
    const image = images.find((i) => i.x === p.sx && i.y === p.sy + 8)!;
    expect(image.setOrigin).toHaveBeenLastCalledWith(0.5, 1);
    expect(image.setDisplaySize).toHaveBeenLastCalledWith(32, height! * 16 + 16);
    expect(image.setDepth).toHaveBeenLastCalledWith(depthKey(x!, y!));
  }
  const ground = canvases.find((c) => c.width === 64)!;
  expect(ground.ctx.fill).toHaveBeenCalledTimes(4); // Water top + three ground faces.
});

it('keeps unchanged high images and skips all work on identical frames', () => {
  const { terrain, map, structures, images, canvases } = setup();
  terrain.redraw(map, structures);
  const original = [...images];
  const canvasCount = canvases.length;
  terrain.sync(map, structures);
  expect(canvases).toHaveLength(canvasCount);
  structures.set('house', { tiles: [[1, 0]], phase: 'built' });
  terrain.sync(map, structures);
  expect(original.every((image) => !image.destroyed)).toBe(true);
  expect(images).toHaveLength(4); // Only the newly built high cell needs an Image.
});

it('overrides built/collapsing to two and restores static height on rubble/removal', () => {
  const { terrain, map, structures, images } = setup([0, 1, 0, 0]);
  structures.set('house', { tiles: [[1, 0]], phase: 'built' });
  terrain.redraw(map, structures);
  const house = images[1]!;
  expect(house.setDisplaySize).toHaveBeenLastCalledWith(32, 48);
  structures.get('house')!.phase = 'collapsing';
  terrain.sync(map, structures);
  terrain.advance(240); // V3 preserves the original opacity after the deterministic transition.
  expect(images).toHaveLength(2);
  expect(house.setAlpha).toHaveBeenLastCalledWith(0.5);
  expect(house.setDisplaySize).toHaveBeenLastCalledWith(32, 48);
  structures.get('house')!.phase = 'rubble';
  terrain.sync(map, structures);
  expect(house.destroyed).toBe(true);
  expect(images).toHaveLength(2);
  structures.clear();
  terrain.sync(map, structures);
  expect(images).toHaveLength(2);
});

it('repositions retained high cells when a replacement map changes its origin', () => {
  const { terrain, map, structures, images } = setup();
  terrain.redraw(map, structures);
  const retained = images[1]!;
  const taller = { ...map, h: 3, ground: new Uint16Array(6).fill(1), collision: new Uint8Array(6) };
  terrain.sync(taller, structures);
  const base = isoProject(0, 1, 0, screenBounds(2, 3));
  expect(retained.destroyed).toBe(false);
  expect({ x: retained.x, y: retained.y }).toEqual({ x: base.sx, y: base.sy + 8 });
});

it('handles in-place ground edits, empty maps, and releases generated textures on shutdown', () => {
  const { terrain, map, structures, images, textures } = setup();
  terrain.redraw(map, structures);
  map.ground![2] = 0;
  terrain.sync(map, structures);
  expect(textures.has('iso-block-2')).toBe(true);
  expect(images[1]!.setTint).toHaveBeenLastCalledWith(0x6b4f2a);
  terrain.sync(null, structures);
  expect(images.every((image) => image.destroyed)).toBe(true);
  terrain.redraw(map, structures);
  terrain.destroy();
  expect(images.every((image) => image.destroyed)).toBe(true);
  expect([...textures.keys()]).toEqual(['god-town-16']);
});

it('merges a built structure into the terrain cell once and puts rubble in the same depth pool', () => {
  const { terrain, map, structures, images, graphics } = setup([0, 1, 0, 0]);
  structures.set('house', { tiles: [[1, 0]], phase: 'built' });
  terrain.redraw(map, structures);
  const house = images[1]!;
  expect(images.filter((image) => !image.destroyed)).toHaveLength(2);
  expect(house.setDepth).toHaveBeenLastCalledWith(depthKey(1, 0));
  expect(house.setAlpha).toHaveBeenLastCalledWith(0.92);
  structures.get('house')!.phase = 'rubble';
  terrain.sync(map, structures);
  expect(house.destroyed).toBe(true);
  expect(graphics).toHaveLength(1);
  const marker = graphics[0]!;
  const top = isoProject(1, 0, 1, screenBounds(2, 2));
  expect(marker).toMatchObject({ x: top.sx, y: top.sy, depth: depthKey(1, 0), destroyed: false });
  expect(marker.fillPoints).toHaveBeenCalledTimes(3);
  expect(marker.fillStyle).toHaveBeenLastCalledWith(0x6b4f2a, 0.5);
  terrain.sync(map, structures);
  expect(marker.clear).toHaveBeenCalledTimes(1);
  structures.get('house')!.phase = 'built';
  terrain.sync(map, structures);
  expect(marker.destroyed).toBe(true);
  expect(images.filter((image) => !image.destroyed)).toHaveLength(2);
});

it('rebuilds moved footprints and clears rubble on removal, empty maps, and shutdown', () => {
  const { terrain, map, structures, images, graphics, textures } = setup([0, 1, 0, 0]);
  structures.set('house', { tiles: [[1, 0]], phase: 'built' });
  terrain.redraw(map, structures);
  const old = images[1]!;
  structures.get('house')!.tiles = [[0, 1]];
  terrain.sync(map, structures);
  expect(old.destroyed).toBe(true);
  expect(images.filter((image) => !image.destroyed)).toHaveLength(2);
  structures.get('house')!.phase = 'rubble';
  terrain.sync(map, structures);
  expect(graphics).toHaveLength(1);
  const ground = isoProject(0, 1, 0, screenBounds(2, 2));
  expect(graphics[0]).toMatchObject({ x: ground.sx, y: ground.sy, depth: depthKey(0, 1) });
  structures.clear();
  terrain.sync(map, structures);
  expect(graphics[0]!.destroyed).toBe(true);
  structures.set('ruin', { tiles: [[0, 1]], phase: 'rubble' });
  terrain.sync(map, structures);
  terrain.sync(null, structures);
  expect(graphics.every((marker) => marker.destroyed)).toBe(true);
  terrain.redraw(map, structures);
  terrain.destroy();
  expect(graphics.every((marker) => marker.destroyed)).toBe(true);
  expect([...textures.keys()]).toEqual(['god-town-16']);
});

it('draws overlapping ruins only once and lets a newer active footprint cover them', () => {
  const { terrain, map, structures, images, graphics } = setup([0, 1, 0, 0]);
  structures.set('old', { tiles: [[1, 0]], phase: 'rubble' });
  structures.set('older', { tiles: [[1, 0]], phase: 'rubble' });
  structures.set('new', { tiles: [[1, 0]], phase: 'collapsing' });
  terrain.redraw(map, structures);
  expect(images).toHaveLength(2);
  expect(graphics).toHaveLength(0);
  structures.delete('new');
  terrain.sync(map, structures);
  expect(graphics).toHaveLength(1);
  expect(graphics[0]!.fillPoints).toHaveBeenCalledTimes(3);
});

it('advances structure opacity by explicit deltas without changing the block height', () => {
  const { terrain, map, structures, images, canvases } = setup([0, 1, 0, 0]);
  structures.set('house', { tiles: [[1, 0]], phase: 'built' });
  terrain.redraw(map, structures);
  const house = images[1]!;
  expect(house.alpha).toBe(0.92);
  const canvasCount = canvases.length;
  structures.get('house')!.phase = 'collapsing';
  terrain.sync(map, structures);
  expect(canvases).toHaveLength(canvasCount); // An opacity-only phase must not stall on a map bake.
  expect(house.alpha).toBe(0.92);
  terrain.advance(120);
  expect(house.alpha).toBeCloseTo(0.71);
  expect(house.setDisplaySize).toHaveBeenLastCalledWith(32, 48);
  terrain.advance(120);
  expect(house.alpha).toBe(0.5);
  structures.get('house')!.phase = 'built';
  terrain.sync(map, structures);
  terrain.advance(60);
  terrain.advance(60);
  expect(house.alpha).toBeCloseTo(0.71);
  terrain.advance(120);
  expect(house.alpha).toBe(0.92);
});

it('drops the high block immediately on rubble and fades only the low marker', () => {
  const { terrain, map, structures, images, graphics } = setup([0, 1, 0, 0]);
  structures.set('house', { tiles: [[1, 0]], phase: 'collapsing' });
  terrain.redraw(map, structures);
  structures.get('house')!.phase = 'rubble';
  terrain.sync(map, structures);
  expect(images[1]!.destroyed).toBe(true);
  expect(graphics[0]!.alpha).toBe(0);
  terrain.advance(120);
  expect(graphics[0]!.alpha).toBeCloseTo(0.5);
  terrain.advance(120);
  expect(graphics[0]!.alpha).toBe(1);
  terrain.destroy();
  terrain.advance(240);
});

it('shares a fixed height texture across differently colored cells and preserves their tints', () => {
  const { terrain, map, structures, images, textures } = setup([2, 2, 2, 2]);
  terrain.redraw(map, structures);
  expect([...textures.keys()].filter((key) => key.startsWith('iso-block-'))).toEqual([
    'iso-block-2',
  ]);
  expect(images.slice(1).every((image) => image.key === 'iso-block-2')).toBe(true);
  expect(images[1]!.setTint).toHaveBeenLastCalledWith(0x6496c8);
  map.ground![1] = 0;
  terrain.sync(map, structures);
  expect(images[2]!.setTint).toHaveBeenLastCalledWith(0x6b4f2a);
  expect(images[1]!.setTint).toHaveBeenLastCalledWith(0x6496c8);
  expect([...textures.keys()].filter((key) => key.startsWith('iso-block-'))).toHaveLength(1);
});

it('includes edits in the surface cache and uses the resulting stone layer for a dug high column', () => {
  const { terrain, map, structures, images } = setup([0, 1, 3, 3]);
  const edits = new Map<
    string,
    { x: number; y: number; action: 'dig' | 'place'; gid: number; height: number }
  >();
  terrain.redraw(map, structures, edits);
  const high = images[1]!;
  edits.set('0,1', { x: 0, y: 1, action: 'dig', gid: 0, height: 2 });
  terrain.sync(map, structures, edits);
  expect(high.setTint).toHaveBeenLastCalledWith(0x8a8880);
  expect(high.setDisplaySize).toHaveBeenLastCalledWith(32, 48); // Dig lowers the canopy from 3 to 2.
});

it('marks a dug cell with a dark scar and clears it when the edit goes away', () => {
  const { terrain, map, structures, graphics } = setup([0, 1, 2, 3]);
  const edits = new Map<
    string,
    { x: number; y: number; action: 'dig' | 'place'; gid: number; height: number }
  >();
  terrain.redraw(map, structures, edits);
  expect(graphics).toHaveLength(0);
  edits.set('0,1', { x: 0, y: 1, action: 'dig', gid: 1, height: 1 });
  terrain.sync(map, structures, edits);
  expect(graphics).toHaveLength(1);
  const top = isoProject(0, 1, 1, screenBounds(2, 2));
  expect(graphics[0]).toMatchObject({ x: top.sx, y: top.sy, depth: depthKey(0, 1) + 0.5 });
  expect(graphics[0]!.fillStyle).toHaveBeenCalledWith(0x3f3020, expect.any(Number));
  edits.clear();
  terrain.sync(map, structures, edits);
  expect(graphics[0]!.destroyed).toBe(true);
});

it('does not scar a placed cell, whose raised block is its own marker', () => {
  const { terrain, map, structures, graphics } = setup([0, 1, 0, 0]);
  const edits = new Map<
    string,
    { x: number; y: number; action: 'dig' | 'place'; gid: number; height: number }
  >();
  edits.set('1,0', { x: 1, y: 0, action: 'place', gid: 0, height: 2 });
  terrain.redraw(map, structures, edits);
  expect(graphics).toHaveLength(0);
});

it('removes a height-two image when digging lowers it into the ground canvas', () => {
  const { terrain, map, structures, images, graphics } = setup([0, 1, 2, 3]);
  terrain.redraw(map, structures);
  const high = images[1]!;
  const edits = new Map([['0,1', { x: 0, y: 1, action: 'dig' as const, gid: 1, height: 1 }]]);
  terrain.sync(map, structures, edits);
  expect(high.destroyed).toBe(true);
  expect(graphics[0]!.y).toBe(48); // origin 56 + diagonal 8 - one height 16.
});

it('leaves no floating scar when digging reaches ground level', () => {
  const { terrain, map, structures, graphics } = setup([0, 1, 0, 0]);
  const edits = new Map([['1,0', { x: 1, y: 0, action: 'dig' as const, gid: 0, height: 0 }]]);
  terrain.redraw(map, structures, edits);
  expect(graphics).toHaveLength(0);
});

it('destroys a prior scar when a replacement edit reaches zero', () => {
  const { terrain, map, structures, graphics } = setup([0, 1, 2, 3]);
  const edits = new Map([['0,1', { x: 0, y: 1, action: 'dig' as const, gid: 1, height: 1 }]]);
  terrain.redraw(map, structures, edits);
  expect(graphics).toHaveLength(1);
  const replacement = new Map([['1,0', { x: 1, y: 0, action: 'dig' as const, gid: 0, height: 0 }]]);
  terrain.sync(map, structures, replacement);
  expect(graphics[0]!.destroyed).toBe(true);
  expect(graphics).toHaveLength(1);
});

it('marks a dug cell with a dark scar and clears it when the edit goes away', () => {
  const { terrain, map, structures, graphics } = setup([0, 1, 2, 3]);
  const edits = new Map<
    string,
    { x: number; y: number; action: 'dig' | 'place'; gid: number; height: number }
  >();
  terrain.redraw(map, structures, edits);
  expect(graphics).toHaveLength(0);
  edits.set('0,1', { x: 0, y: 1, action: 'dig', gid: 1, height: 1 });
  terrain.sync(map, structures, edits);
  expect(graphics).toHaveLength(1);
  // 2026-10-26 裁：dig 一次降一层，疤痕贴在**降后**的顶面（height 2 → 1）。
  const top = isoProject(0, 1, 1, screenBounds(2, 2));
  expect(graphics[0]).toMatchObject({ x: top.sx, y: top.sy, depth: depthKey(0, 1) + 0.5 });
  expect(graphics[0]!.fillStyle).toHaveBeenCalledWith(0x3f3020, expect.any(Number));
  edits.clear();
  terrain.sync(map, structures, edits);
  expect(graphics[0]!.destroyed).toBe(true);
});

it('does not scar a placed cell, whose raised block is its own marker', () => {
  const { terrain, map, structures, graphics } = setup([0, 1, 0, 0]);
  const edits = new Map<
    string,
    { x: number; y: number; action: 'dig' | 'place'; gid: number; height: number }
  >();
  edits.set('1,0', { x: 1, y: 0, action: 'place', gid: 0, height: 2 });
  terrain.redraw(map, structures, edits);
  expect(graphics).toHaveLength(0);
});

it('creates a placed height-two block and removes it on an empty restored edit ledger', () => {
  const { terrain, map, structures, images } = setup([0, 1, 0, 0]);
  const edits = new Map<
    string,
    { x: number; y: number; action: 'dig' | 'place'; gid: number; height: number }
  >();
  terrain.redraw(map, structures, edits);
  edits.set('1,0', { x: 1, y: 0, action: 'place', gid: 0, height: 2 });
  terrain.sync(map, structures, edits);
  const placed = images[1]!;
  expect(placed.setDisplaySize).toHaveBeenLastCalledWith(32, 48);
  expect(placed.setTint).toHaveBeenLastCalledWith(0x8a8880);
  edits.clear();
  terrain.sync(map, structures, edits);
  expect(placed.destroyed).toBe(true);
});

it('does no ground or collection traversal during 120 frames with an unchanged version', () => {
  const { terrain, map, structures } = setup();
  const reads = vi.fn();
  map.ground = new Proxy(map.ground!, {
    get(target, property) {
      reads();
      const value = Reflect.get(target, property, target);
      return typeof value === 'function' ? value.bind(target) : value;
    },
  });
  const edits = new Map();
  terrain.redraw(map, structures, edits, 7);
  const values = vi.spyOn(structures, 'values');
  const entries = vi.spyOn(structures, Symbol.iterator);
  const editEntries = vi.spyOn(edits, Symbol.iterator);
  reads.mockClear();
  for (let i = 0; i < 120; i++) terrain.sync(map, structures, edits, 7);
  expect(reads).not.toHaveBeenCalled();
  expect(values).not.toHaveBeenCalled();
  expect(entries).not.toHaveBeenCalled();
  expect(editEntries).not.toHaveBeenCalled();
});

it('repaints a clipped neighborhood after one edit and retains the canvas texture', () => {
  const { terrain, map, structures, canvases, textures, scene, refresh } = setup(
    new Array<number>(1600).fill(1),
    40,
    40,
  );
  const edits = new Map<
    string,
    { x: number; y: number; action: 'dig' | 'place'; gid: number; height: number }
  >();
  terrain.redraw(map, structures, edits, 1);
  const ground = textures.get('iso-ground-composite');
  const ctx = canvases.find((c) => c.width === 1280)!.ctx;
  expect(ctx.fill).toHaveBeenCalledTimes(4800);
  const canvasCount = canvases.length;
  ctx.fill.mockClear();
  scene.textures.addCanvas.mockClear();
  scene.textures.remove.mockClear();
  edits.set('20,20', { x: 20, y: 20, action: 'dig', gid: 0, height: 0 });
  terrain.sync(map, structures, edits, 2);
  expect(textures.get('iso-ground-composite')).toBe(ground);
  expect(canvases).toHaveLength(canvasCount);
  expect(scene.textures.remove).not.toHaveBeenCalled();
  expect(scene.textures.addCanvas).not.toHaveBeenCalled();
  expect(ctx.clip).toHaveBeenCalledTimes(1);
  expect(ctx.clearRect).toHaveBeenCalledTimes(1);
  const [x, y, width, height] = ctx.clearRect.mock.calls[0]!;
  expect(x).toBeGreaterThan(0);
  expect(y).toBeGreaterThan(0);
  expect(width).toBeLessThanOrEqual(36);
  expect(height).toBeLessThanOrEqual(36);
  expect(ctx.fill.mock.calls.length).toBeGreaterThan(1); // Includes the overlapping neighbors.
  expect(ctx.fill.mock.calls.length).toBeLessThan(100); // Over 98% fewer than the 4800-call bake.
  console.info(`terrain paints: full=4800, dirty=${ctx.fill.mock.calls.length}; idle frames=120`);
  expect(refresh).toHaveBeenCalledTimes(1);
});

it('does not upload ground pixels for phase-only or high-only changes', () => {
  const { terrain, map, structures, canvases, refresh } = setup([2, 2, 2, 2]);
  structures.set('house', { tiles: [[1, 0]], phase: 'built' });
  const edits = new Map<
    string,
    { x: number; y: number; action: 'dig' | 'place'; gid: number; height: number }
  >();
  terrain.redraw(map, structures, edits, 1);
  const canvasCount = canvases.length;
  structures.get('house')!.phase = 'collapsing';
  terrain.sync(map, structures, edits, 2);
  edits.set('0,1', { x: 0, y: 1, action: 'place', gid: 0, height: 3 });
  terrain.sync(map, structures, edits, 3);
  expect(refresh).not.toHaveBeenCalled();
  expect(canvases.length - canvasCount).toBeLessThanOrEqual(1); // At most the shared h=3 texture.
});

it('matches a fresh full bake through clipped dig/place, low/high transitions and edge edits', () => {
  const heights = [0, 1, 2, 3, 1, 0, 1, 2, 1, 1, 0, 1, 3, 2, 1, 0];
  const live = setup(heights, 4, 4, true);
  const edits = new Map<
    string,
    { x: number; y: number; action: 'dig' | 'place'; gid: number; height: number }
  >();
  live.terrain.redraw(live.map, live.structures, edits, 0);
  const original = live.textures.get('iso-ground-composite');
  expect(live.canvases.find((c) => c.width === 128)!.ctx.pixels()).toContain(0xff6496c8);
  const snapshots = [
    [{ x: 0, y: 0, action: 'place' as const, gid: 0, height: 2 }],
    [{ x: 1, y: 0, action: 'dig' as const, gid: 1, height: 1 }],
    [{ x: 2, y: 0, action: 'dig' as const, gid: 1, height: 1 }],
    [{ x: 2, y: 2, action: 'place' as const, gid: 0, height: 2 }],
    [{ x: 3, y: 3, action: 'place' as const, gid: 0, height: 2 }],
    [],
  ];
  for (const [i, snapshot] of snapshots.entries()) {
    edits.clear();
    for (const row of snapshot) edits.set(`${row.x},${row.y}`, row);
    live.terrain.sync(live.map, live.structures, edits, i + 1);
    expect(live.textures.get('iso-ground-composite')).toBe(original);
    const reference = setup(heights, 4, 4, true);
    reference.terrain.redraw(reference.map, reference.structures, edits);
    const actual = live.canvases.find((c) => c.width === 128)!.ctx.pixels!();
    const expected = reference.canvases.find((c) => c.width === 128)!.ctx.pixels!();
    expect(actual, `edit snapshot ${i}`).toEqual(expected);
  }
});

it('matches full ground pixels after versioned structures, in-place edits, empty snapshots and reset', () => {
  const heights = [0, 1, 2, 3, 1, 0, 1, 2, 1, 1, 0, 1, 3, 2, 1, 0];
  const live = setup(heights, 4, 4, true);
  const mirror = new WorldMirror();
  mirror.setMap(live.map);
  live.terrain.redraw(mirror.map, mirror.structures, mirror.voxelEdits, mirror.terrainVersion);
  const changes = [
    () => mirror.applyVoxelEdits([{ x: 1, y: 0, action: 'place', gid: 0, height: 2 }]),
    () => mirror.applyStructures([{ rtoken: 'house', x: 1, y: 0, phase: 'built' }]),
    () => mirror.applyStructures([{ rtoken: 'house', x: 1, y: 0, phase: 'collapsing' }]),
    () => mirror.applyStructures([{ rtoken: 'house', x: 1, y: 0, phase: 'rubble' }]),
    () => mirror.applyStructures([{ rtoken: 'house', op: 'remove' }]),
    () => mirror.applyStructures([], true),
    () => mirror.applyVoxelEdits([], true),
    () => mirror.reset(),
  ];
  for (const [i, change] of changes.entries()) {
    change();
    live.terrain.sync(mirror.map, mirror.structures, mirror.voxelEdits, mirror.terrainVersion);
    const reference = setup(heights, 4, 4, true);
    reference.terrain.redraw(mirror.map, mirror.structures, mirror.voxelEdits);
    expect(live.canvases.find((c) => c.width === 128)!.ctx.pixels(), `mutation ${i}`).toEqual(
      reference.canvases.find((c) => c.width === 128)!.ctx.pixels(),
    );
  }
});

it.each([
  { w: 1, h: 4, heights: [0, 1, 2, 3] },
  { w: 4, h: 1, heights: [3, 2, 1, 0] },
  { w: 3, h: 2, heights: [0, 2, 1, 3, 1, 0] },
])('preserves every edge on a $w by $h map', ({ w, h, heights }) => {
  const live = setup(heights, w, h, true);
  const edits = new Map<
    string,
    { x: number; y: number; action: 'dig' | 'place'; gid: number; height: number }
  >();
  live.terrain.redraw(live.map, live.structures, edits, 0);
  let version = 0;
  for (let index = 0; index < w * h; index++) {
    for (const action of ['dig', 'place'] as const) {
      const x = index % w,
        y = Math.floor(index / w);
      edits.clear();
      edits.set(`${x},${y}`, {
        x,
        y,
        action,
        gid: action === 'dig' ? 1 : 0,
        height: action === 'dig' ? 1 : 2,
      });
      live.terrain.sync(live.map, live.structures, edits, ++version);
      const reference = setup(heights, w, h, true);
      reference.terrain.redraw(reference.map, reference.structures, edits);
      const width = (w + h) * 16;
      expect(live.canvases.find((c) => c.width === width)!.ctx.pixels()).toEqual(
        reference.canvases.find((c) => c.width === width)!.ctx.pixels(),
      );
    }
  }
});
