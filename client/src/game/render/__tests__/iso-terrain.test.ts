import type Phaser from 'phaser';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createHeightLookup, depthKey, isoProject, screenBounds } from '../iso';
import { IsoTerrain, sampleTileColor } from '../iso-terrain';
import type { MapStatic } from '../../world-mirror';

class Image {
  destroyed = false;
  setOrigin = vi.fn(() => this);
  setDepth = vi.fn(() => this);
  setAlpha = vi.fn(() => this);
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

function setup(heights = [0, 1, 2, 3]) {
  const pixels = new Uint8ClampedArray(16 * 16 * 4);
  for (let i = 0; i < pixels.length; i += 4) pixels.set([100, 150, 200, 255], i);
  const canvases: { width: number; height: number; ctx: ReturnType<typeof context> }[] = [];
  function context() {
    return {
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      fill: vi.fn(),
      fillStyle: '',
      drawImage: vi.fn(),
      getImageData: () => ({ data: pixels }),
    };
  }
  vi.stubGlobal('document', {
    createElement: () => {
      const canvas = { width: 0, height: 0, ctx: context(), getContext: () => canvas.ctx };
      canvases.push(canvas);
      return canvas;
    },
  });
  const textures = new Map<string, unknown>();
  textures.set('god-town-16', { width: 16, height: 16 });
  const images: Image[] = [];
  const scene = {
    textures: {
      exists: (key: string) => textures.has(key),
      get: (key: string) => ({ getSourceImage: () => textures.get(key) }),
      addCanvas: (key: string, canvas: unknown) => {
        textures.set(key, canvas);
      },
      remove: (key: string) => {
        textures.delete(key);
      },
    },
    add: {
      image: (x: number, y: number, key: string) => {
        const image = new Image(x, y, key);
        images.push(image);
        return image;
      },
    },
  };
  const map: MapStatic = {
    w: 2,
    h: 2,
    tileset: 'god-town-16',
    collision: new Uint8Array(4).fill(1),
    ground: new Uint16Array(4).fill(1),
  };
  const structures = new Map<string, { tiles: [number, number][]; phase: string }>();
  const terrain = new IsoTerrain(
    scene as unknown as Phaser.Scene,
    createHeightLookup({ w: 2, h: 2, h_values: heights }),
  );
  return { terrain, map, structures, images, textures, canvases };
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
  expect(textures.has('iso-block-2-6b4f2a')).toBe(true);
  terrain.sync(null, structures);
  expect(images.every((image) => image.destroyed)).toBe(true);
  terrain.redraw(map, structures);
  terrain.destroy();
  expect(images.every((image) => image.destroyed)).toBe(true);
  expect([...textures.keys()]).toEqual(['god-town-16']);
});
