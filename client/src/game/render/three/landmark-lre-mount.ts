/** 把 vendored 的 LRE-DT100 试车台挂进 three 世界，并接上检修面板。
 *
 * 三条边界，写在这里免得以后被「顺手优化」掉：
 *
 * 1. **碰撞是世界权威，这里一格都不写。** 占地面在服务端地图 JSON 里已经
 *    变成不可走格（`build_god_town.derive_terrain`），客户端只按 `_structures`
 *    锚点把模型立在同一个矩形上。客户端单方面加墙会让 NPC 照穿、前后端判断打架。
 * 2. **不替换角色系统。** SDK 的 `linhe_voxel_avatar_3d.js` 是每角色 16 个
 *    Group + 46 个 Mesh、各带材质和贴图；本仓 `avatar3d.ts` 是 1 个 SkinnedMesh
 *    / 16 骨骼 / 共享图集（51 人 = 51 次 draw call 而不是 2346 次），且已验收并
 *    转默认。替换等于性能倒退，故 SDK 角色模块只入库做参照，不接线。
 * 3. **失败静默降级。** 建不起来（锚点缺失、WebGL 不支持 shader）就只少一座
 *    地标，绝不能让整个世界起不来。
 */
import * as THREE from 'three';
import {
  LRETestStandBuilding,
  PARTS_BY_ID,
  SYSTEMS_CATALOG,
} from '@vendor/linhe-lre-sdk/src/buildings/linhe_lre_test_stand_building.js';
import { standPlotFrom, type StandPlot } from './landmark-lre';
import { createLandmarkPanel, type LandmarkPanel } from './landmark-lre-panel';
import type { MapStructure } from '../../world-mirror';

/** 悬停射线的最小间隔：与 `three-world.ts` 里体素悬停的 50ms 同一口径。 */
const HOVER_INTERVAL_MS = 50;

export interface LandmarkMount {
  readonly plot: StandPlot;
  /** 每帧推进：转子自转、TVC 摆动、尾焰与粒子。 */
  update(dtSeconds: number, elapsedSeconds: number): void;
  /** 指针悬停到某个子部件时高亮它；NDC 传 NaN 表示清除高亮。
   *  `nowMs` 用于节流（与体素悬停的 50ms 同一口径）。
   *  `pointer` 为视口坐标（浮签定位用），缺省则不显示浮签。 */
  hover(
    ndcX: number,
    ndcY: number,
    camera: THREE.PerspectiveCamera,
    nowMs: number,
    pointer?: { x: number; y: number },
  ): void;
  /** 画布点击：命中部件则选中并返回 true（调用方据此**不**把这次点击当成移动）。 */
  pick(ndcX: number, ndcY: number, camera: THREE.PerspectiveCamera): boolean;
  dispose(): void;
}

/** vendored 模块没有 `dispose()`，它自己建的几何/材质/贴图必须由调用方遍历释放。
 *  这些资源不进 three 的全局缓存，漏掉就是每次重建都多留一份显存。 */
function disposeTree(root: THREE.Object3D): void {
  root.traverse((object) => {
    const mesh = object as THREE.Mesh;
    mesh.geometry?.dispose();
    const material = mesh.material as THREE.Material | THREE.Material[] | undefined;
    if (!material) return;
    for (const entry of Array.isArray(material) ? material : [material]) {
      for (const value of Object.values(entry)) {
        if (value instanceof THREE.Texture) value.dispose();
      }
      entry.dispose();
    }
  });
}

/** 极简天空环境贴图：上下渐变，靠 PMREM 生成 mip 链供粗糙度采样。
 *  和 `three-terrain.ts::skyTexture()` 同一组颜色，所以反射色与天空一致。
 *  返回 null 表示环境不可用（没有 2D 上下文），调用方照常建塔只是金属偏暗。 */
function skyEnvironment(renderer: THREE.WebGLRenderer): THREE.Texture | null {
  const canvas = document.createElement('canvas');
  canvas.width = 2;
  canvas.height = 128;
  const context = canvas.getContext('2d');
  if (context === null) return null;
  const gradient = context.createLinearGradient(0, 0, 0, 128);
  gradient.addColorStop(0, '#80b9e7');
  gradient.addColorStop(0.65, '#c8e0ef');
  gradient.addColorStop(1, '#e6eef2');
  context.fillStyle = gradient;
  context.fillRect(0, 0, 2, 128);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.mapping = THREE.EquirectangularReflectionMapping;
  const pmrem = new THREE.PMREMGenerator(renderer);
  // 注意：不能对 `target` 调 `dispose()` —— 那会连它挂着的 texture 一起删掉，
  // 我们要的正是那张。只释放 PMREM 的中间资源和源 canvas 贴图。
  const target = pmrem.fromEquirectangular(texture);
  pmrem.dispose();
  texture.dispose();
  return target.texture;
}

export interface MountLandmarkOptions {
  readonly scene: THREE.Scene;
  /** 只用于生成金属反射用的环境贴图；传 null（无 WebGL 的单测）就跳过环境。 */
  readonly renderer: THREE.WebGLRenderer | null;
  readonly mapW: number;
  readonly mapH: number;
  /** 服务端地图 `_structures` 的试车台锚点。缺省/不符 → 不建。 */
  readonly anchor: MapStructure | undefined;
  /** 面板与浮签的父容器（世界 canvas 的容器）。缺省 = 只要 3D 塔，
   *  不建检修面板（无 DOM 的单测走这条）。 */
  readonly host?: HTMLElement;
}

/** 按世界锚点建塔。锚点缺失或不符 → 返回 null（静默不建）。 */
export function mountLandmark(options: MountLandmarkOptions): LandmarkMount | null {
  const { scene, renderer, mapW, mapH, anchor, host } = options;
  const plot = standPlotFrom(anchor, mapW, mapH);
  if (plot === null) return null;

  let building: LRETestStandBuilding;
  try {
    building = new LRETestStandBuilding({
      tileX: plot.tileX,
      tileZ: plot.tileZ,
      groundY: plot.groundY,
      scale: 1,
    });
  } catch {
    // shader / canvas 不可用时只少一座地标。
    return null;
  }
  scene.add(building.root);
  // 试车台几乎全是 metalness 0.86~0.92 的 StandardMaterial。金属没有漫反射，
  // 场景里只有半球光 + 平行光时会渲成近乎全黑。给它的材质单独挂一张程序化天空
  // 反射贴图 —— **不设 `scene.environment`**：那会连带影响已验收的 Lambert
  // 角色，把它们的观感一起改掉。地形是 BasicMaterial 烤死顶点色，本来就不受影响。
  const environment = renderer === null ? null : skyEnvironment(renderer);
  if (environment) {
    building.root.traverse((object: THREE.Object3D) => {
      const material = (object as THREE.Mesh).material;
      if (!material) return;
      for (const entry of Array.isArray(material) ? material : [material]) {
        if (!(entry instanceof THREE.MeshStandardMaterial)) continue;
        entry.envMap = environment;
        entry.envMapIntensity = 1;
        entry.needsUpdate = true;
      }
    });
  }

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let hovered: number | null = null;
  let lastProbeAt = -Infinity;
  let lastKey = '';

  const setHover = (partId: number | null): void => {
    if (partId === hovered) return;
    hovered = partId;
    building.hoveredPartId = partId;
    building.applyHighlightStates();
  };

  // 没有 host = 无 DOM 环境（单测）：只要 3D 塔，面板用一个空实现。
  const ports = {
    select(partId: number | null) {
      // vendored 模块用 0 表示「未选中」，null 只在面板层出现。
      building.selectedPartId = partId ?? 0;
      building.applyHighlightStates();
    },
    hover(partId: number | null) {
      setHover(partId);
    },
    setExplode(percent: number) {
      building.setExplodePercentage(percent);
    },
    setView(mode: 'pbr' | 'holo' | 'flir') {
      building.setViewMode(mode);
    },
    setFiring(on: boolean) {
      building.isFiring = on;
    },
  };
  const panel: LandmarkPanel =
    host === undefined
      ? { hover() {}, select() {}, dispose() {} }
      : createLandmarkPanel(host, SYSTEMS_CATALOG, PARTS_BY_ID, ports);

  /** 射线打塔身，返回命中部件 id（没命中 = null）。 */
  const partAt = (ndcX: number, ndcY: number, camera: THREE.PerspectiveCamera): number | null => {
    pointer.set(ndcX, ndcY);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(building.interactiveMeshes, false)[0];
    return hit && typeof hit.object.userData.partId === 'number'
      ? hit.object.userData.partId
      : null;
  };

  return {
    plot,
    update(dtSeconds, elapsedSeconds) {
      building.update(dtSeconds, elapsedSeconds);
    },
    hover(ndcX, ndcY, camera, nowMs, pointerAt) {
      if (!Number.isFinite(ndcX) || !Number.isFinite(ndcY)) {
        lastKey = '';
        setHover(null);
        panel.hover(null, 0, 0);
        return;
      }
      // 同一个 NDC 格 + 同一帧相机矩阵不重复投射；50ms 下限与体素悬停一致。
      // 节流命中也继续把浮签挪到当前指针（悬停的是面板列表里的部件时，
      // 指针在动而射线没必要重打）。
      const key = `${ndcX.toFixed(3)}:${ndcY.toFixed(3)}:${camera.matrixWorld.elements.join(',')}`;
      if (key === lastKey || nowMs - lastProbeAt < HOVER_INTERVAL_MS) {
        if (pointerAt) panel.hover(hovered, pointerAt.x, pointerAt.y);
        return;
      }
      lastKey = key;
      lastProbeAt = nowMs;
      setHover(partAt(ndcX, ndcY, camera));
      panel.hover(hovered, pointerAt?.x ?? 0, pointerAt?.y ?? 0);
    },
    pick(ndcX, ndcY, camera) {
      const partId = partAt(ndcX, ndcY, camera);
      if (partId === null) return false;
      building.selectedPartId = partId;
      building.applyHighlightStates();
      panel.select(partId);
      return true;
    },
    dispose() {
      panel.dispose();
      scene.remove(building.root);
      disposeTree(building.root);
      environment?.dispose();
    },
  };
}
