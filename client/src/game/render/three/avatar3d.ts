/**
 * 3D 分节体素角色（主角试水）。
 *
 * 来源：Gemini 网页端产出的 `linhe_voxel_avatar_3d.js`（r128 预览版），本文件是
 * 移植到本项目 three 0.180 + TypeScript 的版本，做了三处必要改动：
 *
 * 1. **贴图改用 `DataTexture`**，不再 `document.createElement('canvas')`。像素
 *    图本来就是程序生成的 64×64，直接写 RGBA 缓冲即可；顺带脱离 DOM，node
 *    环境的单测能跑，也为后续多人共享图集留出入口。
 * 2. **不再自建光照假设**：地形层是 `MeshBasicMaterial`（亮度烘在顶点色里，
 *    见 `three-terrain.ts` 的 FACE_SHADE），本模块的角色用 `MeshLambertMaterial`，
 *    由 `createAvatarLighting()` 提供一组只作用于受光材质的灯。两者互不影响。
 * 3. **动画相位由外部驱动**（`setPhase`），不自己累计 delta。走环必须跟实际
 *    显示位移同源，否则 16 倍速下腿速不变、人像在冰上滑——这是
 *    `motion-buffer.ts` 已经定下的口径，3D 不得另起一套计时。
 *
 * 尺寸硬约束（与 2D 碰撞盒一致）：总高 1.80 格、总宽 0.90 格，root 在双脚
 * 底面中心 (0,0,0)，本地正面 +Z。
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

/** 64×64 RGBA 画布的最小实现：只需要 fillRect。 */
class PixelCanvas {
  static readonly SIZE = 64;
  readonly data = new Uint8Array(PixelCanvas.SIZE * PixelCanvas.SIZE * 4);

  fillRect(x: number, y: number, w: number, h: number, color: Rgba): void {
    const size = PixelCanvas.SIZE;
    for (let py = Math.max(0, y); py < Math.min(size, y + h); py++)
      for (let px = Math.max(0, x); px < Math.min(size, x + w); px++) {
        const i = (py * size + px) * 4;
        this.data[i] = color.r;
        this.data[i + 1] = color.g;
        this.data[i + 2] = color.b;
        this.data[i + 3] = 255;
      }
  }
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

/** 17 套古风 NPC 色板，顺序与 `GOD_SPRITE_KEYS` 的 01..17 对齐（本步只用
 *  chenmo，但表是直搬，第 2 步铺开到 50 人时不必再改）。 */
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
  const index = /^god_villager_(\d{2})$/.exec(id);
  const item = index ? NPC_ARCHETYPES[Number(index[1]) - 1] : undefined;
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

/** 程序化 64×64 角色贴图。分区与 SDK 一致：
 *  (0,0,32,16) 头脸 / (0,16,32,16) 躯干 / (32,0,32,16) 手臂 /
 *  (32,16,32,16) 腿靴 / (0,32,64,32) 配件。 */
function paintTexture(preset: AvatarPreset): Uint8Array {
  const canvas = new PixelCanvas();
  const { skin, hair, robeMain, robeSub, belt, trim, boots } = {
    skin: parseHex(preset.skin),
    hair: parseHex(preset.hair),
    robeMain: parseHex(preset.robeMain),
    robeSub: parseHex(preset.robeSub),
    belt: parseHex(preset.belt),
    trim: parseHex(preset.trim),
    boots: parseHex(preset.boots),
  };
  const black = parseHex('#171717');
  const white = parseHex('#ffffff');
  const cloth = parseHex('#f6e8dc');

  canvas.fillRect(0, 0, 64, 64, robeMain);

  // 1. 头与五官
  canvas.fillRect(0, 0, 32, 16, skin);
  canvas.fillRect(0, 0, 32, 5, hair);
  canvas.fillRect(16, 5, 16, 11, hair);
  canvas.fillRect(0, 5, 2, 7, hair);
  canvas.fillRect(14, 5, 2, 7, hair);
  canvas.fillRect(4, 8, 2, 3, black);
  canvas.fillRect(10, 8, 2, 3, black);
  canvas.fillRect(5, 8, 1, 1, white);
  canvas.fillRect(11, 8, 1, 1, white);
  canvas.fillRect(7, 12, 2, 1, shade(skin, -22));

  // 2. 躯干交领与束腰
  canvas.fillRect(0, 16, 32, 16, robeMain);
  const weave = shade(robeMain, -14);
  for (let y = 17; y < 31; y += 2)
    for (let x = 1; x < 31; x += 3) canvas.fillRect(x, y, 1, 1, weave);
  canvas.fillRect(4, 16, 2, 6, trim);
  canvas.fillRect(10, 16, 2, 6, trim);
  canvas.fillRect(6, 20, 4, 3, trim);
  canvas.fillRect(6, 16, 4, 4, cloth);
  canvas.fillRect(0, 26, 32, 3, belt);
  if (preset.id === 'chenmo') canvas.fillRect(11, 26, 3, 5, parseHex('#882e2e'));

  // 3. 手臂与护腕
  canvas.fillRect(32, 0, 32, 10, robeMain);
  canvas.fillRect(32, 8, 32, 3, trim);
  canvas.fillRect(32, 11, 32, 5, skin);

  // 4. 腿与靴
  canvas.fillRect(32, 16, 32, 9, robeSub);
  canvas.fillRect(32, 25, 32, 7, boots);

  // 5. 配件区
  canvas.fillRect(0, 32, 32, 32, parseHex('#b89052'));
  const weaveDark = parseHex('#6d4a2f');
  for (let y = 32; y < 64; y += 2)
    for (let x = y % 4 === 0 ? 0 : 1; x < 32; x += 2) canvas.fillRect(x, y, 1, 1, weaveDark);
  canvas.fillRect(32, 32, 16, 16, parseHex('#5a6b49'));
  canvas.fillRect(34, 34, 5, 5, parseHex('#96b37b'));
  canvas.fillRect(48, 32, 16, 16, parseHex('#c43c3c'));

  return canvas.data;
}

function textureFrom(data: Uint8Array): THREE.DataTexture {
  const texture = new THREE.DataTexture(data, 64, 64);
  // DataTexture defaults flipY to false while CanvasTexture defaults to true.
  // The pixel rows below are written top-down (canvas convention) and the UV
  // helper compensates with `1 - py/64`, so the sampler must flip as well —
  // without this the whole atlas renders upside down (head drawn on the legs).
  texture.flipY = true;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}

/** 六个面的 UV 重映射：`regions` 按 BoxGeometry 的面序
 *  (+x, -x, +y, -y, +z, -z) 给出 [u0,v0,u1,v1]；缺省的面沿用自身默认 UV。 */
function remapFaceUvs(geometry: THREE.BoxGeometry, regions: readonly (readonly number[])[]): void {
  const uvs = geometry.getAttribute('uv');
  for (let face = 0; face < regions.length; face++) {
    const region = regions[face];
    if (!region) continue;
    const [u0, v0, u1, v1] = region as [number, number, number, number];
    const base = face * 4;
    uvs.setXY(base, u0, v1);
    uvs.setXY(base + 1, u1, v1);
    uvs.setXY(base + 2, u0, v0);
    uvs.setXY(base + 3, u1, v0);
  }
  uvs.needsUpdate = true;
}

/** 像素坐标 (px0,py0)-(px1,py1) → 归一化 UV，v 轴翻转。 */
function pixelRegion(px0: number, py0: number, px1: number, py1: number): readonly number[] {
  return [px0 / 64, 1 - py1 / 64, px1 / 64, 1 - py0 / 64];
}

function box(w: number, h: number, d: number, pivotY: number): THREE.BoxGeometry {
  const geometry = new THREE.BoxGeometry(w, h, d);
  geometry.translate(0, pivotY, 0);
  return geometry;
}

function headGeometry(): THREE.BoxGeometry {
  const size = 0.64;
  const geometry = box(size, size, size, size / 2);
  remapFaceUvs(geometry, [
    pixelRegion(0, 0, 4, 16), // +x 右鬓
    pixelRegion(12, 0, 16, 16), // -x 左鬓
    pixelRegion(16, 0, 32, 16), // +y 头顶
    pixelRegion(2, 12, 14, 16), // -y 下巴
    pixelRegion(0, 0, 16, 16), // +z 正脸
    pixelRegion(16, 0, 32, 16), // -z 后脑
  ]);
  return geometry;
}

function torsoGeometry(): THREE.BoxGeometry {
  const geometry = box(0.5, 0.39, 0.26, 0.39 / 2);
  remapFaceUvs(geometry, [
    pixelRegion(16, 16, 24, 32),
    pixelRegion(16, 16, 24, 32),
    pixelRegion(16, 16, 28, 22),
    pixelRegion(16, 26, 28, 32),
    pixelRegion(0, 16, 16, 32), // +z 前胸交领
    pixelRegion(16, 16, 32, 32), // -z 后背
  ]);
  return geometry;
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

export interface Avatar3D {
  readonly root: THREE.Group;
  setPosition(x: number, y: number, z: number): void;
  setFacing(facing: AvatarFacing): void;
  setAnim(anim: AvatarAnim): void;
  /** 走环相位（秒）。由调用方按**实际显示位移**推进，见模块头注释。 */
  setPhase(seconds: number): void;
  /** 跳跃进度 0..1；null 表示不在空中。 */
  setJumpProgress(progress: number | null): void;
  setTint(hex: number): void;
  setXray(enabled: boolean): void;
  update(deltaSeconds: number): void;
  dispose(): void;
}

const DEG = Math.PI / 180;

export function createAvatar(presetOrId: string | AvatarPreset): Avatar3D {
  const preset = typeof presetOrId === 'string' ? presetFor(presetOrId) : presetOrId;
  const pixelData = paintTexture(preset);
  const texture = textureFrom(pixelData);
  const bodyMaterial = new THREE.MeshLambertMaterial({ map: texture });
  const xrayMaterial = new THREE.MeshBasicMaterial({
    color: 0xffd166,
    transparent: true,
    opacity: 0.42,
    depthFunc: THREE.GreaterDepth,
    depthWrite: false,
  });
  const geometries: THREE.BufferGeometry[] = [];
  const flatMaterials: THREE.MeshLambertMaterial[] = [];
  const xrayMeshes: THREE.Mesh[] = [];
  /** Every material's own colour, so a tint multiplies instead of replacing.
   *  The wire's tint is a multiplier (white = unchanged); assigning it straight
   *  onto `color` would paint the hair and every accessory solid white. */
  const baseColors = new Map<THREE.MeshLambertMaterial, THREE.Color>();

  const flatMaterial = (hex: string): THREE.MeshLambertMaterial => {
    const material = new THREE.MeshLambertMaterial({ color: hex });
    flatMaterials.push(material);
    return material;
  };

  const addPart = (parent: THREE.Object3D, geometry: THREE.BufferGeometry, hex?: string) => {
    geometries.push(geometry);
    const material = hex === undefined ? bodyMaterial : flatMaterial(hex);
    if (!baseColors.has(material)) baseColors.set(material, material.color.clone());
    const mesh = new THREE.Mesh(geometry, material);
    // 分节骨骼运动会把零件推出原包围球，直接关掉视锥剔除，比伪造半径干净。
    mesh.frustumCulled = false;
    parent.add(mesh);
    const xray = new THREE.Mesh(geometry, xrayMaterial);
    xray.frustumCulled = false;
    xray.visible = false;
    parent.add(xray);
    xrayMeshes.push(xray);
    return mesh;
  };

  const mappedBox = (
    w: number,
    h: number,
    d: number,
    pivotY: number,
    region?: readonly number[],
  ) => {
    const geometry = box(w, h, d, pivotY);
    if (region) remapFaceUvs(geometry, [region, region, region, region, region, region]);
    return geometry;
  };

  // ── 骨架（16 个 Group + root）────────────────────────────────────
  const root = new THREE.Group();
  root.name = 'avatar-root';

  const hips = new THREE.Group();
  hips.position.set(0, 0.58, 0);
  root.add(hips);
  addPart(hips, mappedBox(0.5, 0.19, 0.26, 0.19 / 2, pixelRegion(16, 16, 32, 32)));

  const spine = new THREE.Group();
  spine.position.set(0, 0.13, 0);
  hips.add(spine);
  addPart(spine, torsoGeometry());

  const head = new THREE.Group();
  head.position.set(0, 0.45, 0);
  spine.add(head);
  addPart(head, headGeometry());

  const hairAcc = new THREE.Group();
  hairAcc.position.set(0, 0.64, 0);
  head.add(hairAcc);

  const bunGroup = new THREE.Group();
  addPart(bunGroup, mappedBox(0.26, 0.16, 0.26, 0.08, pixelRegion(16, 0, 32, 16)), preset.hair);
  addPart(bunGroup, mappedBox(0.28, 0.05, 0.28, 0.025), preset.belt);
  hairAcc.add(bunGroup);

  const strawHatGroup = new THREE.Group();
  addPart(strawHatGroup, mappedBox(0.88, 0.05, 0.88, -0.02, pixelRegion(0, 32, 32, 64)));
  addPart(strawHatGroup, mappedBox(0.52, 0.14, 0.52, 0.07, pixelRegion(0, 32, 32, 64)));
  hairAcc.add(strawHatGroup);

  const backProp = new THREE.Group();
  backProp.position.set(0, 0.28, -0.14);
  spine.add(backProp);

  const basketGroup = new THREE.Group();
  const basketBox = mappedBox(0.36, 0.42, 0.24, 0, pixelRegion(0, 32, 32, 64));
  basketBox.translate(0, 0, -0.12);
  addPart(basketGroup, basketBox);
  const herbsBox = mappedBox(0.28, 0.12, 0.16, 0.24, pixelRegion(32, 32, 48, 48));
  herbsBox.translate(0, 0, -0.12);
  addPart(basketGroup, herbsBox, '#5a6b49');
  const gourdBox = mappedBox(0.11, 0.18, 0.11, 0);
  gourdBox.translate(-0.2, 0.02, -0.12);
  addPart(basketGroup, gourdBox, '#c43c3c');
  backProp.add(basketGroup);

  const sackGroup = new THREE.Group();
  const sackBox = mappedBox(0.4, 0.38, 0.22, 0);
  sackBox.translate(0, 0.02, -0.11);
  addPart(sackGroup, sackBox, '#d4c38c');
  backProp.add(sackGroup);

  const robeFront = new THREE.Group();
  robeFront.position.set(0, 0.02, 0.135);
  hips.add(robeFront);
  addPart(robeFront, mappedBox(0.51, 0.32, 0.03, -0.16, pixelRegion(0, 16, 16, 32)));

  const robeBack = new THREE.Group();
  robeBack.position.set(0, 0.02, -0.135);
  hips.add(robeBack);
  addPart(robeBack, mappedBox(0.51, 0.32, 0.03, -0.16, pixelRegion(16, 16, 32, 32)));

  const armUpperL = new THREE.Group();
  armUpperL.position.set(0.35, 0.39, 0);
  spine.add(armUpperL);
  addPart(armUpperL, mappedBox(0.2, 0.29, 0.2, -0.29 / 2, pixelRegion(32, 0, 48, 10)));

  const armLowerL = new THREE.Group();
  armLowerL.position.set(0, -0.29, 0);
  armUpperL.add(armLowerL);
  addPart(armLowerL, mappedBox(0.19, 0.29, 0.19, -0.29 / 2, pixelRegion(32, 6, 48, 16)));

  const armUpperR = new THREE.Group();
  armUpperR.position.set(-0.35, 0.39, 0);
  spine.add(armUpperR);
  addPart(armUpperR, mappedBox(0.2, 0.29, 0.2, -0.29 / 2, pixelRegion(32, 0, 48, 10)));

  const armLowerR = new THREE.Group();
  armLowerR.position.set(0, -0.29, 0);
  armUpperR.add(armLowerR);
  addPart(armLowerR, mappedBox(0.19, 0.29, 0.19, -0.29 / 2, pixelRegion(32, 6, 48, 16)));

  const handSlotR = new THREE.Group();
  handSlotR.position.set(0, -0.24, 0.06);
  armLowerR.add(handSlotR);
  const handleGeom = mappedBox(0.04, 0.04, 0.52, 0);
  handleGeom.translate(0, 0, 0.16);
  addPart(handSlotR, handleGeom, '#6d4a2f');
  const bladeGeom = mappedBox(0.04, 0.18, 0.06, -0.07);
  bladeGeom.translate(0, 0, 0.4);
  addPart(handSlotR, bladeGeom, '#94a3b8');

  const legUpperL = new THREE.Group();
  legUpperL.position.set(0.13, 0, 0);
  hips.add(legUpperL);
  addPart(legUpperL, mappedBox(0.23, 0.29, 0.23, -0.29 / 2, pixelRegion(32, 16, 48, 25)));

  const legLowerL = new THREE.Group();
  legLowerL.position.set(0, -0.29, 0);
  legUpperL.add(legLowerL);
  addPart(legLowerL, mappedBox(0.22, 0.29, 0.22, -0.29 / 2, pixelRegion(32, 22, 48, 32)));

  const legUpperR = new THREE.Group();
  legUpperR.position.set(-0.13, 0, 0);
  hips.add(legUpperR);
  addPart(legUpperR, mappedBox(0.23, 0.29, 0.23, -0.29 / 2, pixelRegion(32, 16, 48, 25)));

  const legLowerR = new THREE.Group();
  legLowerR.position.set(0, -0.29, 0);
  legUpperR.add(legLowerR);
  addPart(legLowerR, mappedBox(0.22, 0.29, 0.22, -0.29 / 2, pixelRegion(32, 22, 48, 32)));

  const acc = preset.acc;
  bunGroup.visible = acc.bun && !acc.strawHat;
  strawHatGroup.visible = acc.strawHat;
  basketGroup.visible = acc.basket;
  sackGroup.visible = acc.sack && !acc.basket;
  robeFront.visible = acc.robe;
  robeBack.visible = acc.robe;
  handSlotR.visible = acc.herbTool;

  const bones = {
    hips,
    spine,
    head,
    armUpperL,
    armLowerL,
    armUpperR,
    armLowerR,
    legUpperL,
    legLowerL,
    legUpperR,
    legLowerR,
    robeFront,
    robeBack,
  };

  let targetRotY = 0;
  let anim: AvatarAnim = 'idle';
  let phase = 0;
  let jumpProgress: number | null = null;

  const evaluate = () => {
    const b = bones;
    b.hips.position.set(0, 0.58, 0);
    b.hips.rotation.set(0, 0, 0);
    b.spine.rotation.set(0, 0, 0);
    b.head.rotation.set(0, 0, 0);
    b.armUpperL.rotation.set(0, 0, 0);
    b.armLowerL.rotation.set(0, 0, 0);
    b.armUpperR.rotation.set(0, 0, 0);
    b.armLowerR.rotation.set(0, 0, 0);
    b.legUpperL.rotation.set(0, 0, 0);
    b.legLowerL.rotation.set(0, 0, 0);
    b.legUpperR.rotation.set(0, 0, 0);
    b.legLowerR.rotation.set(0, 0, 0);
    b.robeFront.rotation.set(0, 0, 0);
    b.robeBack.rotation.set(0, 0, 0);

    if (anim === 'idle') {
      const breathe = Math.sin((phase / 1.6) * Math.PI * 2);
      b.hips.position.y = 0.58 + breathe * 0.015;
      b.spine.rotation.x = (2 + breathe * 1.5) * DEG;
      b.head.rotation.y = Math.sin(phase * 1.1) * 5 * DEG;
      b.armUpperL.rotation.z = (3 + breathe * 1.5) * DEG;
      b.armUpperR.rotation.z = -(3 + breathe * 1.5) * DEG;
      b.armLowerL.rotation.x = -10 * DEG;
      b.armLowerR.rotation.x = -10 * DEG;
      return;
    }
    if (anim === 'walk') {
      const s = Math.sin((phase / 0.6) * Math.PI * 2);
      const c = Math.cos((phase / 0.6) * Math.PI * 2);
      b.hips.position.y = 0.58 + Math.abs(c) * 0.03 - 0.015;
      b.spine.rotation.x = 3 * DEG;
      b.spine.rotation.y = -s * 4 * DEG;
      b.head.rotation.x = -2 * DEG;
      b.head.rotation.y = s * 3 * DEG;
      b.legUpperL.rotation.x = -s * 28 * DEG;
      b.legUpperR.rotation.x = s * 28 * DEG;
      b.legLowerL.rotation.x = (Math.max(0, -c) * 20 + 5) * DEG;
      b.legLowerR.rotation.x = (Math.max(0, c) * 20 + 5) * DEG;
      b.armUpperL.rotation.x = s * 25 * DEG;
      b.armUpperR.rotation.x = -s * 25 * DEG;
      b.armLowerL.rotation.x = -15 * DEG;
      b.armLowerR.rotation.x = -15 * DEG;
      b.robeFront.rotation.x = -Math.max(0.05, Math.abs(s) * 0.32);
      b.robeBack.rotation.x = Math.max(0.05, Math.abs(s) * 0.25);
      return;
    }
    if (anim === 'run') {
      const s = Math.sin((phase / 0.4) * Math.PI * 2);
      const c = Math.cos((phase / 0.4) * Math.PI * 2);
      b.hips.position.y = 0.54 + Math.sin((phase / 0.4) * Math.PI * 4 - Math.PI * 0.3) * 0.065;
      b.spine.rotation.x = 18 * DEG;
      b.spine.rotation.y = -s * 12 * DEG;
      b.head.rotation.x = -12 * DEG;
      b.head.rotation.y = s * 8 * DEG;
      b.legUpperL.rotation.x = (-s * 52 + 3) * DEG;
      b.legUpperR.rotation.x = (s * 52 + 3) * DEG;
      b.legLowerL.rotation.x = (Math.max(0, -s * 0.5 - c * 0.6) * 75 + 10) * DEG;
      b.legLowerR.rotation.x = (Math.max(0, s * 0.5 + c * 0.6) * 75 + 10) * DEG;
      b.armUpperL.rotation.x = s * 62 * DEG;
      b.armUpperR.rotation.x = -s * 62 * DEG;
      b.armUpperL.rotation.z = 8 * DEG;
      b.armUpperR.rotation.z = -8 * DEG;
      b.armLowerL.rotation.x = -(72 + Math.max(0, -s) * 15) * DEG;
      b.armLowerR.rotation.x = -(72 + Math.max(0, s) * 15) * DEG;
      b.robeFront.rotation.x = -(28 + Math.abs(s) * 25) * DEG;
      b.robeBack.rotation.x = (35 + Math.abs(c) * 20) * DEG;
      return;
    }
    // jump：把 0..1 的进度映射到 SDK 的 0.16/0.71/0.91 三段窗口。
    const t = Math.min(1, Math.max(0, jumpProgress ?? 0)) * 0.91;
    if (t < 0.16) {
      const p = t / 0.16;
      const squash = p < 0.65 ? p / 0.65 : 1 - (p - 0.65) / 0.35;
      b.hips.position.y = 0.58 - squash * 0.16;
      b.spine.rotation.x = squash * 22 * DEG;
      b.legUpperL.rotation.x = -squash * 40 * DEG;
      b.legUpperR.rotation.x = -squash * 40 * DEG;
      b.legLowerL.rotation.x = squash * 80 * DEG;
      b.legLowerR.rotation.x = squash * 80 * DEG;
      b.armUpperL.rotation.x = squash * 45 * DEG;
      b.armUpperR.rotation.x = squash * 45 * DEG;
      b.armLowerL.rotation.x = -35 * DEG;
      b.armLowerR.rotation.x = -35 * DEG;
    } else if (t < 0.71) {
      const airP = (t - 0.16) / 0.55;
      b.hips.position.y = 0.58 + 4 * airP * (1 - airP) * 1.15;
      b.spine.rotation.x = (10 - airP * 16) * DEG;
      b.legUpperL.rotation.x = -45 * DEG;
      b.legLowerL.rotation.x = 65 * DEG;
      b.legUpperR.rotation.x = 20 * DEG;
      b.legLowerR.rotation.x = 25 * DEG;
      b.armUpperL.rotation.x = -60 * DEG;
      b.armUpperR.rotation.x = -60 * DEG;
      b.armUpperL.rotation.z = 25 * DEG;
      b.armUpperR.rotation.z = -25 * DEG;
      b.armLowerL.rotation.x = -35 * DEG;
      b.armLowerR.rotation.x = -35 * DEG;
      b.robeFront.rotation.x = -40 * DEG;
      b.robeBack.rotation.x = 42 * DEG;
    } else {
      const landP = Math.min(1, (t - 0.71) / 0.2);
      const dip = Math.sin(landP * Math.PI);
      b.hips.position.y = 0.58 - dip * 0.18;
      b.spine.rotation.x = dip * 25 * DEG;
      b.head.rotation.x = dip * 10 * DEG;
      b.legUpperL.rotation.x = -dip * 42 * DEG;
      b.legUpperR.rotation.x = -dip * 42 * DEG;
      b.legLowerL.rotation.x = dip * 84 * DEG;
      b.legLowerR.rotation.x = dip * 84 * DEG;
      b.armUpperL.rotation.z = dip * 20 * DEG;
      b.armUpperR.rotation.z = -dip * 20 * DEG;
      b.armLowerL.rotation.x = -dip * 40 * DEG;
      b.armLowerR.rotation.x = -dip * 40 * DEG;
    }
  };
  evaluate();

  return {
    root,
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
      const tint = new THREE.Color(hex);
      for (const [material, base] of baseColors) material.color.copy(base).multiply(tint);
    },
    setXray(enabled) {
      for (const mesh of xrayMeshes) mesh.visible = enabled;
    },
    update(deltaSeconds) {
      // 最短弧度平滑转向：跨 ±π 时不绕远路。
      const diff = ((targetRotY - root.rotation.y + Math.PI) % (Math.PI * 2)) - Math.PI;
      const shortest = diff < -Math.PI ? diff + Math.PI * 2 : diff;
      root.rotation.y += shortest * Math.min(1, deltaSeconds * 15);
      evaluate();
    },
    dispose() {
      for (const geometry of geometries) geometry.dispose();
      for (const material of flatMaterials) material.dispose();
      bodyMaterial.dispose();
      xrayMaterial.dispose();
      texture.dispose();
    },
  };
}

/** 相位推进：`animClock` 是 `advanceMotion` 按**实际显示距离**累计的毫秒数
 *  （每格 250ms），换算成秒再乘每格周期，保证腿速与位移同源。 */
export function phaseFromAnimClock(animClockMs: number): number {
  return (animClockMs / 250) * WALK_CYCLE_SECONDS_PER_TILE;
}
