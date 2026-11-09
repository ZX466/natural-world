import * as THREE from 'three';
import { expect, it, vi } from 'vitest';

/** `mountLandmark` 的两条硬边界：没平地不建、建完必须能整棵释放。
 *  这里桩掉 vendored 模块，只验挂载层的契约（真建模需要 WebGL 上下文）。 */
it('does not build anything when no flat plot fits', async () => {
  vi.resetModules();
  const created = vi.fn();
  vi.doMock('@vendor/linhe-lre-sdk/src/buildings/linhe_lre_test_stand_building.js', () => ({
    LRETestStandBuilding: class {
      constructor() {
        created();
      }
    },
  }));
  const { mountLandmark } = await import('../landmark-lre-mount');
  const scene = new THREE.Scene();
  const mount = mountLandmark(scene, 8, 8, () => 1);
  expect(mount).toBeNull();
  expect(created).not.toHaveBeenCalled();
  expect(scene.children).toHaveLength(0);
  vi.doUnmock('@vendor/linhe-lre-sdk/src/buildings/linhe_lre_test_stand_building.js');
});

it('adds one root, forwards hover by partId, and releases the tree on dispose', async () => {
  vi.resetModules();
  const scene = new THREE.Scene();
  const geometry = new THREE.BoxGeometry();
  const material = new THREE.MeshBasicMaterial();
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData.partId = 7;
  const root = new THREE.Group();
  root.add(mesh);
  const dispose = vi.fn();
  let hovered: number | null = null;
  let highlights = 0;

  vi.doMock('@vendor/linhe-lre-sdk/src/buildings/linhe_lre_test_stand_building.js', () => ({
    LRETestStandBuilding: class {
      root = root;
      interactiveMeshes = [mesh];
      selectedPartId = 9;
      throttleValue = 1;
      isFiring = true;
      get hoveredPartId(): number | null {
        return hovered;
      }
      set hoveredPartId(value: number | null) {
        hovered = value;
      }
      applyHighlightStates() {
        highlights += 1;
      }
      update() {
        return { pitchDeg: 0, yawDeg: 0, effThrottle: 1 };
      }
    },
  }));
  // 释放走的是材质/几何的 dispose，这里只关心「被调用过」。
  const realDispose = THREE.BufferGeometry.prototype.dispose;
  THREE.BufferGeometry.prototype.dispose = dispose;

  const { mountLandmark } = await import('../landmark-lre-mount');
  const mount = mountLandmark(scene, 40, 40, () => 1);
  expect(mount).not.toBeNull();
  expect(scene.children).toHaveLength(1);

  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  camera.position.set(0, 0, 5);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  // 屏幕正中射线命中 mesh（mesh 在原点、无变换）。
  mount!.hover(0, 0, camera, 0);
  expect(hovered).toBe(7);
  expect(highlights).toBeGreaterThan(0);

  const before = highlights;
  mount!.hover(0, 0, camera, 1000); // 同一个部件：不重复刷高亮
  expect(highlights).toBe(before);

  // NaN 表示指针离开画布 / 开始转视角：必须清掉高亮。
  mount!.hover(Number.NaN, Number.NaN, camera, 1100);
  expect(hovered).toBeNull();

  mount!.dispose();
  expect(dispose).toHaveBeenCalled();
  expect(scene.children).toHaveLength(0);

  THREE.BufferGeometry.prototype.dispose = realDispose;
  vi.doUnmock('@vendor/linhe-lre-sdk/src/buildings/linhe_lre_test_stand_building.js');
});
