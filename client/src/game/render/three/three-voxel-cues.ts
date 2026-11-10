import * as THREE from 'three';
import type { WorldMirror } from '../../world-mirror';
import type { MovePoint } from '../../movement';
import type { VoxelMaterial } from '../../../store/uiStore';
import type { VoxelStateMessage } from '../../../net/protocol';
import { effectiveHeight, type HeightLookup } from '../iso';
import { worldOf } from './three-projection';

/** 逻辑高度 → 渲染高度（土坎 1 → 2）。缺省不抬，测试与旧调用方不受影响。 */
export type CueDrawHeight = (x: number, y: number, height: number) => number;

export function createVoxelCues(
  scene: THREE.Scene,
  mirror: WorldMirror,
  heightOf: HeightLookup,
  drawHeight: CueDrawHeight = (_x, _y, height) => height,
) {
  const box = new THREE.BoxGeometry(1, 1, 1);
  const edges = new THREE.EdgesGeometry(box);
  const lineMaterial = new THREE.LineBasicMaterial({
    color: 0xffdc87,
    transparent: true,
    opacity: 0.95,
    depthTest: false,
    depthWrite: false,
  });
  const selection = new THREE.LineSegments(edges, lineMaterial);
  const preview = new THREE.Mesh(
    box,
    new THREE.MeshBasicMaterial({
      color: 0xd9c58e,
      transparent: true,
      opacity: 0.26,
      depthTest: false,
      depthWrite: false,
    }),
  );
  const crossGeometry = new THREE.BufferGeometry();
  crossGeometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute([-0.4, 0, -0.4, 0.4, 0, 0.4, -0.4, 0, 0.4, 0.4, 0, -0.4], 3),
  );
  const blockingCross = new THREE.LineSegments(crossGeometry, lineMaterial);
  const background = new THREE.Sprite(
    new THREE.SpriteMaterial({
      color: 0x211d16,
      transparent: true,
      depthTest: false,
      depthWrite: false,
    }),
  );
  const fill = new THREE.Sprite(
    new THREE.SpriteMaterial({
      color: 0xe3cc8c,
      transparent: true,
      depthTest: false,
      depthWrite: false,
    }),
  );
  fill.center.set(0, 0.5);
  background.scale.set(1.04, 0.12, 1);
  const goalMarker = new THREE.Mesh(
    new THREE.RingGeometry(0.17, 0.24, 24),
    new THREE.MeshBasicMaterial({ color: 0xffd75e, side: THREE.DoubleSide, depthWrite: false }),
  );
  goalMarker.rotation.x = -Math.PI / 2;
  background.renderOrder = 10;
  fill.renderOrder = 11;
  selection.renderOrder = blockingCross.renderOrder = 20;
  preview.renderOrder = 19;
  const objects = [selection, preview, blockingCross, background, fill, goalMarker];
  scene.add(...objects);
  let epoch = `${mirror.resetCount}:${mirror.voxelSnapshotVersion}`;
  const clear = () => {
    for (const object of objects) object.visible = false;
  };
  clear();
  return {
    selection,
    preview,
    blockingCross,
    goalMarker,
    progress: { background, fill },
    update(
      hover: MovePoint | null,
      goal: MovePoint | null,
      material: VoxelMaterial,
      inventory: VoxelStateMessage['inventory'] | null,
      camera: THREE.Camera,
      enabled = true,
    ) {
      clear();
      const current = `${mirror.resetCount}:${mirror.voxelSnapshotVersion}`;
      if (current !== epoch) {
        epoch = current;
        return;
      }
      const map = mirror.map;
      if (!map || !enabled) return;
      const valid = (point: MovePoint | null): point is MovePoint =>
        !!point &&
        Number.isInteger(point.x) &&
        Number.isInteger(point.y) &&
        point.x >= 0 &&
        point.y >= 0 &&
        point.x < map.w &&
        point.y < map.h;
      // 选框贴着**画出来的**面：土坎是 2 格矮墙，按逻辑 1 画选框会埋进墙里。
      const height = (point: MovePoint) =>
        drawHeight(
          point.x,
          point.y,
          effectiveHeight(point.x, point.y, heightOf, mirror.structures, mirror.voxelEdits),
        );
      const chosen = mirror.voxelDig ?? hover;
      if (valid(chosen)) {
        const h = height(chosen),
          point = worldOf(chosen.x, chosen.y, map.w, map.h);
        selection.visible = true;
        selection.position.set(point.x, h / 2, point.z);
        selection.scale.set(1.02, Math.max(0.06, h) + 0.02, 1.02);
        // 放置预览只在**逻辑**高度 1 的可走面上出现（服务端 `_validate` 的判据）。
        const placeable =
          !mirror.voxelDig &&
          map.collision[chosen.y * map.w + chosen.x] === 1 &&
          effectiveHeight(chosen.x, chosen.y, heightOf, mirror.structures, mirror.voxelEdits) ===
            1 &&
          (inventory?.[material] ?? 0) > 0;
        if (placeable) {
          const placedHeight = { earth: 1, stone: 2, wood: 3 }[material];
          preview.visible = blockingCross.visible = true;
          preview.position.set(point.x, placedHeight / 2, point.z);
          preview.scale.set(1, placedHeight, 1);
          preview.material.color.setHex(
            { earth: 0xc7a66d, stone: 0xadaeb5, wood: 0x9c744c }[material],
          );
          blockingCross.position.set(point.x, placedHeight + 0.03, point.z);
        }
      }
      const dig = mirror.voxelDig;
      if (valid(dig)) {
        const point = worldOf(dig.x, dig.y, map.w, map.h).setY(height(dig) + 0.18);
        background.visible = fill.visible = true;
        background.position.copy(point);
        fill.position
          .copy(point)
          .addScaledVector(new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion), -0.5);
        fill.scale.set(Math.max(0, Math.min(1, dig.progress)), 0.08, 1);
      }
      // 目标圈只标可走面；`height` 是渲染高度，可走格永远不是土坎，所以这里
      // 仍是 1。（第二条件本身就是碰撞判据。）
      if (valid(goal) && height(goal) === 1 && map.collision[goal.y * map.w + goal.x] === 1) {
        goalMarker.visible = true;
        goalMarker.position.copy(worldOf(goal.x, goal.y, map.w, map.h)).setY(1.03);
      }
    },
    dispose() {
      scene.remove(...objects);
      box.dispose();
      edges.dispose();
      lineMaterial.dispose();
      crossGeometry.dispose();
      preview.material.dispose();
      background.material.dispose();
      fill.material.dispose();
      goalMarker.geometry.dispose();
      goalMarker.material.dispose();
    },
  };
}
export type VoxelCues = ReturnType<typeof createVoxelCues>;
