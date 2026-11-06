/** Bridges the shared cell rule onto the three.js terrain scene.
 *
 * Deliberately thin: `cellAppearances` decides what a cell looks like (shared
 * with the Phaser painter, so the two pictures cannot disagree), and
 * `three-terrain` decides how a block is placed. This file only converts one
 * into the other and keeps the camera glued to the Phaser camera.
 *
 * The Phaser camera remains the authority for *where the player is looking*.
 * The three camera is derived from it every frame, which is what lets
 * `pickVoxel` / `pickGround` keep operating on Phaser screen space untouched —
 * the highest-risk seam in this renderer (three historical picking accidents).
 */

import type { MapStatic, VoxelEdit, WorldMirror } from '../../world-mirror';
import type { HeightLookup } from '../iso';
import { cellAppearances } from '../cell-appearance';
import { alignTarget, updateFollowCamera } from './three-projection';
import { createTerrainScene, type TerrainCell, type TerrainScene } from './three-terrain';

/** ISO.TW: one cell's horizontal screen extent in logical pixels. */
const ISO_TW = 32;

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
    cells[i] = { x: cell.x, y: cell.y, h: cell.h, color: cell.color };
  }
  return cells;
}

export interface TerrainAdapter {
  readonly scene: TerrainScene;
  /** Rebuild block instances if the terrain changed; a no-op otherwise. */
  sync(): void;
  /** Follow the Phaser camera. `centreSx`/`centreSy` are the Phaser camera's
   * visible centre in `screenBounds` space, `zoom` its zoom. */
  syncCamera(centreSx: number, centreSy: number, zoom: number): void;
  /** Set the drawing buffer to CSS pixels × device pixel ratio. */
  resize(width: number, height: number): void;
  dispose(): void;
}

/** One cell step in Phaser iso screen pixels at `zoom`. `ISO.TW / 2` is the
 * horizontal half-cell `isoProject` steps by, so this is the number the three
 * camera must reproduce to line up with the actors. */
export function cellPxAtZoom(zoom: number): number {
  return (ISO_TW / 2) * Math.max(1e-6, zoom);
}

export function createTerrainAdapter(options: TerrainAdapterOptions): TerrainAdapter {
  const { canvas, mirror, heightOf, sampleColor } = options;
  const scene = (options.createScene ?? createTerrainScene)(canvas);
  let lastTerrainVersion = -1;
  let lastMap: MapStatic | null = null;
  let mapW = 1;
  let mapH = 1;
  let cssWidth = 1;
  let cssHeight = 1;

  const sync = (): void => {
    const map = mirror.map;
    if (map === null) return;
    const changedMap = map !== lastMap;
    if (!changedMap && mirror.terrainVersion === lastTerrainVersion) return;
    lastMap = map;
    lastTerrainVersion = mirror.terrainVersion;
    mapW = map.w;
    mapH = map.h;
    scene.setCells(
      terrainCells(map, mirror.structures, mirror.voxelEdits, heightOf, sampleColor),
      map.w,
      map.h,
    );
  };

  const syncCamera = (centreSx: number, centreSy: number, zoom: number): void => {
    if (!Number.isFinite(centreSx) || !Number.isFinite(centreSy)) return;
    if (!Number.isFinite(zoom) || zoom <= 0) return;
    const target = alignTarget(centreSx, centreSy, mapW, mapH);
    updateFollowCamera(scene.camera, cssWidth, cssHeight, target, cellPxAtZoom(zoom));
  };

  const resize = (width: number, height: number): void => {
    if (width <= 0 || height <= 0) return;
    cssWidth = width;
    cssHeight = height;
    scene.renderer.setSize(width, height, false);
  };

  return {
    scene,
    sync,
    syncCamera,
    resize,
    dispose: () => scene.dispose(),
  };
}
