import * as THREE from 'three';
import { expect, it, vi } from 'vitest';
import type { MapStatic } from '../../../world-mirror';
import { WorldMirror } from '../../../world-mirror';
import { ISO, isoProject, screenBounds } from '../../iso';
import { HEIGHT_UNIT, alignTarget } from '../three-projection';
import { cellPxAtZoom, createTerrainAdapter, terrainCells } from '../three-terrain-adapter';
import type { TerrainCell, TerrainScene } from '../three-terrain';

const W = 140;
const H = 100;
const ZOOM = 3.5;
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
    camera: new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 4000),
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

it('cellPxAtZoom matches isoProject’s half-cell at the Phaser zoom', () => {
  // iso.ts steps half a cell horizontally (ISO.TW / 2 = 16 logical px).
  expect(cellPxAtZoom(3.5)).toBe(16 * 3.5);
  expect(cellPxAtZoom(1)).toBe(16);
  // A zero or negative zoom must not produce a zero-width frustum.
  expect(cellPxAtZoom(0)).toBeGreaterThan(0);
  expect(cellPxAtZoom(-2)).toBeGreaterThan(0);
});

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
  expect(cells[0]).toEqual({ x: 0, y: 0, h: 2, color: 3 });
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

it('syncCamera centres the three camera on the Phaser camera’s cell', () => {
  const mirror = mirrorWith();
  const { a, scene } = adapter(mirror);
  a.sync();
  a.resize(VW, VH);

  const bounds = screenBounds(W, H);
  const cell = isoProject(70, 50, 0, bounds);
  a.syncCamera(cell.sx, cell.sy, ZOOM);

  // The followed cell's centre must project to the canvas centre, which is the
  // condition for pickVoxel/pickGround to stay valid on Phaser screen space.
  scene.camera.updateMatrixWorld(true);
  const centre = new THREE.Vector3(70 - W / 2 + 0.5, 0, 50 - H / 2 + 0.5);
  const ndc = centre.clone().project(scene.camera);
  expect(ndc.x).toBeCloseTo(0, 5);
  expect(ndc.y).toBeCloseTo(0, 5);
});

it('syncCamera reproduces isoProject’s cell step in screen pixels', () => {
  const mirror = mirrorWith();
  const { a, scene } = adapter(mirror);
  a.sync();
  a.resize(VW, VH);
  const bounds = screenBounds(W, H);
  a.syncCamera(isoProject(70, 50, 0, bounds).sx, isoProject(70, 50, 0, bounds).sy, ZOOM);

  const px = (v: THREE.Vector3) => {
    scene.camera.updateMatrixWorld(true);
    const ndc = v.clone().project(scene.camera);
    return { x: (ndc.x * VW) / 2, y: (-ndc.y * VH) / 2 };
  };
  const a0 = px(new THREE.Vector3(70 - W / 2 + 0.5, 0, 50 - H / 2 + 0.5));
  const b = px(new THREE.Vector3(71 - W / 2 + 0.5, 0, 50 - H / 2 + 0.5));
  // +x cell: right by ISO.TW/2*zoom, down by ISO.TH/2*zoom — the 2:1 diamond.
  expect(b.x - a0.x).toBeCloseTo((ISO.TW / 2) * ZOOM, 3);
  expect(b.y - a0.y).toBeCloseTo((ISO.TH / 2) * ZOOM, 3);
});

it('syncCamera ignores non-finite or non-positive input', () => {
  const mirror = mirrorWith();
  const { a, scene } = adapter(mirror);
  a.sync();
  a.resize(VW, VH);
  const before = scene.camera.position.clone();
  a.syncCamera(Number.NaN, 10, ZOOM);
  a.syncCamera(10, Infinity, ZOOM);
  a.syncCamera(10, 10, 0);
  a.syncCamera(10, 10, -1);
  expect(scene.camera.position.equals(before)).toBe(true);
});

it('resize ignores a collapsed container and forwards the CSS size', () => {
  const mirror = mirrorWith();
  const { a, scene } = adapter(mirror);
  const setSize = scene.renderer.setSize as unknown as ReturnType<typeof vi.fn>;
  a.resize(0, 500);
  a.resize(500, 0);
  expect(setSize).not.toHaveBeenCalled();
  a.resize(800, 600);
  expect(setSize).toHaveBeenCalledWith(800, 600, false);
});

it('alignTarget keeps the block and actor frames on one origin', () => {
  // A guard on the exact expression the adapter uses: alignTarget must land on
  // worldOf's cell centre, or the blocks sit half a cell off the actors.
  const bounds = screenBounds(W, H);
  for (const [x, y] of [
    [0, 0],
    [70, 50],
    [139, 99],
  ] as const) {
    const p = isoProject(x, y, 0, bounds);
    const t = alignTarget(p.sx, p.sy, W, H);
    expect(t.x).toBeCloseTo(x - W / 2 + 0.5, 9);
    expect(t.z).toBeCloseTo(y - H / 2 + 0.5, 9);
  }
  // Height is the block transform's job, not the camera's.
  expect(HEIGHT_UNIT).toBeLessThan(1);
});
