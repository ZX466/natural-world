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
export type VoxelEdit = components['schemas']['VoxelEdit'];
type VoxelState = components['schemas']['VoxelStateMessage'];
export type RToken = string;

export interface MirrorActor {
  rtoken: RToken;
  x: number;
  y: number;
  facing: string;
  sprite: string;
  anim: string;
  tint?: number | undefined;
  /** 批次 D10：戏内显示名（协议 1.4 可选字段；头顶名字供数） */
  name?: string | undefined;
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
  /** 碰撞层由 HTTP 快照加载，挖放增量就地更新；切分支后重新取图。 */
  collision: Uint8Array;
  /** M7-T6：地面 tile id 网格（u16，调色板值域）；mock 模式无此层（色块渲染回退）。 */
  ground?: Uint16Array;
}

export class WorldMirror {
  actors = new Map<RToken, MirrorActor>();
  lights = new Map<RToken, MirrorLight>();
  map: MapStatic | null = null;
  voxelEdits = new Map<string, VoxelEdit>();
  voxelDig: VoxelState['dig'] = null;
  voxelSnapshotVersion = 0;
  /** Presentation changes only; idle frames and dig progress need no terrain comparison. */
  terrainVersion = 0;
  private baseCollision: Uint8Array | null = null;
  private baseGround: Uint16Array | null = null;
  /** 主角 rtoken（M0 第一个 actor 即主角；M1 由协议显式指定） */
  protagonist: RToken | null = null;
  /** 重连计数（ws.ts 全量重置时递增，供 Phaser 侧清空精灵池） */
  resetCount = 0;
  /** 戏内天气（批次 D7）：日级视觉状态（服务端权威，快照/delta 随行） */
  weather = { visual: 'clear', ambientLight: 1.0 };
  /** D14 头顶气泡：{戏内名: {text, 到期时刻 ms}}（bubble 独白按 name 落） */
  bubbles = new Map<string, { text: string; expiresAt: number }>();
  /** 批次 E7：结构投影（rtoken → {tiles, phase}；delta upsert / 快照全量） */
  structures = new Map<string, { tiles: [number, number][]; phase: string }>();

  /** E7：结构增量 upsert（同 rtoken 重声明=覆盖；相位即最新）。
   *  op/x/y/phase 按生成类型可选——缺省按 add/built 兜底（服务端总是带齐）。 */
  applyStructures(
    list: readonly {
      readonly op?: 'add' | 'remove';
      readonly rtoken: string;
      readonly x?: number;
      readonly y?: number;
      readonly phase?: 'built' | 'collapsing' | 'rubble';
    }[],
    replace = false,
  ): void {
    let changed = replace;
    if (replace) this.structures.clear();
    for (const s of list) {
      if (s.op === 'remove') {
        if (this.structures.delete(s.rtoken)) changed = true;
        continue;
      }
      const x = s.x ?? 0;
      const y = s.y ?? 0;
      const phase = s.phase ?? 'built';
      const cur = this.structures.get(s.rtoken);
      if (cur) {
        if (!cur.tiles.some(([tx, ty]) => tx === x && ty === y)) {
          cur.tiles.push([x, y]);
          changed = true;
        }
        if (cur.phase !== phase) changed = true;
        cur.phase = phase;
      } else {
        this.structures.set(s.rtoken, { tiles: [[x, y]], phase });
        changed = true;
      }
    }
    if (changed) this.terrainVersion += 1;
  }

  /** 记一条头顶气泡（D14；durationMs 由调用方给，WorldScene 逐帧清理过期） */
  setBubble(name: string, text: string, durationMs: number, nowMs: number): void {
    this.bubbles.set(name, { text, expiresAt: nowMs + durationMs });
  }

  /** 到期气泡清理（WorldScene update 每帧调；返回是否清了东西）。 */
  pruneBubbles(nowMs: number): boolean {
    let pruned = false;
    for (const [name, b] of this.bubbles) {
      if (b.expiresAt <= nowMs) {
        this.bubbles.delete(name);
        pruned = true;
      }
    }
    return pruned;
  }

  applySnapshot(
    actors: readonly Actor[],
    lights: readonly Light[],
    weather?: { visual: string; ambientLight: number },
  ): void {
    if (weather) this.weather = { ...weather };
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

  setWeather(weather: { visual: string; ambientLight: number }): void {
    this.weather = { ...weather };
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
          sprite: d.sprite ?? 'villager',
          anim: d.anim ?? 'idle',
          tint: d.tint,
          name: d.name,
        });
        continue;
      }
      if (d.x !== undefined) cur.x = d.x;
      if (d.y !== undefined) cur.y = d.y;
      if (d.facing !== undefined) cur.facing = d.facing;
      if (d.sprite !== undefined) cur.sprite = d.sprite;
      if (d.anim !== undefined) cur.anim = d.anim;
      if (d.tint !== undefined) cur.tint = d.tint;
      if (d.name !== undefined) cur.name = d.name;
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
    this.baseCollision = map.collision.slice();
    this.baseGround = map.ground?.slice() ?? null;
    this.reapplyVoxelEdits();
    this.terrainVersion += 1;
  }

  applyVoxelEdits(rows: readonly VoxelEdit[], replace = false): void {
    let changed = replace;
    if (replace) {
      this.voxelEdits.clear();
      this.voxelDig = null;
      this.voxelSnapshotVersion += 1;
      if (this.map !== null && this.baseCollision !== null)
        this.map.collision.set(this.baseCollision);
      if (this.map?.ground && this.baseGround) this.map.ground.set(this.baseGround);
    }
    for (const row of rows) {
      if (
        !row ||
        !Number.isInteger(row.x) ||
        !Number.isInteger(row.y) ||
        row.x < 0 ||
        row.y < 0 ||
        (this.map !== null && (row.x >= this.map.w || row.y >= this.map.h)) ||
        !Number.isInteger(row.gid) ||
        row.gid < 0 ||
        row.gid > 65535 ||
        (row.action !== 'dig' && row.action !== 'place')
      )
        continue;
      const key = `${row.x},${row.y}`;
      const prior = this.voxelEdits.get(key);
      if (prior?.action === row.action && prior.gid === row.gid) continue;
      this.voxelEdits.set(key, { ...row });
      changed = true;
    }
    this.reapplyVoxelEdits();
    if (changed) this.terrainVersion += 1;
  }

  reapplyVoxelEdits(): void {
    const map = this.map;
    if (map === null) return;
    for (const row of this.voxelEdits.values()) {
      if (row.x >= map.w || row.y >= map.h) continue;
      const index = row.y * map.w + row.x;
      // gid is the committed TILE_CHANGED truth, including structure restores.
      map.collision[index] = row.gid === 0 ? 0 : 1;
      if (map.ground) map.ground[index] = row.gid;
    }
  }

  applyVoxelState(state: Pick<VoxelState, 'dig' | 'inventory'>): boolean {
    const inventory = state.inventory,
      dig = state.dig;
    if (!inventory || !Number.isInteger(inventory.earth) || inventory.earth < 0) return false;
    if (
      dig !== null &&
      (!dig ||
        typeof dig !== 'object' ||
        !Number.isInteger(dig.x) ||
        !Number.isInteger(dig.y) ||
        dig.x < 0 ||
        dig.y < 0 ||
        !Number.isFinite(dig.progress) ||
        dig.progress < 0 ||
        dig.progress > 1)
    )
      return false;
    this.voxelDig = dig === null ? null : { ...dig };
    this.reapplyVoxelEdits();
    return true;
  }

  /** codex 意见 9：重连必须全量重置——增量漂移会把「不存在的实体」画给玩家。 */
  reset(): void {
    this.applyVoxelEdits([], true);
    this.actors.clear();
    this.lights.clear();
    this.applyStructures([], true); // E7：重连重置结构投影（快照随后重灌全集）
    this.protagonist = null;
    this.resetCount += 1;
  }
}
