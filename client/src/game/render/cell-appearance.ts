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

/** Edited cells are shown in material colours rather than their source tile.
 * Index is the cell height, so a dug-out hole (h=0) keeps the water tone. */
export const EDIT_COLORS: readonly number[] = [
  0x8f8055,
  0x8f8055,
  0x8a8880,
  FALLBACK_COLOR,
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
  /** Height-1 but not walkable: the bank glyph at a water edge. */
  readonly bank: boolean;
  /** The player has edited this cell. */
  readonly edited: boolean;
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
  const cells: CellAppearance[] = [];
  for (let y = 0; y < map.h; y++) {
    for (let x = 0; x < map.w; x++) {
      const key = `${x},${y}`;
      const phase = phases.get(key);
      const h = effectiveHeight(x, y, heightOf, structures, edits);
      const bank = h === 1 && map.collision[y * map.w + x] === 0;
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
        edited,
      });
    }
  }
  return cells;
}
