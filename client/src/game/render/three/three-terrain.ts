/** Isometric block terrain rendered with three.js.
 *
 * One `InstancedMesh` per height layer (0..3) of 1×1×1 boxes. Every instance
 * carries a per-cell colour sampled from the tileset, so the whole 140×100 map
 * costs four draw calls instead of 14,000 sprites — that is the reason this
 * renderer exists at all.
 *
 * Geometry lives entirely in **world units**, one unit per map cell, and comes
 * from `three-projection.ts`: a block's footprint centre IS `worldOf(x, y)`, so
 * the camera, the raycaster and the blocks cannot drift apart. Pixels never
 * enter this file; the camera's frustum does the scaling.
 *
 * Block appearance uses the existing per-cell palette and nearest-filtered
 * pixel grain on unit cubes; tall columns never stretch a texture.
 */

import * as THREE from 'three';
import { createCamera, resizeCamera, worldOf } from './three-projection';

/** Fraction of a cell that a water slab occupies. Thin enough to read as a
 * surface, thick enough to still catch the key light. */
export const WATER_THICKNESS = 0.06;

/** Render layers. Layer 0 is water, layers 1..3 are the block stacks. */
export const LAYERS = 4;

/** Clamp a cell height into the render layers. Cells outside the height table
 * already normalise to 1 upstream; this only guards the instanced arrays. */
export function layerOf(h: number): number {
  return Math.max(0, Math.min(LAYERS - 1, Math.trunc(h)));
}

/** Deterministic per-cell brightness jitter in -0.5..0.5. Pure flat blocks read
 * as plastic without it; Minecraft blocks carry the same grain. The hash is
 * positional only, so two clients with the same map see the same town. */
export function grainOf(x: number, y: number): number {
  let v = (x * 374761393 + y * 668265263) >>> 0;
  v = ((v ^ (v >>> 13)) * 1274126177) >>> 0;
  return (v % 17) / 17 - 0.5;
}

/** Scale a 0xRRGGBB colour by the cell's grain, clamped per channel. */
export function tinted(color: number, x: number, y: number): number {
  const factor = 1 + grainOf(x, y) * 0.16;
  const clamp = (v: number): number => Math.max(0, Math.min(255, Math.round(v)));
  const r = clamp(((color >> 16) & 255) * factor);
  const g = clamp(((color >> 8) & 255) * factor);
  const b = clamp((color & 255) * factor);
  return (r << 16) | (g << 8) | b;
}

export interface BlockTransform {
  readonly position: { readonly x: number; readonly y: number; readonly z: number };
  /** Height of the box in world units: a cell stack is `level` units tall, the
   * water slab is `WATER_THICKNESS`. */
  readonly scaleY: number;
}

/** Where a cell's box sits in world space, as plain numbers so it can be
 * asserted without a WebGL context.
 *
 * The box's **bottom face is the ground plane** for a stacked block and its
 * **top face is the ground plane** for water, so the surface a walker stands on
 * is at y = 0 in both cases and matches what `worldOf` / the raycaster expect.
 *
 */
export function blockTransform(
  x: number,
  y: number,
  h: number,
  mapW: number,
  mapH: number,
): BlockTransform {
  const layer = layerOf(h);
  const centre = worldOf(x, y, mapW, mapH);
  const scaleY = layer === 0 ? WATER_THICKNESS : layer;
  const bottom = layer === 0 ? -WATER_THICKNESS : 0;
  return {
    position: { x: centre.x, y: bottom + scaleY / 2, z: centre.z },
    scaleY,
  };
}

export interface TerrainCell {
  readonly x: number;
  readonly y: number;
  /** 0 = water, 1 = walkable earth, 2..3 = stacked blocks. */
  readonly h: number;
  /** 0xRRGGBB, already sampled from the tileset. */
  readonly color: number;
  /** 高度 1 但不可走：土坎，以及玩家刚放下的土块。
   *
   * 它和可走平地**同高**，所以只靠盒子本身根本看不出来 —— 放进世界里的
   * 土块会像「空白」，天然土坎则像能走的空地。Phaser 路径用三道斜杠字形区分
   * （`iso-terrain.ts::syncBanks`），这里画同一组斜杠。 */
  readonly bank?: boolean;
}

/** 土坎斜纹：与 Phaser 的 `syncBanks` 同形——三道斜杠，一亮一暗。
 *
 * 整块压暗不行：全图 1568 格土坎会连成大片深色斑，可走地面反而像被围住。
 * Phaser 用的是「三道斜杠」字形，两条路径必须给同一个格子同一个读法。 */
export const BANK_SLATS = 3;
/** 斜杠在格子内的相对跨度（Phaser 的 ±7px / 32px 菱形宽）。 */
export const BANK_SLAT_SPAN = 0.42;
export const BANK_SLAT_DARK = 0x2c1b10;
export const BANK_SLAT_LIGHT = 0xf1d793;
/** 斜杠厚度。默认机位俯仰只有 12°，平贴地面的记号会被压成一条线；
 *  0.12 高时斜杠自己的侧面露得出来，任何角度都能看见。 */
export const BANK_SLAT_THICKNESS = 0.12;
/** 底面与方块顶面之间的间隙。两者若完全共面，深度相等时的先后就靠
 *  polygonOffset 的舍入运气 —— 抬 4 毫米，任何驱动都不会抖。 */
export const BANK_SLAT_LIFT = 0.004;
/** 土坎格整体压暗系数。只压一点点：1568 格若压狠了会连成大片深色斑，
 *  可走地面反而像被围起来。作用是给斜纹一个底色差，不是替代它。 */
export const BANK_TINT = 0.85;

export interface TerrainScene {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene: THREE.Scene;
  readonly camera: THREE.PerspectiveCamera;
  readonly meshes: readonly THREE.InstancedMesh[];
  /** Replace every instance. Cheap enough to call on each terrain revision. */
  setCells(cells: readonly TerrainCell[], w: number, h: number): void;
  /** Draw one frame. The caller owns the animation loop. */
  render(): void;
  /** Refit the frustum after a canvas resize. */
  resize(aspect: number): void;
  dispose(): void;
}

/** Per-face brightness, copied from `iso-terrain.ts::paintBlock`.
 *
 * Lighting the boxes with real lights looked wrong for two reasons: three's
 * Lambert BRDF divides by π, so every face came out ~0.47× the Phaser tone (the
 * scene measured at luma 45 against Phaser's 83), and any light rig makes the
 * same town look different on a machine with a different renderer. Baked face
 * brightness is deterministic and matches the shipped picture exactly. */
export const FACE_SHADE = { top: 1, left: 0.75, right: 0.6 } as const;

/** Exposed for the shading test: the geometry is pure data, no GPU needed. */
export function shadedBoxForTest(): THREE.BoxGeometry {
  return shadedBox();
}

/** A box with its three visible faces pre-shaded. Index order follows the
 * BoxGeometry vertex layout: +x, -x, +y, -y, +z, -z. */
function shadedBox(): THREE.BoxGeometry {
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const shade = [FACE_SHADE.right, 1, FACE_SHADE.top, 1, FACE_SHADE.left, 1];
  const colour = new THREE.Color();
  const count = geometry.getAttribute('position').count;
  const perVertex = count / 6;
  const colors = new Float32Array(count * 3);
  for (let vertex = 0; vertex < count; vertex++) {
    const face = Math.floor(vertex / perVertex);
    const value = shade[face] ?? 1;
    colour.setRGB(value, value, value);
    colors[vertex * 3] = colour.r;
    colors[vertex * 3 + 1] = colour.g;
    colors[vertex * 3 + 2] = colour.b;
  }
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  return geometry;
}

export interface BlockInstance extends BlockTransform {
  readonly cell: TerrainCell;
}

/** 只有土坎格需要斜纹；高度 ≥2 的阻挡格本来就看得见。 */
export function bankCells(cells: readonly TerrainCell[]): TerrainCell[] {
  return cells.filter((cell) => cell.bank === true && layerOf(cell.h) === 1);
}

/** 一条斜杠的世界位姿：三道平行，横跨格子、贴在 h=1 顶面之上。
 *
 * 角度固定 45°（Phaser 字形也是 ±1px/3px 的斜率），不随相机转——
 * 它是画在地面上的记号，不是朝向玩家的贴片。 */
export function bankSlatTransform(
  x: number,
  y: number,
  slat: number,
  mapW: number,
  mapH: number,
): BlockTransform & { readonly rotationY: number } {
  const centre = worldOf(x, y, mapW, mapH);
  // 三道斜杠互相平行（盒子绕 Y 转 45° 后长轴落在 x-z 对角线上），
  // 所以「垂直于杠」的方向是 x+z：沿它等距铺开，跨度为 ±span/2。
  const t = (slat / (BANK_SLATS - 1)) * 2 - 1;
  const offset = t * BANK_SLAT_SPAN * 0.5;
  return {
    position: {
      x: centre.x + offset,
      y: 1 + BANK_SLAT_LIFT + BANK_SLAT_THICKNESS / 2,
      z: centre.z + offset,
    },
    scaleY: BANK_SLAT_THICKNESS,
    rotationY: Math.PI / 4,
  };
}

export function blockInstances(
  cells: readonly TerrainCell[],
  w: number,
  h: number,
): BlockInstance[] {
  const instances: BlockInstance[] = [];
  for (const cell of cells) {
    const height = layerOf(cell.h);
    if (height === 0) instances.push({ ...blockTransform(cell.x, cell.y, 0, w, h), cell });
    for (let level = 0; level < height; level++) {
      const transform = blockTransform(cell.x, cell.y, 1, w, h);
      instances.push({ ...transform, position: { ...transform.position, y: level + 0.5 }, cell });
    }
  }
  return instances;
}

function skyTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 2;
  canvas.height = 512;
  const ctx = canvas.getContext('2d')!;
  const gradient = ctx.createLinearGradient(0, 0, 0, 512);
  gradient.addColorStop(0, '#80b9e7');
  gradient.addColorStop(0.65, '#c8e0ef');
  gradient.addColorStop(1, '#e6eef2');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 2, 512);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function blockTexture(): THREE.DataTexture {
  const pixels = new Uint8Array(16 * 16 * 4);
  for (let i = 0; i < 256; i++) {
    const value = 239 + ((i * 37 + (i >> 4) * 13) % 17);
    pixels.set([value, value, value, 255], i * 4);
  }
  const texture = new THREE.DataTexture(pixels, 16, 16);
  texture.magFilter = texture.minFilter = THREE.NearestFilter;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

export function createTerrainScene(canvas: HTMLCanvasElement): TerrainScene {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(2, globalThis.devicePixelRatio ?? 1));

  const scene = new THREE.Scene();
  const sky = skyTexture();
  scene.background = sky;
  scene.fog = new THREE.Fog(0xdce9f1, 32, 80);

  // Perspective camera from the projection contract — the same one picking
  // raycasts through, so blocks and clicks share one authority.
  const camera = createCamera(1, 1, 1);

  // No lights: brightness is baked into the geometry's vertex colours (see
  // FACE_SHADE), so the result is identical to the Phaser painter on every
  // device and does not depend on a BRDF's normalisation.
  const texture = blockTexture();
  const geometry = shadedBox();
  const material = new THREE.MeshBasicMaterial({ vertexColors: true, map: texture });
  // 土坎斜杠：细长盒子，抬到顶面之上。关雾——雾会把远处的斜杠冲淡成一片糊。
  const slatGeometry = new THREE.BoxGeometry(0.62, 1, 0.12);
  const slatDarkMaterial = new THREE.MeshBasicMaterial({
    color: BANK_SLAT_DARK,
    fog: false,
    polygonOffset: true,
    polygonOffsetFactor: -1,
    polygonOffsetUnits: -1,
  });
  const slatLightMaterial = new THREE.MeshBasicMaterial({
    color: BANK_SLAT_LIGHT,
    fog: false,
    polygonOffset: true,
    polygonOffsetFactor: -1,
    polygonOffsetUnits: -1,
  });

  const UP = new THREE.Vector3(0, 1, 0);
  let meshes: THREE.InstancedMesh[] = [];
  let mapW = 1;
  let mapH = 1;

  const clearMeshes = (): void => {
    for (const mesh of meshes) {
      scene.remove(mesh);
      mesh.dispose();
    }
    meshes = [];
  };

  const setCells = (cells: readonly TerrainCell[], w: number, h: number): void => {
    clearMeshes();
    mapW = w;
    mapH = h;

    const instances = blockInstances(cells, w, h);
    const counts = new Array<number>(LAYERS).fill(0);
    for (const instance of instances) counts[layerOf(instance.cell.h)]! += 1;

    const matrix = new THREE.Matrix4();
    const colour = new THREE.Color();
    for (let layer = 0; layer < LAYERS; layer++) {
      const count = counts[layer]!;
      if (count === 0) continue;
      const mesh = new THREE.InstancedMesh(geometry, material, count);
      mesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);
      let i = 0;
      const batch = instances.filter((instance) => layerOf(instance.cell.h) === layer);
      mesh.userData.cells = batch.map((instance) => instance.cell);
      for (const t of batch) {
        const cell = t.cell;
        matrix.makeScale(1, t.scaleY, 1);
        matrix.setPosition(t.position.x, t.position.y, t.position.z);
        mesh.setMatrixAt(i, matrix);
        colour.setHex(tinted(cell.color, cell.x, cell.y));
        if (cell.bank === true) colour.multiplyScalar(BANK_TINT);
        mesh.setColorAt(i, colour);
        i += 1;
      }
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      // Instanced bounds are computed from the base geometry, not the instances.
      mesh.computeBoundingBox();
      mesh.computeBoundingSphere();
      mesh.frustumCulled = false;
      meshes.push(mesh);
      scene.add(mesh);
    }

    // 土坎斜纹：两道 InstancedMesh（暗杠 + 亮芯），与 Phaser 的 `syncBanks` 同形。
    // 不设 `userData.cells` —— `editFromRay` 只认带 cells 的 mesh，
    // 斜纹不该成为编辑目标（点它应该命中下面的方块）。
    const banks = bankCells(cells);
    if (banks.length > 0) {
      const slatCount = banks.length * BANK_SLATS;
      const dark = new THREE.InstancedMesh(slatGeometry, slatDarkMaterial, slatCount);
      const light = new THREE.InstancedMesh(slatGeometry, slatLightMaterial, slatCount);
      const quaternion = new THREE.Quaternion();
      let index = 0;
      for (const cell of banks) {
        for (let slat = 0; slat < BANK_SLATS; slat++) {
          const t = bankSlatTransform(cell.x, cell.y, slat, w, h);
          quaternion.setFromAxisAngle(UP, t.rotationY);
          matrix.compose(
            new THREE.Vector3(t.position.x, t.position.y, t.position.z),
            quaternion,
            new THREE.Vector3(1, t.scaleY, 1),
          );
          dark.setMatrixAt(index, matrix);
          // 亮芯比暗杠细一档、抬高一丁点，读作「斜杠中间的高光」。
          matrix.compose(
            new THREE.Vector3(t.position.x, t.position.y + 0.01, t.position.z),
            quaternion,
            new THREE.Vector3(0.55, t.scaleY, 0.45),
          );
          light.setMatrixAt(index, matrix);
          index += 1;
        }
      }
      for (const mesh of [dark, light]) {
        mesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);
        mesh.instanceMatrix.needsUpdate = true;
        mesh.computeBoundingBox();
        mesh.computeBoundingSphere();
        mesh.frustumCulled = false;
        mesh.renderOrder = 1;
        meshes.push(mesh);
        scene.add(mesh);
      }
    }
  };

  const resize = (aspect: number): void => {
    resizeCamera(camera, mapW, mapH, aspect);
  };

  resize(canvas.width / Math.max(1, canvas.height));

  return {
    renderer,
    scene,
    camera,
    get meshes() {
      return meshes;
    },
    setCells,
    resize,
    render: () => renderer.render(scene, camera),
    dispose() {
      clearMeshes();
      material.dispose();
      geometry.dispose();
      slatGeometry.dispose();
      slatDarkMaterial.dispose();
      slatLightMaterial.dispose();
      texture.dispose();
      sky.dispose();
      renderer.dispose();
    },
  };
}
