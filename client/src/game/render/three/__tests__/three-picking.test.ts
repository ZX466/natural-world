import * as THREE from 'three';
import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { pickGround, pickVoxel } from '../../voxel-picking';
import { isoProject, isoUnproject, screenBounds } from '../../iso';
import { renderHeightLookup } from '../../cell-appearance';
import { worldOf, createCamera, defaultOrbit, updateFollowCamera } from '../three-projection';
import { groundFromRay, editFromRay, screenRay, WALK_HEIGHT } from '../three-picking';
import type { MapStatic } from '../../../world-mirror';

function grid(w = 5, h = 5): MapStatic {
  return { w, h, tileset: 'grid', collision: new Uint8Array(w * h).fill(1) };
}
function mesh(cells: { x: number; y: number; h: number }[], w = 5, h = 5) {
  const object = new THREE.InstancedMesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshBasicMaterial(),
    cells.length,
  );
  const matrix = new THREE.Matrix4();
  cells.forEach((cell, index) => {
    const point = worldOf(cell.x, cell.y, w, h);
    matrix.makeScale(1, Math.max(0.06, cell.h), 1).setPosition(point.x, cell.h / 2, point.z);
    object.setMatrixAt(index, matrix);
  });
  object.userData.cells = cells;
  object.computeBoundingSphere();
  object.updateMatrixWorld(true);
  return object;
}
// An equivalent ray for one legacy iso pixel. This deliberately lives only in
// the comparison test; production uses its actual perspective projection.
function legacyRay(sx: number, sy: number, w = 5, h = 5) {
  const ground = isoUnproject(sx, sy + 16, screenBounds(w, h));
  const point = worldOf(ground.x, ground.y, w, h).setY(1);
  return new THREE.Ray(
    point.add(new THREE.Vector3(10, 10, 10)),
    new THREE.Vector3(-1, -1, -1).normalize(),
  );
}

it('matches the Phaser movement/edit split when a high block covers walkable ground', () => {
  const map = grid();
  map.collision[18] = 0;
  const height = (x: number, y: number) => (x === 3 && y === 3 ? 3 : 1);
  const point = isoProject(1, 1, 1, screenBounds(5, 5));
  const ray = legacyRay(point.sx, point.sy);
  expect(groundFromRay(ray, map, height)).toEqual(
    pickGround(point.sx, point.sy, 5, 5, height, (x, y) => map.collision[y * 5 + x] === 1),
  );
  expect(groundFromRay(ray, map, height)).toEqual({ x: 1, y: 1 });
  expect(
    editFromRay(ray, [
      mesh([
        { x: 3, y: 3, h: 3 },
        { x: 1, y: 1, h: 1 },
      ]),
    ]),
  ).toEqual(pickVoxel(point.sx, point.sy, 5, 5, height));
  expect(editFromRay(ray, [mesh([{ x: 3, y: 3, h: 3 }])])).toEqual({ x: 3, y: 3 });
});

it('maps an actual side-face hit to its instance cell, not the adjoining cell', () => {
  const object = mesh([{ x: 3, y: 3, h: 3 }]);
  const ray = new THREE.Ray(new THREE.Vector3(5, 1.5, 1), new THREE.Vector3(-1, 0, 0));
  expect(editFromRay(ray, [object])).toEqual({ x: 3, y: 3 });
});

it.each([0, 90, 180, 270])(
  'inverts a perspective ground click at yaw %i using CSS pixels',
  (azimuth) => {
    const map = grid(20, 20),
      camera = createCamera(20, 20, 16 / 9);
    const target = worldOf(10, 10, 20, 20).setY(2.3);
    updateFollowCamera(camera, target, { ...defaultOrbit(), azimuth });
    const point = worldOf(10, 10, 20, 20).setY(1).project(camera);
    const rect = { left: 10, top: 20, width: 1600, height: 900 };
    const ray = screenRay(camera, 10 + (point.x + 1) * 800, 20 + (1 - point.y) * 450, rect)!;
    expect(groundFromRay(ray, map, () => 1)).toEqual({ x: 10, y: 10 });
    const roof = worldOf(10, 10, 20, 20).setY(3).project(camera);
    const roofRay = screenRay(camera, 10 + (roof.x + 1) * 800, 20 + (1 - roof.y) * 450, rect)!;
    expect(editFromRay(roofRay, [mesh([{ x: 10, y: 10, h: 3 }], 20, 20)])).toEqual({
      x: 10,
      y: 10,
    });
    map.collision[210] = 0;
    expect(groundFromRay(ray, map, () => 1)).toBeNull();
  },
);

it('preserves every real-map walkable center without applying terrain occlusion', () => {
  const root = new URL('../../../../../../', import.meta.url);
  const town = JSON.parse(readFileSync(new URL('sim/content/linhe-town.json', root), 'utf8')) as {
    width: number;
    height: number;
    chunks: Record<string, { collision: boolean[] }>;
  };
  const heights = JSON.parse(
    readFileSync(new URL('client/public/assets/tilesets/linhe-height.json', root), 'utf8'),
  );
  const map = grid(town.width, town.height);
  map.collision.fill(0);
  for (const [key, chunk] of Object.entries(town.chunks)) {
    const [cx, cy] = key.split(',').map(Number);
    const side = Math.sqrt(chunk.collision.length);
    for (let i = 0; i < chunk.collision.length; i++) {
      const x = cx! * side + (i % side),
        y = cy! * side + Math.floor(i / side);
      if (x < map.w && y < map.h) map.collision[y * map.w + x] = chunk.collision[i] ? 1 : 0;
    }
  }
  const height = (x: number, y: number) => heights.h_values[y * map.w + x];
  let checked = 0;
  for (let y = 0; y < map.h; y++)
    for (let x = 0; x < map.w; x++)
      if (map.collision[y * map.w + x]) {
        const point = isoProject(x, y, 1, screenBounds(map.w, map.h));
        const ray = legacyRay(point.sx, point.sy, map.w, map.h);
        expect(groundFromRay(ray, map, height)).toEqual({ x, y });
        expect(
          pickGround(
            point.sx,
            point.sy,
            map.w,
            map.h,
            height,
            (x, y) => map.collision[y * map.w + x] === 1,
          ),
        ).toEqual({ x, y });
        checked++;
      }
  // 3692 = 3947 原始可走格减去试车台 17×15 占地面（255 格）。建筑是**世界
  // 结构**，那 255 格在服务端地图里就不可走，所以这里不该再出现它们。
  expect(checked).toBe(3692);
  // 编辑拾取读**渲染**高度：土坎（逻辑 1、不可走）画成 2 格矮墙。
  const drawHeight = renderHeightLookup(map, height);
  const cells = Array.from({ length: map.w * map.h }, (_, i) => {
    const x = i % map.w,
      y = Math.floor(i / map.w);
    return { x, y, h: drawHeight(x, y) };
  });
  const actualTerrain = mesh(cells, map.w, map.h);
  for (const [x, y] of [
    [20, 3],
    [99, 31],
  ]) {
    const level = drawHeight(x!, y!);
    const point = isoProject(x!, y!, level, screenBounds(map.w, map.h));
    const legacy = pickVoxel(point.sx, point.sy, map.w, map.h, drawHeight);
    expect(legacy).toEqual({ x, y });
    expect(editFromRay(legacyRay(point.sx, point.sy, map.w, map.h), [actualTerrain])).toEqual(
      legacy,
    );
  }
});

it('pins the walk plane to the legacy walk-height contract', () => {
  const source = readFileSync(new URL('../../voxel-picking.ts', import.meta.url), 'utf8');
  expect(WALK_HEIGHT).toBe(Number(/const WALK_HEIGHT = (\d+)/.exec(source)![1]));
});
