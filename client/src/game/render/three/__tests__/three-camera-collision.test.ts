import * as THREE from 'three';
import { expect, it } from 'vitest';
import { avoidCameraBlocks, cameraAzimuth } from '../three-camera-collision';
import { createCamera, defaultOrbit, updateFollowCamera, worldOf } from '../three-projection';

it('pulls a third-person camera in front of foreground blocks that hide the protagonist', () => {
  const camera = createCamera(5, 5, 1);
  const focus = worldOf(2, 2, 5, 5).setY(2.3);
  updateFollowCamera(camera, focus, { ...defaultOrbit(), azimuth: 0 });
  const before = camera.position.clone();
  avoidCameraBlocks(camera, focus, 1, 5, 5, (x, y) => (x === 2 && y === 3 ? 3 : 1));
  expect(camera.position.distanceTo(before)).toBeGreaterThan(1);
  expect(camera.position.distanceTo(focus)).toBeGreaterThanOrEqual(2.5);
  const offset = camera.position.clone().sub(focus);
  expect(THREE.MathUtils.radToDeg(Math.asin(offset.y / offset.length()))).toBeLessThanOrEqual(
    35 + 1e-8,
  );
  expect(Math.abs(offset.x)).toBeGreaterThan(1);
  expect(cameraAzimuth(camera)).toBeCloseTo(
    THREE.MathUtils.radToDeg(Math.atan2(offset.x, offset.z)),
  );
  const feet = new THREE.Vector3(0, 1.12, 0);
  const ray = new THREE.Ray(feet, camera.position.clone().sub(feet).normalize());
  const wall = new THREE.Box3(new THREE.Vector3(-0.5, 0, 0.5), new THREE.Vector3(0.5, 3, 1.5));
  const hit = ray.intersectBox(wall, new THREE.Vector3());
  expect(hit === null || hit.distanceTo(feet) > camera.position.distanceTo(feet)).toBe(true);
  expect(focus.clone().project(camera).x).toBeCloseTo(0);
});

it('keeps a low camera safely inside an enclosure when no full orbit is clear', () => {
  const camera = createCamera(7, 7, 1);
  const focus = worldOf(3, 3, 7, 7).setY(2.3);
  updateFollowCamera(camera, focus, { ...defaultOrbit(), azimuth: 0 });
  avoidCameraBlocks(camera, focus, 1, 7, 7, (x, y) =>
    x >= 2 && x <= 4 && y >= 2 && y <= 4 && (x !== 3 || y !== 3) ? 4 : 1,
  );
  const offset = camera.position.clone().sub(focus);
  expect(THREE.MathUtils.radToDeg(Math.asin(offset.y / offset.length()))).toBeLessThanOrEqual(
    35 + 1e-8,
  );
  expect(Math.abs(camera.position.x)).toBeLessThan(0.5);
  expect(Math.abs(camera.position.z)).toBeLessThan(0.5);
  expect(offset.length()).toBeGreaterThan(0);
});

it('keeps the requested orbit when there are no intervening tall blocks', () => {
  const camera = createCamera(30, 30, 1);
  const focus = worldOf(15, 15, 30, 30).setY(2.3);
  updateFollowCamera(camera, focus, defaultOrbit());
  const before = camera.position.clone();
  avoidCameraBlocks(camera, focus, 1, 30, 30, () => 1);
  expect(camera.position.distanceTo(before)).toBeLessThan(1e-8);
});

it('keeps the camera clear when interpolated feet start inside a wall clearance margin', () => {
  const camera = createCamera(7, 50, 1);
  const focus = worldOf(3, 25, 7, 50).setY(2.3);
  focus.x += 0.49; // Feet remain outside the wall, but inside its safety margin.
  updateFollowCamera(camera, focus, { ...defaultOrbit(), azimuth: 90 });
  avoidCameraBlocks(camera, focus, 1, 7, 50, (x) => (x === 4 ? 4 : 1));
  const wall = new THREE.Box3(new THREE.Vector3(0.38, 0, -25), new THREE.Vector3(1.62, 4.12, 25));
  expect(wall.containsPoint(camera.position)).toBe(false);
  const feet = focus.clone().setY(1.12);
  const ray = new THREE.Ray(feet, camera.position.clone().sub(feet).normalize());
  const solidWall = new THREE.Box3(new THREE.Vector3(0.5, 0, -25), new THREE.Vector3(1.5, 4, 25));
  const hit = ray.intersectBox(solidWall, new THREE.Vector3());
  expect(hit === null || hit.distanceTo(feet) > camera.position.distanceTo(feet)).toBe(true);
});

it('lets a requested orbit escape padding without turning back into the wall', () => {
  // 方位角 90°：脚点已在墙的 padding 里，相机在墙的另一侧，射线真的穿过实心柱。
  // 旧实现在这里把相机裁到 (0.65, 2.33, 0) —— 落在柱体内部（`intersectBox` 返回的是
  // 出口，不是入口）。默认 225° 时射线根本碰不到这堵墙，新旧都会「通过」，
  // 那条断言是空转的，别改回去。
  const camera = createCamera(7, 7, 1);
  const focus = worldOf(3, 3, 7, 7).setY(2.3);
  focus.x += 0.49;
  updateFollowCamera(camera, focus, { ...defaultOrbit(), azimuth: 90 });
  const before = camera.position.clone();
  avoidCameraBlocks(camera, focus, 1, 7, 7, (x, y) => (x === 4 && y === 3 ? 3 : 1));
  expect(camera.position.distanceTo(before)).toBeGreaterThan(1);
  const wall = new THREE.Box3(new THREE.Vector3(0.5, 0, -0.5), new THREE.Vector3(1.5, 3, 0.5));
  expect(wall.containsPoint(camera.position)).toBe(false);
  const feet = focus.clone().setY(1.12);
  const ray = new THREE.Ray(feet, camera.position.clone().sub(feet).normalize());
  const hit = ray.intersectBox(wall, new THREE.Vector3());
  expect(hit === null || hit.distanceTo(feet) > camera.position.distanceTo(feet)).toBe(true);
});

it('keeps wall, corner and enclosed orbits out of solid columns across sub-tile positions', () => {
  const patterns = [
    [[5, 4]],
    [
      [5, 4],
      [4, 5],
      [5, 5],
    ],
    [
      [3, 3],
      [4, 3],
      [5, 3],
      [3, 4],
      [5, 4],
      [3, 5],
      [4, 5],
      [5, 5],
    ],
  ];
  for (const walls of patterns) {
    const boxes = walls.map(([x, y]) => {
      const centre = worldOf(x!, y!, 9, 9);
      return new THREE.Box3(
        new THREE.Vector3(centre.x - 0.5, 0, centre.z - 0.5),
        new THREE.Vector3(centre.x + 0.5, 4, centre.z + 0.5),
      );
    });
    const camera = createCamera(9, 9, 1);
    for (const dx of [-0.49, 0, 0.49])
      for (const dz of [-0.49, 0, 0.49]) {
        const focus = worldOf(4, 4, 9, 9).setY(2.3);
        focus.x += dx;
        focus.z += dz;
        for (let azimuth = 0; azimuth < 360; azimuth += 45)
          for (const distance of [3, 8]) {
            updateFollowCamera(camera, focus, { azimuth, elevation: 12, distance });
            avoidCameraBlocks(camera, focus, 1, 9, 9, (x, y) =>
              walls.some(([wx, wy]) => wx === x && wy === y) ? 4 : 1,
            );
            expect(camera.position.distanceTo(focus)).toBeGreaterThan(0.001);
            const feet = focus.clone().setY(1.12);
            const ray = new THREE.Ray(feet, camera.position.clone().sub(feet).normalize());
            for (const box of boxes) {
              expect(box.containsPoint(camera.position)).toBe(false);
              const hit = ray.intersectBox(box, new THREE.Vector3());
              expect(hit === null || hit.distanceTo(feet) > camera.position.distanceTo(feet)).toBe(
                true,
              );
            }
          }
      }
  }
});
