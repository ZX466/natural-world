import { expect, it } from 'vitest';
import { isoProject, screenBounds } from '../iso';
import { pickGround, pickVoxel } from '../voxel-picking';

/**
 * 2026-10-29「人物无法移动」回归钉。
 *
 * 可走格恒为 h=1（terrain_class 单向不变量：walkable ⇒ EARTH）。相邻两格
 * 斜向「屏幕上两格」处若立着 h=3 的方块，它的顶面菱形与本格顶面**完全重合**
 * ——真实地图实测 3947 个可走格里有 763 个（19.3%）被 `pickVoxel` 判成阻挡格，
 * 出生点邻域 26 个可走格里 21 个如此。`movementFailure` 因此全部拒绝，一个移动
 * 帧都发不出去。
 */
function scene() {
  const w = 8,
    h = 8;
  const blocked = (x: number, y: number) => (x === 6 && y === 6) || (x === 2 && y === 2);
  const walkable = (x: number, y: number) => x >= 0 && y >= 0 && x < w && y < h && !blocked(x, y);
  const height = (x: number, y: number) => (x === 6 && y === 6 ? 3 : 1);
  return { w, h, walkable, height };
}

it('picks the walkable cell whose top face was clicked, not the tall block covering it', () => {
  const { w, h, walkable, height } = scene();
  const point = isoProject(4, 4, 1, screenBounds(w, h));

  // 同一个屏幕点：h=3 的 (6,6) 顶面与 h=1 的 (4,4) 顶面重合。
  // 编辑拾取取高方块（玩家看到的就是它）——正确。
  expect(pickVoxel(point.sx, point.sy, w, h, height)).toEqual({ x: 6, y: 6 });
  // 移动拾取必须落在可走格，否则点空地等于点房子。
  expect(pickGround(point.sx, point.sy, w, h, height, walkable)).toEqual({ x: 4, y: 4 });
});

it('never returns a blocked cell, so movement can never be refused for a visible ground click', () => {
  const { w, h, walkable, height } = scene();
  for (let y = 0; y < h; y += 1)
    for (let x = 0; x < w; x += 1) {
      if (!walkable(x, y)) continue;
      const point = isoProject(x, y, height(x, y), screenBounds(w, h));
      const picked = pickGround(point.sx, point.sy, w, h, height, walkable);
      expect(picked).toEqual({ x, y });
    }
});

it('returns null on a blocked ground cell so the caller falls back to editing', () => {
  const { w, h, walkable, height } = scene();
  const point = isoProject(2, 2, 1, screenBounds(w, h));
  expect(pickGround(point.sx, point.sy, w, h, height, walkable)).toBeNull();
  expect(pickGround(-999, -999, w, h, height, walkable)).toBeNull();
});

it('never returns a cell whose height is not the walkable surface', () => {
  // 资产漂移防御：可走却标了非 EARTH 高度时宁可不动，也不要把人送到错位格。
  const w = 4,
    h = 4;
  const walkable = () => true;
  const height = () => 2;
  const point = isoProject(1, 1, 1, screenBounds(w, h));
  expect(pickGround(point.sx, point.sy, w, h, height, walkable)).toBeNull();
});
