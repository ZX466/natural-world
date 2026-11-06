import { expect, it } from 'vitest';
import type { MapStatic } from '../../world-mirror';
import { EDIT_COLORS, cellAppearances, structureOverrides } from '../cell-appearance';
import { FALLBACK_COLOR } from '../tile-color';

const W = 4;
const H = 3;

function mapWith(overrides: Partial<MapStatic> = {}): MapStatic {
  const n = W * H;
  return {
    w: W,
    h: H,
    tileset: 'god',
    collision: new Uint8Array(n).fill(1),
    ground: new Uint16Array(n).fill(7),
    ...overrides,
  };
}

/** Every cell the same height, so a test can vary exactly one thing. */
const flatOne = () => 1;
const identity = (gid: number) => gid;

it('a plain cell is its tile colour at its height, with no flags', () => {
  const cells = cellAppearances(mapWith(), new Map(), new Map(), flatOne, identity);
  expect(cells).toHaveLength(W * H);
  const c = cells[0]!;
  expect(c).toMatchObject({ x: 0, y: 0, h: 1, color: 7, rubble: false, scar: false });
  expect(c.phase).toBeUndefined();
  expect(c.edited).toBe(false);
  // Row-major: index 1 is (1,0), index W is (0,1).
  expect(cells[1]!.x).toBe(1);
  expect(cells[W]!.y).toBe(1);
});

it('height comes from the lookup, and non-walkable h=1 is a bank', () => {
  const collision = new Uint8Array(W * H).fill(1);
  collision[0] = 0; // (0,0) blocked at height 1
  const cells = cellAppearances(mapWith({ collision }), new Map(), new Map(), flatOne, identity);
  expect(cells[0]!.bank).toBe(true);
  expect(cells[1]!.bank).toBe(false);
  // Bank only exists at height 1; blocked water is not a bank.
  const heights = (x: number, y: number) => (x === 0 && y === 0 ? 0 : 1);
  const water = cellAppearances(mapWith({ collision }), new Map(), new Map(), heights, identity);
  expect(water[0]!.h).toBe(0);
  expect(water[0]!.bank).toBe(false);
});

it('an edited cell takes the material colour instead of the tile', () => {
  for (const h of [0, 1, 2, 3]) {
    const cells = cellAppearances(
      mapWith(),
      new Map(),
      new Map([['0,0', { height: h, action: 'place' }]]),
      () => h,
      identity,
    );
    expect(cells[0]!.edited).toBe(true);
    expect(cells[0]!.h).toBe(h);
    expect(cells[0]!.color).toBe(EDIT_COLORS[h]);
  }
});

it('a dig on open ground is a scar, but a dig under a structure is not', () => {
  const edits = new Map([['0,0', { height: 1, action: 'dig' as const }]]);
  const plain = cellAppearances(mapWith(), new Map(), edits, flatOne, identity);
  expect(plain[0]!.scar).toBe(true);
  // A dug cell that is not walkable is a bank, and a bank is not a scar.
  const collision = new Uint8Array(W * H).fill(1);
  collision[0] = 0;
  const banked = cellAppearances(mapWith({ collision }), new Map(), edits, flatOne, identity);
  expect(banked[0]!.bank).toBe(true);
  expect(banked[0]!.scar).toBe(false);
});

it('a built structure raises its tiles to h=2 and owns the colour', () => {
  const structures = new Map([
    ['s1', { phase: 'built', tiles: [[0, 0] as const, [1, 0] as const] }],
  ]);
  const cells = cellAppearances(mapWith(), structures, new Map(), flatOne, identity);
  expect(cells[0]!.h).toBe(2);
  expect(cells[0]!.phase).toBe('built');
  expect(cells[1]!.h).toBe(2);
  // Untouched cells keep the lookup height.
  expect(cells[2]!.h).toBe(1);
  expect(cells[2]!.phase).toBeUndefined();
});

it('a structure outranks an edit on the same cell', () => {
  const structures = new Map([['s1', { phase: 'built', tiles: [[0, 0] as const] }]]);
  const edits = new Map([['0,0', { height: 0, action: 'dig' as const }]]);
  const cells = cellAppearances(mapWith(), structures, edits, flatOne, identity);
  expect(cells[0]!.h).toBe(2);
  expect(cells[0]!.phase).toBe('built');
  // The edit still marks the cell, but the structure colour wins.
  expect(cells[0]!.edited).toBe(true);
  expect(cells[0]!.color).toBe(7);
});

it('a collapsing structure looks like a built one, a planned one does nothing', () => {
  const collapsing = cellAppearances(
    mapWith(),
    new Map([['s1', { phase: 'collapsing', tiles: [[0, 0] as const] }]]),
    new Map(),
    flatOne,
    identity,
  );
  expect(collapsing[0]!.h).toBe(2);
  expect(collapsing[0]!.phase).toBe('collapsing');

  for (const phase of ['planned', 'building', 'active']) {
    const cells = cellAppearances(
      mapWith(),
      new Map([['s1', { phase, tiles: [[0, 0] as const] }]]),
      new Map(),
      flatOne,
      identity,
    );
    expect(cells[0]!.h).toBe(1);
    expect(cells[0]!.phase).toBeUndefined();
  }
});

it('rubble marks its tiles but raises nothing', () => {
  const cells = cellAppearances(
    mapWith(),
    new Map([['s1', { phase: 'rubble', tiles: [[0, 0] as const] }]]),
    new Map(),
    flatOne,
    identity,
  );
  expect(cells[0]!.rubble).toBe(true);
  expect(cells[0]!.h).toBe(1);
  expect(cells[0]!.phase).toBeUndefined();
});

it('a cell with no ground gid falls back to the timber colour', () => {
  const ground = new Uint16Array(W * H).fill(0);
  const cells = cellAppearances(mapWith({ ground }), new Map(), new Map(), flatOne, (gid) =>
    gid === 0 ? FALLBACK_COLOR : gid,
  );
  expect(cells[0]!.color).toBe(FALLBACK_COLOR);
});

it('structureOverrides separates claims from ruins', () => {
  const { phases, ruins } = structureOverrides(
    new Map([
      ['a', { phase: 'built', tiles: [[0, 0] as const, [1, 0] as const] }],
      ['b', { phase: 'collapsing', tiles: [[2, 0] as const] }],
      ['c', { phase: 'rubble', tiles: [[0, 1] as const] }],
      ['d', { phase: 'building', tiles: [[1, 1] as const] }],
    ]),
  );
  expect([...phases.keys()].sort()).toEqual(['0,0', '1,0', '2,0']);
  expect(phases.get('2,0')).toBe('collapsing');
  expect([...ruins]).toEqual(['0,1']);
  // A building site is neither claimed nor rubble.
  expect(phases.has('1,1')).toBe(false);
  expect(ruins.has('1,1')).toBe(false);
});
