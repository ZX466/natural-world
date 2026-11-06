import * as THREE from 'three';
import { expect, it } from 'vitest';
import {
  AZIMUTH_DEG,
  ELEVATION_DEG,
  cellOf,
  createCamera,
  resizeCamera,
  worldOf,
} from '../three-projection';

const W = 140;
const H = 100;

/** Project a world point through the real camera into **normalised** screen
 * coordinates (0..1, y down). Assertions stay in this unit because the pixel
 * scale depends on the viewport, which is the whole point of the fit. */
function throughCamera(
  camera: THREE.OrthographicCamera,
  point: THREE.Vector3,
): { nx: number; ny: number } {
  // project() reads matrixWorldInverse, which lookAt does not refresh on its
  // own. Without this the camera reads as an unrotated top-down view.
  camera.updateMatrixWorld(true);
  const ndc = point.clone().project(camera);
  // Frustum units, not normalised 0..1: the viewport aspect scales the two
  // axes differently, and the 2:1 ratio is a property of the camera basis.
  return {
    nx: ndc.x * ((camera.right - camera.left) / 2),
    ny: -ndc.y * ((camera.top - camera.bottom) / 2),
  };
}

function anchored(aspect: number) {
  const camera = createCamera(W, H, aspect);
  resizeCamera(camera, W, H, aspect);
  return camera;
}

it('a cell step projects to the 2:1 diamond (drop is half the run)', () => {
  const camera = anchored(1600 / 1200);
  const a = throughCamera(camera, worldOf(0, 0, W, H));
  const right = throughCamera(camera, worldOf(1, 0, W, H));
  const down = throughCamera(camera, worldOf(0, 1, W, H));

  // +x and +y must mirror each other horizontally and share the same drop.
  expect(right.nx - a.nx).toBeCloseTo(-(down.nx - a.nx), 8);
  expect(right.ny - a.ny).toBeCloseTo(down.ny - a.ny, 8);

  // The vertical drop is exactly half the horizontal run: that IS 2:1.
  const run = Math.abs(right.nx - a.nx);
  const drop = right.ny - a.ny;
  expect(drop / run).toBeCloseTo(0.5, 8);
});

it('one height unit lifts by the elevation cosine over the same scale', () => {
  const camera = anchored(1600 / 1200);
  const ground = worldOf(10, 10, W, H);
  const lifted = ground.clone();
  lifted.y = 1;
  const pg = throughCamera(camera, ground);
  const pl = throughCamera(camera, lifted);
  // The lift must be purely vertical, and must equal cos(30°)/cos(45°) of the
  // horizontal run — i.e. 0.866/0.7071 ≈ 1.2247 times a cell run.
  expect(pl.nx - pg.nx).toBeCloseTo(0, 8);
  const lift = pg.ny - pl.ny;
  const step = Math.abs(throughCamera(camera, worldOf(11, 10, W, H)).nx - pg.nx);
  expect(lift / step).toBeCloseTo(
    Math.cos((ELEVATION_DEG * Math.PI) / 180) / Math.cos((AZIMUTH_DEG * Math.PI) / 180),
    6,
  );
});

it('cellOf inverts worldOf on the ground plane', () => {
  for (let x = 0; x < W; x += 7) {
    for (let y = 0; y < H; y += 11) {
      expect(cellOf(worldOf(x, y, W, H), W, H)).toEqual({ x, y });
    }
  }
});

it('the 2:1 ratio and the camera angles are fixed', () => {
  expect(AZIMUTH_DEG).toBe(45);
  expect(ELEVATION_DEG).toBe(30);
  expect(Math.sin((ELEVATION_DEG * Math.PI) / 180)).toBeCloseTo(0.5, 10);
});

it('the camera frames the whole map at any aspect', () => {
  for (const aspect of [0.5, 1, 16 / 9, 3]) {
    const camera = anchored(aspect);
    // Every corner of the map must land inside the frustum.
    for (const [x, y] of [
      [0, 0],
      [W - 1, 0],
      [0, H - 1],
      [W - 1, H - 1],
    ] as const) {
      const p = throughCamera(camera, worldOf(x, y, W, H));
      expect(Math.abs(p.nx)).toBeLessThan(camera.right);
      expect(Math.abs(p.ny)).toBeLessThan(camera.top);
    }
    expect((camera.right - camera.left) / (camera.top - camera.bottom)).toBeCloseTo(aspect, 6);
  }
});
