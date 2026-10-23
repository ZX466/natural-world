import type Phaser from 'phaser';
import type { MapStatic, WorldMirror } from '../world-mirror';
import { ISO, depthKey, isoProject, screenBounds } from './iso';

const GROUND_KEY = 'iso-ground-composite';
const TILESET_KEY = 'god-town-16';
const TILE = 16;
// Structures may replace their ground gid with 0. No source pixels exist then;
// use the same deterministic timber fallback as build_height_map.py.
const FALLBACK_COLOR = 0x6b4f2a;
type Structures = WorldMirror['structures'];
type HeightLookup = (x: number, y: number) => number;

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

/** V1 terrain only: one low canvas, coordinate-keyed high Image pool.
 * Actors, camera, picking and the separate structure graphics stay outside it.
 */
export class IsoTerrain {
  private ground: Phaser.GameObjects.Image | null = null;
  private blocks = new Map<string, { image: Phaser.GameObjects.Image; texture: string }>();
  private textureKeys = new Set<string>();
  private colors: ((gid: number) => number) | null = null;
  private lastMap: MapStatic | null = null;
  private lastGround: Uint16Array | undefined;
  private lastShape = '';
  private lastStructures = '';

  constructor(
    private scene: Phaser.Scene,
    private heightOf: HeightLookup,
  ) {}

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
      signature === this.lastStructures &&
      groundUnchanged
    )
      return;
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
    const ctx = canvas.getContext('2d');
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
        const h = phase === undefined ? this.heightOf(x, y) : 2;
        const color = this.colors(map.ground?.[y * map.w + x] ?? 0);
        if (h >= 2) {
          high.push({ x, y, h, color, phase });
        } else {
          const top = isoProject(x, y, h, bounds);
          paintBlock(ctx, top.sx, top.sy, h, color);
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
      const texture = `iso-block-${h}-${color.toString(16)}`;
      if (!this.scene.textures.exists(texture)) {
        const block = document.createElement('canvas');
        block.width = ISO.TW;
        block.height = h * ISO.HH + ISO.TH;
        const blockCtx = block.getContext('2d');
        if (blockCtx === null) continue;
        paintBlock(blockCtx, ISO.TW / 2, ISO.TH / 2, h, color);
        this.scene.textures.addCanvas(texture, block);
        this.textureKeys.add(texture);
      }
      let view = this.blocks.get(key);
      if (view === undefined) {
        const base = isoProject(x, y, 0, bounds);
        const image = this.scene.add
          .image(base.sx, base.sy + ISO.TH / 2, texture)
          .setOrigin(0.5, 1);
        view = { image, texture };
        this.blocks.set(key, view);
      } else if (view.texture !== texture) {
        view.image.setTexture(texture);
        view.texture = texture;
      }
      const base = isoProject(x, y, 0, bounds);
      view.image.setPosition(base.sx, base.sy + ISO.TH / 2);
      view.image.setDisplaySize(ISO.TW, h * ISO.HH + ISO.TH).setDepth(depthKey(x, y));
      view.image.setAlpha(phase === 'collapsing' ? 0.5 : phase === 'built' ? 0.92 : 1);
      retained.add(key);
      usedTextures.add(texture);
    }
    for (const [key, view] of this.blocks) {
      if (retained.has(key)) continue;
      view.image.destroy();
      this.blocks.delete(key);
    }
    for (const key of this.textureKeys) {
      if (usedTextures.has(key)) continue;
      this.scene.textures.remove(key);
      this.textureKeys.delete(key);
    }
    this.lastMap = map;
    this.lastShape = `${map.w},${map.h}`;
    this.lastGround = map.ground?.slice();
    this.lastStructures = JSON.stringify([...structures]);
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
    this.ground?.destroy();
    this.ground = null;
    for (const view of this.blocks.values()) view.image.destroy();
    this.blocks.clear();
    for (const key of this.textureKeys) this.scene.textures.remove(key);
    this.textureKeys.clear();
    if (this.scene.textures.exists(GROUND_KEY)) this.scene.textures.remove(GROUND_KEY);
    this.lastMap = null;
    this.lastGround = undefined;
    this.lastShape = '';
    this.lastStructures = '';
  }

  destroy(): void {
    this.clear();
    this.colors = null;
  }
}
