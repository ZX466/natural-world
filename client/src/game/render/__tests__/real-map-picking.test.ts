import { readFileSync } from 'node:fs';
import { afterEach, expect, it, vi } from 'vitest';
import { createHeightLookup, depthKey, ISO, isoProject, screenBounds } from '../iso';
import { pickGround, pickVoxel } from '../voxel-picking';
import { WorldMirror, type MapStatic } from '../../world-mirror';

vi.mock('phaser', () => ({ default: { Scene: class {} } }));
import { WorldScene } from '../../scenes/WorldScene';

const root = new URL('../../../../../', import.meta.url);
const source = JSON.parse(readFileSync(new URL('sim/content/linhe-town.json', root), 'utf8')) as {
  width: number;
  height: number;
  chunks: Record<string, { ground: number[]; collision: boolean[] }>;
  _structures?: Record<string, { x: number; y: number; w: number; h: number }>;
};
const table: unknown = JSON.parse(
  readFileSync(new URL('client/public/assets/tilesets/linhe-height.json', root), 'utf8'),
);
const map: MapStatic = {
  w: source.width,
  h: source.height,
  tileset: 'linhe-town',
  collision: new Uint8Array(source.width * source.height),
  ground: new Uint16Array(source.width * source.height),
  structures: source._structures ?? {},
};
for (const [key, chunk] of Object.entries(source.chunks)) {
  const [cx, cy] = key.split(',').map(Number);
  const side = Math.sqrt(chunk.collision.length);
  for (let i = 0; i < chunk.collision.length; i++) {
    const x = cx! * side + (i % side),
      y = cy! * side + Math.floor(i / side);
    if (x >= map.w || y >= map.h) continue;
    map.collision[y * map.w + x] = Number(chunk.collision[i]);
    map.ground![y * map.w + x] = chunk.ground[i]!;
  }
}
const heightAt = createHeightLookup(table);
const bounds = screenBounds(map.w, map.h);
const blocked = (x: number, y: number) => map.collision[y * map.w + x] === 0;
const cells = Array.from({ length: map.w * map.h }, (_, index) => {
  const x = index % map.w,
    y = Math.floor(index / map.w),
    height = heightAt(x, y);
  return { x, y, height, top: isoProject(x, y, height, bounds), depth: depthKey(x, y) };
});
type Cell = (typeof cells)[number];
type Point = { sx: number; sy: number };
const tall = cells.filter((cell) => cell.height >= 2 && blocked(cell.x, cell.y));
/** 静态结构占地面：高度 1、碰撞 0，但不是土坎（建筑地基，挖不得）。 */
const inStructure = (x: number, y: number) =>
  Object.values(map.structures ?? {}).some(
    (a) => Math.abs(x - a.x) <= Math.floor(a.w / 2) && Math.abs(y - a.y) <= Math.floor(a.h / 2),
  );
const banks = cells.filter(
  (cell) => cell.height === 1 && blocked(cell.x, cell.y) && !inStructure(cell.x, cell.y),
);

/** Independent draw oracle: test the six prism outline edges in painter's order.
 * This never calls the picker or copies its search window/priority calculation. */
function covers(cell: Cell, point: Point): boolean {
  if (Math.abs(cell.top.sx - point.sx) > ISO.TW / 2) return false;
  const { sx, sy } = cell.top,
    hw = ISO.TW / 2,
    hh = ISO.TH / 2,
    bottom = sy + cell.height * ISO.HH;
  const outline = [
    [sx, sy - hh],
    [sx + hw, sy],
    [sx + hw, bottom],
    [sx, bottom + hh],
    [sx - hw, bottom],
    [sx - hw, sy],
  ];
  return outline.every(([x, y], index) => {
    const [nx, ny] = outline[(index + 1) % outline.length]!;
    return (nx! - x!) * (point.sy - y!) - (ny! - y!) * (point.sx - x!) >= 0;
  });
}
const visibleBanks = banks.filter(
  (cell) => !tall.some((front) => front.depth > cell.depth + 0.5 && covers(front, cell.top)),
);
const pick = ({ sx, sy }: Point) => pickVoxel(sx, sy, map.w, map.h, heightAt, blocked);

afterEach(() => vi.useRealTimers());

it('picks all 448 real bank centers not hidden by a foreground high block', () => {
  expect(banks).toHaveLength(1568);
  expect(visibleBanks).toHaveLength(448);
  const misses = visibleBanks.filter((cell) => {
    const hit = pick(cell.top);
    return hit?.x !== cell.x || hit.y !== cell.y;
  });
  expect(misses.length, `${visibleBanks.length - misses.length}/448 bank centers hit`).toBe(0);
});

it('picks a real foreground bank top while keeping its baked side behind high blocks', () => {
  const top = isoProject(20, 3, 1, bounds);
  expect(blocked(20, 3)).toBe(true);
  expect(heightAt(20, 3)).toBe(1);
  expect(pick(top)).toEqual({ x: 20, y: 3 });
  const side = isoProject(20, 3, 0, bounds);
  expect(pick({ sx: side.sx, sy: side.sy - 4 })).toEqual({ x: 22, y: 4 });
});

it('does not reduce real high-block center hits from the original 7141 of 7373', () => {
  expect(tall).toHaveLength(7373);
  const hits = tall.filter((cell) => {
    const hit = pick(cell.top);
    return hit?.x === cell.x && hit.y === cell.y;
  });
  expect(hits.length).toBeGreaterThanOrEqual(7141);
});

it('keeps the visible rear house side outside the real bank glyph strokes pickable', () => {
  const top = isoProject(20, 3, 1, bounds);
  // The bank's three painted quads have local y in [-2,2]. Here its baked top
  // is behind the opaque side of(19,3), so that side remains the visible target.
  expect(heightAt(19, 3)).toBe(2);
  expect(pick({ sx: top.sx - 8, sy: top.sy + 3 })).toEqual({ x: 19, y: 3 });
});

it('keeps every real-map walking center on its own cell', () => {
  const walkable = (x: number, y: number) => !blocked(x, y);
  const walk = cells.filter((cell) => walkable(cell.x, cell.y));
  // 3692 = 3947 原始可走格 − 试车台 17×15 占地面（世界结构，服务端已挡）。
  expect(walk).toHaveLength(3692);
  for (const cell of walk)
    expect(pickGround(cell.top.sx, cell.top.sy, map.w, map.h, heightAt, walkable)).toEqual({
      x: cell.x,
      y: cell.y,
    });
});

it('keeps a genuinely occluded real bank center on its visible foreground high block', () => {
  expect(visibleBanks.some(({ x, y }) => x === 91 && y === 30)).toBe(false);
  expect(pick(isoProject(91, 30, 1, bounds))).toEqual({ x: 92, y: 31 });
});

it('sends the real foreground bank coordinate through the actual scene hold handler', () => {
  vi.useFakeTimers();
  const mirror = new WorldMirror();
  mirror.setMap({ ...map, collision: map.collision.slice(), ground: map.ground!.slice() });
  mirror.protagonist = 'hero';
  const scene = new WorldScene(mirror, 'iso');
  const emit = vi.fn();
  Object.assign(scene, { game: { events: { emit } }, heightAt });
  const input = scene as unknown as {
    handlePointerDown(pointer: unknown): void;
    cancelVoxelInput(): void;
  };
  const top = isoProject(20, 3, 1, bounds);
  input.handlePointerDown({ worldX: top.sx, worldY: top.sy, button: 0, id: 1 });
  try {
    vi.advanceTimersByTime(150);
    expect(emit).toHaveBeenLastCalledWith('client:voxel_request', {
      action: 'dig_start',
      x: 20,
      y: 3,
    });
  } finally {
    input.cancelVoxelInput();
  }
});
