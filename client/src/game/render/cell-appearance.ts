/** What one map cell looks like, decided once for every renderer.
 *
 * `iso-terrain.ts` (Phaser) and `three-terrain.ts` (three.js) must agree on
 * height, colour and phase, or the two pictures disagree about the same town.
 * The rule lives here so neither renderer can drift: it is pure, takes no
 * canvas, and needs no Phaser or three import.
 *
 * Extracted verbatim from `IsoTerrain.updateSurface`, which was the only
 * implementation until the three.js path existed.
 */

import type { MapStatic, VoxelEdit } from '../world-mirror';
import { effectiveHeight, type HeightLookup } from './iso';
import { FALLBACK_COLOR } from './tile-color';

export type VoxelEdits = ReadonlyMap<string, Pick<VoxelEdit, 'height' | 'action'>>;
export type Structures = ReadonlyMap<
  string,
  { readonly phase: string; readonly tiles: readonly (readonly [number, number])[] }
>;

/** The atlas's `water` role tone, also used for a cell dug down to h=0. */
export const WATER_COLOR = 0x5b7674;

/** Edited cells are shown in material colours rather than their source tile.
 *
 * Index is the cell height, matching `voxel_exec._HEIGHT_BY_MATERIAL`
 * (1 earth, 2 stone, 3 wood). Digging lowers the height by one, so the colour a
 * dug cell keeps is the layer it now exposes — wood 3→2 shows stone, stone 2→1
 * shows earth — which is what the height index already gives us.
 *
 * h=0 is water, not a hole in the ground: `blockTransform` draws it as the same
 * 0.06-thick slab as a lake, and a dig that reaches 0 clears collision. Painting
 * it earth made a dug-out cell read as untouched ground, so the block looked
 * like it had gone see-through instead of been dug away.
 *
 * Stone is the atlas's `building` role tone. A pale grey here (the old 0x8a8880
 * sat at luma 136, the 99th percentile of the whole frame) reads as the sky
 * showing through the terrain rather than as a block. */
export const EDIT_COLORS: readonly number[] = [
  WATER_COLOR, // h=0: a dug-out cell becomes water, not a hole
  0x8f8055, // earth
  0x5f5c43, // stone, same tone as the atlas building role
  FALLBACK_COLOR, // wood (timber)
] as const;

export interface CellAppearance {
  readonly x: number;
  readonly y: number;
  /** Effective height 0..3, after structures and edits. */
  readonly h: number;
  /** 0xRRGGBB for the top face / the whole block. */
  readonly color: number;
  /** `built` / `collapsing` when a structure owns this cell. */
  readonly phase: string | undefined;
  /** Structure rubble: drawn as debris, not as a block. */
  readonly rubble: boolean;
  /** A dig scar on otherwise open ground. */
  readonly scar: boolean;
  /** Height-1 but not walkable: a bank, or earth the player just placed. */
  readonly bank: boolean;
  /** Height the renderers draw. Equals `h` except on a bank, which is lifted to
   * `BANK_RENDER_HEIGHT` so it reads as a wall instead of as open ground. */
  readonly drawH: number;
  /** The player has edited this cell. */
  readonly edited: boolean;
}

/** 土坎（高度 1、不可走）的渲染高度。
 *
 * 这类格子和可走平地**同高同色**（实测色差仅 2/255），只靠盒子本身分不出来：
 * 天然土坎看起来像能走的空地，玩家放下的土块看起来像空白。2026-11-10 用户裁定
 * 不再画斜纹记号，直接把格子抬成 2 格高的实心方块 —— 和石料/木料方块同形，
 * 一眼就是过不去。
 *
 * **逻辑高度仍是 1**：碰撞不可走、跳跃落点是服务端的 `height_at`、土坎 1→0
 * 仍是 earth 的唯一来源。渲染读 `drawH`，判定一律读 `h`。 */
export const BANK_RENDER_HEIGHT = 2;

/** 高度 1 且不可走、又不是静态结构占地面 ⇒ 抬成矮墙。
 *
 * 静态结构（试车台）占地面高度 1、碰撞 0，与土坎同形，但那是建筑地基：
 * 模型自己立在上面，抬起来会穿模。 */
export function isBankCell(
  map: MapStatic,
  staticTiles: ReadonlySet<string>,
  x: number,
  y: number,
  height: number,
): boolean {
  return height === 1 && map.collision[y * map.w + x] === 0 && !staticTiles.has(`${x},${y}`);
}

export type RenderHeightLookup = (x: number, y: number, height?: number) => number;

/** 逻辑高度 → 渲染高度。第三参可传已知的逻辑高度（跳跃起止高度来自服务端）。 */
export function renderHeightLookup(
  map: MapStatic,
  heightOf: (x: number, y: number) => number,
): RenderHeightLookup {
  const staticTiles = staticStructureTiles(map);
  return (x, y, height = heightOf(x, y)) =>
    isBankCell(map, staticTiles, x, y, height) ? BANK_RENDER_HEIGHT : height;
}

/** 同 `renderHeightLookup`，但按 `mapOf()` 的当前地图缓存占地面集合。
 *
 * 世界常在首帧快照之前就建好渲染层，地图会晚到；地图一换（重连取新图）
 * 缓存自动失效。`map.collision` 是就地改写的，闭包读到的是最新值。 */
export function cachedRenderHeightLookup(
  mapOf: () => MapStatic | null,
  heightOf: (x: number, y: number) => number,
): RenderHeightLookup {
  let cachedMap: MapStatic | null = null;
  let lookup: RenderHeightLookup | null = null;
  return (x, y, height) => {
    const map = mapOf();
    if (map === null) return height ?? heightOf(x, y);
    if (map !== cachedMap) {
      cachedMap = map;
      lookup = renderHeightLookup(map, heightOf);
    }
    return lookup!(x, y, height);
  };
}

/** 静态结构（服务端地图 `_structures`）的占地面展开成 `"x,y"` 集合。
 *
 * 这些格子在碰撞层里不可走、高度却仍是 1 —— 与「土坎」的判定条件完全重合。
 * 不排除的话，试车台脚下会被抬成一片矮墙，把建筑模型整个包住。
 * 动态结构（玩家建的房）走 `structureOverrides`，是另一条路。
 * 每个结构展开一次，14000 格的循环里只剩一次 Set 查询。 */
export function staticStructureTiles(map: MapStatic): ReadonlySet<string> {
  const tiles = new Set<string>();
  for (const anchor of Object.values(map.structures ?? {})) {
    // w/h 是闭区间跨度（17 → 中心 ±8），与 `getOccupiedTiles()` 同形。
    const halfW = Math.floor(anchor.w / 2);
    const halfH = Math.floor(anchor.h / 2);
    for (let y = anchor.y - halfH; y <= anchor.y + halfH; y++)
      for (let x = anchor.x - halfW; x <= anchor.x + halfW; x++) tiles.add(`${x},${y}`);
  }
  return tiles;
}

/** The cells a structure claims, plus the cells that are its rubble.
 *
 * `built` and `collapsing` structures raise the ground to h=2; `rubble` is
 * debris drawn under the block. Both sets are keyed `"x,y"` so the per-cell
 * loop is one map lookup instead of a scan over every structure. */
export function structureOverrides(structures: Structures): {
  readonly phases: ReadonlyMap<string, string>;
  readonly ruins: ReadonlySet<string>;
} {
  const phases = new Map<string, string>();
  const ruins = new Set<string>();
  for (const structure of structures.values()) {
    if (structure.phase === 'rubble') {
      for (const [x, y] of structure.tiles) ruins.add(`${x},${y}`);
    }
    if (structure.phase !== 'built' && structure.phase !== 'collapsing') continue;
    for (const [x, y] of structure.tiles) phases.set(`${x},${y}`, structure.phase);
  }
  return { phases, ruins };
}

/** Row-major appearance for the whole map.
 *
 * `sampleColor(gid)` turns a tileset gid into 0xRRGGBB; passing the identity
 * function would render raw gids, so callers always pass the sampler.
 * Structures and edits outrank the source tile, in that order. */
export function cellAppearances(
  map: MapStatic,
  structures: Structures,
  edits: VoxelEdits,
  heightOf: HeightLookup,
  sampleColor: (gid: number) => number,
): readonly CellAppearance[] {
  const { phases, ruins } = structureOverrides(structures);
  const staticTiles = staticStructureTiles(map);
  const cells: CellAppearance[] = [];
  for (let y = 0; y < map.h; y++) {
    for (let x = 0; x < map.w; x++) {
      const key = `${x},${y}`;
      const phase = phases.get(key);
      const h = effectiveHeight(x, y, heightOf, structures, edits);
      // 静态结构占地面不算土坎：它高度 1、碰撞 0，与土坎同形，但那是台体
      // 地基而不是可挖的土坎。建筑自己的模型由 three 层负责。
      const bank = isBankCell(map, staticTiles, x, y, h);
      const edited = edits.has(key);
      const color =
        edited && phase === undefined
          ? EDIT_COLORS[h]!
          : sampleColor(map.ground?.[y * map.w + x] ?? 0);
      cells.push({
        x,
        y,
        h,
        color,
        phase,
        rubble: phase === undefined && ruins.has(key),
        scar: phase === undefined && h === 1 && !bank && edits.get(key)?.action === 'dig',
        bank,
        drawH: bank ? BANK_RENDER_HEIGHT : h,
        edited,
      });
    }
  }
  return cells;
}
