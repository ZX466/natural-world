/** LRE-DT100 试车台的放置逻辑（纯函数，可单测，不碰 WebGL）。
 *
 * 为什么单独一层：`linhe_lre_test_stand_building.js` 是**原样引入的外部 ES Module**
 * （带自己的 canvas 程序化贴图、shader 与 24 个子部件），它不知道《临河镇》的
 * 坐标口径。这里只回答「世界给的锚点 → 世界坐标怎么算」。
 *
 * 坐标口径：`worldOf` 把格子 `(x, y)` 映射到世界 `(x - w/2 + 0.5, 0, y - h/2 + 0.5)`，
 * 而 vendored 模块的 `root.position.set(tileX, groundY, tileZ)` 直接吃世界坐标，
 * 所以 `tileX/tileZ` 必须是**世界坐标**，不是格子下标。
 *
 * **锚点来自世界数据，不是客户端扫描。** 服务端地图 JSON 的 `_structures`
 * 给出占地面，且那 17×15 格在 collision 里已经不可走。客户端若自己扫地形挑点，
 * 会与服务端挡路的矩形错位 —— 模型浮在可通行地上，或者站在一堵看不见的墙上。
 */
import type { MapStructure } from '../../world-mirror';

/** 占地面：vendored `getOccupiedTiles()` 从 `tileX-8` 到 `tileX+8`、`tileZ-7` 到
 *  `tileZ+7` 闭区间 —— 是 17×15，不是规格文档里写的 16×14。以代码为准。 */
export const STAND_FOOTPRINT_W = 17;
export const STAND_FOOTPRINT_H = 15;

/** 服务端地图 `_structures` 里试车台那条记录的键名。 */
export const STAND_STRUCTURE_KEY = 'lre_test_stand';

/** 地基顶面高度：`getOccupiedTiles()` 的 `topY = groundY + 0.52`。 */
const DECK_LIFT = 0.52;

/** 默认站在高度 1 的可走地面上（与体素地表同一个「土块顶面」口径）。 */
const DEFAULT_GROUND_Y = 1;

export interface StandPlot {
  /** 建筑中心的世界 X（`worldOf` 口径，已减地图中心）——直接喂 `root.position`。 */
  readonly tileX: number;
  /** 建筑中心的世界 Z。 */
  readonly tileZ: number;
  /** 建筑中心的格子下标（`standFootprint` 用它算占位，避免世界坐标取整漂移）。 */
  readonly gridX: number;
  readonly gridY: number;
  /** 地基贴合的地面高度。 */
  readonly groundY: number;
}

export interface StandTile {
  readonly gx: number;
  readonly gz: number;
  readonly topY: number;
}

/** 世界锚点 → 世界坐标。锚点越界/尺寸不符返回 `null`（调用方静默不建，
 *  绝不自己找位置顶替）。`anchor.x/y` 是**格子下标中心**，`w/h` 是闭区间跨度。 */
export function standPlotFrom(
  anchor: MapStructure | undefined,
  mapW: number,
  mapH: number,
): StandPlot | null {
  if (!anchor) return null;
  const { x, y, w, h } = anchor;
  if (![x, y, w, h, mapW, mapH].every(Number.isFinite)) return null;
  if (w !== STAND_FOOTPRINT_W || h !== STAND_FOOTPRINT_H) return null;
  const halfW = Math.floor(w / 2);
  const halfH = Math.floor(h / 2);
  if (x - halfW < 0 || y - halfH < 0 || x + halfW >= mapW || y + halfH >= mapH) return null;
  return {
    tileX: x - mapW / 2 + 0.5,
    tileZ: y - mapH / 2 + 0.5,
    gridX: x,
    gridY: y,
    groundY: DEFAULT_GROUND_Y,
  };
}

/** 17×15 个格子的占位表。`gx/gz` 是**格子下标**（可直接进 `collision` 数组），
 *  `topY` 是地基顶面世界高度。 */
export function standFootprint(plot: StandPlot): StandTile[] {
  const tiles: StandTile[] = [];
  const cx = plot.gridX;
  const cz = plot.gridY;
  const halfW = Math.floor(STAND_FOOTPRINT_W / 2); // 8
  const halfH = Math.floor(STAND_FOOTPRINT_H / 2); // 7
  for (let gz = cz - halfH; gz <= cz + halfH; gz++) {
    for (let gx = cx - halfW; gx <= cx + halfW; gx++) {
      tiles.push({ gx, gz, topY: plot.groundY + DECK_LIFT });
    }
  }
  return tiles;
}
