/**
 * client/src/game/scenes/WorldScene.ts — 主场景（m0-client.md §4.2）。
 *
 * 瓦片地图 + 池化精灵 + 位置插值 + 点击寻路（路径由 sim 算，前端只发目标格）
 * + 昼夜色罩（读 uiStore 的 phase）。Phaser 侧不 import React 组件。
 */
import Phaser from 'phaser';
import { createFaunaTextures } from '../render/fauna';
import {
  ISO,
  createHeightLookup,
  depthKey,
  effectiveHeight,
  isoProject,
  isoUnproject,
  screenBounds,
} from '../render/iso';
import { IsoTerrain } from '../render/iso-terrain';
import { pickVoxel } from '../render/voxel-picking';
import { BLOCK_ATLAS_KEY, BLOCK_ATLAS_META_KEY } from '../render/block-atlas';
import { placeBubble, selectBubbleNames } from '../render/bubbles';
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
import {
  assignStackOffsets,
  actorDepth,
  bubbleDepth,
  labelDepth,
  labelY,
  manhattan,
  shouldShowNameLabel,
  aboveSurface,
  ISO_DEPTH,
  ISO_LABEL_GAP_PX,
  ISO_BUBBLE_GAP_PX,
  RAIN_LAYER_DEPTH,
  NIGHT_OVERLAY_DEPTH,
  rendererFromSearch,
} from '../render/presentation';
import { useUiStore } from '../../store/uiStore';

const PIXEL_SCALE = 3.5; // A 档：3x→3.5x（人物更可辨，缓解小片区人群拥挤观感）
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
type Renderer = 'flat' | 'iso';

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
  /** A 档：脚下接触阴影（重叠时也能看出各自站位） */
  shadow: Phaser.GameObjects.Ellipse | null;
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
  /** 建筑内容签名：同数量的相位/格位变化也须重绘。 */
  private lastStructureSignature = '';
  private renderMode: Renderer;
  private isoTerrain: IsoTerrain | null = null;
  private heightAt = createHeightLookup(null);
  private isoCameraTarget = { x: 0, y: 0 };
  private isoFollowToken: string | null = null;
  private voxelPress: {
    id: number;
    at: number;
    target: { x: number; y: number } | null;
    digging: boolean;
    version: number;
  } | null = null;
  private voxelHoldTimer: ReturnType<typeof setTimeout> | null = null;
  private voxelProgress: Phaser.GameObjects.Graphics | null = null;
  private lastVoxelVersion = -1;
  private lastVoxelSignature = '';
  private lastVoxelMap: WorldMirror['map'] = null;

  constructor(
    mirror: WorldMirror,
    renderer: Renderer = rendererFromSearch(globalThis.location?.search ?? ''),
  ) {
    super({ key: 'world' });
    this.mirror = mirror;
    this.renderMode = renderer;
  }

  preload(): void {
    // M7-T6：图集与角色表（Vite public 静态服务；sim 只发 id 不发素材）。
    this.load.image(TILESET_KEY, '/assets/tilesets/god-town-16.png');
    this.load.json('linhe-height', '/assets/tilesets/linhe-height.json');
    this.load.image(BLOCK_ATLAS_KEY, '/assets/tilesets/linhe-block-atlas.png');
    this.load.json(BLOCK_ATLAS_META_KEY, '/assets/tilesets/linhe-block-atlas.json');
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
    if (this.renderMode === 'iso') {
      this.heightAt = createHeightLookup(this.cache.json.get('linhe-height'));
      this.isoTerrain = new IsoTerrain(this, this.heightAt);
      this.events.once('shutdown', () => {
        this.isoTerrain?.destroy();
        this.isoTerrain = null;
      });
    }
    createFaunaTextures(this);
    this.mapLayer = this.add.graphics().setDepth(1);
    this.voxelProgress = this.add
      .graphics()
      .setDepth(this.renderMode === 'iso' ? ISO_DEPTH.BUBBLE + 100 : 89.5);
    this.nightOverlay = this.add
      .rectangle(0, 0, this.scale.width, this.scale.height, 0x0a1030, 0)
      .setOrigin(0)
      .setScrollFactor(0)
      .setDepth(this.renderMode === 'iso' ? ISO_DEPTH.NIGHT : NIGHT_OVERLAY_DEPTH);
    // 批次 D7：雨层（短雨丝 Graphics；雨落动画在 update 里逐帧推进）
    this.rainLayer = this.add
      .graphics()
      .setScrollFactor(0)
      .setDepth(this.renderMode === 'iso' ? ISO_DEPTH.RAIN : RAIN_LAYER_DEPTH);
    // 目标点标记：压在精灵与名字之间（A 档分层带内，见 presentation.ts）
    this.goalMarker = this.add.circle(0, 0, 3, 0xffd75e).setVisible(false).setDepth(70.5);
    // E7 建筑投影层：完工结构占格（depth 14）
    if (this.renderMode === 'flat') this.structureLayer = this.add.graphics().setDepth(14);

    this.input.mouse?.disableContextMenu();
    this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) =>
      this.handlePointerDown(pointer),
    );
    this.input.on('pointerup', (pointer: Phaser.Input.Pointer) => this.handlePointerUp(pointer));
    this.input.on('pointerupoutside', () => this.cancelVoxelInput());
    this.input.on('gameout', () => this.cancelVoxelInput());
    this.events.once('shutdown', () => this.cancelVoxelInput());

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
    if (this.renderMode === 'iso') {
      this.isoTerrain?.redraw(map, this.mirror.structures, this.mirror.voxelEdits);
      return;
    }
    if (map === null) {
      // 无地图：铺 32x32 默认可通行网格
      g.fillStyle(0x3a4a3f, 1);
      g.fillRect(0, 0, 32 * TILE, 32 * TILE);
      return;
    }
    if (map.tileset !== 'grid' && map.ground && this.textures.exists(TILESET_KEY)) {
      this.renderTileset(map);
      this.drawFlatVoxels();
      return;
    }
    for (let y = 0; y < map.h; y += 1) {
      for (let x = 0; x < map.w; x += 1) {
        const walkable = map.collision[y * map.w + x] === 1;
        g.fillStyle(walkable ? 0x4a5d4e : 0x2a3038, 1);
        g.fillRect(x * TILE, y * TILE, TILE - 1, TILE - 1);
      }
    }
    this.drawFlatVoxels();
  }

  private drawFlatVoxels(): void {
    const g = this.mapLayer;
    if (g === null) return;
    for (const edit of this.mirror.voxelEdits.values()) {
      g.fillStyle(0x8f8055, 1);
      g.fillRect(edit.x * TILE, edit.y * TILE, TILE, TILE);
      if (edit.action === 'place') {
        g.fillStyle(0x6b4f2a, 1);
        g.fillRect(edit.x * TILE + TILE - 3, edit.y * TILE, 3, TILE);
      } else {
        // V4a：挖后仍是静态高度，只靠整格土色几乎认不出——加一道深色内框。
        g.fillStyle(0x3f3020, 0.55);
        g.fillRect(edit.x * TILE + 3, edit.y * TILE + 3, TILE - 6, TILE - 6);
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

  private voxelTarget(pointer: Phaser.Input.Pointer): { x: number; y: number } | null {
    const map = this.mirror.map;
    if (map === null) return null;
    if (this.renderMode === 'iso')
      return pickVoxel(pointer.worldX, pointer.worldY, map.w, map.h, (x, y) =>
        effectiveHeight(x, y, this.heightAt, this.mirror.structures, this.mirror.voxelEdits),
      );
    const x = Math.floor(pointer.worldX / TILE),
      y = Math.floor(pointer.worldY / TILE);
    return x >= 0 && y >= 0 && x < map.w && y < map.h ? { x, y } : null;
  }

  private handlePointerDown(pointer: Phaser.Input.Pointer): void {
    this.cancelVoxelInput();
    const map = this.mirror.map;
    if (map === null || this.mirror.protagonist === null) return;
    const target = this.voxelTarget(pointer);
    if (pointer.button === 2) {
      if (target && map.collision[target.y * map.w + target.x] === 1)
        this.game.events.emit('client:voxel_request', { action: 'place', ...target });
      return;
    }
    if (pointer.button !== 0) return;
    const press = {
      id: pointer.id,
      at: Date.now(),
      target,
      digging: false,
      version: this.mirror.voxelSnapshotVersion,
    };
    this.voxelPress = press;
    this.voxelHoldTimer = setTimeout(() => {
      this.voxelHoldTimer = null;
      const current = this.mirror.map;
      if (
        this.voxelPress !== press ||
        press.version !== this.mirror.voxelSnapshotVersion ||
        !target ||
        !current ||
        current.collision[target.y * current.w + target.x] !== 0
      )
        return;
      press.digging = true;
      this.game.events.emit('client:voxel_request', { action: 'dig_start', ...target });
    }, 150);
  }

  private handlePointerUp(pointer: Phaser.Input.Pointer): void {
    const press = this.voxelPress;
    if (press === null || pointer.id !== press.id) return;
    this.cancelVoxelInput();
    if (
      !press.digging &&
      press.version === this.mirror.voxelSnapshotVersion &&
      Date.now() - press.at < 150
    )
      this.handlePointer(pointer);
  }

  private cancelVoxelInput(): void {
    if (this.voxelHoldTimer !== null) clearTimeout(this.voxelHoldTimer);
    this.voxelHoldTimer = null;
    const press = this.voxelPress;
    this.voxelPress = null;
    if (press?.digging && press.target)
      this.game.events.emit('client:voxel_request', { action: 'dig_cancel', ...press.target });
  }

  private handlePointer(pointer: Phaser.Input.Pointer): void {
    if (this.mirror.protagonist === null || this.mirror.map === null) return;
    const map = this.mirror.map;
    // R6: picking intersects the ground plane; the marker then uses the shared surface.
    const { x: wx, y: wy } =
      this.renderMode === 'iso'
        ? isoUnproject(pointer.worldX, pointer.worldY, screenBounds(map.w, map.h))
        : { x: Math.floor(pointer.worldX / TILE), y: Math.floor(pointer.worldY / TILE) };
    if (wx < 0 || wy < 0 || wx >= map.w || wy >= map.h) return;
    if (map.collision[wy * map.w + wx] !== 1) return; // 目标不可通行，不请求
    const goal = this.projectSurface(wx, wy);
    this.goalMarker?.setPosition(goal.sx, goal.sy).setVisible(true);
    if (this.renderMode === 'iso') this.goalMarker?.setDepth(depthKey(wx, wy) + 1.5);
    // sim 负责寻路（世界真相在 sim）；前端发的是玩家对主角的「移动请求」——
    // move_request 协议早已落地（ws.py `_handle_move_request` → `issue_move`，
    // 含 bad_target 错误帧与不可达静默两条路径）。旧注释说「用 player_impulse
    // 占位」是 M0 时代残留，2026-10-20 核实后更正。
    this.game.events.emit('client:move_request', { x: wx, y: wy });
  }

  update(time: number, delta: number): void {
    this.syncVoxelPresentation();
    this.syncActorViews(delta, time);
    this.syncCamera();
    this.syncOverlay();
    this.syncRain(delta);
    this.syncBubbles(Date.now()); // 与 mirror.setBubble 的到期时钟一致
    this.syncStructures();
    this.isoTerrain?.advance(delta);
  }

  /** E7 建筑投影：内容变化才重绘，保留相位对应的颜色与透明度。 */
  private syncStructures(): void {
    if (this.renderMode === 'iso') {
      // Reverse merge: IsoTerrain's content signature gates its shared structure/block pool.
      this.isoTerrain?.sync(this.mirror.map, this.mirror.structures, this.mirror.voxelEdits);
      return;
    }
    const g = this.structureLayer;
    if (g === null) return;
    const signature = JSON.stringify([...this.mirror.structures]);
    if (signature === this.lastStructureSignature) return;
    this.lastStructureSignature = signature;
    g.clear();
    for (const structure of this.mirror.structures.values()) {
      for (const [x, y] of structure.tiles) {
        g.fillStyle(0x6b4f2a, structure.phase === 'built' ? 0.92 : 0.5);
        g.fillRect(x * TILE, y * TILE, TILE - 1, TILE - 1);
      }
    }
  }

  private syncVoxelPresentation(): void {
    if (this.lastVoxelVersion !== this.mirror.voxelSnapshotVersion) {
      this.cancelVoxelInput();
      this.lastVoxelVersion = this.mirror.voxelSnapshotVersion;
    }
    if (this.renderMode === 'flat') {
      const signature = JSON.stringify([...this.mirror.voxelEdits]);
      if (this.lastVoxelMap !== this.mirror.map || signature !== this.lastVoxelSignature) {
        this.redrawMap();
        this.lastVoxelMap = this.mirror.map;
        this.lastVoxelSignature = signature;
      }
    }
    const g = this.voxelProgress;
    if (g === null) return;
    g.clear();
    const dig = this.mirror.voxelDig;
    if (dig === null) return;
    const top = this.projectSurface(dig.x, dig.y);
    g.fillStyle(0x211d16, 0.9);
    g.fillRect(top.sx - 8, top.sy - 4, 16, 3);
    g.fillStyle(0xe3cc8c, 1);
    g.fillRect(top.sx - 8, top.sy - 4, 16 * dig.progress, 3);
  }

  /** D14 头顶气泡：mirror.bubbles（name→text/到期）→ Text 池增删/跟随。 */
  private syncBubbles(nowMs: number): void {
    this.mirror.pruneBubbles(nowMs);
    const iso = this.renderMode === 'iso';
    const anchors = new Map<string, { x: number; y: number; height: number }>();
    for (const actor of this.mirror.actors.values()) {
      const view = this.views.get(actor.rtoken);
      if (actor.name && view)
        anchors.set(actor.name, {
          x: view.sprite.x,
          y: view.sprite.y,
          height: view.sprite.displayHeight || 32,
        });
    }
    const candidates = new Map([...this.mirror.bubbles].filter(([name]) => anchors.has(name)));
    const protagonistName = this.mirror.actors.get(this.mirror.protagonist ?? '')?.name;
    const selected = selectBubbleNames(candidates, protagonistName);
    const retained = new Set(selected);
    for (const [name, text] of this.bubbleTexts) {
      if (!retained.has(name)) {
        text.destroy();
        this.bubbleTexts.delete(name);
      }
    }
    const placed: ReturnType<typeof placeBubble>[] = [];
    for (const name of selected) {
      const bubble = this.mirror.bubbles.get(name)!;
      let text = this.bubbleTexts.get(name);
      if (text === undefined) {
        text = this.add
          .text(0, 0, bubble.text, {
            fontFamily: 'sans-serif',
            fontSize: '13px',
            color: '#f0ead8',
            backgroundColor: '#000000aa',
            padding: { x: 3, y: 1 },
            resolution: 4,
            wordWrap: { width: 140 },
          })
          .setOrigin(0.5, 1)
          // A 档：同标签——世界坐标文字需反向缩放，否则 zoom 放大后糊满画面
          .setScale(1 / PIXEL_SCALE)
          .setDepth(12);
        this.bubbleTexts.set(name, text);
      }
      // 内容变了才重设（setText 会触发重新排版，每帧调会抖）
      if (text.text !== bubble.text) text.setText(bubble.text);
      const anchor = anchors.get(name)!;
      // H：被选中后按优先级依次避让已放置的气泡矩形（主角优先 → 不会互相压字）
      const box = placeBubble(
        {
          x: anchor.x,
          // Feet already interpolate between isoProject surface points.
          y: iso
            ? aboveSurface(anchor.y, anchor.height, ISO_BUBBLE_GAP_PX, PIXEL_SCALE)
            : anchor.y - TILE - 2,
          width: iso ? text.displayWidth : text.width,
          height: iso ? text.displayHeight : text.height,
        },
        placed,
        iso ? 4 / PIXEL_SCALE : undefined,
      );
      text.setPosition(box.x, box.y);
      // A 档：气泡随脚底深度抬升，避免被邻格更大的脚底深度精灵压住
      text.setDepth(bubbleDepth(anchor.y, this.renderMode));
      placed.push(box);
    }
  }

  private syncActorViews(delta: number, timeMs: number): void {
    const iso = this.renderMode === 'iso';
    if (this.mirror.resetCount !== this.lastResetSeen) {
      // 镜像被重连重置：清空精灵池重建（codex 意见 9 的表现层配合）
      for (const v of this.views.values()) {
        v.sprite.destroy();
        v.label?.destroy();
        v.shadow?.destroy();
      }
      this.views.clear();
      for (const t of this.bubbleTexts.values()) t.destroy();
      this.bubbleTexts.clear();
      this.lastResetSeen = this.mirror.resetCount;
    }
    // A 档：同格多人视觉错位（每帧重算；逻辑坐标不动，仅精灵偏移）
    const stackOffsets = assignStackOffsets(
      [...this.mirror.actors].map(([rtoken, a]) => ({ rtoken, x: a.x, y: a.y })),
    );
    const protagonist = this.mirror.protagonist
      ? this.mirror.actors.get(this.mirror.protagonist)
      : undefined;
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
        const top = this.projectSurface(actor.x, actor.y);
        const initialDepth = iso
          ? depthKey(actor.x, actor.y) + 1
          : actorDepth((actor.y + 1) * TILE);
        // A 档：脚下阴影先建，深度按脚底 y 略低于同格精灵
        const shadow = this.add
          .ellipse(
            top.sx,
            iso ? top.sy : actor.y * TILE + TILE - 1,
            iso ? ISO.TW / 2 : 10,
            iso ? ISO.TH / 4 : 4,
            0x000000,
            0.28,
          )
          .setDepth(initialDepth - (iso ? 0.5 : 1));
        const sprite = this.add
          .sprite(top.sx, iso ? top.sy : actor.y * TILE + TILE, textureKey, 0)
          .setOrigin(0.5, 1)
          .setDepth(initialDepth);
        // 批次 D10：头顶戏内名（快照 actor.name 供数；canvas 内 Text——
        // DESIGN §4 硬约束：Phaser 画 canvas 世界，React 画 canvas 外 UI）。
        // A 档（2026-10-20）：Text 处于世界坐标，镜头 zoom 会把字号同比放大——
        // 9px 在 3.5x 下变 ~31px 屏幕字，几人并排就把画面糊满。反向缩放
        // 1/PIXEL_SCALE 让标签保持固定屏幕尺寸。
        const label =
          actor.name !== undefined
            ? this.add
                .text(
                  top.sx,
                  iso
                    ? aboveSurface(
                        top.sy,
                        sprite.displayHeight || 32,
                        ISO_LABEL_GAP_PX,
                        PIXEL_SCALE,
                      )
                    : actor.y * TILE - 4,
                  actor.name,
                  {
                    fontFamily: 'sans-serif',
                    fontSize: '12px',
                    color: '#e7e0d0',
                    stroke: '#1a1f14',
                    strokeThickness: 2,
                    resolution: 4,
                  },
                )
                .setOrigin(0.5, 1)
                .setScale(1 / PIXEL_SCALE)
                .setDepth(labelDepth((actor.y + 1) * TILE, this.renderMode))
            : null;
        view = {
          sprite,
          fromX: iso ? top.sx : actor.x,
          fromY: iso ? top.sy : actor.y,
          snapAtMs: 0,
          prevX: actor.x,
          prevY: actor.y,
          animClockMs: -1,
          lastFacing: 's' as Facing,
          label,
          shadow,
        };
        this.views.set(rtoken, view);
        if (isProtagonist && !iso) this.cameras.main.startFollow(sprite, true, 0.12, 0.12);
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
      const stack = stackOffsets.get(rtoken) ?? { dx: 0, dy: 0 };
      const top = this.projectSurface(actor.x, actor.y);
      const targetX = top.sx + stack.dx;
      const targetY = top.sy + stack.dy;
      view.sprite.x = view.fromX + (targetX - view.fromX) * k;
      view.sprite.y = view.fromY + (targetY - view.fromY) * k;
      // A 档：深度随脚底（插值后）位置更新——靠下的人自然压住靠上的人。
      // 精灵 origin(0.5,1)，sprite.y 即脚底世界像素。
      const footDepth = iso ? depthKey(actor.x, actor.y) + 1 : actorDepth(view.sprite.y);
      view.sprite.setDepth(footDepth);
      view.shadow?.setPosition(view.sprite.x, view.sprite.y - (iso ? 0 : 1));
      view.shadow?.setDepth(footDepth - (iso ? 0.5 : 1));
      // A 档：名字挂头顶（帧高 32px，此前按半格 8px 挂 → 压在脸上）
      view.label?.setPosition(
        view.sprite.x,
        iso
          ? aboveSurface(
              view.sprite.y,
              view.sprite.displayHeight || 32,
              ISO_LABEL_GAP_PX,
              PIXEL_SCALE,
            )
          : labelY(view.sprite.y),
      );
      view.label?.setDepth(labelDepth(view.sprite.y, this.renderMode));
      // A 档：名字只在主角邻近显示（远端 50 个标签是最大噪声源）
      if (view.label) {
        const dist = protagonist ? manhattan(actor, protagonist) : 0;
        const isSelf = rtoken === this.mirror.protagonist;
        view.label.setVisible(isSelf || shouldShowNameLabel(dist));
      }
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
        view.shadow?.destroy();
        this.views.delete(rtoken);
      }
    }
  }

  private syncCamera(): void {
    const map = this.mirror.map;
    if (map === null) return;
    if (this.renderMode === 'iso') {
      const bounds = screenBounds(map.w, map.h);
      const camera = this.cameras.main;
      camera.setBounds(-64, -64, bounds.width + 128, bounds.height + 128);
      camera.setZoom(PIXEL_SCALE);
      const actor = this.mirror.actors.get(this.mirror.protagonist ?? '');
      if (actor === undefined) {
        if (this.isoFollowToken !== null) camera.stopFollow();
        this.isoFollowToken = null;
        return;
      }
      // A logical top-face target keeps same-cell presentation offsets out of the camera.
      const top = this.projectSurface(actor.x, actor.y);
      this.isoCameraTarget.x = top.sx;
      this.isoCameraTarget.y = top.sy;
      if (this.isoFollowToken !== this.mirror.protagonist) {
        camera.startFollow(this.isoCameraTarget, true, 0.12, 0.12);
        this.isoFollowToken = this.mirror.protagonist;
      }
      return;
    }
    this.cameras.main.setBounds(0, 0, map.w * TILE, map.h * TILE);
    this.cameras.main.setZoom(PIXEL_SCALE);
  }

  private projectSurface(x: number, y: number): { sx: number; sy: number } {
    if (this.renderMode === 'flat') return { sx: x * TILE + TILE / 2, sy: y * TILE + TILE / 2 };
    const map = this.mirror.map;
    const bounds = map === null ? undefined : screenBounds(map.w, map.h);
    return isoProject(
      x,
      y,
      effectiveHeight(x, y, this.heightAt, this.mirror.structures, this.mirror.voxelEdits),
      bounds,
    );
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
