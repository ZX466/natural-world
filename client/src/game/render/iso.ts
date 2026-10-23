/** V1 geometry. Logical TILE=16 stays independent of the rendered block size. */
export const ISO = { TW: 32, TH: 16, HH: 16 } as const;

export function screenBounds(w = 140, h = 100, maxH = 3) {
  const topMargin = Math.max(3, maxH) * ISO.HH + ISO.TH / 2;
  return {
    width: ((w + h) * ISO.TW) / 2,
    height: ((w + h) * ISO.TH) / 2 + topMargin + 64,
    originX: (h * ISO.TW) / 2,
    originY: topMargin,
  };
}

type Bounds = ReturnType<typeof screenBounds>;
const TOWN_BOUNDS = screenBounds();

/** Top face center; callers never add an origin or subtract the height again. */
export function isoProject(x: number, y: number, h = 0, bounds: Bounds = TOWN_BOUNDS) {
  return {
    sx: bounds.originX + ((x - y) * ISO.TW) / 2,
    sy: bounds.originY + ((x + y) * ISO.TH) / 2 - h * ISO.HH,
  };
}

/** Ground plane only. Shared diamond edges belong to the positive-axis cell.
 * Rounding both inverse axes is equivalent to |dx|/(TW/2)+|dy|/(TH/2) <= 1.
 * Map bounds and collision checks belong to the interaction caller (V2).
 */
export function isoUnproject(px: number, py: number, bounds: Bounds = TOWN_BOUNDS) {
  const dx = (px - bounds.originX) / (ISO.TW / 2);
  const dy = (py - bounds.originY) / (ISO.TH / 2);
  return { x: Math.floor((dx + dy) / 2 + 0.5), y: Math.floor((dy - dx) / 2 + 0.5) };
}

export function depthKey(x: number, y: number): number {
  return (x + y) * 1024 + y;
}

export interface HeightTable {
  readonly w: number;
  readonly h: number;
  readonly h_values: readonly number[];
}

export function heightOf(x: number, y: number, table?: HeightTable | null): number {
  if (
    !table ||
    !Number.isInteger(x) ||
    !Number.isInteger(y) ||
    x < 0 ||
    y < 0 ||
    x >= table.w ||
    y >= table.h
  )
    return 1;
  const height = table.h_values[y * table.w + x];
  return height !== undefined && Number.isInteger(height) && height >= 0 && height <= 3
    ? height
    : 1;
}

/** Validate the loaded JSON once and retain a snapshot, rather than mutable cache data. */
export function createHeightLookup(data: unknown): (x: number, y: number) => number {
  if (typeof data !== 'object' || data === null) return () => 1;
  const table = data as Partial<HeightTable>;
  if (
    !Number.isInteger(table.w) ||
    !Number.isInteger(table.h) ||
    table.w! <= 0 ||
    table.h! <= 0 ||
    !Array.isArray(table.h_values) ||
    table.h_values.length !== table.w! * table.h! ||
    !table.h_values.every((h) => Number.isInteger(h) && h >= 0 && h <= 3)
  )
    return () => 1;
  const snapshot = { w: table.w!, h: table.h!, h_values: [...table.h_values] };
  return (x, y) => heightOf(x, y, snapshot);
}
