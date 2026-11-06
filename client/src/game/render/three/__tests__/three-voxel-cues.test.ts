import * as THREE from 'three';
import { expect, it } from 'vitest';
import { WorldMirror } from '../../../world-mirror';
import { createVoxelCues } from '../three-voxel-cues';

function setup() {
  const mirror = new WorldMirror();
  const collision = new Uint8Array(25).fill(1);
  collision[7] = 0;
  mirror.setMap({ w: 5, h: 5, tileset: 'grid', collision });
  const scene = new THREE.Scene(),
    camera = new THREE.PerspectiveCamera();
  camera.updateMatrixWorld(true);
  const cues = createVoxelCues(scene, mirror, (x, y) => (x === 2 && y === 1 ? 3 : 1));
  return { scene, camera, mirror, cues };
}

it('fits the selected outline to a whole column and does not preview placement in a blocked cell', () => {
  const { cues, camera } = setup();
  cues.update({ x: 2, y: 1 }, null, 'stone', { earth: 0, stone: 1 }, camera);
  expect(cues.selection.visible).toBe(true);
  expect(cues.selection.position.toArray()).toEqual([0, 1.5, -1]);
  expect(cues.selection.scale.y).toBeCloseTo(3.02);
  expect(cues.selection.material.depthTest).toBe(false);
  expect(cues.selection.renderOrder).toBeGreaterThan(0);
  expect(cues.preview.visible).toBe(false);
});

it.each([
  ['earth', 1],
  ['stone', 2],
  ['wood', 3],
] as const)('previews %s at its actual blocking placement height', (material, height) => {
  const { cues, camera } = setup();
  cues.update({ x: 1, y: 2 }, null, material, { earth: 1, stone: 1, wood: 1 }, camera);
  expect(cues.preview.visible).toBe(true);
  expect(cues.preview.position.toArray()).toEqual([-1, height / 2, 0]);
  expect(cues.preview.scale.y).toBe(height);
  expect(cues.blockingCross.position.y).toBeCloseTo(height + 0.03);
  cues.update({ x: 1, y: 2 }, null, material, { earth: 0, stone: 0, wood: 0 }, camera);
  expect(cues.preview.visible).toBe(false);
});

it('anchors progress and destination in world space and clears stale cues on snapshots', () => {
  const { cues, mirror, camera, scene } = setup();
  mirror.applyVoxelState({ dig: { x: 2, y: 1, progress: 0.5 }, inventory: { earth: 0 } });
  cues.update(null, { x: 3, y: 2 }, 'earth', { earth: 0 }, camera);
  expect(cues.progress.fill.visible).toBe(true);
  expect(cues.progress.fill.scale.x).toBeCloseTo(0.5);
  expect(cues.progress.fill.position.y).toBeCloseTo(3.18);
  expect(cues.goalMarker.position.toArray()).toEqual([1, 1.03, 0]);
  mirror.applyVoxelEdits([], true);
  cues.update({ x: 2, y: 1 }, { x: 3, y: 2 }, 'earth', { earth: 0 }, camera);
  expect(cues.selection.visible).toBe(false);
  expect(cues.goalMarker.visible).toBe(false);
  expect(cues.progress.fill.visible).toBe(false);
  cues.dispose();
  expect(scene.children).toHaveLength(0);
});
