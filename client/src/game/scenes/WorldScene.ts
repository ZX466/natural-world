/**
 * client/src/game/scenes/WorldScene.ts — 主场景（m0-client.md §4.2）。
 *
 * 瓦片地图 + 池化精灵 + 位置插值 + 点击寻路（路径由 sim 算，前端只发目标格）
 * + 昼夜色罩（读 uiStore 的 phase）。Phaser 侧不 import React 组件。
 */
import Phaser from 'phaser';
import type { WorldMirror } from '../world-mirror';
import { facingRow, walkFrame, advanceAnimClock, inferFacing, type Facing } from '../render/actors';
import { useUiStore } from '../../store/uiStore';

const PIXEL_SCALE = 3; // 批次 D8：2x→3x（48×48 镇铺满视口，人物可辨）
const TILE = 16;
// 批次 D1：插值窗口 = 行走节拍（sim 侧 15 tick/格 @1x = 250ms/格）。
// 服务端每 delta 帧给出新格坐标，客户端在 250ms 内平滑走完一格——
// 1x 手感对齐；16x 快进时 sim 节奏加快，帧到得更密，窗口缩短自然适配。
const INTERP_MS = 250;
const TILESET_KEY = 'sprout-tileset'; // 图集加载键（main.ts preload 同名）
const GROUND_KEY = 'ground-composite'; // 预拼地面 CanvasTexture 键

interface ActorView {
  sprite: Phaser.GameObjects.Sprite;
  /** 上一帧逻辑格（anim/facing 推断输入，R2） */
  prevX: number;
  prevY: number;
  /** walk 动画钟（位移中累加 delta；静止归 -1=站立帧） */
  animClockMs: number;
  /** H-3：最后非零朝向（停下沿用，不转身） */
  lastFacing: 'n' | 'e' | 's' | 'w';
}

export class WorldScene extends Phaser.Scene {
  private mirror: WorldMirror;
  private views = new Map<string, ActorView>();
  private mapLayer: Phaser.GameObjects.Graphics | null = null;
  private groundImage: Phaser.GameObjects.Image | null = null;
  private nightOverlay: Phaser.GameObjects.Rectangle | null = null;
  private rainLayer: Phaser.GameObjects.Graphics | null = null;
  private rainDrops: { x: number; y: number; speed: number }[] = [];
  private lastResetSeen = -1;
  private goalMarker: Phaser.GameObjects.Arc | null = null;

  constructor(mirror: WorldMirror) {
    super({ key: 'world' });
    this.mirror = mirror;
  }

  preload(): void {
    // M7-T6：图集与角色表（Vite public 静态服务；sim 只发 id 不发素材）。
    this.load.image(TILESET_KEY, '/assets/tilesets/sprout-tileset.png');
    this.load.spritesheet('chenmo', '/assets/actors/chenmo.png', {
      frameWidth: 16,
      frameHeight: 16,
    });
    this.load.spritesheet('villager', '/assets/actors/villager.png', {
      frameWidth: 16,
      frameHeight: 16,
    });
  }

  create(): void {
    this.mapLayer = this.add.graphics();
    this.nightOverlay = this.add
      .rectangle(0, 0, this.scale.width, this.scale.height, 0x0a1030, 0)
      .setOrigin(0)
      .setScrollFactor(0)
      .setDepth(100);
    // 批次 D7：雨层（短雨丝 Graphics；雨落动画在 update 里逐帧推进）
    this.rainLayer = this.add.graphics().setScrollFactor(0).setDepth(99);
    this.goalMarker = this.add.circle(0, 0, 3, 0xffd75e).setVisible(false).setDepth(50);

    this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      this.handlePointer(pointer);
    });

    this.scale.on('resize', () => this.redrawMap());
    this.redrawMap();
    // 地图 HTTP 加载是异步的：真实模式下晚于镜像到达 → 轮询重绘（mock 即时 setMap 无需等待）
    const waitMap = setInterval(() => {
      if (this.mirror.map !== null) {
        clearInterval(waitMap);
        this.redrawMap();
      }
    }, 250);
    this.events.once('shutdown', () => clearInterval(waitMap));
  }

  /** M0：无 tileset 资产时以网格色块渲染（瓦片可通行=浅色，不可=深色）。
   *  M7-T6：tileset≠'grid' 且镜像带 ground 层 → 图集拼合渲染（色块层保持清空）。 */
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
    if (map.tileset !== 'grid' && map.ground && this.textures.exists(TILESET_KEY)) {
      this.renderTileset(map);
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

  /** 图集渲染（M7-T6）：ground id → 图集帧，预拼到一张 CanvasTexture 上，
   *  再以单张 image 显示（整图 48×48×16px=768px 方；一次绘制零每帧成本）。
   *  不可行方案记录：Phaser Graphics **无 drawImage**（tsc 实证）——
   *  逐格 blitter 是备选，本方案更简单且静态层不重绘。 */
  private renderTileset(map: NonNullable<WorldMirror['map']>): void {
    const img = this.textures.get(TILESET_KEY).getSourceImage() as HTMLImageElement;
    const cols = Math.floor(img.width / TILE);
    const canvas = document.createElement('canvas');
    canvas.width = map.w * TILE;
    canvas.height = map.h * TILE;
    const ctx = canvas.getContext('2d');
    if (ctx === null) return;
    for (let y = 0; y < map.h; y += 1) {
      for (let x = 0; x < map.w; x += 1) {
        const id = map.ground![y * map.w + x] ?? 0;
        ctx.drawImage(
          img,
          (id % cols) * TILE,
          Math.floor(id / cols) * TILE,
          TILE,
          TILE,
          x * TILE,
          y * TILE,
          TILE,
          TILE,
        );
      }
    }
    if (this.textures.exists(GROUND_KEY)) this.textures.remove(GROUND_KEY);
    this.textures.addCanvas(GROUND_KEY, canvas);
    if (this.groundImage === null) {
      this.groundImage = this.add.image(0, 0, GROUND_KEY).setOrigin(0).setDepth(0);
    } else {
      this.groundImage.setTexture(GROUND_KEY);
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
    this.syncRain(delta);
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
        // M7-T7：矩形色块 → 真精灵（主角=chenmo 走环；村民=villager 站立帧）
        const sprite = this.add
          .sprite(
            actor.x * TILE + TILE / 2,
            actor.y * TILE + TILE / 2,
            isProtagonist ? 'chenmo' : 'villager',
            0,
          )
          .setDepth(10);
        view = { sprite, prevX: actor.x, prevY: actor.y, animClockMs: -1, lastFacing: 's' as Facing };
        this.views.set(rtoken, view);
        if (isProtagonist) this.cameras.main.startFollow(sprite, true, 0.12, 0.12);
      }
      const targetX = actor.x * TILE + TILE / 2;
      const targetY = actor.y * TILE + TILE / 2;
      // 相邻 tick 快照间线性插值（m0-client §3）
      view.sprite.x = Phaser.Math.Linear(view.sprite.x, targetX, t);
      view.sprite.y = Phaser.Math.Linear(view.sprite.y, targetY, t);
      // R2：位移推断 anim/facing → 帧号（villager 无 walk 环，恒帧 0；R7 静止）
      if (rtoken === this.mirror.protagonist) {
        const moved = view.prevX !== actor.x || view.prevY !== actor.y;
        // H-2：walk 累加/idle 归 -1（修前写反 → 循环死在第 0 帧）
        view.animClockMs = advanceAnimClock(view.animClockMs, moved, delta);
        // H-3：零位移沿用 lastFacing（停下不转身）；frameOf 只用方向行号
        if (moved) {
          view.lastFacing = inferFacing(actor.x - view.prevX, actor.y - view.prevY, view.lastFacing);
        }
        view.sprite.setFrame(walkFrame(facingRow(view.lastFacing), view.animClockMs));
        view.prevX = actor.x;
        view.prevY = actor.y;
      }
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
    if (overlay.width !== this.scale.width || overlay.height !== this.scale.height) {
      overlay.setSize(this.scale.width, this.scale.height);
    }
    // M-3：静态 import（动态 import 每帧一次 microtask 且 alpha 恒迟一帧）
    const phase = useUiStore.getState().gameClock?.phase ?? 'day';
    const alpha = { day: 0, dawn: 0.12, dusk: 0.2, night: 0.38 }[phase];
    // 批次 D7：天气压暗叠乘（雨比阴更暗——服务端 ambient_light 同源档位）
    const weatherDark = { clear: 0, overcast: 0.08, rain: 0.16 }[this.mirror.weather.visual] ?? 0;
    overlay.setFillStyle(0x0a1030, Math.min(1, alpha + weatherDark));
  }

  /** 批次 D7：雨层（rain 时 80 条短雨丝循环下落；其他天气清空层） */
  private syncRain(delta: number): void {
    const layer = this.rainLayer;
    if (layer === null) return;
    if (this.mirror.weather.visual !== 'rain') {
      if (this.rainDrops.length > 0) {
        this.rainDrops = [];
        layer.clear();
      }
      return;
    }
    const w = this.scale.width;
    const h = this.scale.height;
    const TARGET = 80;
    while (this.rainDrops.length < TARGET) {
      this.rainDrops.push({ x: Math.random() * w, y: Math.random() * h, speed: 220 + Math.random() * 160 });
    }
    layer.clear();
    layer.lineStyle(1, 0x9fb8d8, 0.45);
    for (const drop of this.rainDrops) {
      drop.y += (drop.speed * delta) / 1000;
      drop.x -= (drop.speed * delta) / 3000;
      if (drop.y > h) {
        drop.y = -8;
        drop.x = Math.random() * w;
      }
      layer.beginPath();
      layer.moveTo(drop.x, drop.y);
      layer.lineTo(drop.x - 1.5, drop.y + 7);
      layer.strokePath();
    }
  }
}
