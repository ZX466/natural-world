import * as THREE from 'three';
import { expect, it } from 'vitest';
import { ISO, isoProject, screenBounds } from '../../iso';
import { HEIGHT_UNIT, alignTarget, followCamera, worldOf } from '../three-projection';

const W = 140;
const H = 100;
const PIXEL_SCALE = 3.5;
/** ISO.TW / 2 * PIXEL_SCALE — one cell step as the Phaser iso camera shows it. */
const CELL_PX = (ISO.TW / 2) * PIXEL_SCALE;
const VW = 1600;
const VH = 900;

/** Where a three world point lands on the canvas, in px from the canvas centre. */
function threePx(camera: THREE.OrthographicCamera, p: THREE.Vector3) {
  camera.updateMatrixWorld(true);
  const ndc = p.clone().project(camera);
  return { x: (ndc.x * VW) / 2, y: (-ndc.y * VH) / 2 };
}

/** Phaser iso screen px → px relative to the camera's centred point, at zoom. */
function phaserDelta(
  cameraCell: readonly [number, number],
  cell: readonly [number, number],
  level = 0,
) {
  const bounds = screenBounds(W, H);
  const a = isoProject(cameraCell[0], cameraCell[1], 0, bounds);
  const b = isoProject(cell[0], cell[1], level, bounds);
  return { x: (b.sx - a.sx) * PIXEL_SCALE, y: (b.sy - a.sy) * PIXEL_SCALE };
}

function alignedCamera(cameraCell: readonly [number, number]) {
  const bounds = screenBounds(W, H);
  const centre = isoProject(cameraCell[0], cameraCell[1], 0, bounds);
  const target = alignTarget(centre.sx, centre.sy, W, H);
  return followCamera(VW, VH, target, CELL_PX);
}

it('alignTarget is the continuous inverse of isoProject on the ground plane', () => {
  const bounds = screenBounds(W, H);
  for (const [x, y] of [
    [0, 0],
    [10, 20],
    [70, 50],
    [139, 99],
  ] as const) {
    const p = isoProject(x, y, 0, bounds);
    const target = alignTarget(p.sx, p.sy, W, H);
    // Must land exactly on worldOf's cell centre, so blocks sit where the
    // camera thinks the cells are.
    const world = worldOf(x, y, W, H);
    expect(target.x).toBeCloseTo(world.x, 9);
    expect(target.z).toBeCloseTo(world.z, 9);
  }
});

it('the followed cell renders dead centre', () => {
  for (const cell of [
    [0, 0],
    [70, 50],
    [W - 1, H - 1],
  ] as const) {
    const camera = alignedCamera(cell);
    const p = threePx(camera, worldOf(cell[0], cell[1], W, H));
    expect(p.x).toBeCloseTo(0, 6);
    expect(p.y).toBeCloseTo(0, 6);
  }
});

it('every cell lands where isoProject puts it — the picking invariant', () => {
  // Three picking accidents came from exactly this seam. `pickVoxel` and
  // `pickGround` unproject Phaser screen space, so the three canvas must place
  // every cell at the same pixel or a click edits the wrong block.
  const cameraCell = [70, 50] as const;
  const camera = alignedCamera(cameraCell);
  const origin = threePx(camera, worldOf(cameraCell[0], cameraCell[1], W, H));

  for (const cell of [
    [70, 50],
    [70, 51],
    [71, 50],
    [69, 51],
    [60, 40],
    [80, 60],
    [0, 0],
    [W - 1, H - 1],
  ] as const) {
    const three = threePx(camera, worldOf(cell[0], cell[1], W, H));
    const expected = phaserDelta(cameraCell, cell);
    expect(three.x - origin.x).toBeCloseTo(expected.x, 4);
    expect(three.y - origin.y).toBeCloseTo(expected.y, 4);
  }
});

it('a lifted cell rises one cell height per level, like isoProject', () => {
  const cameraCell = [70, 50] as const;
  const camera = alignedCamera(cameraCell);
  const ground = threePx(camera, worldOf(70, 50, W, H));

  for (const level of [1, 2, 3]) {
    // iso.ts lifts one level by ISO.HH = one cell step, so a block is as tall
    // as it is wide. Three applies HEIGHT_UNIT to the block transform, not the
    // camera; this pins that the two agree.
    const lifted = threePx(camera, worldOf(70, 50, W, H).setY(level * HEIGHT_UNIT));
    const expected = phaserDelta(cameraCell, [70, 50], level);
    expect(lifted.x - ground.x).toBeCloseTo(expected.x, 4);
    expect(lifted.y - ground.y).toBeCloseTo(expected.y, 4);
    // Straight up, one cell step per level.
    expect(lifted.x - ground.x).toBeCloseTo(0, 6);
    expect(ground.y - lifted.y).toBeCloseTo(level * CELL_PX, 4);
  }
});
