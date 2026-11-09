import { expect, it } from 'vitest';
import {
  STAND_FOOTPRINT_H,
  STAND_FOOTPRINT_W,
  STAND_STRUCTURE_KEY,
  standFootprint,
  standPlotFrom,
} from '../landmark-lre';

/** 17×15（x 从 cx-8 到 cx+8，y 从 cy-7 到 cy+7）——与 vendored 模块
 *  `getOccupiedTiles()` 的取整范围一致，不是规格文档写的 16×14。 */
it('footprint constants match the vendored occupied-tile loop', () => {
  expect(STAND_FOOTPRINT_W).toBe(17);
  expect(STAND_FOOTPRINT_H).toBe(15);
});

it('the world anchor becomes a world-space plot, never a grid guess', () => {
  // 服务端地图 `_structures.lre_test_stand` 的形状：格子中心 + 闭区间跨度。
  expect(standPlotFrom({ x: 82, y: 41, w: 17, h: 15 }, 140, 100)).toEqual({
    tileX: 12.5,
    tileZ: -8.5,
    gridX: 82,
    gridY: 41,
    groundY: 1,
  });
});

it('refuses an anchor whose size does not match the vendored footprint', () => {
  // 规格文档写的 16×14 是错的；拿错尺寸建塔会跟碰撞矩形错位。
  expect(standPlotFrom({ x: 82, y: 41, w: 16, h: 14 }, 140, 100)).toBeNull();
});

it('refuses an anchor that would hang off the map', () => {
  expect(standPlotFrom({ x: 4, y: 41, w: 17, h: 15 }, 140, 100)).toBeNull();
  expect(standPlotFrom({ x: 136, y: 41, w: 17, h: 15 }, 140, 100)).toBeNull();
});

it('builds nothing when the map carries no structure anchor', () => {
  // 缺锚点 = 这张图没有静态结构（占位 32×32 图就是这样）。绝不自己找位置顶替：
  // 那样模型会浮在可通行地上，或者站在一堵看不见的墙上。
  expect(standPlotFrom(undefined, 140, 100)).toBeNull();
});

it('footprint covers every occupied tile at the concrete deck height', () => {
  const tiles = standFootprint({ tileX: 0, tileZ: 0, gridX: 20, gridY: 30, groundY: 1 });
  expect(tiles).toHaveLength(STAND_FOOTPRINT_W * STAND_FOOTPRINT_H);
  expect(tiles[0]).toEqual({ gx: 12, gz: 23, topY: 1.52 });
  expect(tiles.at(-1)).toEqual({ gx: 28, gz: 37, topY: 1.52 });
  expect(new Set(tiles.map((t) => `${t.gx}:${t.gz}`)).size).toBe(tiles.length);
});

it('the structure key matches the key the world data writes', () => {
  // 与 sim/content/build_god_town.py::STAND_KEY 逐字一致；改一处必须改两处。
  expect(STAND_STRUCTURE_KEY).toBe('lre_test_stand');
});
