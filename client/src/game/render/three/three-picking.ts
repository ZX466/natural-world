/** Editing sees the nearest column; movement inverts only the walkable plane. */
import * as THREE from 'three';
import type { MapStatic } from '../../world-mirror';
import type { MovePoint } from '../../movement';
import type { HeightLookup } from '../iso';
import { cellOf } from './three-projection';

export const WALK_HEIGHT = 1;
export type ScreenRect = Pick<DOMRect, 'left' | 'top' | 'width' | 'height'>;
const walkPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -WALK_HEIGHT);

export function screenRay(
  camera: THREE.Camera,
  x: number,
  y: number,
  rect: ScreenRect,
): THREE.Ray | null {
  if (
    ![x, y, rect.left, rect.top, rect.width, rect.height].every(Number.isFinite) ||
    rect.width <= 0 ||
    rect.height <= 0
  )
    return null;
  if (x < rect.left || y < rect.top || x > rect.left + rect.width || y > rect.top + rect.height)
    return null;
  const caster = new THREE.Raycaster();
  camera.updateMatrixWorld(true);
  caster.setFromCamera(
    new THREE.Vector2(
      (2 * (x - rect.left)) / rect.width - 1,
      1 - (2 * (y - rect.top)) / rect.height,
    ),
    camera,
  );
  return caster.ray;
}

export function groundFromRay(
  ray: THREE.Ray,
  map: MapStatic,
  heightOf: HeightLookup,
): MovePoint | null {
  const point = ray.intersectPlane(walkPlane, new THREE.Vector3());
  if (!point) return null;
  const cell = cellOf(point, map.w, map.h);
  if (
    !Number.isInteger(cell.x) ||
    !Number.isInteger(cell.y) ||
    cell.x < 0 ||
    cell.y < 0 ||
    cell.x >= map.w ||
    cell.y >= map.h
  )
    return null;
  return map.collision[cell.y * map.w + cell.x] === 1 && heightOf(cell.x, cell.y) === WALK_HEIGHT
    ? cell
    : null;
}

export function editFromRay(ray: THREE.Ray, meshes: readonly THREE.Object3D[]): MovePoint | null {
  const caster = new THREE.Raycaster();
  caster.ray.copy(ray);
  for (const hit of caster.intersectObjects([...meshes], false)) {
    if (hit.instanceId === undefined) continue;
    const cells: unknown = hit.object.userData.cells;
    if (!Array.isArray(cells)) continue;
    const cell = cells[hit.instanceId] as MovePoint | undefined;
    if (cell && Number.isInteger(cell.x) && Number.isInteger(cell.y))
      return { x: cell.x, y: cell.y };
  }
  return null;
}
