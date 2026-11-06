import * as THREE from 'three';
import { expect, it } from 'vitest';
import { cellOf, createCamera, resizeCamera, worldOf } from '../three-projection';

it('uses perspective so equal objects get smaller with distance', () => {
  const camera = createCamera(140, 100, 16 / 9);
  expect(camera).toBeInstanceOf(THREE.PerspectiveCamera);
  camera.position.set(0, 2, 8);
  camera.lookAt(0, 2, 0);
  camera.updateMatrixWorld(true);
  const near = new THREE.Vector3(1, 2, 0).project(camera).x;
  const far = new THREE.Vector3(1, 2, -8).project(camera).x;
  expect(near).toBeGreaterThan(far * 1.8);
});

it('resizing updates aspect without changing world height or reframing the map', () => {
  const camera = createCamera(140, 100, 1);
  const before = camera.position.clone();
  resizeCamera(camera, 140, 100, 2);
  expect(camera.aspect).toBe(2);
  expect(camera.position.equals(before)).toBe(true);
  expect(camera.projectionMatrix.elements[0]).toBeCloseTo(camera.projectionMatrix.elements[5]! / 2);
});

it('cellOf inverts worldOf without an isometric screen conversion', () => {
  for (let x = 0; x < 140; x += 7)
    for (let y = 0; y < 100; y += 11)
      expect(cellOf(worldOf(x, y, 140, 100), 140, 100)).toEqual({ x, y });
});
