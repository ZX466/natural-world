import * as THREE from 'three';
import { expect, it } from 'vitest';
import { CAMERA_DIR, HEIGHT_UNIT, followCamera, pixelsPerUnit } from '../three-projection';

const CANVAS_W = 1600;
const CANVAS_H = 900;

/** Screen pixels between two adjacent cell centres, measured through the camera. */
function cellStepPx(camera: THREE.OrthographicCamera, w: number, h: number): number {
  camera.updateMatrixWorld(true);
  const a = new THREE.Vector3(0 - w / 2 + 0.5, 0, 0 - h / 2 + 0.5).project(camera);
  const b = new THREE.Vector3(1 - w / 2 + 0.5, 0, 0 - h / 2 + 0.5).project(camera);
  return Math.abs(b.x - a.x) * (CANVAS_W / 2);
}

it('pixelsPerUnit turns a Phaser cell step into the matching three scale', () => {
  // iso.ts projects one cell step to ISO.TW/2 = 16 px, and the Phaser camera
  // runs at 3.5x, so a cell is 56 screen px wide. Three's +x cell step is
  // 0.7071 world units wide, so the scale is 56 / 0.7071.
  expect(pixelsPerUnit(56)).toBeCloseTo(56 / Math.sqrt(0.5), 6);
  expect(pixelsPerUnit(0)).toBeGreaterThan(0);
});

it('followCamera keeps the target dead centre', () => {
  const camera = followCamera(1600, 900, { x: 12, z: -7 }, 56);
  camera.updateMatrixWorld(true);
  const ndc = new THREE.Vector3(12, 0, -7).project(camera);
  expect(ndc.x).toBeCloseTo(0, 6);
  expect(ndc.y).toBeCloseTo(0, 6);
});

it('followCamera renders one cell at the requested pixel width', () => {
  for (const cellPx of [16, 56, 112]) {
    const camera = followCamera(CANVAS_W, CANVAS_H, { x: 0, z: 0 }, cellPx);
    // A +x cell step is 0.7071 world units; through the camera it must measure
    // exactly `cellPx` screen pixels, which is what makes the block grid line up
    // with the Phaser actors standing on it.
    expect(cellStepPx(camera, 140, 100)).toBeCloseTo(cellPx, 4);
  }
});

it('followCamera keeps the viewport aspect and never zooms out of ortho', () => {
  for (const [w, h] of [
    [1600, 900],
    [900, 1600],
    [400, 400],
  ] as const) {
    const camera = followCamera(w, h, { x: 0, z: 0 }, 56);
    expect((camera.right - camera.left) / (camera.top - camera.bottom)).toBeCloseTo(w / h, 6);
    expect(camera).toBeInstanceOf(THREE.OrthographicCamera);
  }
});

it('HEIGHT_UNIT makes one height level rise exactly one cell run', () => {
  // iso.ts lifts one height level by ISO.HH = 16 logical px, and one cell step
  // is ISO.TW/2 = 16 logical px too — a block is as tall as it is wide. Three's
  // raw +1 world-Y lifts cos(30)/cos(45) = 1.2247 cell runs, so the height axis
  // must be scaled by cos(45)/cos(30) to land on the same pixel.
  expect(HEIGHT_UNIT).toBeCloseTo(
    Math.cos((45 * Math.PI) / 180) / Math.cos((30 * Math.PI) / 180),
    10,
  );

  const camera = followCamera(CANVAS_W, CANVAS_H, { x: 0, z: 0 }, 56);
  camera.updateMatrixWorld(true);
  const px = (v: THREE.Vector3) => {
    const ndc = v.clone().project(camera);
    return { x: (ndc.x * CANVAS_W) / 2, y: (-ndc.y * CANVAS_H) / 2 };
  };
  const ground = px(new THREE.Vector3(0, 0, 0));
  const lifted = px(new THREE.Vector3(0, HEIGHT_UNIT, 0));
  const step = px(new THREE.Vector3(1, 0, 0));
  // Same pixels iso.ts produces: +1 level is 56 px straight up, +1 cell is
  // (56, 28). Any other ratio means the blocks and the actors drift apart.
  expect(lifted.x - ground.x).toBeCloseTo(0, 6);
  expect(ground.y - lifted.y).toBeCloseTo(56, 4);
  expect(Math.abs(step.x - ground.x)).toBeCloseTo(56, 4);
  expect(step.y - ground.y).toBeCloseTo(28, 4);
});

it('followCamera sits on the same camera direction the projection fixed', () => {
  const target = new THREE.Vector3(30, 0, -20);
  const camera = followCamera(CANVAS_W, CANVAS_H, { x: 30, z: -20 }, 56);
  const offset = camera.position.clone().sub(target).normalize();
  expect(offset.x).toBeCloseTo(CAMERA_DIR.x, 6);
  expect(offset.y).toBeCloseTo(CAMERA_DIR.y, 6);
  expect(offset.z).toBeCloseTo(CAMERA_DIR.z, 6);
  // Up stays world-up so the diamond keeps its 2:1 shape rather than rolling.
  expect(camera.up.toArray()).toEqual([0, 1, 0]);
});
