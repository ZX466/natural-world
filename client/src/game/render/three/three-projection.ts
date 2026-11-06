/** Unit-world perspective camera. No Phaser screen-space alignment. */
import * as THREE from 'three';

export interface OrbitPose {
  readonly azimuth: number;
  readonly elevation: number;
  readonly distance: number;
}
export const defaultOrbit = (): OrbitPose => ({ azimuth: 45, elevation: 12, distance: 8 });
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

export function orbitBy(pose: OrbitPose, dx: number, dy: number): OrbitPose {
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return pose;
  return {
    ...pose,
    azimuth: (((pose.azimuth - dx * 0.25) % 360) + 360) % 360,
    elevation: clamp(pose.elevation - dy * 0.2, 3, 80),
  };
}
export function zoomBy(pose: OrbitPose, delta: number): OrbitPose {
  if (!Number.isFinite(delta)) return pose;
  return { ...pose, distance: clamp(pose.distance * Math.exp(delta * 0.001), 3, 24) };
}
export function worldOf(x: number, y: number, w: number, h: number): THREE.Vector3 {
  return new THREE.Vector3(x - w / 2 + 0.5, 0, y - h / 2 + 0.5);
}
export function cellOf(point: THREE.Vector3, w: number, h: number): { x: number; y: number } {
  return { x: Math.round(point.x + w / 2 - 0.5), y: Math.round(point.z + h / 2 - 0.5) };
}
export function createCamera(_w: number, _h: number, aspect: number): THREE.PerspectiveCamera {
  const camera = new THREE.PerspectiveCamera(60, Math.max(0.01, aspect), 0.05, 300);
  updateFollowCamera(camera, new THREE.Vector3(0, 2.3, 0), defaultOrbit());
  return camera;
}
export function updateFollowCamera(
  camera: THREE.PerspectiveCamera,
  target: THREE.Vector3,
  pose: OrbitPose,
): void {
  if (
    ![target.x, target.y, target.z, pose.azimuth, pose.elevation, pose.distance].every(
      Number.isFinite,
    )
  )
    return;
  const azimuth = THREE.MathUtils.degToRad(pose.azimuth);
  const elevation = THREE.MathUtils.degToRad(pose.elevation);
  const run = Math.cos(elevation) * pose.distance;
  camera.position.set(
    target.x + Math.sin(azimuth) * run,
    target.y + Math.sin(elevation) * pose.distance,
    target.z + Math.cos(azimuth) * run,
  );
  camera.lookAt(target);
  camera.updateMatrixWorld(true);
}
export function resizeCamera(
  camera: THREE.PerspectiveCamera,
  _w: number,
  _h: number,
  aspect: number,
): void {
  if (!Number.isFinite(aspect) || aspect <= 0) return;
  camera.aspect = aspect;
  camera.updateProjectionMatrix();
}
