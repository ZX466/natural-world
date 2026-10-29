import type { MapStatic } from './world-mirror';

export type MovePoint = { x: number; y: number };

function inBounds(map: MapStatic, { x, y }: MovePoint): boolean {
  return Number.isInteger(x) && Number.isInteger(y) && x >= 0 && y >= 0 && x < map.w && y < map.h;
}

function walkable(map: MapStatic, point: MovePoint): boolean {
  return inBounds(map, point) && map.collision[point.y * map.w + point.x] === 1;
}

/** Same local step topology as Pathfinder: neither diagonal corner may be blocked. */
export function canStep(map: MapStatic, from: MovePoint, to: MovePoint): boolean {
  const dx = to.x - from.x,
    dy = to.y - from.y;
  return (
    Math.abs(dx) <= 1 &&
    Math.abs(dy) <= 1 &&
    walkable(map, to) &&
    (dx === 0 ||
      dy === 0 ||
      (walkable(map, { x: from.x + dx, y: from.y }) &&
        walkable(map, { x: from.x, y: from.y + dy })))
  );
}

/** Only a local preflight; sim remains authoritative for the path and movement. */
export function movementFailure(
  map: MapStatic,
  start: MovePoint,
  target: MovePoint,
): string | null {
  if (!inBounds(map, start)) return '这会儿走不了。';
  if (!walkable(map, target)) return '那处挡着路。';
  const destination = target.y * map.w + target.x;
  const first = start.y * map.w + start.x;
  const visited = new Uint8Array(map.w * map.h);
  const queue = new Int32Array(map.w * map.h);
  queue[0] = first;
  visited[first] = 1;
  let head = 0,
    tail = 1;
  while (head < tail) {
    const cell = queue[head++]!;
    if (cell === destination) return null;
    const current = { x: cell % map.w, y: Math.floor(cell / map.w) };
    for (let dy = -1; dy <= 1; dy++)
      for (let dx = -1; dx <= 1; dx++) {
        if (dx === 0 && dy === 0) continue;
        const next = { x: current.x + dx, y: current.y + dy };
        if (!canStep(map, current, next)) continue;
        const index = next.y * map.w + next.x;
        if (visited[index]) continue;
        visited[index] = 1;
        queue[tail++] = index;
      }
  }
  return '那处绕不过去。';
}
