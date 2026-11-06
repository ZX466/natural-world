import * as THREE from 'three';
import { expect, it, vi } from 'vitest';
import type { MapStatic } from '../../../world-mirror';
import { WorldMirror } from '../../../world-mirror';
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
