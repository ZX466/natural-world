import * as THREE from 'three';
import { expect, it } from 'vitest';
import {
  createCamera,
  defaultOrbit,
  orbitBy,
  updateFollowCamera,
  zoomBy,
} from '../three-projection';

it('follows a world-space protagonist and preserves the selected orbit while moving', () => {
  const camera = createCamera(140, 100, 16 / 9);
  const pose = orbitBy(defaultOrbit(), 120, -15);
  const first = new THREE.Vector3(10, 2.3, 20);
  updateFollowCamera(camera, first, pose);
  const relative = camera.position.clone().sub(first);
  const second = first.clone().add(new THREE.Vector3(4, 0, -3));
  updateFollowCamera(camera, second, pose);
  expect(camera.position.clone().sub(second).distanceTo(relative)).toBeLessThan(1e-8);
  expect(second.clone().project(camera).length()).toBeLessThan(1);
});

it('bounds orbit pitch and zoom, and ignores nonfinite pointer input', () => {
  const pose = defaultOrbit();
  const raised = orbitBy(pose, 0, -10_000);
  const lowered = orbitBy(pose, 0, 10_000);
  expect(raised.elevation).toBeLessThanOrEqual(80);
  expect(lowered.elevation).toBeGreaterThanOrEqual(3);
  expect(zoomBy(pose, 10_000).distance).toBeLessThanOrEqual(24);
  expect(zoomBy(pose, -10_000).distance).toBeGreaterThanOrEqual(3);
  expect(orbitBy(pose, NaN, 0)).toEqual(pose);
  expect(zoomBy(pose, Infinity)).toEqual(pose);
});
