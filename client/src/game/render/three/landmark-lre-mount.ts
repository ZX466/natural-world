/** 把 vendored 的 LRE-DT100 试车台挂进 three 世界。
 *
 * 三条边界，写在这里免得以后被「顺手优化」掉：
 *
 * 1. **只做表现层，不改世界状态。** 规格文档要求把 `getOccupiedTiles()` 写进
 *    地图高度表，但碰撞是世界权威（服务端 `linhe-town.json` + `voxel.edited`
 *    事件）。客户端单方面加 17×15 格挡路会让前后端永久分叉，而且服务端寻路
 *    仍当那里可走。所以占地面只用来决定「放哪」，绝不写 `collision`。
 * 2. **不替换角色系统。** SDK 的 `linhe_voxel_avatar_3d.js` 是每角色 16 个
 *    Group + 46 个 Mesh、各带材质和贴图；本仓 `avatar3d.ts` 已改成 1 个
 *    SkinnedMesh / 16 骨骼 / 共享图集（51 人 = 51 次 draw call 而不是 2346 次），
 *    且已验收并转默认。替换等于性能倒退，故 SDK 角色模块只入库做参照，不接线。
 * 3. **失败静默降级。** 建不起来（没有平地、WebGL 不支持 shader）就只少一座
 *    地标，绝不能让整个世界起不来。
 */
import * as THREE from 'three';
import { LRETestStandBuilding } from '@vendor/linhe-lre-sdk/src/buildings/linhe_lre_test_stand_building.js';
import { findStandPlot, type StandPlot } from './landmark-lre';

/** 悬停射线的最小间隔：与 `three-world.ts` 里体素悬停的 50ms 同一口径。 */
const HOVER_INTERVAL_MS = 50;

export interface LandmarkMount {
  readonly plot: StandPlot;
  /** 每帧推进：转子自转、TVC 摆动、尾焰与粒子。 */
  update(dtSeconds: number, elapsedSeconds: number): void;
  /** 指针悬停到某个子部件时高亮它；NDC 传 NaN 表示清除高亮。
   *  `nowMs` 用于节流（与体素悬停的 50ms 同一口径）。 */
  hover(ndcX: number, ndcY: number, camera: THREE.PerspectiveCamera, nowMs: number): void;
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

/** 在 `heightOf` 描述的地形上找一块 17×15 平地并建塔。找不到返回 null。 */
export function mountLandmark(
  scene: THREE.Scene,
  mapW: number,
  mapH: number,
  heightOf: (x: number, y: number) => number,
): LandmarkMount | null {
  const plot = findStandPlot(mapW, mapH, heightOf);
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

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let hovered: number | null = null;
  let lastProbeAt = -Infinity;
  let lastKey = '';

  const clearHover = (): void => {
    lastKey = '';
    if (hovered === null) return;
    hovered = null;
    building.hoveredPartId = null;
    building.applyHighlightStates();
  };

  return {
    plot,
    update(dtSeconds, elapsedSeconds) {
      building.update(dtSeconds, elapsedSeconds);
    },
    hover(ndcX, ndcY, camera, nowMs) {
      if (!Number.isFinite(ndcX) || !Number.isFinite(ndcY)) {
        clearHover();
        return;
      }
      // 同一个 NDC 格 + 同一帧相机矩阵不重复投射；50ms 下限与体素悬停一致。
      const key = `${ndcX.toFixed(3)}:${ndcY.toFixed(3)}:${camera.matrixWorld.elements.join(',')}`;
      if (key === lastKey || nowMs - lastProbeAt < HOVER_INTERVAL_MS) return;
      lastKey = key;
      lastProbeAt = nowMs;

      pointer.set(ndcX, ndcY);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(building.interactiveMeshes, false)[0];
      const partId: number | null =
        hit && typeof hit.object.userData.partId === 'number' ? hit.object.userData.partId : null;
      if (partId === hovered) return;
      hovered = partId;
      building.hoveredPartId = partId;
      building.applyHighlightStates();
    },
    dispose() {
      scene.remove(building.root);
      disposeTree(building.root);
    },
  };
}
