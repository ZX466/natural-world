import * as THREE from 'three';
import { expect, it } from 'vitest';
import { createCamera, defaultOrbit, updateFollowCamera, worldOf } from '../three-projection';

it.each([0, 90, 180, 270])('keeps a target aligned with terrain at azimuth %i', (azimuth) => {
  const camera = createCamera(140, 100, 16 / 9);
  const target = worldOf(100, 53, 140, 100).setY(2.3);
  updateFollowCamera(camera, target, { ...defaultOrbit(), azimuth });
  const ndc = target.clone().project(camera);
  expect(ndc.x).toBeCloseTo(0, 8);
  expect(ndc.y).toBeCloseTo(0, 8);
  const ray = new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2(0, 0), camera);
  const point = ray.ray.intersectPlane(
    new THREE.Plane(new THREE.Vector3(0, 1, 0), -2.3),
    new THREE.Vector3(),
  );
  expect(point?.distanceTo(target)).toBeLessThan(1e-6);
});
