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
      let y = Math.max(0, Math.min(home.y, end.y));
      y <= Math.min(h - 1, Math.max(home.y, end.y));
      y++
    ) {
      for (
        let x = Math.max(0, Math.min(home.x, end.x));
        x <= Math.min(w - 1, Math.max(home.x, end.x));
        x++
      ) {
        const height = heightOf(x, y);
        if ((x === home.x && y === home.y) || height <= feet.y) continue;
        const centre = worldOf(x, y, w, h);
        const box = new THREE.Box3(
          new THREE.Vector3(centre.x - 0.5, 0, centre.z - 0.5),
          new THREE.Vector3(centre.x + 0.5, height, centre.z + 0.5),
        );
        if (ray.intersectBox(box, hitPoint)) {
          const distance = hitPoint.distanceTo(feet);
          if (distance < length)
            fraction = Math.min(fraction, Math.max(0.02, (distance - 0.25) / length));
        }
      }
    }
    return fraction;
  };
  let offset = camera.position.clone().sub(focus);
  const distance = offset.length();
  let fraction = safeFraction(camera.position);
  if (distance * fraction < 2.5) {
    const azimuth = Math.atan2(offset.x, offset.z);
    const elevation = THREE.MathUtils.radToDeg(Math.asin(offset.y / distance));
    // A near wall must not force the eye inside the player's billboard. Raise
    // the boom only while obstructed; the user's orbit returns on clear ground.
    for (let angle = Math.max(20, elevation + 5); angle <= 80; angle += 5) {
      const radians = THREE.MathUtils.degToRad(angle);
      const candidate = new THREE.Vector3(
        Math.sin(azimuth) * Math.cos(radians),
        Math.sin(radians),
        Math.cos(azimuth) * Math.cos(radians),
      ).multiplyScalar(distance);
      const safe = safeFraction(focus.clone().add(candidate));
      if (distance * safe >= 2.5) {
        offset = candidate;
        fraction = safe;
        break;
      }
    }
  }
  camera.position.copy(focus).addScaledVector(offset, fraction);
  camera.lookAt(focus);
  camera.updateMatrixWorld(true);
}
