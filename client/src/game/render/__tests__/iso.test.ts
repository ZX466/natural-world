import { describe, expect, it } from 'vitest';
import {
  ISO,
  createHeightLookup,
  depthKey,
  effectiveHeight,
  heightOf,
  isoProject,
  isoUnproject,
  screenBounds,
} from '../iso';

describe('isometric ground geometry', () => {
  it('uses the specified canvas bounds and one origin for the town', () => {
    expect(ISO).toEqual({ TW: 32, TH: 16, HH: 16 });
    expect(screenBounds(140, 100)).toEqual({
      width: 3840,
      height: 2040,
      originX: 1600,
      originY: 56,
    });
    expect(isoProject(0, 0, 0)).toEqual({ sx: 1600, sy: 56 });
    expect(isoProject(2, 1, 3)).toEqual({ sx: 1616, sy: 32 });
  });

  it('round trips every town ground cell, including all four corners', () => {
    for (let y = 0; y < 100; y++) {
      for (let x = 0; x < 140; x++) {
        const p = isoProject(x, y, 0);
        expect(isoUnproject(p.sx, p.sy)).toEqual({ x, y });
      }
    }
  });

  it('uses the same origin for injected small map bounds', () => {
    const bounds = screenBounds(4, 4);
    const p = isoProject(3, 1, 0, bounds);
    expect(p).toEqual({ sx: 96, sy: 88 });
    expect(isoUnproject(p.sx, p.sy, bounds)).toEqual({ x: 3, y: 1 });
  });

  it('keeps interior points in the diamond and excludes exterior points', () => {
    const p = isoProject(10, 10, 0);
    for (const [dx, dy] of [
      [0, 0],
      [15, 0],
      [0, 7],
      [-7, -4],
    ]) {
      expect(isoUnproject(p.sx + dx!, p.sy + dy!)).toEqual({ x: 10, y: 10 });
    }
    expect(isoUnproject(p.sx + 17, p.sy)).not.toEqual({ x: 10, y: 10 });
    expect(isoUnproject(p.sx, p.sy - 9)).not.toEqual({ x: 10, y: 10 });
  });

  it('assigns shared edges deterministically to a touching diamond', () => {
    const p = isoProject(10, 10, 0);
    for (const [dx, dy] of [
      [16, 0],
      [-16, 0],
      [0, 8],
      [0, -8],
      [8, 4],
    ]) {
      const hit = isoUnproject(p.sx + dx!, p.sy + dy!);
      const center = isoProject(hit.x, hit.y, 0);
      const distance = Math.abs(p.sx + dx! - center.sx) / 16 + Math.abs(p.sy + dy! - center.sy) / 8;
      expect(distance).toBeLessThanOrEqual(1);
      expect(isoUnproject(p.sx + dx!, p.sy + dy!)).toEqual(hit);
    }
  });

  it('contains the complete blocks at map edges without clipping vertices', () => {
    const bounds = screenBounds(140, 100);
    for (const x of [0, 139]) {
      for (const y of [0, 99]) {
        const top = isoProject(x, y, 3);
        const bottom = isoProject(x, y, 0);
        expect(top.sx - 16).toBeGreaterThanOrEqual(0);
        expect(top.sx + 16).toBeLessThanOrEqual(bounds.width);
        expect(top.sy - 8).toBeGreaterThanOrEqual(0);
        expect(bottom.sy + 8).toBeLessThanOrEqual(bounds.height);
      }
    }
  });

  it('totally orders town cells by diagonal then row without collisions', () => {
    const cells = Array.from({ length: 14000 }, (_, i) => ({ x: i % 140, y: Math.floor(i / 140) }));
    const keys = cells.map(({ x, y }) => depthKey(x, y));
    expect(new Set(keys).size).toBe(14000);
    const ordered = cells.sort((a, b) => a.x + a.y - b.x - b.y || a.y - b.y);
    for (let i = 1; i < ordered.length; i++) {
      const a = ordered[i - 1]!;
      const b = ordered[i]!;
      expect(depthKey(a.x, a.y)).toBeLessThan(depthKey(b.x, b.y));
    }
    expect(depthKey(4, 7)).toBe(11 * 1024 + 7);
  });
});

describe('shared effective surface height', () => {
  it('overrides static water or canopy for built and collapsing footprints only', () => {
    const structures = new Map([
      ['house', { tiles: [[1, 2]] as [number, number][], phase: 'built' }],
    ]);
    expect(effectiveHeight(1, 2, () => 0, structures)).toBe(2);
    expect(effectiveHeight(1, 2, () => 3, structures)).toBe(2);
    structures.get('house')!.phase = 'collapsing';
    expect(effectiveHeight(1, 2, () => 1, structures)).toBe(2);
    expect(effectiveHeight(0, 2, () => 0, structures)).toBe(0);
  });

  it('restores static height for rubble, removal, and empty structure snapshots', () => {
    const structures = new Map([
      ['house', { tiles: [[1, 2]] as [number, number][], phase: 'rubble' }],
    ]);
    expect(effectiveHeight(1, 2, () => 3, structures)).toBe(3);
    expect(effectiveHeight(1, 2, () => 0, structures)).toBe(0);
    structures.clear();
    expect(effectiveHeight(1, 2, () => 1, structures)).toBe(1);
  });
});

describe('coordinate indexed height lookup', () => {
  const table = { w: 4, h: 4, h_values: [0, 1, 2, 3, 3, 2, 1, 0, 1, 0, 3, 2, 2, 3, 0, 1] };

  it('reads an injected 4×4 table by row and column', () => {
    const lookup = createHeightLookup(table);
    for (let y = 0; y < 4; y++) {
      for (let x = 0; x < 4; x++) {
        expect(lookup(x, y)).toBe(table.h_values[y * 4 + x]);
        expect(heightOf(x, y, table)).toBe(lookup(x, y));
      }
    }
  });

  it('falls back to one for missing, out of bounds, or noninteger coordinates', () => {
    const lookup = createHeightLookup(table);
    for (const [x, y] of [
      [-1, 0],
      [4, 0],
      [0, 4],
      [1.5, 0],
      [NaN, 0],
    ]) {
      expect(lookup(x!, y!)).toBe(1);
    }
    expect(heightOf(0, 0)).toBe(1);
    expect(createHeightLookup(null)(0, 0)).toBe(1);
  });

  it('rejects malformed tables and isolates the lookup from later mutation', () => {
    for (const bad of [
      {},
      { ...table, w: -1 },
      { ...table, h_values: [3] },
      { ...table, h_values: table.h_values.map(() => 9) },
    ]) {
      expect(createHeightLookup(bad)(0, 0)).toBe(1);
    }
    const source = { ...table, h_values: [...table.h_values] };
    const lookup = createHeightLookup(source);
    source.h_values[0] = 3;
    expect(lookup(0, 0)).toBe(0);
  });
});
