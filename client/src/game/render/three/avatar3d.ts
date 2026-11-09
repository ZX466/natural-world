/**
 * 3D 分节体素角色（**默认全员人形使用**；`?avatar3d=0` 回滚 2D；动物仍走 billboard）。
 *
 * 来源：Gemini 网页端产出的 `linhe_voxel_avatar_3d.js`（r128 预览版）。那个版本
 * 每个角色是 16 个 `Group` + 46 个 `Mesh`（本体 + 描边）**各带自己的材质和贴图**；
 * 实测 18 套角色共 828 个 mesh、162 个材质、18 张 64×64 贴图，按 51 人推算
 * **2346 次 draw call**（2D billboard 只有 51 次）。铺开前必须换形态。
 *
 * 本文件的形态：
 * - **真 `SkinnedMesh`**：16 根 `Bone` + 一份合并几何 + 一个材质 ⇒ 每角色 1 次 draw call。
 *   体素风格每个零件刚性绑一根骨（权重 1），不需要平滑蒙皮。
 * - **共享图集**：19 套预设各占 64×64 一格，拼成一张 512×256 `DataTexture`，
 *   全场共用一张。UV 在几何里按格偏移烘死。
 * - **顶点色承载纯色零件**：头发、腰带、葫芦这些原本各要一个材质的零件，改成
 *   顶点色 + 指向图集里的纯白格，于是全部并进同一个材质。
 * - **配件在构建期决定**：预设的配件是静态的（谁戴斗笠是固定的），所以隐藏的
 *   配件直接不进几何，不再需要运行时 `.visible` 开关。
 *
 * 三处与源 SDK 不同的必要改动（都是真机踩出来的）：
 * 1. 贴图用 `DataTexture`（不用 `document.createElement('canvas')`）：像素本就程序
 *    生成，写 RGBA 缓冲即可。脱离 DOM ⇒ node 单测能跑，也是共享图集的前提。
 * 2. **`flipY = true`**：`DataTexture` 默认 false、`CanvasTexture` 默认 true。UV 按
 *    canvas 约定（`1 - py/H`）算，不设会把整张图上下颠倒（真机：头长在腿上）。
 * 3. **tint 是乘数**：线缆的 `tint` 语义是乘算（`0xffffff` = 不变）。直接写
 *    `material.color` 会把黑发和所有纯色配件刷成纯白。
 *
 * 尺寸硬约束（与 2D 碰撞盒一致）：总高 1.80 格、总宽 0.90 格，root 在双脚底面
 * 中心 (0,0,0)，本地正面 +Z。
 */
import * as THREE from 'three';

export type AvatarFacing = 'n' | 'e' | 's' | 'w';
export type AvatarAnim = 'idle' | 'walk' | 'run' | 'jump';

/** 世界方向 → root.rotation.y。tile 的 +x 是东、+y 是南，与 `worldOf` 的
 *  x→x / y→z 映射一致，所以可以直接用世界朝向，不需要相机相对换算。 */
const FACING_RAD: Readonly<Record<AvatarFacing, number>> = {
  s: 0,
  e: Math.PI * 0.5,
  n: Math.PI,
  w: -Math.PI * 0.5,
};

/** 一格位移对应多少秒的走环相位。0.6s = SDK 的一个完整 walk 周期，即
 *  一格的显示位移恰好走完一轮迈步，腿不会打滑。 */
const WALK_CYCLE_SECONDS_PER_TILE = 0.6;

/** 图集：每套预设一格 64×64，8 列 × 4 行 = 32 格（用 19 格）。 */
const TILE = 64;
const ATLAS_COLS = 8;
const ATLAS_ROWS = 4;
const ATLAS_W = TILE * ATLAS_COLS;
const ATLAS_H = TILE * ATLAS_ROWS;

interface Rgba {
  readonly r: number;
  readonly g: number;
  readonly b: number;
}

function parseHex(hex: string): Rgba {
  const n = Number.parseInt(hex.slice(1), 16);
  return { r: (n >> 16) & 0xff, g: (n >> 8) & 0xff, b: n & 0xff };
}

function shade(color: Rgba, delta: number): Rgba {
  const clamp = (v: number) => Math.min(255, Math.max(0, v + delta));
  return { r: clamp(color.r), g: clamp(color.g), b: clamp(color.b) };
}

export interface AvatarAccessories {
  readonly bun: boolean;
  readonly strawHat: boolean;
  readonly basket: boolean;
  readonly sack: boolean;
  readonly robe: boolean;
  readonly herbTool: boolean;
}

export interface AvatarPreset {
  readonly id: string;
  readonly skin: string;
  readonly hair: string;
  readonly robeMain: string;
  readonly robeSub: string;
  readonly belt: string;
  readonly trim: string;
  readonly boots: string;
  readonly acc: AvatarAccessories;
}

interface Archetype {
  readonly role: string;
  readonly main: string;
  readonly sub: string;
  readonly belt: string;
  readonly bun: boolean;
  readonly hat: boolean;
  readonly sack: boolean;
  readonly robe: boolean;
  readonly basket: boolean;
}

/** 17 套古风 NPC 色板。顺序与后端 `GOD_SPRITE_POOL` 一致——那边是名字
 *  (`god_villager_taocunzhang`)，不是编号，所以下面用同一份名字建索引。 */
const NPC_ARCHETYPES: readonly Archetype[] = [
  {
    role: '01·青衫书生',
    main: '#96b37b',
    sub: '#d4c38c',
    belt: '#5a6b49',
    bun: true,
    hat: false,
    sack: false,
    robe: true,
    basket: false,
  },
  {
    role: '02·暖橙绣娘',
    main: '#ffbd7f',
    sub: '#f6e8dc',
    belt: '#b89052',
    bun: true,
    hat: false,
    sack: false,
    robe: true,
    basket: false,
  },
  {
    role: '03·土黄账房',
    main: '#b89052',
    sub: '#6d4a2f',
    belt: '#432e27',
    bun: true,
    hat: false,
    sack: false,
    robe: true,
    basket: false,
  },
  {
    role: '04·深绿老农',
    main: '#5a6b49',
    sub: '#6d4a2f',
    belt: '#b89052',
    bun: false,
    hat: true,
    sack: false,
    robe: false,
    basket: false,
  },
  {
    role: '05·米黄货郎',
    main: '#d4c38c',
    sub: '#6d4a2f',
    belt: '#ffbd7f',
    bun: false,
    hat: true,
    sack: true,
    robe: true,
    basket: false,
  },
  {
    role: '06·褐衣樵夫',
    main: '#6d4a2f',
    sub: '#b89052',
    belt: '#432e27',
    bun: false,
    hat: true,
    sack: false,
    robe: false,
    basket: false,
  },
  {
    role: '07·翠衫茶客',
    main: '#96b37b',
    sub: '#5a6b49',
    belt: '#d4c38c',
    bun: true,
    hat: false,
    sack: false,
    robe: true,
    basket: false,
  },
  {
    role: '08·橙衣歌女',
    main: '#ffbd7f',
    sub: '#b89052',
    belt: '#c43c3c',
    bun: true,
    hat: false,
    sack: false,
    robe: true,
    basket: false,
  },
  {
    role: '09·黄袍里正',
    main: '#b89052',
    sub: '#d4c38c',
    belt: '#6d4a2f',
    bun: true,
    hat: false,
    sack: false,
    robe: true,
    basket: false,
  },
  {
    role: '10·苍绿药农',
    main: '#5a6b49',
    sub: '#96b37b',
    belt: '#6d4a2f',
    bun: false,
    hat: true,
    sack: false,
    robe: true,
    basket: true,
  },
  {
    role: '11·米白画师',
    main: '#d4c38c',
    sub: '#96b37b',
    belt: '#5a6b49',
    bun: true,
    hat: false,
    sack: true,
    robe: true,
    basket: false,
  },
  {
    role: '12·深褐铁匠',
    main: '#6d4a2f',
    sub: '#432e27',
    belt: '#b89052',
    bun: false,
    hat: false,
    sack: false,
    robe: false,
    basket: false,
  },
  {
    role: '13·浅绿医女',
    main: '#96b37b',
    sub: '#f6e8dc',
    belt: '#ffbd7f',
    bun: true,
    hat: false,
    sack: false,
    robe: true,
    basket: false,
  },
  {
    role: '14·暖杏厨娘',
    main: '#ffbd7f',
    sub: '#d4c38c',
    belt: '#6d4a2f',
    bun: true,
    hat: false,
    sack: false,
    robe: true,
    basket: false,
  },
  {
    role: '15·秋黄算命',
    main: '#b89052',
    sub: '#5a6b49',
    belt: '#171717',
    bun: true,
    hat: false,
    sack: true,
    robe: true,
    basket: false,
  },
  {
    role: '16·竹绿钓叟',
    main: '#5a6b49',
    sub: '#d4c38c',
    belt: '#6d4a2f',
    bun: false,
    hat: true,
    sack: false,
    robe: true,
    basket: false,
  },
  {
    role: '17·古褐掌柜',
    main: '#6d4a2f',
    sub: '#d4c38c',
    belt: '#882e2e',
    bun: true,
    hat: false,
    sack: false,
    robe: true,
    basket: false,
  },
];

/** 后端 `GOD_SPRITE_POOL` 的同序副本（`sim/content/villagers.py:83`）。
 *  两边漂移 = 某个 NPC 拿不到自己的配色、静默回落到主角皮。 */
export const GOD_SPRITE_POOL: readonly string[] = [
  'god_villager_taocunzhang',
  'god_villager_acheng',
  'god_villager_ali',
  'god_villager_xiaolan',
  'god_villager_zhouyue',
  'god_villager_mengjiaoshou',
  'god_villager_xuning',
  'god_villager_taobo',
  'god_villager_axiu',
  'god_villager_ayuan',
  'god_villager_linkai',
  'god_villager_ada',
  'god_villager_zhibufu',
  'god_villager_liangcangguanshi',
  'god_villager_chuanlingbing',
  'god_villager_laojunhou',
  'god_villager_zuheshishen',
];

/** 图集里的格位顺序。索引即 tile 序号，构建图集和查 UV 都用它。 */
const PRESET_IDS: readonly string[] = ['chenmo', 'villager', ...GOD_SPRITE_POOL];

export const AVATAR_PRESET_IDS = PRESET_IDS;

function presetFor(id: string): AvatarPreset {
  if (id === 'chenmo')
    return {
      id: 'chenmo',
      skin: '#e8d4b2',
      hair: '#171717',
      robeMain: '#bfa787',
      robeSub: '#6a4834',
      belt: '#c43c3c',
      trim: '#65659b',
      boots: '#432e27',
      acc: { bun: true, strawHat: false, basket: true, sack: false, robe: true, herbTool: true },
    };
  if (id === 'villager')
    return {
      id: 'villager',
      skin: '#e8d4b2',
      hair: '#171717',
      robeMain: '#bfa787',
      robeSub: '#6a4834',
      belt: '#432e27',
      trim: '#6a4834',
      boots: '#432e27',
      acc: {
        bun: false,
        strawHat: false,
        basket: false,
        sack: false,
        robe: false,
        herbTool: false,
      },
    };
  const index = GOD_SPRITE_POOL.indexOf(id);
  const item = index >= 0 ? NPC_ARCHETYPES[index] : undefined;
  if (!item) return presetFor('chenmo');
  return {
    id,
    skin: '#f6e8dc',
    hair: '#171717',
    robeMain: item.main,
    robeSub: item.sub,
    belt: item.belt,
    trim: item.sub,
    boots: '#6d4a2f',
    acc: {
      bun: item.bun,
      strawHat: item.hat,
      basket: item.basket,
      sack: item.sack,
      robe: item.robe,
      herbTool: false,
    },
  };
}

// ── 图集里的纯色格 ────────────────────────────────────────────────
// 原本各占一个材质的零件改用顶点色，UV 统一指向这一格纯白。
// 位置在 64×64 格内、臂/腿贴图区（32..48 × 0..32）之右，未被占用。
const WHITE_SWATCH = { x: 48, y: 0, w: 16, h: 16 } as const;

/** 64×64 单格像素。分区与 SDK 一致：
 *  (0,0,32,16) 头脸 / (0,16,32,16) 躯干 / (32,0,32,16) 手臂 /
 *  (32,16,32,16) 腿靴 / (0,32,64,32) 配件 / (48,0,16,16) 纯白格。 */
function paintTile(preset: AvatarPreset): Uint8Array {
  const size = TILE;
  const data = new Uint8Array(size * size * 4);
  const fill = (x: number, y: number, w: number, h: number, color: Rgba) => {
    for (let py = Math.max(0, y); py < Math.min(size, y + h); py++)
      for (let px = Math.max(0, x); px < Math.min(size, x + w); px++) {
        const i = (py * size + px) * 4;
        data[i] = color.r;
        data[i + 1] = color.g;
        data[i + 2] = color.b;
        data[i + 3] = 255;
      }
  };

  const skin = parseHex(preset.skin);
  const hair = parseHex(preset.hair);
  const robeMain = parseHex(preset.robeMain);
  const robeSub = parseHex(preset.robeSub);
  const belt = parseHex(preset.belt);
  const trim = parseHex(preset.trim);
  const boots = parseHex(preset.boots);
  const black = parseHex('#171717');
  const white = parseHex('#ffffff');
  const cloth = parseHex('#f6e8dc');

  fill(0, 0, 64, 64, robeMain);

  // 1. 头与五官
  fill(0, 0, 32, 16, skin);
  fill(0, 0, 32, 5, hair);
  fill(16, 5, 16, 11, hair);
  fill(0, 5, 2, 7, hair);
  fill(14, 5, 2, 7, hair);
  fill(4, 8, 2, 3, black);
  fill(10, 8, 2, 3, black);
  fill(5, 8, 1, 1, white);
  fill(11, 8, 1, 1, white);
  fill(7, 12, 2, 1, shade(skin, -22));

  // 2. 躯干交领与束腰
  fill(0, 16, 32, 16, robeMain);
  const weave = shade(robeMain, -14);
  for (let y = 17; y < 31; y += 2) for (let x = 1; x < 31; x += 3) fill(x, y, 1, 1, weave);
  fill(4, 16, 2, 6, trim);
  fill(10, 16, 2, 6, trim);
  fill(6, 20, 4, 3, trim);
  fill(6, 16, 4, 4, cloth);
  fill(0, 26, 32, 3, belt);
  if (preset.id === 'chenmo') fill(11, 26, 3, 5, parseHex('#882e2e'));

  // 3. 手臂与护腕
  fill(32, 0, 32, 10, robeMain);
  fill(32, 8, 32, 3, trim);
  fill(32, 11, 32, 5, skin);

  // 4. 腿与靴
  fill(32, 16, 32, 9, robeSub);
  fill(32, 25, 32, 7, boots);

  // 5. 配件区
  fill(0, 32, 32, 32, parseHex('#b89052'));
  const weaveDark = parseHex('#6d4a2f');
  for (let y = 32; y < 64; y += 2)
    for (let x = y % 4 === 0 ? 0 : 1; x < 32; x += 2) fill(x, y, 1, 1, weaveDark);
  fill(32, 32, 16, 16, parseHex('#5a6b49'));
  fill(34, 34, 5, 5, parseHex('#96b37b'));
  fill(48, 32, 16, 16, parseHex('#c43c3c'));

  // 6. 纯白格（顶点色零件取样用）
  fill(WHITE_SWATCH.x, WHITE_SWATCH.y, WHITE_SWATCH.w, WHITE_SWATCH.h, white);

  return data;
}

export interface AvatarAtlas {
  readonly texture: THREE.DataTexture;
  /** 某预设的格位序号；未知 id 落到主角格。 */
  tileOf(id: string): number;
  dispose(): void;
}

/** 19 套预设拼成一张 512×256 图集，全场共用。 */
export function createAvatarAtlas(): AvatarAtlas {
  const data = new Uint8Array(ATLAS_W * ATLAS_H * 4);
  PRESET_IDS.forEach((id, index) => {
    const tile = paintTile(presetFor(id));
    const col = index % ATLAS_COLS;
    const row = Math.floor(index / ATLAS_COLS);
    for (let y = 0; y < TILE; y++) {
      const src = y * TILE * 4;
      const dst = ((row * TILE + y) * ATLAS_W + col * TILE) * 4;
      data.set(tile.subarray(src, src + TILE * 4), dst);
    }
  });
  const texture = new THREE.DataTexture(data, ATLAS_W, ATLAS_H);
  // DataTexture 默认 flipY=false；下面的 UV 按 canvas 约定算（v 轴翻转），必须对齐。
  texture.flipY = true;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return {
    texture,
    tileOf(id) {
      const index = PRESET_IDS.indexOf(id);
      return index < 0 ? 0 : index;
    },
    dispose() {
      texture.dispose();
    },
  };
}

/** 图集内归一化 UV：像素坐标 → [u0,v0,u1,v1]，v 轴按 canvas 约定翻转。 */
function atlasRegion(
  tile: number,
  px0: number,
  py0: number,
  px1: number,
  py1: number,
): readonly [number, number, number, number] {
  const col = tile % ATLAS_COLS;
  const row = Math.floor(tile / ATLAS_COLS);
  const x0 = col * TILE + px0;
  const y0 = row * TILE + py0;
  const x1 = col * TILE + px1;
  const y1 = row * TILE + py1;
  return [x0 / ATLAS_W, 1 - y1 / ATLAS_H, x1 / ATLAS_W, 1 - y0 / ATLAS_H];
}

// ── 骨架 ──────────────────────────────────────────────────────────
/** 骨骼索引 = 下面数组的下标，`skinIndex` 直接存它。 */
const BONE_NAMES = [
  'hips',
  'spine',
  'head',
  'hairAcc',
  'backProp',
  'robeFront',
  'robeBack',
  'armUpperL',
  'armLowerL',
  'armUpperR',
  'armLowerR',
  'handSlotR',
  'legUpperL',
  'legLowerL',
  'legUpperR',
  'legLowerR',
] as const;
type BoneName = (typeof BONE_NAMES)[number];

interface BoneSpec {
  readonly name: BoneName;
  readonly parent: BoneName | null;
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

/** 局部枢轴坐标（相对父骨）。数值来自 SDK 的 2.8 头身规格表。 */
const BONE_SPECS: readonly BoneSpec[] = [
  { name: 'hips', parent: null, x: 0, y: 0.58, z: 0 },
  { name: 'spine', parent: 'hips', x: 0, y: 0.13, z: 0 },
  { name: 'head', parent: 'spine', x: 0, y: 0.45, z: 0 },
  { name: 'hairAcc', parent: 'head', x: 0, y: 0.64, z: 0 },
  { name: 'backProp', parent: 'spine', x: 0, y: 0.28, z: -0.14 },
  { name: 'robeFront', parent: 'hips', x: 0, y: 0.02, z: 0.135 },
  { name: 'robeBack', parent: 'hips', x: 0, y: 0.02, z: -0.135 },
  { name: 'armUpperL', parent: 'spine', x: 0.35, y: 0.39, z: 0 },
  { name: 'armLowerL', parent: 'armUpperL', x: 0, y: -0.29, z: 0 },
  { name: 'armUpperR', parent: 'spine', x: -0.35, y: 0.39, z: 0 },
  { name: 'armLowerR', parent: 'armUpperR', x: 0, y: -0.29, z: 0 },
  { name: 'handSlotR', parent: 'armLowerR', x: 0, y: -0.24, z: 0.06 },
  { name: 'legUpperL', parent: 'hips', x: 0.13, y: 0, z: 0 },
  { name: 'legLowerL', parent: 'legUpperL', x: 0, y: -0.29, z: 0 },
  { name: 'legUpperR', parent: 'hips', x: -0.13, y: 0, z: 0 },
  { name: 'legLowerR', parent: 'legUpperR', x: 0, y: -0.29, z: 0 },
];

type Region = readonly [number, number, number, number];

/** 一个刚性零件：挂在某根骨上的一块长方体。 */
interface PartSpec {
  readonly bone: BoneName;
  readonly w: number;
  readonly h: number;
  readonly d: number;
  /** 相对骨骼枢轴的高度偏移（BoxGeometry 居中，所以通常传 -h/2）。 */
  readonly pivotY: number;
  readonly dx?: number;
  readonly dy?: number;
  readonly dz?: number;
  /** 六面共用的图集像素区域；缺省表示用顶点色。 */
  readonly uv?: Region;
  /** 逐面区域，顺序 +x,-x,+y,-y,+z,-z；优先于 `uv`。
   *  头与躯干必须逐面，否则五官会印到四个侧面上。 */
  readonly uvFaces?: readonly Region[];
  /** 顶点色（纯色零件）。 */
  readonly color?: string;
}

/** 纯白顶点色：贴图零件乘 1，不改变取样结果。 */
const WHITE = new THREE.Color(1, 1, 1);

function buildParts(preset: AvatarPreset): PartSpec[] {
  const parts: PartSpec[] = [];
  const acc = preset.acc;

  parts.push({ bone: 'hips', w: 0.5, h: 0.19, d: 0.26, pivotY: 0.095, uv: [16, 16, 32, 32] });
  parts.push({
    bone: 'spine',
    w: 0.5,
    h: 0.39,
    d: 0.26,
    pivotY: 0.195,
    uvFaces: [
      [16, 16, 24, 32],
      [16, 16, 24, 32],
      [16, 16, 28, 22],
      [16, 26, 28, 32],
      [0, 16, 16, 32],
      [16, 16, 32, 32],
    ],
  });
  parts.push({
    bone: 'head',
    w: 0.64,
    h: 0.64,
    d: 0.64,
    pivotY: 0.32,
    uvFaces: [
      [0, 0, 4, 16],
      [12, 0, 16, 16],
      [16, 0, 32, 16],
      [2, 12, 14, 16],
      [0, 0, 16, 16],
      [16, 0, 32, 16],
    ],
  });

  if (acc.bun && !acc.strawHat) {
    parts.push({ bone: 'hairAcc', w: 0.26, h: 0.16, d: 0.26, pivotY: 0.08, uv: [16, 0, 32, 16] });
    parts.push({ bone: 'hairAcc', w: 0.28, h: 0.05, d: 0.28, pivotY: 0.025, color: preset.belt });
  }
  if (acc.strawHat) {
    parts.push({ bone: 'hairAcc', w: 0.88, h: 0.05, d: 0.88, pivotY: -0.02, uv: [0, 32, 32, 64] });
    parts.push({ bone: 'hairAcc', w: 0.52, h: 0.14, d: 0.52, pivotY: 0.07, uv: [0, 32, 32, 64] });
  }

  if (acc.basket) {
    parts.push({
      bone: 'backProp',
      w: 0.36,
      h: 0.42,
      d: 0.24,
      pivotY: 0,
      dz: -0.12,
      uv: [0, 32, 32, 64],
    });
    parts.push({
      bone: 'backProp',
      w: 0.28,
      h: 0.12,
      d: 0.16,
      pivotY: 0.24,
      dz: -0.12,
      color: '#5a6b49',
    });
    parts.push({
      bone: 'backProp',
      w: 0.11,
      h: 0.18,
      d: 0.11,
      pivotY: 0,
      dx: -0.2,
      dy: 0.02,
      dz: -0.12,
      color: '#c43c3c',
    });
  }
  if (acc.sack && !acc.basket) {
    parts.push({
      bone: 'backProp',
      w: 0.4,
      h: 0.38,
      d: 0.22,
      pivotY: 0,
      dy: 0.02,
      dz: -0.11,
      color: '#d4c38c',
    });
  }

  if (acc.robe) {
    parts.push({
      bone: 'robeFront',
      w: 0.51,
      h: 0.32,
      d: 0.03,
      pivotY: -0.16,
      uv: [0, 16, 16, 32],
    });
    parts.push({
      bone: 'robeBack',
      w: 0.51,
      h: 0.32,
      d: 0.03,
      pivotY: -0.16,
      uv: [16, 16, 32, 32],
    });
  }

  for (const side of ['L', 'R'] as const) {
    parts.push({
      bone: `armUpper${side}`,
      w: 0.2,
      h: 0.29,
      d: 0.2,
      pivotY: -0.145,
      uv: [32, 0, 48, 10],
    });
    parts.push({
      bone: `armLower${side}`,
      w: 0.19,
      h: 0.29,
      d: 0.19,
      pivotY: -0.145,
      uv: [32, 6, 48, 16],
    });
    parts.push({
      bone: `legUpper${side}`,
      w: 0.23,
      h: 0.29,
      d: 0.23,
      pivotY: -0.145,
      uv: [32, 16, 48, 25],
    });
    parts.push({
      bone: `legLower${side}`,
      w: 0.22,
      h: 0.29,
      d: 0.22,
      pivotY: -0.145,
      uv: [32, 22, 48, 32],
    });
  }

  if (acc.herbTool) {
    parts.push({
      bone: 'handSlotR',
      w: 0.04,
      h: 0.04,
      d: 0.52,
      pivotY: 0,
      dz: 0.16,
      color: '#6d4a2f',
    });
    parts.push({
      bone: 'handSlotR',
      w: 0.04,
      h: 0.18,
      d: 0.06,
      pivotY: -0.07,
      dz: 0.4,
      color: '#94a3b8',
    });
  }
  return parts;
}

/** 合并几何的累积缓冲。 */
interface MeshBuffers {
  position: number[];
  normal: number[];
  uv: number[];
  color: number[];
  skinIndex: number[];
  skinWeight: number[];
  index: number[];
}

/** 把一块长方体烘成合并几何的一段：位置/法线/UV/顶点色/蒙皮索引权重/索引。 */
function appendBox(
  target: MeshBuffers,
  part: PartSpec,
  boneMatrix: THREE.Matrix4,
  tile: number,
): void {
  const geometry = new THREE.BoxGeometry(part.w, part.h, part.d);
  geometry.translate(part.dx ?? 0, part.pivotY + (part.dy ?? 0), part.dz ?? 0);
  // 顶点烘到绑定姿态的世界位置；蒙皮时 boneMatrixWorld × boneInverse 抵消回来。
  geometry.applyMatrix4(boneMatrix);

  const position = geometry.getAttribute('position');
  const normal = geometry.getAttribute('normal');
  const uv = geometry.getAttribute('uv');
  const base = target.position.length / 3;
  const boneIndex = BONE_NAMES.indexOf(part.bone);
  // 顶点色零件取样纯白格：白 × 顶点色 = 顶点色。纯白格每格都在同一位置，
  // 所以这里按「该 tile 内的纯白格」算，保证取样落在自己那格里。
  const whiteRegion = atlasRegion(
    tile,
    WHITE_SWATCH.x,
    WHITE_SWATCH.y,
    WHITE_SWATCH.x + 8,
    WHITE_SWATCH.y + 8,
  );
  const regions = part.uvFaces?.map((r) => atlasRegion(tile, ...r));
  const shared = part.uv ? atlasRegion(tile, ...part.uv) : undefined;
  const color = part.color ? new THREE.Color(part.color) : WHITE;
  // BoxGeometry 每个面 4 个顶点，面序 +x,-x,+y,-y,+z,-z。
  const perFace = position.count / 6;

  for (let i = 0; i < position.count; i++) {
    target.position.push(position.getX(i), position.getY(i), position.getZ(i));
    target.normal.push(normal.getX(i), normal.getY(i), normal.getZ(i));
    const face = Math.floor(i / perFace);
    const r = regions?.[face] ?? shared ?? whiteRegion;
    // 把该面的 0..1 UV 压到目标像素格上。
    target.uv.push(r[0] + uv!.getX(i) * (r[2] - r[0]), r[1] + uv!.getY(i) * (r[3] - r[1]));
    target.color.push(color.r, color.g, color.b);
    target.skinIndex.push(boneIndex, 0, 0, 0);
    target.skinWeight.push(1, 0, 0, 0);
  }
  const indices = geometry.getIndex()!;
  for (let i = 0; i < indices.count; i++) target.index.push(base + indices.getX(i));
  geometry.dispose();
}

export interface Avatar3D {
  readonly root: THREE.Group;
  readonly mesh: THREE.SkinnedMesh;
  setPosition(x: number, y: number, z: number): void;
  setFacing(facing: AvatarFacing): void;
  setAnim(anim: AvatarAnim): void;
  /** 走环相位（秒）。由调用方按**实际显示位移**推进，见模块头注释。 */
  setPhase(seconds: number): void;
  /** 跳跃进度 0..1；null 表示不在空中。 */
  setJumpProgress(progress: number | null): void;
  setTint(hex: number): void;
  update(deltaSeconds: number): void;
  dispose(): void;
}

const DEG = Math.PI / 180;

export function createAvatar(presetOrId: string | AvatarPreset, atlas: AvatarAtlas): Avatar3D {
  const preset = typeof presetOrId === 'string' ? presetFor(presetOrId) : presetOrId;
  const tile = atlas.tileOf(preset.id);

  // 1. 建骨架，先算绑定姿态的世界矩阵
  const bones = new Map<BoneName, THREE.Bone>();
  for (const spec of BONE_SPECS) {
    const bone = new THREE.Bone();
    bone.name = spec.name;
    bone.position.set(spec.x, spec.y, spec.z);
    bones.set(spec.name, bone);
  }
  for (const spec of BONE_SPECS)
    if (spec.parent) bones.get(spec.parent)!.add(bones.get(spec.name)!);
  const rootBone = bones.get('hips')!;
  rootBone.updateMatrixWorld(true);

  // 2. 合并几何
  const buffers: MeshBuffers = {
    position: [],
    normal: [],
    uv: [],
    color: [],
    skinIndex: [],
    skinWeight: [],
    index: [],
  };
  const parts = buildParts(preset);
  for (const part of parts) appendBox(buffers, part, bones.get(part.bone)!.matrixWorld, tile);

  const buildGeometry = (buffers: MeshBuffers) => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(buffers.position, 3));
    geometry.setAttribute('normal', new THREE.Float32BufferAttribute(buffers.normal, 3));
    geometry.setAttribute('uv', new THREE.Float32BufferAttribute(buffers.uv, 2));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(buffers.color, 3));
    geometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(buffers.skinIndex, 4));
    geometry.setAttribute('skinWeight', new THREE.Float32BufferAttribute(buffers.skinWeight, 4));
    geometry.setIndex(buffers.index);
    return geometry;
  };
  const geometry = buildGeometry(buffers);

  const material = new THREE.MeshLambertMaterial({ map: atlas.texture, vertexColors: true });
  const mesh = new THREE.SkinnedMesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.castShadow = false;
  mesh.receiveShadow = false;
  mesh.add(rootBone);
  const skeleton = new THREE.Skeleton(BONE_NAMES.map((name) => bones.get(name)!));
  mesh.bind(skeleton);

  // 3. 3D 描边**暂不提供**（2026-11-08 试水实测结论）。
  //    2D 路径的「穿墙剪影」用同位置 Sprite + `GreaterDepth` 实现：那张 sprite
  //    是平面，深度处处相等，所以只在真正被挡住时才显色。3D 网格自身有前后
  //    深度差——躯干背面比正面深，同样的比较会让被身体挡住的胳膊透出来，真机
  //    上就是整个人套了个黄罩子；改成外扩则会在零件交界处露出一圈黄边。
  //    要做对需要模板缓冲 + 严格的两遍渲染顺序，属于独立一轮的活。
  //    这里宁可没有，也不留一个错的视觉。
  const root = new THREE.Group();
  root.name = 'avatar-root';
  root.add(mesh);

  // ── 姿态 ──────────────────────────────────────────────────────
  let targetRotY = 0;
  let anim: AvatarAnim = 'idle';
  let phase = 0;
  let jumpProgress: number | null = null;

  const evaluate = () => {
    const b = (name: BoneName) => bones.get(name)!;
    const set = (name: BoneName, x = 0, y = 0, z = 0) => b(name).rotation.set(x, y, z);

    b('hips').position.set(0, 0.58, 0);
    for (const name of BONE_NAMES) if (name !== 'hips') set(name);

    if (anim === 'idle') {
      const breathe = Math.sin((phase / 1.6) * Math.PI * 2);
      b('hips').position.y = 0.58 + breathe * 0.015;
      set('spine', (2 + breathe * 1.5) * DEG);
      set('head', 0, Math.sin(phase * 1.1) * 5 * DEG);
      set('armUpperL', 0, 0, (3 + breathe * 1.5) * DEG);
      set('armUpperR', 0, 0, -(3 + breathe * 1.5) * DEG);
      set('armLowerL', -10 * DEG);
      set('armLowerR', -10 * DEG);
      return;
    }
    if (anim === 'walk') {
      const s = Math.sin((phase / 0.6) * Math.PI * 2);
      const c = Math.cos((phase / 0.6) * Math.PI * 2);
      b('hips').position.y = 0.58 + Math.abs(c) * 0.03 - 0.015;
      set('spine', 3 * DEG, -s * 4 * DEG);
      set('head', -2 * DEG, s * 3 * DEG);
      set('legUpperL', -s * 28 * DEG);
      set('legUpperR', s * 28 * DEG);
      set('legLowerL', (Math.max(0, -c) * 20 + 5) * DEG);
      set('legLowerR', (Math.max(0, c) * 20 + 5) * DEG);
      set('armUpperL', s * 25 * DEG);
      set('armUpperR', -s * 25 * DEG);
      set('armLowerL', -15 * DEG);
      set('armLowerR', -15 * DEG);
      set('robeFront', -Math.max(0.05, Math.abs(s) * 0.32));
      set('robeBack', Math.max(0.05, Math.abs(s) * 0.25));
      return;
    }
    if (anim === 'run') {
      const s = Math.sin((phase / 0.4) * Math.PI * 2);
      const c = Math.cos((phase / 0.4) * Math.PI * 2);
      b('hips').position.y = 0.54 + Math.sin((phase / 0.4) * Math.PI * 4 - Math.PI * 0.3) * 0.065;
      set('spine', 18 * DEG, -s * 12 * DEG);
      set('head', -12 * DEG, s * 8 * DEG);
      set('legUpperL', (-s * 52 + 3) * DEG);
      set('legUpperR', (s * 52 + 3) * DEG);
      set('legLowerL', (Math.max(0, -s * 0.5 - c * 0.6) * 75 + 10) * DEG);
      set('legLowerR', (Math.max(0, s * 0.5 + c * 0.6) * 75 + 10) * DEG);
      set('armUpperL', s * 62 * DEG, 0, 8 * DEG);
      set('armUpperR', -s * 62 * DEG, 0, -8 * DEG);
      set('armLowerL', -(72 + Math.max(0, -s) * 15) * DEG);
      set('armLowerR', -(72 + Math.max(0, s) * 15) * DEG);
      set('robeFront', -(28 + Math.abs(s) * 25) * DEG);
      set('robeBack', (35 + Math.abs(c) * 20) * DEG);
      return;
    }
    // jump：把 0..1 的进度映射到 SDK 的 0.16/0.71/0.91 三段窗口。
    const t = Math.min(1, Math.max(0, jumpProgress ?? 0)) * 0.91;
    if (t < 0.16) {
      const p = t / 0.16;
      const squash = p < 0.65 ? p / 0.65 : 1 - (p - 0.65) / 0.35;
      b('hips').position.y = 0.58 - squash * 0.16;
      set('spine', squash * 22 * DEG);
      set('legUpperL', -squash * 40 * DEG);
      set('legUpperR', -squash * 40 * DEG);
      set('legLowerL', squash * 80 * DEG);
      set('legLowerR', squash * 80 * DEG);
      set('armUpperL', squash * 45 * DEG);
      set('armUpperR', squash * 45 * DEG);
      set('armLowerL', -35 * DEG);
      set('armLowerR', -35 * DEG);
    } else if (t < 0.71) {
      const airP = (t - 0.16) / 0.55;
      b('hips').position.y = 0.58 + 4 * airP * (1 - airP) * 1.15;
      set('spine', (10 - airP * 16) * DEG);
      set('legUpperL', -45 * DEG);
      set('legLowerL', 65 * DEG);
      set('legUpperR', 20 * DEG);
      set('legLowerR', 25 * DEG);
      set('armUpperL', -60 * DEG, 0, 25 * DEG);
      set('armUpperR', -60 * DEG, 0, -25 * DEG);
      set('armLowerL', -35 * DEG);
      set('armLowerR', -35 * DEG);
      set('robeFront', -40 * DEG);
      set('robeBack', 42 * DEG);
    } else {
      const landP = Math.min(1, (t - 0.71) / 0.2);
      const dip = Math.sin(landP * Math.PI);
      b('hips').position.y = 0.58 - dip * 0.18;
      set('spine', dip * 25 * DEG);
      set('head', dip * 10 * DEG);
      set('legUpperL', -dip * 42 * DEG);
      set('legUpperR', -dip * 42 * DEG);
      set('legLowerL', dip * 84 * DEG);
      set('legLowerR', dip * 84 * DEG);
      set('armUpperL', 0, 0, dip * 20 * DEG);
      set('armUpperR', 0, 0, -dip * 20 * DEG);
      set('armLowerL', -dip * 40 * DEG);
      set('armLowerR', -dip * 40 * DEG);
    }
  };
  evaluate();

  return {
    root,
    mesh,
    setPosition(x, y, z) {
      root.position.set(x, y, z);
    },
    setFacing(facing) {
      targetRotY = FACING_RAD[facing];
    },
    setAnim(next) {
      anim = next;
    },
    setPhase(seconds) {
      phase = seconds;
    },
    setJumpProgress(progress) {
      jumpProgress = progress;
    },
    setTint(hex) {
      // 顶点色承载基色，材质色做乘数——白 = 不变，不会把黑发刷成纯白。
      material.color.setHex(hex);
    },
    update(deltaSeconds) {
      // 最短弧度平滑转向：跨 ±π 时不绕远路。
      const diff = ((targetRotY - root.rotation.y + Math.PI) % (Math.PI * 2)) - Math.PI;
      const shortest = diff < -Math.PI ? diff + Math.PI * 2 : diff;
      root.rotation.y += shortest * Math.min(1, deltaSeconds * 15);
      evaluate();
    },
    dispose() {
      root.remove(mesh);
      geometry.dispose();
      material.dispose();
      skeleton.dispose();
    },
  };
}

/** 只作用于受光材质的一组灯。地形用 MeshBasicMaterial，完全不受影响。 */
export function createAvatarLighting(scene: THREE.Scene): () => void {
  // Lambert 的 BRDF 会除以 π，用 2~3 的强度把体素块的明暗拉回肉眼可读的范围。
  const hemisphere = new THREE.HemisphereLight(0xffffff, 0x667788, 2.2);
  const sun = new THREE.DirectionalLight(0xffffff, 2.0);
  sun.position.set(-0.6, 1, -0.8);
  scene.add(hemisphere, sun);
  return () => {
    scene.remove(hemisphere, sun);
    hemisphere.dispose();
    sun.dispose();
  };
}

/** 相位推进：`animClock` 是 `advanceMotion` 按**实际显示距离**累计的毫秒数
 *  （每格 250ms），换算成秒再乘每格周期，保证腿速与位移同源。 */
export function phaseFromAnimClock(animClockMs: number): number {
  return (animClockMs / 250) * WALK_CYCLE_SECONDS_PER_TILE;
}
