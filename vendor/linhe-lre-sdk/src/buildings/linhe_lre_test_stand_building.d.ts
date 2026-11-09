/** `linhe_lre_test_stand_building.js` 是原样引入的外部 ES Module（见该文件头），
 *  这里只声明本项目实际用到的那部分表面，不追求把 1489 行 JS 全量类型化。
 *  改 vendored 文件的接口时**同时改这里**，否则类型与运行时静默脱节。
 *  文件名必须与 `.js` 同名，TS 才会自动配对。 */
import type * as THREE from 'three';

export interface StandPartMeta {
  readonly id: number;
  readonly name: string;
  readonly en: string;
  readonly mat: string;
  readonly env: string;
  readonly stage: number;
  readonly explodeVec: readonly [number, number, number];
  readonly desc: string;
}

export interface StandSystem {
  readonly sysId: number;
  readonly sysName: string;
  readonly parts: readonly StandPartMeta[];
}

export interface StandTile {
  readonly gx: number;
  readonly gz: number;
  readonly topY: number;
}

export interface StandBuildingOptions {
  readonly tileX?: number;
  readonly tileZ?: number;
  readonly groundY?: number;
  readonly scale?: number;
}

export interface StandTelemetry {
  readonly pitchDeg: number;
  readonly yawDeg: number;
  readonly effThrottle: number;
}

export declare const SYSTEMS_CATALOG: readonly StandSystem[];
export declare const PARTS_BY_ID: Readonly<Record<number, StandPartMeta>>;

export declare class LRETestStandBuilding {
  constructor(options?: StandBuildingOptions);
  readonly root: THREE.Group;
  readonly interactiveMeshes: THREE.Mesh[];
  hoveredPartId: number | null;
  selectedPartId: number;
  throttleValue: number;
  isFiring: boolean;
  getWorldCenter(target?: THREE.Vector3): THREE.Vector3;
  getOccupiedTiles(): StandTile[];
  getPlatformStandPoint(side?: 'left' | 'right'): THREE.Vector3;
  setViewMode(mode: 'pbr' | 'holo' | 'flir'): void;
  setExplodePercentage(percent: number): void;
  applyHighlightStates(): void;
  update(dtSeconds: number, elapsedSeconds: number): StandTelemetry;
}
