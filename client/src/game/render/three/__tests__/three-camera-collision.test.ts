import * as THREE from 'three';
import { expect, it } from 'vitest';
import { avoidCameraBlocks } from '../three-camera-collision';
import { createCamera, defaultOrbit, updateFollowCamera, worldOf } from '../three-projection';

it('pulls a third-person camera in front of foreground blocks that hide the protagonist', () => {
  const camera = createCamera(5, 5, 1);
  const focus = worldOf(2, 2, 5, 5).setY(2.3);
  updateFollowCamera(camera, focus, { ...defaultOrbit(), azimuth: 0 });
  const before = camera.position.clone();
  avoidCameraBlocks(camera, focus, 1, 5, 5, (x, y) => (x === 2 && y === 3 ? 3 : 1));
  expect(camera.position.distanceTo(before)).toBeGreaterThan(1);
  expect(camera.position.distanceTo(focus)).toBeGreaterThanOrEqual(2.5);
  const feet = new THREE.Vector3(0, 1.12, 0);
  const ray = new THREE.Ray(feet, camera.position.clone().sub(feet).normalize());
  const wall = new THREE.Box3(new THREE.Vector3(-0.5, 0, 0.5), new THREE.Vector3(0.5, 3, 1.5));
  const hit = ray.intersectBox(wall, new THREE.Vector3());
  expect(hit === null || hit.distanceTo(feet) > camera.position.distanceTo(feet)).toBe(true);
  expect(focus.clone().project(camera).x).toBeCloseTo(0);
});

it('keeps the requested orbit when there are no intervening tall blocks', () => {
  const camera = createCamera(30, 30, 1);
  const focus = worldOf(15, 15, 30, 30).setY(2.3);
  updateFollowCamera(camera, focus, defaultOrbit());
  const before = camera.position.clone();
  avoidCameraBlocks(camera, focus, 1, 30, 30, () => 1);
  expect(camera.position.distanceTo(before)).toBeLessThan(1e-8);
});
