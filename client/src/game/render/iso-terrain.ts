import type Phaser from 'phaser';
import type { MapStatic } from '../world-mirror';
import { ISO, depthKey, effectiveHeight, isoProject, screenBounds, type VoxelEdits } from './iso';
import { BlockAtlas } from './block-atlas';
import { frameOf, paintTile } from './tile-projection';
import { createColorSampler, FALLBACK_COLOR } from './tile-color';
import {
  cellAppearances,
  structureOverrides,
  type CellAppearance,
  type Structures,
} from './cell-appearance';

const GROUND_KEY = 'iso-ground-composite';
const TILESET_KEY = 'god-town-16';
type Edits = VoxelEdits;
const NO_EDITS: Edits = new Map();
type HeightLookup = (x: number, y: number) => number;
interface BlockView {
  /** Shared-height mask with a per-cell tint: the two side faces. */
  side: Phaser.GameObjects.Image;
  /** The cell's own tileset frame as the top face; absent when the gid has no pixels. */
  top: Phaser.GameObjects.Image | null;
  texture: string;
  phase: string | undefined;
}
/** The shared per-cell rule; see `cell-appearance.ts` for why it is not local. */
type SurfaceCell = CellAppearance;
type Rect = { left: number; top: number; right: number; bottom: number };

function shade(color: number, factor: number): string {
  const channels = [color >> 16, (color >> 8) & 255, color & 255];
  return `rgb(${channels.map((c) => Math.floor(c * factor)).join(',')})`;
}

/** Center is the top face center. Both sides terminate at the ground baseline. */
function paintBlock(
  ctx: CanvasRenderingContext2D,
  sx: number,
  sy: number,
  h: number,
  color: number,
) {
  const hw = ISO.TW / 2,
    hh = ISO.TH / 2,
    drop = h * ISO.HH;
  const face = (points: number[], factor: number) => {
    ctx.beginPath();
    ctx.moveTo(points[0]!, points[1]!);
    for (let i = 2; i < points.length; i += 2) ctx.lineTo(points[i]!, points[i + 1]!);
    ctx.closePath();
    ctx.fillStyle = shade(color, factor);
    ctx.fill();
  };
  if (h > 0) {
    face([sx - hw, sy, sx, sy + hh, sx, sy + hh + drop, sx - hw, sy + drop], 0.75);
    face([sx, sy + hh, sx + hw, sy, sx + hw, sy + drop, sx, sy + hh + drop], 0.6);
  }
  face([sx, sy - hh, sx + hw, sy, sx, sy + hh, sx - hw, sy], 1);
}

/** One low canvas and one coordinate-keyed surface Image per high cell.
 * V2 reverse-merges active structures into that same pool, so a building is
 * never drawn again in a separate structureLayer. Rubble is a low marker on
 * the restored static surface, in the same depthKey pool as blocks and actors.
 */
export class IsoTerrain {
  private ground: Phaser.GameObjects.Image | null = null;
  private blocks = new Map<string, BlockView>();
  private rubble = new Map<string, Phaser.GameObjects.Graphics>();
  private scars = new Map<string, Phaser.GameObjects.Graphics>();
  private textureKeys = new Set<string>();
  private colors: ((gid: number) => number) | null = null;
  /** The tileset image itself, kept for the per-cell `drawImage` bake. */
  private sourceImage: CanvasImageSource | null = null;
  private sourceSize: { width: number; height: number } | null = null;
  private lastMap: MapStatic | null = null;
  private lastWidth = 0;
  private lastHeight = 0;
  private lastVersion: number | undefined;
  private cells: SurfaceCell[] = [];
  private groundCanvas: HTMLCanvasElement | null = null;
  private groundContext: CanvasRenderingContext2D | null = null;
  private groundTexture: Phaser.Textures.CanvasTexture | null = null;
  private atlas: BlockAtlas | null;
  private transitions = new Map<
    Phaser.GameObjects.Image | Phaser.GameObjects.Graphics,
    { from: number; to: number; elapsed: number }
  >();

  constructor(
    private scene: Phaser.Scene,
    private heightOf: HeightLookup,
  ) {
    this.atlas = BlockAtlas.fromScene(scene);
  }

  /** Phase fades use only supplied frame deltas, with no clock or random source. */
  advance(deltaMs: number): void {
    const dt = Number.isFinite(deltaMs) ? Math.max(0, deltaMs) : 0;
    for (const [target, fade] of this.transitions) {
      fade.elapsed = Math.min(240, fade.elapsed + dt);
      const t = fade.elapsed / 240;
      const eased = t * t * (3 - 2 * t);
      target.setAlpha(t === 1 ? fade.to : fade.from + (fade.to - fade.from) * eased);
      if (t === 1) this.transitions.delete(target);
    }
  }

  private phase(view: BlockView, phase: string | undefined, initial = false): void {
    const opacity = phase === 'collapsing' ? 0.5 : phase === 'built' ? 0.92 : 1;
    const targets = view.top === null ? [view.side] : [view.side, view.top];
    for (const image of targets) {
      if (initial) image.setAlpha(opacity);
      else if (view.phase !== phase)
        this.transitions.set(image, { from: image.alpha, to: opacity, elapsed: 0 });
    }
    view.phase = phase;
  }

  /** WorldScene supplies a mutation version: unchanged frames touch no terrain collections.
   * Unversioned callers can still explicitly sync mutable standalone maps.
   */
  sync(
    map: MapStatic | null,
    structures: Structures,
    edits: Edits = NO_EDITS,
    version?: number,
  ): void {
    if (map === null) {
      if (this.lastMap !== null) this.clear();
      return;
    }
    if (
      map === this.lastMap &&
      map.w === this.lastWidth &&
      map.h === this.lastHeight &&
      version !== undefined &&
      version === this.lastVersion
    )
      return;
    if (
      map !== this.lastMap ||
      map.w !== this.lastWidth ||
      map.h !== this.lastHeight ||
      this.groundContext === null
    ) {
      this.redraw(map, structures, edits, version);
      return;
    }
    this.updateSurface(map, structures, edits, version, false);
  }

  redraw(
    map: MapStatic | null,
    structures: Structures,
    edits: Edits = NO_EDITS,
    version?: number,
  ): void {
    if (map === null) {
      this.clear();
      return;
    }
    const bounds = screenBounds(map.w, map.h);
    const canvas = document.createElement('canvas');
    canvas.width = bounds.width;
    canvas.height = bounds.height;
    // Atlas tinting copies a tiny mutable canvas thousands of times. Keep the
    // one-shot bake on CPU to avoid GPU synchronization for every face copy.
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (ctx === null) return;
    this.groundCanvas = canvas;
    this.groundContext = ctx;
    this.updateSurface(map, structures, edits, version, true);
  }

  private updateSurface(
    map: MapStatic,
    structures: Structures,
    edits: Edits,
    version: number | undefined,
    full: boolean,
  ): void {
    const bounds = screenBounds(map.w, map.h);
    this.colors ??= this.readColors();
    const previous = this.cells;
    // The per-cell rule is shared with the three.js renderer; see
    // `cell-appearance.ts`. Keeping it here would let the two pictures drift.
    const cells = cellAppearances(map, structures, edits, this.heightOf, this.colors);
    let dirty: Rect | null = null;
    let changed = full;
    // `drawH` 而不是 `h`：土坎逻辑高度 1 但画成 2 格矮墙，按逻辑高度算脏区
    // 会把它的上半截留在旧图里。
    const includeLow = (cell: SurfaceCell) => {
      if (cell.drawH >= 2) return;
      const top = isoProject(cell.x, cell.y, cell.drawH, bounds);
      const bottom = top.sy + cell.drawH * ISO.HH + ISO.TH / 2;
      dirty = {
        left: Math.min(dirty?.left ?? Infinity, top.sx - ISO.TW / 2 - 1),
        top: Math.min(dirty?.top ?? Infinity, top.sy - ISO.TH / 2 - 1),
        right: Math.max(dirty?.right ?? -Infinity, top.sx + ISO.TW / 2 + 1),
        bottom: Math.max(dirty?.bottom ?? -Infinity, bottom + 1),
      };
    };
    for (let index = 0; index < cells.length; index++) {
      const cell = cells[index]!;
      const prior = full ? undefined : previous[index];
      if (
        prior?.h !== cell.h ||
        prior.drawH !== cell.drawH ||
        prior.color !== cell.color ||
        prior.edited !== cell.edited
      ) {
        if (prior) includeLow(prior);
        includeLow(cell);
        changed = true;
      }
      if (
        prior?.phase !== cell.phase ||
        prior?.rubble !== cell.rubble ||
        prior?.scar !== cell.scar ||
        prior?.bank !== cell.bank
      )
        changed = true;
    }
    this.lastVersion = version;
    if (!changed) return;
    this.cells = [...cells];
    if (full || dirty !== null) this.paintGround(map, bounds, full ? null : dirty);
    if (full) {
      if (this.scene.textures.exists(GROUND_KEY)) this.scene.textures.remove(GROUND_KEY);
      this.groundTexture = this.scene.textures.addCanvas(GROUND_KEY, this.groundCanvas!);
      if (this.ground === null) {
        this.ground = this.scene.add.image(0, 0, GROUND_KEY).setOrigin(0).setDepth(0);
      } else {
        this.ground.setTexture(GROUND_KEY);
      }
    }
    const retained = new Set<string>();
    for (const cell of cells) {
      // 土坎按 `drawH`（2）走方块视图：和石料/木料同形，才看得出过不去。
      if (cell.drawH < 2) continue;
      retained.add(`${cell.x},${cell.y}`);
      const prior = full ? undefined : previous[cell.y * map.w + cell.x];
      if (
        prior?.drawH !== cell.drawH ||
        prior.color !== cell.color ||
        prior.phase !== cell.phase ||
        prior.edited !== cell.edited
      ) {
        this.syncBlock(cell, map, bounds);
      }
    }
    for (const [key, view] of this.blocks) {
      if (retained.has(key)) continue;
      this.destroyBlock(view);
      this.blocks.delete(key);
    }
    this.syncRubble(map, structures, structureOverrides(structures).phases, bounds, edits);
    this.syncScars(cells, bounds);
    this.lastMap = map;
    this.lastWidth = map.w;
    this.lastHeight = map.h;
  }

  private syncBlock(
    { x, y, drawH: h, color, phase }: SurfaceCell,
    map: MapStatic,
    bounds: ReturnType<typeof screenBounds>,
  ) {
    const key = `${x},${y}`;
    const texture = `iso-block-${h}`;
    if (!this.scene.textures.exists(texture)) {
      const block = document.createElement('canvas');
      block.width = ISO.TW;
      block.height = h * ISO.HH + ISO.TH;
      const ctx = block.getContext('2d');
      if (ctx === null) return;
      if (this.atlas) this.atlas.paintBlock(ctx, ISO.TW / 2, ISO.TH / 2, h);
      else paintBlock(ctx, ISO.TW / 2, ISO.TH / 2, h, 0xffffff);
      this.scene.textures.addCanvas(texture, block);
      this.textureKeys.add(texture);
    }
    const topFrame = this.ensureTileFrame(map.ground?.[y * map.w + x] ?? 0);
    let view = this.blocks.get(key);
    const isNew = view === undefined;
    const base = isoProject(x, y, 0, bounds);
    if (view === undefined) {
      const side = this.scene.add.image(base.sx, base.sy + ISO.TH / 2, texture).setOrigin(0.5, 1);
      // The top is created by the branch below, so a later gid change reuses one path.
      view = { side, top: null, texture, phase };
      this.blocks.set(key, view);
    } else if (view.texture !== texture) {
      view.side.setTexture(texture);
      view.texture = texture;
    }
    view.side.setPosition(base.sx, base.sy + ISO.TH / 2);
    // The mask already contains its own top face, so the side keeps its full height.
    view.side.setDisplaySize(ISO.TW, h * ISO.HH + ISO.TH).setDepth(depthKey(x, y) - 0.01);
    view.side.setTint(color);
    if (topFrame === null) {
      // A gid that was invalid can become valid in place; drop the stale top.
      if (view.top !== null) {
        this.transitions.delete(view.top);
        view.top.destroy();
        view.top = null;
      }
    } else if (view.top === null) {
      view.top = this.scene.add
        .image(base.sx, base.sy - h * ISO.HH, TILESET_KEY, topFrame)
        .setOrigin(0.5, 0.5)
        .setDisplaySize(ISO.TW, ISO.TH)
        .setDepth(depthKey(x, y));
      view.top.setAlpha(view.side.alpha);
    } else {
      view.top
        .setTexture(TILESET_KEY, topFrame)
        .setPosition(base.sx, base.sy - h * ISO.HH)
        .setDisplaySize(ISO.TW, ISO.TH)
        .setDepth(depthKey(x, y));
    }
    this.phase(view, phase, isNew);
  }

  /** Register the tileset frame for a gid on first use, on both the full and the
   * incremental path. `Texture.add` records metadata only — no pixel copy. */
  private ensureTileFrame(gid: number): string | null {
    if (gid <= 0 || this.sourceSize === null) return null;
    const name = `tile-${gid}`;
    const texture = this.scene.textures.get(TILESET_KEY);
    if (texture.has(name)) return name;
    const frame = frameOf(gid, this.sourceSize);
    if (frame.w === 0) return null;
    texture.add(name, 0, frame.x, frame.y, frame.w, frame.h);
    return name;
  }

  /** Repaint every overlapping low block, clipped to the old/new footprint union.
   * The inverse bounds limit enumeration to nearby diagonals and columns, while
   * the original diagonal/row order preserves both background and foreground.
   */
  private paintGround(map: MapStatic, bounds: ReturnType<typeof screenBounds>, dirty: Rect | null) {
    const ctx = this.groundContext!;
    if (dirty) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(dirty.left, dirty.top, dirty.right - dirty.left, dirty.bottom - dirty.top);
      ctx.clip();
      ctx.clearRect(dirty.left, dirty.top, dirty.right - dirty.left, dirty.bottom - dirty.top);
    }
    const hw = ISO.TW / 2,
      hh = ISO.TH / 2;
    const first = dirty ? Math.max(0, Math.ceil((dirty.top - bounds.originY - hh) / hh)) : 0;
    const last = dirty
      ? Math.min(map.w + map.h - 2, Math.floor((dirty.bottom - bounds.originY + ISO.HH + hh) / hh))
      : map.w + map.h - 2;
    for (let diagonal = first; diagonal <= last; diagonal++) {
      const minY = Math.max(
        0,
        diagonal - map.w + 1,
        dirty ? Math.ceil((bounds.originX + diagonal * hw - dirty.right - hw) / ISO.TW) : 0,
      );
      const maxY = Math.min(
        map.h - 1,
        diagonal,
        dirty ? Math.floor((bounds.originX + diagonal * hw - dirty.left + hw) / ISO.TW) : map.h - 1,
      );
      for (let y = minY; y <= maxY; y++) {
        const x = diagonal - y;
        const cell = this.cells[y * map.w + x]!;
        // 土坎按 `drawH` 走方块视图，这里不贴地面图。
        if (cell.drawH >= 2) continue;
        const top = isoProject(x, y, cell.drawH, bounds);
        if (dirty) {
          // Diamond bounding box: the top face plus the column below it.
          const left = top.sx - hw,
            right = top.sx + hw;
          const up = top.sy - hh - cell.drawH * ISO.HH,
            down = top.sy + hh;
          if (right < dirty.left || left > dirty.right || down < dirty.top || up > dirty.bottom)
            continue;
        }
        const gid = map.ground?.[y * map.w + x] ?? 0;
        const painted =
          !cell.edited &&
          this.sourceImage !== null &&
          this.sourceSize !== null &&
          paintTile(ctx, this.sourceImage, top.sx, top.sy, gid, this.sourceSize);
        if (!painted) {
          if (this.atlas) this.atlas.paintBlock(ctx, top.sx, top.sy, cell.drawH, cell.color);
          else paintBlock(ctx, top.sx, top.sy, cell.drawH, cell.color);
        }
      }
    }
    if (dirty) {
      ctx.restore();
      this.groundTexture?.refresh();
    }
  }

  private syncRubble(
    map: MapStatic,
    structures: Structures,
    active: ReadonlyMap<string, string>,
    bounds: ReturnType<typeof screenBounds>,
    edits: Edits,
  ): void {
    const retained = new Set<string>();
    for (const structure of structures.values()) {
      if (structure.phase !== 'rubble') continue;
      for (const [x, y] of structure.tiles) {
        const key = `${x},${y}`;
        if (
          !Number.isInteger(x) ||
          !Number.isInteger(y) ||
          x < 0 ||
          y < 0 ||
          x >= map.w ||
          y >= map.h ||
          active.has(key) ||
          retained.has(key)
        )
          continue;
        let marker = this.rubble.get(key);
        if (marker === undefined) {
          marker = this.scene.add.graphics();
          marker.setAlpha(0);
          this.transitions.set(marker, { from: 0, to: 1, elapsed: 0 });
          this.rubble.set(key, marker);
        }
        const top = isoProject(
          x,
          y,
          effectiveHeight(x, y, this.heightOf, structures, edits),
          bounds,
        );
        marker.setPosition(top.sx, top.sy).setDepth(depthKey(x, y));
        marker.clear();
        const face = (points: number[], color: number) => {
          marker.fillStyle(color, 0.5);
          marker.fillPoints(
            Array.from({ length: points.length / 2 }, (_, i) => ({
              x: points[i * 2]!,
              y: points[i * 2 + 1]!,
            })),
            true,
          );
        };
        const hw = ISO.TW / 2,
          hh = ISO.TH / 2,
          rise = ISO.HH / 4;
        // Quarter-height rubble rests on the restored surface; its opacity uses frame deltas.
        face([-hw, -rise, 0, hh - rise, 0, hh, -hw, 0], 0x503b1f);
        face([0, hh - rise, hw, -rise, hw, 0, 0, hh], 0x402f19);
        face([0, -hh - rise, hw, -rise, 0, hh - rise, -hw, -rise], FALLBACK_COLOR);
        retained.add(key);
      }
    }
    for (const [key, marker] of this.rubble) {
      if (retained.has(key)) continue;
      this.transitions.delete(marker);
      marker.destroy();
      this.rubble.delete(key);
    }
  }

  /** Only walkable dug surfaces get the inset diamond; a bank is its own block.
   * A cell lowered to zero has no floating scar; placed cells are their own marker.
   */
  private syncScars(cells: readonly SurfaceCell[], bounds: ReturnType<typeof screenBounds>): void {
    const retained = new Set<string>();
    for (const { x, y, h, scar } of cells) {
      if (!scar) continue;
      const key = `${x},${y}`;
      let marker = this.scars.get(key);
      if (marker === undefined) {
        marker = this.scene.add.graphics();
        this.scars.set(key, marker);
      }
      const top = isoProject(x, y, h, bounds);
      // Above its own block, below the actor standing on it (depthKey + 1).
      marker.setPosition(top.sx, top.sy).setDepth(depthKey(x, y) + 0.5);
      marker.clear();
      const hw = ISO.TW / 2,
        hh = ISO.TH / 2;
      marker.fillStyle(0x3f3020, 0.55);
      marker.fillPoints(
        [
          { x: 0, y: -hh / 2 },
          { x: hw / 2, y: 0 },
          { x: 0, y: hh / 2 },
          { x: -hw / 2, y: 0 },
        ],
        true,
      );
      retained.add(key);
    }
    for (const [key, marker] of this.scars) {
      if (retained.has(key)) continue;
      marker.destroy();
      this.scars.delete(key);
    }
  }

  private readColors(): (gid: number) => number {
    if (!this.scene.textures.exists(TILESET_KEY)) {
      this.sourceImage = null;
      this.sourceSize = null;
      return () => FALLBACK_COLOR;
    }
    const source = this.scene.textures.get(TILESET_KEY).getSourceImage() as HTMLImageElement;
    // The bake reads these; keeping them here avoids a texture lookup per cell.
    this.sourceImage = source;
    this.sourceSize = { width: source.width, height: source.height };
    const canvas = document.createElement('canvas');
    canvas.width = source.width;
    canvas.height = source.height;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (ctx === null) return () => FALLBACK_COLOR;
    ctx.drawImage(source, 0, 0);
    const pixels = ctx.getImageData(0, 0, source.width, source.height).data;
    return createColorSampler(pixels, source.width, source.height);
  }

  private destroyBlock(view: BlockView): void {
    this.transitions.delete(view.side);
    view.side.destroy();
    if (view.top !== null) {
      this.transitions.delete(view.top);
      view.top.destroy();
    }
  }

  private clear(): void {
    this.transitions.clear();
    this.ground?.destroy();
    this.ground = null;
    for (const view of this.blocks.values()) this.destroyBlock(view);
    this.blocks.clear();
    for (const marker of this.rubble.values()) marker.destroy();
    this.rubble.clear();
    for (const marker of this.scars.values()) marker.destroy();
    this.scars.clear();
    for (const key of this.textureKeys) this.scene.textures.remove(key);
    this.textureKeys.clear();
    if (this.scene.textures.exists(GROUND_KEY)) this.scene.textures.remove(GROUND_KEY);
    this.lastMap = null;
    this.lastWidth = 0;
    this.lastHeight = 0;
    this.lastVersion = undefined;
    this.cells = [];
    this.groundCanvas = null;
    this.groundContext = null;
    this.groundTexture = null;
  }

  destroy(): void {
    this.clear();
    this.colors = null;
  }
}
