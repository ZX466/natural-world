/**
 * client/src/game/scenes/WorldScene.ts — 主场景（m0-client.md §4.2）。
 *
 * 瓦片地图 + 池化精灵 + 位置插值 + 点击寻路（路径由 sim 算，前端只发目标格）
 * + 昼夜色罩（读 uiStore 的 phase）。Phaser 侧不 import React 组件。
 */
import Phaser from 'phaser';
import type { WorldMirror } from '../world-mirror';

const PIXEL_SCALE = 2; // 俯视像素调性，M0 固定 2x
const TILE = 16;
const INTERP_MS = 1000 / 60; // tick 间隔（60tps @1x；倍速插值由 sim 侧节奏吸收）

interface ActorView {
  sprite: Phaser.GameObjects.Rectangle;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  interpStart: number;
}

export class WorldScene extends Phaser.Scene {
  private mirror: WorldMirror;
  private views = new Map<string, ActorView>();
  private mapLayer: Phaser.GameObjects.Graphics | null = null;
  private nightOverlay: Phaser.GameObjects.Rectangle | null = null;
  private lastResetSeen = -1;
  private goalMarker: Phaser.GameObjects.Arc | null = null;

  constructor(mirror: WorldMirror) {
    super({ key: 'world' });
    this.mirror = mirror;
  }

  create(): void {
    this.mapLayer = this.add.graphics();
    this.nightOverlay = this.add
      .rectangle(0, 0, this.scale.width, this.scale.height, 0x0a1030, 0)
      .setOrigin(0)
      .setScrollFactor(0)
      .setDepth(100);
    this.goalMarker = this.add.circle(0, 0, 3, 0xffd75e).setVisible(false).setDepth(50);

    this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      this.handlePointer(pointer);
    });

    this.scale.on('resize', () => this.redrawMap());
    this.redrawMap();
  }

  /** M0：无 tileset 资产时以网格色块渲染（瓦片可通行=浅色，不可=深色）。 */
  private redrawMap(): void {
    const g = this.mapLayer;
    const map = this.mirror.map;
    if (g === null) return;
    g.clear();
    if (map === null) {
      // 无地图：铺 32x32 默认可通行网格
      g.fillStyle(0x3a4a3f, 1);
      g.fillRect(0, 0, 32 * TILE, 32 * TILE);
      return;
    }
    for (let y = 0; y < map.h; y += 1) {
      for (let x = 0; x < map.w; x += 1) {
        const walkable = map.collision[y * map.w + x] === 1;
        g.fillStyle(walkable ? 0x4a5d4e : 0x2a3038, 1);
        g.fillRect(x * TILE, y * TILE, TILE - 1, TILE - 1);
      }
    }
  }

  private handlePointer(pointer: Phaser.Input.Pointer): void {
    if (this.mirror.protagonist === null || this.mirror.map === null) return;
    const wx = Math.floor(pointer.worldX / TILE);
    const wy = Math.floor(pointer.worldY / TILE);
    const map = this.mirror.map;
    if (wx < 0 || wy < 0 || wx >= map.w || wy >= map.h) return;
    if (map.collision[wy * map.w + wx] !== 1) return; // 目标不可通行，不请求
    this.goalMarker?.setPosition(wx * TILE + TILE / 2, wy * TILE + TILE / 2).setVisible(true);
    // sim 负责寻路（世界真相在 sim）；前端发的是玩家对主角的「移动请求」——
    // M0 协议暂缺 move 消息，用 player_impulse 的移动意图占位（kilo 已知缺口，见主树留言）
    this.game.events.emit('client:move_request', { x: wx, y: wy });
  }

  update(_time: number, delta: number): void {
    this.syncActorViews(delta);
    this.syncCamera();
    this.syncOverlay();
  }

  private syncActorViews(delta: number): void {
    if (this.mirror.resetCount !== this.lastResetSeen) {
      // 镜像被重连重置：清空精灵池重建（codex 意见 9 的表现层配合）
      for (const v of this.views.values()) v.sprite.destroy();
      this.views.clear();
      this.lastResetSeen = this.mirror.resetCount;
    }
    const t = Math.min(1, delta / INTERP_MS);
    for (const [rtoken, actor] of this.mirror.actors) {
      let view = this.views.get(rtoken);
      if (view === undefined) {
        const isProtagonist = rtoken === this.mirror.protagonist;
        const sprite = this.add
          .rectangle(
            actor.x * TILE + TILE / 2,
            actor.y * TILE + TILE / 2,
            TILE - 4,
            TILE - 4,
            isProtagonist ? 0xe8c39e : 0x9aa7b0,
          )
          .setDepth(10);
        view = {
          sprite,
          fromX: actor.x,
          fromY: actor.y,
          toX: actor.x,
          toY: actor.y,
          interpStart: 0,
        };
        this.views.set(rtoken, view);
        if (isProtagonist) this.cameras.main.startFollow(sprite, true, 0.12, 0.12);
      }
      const targetX = actor.x * TILE + TILE / 2;
      const targetY = actor.y * TILE + TILE / 2;
      // 相邻 tick 快照间线性插值（m0-client §3）
      view.sprite.x = Phaser.Math.Linear(view.sprite.x, targetX, t);
      view.sprite.y = Phaser.Math.Linear(view.sprite.y, targetY, t);
      view.sprite.setFillStyle(
        actor.tint ?? (rtoken === this.mirror.protagonist ? 0xe8c39e : 0x9aa7b0),
      );
    }
    // 移除已消失的 actor
    for (const [rtoken, view] of this.views) {
      if (!this.mirror.actors.has(rtoken)) {
        view.sprite.destroy();
        this.views.delete(rtoken);
      }
    }
  }

  private syncCamera(): void {
    const map = this.mirror.map;
    if (map === null) return;
    this.cameras.main.setBounds(0, 0, map.w * TILE, map.h * TILE);
    this.cameras.main.setZoom(PIXEL_SCALE);
  }

  private syncOverlay(): void {
    const overlay = this.nightOverlay;
    if (overlay === null) return;
    // 读薄 store（低频；Zustand 非 React 用法 getState，不触发渲染树）
    import('../../store/uiStore').then(({ useUiStore }) => {
      const phase = useUiStore.getState().gameClock?.phase ?? 'day';
      const alpha = { day: 0, dawn: 0.12, dusk: 0.2, night: 0.38 }[phase];
      overlay.setFillStyle(0x0a1030, alpha);
    });
  }
}
