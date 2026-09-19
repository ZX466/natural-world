/**
 * client/src/game/world-mirror.ts — 世界镜像（普通 TS 类，非 React 状态）。
 *
 * m0-client.md §9 裁决（codex 意见 4）：高频实体数据完全绕开 React，
 * 镜像是普通类；薄 Zustand 适配层只暴露白名单低频字段。
 * codex 意见 9：ws 重连时必须全量重置本镜像（防增量丢失造成表现层幻觉）。
 */
import type { components } from '@shared/protocol';

type Actor = components['schemas']['Actor'];
type ActorDelta = components['schemas']['ActorDelta'];
type Light = components['schemas']['Light'];
type LightDelta = components['schemas']['LightDelta'];
export type RToken = string;

export interface MirrorActor {
  rtoken: RToken;
  x: number;
  y: number;
  facing: string;
  sprite: string;
  anim: string;
  tint?: number | undefined;
}

export interface MirrorLight {
  rtoken: RToken;
  x: number;
  y: number;
  radius: number;
  kind: string;
  flicker: number;
}

export interface MapStatic {
  w: number;
  h: number;
  tileset: string;
  /** 碰撞层走 HTTP 一次性加载（codex 意见 5：静态资产≠状态流）。M0 mock 用布尔网格。 */
  collision: Uint8Array;
}

export class WorldMirror {
  actors = new Map<RToken, MirrorActor>();
  lights = new Map<RToken, MirrorLight>();
  map: MapStatic | null = null;
  /** 主角 rtoken（M0 第一个 actor 即主角；M1 由协议显式指定） */
  protagonist: RToken | null = null;
  /** 重连计数（ws.ts 全量重置时递增，供 Phaser 侧清空精灵池） */
  resetCount = 0;

  applySnapshot(actors: readonly Actor[], lights: readonly Light[]): void {
    this.actors.clear();
    for (const a of actors) {
      this.actors.set(a.rtoken, { ...a });
    }
    this.lights.clear();
    for (const l of lights) {
      this.lights.set(l.rtoken, { ...l });
    }
    if (this.protagonist === null && actors.length > 0) {
      this.protagonist = actors[0]?.rtoken ?? null;
    }
  }

  applyActorDeltas(deltas: readonly ActorDelta[]): void {
    for (const d of deltas) {
      if (d.op === 'remove') {
        this.actors.delete(d.rtoken);
        continue;
      }
      const cur = this.actors.get(d.rtoken);
      if (d.op === 'add' || cur === undefined) {
        this.actors.set(d.rtoken, {
          rtoken: d.rtoken,
          x: d.x ?? 0,
          y: d.y ?? 0,
          facing: d.facing ?? 's',
          sprite: d.sprite ?? 'placeholder',
          anim: d.anim ?? 'idle',
          tint: d.tint,
        });
        continue;
      }
      if (d.x !== undefined) cur.x = d.x;
      if (d.y !== undefined) cur.y = d.y;
      if (d.facing !== undefined) cur.facing = d.facing;
      if (d.sprite !== undefined) cur.sprite = d.sprite;
      if (d.anim !== undefined) cur.anim = d.anim;
      if (d.tint !== undefined) cur.tint = d.tint;
    }
  }

  applyLightDeltas(deltas: readonly LightDelta[]): void {
    for (const d of deltas) {
      const cur = this.lights.get(d.rtoken);
      if (cur && d.flicker !== undefined) cur.flicker = d.flicker;
    }
  }

  setMap(map: MapStatic): void {
    this.map = map;
  }

  /** codex 意见 9：重连必须全量重置——增量漂移会把「不存在的实体」画给玩家。 */
  reset(): void {
    this.actors.clear();
    this.lights.clear();
    this.protagonist = null;
    this.resetCount += 1;
  }
}
