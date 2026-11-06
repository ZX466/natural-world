/** The projection contract shared by the three.js camera and its picking.
 *
 * One map cell is **one world unit** wide (1×1 in the XZ plane), and the map
 * is centred on the world origin. The camera is orthographic at azimuth 45°
 * and elevation 30°, which is exactly the pixel-art 2:1 isometric ratio:
 *
 *   map +x step  →  right 0.7071, down 0.3536  (world-screen units)
 *   map +y step  →  left  0.7071, down 0.3536
 *   +1 height    →  up    0.8660
 *
 * The drop/horizontal ratio is sin(30°) = 0.5, so a square cell projects to a
 * 2:1 diamond — the same diamond `iso.ts` draws. Pixels per world unit depend
 * on the viewport (the camera fits the whole map), so every assertion here
 * works in world-screen units and never in pixels.
 *
 * Picking does not invert this by hand: three's `Raycaster` against the
 * instanced meshes is the authority, so the two cannot drift apart.
 */

import * as THREE from 'three';
import { ISO, screenBounds } from '../iso';

export const AZIMUTH_DEG = 45;
export const ELEVATION_DEG = 30;

/** Unit vector from the scene origin toward the camera. */
export const CAMERA_DIR = new THREE.Vector3(
  Math.cos((ELEVATION_DEG * Math.PI) / 180) * Math.sin((AZIMUTH_DEG * Math.PI) / 180),
  Math.sin((ELEVATION_DEG * Math.PI) / 180),
  Math.cos((ELEVATION_DEG * Math.PI) / 180) * Math.cos((AZIMUTH_DEG * Math.PI) / 180),
);

/** Map cell → world position of the cell's **bottom centre**. */
export function worldOf(x: number, y: number, w: number, h: number): THREE.Vector3 {
  return new THREE.Vector3(x - w / 2 + 0.5, 0, y - h / 2 + 0.5);
}

/** World → map cell, for points already known to be on the ground plane.
 * This is the analytic inverse used by tests; runtime picking uses the raycaster. */
export function cellOf(point: THREE.Vector3, w: number, h: number): { x: number; y: number } {
  return {
    x: Math.round(point.x + w / 2 - 0.5),
    y: Math.round(point.z + h / 2 - 0.5),
  };
}

/** The camera every renderer and picker shares. `distance` only has to clear
 * the scene; the projection is orthographic, so it never changes scale. */
export function createCamera(w: number, h: number, aspect: number): THREE.OrthographicCamera {
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 4000);
  camera.position.copy(CAMERA_DIR).multiplyScalar(800);
  camera.up.set(0, 1, 0);
  camera.lookAt(0, 0, 0);
  // lookAt writes the rotation; without this the matrixWorld stays identity and
  // every projection silently reads as an unrotated top-down view.
  camera.updateMatrixWorld(true);
  resizeCamera(camera, w, h, aspect);
  return camera;
}

/** World-Y that renders as exactly one height level on screen.
 *
 * `iso.ts` lifts one level by `ISO.HH` and steps one cell by `ISO.TW / 2`, and
 * those are equal — a block is as tall as it is wide. Under the 45°/30° basis a
 * raw +1 world-Y lifts `cos(30°) / cos(45°) = 1.2247` cell runs, so the height
 * axis has to be scaled down by the reciprocal. Getting this wrong makes every
 * stacked block a third taller than the actors standing on it. */
export const HEIGHT_UNIT =
  Math.cos((AZIMUTH_DEG * Math.PI) / 180) / Math.cos((ELEVATION_DEG * Math.PI) / 180);

/** Screen pixels per world unit, given the screen-pixel width of one map cell.
 *
 * Under the 45°/30° basis a +x cell step is `cos(45°) = 0.7071` world units wide
 * on screen, so a cell that must measure `cellPx` pixels sets the scale. The
 * Phaser iso camera supplies the number: `ISO.TW / 2 * PIXEL_SCALE` = 16 × 3.5.
 *
 * This is the single number that makes the two canvases agree — actors stand on
 * blocks only if both renderers use the same pixels-per-unit. */
export function pixelsPerUnit(cellPx: number): number {
  return Math.max(1e-6, cellPx) / Math.cos((AZIMUTH_DEG * Math.PI) / 180);
}

/** Phaser screen pixels → the world-space ground point the three camera must
 * centre on.
 *
 * `isoProject` is top-left origin and puts a cell's **top face** at `sy`, so a
 * cell at height `h` sits `h * ISO.HH` above its ground point. The three camera
 * works in a canvas-centred frame, so both offsets are undone here.
 *
 * This is the bridge that lets `pickVoxel` / `pickGround` stay byte-identical:
 * they unproject in Phaser screen space, which is only valid while both canvases
 * agree pixel-for-pixel. Three picking accidents already came from this seam.
 *
 * The Phaser camera must be centred on the same point at the same zoom
 * (`ISO.TW / 2 * PIXEL_SCALE` px per cell) for the alignment to hold. */
export function alignTarget(
  phaserSx: number,
  phaserSy: number,
  mapW: number,
  mapH: number,
): { readonly x: number; readonly z: number } {
  // Screen x encodes (x - y) and screen y encodes (x + y), so a translation is
  // not enough: both axes have to be solved together, which is exactly what
  // `isoUnproject` does for the ground plane. Continuous here (no rounding),
  // because the camera may centre between cells while an actor is sliding.
  const bounds = screenBounds(mapW, mapH);
  const dx = (phaserSx - bounds.originX) / (ISO.TW / 2);
  const dy = (phaserSy - bounds.originY) / (ISO.TH / 2);
  return {
    x: (dx + dy) / 2 - mapW / 2 + 0.5,
    z: (dy - dx) / 2 - mapH / 2 + 0.5,
  };
}

/** A camera that follows a world-space target at a fixed zoom, for the live
 * gameplay view (as opposed to `createCamera`, which frames the whole map).
 *
 * `target` is a point on the **ground plane** (y = 0). The camera sits
 * `CAMERA_DIR` away from it, so the diamond keeps the exact 2:1 shape that
 * `worldOf` and the raycaster assume, and the viewport aspect is honoured
 * without ever changing the zoom. */
export function followCamera(
  viewportW: number,
  viewportH: number,
  target: { readonly x: number; readonly z: number },
  cellPx: number,
): THREE.OrthographicCamera {
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 4000);
  camera.up.set(0, 1, 0);
  updateFollowCamera(camera, viewportW, viewportH, target, cellPx);
  return camera;
}

/** Move an existing camera to `target`. Same contract as `followCamera`, but
 * reusable, so the per-frame follow path allocates nothing. */
export function updateFollowCamera(
  camera: THREE.OrthographicCamera,
  viewportW: number,
  viewportH: number,
  target: { readonly x: number; readonly z: number },
  cellPx: number,
): void {
  const ppu = pixelsPerUnit(cellPx);
  const halfW = Math.max(1, viewportW) / 2 / ppu;
  const halfH = Math.max(1, viewportH) / 2 / ppu;

  camera.left = -halfW;
  camera.right = halfW;
  camera.top = halfH;
  camera.bottom = -halfH;
  camera.updateProjectionMatrix();

  camera.position.set(
    target.x + CAMERA_DIR.x * 800,
    CAMERA_DIR.y * 800,
    target.z + CAMERA_DIR.z * 800,
  );
  camera.lookAt(target.x, 0, target.z);
  // lookAt writes the rotation; the matrixWorldInverse read by project() and by
  // the raycaster is only refreshed here.
  camera.updateMatrixWorld(true);
}

/** Fit the whole map plus head-room for the tallest column, then widen the
 * tighter axis so the viewport aspect matches. */
export function resizeCamera(
  camera: THREE.OrthographicCamera,
  w: number,
  h: number,
  aspect: number,
): void {
  // Screen extent of the map in world-screen units (before any pixel scaling).
  const halfDiag = (w + h) / 2;
  const worldW = halfDiag * 2 * Math.cos((AZIMUTH_DEG * Math.PI) / 180);
  const worldH = halfDiag * 2 * Math.sin((ELEVATION_DEG * Math.PI) / 180) + 4 * 0.866;
  let halfW = worldW / 2 + 2;
  let halfH = worldH / 2 + 2;
  if (aspect > halfW / halfH) halfW = halfH * aspect;
  else halfH = halfW / aspect;
  camera.left = -halfW;
  camera.right = halfW;
  camera.top = halfH;
  camera.bottom = -halfH;
  camera.updateProjectionMatrix();
}
