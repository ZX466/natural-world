import * as THREE from 'three';
import { expect, it, vi } from 'vitest';

const VENDOR = '@vendor/linhe-lre-sdk/src/buildings/linhe_lre_test_stand_building.js';
const ANCHOR = { x: 20, y: 20, w: 17, h: 15 };

/** `mountLandmark` 的硬边界：没锚点不建、建完必须能整棵释放、点中部件必须被
 *  识别成「选中」而不是「走到那里」。这里桩掉 vendored 模块，只验挂载层的
 *  契约（真建模需要 WebGL 上下文；面板 DOM 由浏览器实测覆盖，见 README）。 */
it('does not build anything when the map carries no anchor', async () => {
  vi.resetModules();
  const created = vi.fn();
  vi.doMock(VENDOR, () => ({
    LRETestStandBuilding: class {
      constructor() {
        created();
      }
    },
    SYSTEMS_CATALOG: [],
    PARTS_BY_ID: {},
  }));
  const { mountLandmark } = await import('../landmark-lre-mount');
  const scene = new THREE.Scene();
  const mount = mountLandmark({ scene, renderer: null, mapW: 40, mapH: 40, anchor: undefined });
  expect(mount).toBeNull();
  expect(created).not.toHaveBeenCalled();
  expect(scene.children).toHaveLength(0);
  vi.doUnmock(VENDOR);
});

it('builds at the world anchor, identifies parts, and releases everything on dispose', async () => {
  vi.resetModules();
  const scene = new THREE.Scene();
  const geometry = new THREE.BoxGeometry();
  const material = new THREE.MeshBasicMaterial();
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData.partId = 7;
  const root = new THREE.Group();
  root.add(mesh);
  const dispose = vi.fn();
  const state = { hovered: null as number | null, selected: 0 };
  const options = { tileX: Number.NaN, tileZ: Number.NaN };

  vi.doMock(VENDOR, () => ({
    LRETestStandBuilding: class {
      root = root;
      interactiveMeshes = [mesh];
      throttleValue = 1;
      constructor(opts: { tileX: number; tileZ: number }) {
        options.tileX = opts.tileX;
        options.tileZ = opts.tileZ;
      }
      get hoveredPartId(): number | null {
        return state.hovered;
      }
      set hoveredPartId(value: number | null) {
        state.hovered = value;
      }
      get selectedPartId(): number {
        return state.selected;
      }
      set selectedPartId(value: number) {
        state.selected = value;
      }
      applyHighlightStates() {}
      update() {
        return { pitchDeg: 0, yawDeg: 0, effThrottle: 1 };
      }
    },
    SYSTEMS_CATALOG: [],
    PARTS_BY_ID: {},
  }));
  // 释放走的是几何/材质的 dispose，这里只关心「被调用过」。
  const realDispose = THREE.BufferGeometry.prototype.dispose;
  THREE.BufferGeometry.prototype.dispose = dispose;

  const { mountLandmark } = await import('../landmark-lre-mount');
  const mount = mountLandmark({ scene, renderer: null, mapW: 40, mapH: 40, anchor: ANCHOR });
  expect(mount).not.toBeNull();
  expect(scene.children).toHaveLength(1);
  // 世界坐标（不是格子下标）：20 - 40/2 + 0.5 = 0.5。
  expect(options.tileX).toBe(0.5);
  expect(options.tileZ).toBe(0.5);
  expect(mount!.plot).toMatchObject({ gridX: 20, gridY: 20, groundY: 1 });

  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  camera.position.set(0, 0, 5);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);

  // 屏幕正中射线命中 mesh（mesh 在原点、无变换）→ 悬停识别。
  mount!.hover(0, 0, camera, 0);
  expect(state.hovered).toBe(7);

  // NaN = 指针离开画布 / 开始转视角：高亮必须清掉，否则会一直亮着。
  mount!.hover(Number.NaN, Number.NaN, camera, 1000);
  expect(state.hovered).toBeNull();

  // 画布点击命中部件 → 选中它，并且调用方知道「这次点击不是移动」。
  expect(mount!.pick(0, 0, camera)).toBe(true);
  expect(state.selected).toBe(7);
  // 点空白处（无 mesh）→ false，让正常移动逻辑接管。
  const blankCamera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  blankCamera.position.set(50, 50, 50);
  blankCamera.lookAt(100, 100, 100);
  blankCamera.updateMatrixWorld(true);
  expect(mount!.pick(0, 0, blankCamera)).toBe(false);

  mount!.dispose();
  expect(dispose).toHaveBeenCalled();
  expect(scene.children).toHaveLength(0);

  THREE.BufferGeometry.prototype.dispose = realDispose;
  vi.doUnmock(VENDOR);
});
