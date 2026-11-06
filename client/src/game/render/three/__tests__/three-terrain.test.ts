import { expect, it } from 'vitest';
import { worldOf } from '../three-projection';
import {
  FACE_SHADE,
  WATER_THICKNESS,
  blockTransform,
  blockInstances,
  grainOf,
  layerOf,
  shadedBoxForTest,
  tinted,
} from '../three-terrain';

const W = 140;
const H = 100;

it('builds tall columns from unit cubes rather than stretching a face texture', () => {
  const instances = blockInstances([{ x: 10, y: 20, h: 3, color: 0xffffff }], W, H);
  expect(instances).toHaveLength(3);
  expect(instances.map((instance) => instance.scaleY)).toEqual([1, 1, 1]);
  expect(instances.map((instance) => instance.position.y)).toEqual([0.5, 1.5, 2.5]);
});

it('grain is deterministic, bounded, and not uniform', () => {
  const values = new Set<number>();
  for (let y = 0; y < 20; y++) {
    for (let x = 0; x < 20; x++) {
      const g = grainOf(x, y);
      // Bounded: the tint factor stays within ±8%.
      expect(g).toBeGreaterThanOrEqual(-0.5);
      expect(g).toBeLessThan(0.5);
      values.add(g);
    }
  }
  // A constant grain would make every block read as the same plastic colour.
  // 17 discrete shades is the design: enough to break up a flat field, few
  // enough that the town keeps one palette.
  expect(values.size).toBe(17);
  expect(grainOf(7, 11)).toBe(grainOf(7, 11));
});

it('neighbouring cells rarely share a shade', () => {
  // If the hash correlated with position, whole blocks of the map would read
  // as one flat colour — the failure this grain exists to prevent.
  let same = 0;
  let total = 0;
  for (let y = 0; y < 40; y++) {
    for (let x = 0; x < 40; x++) {
      total += 2;
      if (grainOf(x, y) === grainOf(x + 1, y)) same += 1;
      if (grainOf(x, y) === grainOf(x, y + 1)) same += 1;
    }
  }
  // 17 shades ⇒ ~5.9% by chance alone. Allow up to 12%.
  expect(same / total).toBeLessThan(0.12);
});

it('tinted shifts brightness by at most 8% and clamps at the ends', () => {
  // 0x808080 = 128 on every channel; ±8% is 117.76..138.24.
  for (let y = 0; y < 12; y++) {
    for (let x = 0; x < 12; x++) {
      const c = tinted(0x808080, x, y);
      for (const channel of [(c >> 16) & 255, (c >> 8) & 255, c & 255]) {
        expect(channel).toBeGreaterThanOrEqual(117);
        expect(channel).toBeLessThanOrEqual(138);
      }
    }
  }
  // The clamp has to hold at both ends, not just the middle.
  expect(tinted(0x000000, 0, 0)).toBe(0x000000);
  // Grain(0,0) is the darkest step (-0.5), so white comes out at 255*0.92 = 235.
  expect(tinted(0xffffff, 0, 0)).toBe(0xebebeb);
  // The brightest step (+0.47) would push white past 255; the clamp holds it.
  for (let y = 0; y < 20; y++) {
    for (let x = 0; x < 20; x++) {
      const c = tinted(0xffffff, x, y);
      for (const channel of [(c >> 16) & 255, (c >> 8) & 255, c & 255]) {
        expect(channel).toBeLessThanOrEqual(255);
      }
    }
  }
});

it('layerOf clamps a cell height into the four render layers', () => {
  expect(layerOf(-1)).toBe(0);
  expect(layerOf(0)).toBe(0);
  expect(layerOf(1)).toBe(1);
  expect(layerOf(3)).toBe(3);
  expect(layerOf(5)).toBe(3);
});

it('a block stands on the ground plane with its top at its height level', () => {
  for (const level of [1, 2, 3]) {
    const t = blockTransform(10, 20, level, W, H);
    expect(t.scaleY).toBeCloseTo(level, 10);
    // Centre sits half a box up, so the bottom face is exactly at y = 0 ...
    expect(t.position.y).toBeCloseTo(t.scaleY / 2, 10);
    // ... and the top face lands on the elevation the camera and picking assume.
    expect(t.position.y + t.scaleY / 2).toBeCloseTo(level, 10);
  }
});

it('water is a thin slab whose top face is the ground plane', () => {
  const t = blockTransform(10, 20, 0, W, H);
  expect(t.scaleY).toBeCloseTo(WATER_THICKNESS, 10);
  // Top at y = 0 so walkable h=0 cells are flush with the pick plane.
  expect(t.position.y + t.scaleY / 2).toBeCloseTo(0, 10);
  // The slab hangs below the plane rather than above it.
  expect(t.position.y).toBeLessThan(0);
});

it('the block geometry bakes the same face shading as the Phaser painter', () => {
  // iso-terrain.paintBlock shades top 1.0, left 0.75, right 0.6. The three path
  // bakes those into vertex colours instead of using lights, because a Lambert
  // rig divides by π (measured luma 45 vs the painter's 83) and would also make
  // the town look different on another device's renderer.
  const geometry = shadedBoxForTest();
  const colours = geometry.getAttribute('color') as {
    count: number;
    getX(i: number): number;
  };
  const normals = geometry.getAttribute('normal') as {
    count: number;
    getX(i: number): number;
    getY(i: number): number;
    getZ(i: number): number;
  };
  expect(colours.count).toBe(normals.count);

  // Group every vertex by the axis its normal points along, then check the
  // baked brightness of each group. BoxGeometry's face order is +x, -x, +y,
  // -y, +z, -z; reading the normal rather than the index makes this a test of
  // the shading, not of three's vertex layout.
  const seen = new Map<string, Set<number>>();
  for (let i = 0; i < normals.count; i++) {
    const nx = Math.round(normals.getX(i));
    const ny = Math.round(normals.getY(i));
    const nz = Math.round(normals.getZ(i));
    const key = `${nx},${ny},${nz}`;
    if (!seen.has(key)) seen.set(key, new Set());
    seen.get(key)!.add(Number(colours.getX(i).toFixed(4)));
  }
  // The three faces the 45°/30° camera can see, at the painter's brightness.
  expect([...seen.get('1,0,0')!]).toEqual([FACE_SHADE.right]);
  expect([...seen.get('0,1,0')!]).toEqual([FACE_SHADE.top]);
  expect([...seen.get('0,0,1')!]).toEqual([FACE_SHADE.left]);
  // The back faces are never visible; leaving them at full brightness would
  // show through at the silhouette edge under antialiasing.
  expect(seen.get('-1,0,0')!.size).toBe(1);
  expect(seen.get('0,-1,0')!.size).toBe(1);
  expect(seen.get('0,0,-1')!.size).toBe(1);
});

it('a block is placed on the projection module’s cell centre', () => {
  for (const [x, y] of [
    [0, 0],
    [W - 1, 0],
    [0, H - 1],
    [W - 1, H - 1],
    [70, 50],
  ] as const) {
    const t = blockTransform(x, y, 2, W, H);
    const centre = worldOf(x, y, W, H);
    // Same footprint centre as the camera and raycaster use: one authority.
    expect(t.position.x).toBeCloseTo(centre.x, 10);
    expect(t.position.z).toBeCloseTo(centre.z, 10);
  }
});
