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
 * Block appearance is Minecraft-style: flat per-cell colour, a small
 * deterministic brightness grain, no texture sampling.
 */

import * as THREE from 'three';
import { HEIGHT_UNIT, createCamera, resizeCamera, worldOf } from './three-projection';

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
 * Every height is multiplied by `HEIGHT_UNIT`: a raw world-Y lift is 1.2247 cell
 * runs, and a block has to be exactly as tall as it is wide (`iso.ts` lifts one
 * level by `ISO.HH` = one cell step). */
export function blockTransform(
  x: number,
  y: number,
  h: number,
  mapW: number,
  mapH: number,
): BlockTransform {
  const layer = layerOf(h);
  const centre = worldOf(x, y, mapW, mapH);
  const scaleY = (layer === 0 ? WATER_THICKNESS : layer) * HEIGHT_UNIT;
  const bottom = layer === 0 ? -WATER_THICKNESS * HEIGHT_UNIT : 0;
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
}

export interface TerrainScene {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene: THREE.Scene;
  readonly camera: THREE.OrthographicCamera;
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

/** One 1×1×1 box shared by every instance, with baked face shading. */
const BOX = shadedBox();

export function createTerrainScene(canvas: HTMLCanvasElement): TerrainScene {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(globalThis.devicePixelRatio ?? 1);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1b2a24);

  // Orthographic camera from the projection contract — the same one picking
  // raycasts through, so blocks and clicks share one authority.
  const camera = createCamera(1, 1, 1);

  // No lights: brightness is baked into the geometry's vertex colours (see
  // FACE_SHADE), so the result is identical to the Phaser painter on every
  // device and does not depend on a BRDF's normalisation.
  const material = new THREE.MeshBasicMaterial({ vertexColors: true });

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

    const counts = new Array<number>(LAYERS).fill(0);
    for (const cell of cells) counts[layerOf(cell.h)]! += 1;

    const matrix = new THREE.Matrix4();
    const colour = new THREE.Color();
    for (let layer = 0; layer < LAYERS; layer++) {
      const count = counts[layer]!;
      if (count === 0) continue;
      const mesh = new THREE.InstancedMesh(BOX, material, count);
      mesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);
      let i = 0;
      for (const cell of cells) {
        if (layerOf(cell.h) !== layer) continue;
        const t = blockTransform(cell.x, cell.y, cell.h, w, h);
        matrix.makeScale(1, t.scaleY, 1);
        matrix.setPosition(t.position.x, t.position.y, t.position.z);
        mesh.setMatrixAt(i, matrix);
        colour.setHex(tinted(cell.color, cell.x, cell.y));
        mesh.setColorAt(i, colour);
        i += 1;
      }
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      // Instanced bounds are computed from the base geometry, not the instances.
      mesh.frustumCulled = false;
      meshes.push(mesh);
      scene.add(mesh);
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
    setCells,
    resize,
    render: () => renderer.render(scene, camera),
    dispose() {
      clearMeshes();
      material.dispose();
      renderer.dispose();
    },
  };
}
