/** LRE-DT100 试车台地标的放置逻辑（纯函数，可单测，不碰 WebGL）。
 *
 * 为什么单独一层：`landmarks/lre-test-stand.js` 是**原样引入的外部 ES Module**
 * （r128 预览版，带自己的 canvas 程序化贴图、shader 与 24 个子部件），它不知道
 * 《临河镇》的格子高度表与坐标口径。这里只回答三个问题：放哪、占哪些格、
 * URL 怎么回滚；真正的建模与动画仍由那个模块负责。
 *
 * 坐标口径：`worldOf` 把格子 `(x, y)` 映射到世界 `(x - w/2 + 0.5, 0, y - h/2 + 0.5)`，
 * 而 vendored 模块的 `root.position.set(tileX, groundY, tileZ)` 直接吃世界坐标，
 * 所以 `tileX/tileZ` 必须已经是**世界坐标**，不是格子下标。`findStandPlot` 返回
 * 的就是世界坐标（已减去地图中心）。
 */

/** 占地面：vendored `getOccupiedTiles()` 从 `tileX-8` 到 `tileX+8`、`tileZ-7` 到
 *  `tileZ+7` 闭区间 —— 是 17×15，不是规格文档里写的 16×14。以代码为准。 */
export const STAND_FOOTPRINT_W = 17;
export const STAND_FOOTPRINT_H = 15;

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

/** 在高度表里找第一块 17×15 全平（高度 1）、且整块占地面都在图内的地。
 *
 * 扫描序固定为「先北后南、先西后东」，所以同一张图永远给出同一个点 —— 这是
 * 可复现的前提（C5：不许靠随机或 Map 迭代序选位置）。找不到返回 `null`，
 * 调用方据此静默不建（不能凭空垫一块地基出来，那是世界状态）。
 *
 * `heightOf(x, y)` 用**格子下标**，与 `WorldMirror` 的 `heightOf` 同口径。
 */
export function findStandPlot(
  mapW: number,
  mapH: number,
  heightOf: (x: number, y: number) => number,
): StandPlot | null {
  const halfW = Math.floor(STAND_FOOTPRINT_W / 2);
  const halfH = Math.floor(STAND_FOOTPRINT_H / 2);
  for (let cz = halfH; cz + halfH < mapH; cz++) {
    for (let cx = halfW; cx + halfW < mapW; cx++) {
      let flat = true;
      for (let y = cz - halfH; y <= cz + halfH && flat; y++) {
        for (let x = cx - halfW; x <= cx + halfW; x++) {
          if (heightOf(x, y) !== DEFAULT_GROUND_Y) {
            flat = false;
            break;
          }
        }
      }
      if (flat) {
        return {
          tileX: cx - mapW / 2 + 0.5,
          tileZ: cz - mapH / 2 + 0.5,
          gridX: cx,
          gridY: cz,
          groundY: DEFAULT_GROUND_Y,
        };
      }
    }
  }
  return null;
}

/** 地标开关（`?landmark=0` 回滚）。**默认开** —— 与 `avatars3dFromSearch`
 *  同一套「精确值才回滚」口径：只有精确的 `"0"` 关掉，拼写错误保持默认。 */
export function landmarkFromSearch(search: string): boolean {
  return new URLSearchParams(search).get('landmark') !== '0';
}
