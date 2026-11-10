import * as THREE from 'three';
import { readFileSync } from 'node:fs';
import { expect, it, vi } from 'vitest';
import type { MapStatic } from '../../../world-mirror';
import { WorldMirror } from '../../../world-mirror';
import { cellAppearances } from '../../cell-appearance';
import { createHeightLookup } from '../../iso';
import { createTerrainAdapter, terrainCells } from '../three-terrain-adapter';
import type { TerrainCell, TerrainScene } from '../three-terrain';

const W = 140;
const H = 100;
const VW = 1600;
const VH = 900;

function map(): MapStatic {
  const n = W * H;
  return {
    w: W,
    h: H,
    tileset: 'god',
    collision: new Uint8Array(n).fill(1),
    ground: new Uint16Array(n).fill(3),
  };
}

function mirrorWith(m: MapStatic = map()): WorldMirror {
  const mirror = new WorldMirror();
  mirror.setMap(m);
  return mirror;
}

/** A stand-in for the WebGL scene: records the instance lists it was given. */
function stubScene() {
  const setCells = vi.fn<(cells: readonly TerrainCell[], w: number, h: number) => void>();
  const scene: TerrainScene = {
    renderer: { setSize: vi.fn(), domElement: { width: VW, height: VH } } as never,
    scene: new THREE.Scene(),
    camera: new THREE.PerspectiveCamera(60, 1, 0.05, 300),
    meshes: [],
    setCells,
    render: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  };
  return { scene, setCells };
}

function adapter(mirror: WorldMirror, heightOf = () => 1) {
  const stub = stubScene();
  const a = createTerrainAdapter({
    canvas: {} as HTMLCanvasElement,
    mirror,
    heightOf,
    sampleColor: (gid) => gid,
    createScene: () => stub.scene,
  });
  return { a, ...stub };
}

it('terrainCells maps the shared rule onto the instance list', () => {
  const mirror = mirrorWith();
  const cells = terrainCells(
    mirror.map!,
    mirror.structures,
    mirror.voxelEdits,
    () => 2,
    (g) => g,
  );
  expect(cells).toHaveLength(W * H);
  expect(cells[0]).toEqual({ x: 0, y: 0, h: 2, color: 3, bank: false });
  // Row-major, same as the Phaser painter's cell array.
  expect(cells[1]!.x).toBe(1);
  expect(cells[W]!.y).toBe(1);
});

it('sync rebuilds instances once per terrain revision', () => {
  const mirror = mirrorWith();
  const { a, setCells } = adapter(mirror);
  a.sync();
  expect(setCells).toHaveBeenCalledTimes(1);
  // Nothing changed: the terrain version is the same, so no rebuild.
  a.sync();
  a.sync();
  expect(setCells).toHaveBeenCalledTimes(1);

  // A voxel edit bumps terrainVersion and must reach the scene.
  mirror.applyVoxelEdits([{ x: 5, y: 6, gid: 3, height: 2, action: 'place' }]);
  a.sync();
  expect(setCells).toHaveBeenCalledTimes(2);
  const cells = setCells.mock.calls[1]![0];
  expect(cells[6 * W + 5]!.h).toBe(2);
});

it('a placed earth block reaches the scene marked as a bank', () => {
  // 放土后那格是「高度 1、不可走」，与可走平地同高同色（实测色差 2/255）。
  // 不带 bank 标记，three 里它看起来就是一块空地 —— 用户报的「放置是空白」。
  const mirror = mirrorWith();
  const { a, setCells } = adapter(mirror);
  a.sync();
  mirror.applyVoxelEdits([{ x: 5, y: 6, gid: 0, height: 1, action: 'place', material: 'earth' }]);
  a.sync();
  const cells = setCells.mock.calls.at(-1)![0];
  expect(cells[6 * W + 5]).toMatchObject({ h: 1, bank: true });
  // 没动过的可走格不能被误标成土坎。
  expect(cells[6 * W + 4]!.bank).toBe(false);
});

it('the real map marks every blocked height-one cell, and only those, as a bank', () => {
  // 这条是两条渲染路径的合同：Phaser 的斜纹字形与 three 的斜杠必须覆盖
  // **同一批格子**，否则同一座镇子在两个渲染器里读法不同。
  // 试车台地基（静态结构，高度 1、碰撞 0）不算土坎 —— 那是建筑占地面。
  // 本文件比 `render/__tests__/iso-banks.test.ts` 深一层（多一个 `three/`）。
  const root = new URL('../../../../../../', import.meta.url);
  const source = JSON.parse(readFileSync(new URL('sim/content/linhe-town.json', root), 'utf8')) as {
    width: number;
    height: number;
    chunks: Record<string, { ground: number[]; collision: boolean[] }>;
    _structures?: Record<string, { x: number; y: number; w: number; h: number }>;
  };
  const heights = JSON.parse(
    readFileSync(new URL('client/public/assets/tilesets/linhe-height.json', root), 'utf8'),
  ) as { h_values: number[] };
  const map: MapStatic = {
    w: source.width,
    h: source.height,
    tileset: 'god',
    collision: new Uint8Array(source.width * source.height),
    ground: new Uint16Array(source.width * source.height),
    structures: source._structures ?? {},
  };
  for (const [key, chunk] of Object.entries(source.chunks)) {
    const [cx, cy] = key.split(',').map(Number);
    for (let i = 0; i < chunk.collision.length; i++) {
      const x = cx! * 16 + (i % 16),
        y = cy! * 16 + Math.floor(i / 16);
      if (x >= map.w || y >= map.h) continue;
      map.collision[y * map.w + x] = Number(chunk.collision[i]);
      map.ground![y * map.w + x] = chunk.ground[i]!;
    }
  }
  const cells = terrainCells(map, new Map(), new Map(), createHeightLookup(heights), (gid) => gid);
  const inStructure = (x: number, y: number) =>
    Object.values(map.structures ?? {}).some(
      (a) => Math.abs(x - a.x) <= Math.floor(a.w / 2) && Math.abs(y - a.y) <= Math.floor(a.h / 2),
    );
  let banks = 0;
  for (const cell of cells) {
    const expected =
      heights.h_values[cell.y * map.w + cell.x] === 1 &&
      map.collision[cell.y * map.w + cell.x] === 0 &&
      !inStructure(cell.x, cell.y);
    expect(cell.bank, `${cell.x},${cell.y}`).toBe(expected);
    if (expected) banks += 1;
  }
  // 与 Phaser 路径的 `iso-banks.test.ts` 同一个数：1568。
  expect(banks).toBe(1568);
  // 两份渲染规则必须一致，而不是各算一套。
  const appearance = cellAppearances(
    map,
    new Map(),
    new Map(),
    createHeightLookup(heights),
    (g) => g,
  );
  expect(cells.map((c) => c.bank)).toEqual(appearance.map((c) => c.bank));
});

it('sync does nothing without a map', () => {
  const mirror = new WorldMirror();
  const { a, setCells } = adapter(mirror);
  a.sync();
  expect(setCells).not.toHaveBeenCalled();
});

it('a fresh map object forces a rebuild even at the same version', () => {
  const mirror = mirrorWith();
  const { a, setCells } = adapter(mirror);
  a.sync();
  mirror.setMap(map());
  a.sync();
  expect(setCells).toHaveBeenCalledTimes(2);
});

it('follows a world target and lets orbit change the camera independently', () => {
  const { a, scene } = adapter(mirrorWith());
  a.follow(new THREE.Vector3(10, 2.3, 20));
  const before = scene.camera.position.clone();
  a.rotate(100, -20);
  expect(scene.camera.position.distanceTo(before)).toBeGreaterThan(1);
  expect(a.orbitPose.azimuth).not.toBe(45);
  a.zoom(200);
  expect(a.orbitPose.distance).toBeGreaterThan(8);
});

it('resize ignores a collapsed container and updates aspect using CSS dimensions', () => {
  const { a, scene } = adapter(mirrorWith());
  a.resize(0, 500);
  expect(scene.renderer.setSize).not.toHaveBeenCalled();
  a.resize(800, 600);
  expect(scene.renderer.setSize).toHaveBeenCalledWith(800, 600, false);
  expect(scene.resize).toHaveBeenCalledWith(800 / 600);
});
