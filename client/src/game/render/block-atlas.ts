import type Phaser from 'phaser';
import { ISO } from './iso';

export const BLOCK_ATLAS_KEY = 'linhe-block-atlas';
export const BLOCK_ATLAS_META_KEY = 'linhe-block-atlas-meta';
const TILE = 16;
const COLS = 4;
const ROWS = 3;
const ROLES = ['water', 'ground', 'building', 'canopy'] as const;
type Face = 'top' | 'left' | 'right';

export function atlasFrame(height: number, face: Face) {
  const role = Number.isFinite(height) ? Math.max(0, Math.min(3, Math.floor(height))) : 1;
  return {
    x: role * TILE,
    y: { top: 0, left: 1, right: 2 }[face] * TILE,
    width: TILE,
    height: TILE,
  };
}

/** Turn role-colored pixels into neutral masks. Tint then retains each cell's
 * original hue, rather than multiplying it by the representative role color.
 */
export function neutralizeAtlas(
  pixels: Uint8ClampedArray,
  colors: readonly number[],
): Uint8ClampedArray {
  const mask = new Uint8ClampedArray(pixels.length);
  for (let i = 0; i < pixels.length; i += 4) {
    const role = Math.floor(((i / 4) % (COLS * TILE)) / TILE);
    const base = colors[role]!;
    const peak = Math.max(1, base >> 16, (base >> 8) & 255, base & 255);
    const gray = Math.min(
      255,
      Math.round((Math.max(pixels[i]!, pixels[i + 1]!, pixels[i + 2]!) / peak) * 255),
    );
    mask.set([gray, gray, gray, pixels[i + 3]!], i);
  }
  return mask;
}

/** One mask atlas and one reusable tint scratch canvas, never one per color. */
export class BlockAtlas {
  private constructor(
    private mask: HTMLCanvasElement,
    private scratch: HTMLCanvasElement,
    private tintCtx: CanvasRenderingContext2D,
  ) {}

  static fromScene(scene: Phaser.Scene): BlockAtlas | null {
    if (!scene.textures.exists(BLOCK_ATLAS_KEY)) return null;
    const data: unknown = scene.cache?.json.get(BLOCK_ATLAS_META_KEY);
    if (typeof data !== 'object' || data === null || !('base_colors' in data)) return null;
    const palette = data.base_colors;
    if (typeof palette !== 'object' || palette === null) return null;
    const colors = ROLES.map((role) => (palette as Record<string, unknown>)[role]);
    if (
      !colors.every(
        (color) =>
          typeof color === 'number' && Number.isInteger(color) && color > 0 && color <= 0xffffff,
      )
    )
      return null;
    const source = scene.textures.get(BLOCK_ATLAS_KEY).getSourceImage() as HTMLImageElement;
    if (source.width !== COLS * TILE || source.height !== ROWS * TILE) return null;
    const mask = document.createElement('canvas');
    mask.width = COLS * TILE;
    mask.height = ROWS * TILE;
    const ctx = mask.getContext('2d', { willReadFrequently: true });
    if (ctx === null) return null;
    ctx.drawImage(source, 0, 0);
    const imageData = ctx.getImageData(0, 0, mask.width, mask.height);
    imageData.data.set(neutralizeAtlas(imageData.data, colors as number[]));
    ctx.putImageData(imageData, 0, 0);
    const scratch = document.createElement('canvas');
    scratch.width = TILE;
    scratch.height = TILE;
    const tintCtx = scratch.getContext('2d', { willReadFrequently: true });
    return tintCtx === null ? null : new BlockAtlas(mask, scratch, tintCtx);
  }

  paintBlock(
    ctx: CanvasRenderingContext2D,
    sx: number,
    sy: number,
    height: number,
    tint?: number,
  ): void {
    const hw = ISO.TW / 2,
      hh = ISO.TH / 2,
      drop = height * ISO.HH;
    if (height > 0) {
      this.face(
        ctx,
        height,
        'left',
        [sx - hw, sy, sx, sy + hh, sx, sy + hh + drop, sx - hw, sy + drop],
        tint,
      );
      this.face(
        ctx,
        height,
        'right',
        [sx, sy + hh, sx + hw, sy, sx + hw, sy + drop, sx, sy + hh + drop],
        tint,
      );
    }
    this.face(ctx, height, 'top', [sx, sy - hh, sx + hw, sy, sx, sy + hh, sx - hw, sy], tint);
  }

  private face(
    ctx: CanvasRenderingContext2D,
    height: number,
    face: Face,
    p: number[],
    tint?: number,
  ): void {
    const frame = atlasFrame(height, face);
    let source = this.mask,
      sourceX = frame.x,
      sourceY = frame.y;
    if (tint !== undefined) {
      this.tintCtx.globalCompositeOperation = 'copy';
      this.tintCtx.drawImage(this.mask, frame.x, frame.y, TILE, TILE, 0, 0, TILE, TILE);
      this.tintCtx.globalCompositeOperation = 'multiply';
      this.tintCtx.fillStyle = `rgb(${tint >> 16},${(tint >> 8) & 255},${tint & 255})`;
      this.tintCtx.fillRect(0, 0, TILE, TILE);
      this.tintCtx.globalCompositeOperation = 'source-over';
      source = this.scratch;
      sourceX = 0;
      sourceY = 0;
    }
    ctx.save();
    ctx.imageSmoothingEnabled = false;
    ctx.transform(
      (p[2]! - p[0]!) / TILE,
      (p[3]! - p[1]!) / TILE,
      (p[6]! - p[0]!) / TILE,
      (p[7]! - p[1]!) / TILE,
      p[0]!,
      p[1]!,
    );
    ctx.drawImage(source, sourceX, sourceY, TILE, TILE, 0, 0, TILE, TILE);
    ctx.restore();
  }
}
