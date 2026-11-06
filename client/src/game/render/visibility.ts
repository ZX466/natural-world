/** Human geometry only: fixed radius and the server's endpoint-excluding LOS. */
import type { WorldMirror, MapStatic } from '../world-mirror';
import type { MovePoint } from '../movement';

export const VISION_RADIUS = 12;
const integerPoint = (point: MovePoint): boolean =>
  Number.isSafeInteger(point.x) && Number.isSafeInteger(point.y);

/** Direct port of sim/perception/propagation.py::line_blocked. Keep both
 * comparisons against the same e2, including its directional tie behavior. */
export function lineBlocked(
  map: Pick<MapStatic, 'w' | 'h' | 'collision'>,
  a: MovePoint,
  b: MovePoint,
): boolean {
  if (!integerPoint(a) || !integerPoint(b)) return true;
  let x0 = a.x,
    y0 = a.y;
  const x1 = b.x,
    y1 = b.y;
  const dx = Math.abs(x1 - x0);
  const dy = -Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1;
  const sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  while (true) {
    if (
      (x0 !== a.x || y0 !== a.y) &&
      (x0 !== b.x || y0 !== b.y) &&
      !(x0 >= 0 && y0 >= 0 && x0 < map.w && y0 < map.h && map.collision[y0 * map.w + x0])
    )
      return true;
    if (x0 === x1 && y0 === y1) return false;
    const e2 = 2 * err;
    if (e2 >= dy) {
      err += dy;
      x0 += sx;
    }
    if (e2 <= dx) {
      err += dx;
      y0 += sy;
    }
  }
}

export function pointVisible(
  map: Pick<MapStatic, 'w' | 'h' | 'collision'>,
  hero: MovePoint,
  point: MovePoint,
): boolean {
  if (!integerPoint(hero) || !integerPoint(point)) return false;
  if (
    hero.x < 0 ||
    hero.y < 0 ||
    hero.x >= map.w ||
    hero.y >= map.h ||
    point.x < 0 ||
    point.y < 0 ||
    point.x >= map.w ||
    point.y >= map.h
  )
    return false;
  const dx = point.x - hero.x,
    dy = point.y - hero.y;
  return dx * dx + dy * dy <= VISION_RADIUS * VISION_RADIUS && !lineBlocked(map, hero, point);
}

export function visibleActorTokens(
  mirror: Pick<WorldMirror, 'actors' | 'protagonist' | 'map'>,
): Set<string> {
  const hero = mirror.actors.get(mirror.protagonist ?? '');
  const shown = new Set<string>();
  if (!hero || mirror.protagonist === null) return shown;
  shown.add(mirror.protagonist);
  if (!mirror.map) return shown;
  for (const [token, actor] of mirror.actors)
    if (token !== mirror.protagonist && pointVisible(mirror.map, hero, actor)) shown.add(token);
  return shown;
}
