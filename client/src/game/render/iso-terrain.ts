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
type HeightLookup = (x: number, y: number) => number;
interface BlockView {
  image: Phaser.GameObjects.Image;
  texture: string;
  phase: string | undefined;
}

function surfaceSignature(structures: Structures): string {
  return JSON.stringify(
    [...structures].map(([id, structure]) => [
      id,
      structure.tiles,
      structure.phase === 'built' || structure.phase === 'collapsing' ? 'solid' : structure.phase,
    ]),
  );
}

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
  private textureKeys = new Set<string>();
  private colors: ((gid: number) => number) | null = null;
  private lastMap: MapStatic | null = null;
  private lastGround: Uint16Array | undefined;
  private lastShape = '';
  private lastStructureSignature = '';
  private lastSurfaceSignature = '';
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

  /** Compare contents so same-array ground edits and empty snapshots both invalidate. */
  sync(map: MapStatic | null, structures: Structures): void {
    if (map === null) {
      if (this.lastMap !== null) this.clear();
      return;
    }
    const signature = JSON.stringify([...structures]);
    const groundUnchanged =
      map.ground === undefined
        ? this.lastGround === undefined
        : this.lastGround !== undefined &&
          map.ground.length === this.lastGround.length &&
          map.ground.every((gid, i) => gid === this.lastGround![i]);
    if (
      map === this.lastMap &&
      `${map.w},${map.h}` === this.lastShape &&
      signature === this.lastStructureSignature &&
      groundUnchanged
    )
      return;
    // built <-> collapsing changes opacity only. This keeps the fade running
    // without a terrain bake; TILE_CHANGED and geometry still use full redraws.
    if (
      map === this.lastMap &&
      `${map.w},${map.h}` === this.lastShape &&
      groundUnchanged &&
      surfaceSignature(structures) === this.lastSurfaceSignature
    ) {
      for (const structure of structures.values()) {
        if (structure.phase !== 'built' && structure.phase !== 'collapsing') continue;
        for (const [x, y] of structure.tiles) {
          const view = this.blocks.get(`${x},${y}`);
          if (view) this.phase(view, structure.phase);
        }
      }
      this.lastStructureSignature = signature;
      return;
    }
    this.redraw(map, structures);
  }

  redraw(map: MapStatic | null, structures: Structures): void {
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
    const overrides = new Map<string, string>();
    for (const structure of structures.values()) {
      if (structure.phase !== 'built' && structure.phase !== 'collapsing') continue;
      for (const [x, y] of structure.tiles) overrides.set(`${x},${y}`, structure.phase);
    }
    this.colors ??= this.readColors();
    const high: { x: number; y: number; h: number; color: number; phase: string | undefined }[] =
      [];
    // Diagonal order matches depthKey; later low faces cannot paint over nearer tiles.
    for (let diagonal = 0; diagonal < map.w + map.h - 1; diagonal++) {
      for (let y = Math.max(0, diagonal - map.w + 1); y <= Math.min(map.h - 1, diagonal); y++) {
        const x = diagonal - y;
        const phase = overrides.get(`${x},${y}`);
        const h = effectiveHeight(x, y, this.heightOf, structures);
        const color = this.colors(map.ground?.[y * map.w + x] ?? 0);
        if (h >= 2) {
          high.push({ x, y, h, color, phase });
        } else {
          const top = isoProject(x, y, h, bounds);
          if (this.atlas) this.atlas.paintBlock(ctx, top.sx, top.sy, h, color);
          else paintBlock(ctx, top.sx, top.sy, h, color);
        }
      }
    }
    if (this.scene.textures.exists(GROUND_KEY)) this.scene.textures.remove(GROUND_KEY);
    this.scene.textures.addCanvas(GROUND_KEY, canvas);
    if (this.ground === null) {
      this.ground = this.scene.add.image(0, 0, GROUND_KEY).setOrigin(0).setDepth(0);
    } else {
      this.ground.setTexture(GROUND_KEY);
    }
    const retained = new Set<string>();
    const usedTextures = new Set<string>();
    for (const { x, y, h, color, phase } of high) {
      const key = `${x},${y}`;
      const texture = `iso-block-${h}`;
      if (!this.scene.textures.exists(texture)) {
        const block = document.createElement('canvas');
        block.width = ISO.TW;
        block.height = h * ISO.HH + ISO.TH;
        const blockCtx = block.getContext('2d');
        if (blockCtx === null) continue;
        if (this.atlas) this.atlas.paintBlock(blockCtx, ISO.TW / 2, ISO.TH / 2, h);
        else paintBlock(blockCtx, ISO.TW / 2, ISO.TH / 2, h, 0xffffff);
        this.scene.textures.addCanvas(texture, block);
        this.textureKeys.add(texture);
      }
      let view = this.blocks.get(key);
      const isNew = view === undefined;
      if (view === undefined) {
        const base = isoProject(x, y, 0, bounds);
        const image = this.scene.add
          .image(base.sx, base.sy + ISO.TH / 2, texture)
          .setOrigin(0.5, 1);
        view = { image, texture, phase };
        this.blocks.set(key, view);
      } else if (view.texture !== texture) {
        view.image.setTexture(texture);
        view.texture = texture;
      }
      const base = isoProject(x, y, 0, bounds);
      view.image.setPosition(base.sx, base.sy + ISO.TH / 2);
      view.image.setDisplaySize(ISO.TW, h * ISO.HH + ISO.TH).setDepth(depthKey(x, y));
      view.image.setTint(color);
      this.phase(view, phase, isNew);
      retained.add(key);
      usedTextures.add(texture);
    }
    for (const [key, view] of this.blocks) {
      if (retained.has(key)) continue;
      this.transitions.delete(view.image);
      view.image.destroy();
      this.blocks.delete(key);
    }
    for (const key of this.textureKeys) {
      if (usedTextures.has(key)) continue;
      this.scene.textures.remove(key);
      this.textureKeys.delete(key);
    }
    this.syncRubble(map, structures, overrides, bounds);
    this.lastMap = map;
    this.lastShape = `${map.w},${map.h}`;
    this.lastGround = map.ground?.slice();
    this.lastStructureSignature = JSON.stringify([...structures]);
    this.lastSurfaceSignature = surfaceSignature(structures);
  }

  private syncRubble(
    map: MapStatic,
    structures: Structures,
    active: ReadonlyMap<string, string>,
    bounds: ReturnType<typeof screenBounds>,
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
        const top = isoProject(x, y, effectiveHeight(x, y, this.heightOf, structures), bounds);
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
    for (const key of this.textureKeys) this.scene.textures.remove(key);
    this.textureKeys.clear();
    if (this.scene.textures.exists(GROUND_KEY)) this.scene.textures.remove(GROUND_KEY);
    this.lastMap = null;
    this.lastGround = undefined;
    this.lastShape = '';
    this.lastStructureSignature = '';
    this.lastSurfaceSignature = '';
  }

  destroy(): void {
    this.clear();
    this.colors = null;
  }
}
