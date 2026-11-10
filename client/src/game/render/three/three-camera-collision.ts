/** Keep a chase camera outside foreground columns, without changing game state. */
import * as THREE from 'three';
import { cellOf, worldOf } from './three-projection';
import type { HeightLookup } from '../iso';

export function avoidCameraBlocks(
  camera: THREE.PerspectiveCamera,
  focus: THREE.Vector3,
  floor: number,
  w: number,
  h: number,
  heightOf: HeightLookup,
): void {
  const feet = new THREE.Vector3(focus.x, floor + 0.12, focus.z);
  const home = cellOf(focus, w, h);
  const hitPoint = new THREE.Vector3();
  const safeFraction = (position: THREE.Vector3): number => {
    const direction = position.clone().sub(feet);
    const length = direction.length();
    const ray = new THREE.Ray(feet, direction.normalize());
    const end = cellOf(position, w, h);
    let fraction = 1;
    for (
      let y = Math.max(0, Math.min(home.y, end.y) - 1);
      y <= Math.min(h - 1, Math.max(home.y, end.y) + 1);
      y++
    ) {
      for (
        let x = Math.max(0, Math.min(home.x, end.x) - 1);
        x <= Math.min(w - 1, Math.max(home.x, end.x) + 1);
        x++
      ) {
        const height = heightOf(x, y);
        if ((x === home.x && y === home.y) || height <= feet.y) continue;
        const centre = worldOf(x, y, w, h);
        const box = new THREE.Box3(
          new THREE.Vector3(centre.x - 0.62, 0, centre.z - 0.62),
          new THREE.Vector3(centre.x + 0.62, height + 0.12, centre.z + 0.62),
        );
        if (box.containsPoint(feet)) {
          // Interpolated feet can enter the padding while still outside the
          // solid wall. intersectBox then returns the EXIT, which is not safe
          // boom length. Permit escape from the padding; test the actual wall
          // for entry, and reject endpoints that stay in its margin.
          if (box.containsPoint(position)) {
            fraction = 0;
            continue;
          }
          box.min.set(centre.x - 0.5, 0, centre.z - 0.5);
          box.max.set(centre.x + 0.5, height, centre.z + 0.5);
        }
        if (ray.intersectBox(box, hitPoint)) {
          const distance = hitPoint.distanceTo(feet);
          if (distance < length)
            fraction = Math.min(fraction, Math.max(0, (distance - 0.25) / length));
        }
      }
    }
    return fraction;
  };
  let offset = camera.position.clone().sub(focus);
  const distance = offset.length();
  if (distance < 1e-8) return;
  let fraction = safeFraction(camera.position);
  if (distance * fraction < 2.5) {
    const azimuth = Math.atan2(offset.x, offset.z);
    const elevation = THREE.MathUtils.radToDeg(Math.asin(offset.y / distance));
    // Search sideways before raising the boom. Only a deliberately high user
    // orbit may exceed 35 degrees; a confined room shortens the boom instead.
    const angles = [elevation];
    for (let angle = elevation + 5; angle < 35; angle += 5) angles.push(angle);
    if (elevation < 35) angles.push(35);
    search: for (const angle of angles) {
      const radians = THREE.MathUtils.degToRad(angle);
      for (const turn of [
        0, 15, -15, 30, -30, 45, -45, 60, -60, 75, -75, 90, -90, 120, -120, 150, -150, 180,
      ]) {
        const yaw = azimuth + THREE.MathUtils.degToRad(turn);
        const candidate = new THREE.Vector3(
          Math.sin(yaw) * Math.cos(radians),
          Math.sin(radians),
          Math.cos(yaw) * Math.cos(radians),
        ).multiplyScalar(distance);
        const safe = safeFraction(focus.clone().add(candidate));
        if (safe > fraction) {
          offset = candidate;
          fraction = safe;
        }
        if (safe === 1) break search;
      }
    }
  }
  camera.position.copy(focus).addScaledVector(offset, fraction);
  camera.lookAt(focus);
  camera.updateMatrixWorld(true);
}

/** Screen-relative controls and billboards must follow the resolved camera. */
export function cameraAzimuth(camera: THREE.PerspectiveCamera): number {
  const direction = camera.getWorldDirection(new THREE.Vector3());
  return THREE.MathUtils.radToDeg(Math.atan2(-direction.x, -direction.z));
}
