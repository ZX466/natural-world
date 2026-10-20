/**
 * client/src/game/scenes/WorldScene.ts — 主场景（m0-client.md §4.2）。
 *
 * 瓦片地图 + 池化精灵 + 位置插值 + 点击寻路（路径由 sim 算，前端只发目标格）
 * + 昼夜色罩（读 uiStore 的 phase）。Phaser 侧不 import React 组件。
 */
import Phaser from 'phaser';
import { createFaunaTextures } from '../render/fauna';
import type { WorldMirror } from '../world-mirror';
import {
  facingRow,
  walkFrame,
  villagerFrame,
  advanceAnimClock,
  inferFacing,
  VILLAGER_SHEET,
  GOD_SHEET,
  GOD_SPRITE_KEYS,
  godVillagerFrame,
  type Facing,
} from '../render/actors';
import { useUiStore } from '../../store/uiStore';

const PIXEL_SCALE = 3; // 批次 D8：2x→3x（48×48 镇铺满视口，人物可辨）
const TILE = 16;
// 批次 D1：插值窗口 = 行走节拍（sim 侧 15 tick/格 @1x = 250ms/格）。
// 服务端每 delta 帧给出新格坐标，客户端在 250ms 内平滑走完一格——
// 1x 手感对齐；16x 快进时 sim 节奏加快，帧到得更密，窗口缩短自然适配。
const INTERP_MS = 250;
// 2026-10-12 D6-D8 换图：GOD 桃花源缩半图集（build_god_town.py 产物，
// 2240×1600 = 140 列 @16px）。gid 1-based，id%140/id/140 换算在 renderTileset。
const TILESET_KEY = 'god-town-16';
/** GOD 图集列数（2240/16——gid→坐标换算与 png 实宽绑定，换素材必同改） */
const TILESET_COLS = 140;
const GROUND_KEY = 'ground-composite'; // 预拼地面 CanvasTexture 键

interface ActorView {
  sprite: Phaser.GameObjects.Sprite;
  /** 快照对快照插值基准（D20 漂移修）：上一快照的逻辑格 + 到达时刻——
   *  精灵在 [snapAtMs, snapAtMs+INTERP_MS) 内从 prev 线性走到最新快照格，
   *  到点即停；修前是帧对帧指数逼近（永远落后渐近=滑行漂移感）。 */
  fromX: number;
  fromY: number;
  snapAtMs: number;
  /** 上一帧逻辑格（anim/facing 推断输入，R2） */
  prevX: number;
  prevY: number;
  /** walk 动画钟（位移中累加 delta；静止归 -1=站立帧） */
  animClockMs: number;
  /** H-3：最后非零朝向（停下沿用，不转身） */
  lastFacing: 'n' | 'e' | 's' | 'w';
  /** D10：头顶戏内名（快照 actor.name；无 name 的 actor 无此对象） */
  label: Phaser.GameObjects.Text | null;
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
  /** D14 头顶气泡 Text 池（键=戏内名；mirror.bubbles 驱动增删） */
  private bubbleTexts = new Map<string, Phaser.GameObjects.Text>();
  /** E7 建筑投影层（depth 14——旧雾层随雾机制删除退役，此层保留压暗未揭示区语义已无） */
  private structureLayer: Phaser.GameObjects.Graphics | null = null;
  /** 建筑投影脏标记：structures.size 变化才重绘 */
  private lastStructureCount = -1;

  constructor(mirror: WorldMirror) {
    super({ key: 'world' });
    this.mirror = mirror;
  }

  preload(): void {
    // M7-T6：图集与角色表（Vite public 静态服务；sim 只发 id 不发素材）。
    this.load.image(TILESET_KEY, '/assets/tilesets/god-town-16.png');
    // 2026-10-12「有头没身」修复：ArMM1998 人物帧 16×32（此前 16×16 裁半身）。
    // 'protagonist' 是 chenmo.png 的中性出站键（后端 sprite 字段恒发它——
    // 快照文本禁含内部 id 词面 "chenmo"，W 系列出戏钉）。
    this.load.spritesheet('chenmo', '/assets/actors/chenmo.png', {
      frameWidth: 16,
      frameHeight: 32,
    });
    this.load.spritesheet('protagonist', '/assets/actors/chenmo.png', {
      frameWidth: 16,
      frameHeight: 32,
    });
    this.load.spritesheet('villager', '/assets/actors/villager.png', {
      frameWidth: 16,
      frameHeight: 32,
    });
    // 2026-10-12 D1-D5 接入：GOD 古风外观池 17 张（后端 sprite 字段确定性
    // 分派；texture key 与后端 slug 同名——sprite_for_entity 单一真相源）。
    // 几何 48×128 = 3 列 × 4 行 @16×32（行序 下/上/右/左，与 facingRow 对齐）。
    for (const key of GOD_SPRITE_KEYS) {
      this.load.spritesheet(key, `/assets/sprites/${key}.png`, {
        frameWidth: 16,
        frameHeight: 32,
      });
    }
  }

  create(): void {
    createFaunaTextures(this);
    this.mapLayer = this.add.graphics();
    this.nightOverlay = this.add
      .rectangle(0, 0, this.scale.width, this.scale.height, 0x0a1030, 0)
      .setOrigin(0)
      .setScrollFactor(0)
      .setDepth(100);
    // 批次 D7：雨层（短雨丝 Graphics；雨落动画在 update 里逐帧推进）
    this.rainLayer = this.add.graphics().setScrollFactor(0).setDepth(99);
    this.goalMarker = this.add.circle(0, 0, 3, 0xffd75e).setVisible(false).setDepth(50);
    // E7 建筑投影层：完工结构占格（depth 14）
    this.structureLayer = this.add.graphics().setDepth(14);

    this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      this.handlePointer(pointer);
    });

    this.scale.on('resize', () => this.redrawMap());
    this.redrawMap();
    // 地图 HTTP 加载是异步的：晚于镜像到达 → 轮询重绘（后端未起时镜像恒 null，轮询空转无害）
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
    // D6-D8 换图：GOD 图集 140 列常量（img 宽度/16 的静态事实——
    // 运行时算亦可，常量防 tileset 换装时静默错位）
    const cols = TILESET_COLS;
    const canvas = document.createElement('canvas');
    canvas.width = map.w * TILE;
    canvas.height = map.h * TILE;
    const ctx = canvas.getContext('2d');
    if (ctx === null) return;
    // 2026-10-12 贴图锐度：canvas drawImage 默认双线性模糊像素风——关掉
    // 平滑，tile 边界与纹理保持硬边（pixelArt: true 只管 Phaser 内部纹理，
    // 管不到自拼 CanvasTexture）。
    ctx.imageSmoothingEnabled = false;
    for (let y = 0; y < map.h; y += 1) {
      for (let x = 0; x < map.w; x += 1) {
        // gid 1-based（Tiled 语义，0=空格哨兵——越界兜底格）
        const id = map.ground![y * map.w + x] ?? 0;
        if (id === 0) continue;
        ctx.drawImage(
          img,
          ((id - 1) % cols) * TILE,
          Math.floor((id - 1) / cols) * TILE,
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

  update(time: number, delta: number): void {
    this.syncActorViews(delta, time);
    this.syncCamera();
    this.syncOverlay();
    this.syncRain(delta);
    this.syncBubbles(time);
    this.syncStructures();
  }

  /** E7 建筑投影：完工结构画深棕占格（size 变化才重绘——静态层零每帧成本）。 */
  private syncStructures(): void {
    const g = this.structureLayer;
    if (g === null) return;
    if (this.mirror.structures.size === this.lastStructureCount) return;
    this.lastStructureCount = this.mirror.structures.size;
    g.clear();
    for (const structure of this.mirror.structures.values()) {
      for (const [x, y] of structure.tiles) {
        g.fillStyle(0x6b4f2a, structure.phase === 'built' ? 0.92 : 0.5);
        g.fillRect(x * TILE, y * TILE, TILE - 1, TILE - 1);
      }
    }
  }

  /** D14 头顶气泡：mirror.bubbles（name→text/到期）→ Text 池增删/跟随。 */
  private syncBubbles(nowMs: number): void {
    if (this.mirror.pruneBubbles(nowMs)) {
      // 过期清理：池里有而账本没有的 → 销毁
      for (const [name, text] of this.bubbleTexts) {
        if (!this.mirror.bubbles.has(name)) {
          text.destroy();
          this.bubbleTexts.delete(name);
        }
      }
    }
    for (const [name, bubble] of this.mirror.bubbles) {
      let text = this.bubbleTexts.get(name);
      if (text === undefined) {
        text = this.add
          .text(0, 0, bubble.text, {
            fontFamily: 'sans-serif',
            fontSize: '10px',
            color: '#f0ead8',
            backgroundColor: '#000000aa',
            padding: { x: 3, y: 1 },
            resolution: 4,
            wordWrap: { width: 140 },
          })
          .setOrigin(0.5, 1)
          .setDepth(12);
        this.bubbleTexts.set(name, text);
      }
      // 跟随同名精灵（actor.name ↔ 气泡键；找不到就先挂原地）
      const actor = [...this.mirror.actors.values()].find((a) => a.name === name);
      const view = actor ? this.views.get(actor.rtoken) : undefined;
      if (view) text.setPosition(view.sprite.x, view.sprite.y - TILE - 2);
    }
  }

  private syncActorViews(delta: number, timeMs: number): void {
    if (this.mirror.resetCount !== this.lastResetSeen) {
      // 镜像被重连重置：清空精灵池重建（codex 意见 9 的表现层配合）
      for (const v of this.views.values()) {
        v.sprite.destroy();
        v.label?.destroy();
      }
      this.views.clear();
      for (const t of this.bubbleTexts.values()) t.destroy();
      this.bubbleTexts.clear();
      this.lastResetSeen = this.mirror.resetCount;
    }
    for (const [rtoken, actor] of this.mirror.actors) {
      let view = this.views.get(rtoken);
      if (view === undefined) {
        const isProtagonist = rtoken === this.mirror.protagonist;
        // M7-T7：矩形色块 → 真精灵（主角=chenmo 走环；村民=villager 走环）。
        // 2026-10-12「有头没身」修复：ArMM1998 人物帧是 **16×32**（头+身一格
        // 高两格），frameHeight:16 把每帧裁掉下半身。改 32 帧高 + 底对齐
        // origin(0.5,1)——脚踩格底（y=格底边），头顶伸出上一格（遮挡正确）。
        // 2026-10-12 D1-D5：texture key 取后端 sprite 字段（GOD 古风池，
        // chenmo 恒主角皮）；字段缺席/texture 未注册时兜底 villager。
        const textureKey =
          isProtagonist || !actor.sprite || !this.textures.exists(actor.sprite)
            ? isProtagonist
              ? 'protagonist'
              : 'villager'
            : actor.sprite;
        const sprite = this.add
          .sprite(actor.x * TILE + TILE / 2, actor.y * TILE + TILE, textureKey, 0)
          .setOrigin(0.5, 1)
          .setDepth(10);
        // 批次 D10：头顶戏内名（快照 actor.name 供数；canvas 内 Text——
        // DESIGN §4 硬约束：Phaser 画 canvas 世界，React 画 canvas 外 UI）。
        const label =
          actor.name !== undefined
            ? this.add
                .text(actor.x * TILE + TILE / 2, actor.y * TILE - 4, actor.name, {
                  fontFamily: 'sans-serif',
                  fontSize: '9px',
                  color: '#e7e0d0',
                  stroke: '#1a1f14',
                  strokeThickness: 2,
                  resolution: 4,
                })
                .setOrigin(0.5, 1)
                .setDepth(11)
            : null;
        view = {
          sprite,
          fromX: actor.x,
          fromY: actor.y,
          snapAtMs: 0,
          prevX: actor.x,
          prevY: actor.y,
          animClockMs: -1,
          lastFacing: 's' as Facing,
          label,
        };
        this.views.set(rtoken, view);
        if (isProtagonist) this.cameras.main.startFollow(sprite, true, 0.12, 0.12);
      }
      // D20 漂移修：快照对快照插值——逻辑格变化时以「此刻」为起点、
      // 从上一快照格线性走到新快照格（插值窗走完，到点即停）；
      // 修前的帧对帧指数逼近每帧只走剩余距离的 t 比例 → 永远落后
      // 目标渐近=滑行漂移感。位置未变时保持原地（不重复计时）。
      // 2026-10-12 移动手感修：插值窗按当前倍速缩放——sim 每格 15 tick
      // 是游戏时恒定，1x=250ms；16x=15.6ms，固定 250ms 窗在倍速下逐帧
      // 重置起点 → 永远追不上下一格=滑行。窗=max(帧预算, 15000/speed ms)。
      if (view.prevX !== actor.x || view.prevY !== actor.y) {
        view.fromX = view.sprite.x;
        view.fromY = view.sprite.y;
        view.snapAtMs = timeMs;
      }
      const speed = useUiStore.getState().speed;
      const interpMs = Math.max(1000 / 60, INTERP_MS / speed);
      const k = Math.min(1, (timeMs - view.snapAtMs) / interpMs);
      const targetX = actor.x * TILE + TILE / 2;
      const targetY = actor.y * TILE + TILE / 2;
      view.sprite.x = view.fromX + (targetX - view.fromX) * k;
      view.sprite.y = view.fromY + (targetY - view.fromY) * k;
      view.label?.setPosition(view.sprite.x, view.sprite.y - TILE / 2 - 3);
      // R2：位移推断 anim/facing → 帧号（D10：villager 4 列帧表启用行走环；
      // 修前恒帧 0——素材有 4×8 走环/劳作表却只画迈步中间帧，人群看着呆滞）
      const moved = view.prevX !== actor.x || view.prevY !== actor.y;
      // H-2：walk 累加/idle 归 -1（修前写反 → 循环死在第 0 帧）
      view.animClockMs = advanceAnimClock(view.animClockMs, moved, delta);
      // H-3：零位移沿用 lastFacing（停下不转身）；frameOf 只用方向行号
      if (moved) {
        view.lastFacing = inferFacing(actor.x - view.prevX, actor.y - view.prevY, view.lastFacing);
      }
      const row = facingRow(view.lastFacing);
      // D14：村民姿势——静止 + work/eat/rest/chat → 劳作姿势行（R4-7）；
      // 行走中 → 四向走环。主角仍走 chenmo 走环（素材无姿势行）。
      // 2026-10-12 D1-D5：GOD 皮走 godVillagerFrame（3 列几何）；villager
      // 兜底皮仍走 VILLAGER_SHEET（4 列）——几何按 texture 分派。
      const isGod = GOD_SPRITE_KEYS.includes(view.sprite.texture.key);
      const isFauna = actor.sprite.startsWith('fauna_');
      view.sprite.setAlpha(isFauna && actor.anim === 'rest' ? 0.5 : 1);
      view.sprite.setFrame(
        isFauna
          ? 0
          : rtoken === this.mirror.protagonist
            ? walkFrame(row, view.animClockMs)
            : isGod
              ? godVillagerFrame(
                  GOD_SHEET,
                  moved ? 'walk' : (actor.anim ?? 'idle'),
                  view.lastFacing,
                  view.animClockMs,
                )
              : villagerFrame(
                  VILLAGER_SHEET,
                  moved ? 'walk' : (actor.anim ?? 'idle'),
                  view.lastFacing,
                  view.animClockMs,
                ),
      );
      view.prevX = actor.x;
      view.prevY = actor.y;
    }
    // 移除已消失的 actor
    for (const [rtoken, view] of this.views) {
      if (!this.mirror.actors.has(rtoken)) {
        view.sprite.destroy();
        view.label?.destroy();
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
      this.rainDrops.push({
        x: Math.random() * w,
        y: Math.random() * h,
        speed: 220 + Math.random() * 160,
      });
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
