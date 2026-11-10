import type { MapStatic, VoxelEdit, WorldMirror } from '../../world-mirror';
import * as THREE from 'three';
import type { HeightLookup } from '../iso';
import { cellAppearances } from '../cell-appearance';
import {
  defaultOrbit,
  orbitBy,
  zoomBy,
  updateFollowCamera,
  type OrbitPose,
} from './three-projection';
import { createTerrainScene, type TerrainCell, type TerrainScene } from './three-terrain';

export interface TerrainAdapterOptions {
  readonly canvas: HTMLCanvasElement;
  readonly mirror: WorldMirror;
  readonly heightOf: HeightLookup;
  /** gid → 0xRRGGBB, sharing the sampler the Phaser painter uses so one
   * tileset fetch serves both. */
  readonly sampleColor: (gid: number) => number;
  /** Scene factory. Production uses the real one; tests inject a stub so the
   * adapter's dirty-check and camera glue can be exercised without WebGL. */
  readonly createScene?: (canvas: HTMLCanvasElement) => TerrainScene;
}

/** The shared cell rule → the flat instance list the terrain scene consumes. */
export function terrainCells(
  map: MapStatic,
  structures: Parameters<typeof cellAppearances>[1],
  edits: ReadonlyMap<string, VoxelEdit>,
  heightOf: HeightLookup,
  sampleColor: (gid: number) => number,
): TerrainCell[] {
  const appearance = cellAppearances(map, structures, edits, heightOf, sampleColor);
  const cells: TerrainCell[] = new Array(appearance.length);
  for (let i = 0; i < appearance.length; i++) {
    const cell = appearance[i]!;
    // `drawH` 而不是 `h`：土坎（逻辑高度 1、不可走）要画成 2 格高的矮墙，
    // 否则它和可走平地同高同色 —— 天然土坎像能走的空地，放下的土块像空白。
    cells[i] = { x: cell.x, y: cell.y, h: cell.drawH, color: cell.color };
  }
  return cells;
}

export interface TerrainAdapter {
  readonly scene: TerrainScene;
  readonly heightOf: HeightLookup;
  readonly orbitPose: OrbitPose;
  sync(): void;
  follow(target: THREE.Vector3): void;
  rotate(dx: number, dy: number): void;
  zoom(delta: number): void;
  resize(width: number, height: number): void;
  dispose(): void;
}

export function createTerrainAdapter(options: TerrainAdapterOptions): TerrainAdapter {
  const { canvas, mirror, heightOf, sampleColor } = options;
  const scene = (options.createScene ?? createTerrainScene)(canvas);
  let lastTerrainVersion = -1;
  let lastMap: MapStatic | null = null;
  let pose = defaultOrbit();
  const target = new THREE.Vector3(0, 2.3, 0);

  const sync = (): void => {
    const map = mirror.map;
    if (map === null) return;
    const changedMap = map !== lastMap;
    if (!changedMap && mirror.terrainVersion === lastTerrainVersion) return;
    lastMap = map;
    lastTerrainVersion = mirror.terrainVersion;
    scene.setCells(
      terrainCells(map, mirror.structures, mirror.voxelEdits, heightOf, sampleColor),
      map.w,
      map.h,
    );
  };

  const follow = (point: THREE.Vector3): void => {
    target.copy(point);
    updateFollowCamera(scene.camera, target, pose);
  };
  const rotate = (dx: number, dy: number): void => {
    pose = orbitBy(pose, dx, dy);
    updateFollowCamera(scene.camera, target, pose);
  };
  const zoom = (delta: number): void => {
    pose = zoomBy(pose, delta);
    updateFollowCamera(scene.camera, target, pose);
  };

  const resize = (width: number, height: number): void => {
    if (width <= 0 || height <= 0) return;
    scene.renderer.setSize(width, height, false);
    scene.resize(width / height);
  };

  return {
    scene,
    sync,
    heightOf,
    get orbitPose() {
      return pose;
    },
    follow,
    rotate,
    zoom,
    resize,
    dispose: () => scene.dispose(),
  };
}
