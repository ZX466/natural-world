import type Phaser from 'phaser';
import type { MapStatic, WorldMirror } from '../world-mirror';
import { ISO, depthKey, effectiveHeight, isoProject, screenBounds } from './iso';
import { BlockAtlas } from './block-atlas';

const GROUND_KEY = 'iso-ground-composite';
const TILESET_KEY = 'god-town-16';
const TILE = 16;
// Structures may replace their ground gid with 0. No source pixels exist then;
// use the same deterministic timber fallback as build_height_map.py.
const FALLBACK_COLOR = 0x6b4f2a;
type Structures = WorldMirror['structures'];
type Edits = WorldMirror['voxelEdits'];
const NO_EDITS: Edits = new Map();
type HeightLookup = (x: number, y: number) => number;
interface BlockView {
  image: Phaser.GameObjects.Image;
  texture: string;
  phase: string | undefined;
}
interface SurfaceCell {
  x: number;
  y: number;
  h: number;
  color: number;
  phase: string | undefined;
  rubble: boolean;
  scar: boolean;
}
type Rect = { left: number; top: number; right: number; bottom: number };

export function sampleTileColor(
  data: Uint8ClampedArray,
  w: number,
  h: number,
  gid: number,
): number {
  const cols = Math.floor(w / TILE);
  if (!Number.isInteger(gid) || gid <= 0 || gid > cols * Math.floor(h / TILE))
    return FALLBACK_COLOR;
  const sx = ((gid - 1) % cols) * TILE + 6;
  const sy = Math.floor((gid - 1) / cols) * TILE + 6;
  let r = 0,
    g = 0,
    b = 0;
  for (let y = sy; y < sy + 4; y++) {
    for (let x = sx; x < sx + 4; x++) {
      const i = (y * w + x) * 4;
      r += data[i]!;
      g += data[i + 1]!;
      b += data[i + 2]!;
    }
  }
  return (Math.floor(r / 16) << 16) | (Math.floor(g / 16) << 8) | Math.floor(b / 16);
}

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
    if (initial) view.image.setAlpha(opacity);
    else if (view.phase !== phase)
      this.transitions.set(view.image, { from: view.image.alpha, to: opacity, elapsed: 0 });
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
    const overrides = new Map<string, string>();
    const ruins = new Set<string>();
    for (const structure of structures.values()) {
      if (structure.phase === 'rubble') {
        for (const [x, y] of structure.tiles) ruins.add(`${x},${y}`);
      }
      if (structure.phase !== 'built' && structure.phase !== 'collapsing') continue;
      for (const [x, y] of structure.tiles) overrides.set(`${x},${y}`, structure.phase);
    }
    this.colors ??= this.readColors();
    const previous = this.cells;
    const cells: SurfaceCell[] = [];
    let dirty: Rect | null = null;
    let changed = full;
    const includeLow = (cell: SurfaceCell) => {
      if (cell.h >= 2) return;
      const top = isoProject(cell.x, cell.y, cell.h, bounds);
      const bottom = top.sy + cell.h * ISO.HH + ISO.TH / 2;
      dirty = {
        left: Math.min(dirty?.left ?? Infinity, top.sx - ISO.TW / 2 - 1),
        top: Math.min(dirty?.top ?? Infinity, top.sy - ISO.TH / 2 - 1),
        right: Math.max(dirty?.right ?? -Infinity, top.sx + ISO.TW / 2 + 1),
        bottom: Math.max(dirty?.bottom ?? -Infinity, bottom + 1),
      };
    };
    for (let y = 0; y < map.h; y++) {
      for (let x = 0; x < map.w; x++) {
        const key = `${x},${y}`;
        const phase = overrides.get(key);
        const h = effectiveHeight(x, y, this.heightOf, structures, edits);
        const color =
          edits.has(key) && phase === undefined
            ? 0x8f8055
            : this.colors(map.ground?.[y * map.w + x] ?? 0);
        const cell = {
          x,
          y,
          h,
          color,
          phase,
          rubble: phase === undefined && ruins.has(key),
          scar: phase === undefined && h > 0 && edits.get(key)?.action === 'dig',
        };
        cells.push(cell);
        const prior = full ? undefined : previous[y * map.w + x];
        if (prior?.h !== h || prior.color !== color) {
          if (prior) includeLow(prior);
          includeLow(cell);
          changed = true;
        }
        if (prior?.phase !== phase || prior?.rubble !== cell.rubble || prior?.scar !== cell.scar)
          changed = true;
      }
    }
    this.lastVersion = version;
    if (!changed) return;
    this.cells = cells;
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
      if (cell.h < 2) continue;
      retained.add(`${cell.x},${cell.y}`);
      const prior = full ? undefined : previous[cell.y * map.w + cell.x];
      if (prior?.h !== cell.h || prior.color !== cell.color || prior.phase !== cell.phase) {
        this.syncBlock(cell, bounds);
      }
    }
    for (const [key, view] of this.blocks) {
      if (retained.has(key)) continue;
      this.transitions.delete(view.image);
      view.image.destroy();
      this.blocks.delete(key);
    }
    this.syncRubble(map, structures, overrides, bounds, edits);
    this.syncScars(map, structures, bounds, edits);
    this.lastMap = map;
    this.lastWidth = map.w;
    this.lastHeight = map.h;
  }

  private syncBlock(
    { x, y, h, color, phase }: SurfaceCell,
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
    let view = this.blocks.get(key);
    const isNew = view === undefined;
    const base = isoProject(x, y, 0, bounds);
    if (view === undefined) {
      const image = this.scene.add.image(base.sx, base.sy + ISO.TH / 2, texture).setOrigin(0.5, 1);
      view = { image, texture, phase };
      this.blocks.set(key, view);
    } else if (view.texture !== texture) {
      view.image.setTexture(texture);
      view.texture = texture;
    }
    view.image.setPosition(base.sx, base.sy + ISO.TH / 2);
    view.image.setDisplaySize(ISO.TW, h * ISO.HH + ISO.TH).setDepth(depthKey(x, y));
    view.image.setTint(color);
    this.phase(view, phase, isNew);
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
        if (cell.h >= 2) continue;
        const top = isoProject(x, y, cell.h, bounds);
        if (this.atlas) this.atlas.paintBlock(ctx, top.sx, top.sy, cell.h, cell.color);
        else paintBlock(ctx, top.sx, top.sy, cell.h, cell.color);
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

  /** Mark raised dug surfaces only; a cell lowered to zero has no floating scar. */
  private syncScars(
    map: MapStatic,
    structures: Structures,
    bounds: ReturnType<typeof screenBounds>,
    edits: Edits,
  ): void {
    const retained = new Set<string>();
    const active = new Set<string>();
    for (const structure of structures.values()) {
      if (structure.phase !== 'built' && structure.phase !== 'collapsing') continue;
      for (const [x, y] of structure.tiles) active.add(`${x},${y}`);
    }
    for (const [key, edit] of edits) {
      if (edit.action !== 'dig') continue;
      const { x, y } = edit;
      if (x < 0 || y < 0 || x >= map.w || y >= map.h) continue;
      if (active.has(key) || retained.has(key)) continue;
      const height = effectiveHeight(x, y, this.heightOf, structures, edits);
      if (height === 0) continue;
      let marker = this.scars.get(key);
      if (marker === undefined) {
        marker = this.scene.add.graphics();
        this.scars.set(key, marker);
      }
      const top = isoProject(x, y, height, bounds);
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
    if (!this.scene.textures.exists(TILESET_KEY)) return () => FALLBACK_COLOR;
    const source = this.scene.textures.get(TILESET_KEY).getSourceImage() as HTMLImageElement;
    const canvas = document.createElement('canvas');
    canvas.width = source.width;
    canvas.height = source.height;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (ctx === null) return () => FALLBACK_COLOR;
    ctx.drawImage(source, 0, 0);
    const pixels = ctx.getImageData(0, 0, source.width, source.height).data;
    const cached = new Map<number, number>();
    return (gid) => {
      let color = cached.get(gid);
      if (color === undefined) {
        color = sampleTileColor(pixels, source.width, source.height, gid);
        cached.set(gid, color);
      }
      return color;
    };
  }

  private clear(): void {
    this.transitions.clear();
    this.ground?.destroy();
    this.ground = null;
    for (const view of this.blocks.values()) view.image.destroy();
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
