import { readFileSync } from 'node:fs';
import { afterEach, expect, it, vi } from 'vitest';
import { createHeightLookup, depthKey, ISO, isoProject, screenBounds } from '../iso';
import { renderHeightLookup } from '../cell-appearance';
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
/** 逻辑高度 → 画出来的高度：土坎（1、不可走）画成 2 格矮墙。 */
const drawHeight = renderHeightLookup(map, heightAt);
const bounds = screenBounds(map.w, map.h);
const blocked = (x: number, y: number) => map.collision[y * map.w + x] === 0;
const cells = Array.from({ length: map.w * map.h }, (_, index) => {
  const x = index % map.w,
    y = Math.floor(index / map.w),
    logical = heightAt(x, y),
    height = drawHeight(x, y);
  return {
    x,
    y,
    logical,
    height,
    top: isoProject(x, y, height, bounds),
    depth: depthKey(x, y),
  };
});
type Cell = (typeof cells)[number];
type Point = { sx: number; sy: number };
/** 画出来 ≥2 的格子都会挡住后面的顶面；土坎抬起来以后也在这批里。 */
const tall = cells.filter((cell) => cell.height >= 2);
/** 静态结构占地面：逻辑高度 1、碰撞 0，但不是土坎（建筑地基，挖不得）。 */
const inStructure = (x: number, y: number) =>
  Object.values(map.structures ?? {}).some(
    (a) => Math.abs(x - a.x) <= Math.floor(a.w / 2) && Math.abs(y - a.y) <= Math.floor(a.h / 2),
  );
const banks = cells.filter(
  (cell) => cell.logical === 1 && blocked(cell.x, cell.y) && !inStructure(cell.x, cell.y),
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
const pick = ({ sx, sy }: Point) => pickVoxel(sx, sy, map.w, map.h, drawHeight);

afterEach(() => vi.useRealTimers());

it('picks every real bank center that no foreground block hides', () => {
  // 土坎仍是 1568 格（逻辑高度 1、不可走、非结构占地面）；现在它们画在 2。
  expect(banks).toHaveLength(1568);
  expect(banks.every((cell) => cell.height === 2)).toBe(true);
  const misses = visibleBanks.filter((cell) => {
    const hit = pick(cell.top);
    return hit?.x !== cell.x || hit.y !== cell.y;
  });
  expect(misses.length, `${visibleBanks.length - misses.length}/${visibleBanks.length} hit`).toBe(
    0,
  );
});

it('picks a real foreground bank top on the wall it is now drawn as', () => {
  const top = isoProject(20, 3, 2, bounds);
  expect(blocked(20, 3)).toBe(true);
  expect(heightAt(20, 3)).toBe(1);
  expect(drawHeight(20, 3)).toBe(2);
  expect(pick(top)).toEqual({ x: 20, y: 3 });
});

it('does not reduce real high-block center hits from the original 7141 of 7373', () => {
  // 高块中心命中数不能因为土坎改画矮墙而下降。土坎抬高后本身也成了「高块」，
  // 所以分母变大，这里只钉住原来那批真高块（逻辑高度 ≥2）。
  const realTall = tall.filter((cell) => cell.logical >= 2);
  expect(realTall).toHaveLength(7373);
  const hits = realTall.filter((cell) => {
    const hit = pick(cell.top);
    return hit?.x === cell.x && hit.y === cell.y;
  });
  expect(hits.length).toBeGreaterThanOrEqual(7141);
});

it('picks the bank wall itself across its whole visible face, not the ground behind it', () => {
  // 土坎画成 2 格矮墙后，它自己的墙面就是最前面的编辑目标。
  // 旧实现靠「斜纹像素 + 0.5 深度」把墙面让给后面的房子；现在整根柱子
  // 都是实体，点墙面必须命中土坎本身。
  const top = isoProject(20, 3, 2, bounds);
  expect(heightAt(20, 3)).toBe(1);
  expect(drawHeight(20, 3)).toBe(2);
  for (const dy of [-6, 0, 3, 6])
    expect(pick({ sx: top.sx, sy: top.sy + dy })).toEqual({
      x: 20,
      y: 3,
    });
  // 墙根以下仍属于前面那一格。
  expect(pick({ sx: top.sx, sy: top.sy + 22 })).toEqual({ x: 21, y: 4 });
});

it('keeps every real-map walking center on its own cell', () => {
  const walkable = (x: number, y: number) => !blocked(x, y);
  const walk = cells.filter((cell) => walkable(cell.x, cell.y));
  // 3692 = 3947 原始可走格 − 试车台 17×15 占地面（世界结构，服务端已挡）。
  expect(walk).toHaveLength(3692);
  for (const cell of walk)
    // 移动拾取读**逻辑**高度：可走格永远不是土坎，所以顶面仍在 1。
    expect(pickGround(cell.top.sx, cell.top.sy, map.w, map.h, heightAt, walkable)).toEqual({
      x: cell.x,
      y: cell.y,
    });
});

it('keeps a genuinely occluded real bank center on its visible foreground block', () => {
  // 遮挡集变小了：土坎抬高后自己也会挡住斜后方的格子，所以「被挡住」的
  // 土坎从 1120 降到 69。钉住的是「有遮挡、且遮挡时点到的是前面那格」，
  // 不是某个固定数字。
  expect(visibleBanks.length).toBeLessThan(banks.length);
  const hidden = banks.find((cell) => !visibleBanks.includes(cell))!;
  expect(hidden).toBeDefined();
  expect(pick(hidden.top)).not.toEqual({ x: hidden.x, y: hidden.y });
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
  // 土坎画成 2 格矮墙，指针要点在**画出来的**顶面（2），不是逻辑高度 1。
  const top = isoProject(20, 3, 2, bounds);
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
