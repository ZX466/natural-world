import type Phaser from 'phaser';
import { readFileSync } from 'node:fs';
import { afterEach, expect, expectTypeOf, it, vi } from 'vitest';
import { IsoTerrain } from '../iso-terrain';
import { createHeightLookup, depthKey, isoProject, screenBounds, type VoxelEdits } from '../iso';
import { WorldMirror, type MapStatic, type VoxelEdit } from '../../world-mirror';

type Point = { x: number; y: number };

/** Lightweight draw-command adapter: no browser/canvas renderer or per-tile spies. */
class View {
  destroyed = false;
  alpha = 1;
  depth = 0;
  x = 0;
  y = 0;
  width = 0;
  height = 0;
  key = '';
  moves = 0;
  clears = 0;
  color = 0;
  fillAlpha = 1;
  faces: { color: number; alpha: number; points: Point[] }[] = [];
  setOrigin() {
    return this;
  }
  setTexture(key?: string) {
    if (typeof key === 'string') this.key = key;
    return this;
  }
  setDisplaySize(width: number, height: number) {
    this.width = width;
    this.height = height;
    return this;
  }
  setTint(color: number) {
    this.color = color;
    return this;
  }
  setDepth(depth: number) {
    this.depth = depth;
    return this;
  }
  setAlpha(alpha: number) {
    this.alpha = alpha;
    return this;
  }
  setPosition(x: number, y: number) {
    this.x = x;
    this.y = y;
    this.moves++;
    return this;
  }
  clear() {
    this.faces = [];
    this.clears++;
    return this;
  }
  fillStyle(color: number, alpha: number) {
    this.color = color;
    this.fillAlpha = alpha;
    return this;
  }
  fillPoints(points: Point[]) {
    this.faces.push({
      color: this.color,
      alpha: this.fillAlpha,
      points: points.map((p) => ({ ...p })),
    });
    return this;
  }
  destroy() {
    this.destroyed = true;
  }
}

function setup(heights = [1, 1, 2, 0], w = 2, h = 2) {
  const images: View[] = [];
  const graphics: View[] = [];
  const textures = new Set<string>();
  const noop = () => {};
  const context = {
    beginPath: noop,
    moveTo: noop,
    lineTo: noop,
    closePath: noop,
    fill: noop,
    clearRect: noop,
    save: noop,
    restore: noop,
    rect: noop,
    clip: noop,
    fillStyle: '',
  };
  vi.stubGlobal('document', {
    createElement: () => ({ width: 0, height: 0, getContext: () => context }),
  });
  const scene = {
    textures: {
      exists: (key: string) => textures.has(key),
      addCanvas: (key: string) => {
        textures.add(key);
        return { refresh: noop };
      },
      remove: (key: string) => textures.delete(key),
    },
    add: {
      graphics: () => {
        const view = new View();
        graphics.push(view);
        return view;
      },
      image: (_x: number, _y: number, key: string) => {
        const view = new View();
        view.key = key;
        images.push(view);
        return view;
      },
    },
  };
  const map: MapStatic = {
    w,
    h,
    tileset: 'grid',
    collision: new Uint8Array(w * h).fill(1),
    ground: new Uint16Array(w * h).fill(7),
  };
  map.collision[0] = 0;
  const structures = new Map<string, { tiles: [number, number][]; phase: string }>();
  const edits = new Map<string, VoxelEdit>();
  const terrain = new IsoTerrain(
    scene as unknown as Phaser.Scene,
    createHeightLookup({ w, h, h_values: heights }),
  );
  const live = () => images.filter((image) => !image.destroyed);
  /** 画成 `h` 高的方块柱侧面（高度 h*16+16，纹理 `iso-block-h`）。 */
  const walls = (h = 2) => live().filter((image) => image.key === `iso-block-${h}`);
  /** 某格那根柱子（侧面 depth = depthKey - 0.01）。按 depth 建索引并在每次
   *  terrain 变更后 `rebuild()`：真实地图 14000 格逐格线性扫 3000+ 图会超时。 */
  const wallIndex = new Map<number, View>();
  const rebuild = () => {
    wallIndex.clear();
    for (const image of live())
      if (image.key.startsWith('iso-block-')) wallIndex.set(image.depth, image);
  };
  const wallAt = (x: number, y: number, h = 2) => {
    const found = wallIndex.get(depthKey(x, y) - 0.01);
    return found?.key === `iso-block-${h}` ? found : undefined;
  };
  /** 挖疤画在 Graphics 上，不是 Image。 */
  const scars = () => graphics.filter((view) => !view.destroyed && view.faces.length > 0);
  return { terrain, map, structures, edits, images, live, walls, wallAt, rebuild, scars, graphics };
}

afterEach(() => vi.unstubAllGlobals());

it('shares one protocol-derived readonly height/action type across geometry and terrain', () => {
  expectTypeOf<VoxelEdits>().toEqualTypeOf<
    ReadonlyMap<string, Pick<VoxelEdit, 'height' | 'action'>>
  >();
  expectTypeOf<NonNullable<Parameters<IsoTerrain['sync']>[2]>>().toEqualTypeOf<VoxelEdits>();
});

it('draws a blocked height-one cell as a two-high block instead of a flat ground tile', () => {
  // 2026-11-10 用户裁定：土坎不再画斜纹，直接抬成 2 格高方块。
  // 逻辑高度仍是 1（碰撞不可走、土坎 1→0 仍是 earth 的唯一来源）。
  const { terrain, map, structures, walls } = setup();
  map.collision[2] = map.collision[3] = 0;
  const collision = map.collision.slice();
  terrain.redraw(map, structures);
  // 视觉抬升绝不改碰撞：世界权威在服务端。
  expect(map.collision).toEqual(collision);
  // (0,0) 是土坎，(1,1) 高度表就是 2 —— 两根 2 格柱。
  expect(walls()).toHaveLength(2);
  const wall = walls().find((image) => Math.abs(image.depth - (depthKey(0, 0) - 0.01)) < 1e-6)!;
  const base = isoProject(0, 0, 0, screenBounds(2, 2));
  // 柱子贴在格底，整根高度 = 2*HH + TH。
  expect(wall).toMatchObject({ x: base.sx, y: base.sy + 8, height: 2 * 16 + 16 });
});

it('removes and recreates the wall when collision alone changes at the same height and color', () => {
  const { terrain, map, structures, walls, wallAt, rebuild } = setup();
  terrain.redraw(map, structures, undefined, 1);
  rebuild();
  const wall = wallAt(0, 0)!;
  expect(wall).toBeDefined();
  map.collision[0] = 1;
  terrain.sync(map, structures, undefined, 2);
  rebuild();
  expect(wall.destroyed).toBe(true);
  expect(wallAt(0, 0)).toBeUndefined();
  map.collision[0] = 0;
  terrain.sync(map, structures, undefined, 3);
  rebuild();
  expect(wallAt(0, 0)).toBeDefined();
  expect(walls().length).toBeGreaterThan(0);
});

it('keeps the dug scar on an opened cell and never on a wall', () => {
  const { terrain, map, structures, edits, scars } = setup();
  edits.set('0,0', { x: 0, y: 0, action: 'dig', gid: 0, height: 1 });
  terrain.redraw(map, structures, edits, 1);
  // 土坎上不画挖疤（疤只给可走面）。
  expect(scars()).toHaveLength(0);
  map.collision[0] = 1;
  edits.set('0,0', { x: 0, y: 0, action: 'dig', gid: 7, height: 1 });
  terrain.sync(map, structures, edits, 2);
  expect(scars()).toHaveLength(1);
  expect(scars()[0]!.faces).toMatchObject([{ color: 0x3f3020, alpha: 0.55 }]);
});

it('drops the wall when digging reaches zero and restores it with an empty snapshot', () => {
  const { terrain, map, structures, wallAt, rebuild } = setup();
  const mirror = new WorldMirror();
  mirror.setMap(map);
  terrain.redraw(map, structures, mirror.voxelEdits, mirror.terrainVersion);
  rebuild();
  expect(wallAt(0, 0)).toBeDefined();
  mirror.applyVoxelEdits([{ x: 0, y: 0, action: 'dig', gid: 0, height: 0 }]);
  terrain.sync(map, structures, mirror.voxelEdits, mirror.terrainVersion);
  rebuild();
  expect(wallAt(0, 0)).toBeUndefined();
  expect(map.collision[0]).toBe(0); // 视觉抬升从不改碰撞。
  mirror.applyVoxelEdits([], true);
  terrain.sync(map, structures, mirror.voxelEdits, mirror.terrainVersion);
  rebuild();
  expect(wallAt(0, 0)).toBeDefined();
});

it('repositions the wall when the map bounds change and clears it on shutdown', () => {
  const { terrain, map, structures, wallAt, rebuild } = setup();
  terrain.redraw(map, structures);
  const replacement = { ...map, w: 1, h: 4 };
  terrain.sync(replacement, structures);
  rebuild();
  const base = isoProject(0, 0, 0, screenBounds(1, 4));
  expect(wallAt(0, 0)).toMatchObject({ x: base.sx, y: base.sy + 8 });
  terrain.sync(null, structures);
  rebuild();
  expect(wallAt(0, 0)).toBeUndefined();
  terrain.redraw(map, structures);
  rebuild();
  expect(wallAt(0, 0)).toBeDefined();
  terrain.destroy();
  rebuild();
  expect(wallAt(0, 0)).toBeUndefined();
});

it('marks every real-map bank, covers both neighborhoods, and does no collision work for 120 idle frames', () => {
  const root = new URL('../../../../../', import.meta.url);
  const source = JSON.parse(readFileSync(new URL('sim/content/linhe-town.json', root), 'utf8')) as {
    width: number;
    height: number;
    chunks: Record<string, { ground: number[]; collision: boolean[] }>;
    _structures?: Record<string, { x: number; y: number; w: number; h: number }>;
  };
  const heights = JSON.parse(
    readFileSync(new URL('client/public/assets/tilesets/linhe-height.json', root), 'utf8'),
  ) as { h_values: number[] };
  const { terrain, map, structures, wallAt, walls, rebuild } = setup(
    heights.h_values,
    source.width,
    source.height,
  );
  // 真实地图 (0,0) 逻辑高度 3 —— 不是土坎，先钉住这个前提。
  expect(heights.h_values[0]).toBe(3);
  // 静态结构锚点必须一起装进来：试车台占地面高度 1、碰撞 0，与土坎同形，
  // 客户端靠 `map.structures` 才不把它们抬成矮墙（那是建筑地基）。
  map.structures = source._structures ?? {};
  for (const [key, chunk] of Object.entries(source.chunks)) {
    const [cx, cy] = key.split(',').map(Number);
    const side = Math.sqrt(chunk.collision.length);
    expect(side).toBe(16);
    for (let i = 0; i < chunk.collision.length; i++) {
      const x = cx! * side + (i % side),
        y = cy! * side + Math.floor(i / side);
      if (x >= map.w || y >= map.h) continue;
      map.collision[y * map.w + x] = Number(chunk.collision[i]);
      map.ground![y * map.w + x] = chunk.ground[i]!;
    }
  }
  const original = map.collision.slice();
  terrain.redraw(map, structures, undefined, 1);
  rebuild();
  let banks = 0,
    walkable = 0,
    adjacent = 0,
    requestedArea = 0,
    currentArea = 0;
  const inStructure = (x: number, y: number) =>
    Object.values(map.structures ?? {}).some(
      (a) => Math.abs(x - a.x) <= Math.floor(a.w / 2) && Math.abs(y - a.y) <= Math.floor(a.h / 2),
    );
  for (let y = 0; y < map.h; y++)
    for (let x = 0; x < map.w; x++) {
      const i = y * map.w + x;
      if (map.collision[i] === 1) walkable++;
      const logical = heights.h_values[i]!;
      const expected = logical === 1 && map.collision[i] === 0 && !inStructure(x, y);
      // 每格画出来的高度：土坎 2，其余照逻辑高度；≥2 的必须真有一根柱子。
      const drawH = expected ? 2 : logical;
      expect(wallAt(x, y, drawH) !== undefined, `${x},${y} h${drawH}`).toBe(drawH >= 2);
      if (!expected) continue;
      banks++;
      if (Math.abs(x - 14) <= 15 && Math.abs(y - 17) <= 15) requestedArea++;
      if (Math.abs(x - 100) <= 15 && Math.abs(y - 53) <= 15) currentArea++;
      if (
        [
          [1, 0],
          [-1, 0],
          [0, 1],
          [0, -1],
        ].some(
          ([dx, dy]) =>
            x + dx! >= 0 &&
            y + dy! >= 0 &&
            x + dx! < map.w &&
            y + dy! < map.h &&
            map.collision[(y + dy!) * map.w + x + dx!] === 1,
        )
      )
        adjacent++;
    }
  // 可走面 3692 = 3947 − 试车台 17×15（255 格）。土坎数不变：那 255 格是
  // **静态结构地基**，不是土坎（`map.structures` 把它们排除在矮墙之外）。
  expect({ banks, walkable, adjacent, requestedArea, currentArea }).toEqual({
    banks: 1568,
    walkable: 3692,
    adjacent: 269,
    requestedArea: 57,
    currentArea: 135,
  });
  expect(map.collision).toEqual(original);
  let reads = 0;
  map.collision = new Proxy(map.collision, {
    get(target, key) {
      if (typeof key === 'string' && /^\d+$/.test(key)) reads++;
      return Reflect.get(target, key, target);
    },
  });
  const snapshot = () =>
    [2, 3].flatMap((h) => walls(h).map((image) => `${image.depth}:${image.moves}`));
  const before = snapshot();
  for (let frame = 0; frame < 120; frame++) terrain.sync(map, structures, undefined, 1);
  expect(reads).toBe(0);
  expect(snapshot()).toEqual(before);
  terrain.sync(map, structures, undefined, 2);
  expect(snapshot()).toEqual(before);
  console.info(
    JSON.stringify({
      banks,
      walkable,
      adjacent,
      requestedArea,
      currentArea,
      idle_frames: 120,
      idle_collision_reads: 0,
      idle_block_moves: 0,
    }),
  );
});
