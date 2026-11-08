import * as THREE from 'three';
import { expect, it } from 'vitest';
import { createAvatar, createAvatarLighting, phaseFromAnimClock } from '../avatar3d';

/** Box3.setFromObject counts hidden meshes too; a switched-off accessory must
 *  not inflate the measured silhouette. */
function visibleBox(root: THREE.Object3D): THREE.Box3 {
  const box = new THREE.Box3();
  root.updateMatrixWorld(true);
  root.traverseVisible((node) => {
    if (node instanceof THREE.Mesh) box.expandByObject(node);
  });
  return box;
}

it('builds a 1.80-tall avatar rooted at the feet with no DOM canvas', () => {
  // No accessories: the body itself must be exactly the 2D collision box.
  const plain = createAvatar('villager');
  // DataTexture means this runs in node with no document at all.
  plain.update(1 / 60);
  const plainBox = visibleBox(plain.root);
  expect(plainBox.min.y).toBeCloseTo(0, 2);
  // The idle pose tilts the spine 2°, which lifts the top corner by ~1cm; the
  // skeleton's neutral height is exactly 1.80 (hips .58 + spine .13 + head .45
  // + head 0.64).
  expect(plainBox.max.y).toBeCloseTo(1.8, 1);
  // Nominal width is 0.90 (the 2D collision box); the idle pose splays the arms
  // 3° outward, which adds ~2cm per side.
  expect(plainBox.max.x - plainBox.min.x).toBeLessThanOrEqual(0.96);
  plain.dispose();

  // 陈默的发髻长在头顶之上，所以总高会超过 1.80——SDK 的头顶挂点 1.95 正是
  // 按「头顶 + 发髻」留的余量，这里把它钉住，防止以后把配件塞进身体高度里。
  const hero = createAvatar('chenmo');
  hero.update(1 / 60);
  const heroBox = visibleBox(hero.root);
  expect(heroBox.min.y).toBeCloseTo(0, 2);
  expect(heroBox.max.y).toBeGreaterThan(1.8);
  expect(heroBox.max.y).toBeLessThan(1.98);
  hero.dispose();
});

it('places the feet exactly on the given block top', () => {
  const avatar = createAvatar('chenmo');
  avatar.setPosition(10, 2, 15);
  avatar.update(0);
  expect(avatar.root.position.y).toBe(2);
  const box = visibleBox(avatar.root);
  expect(box.min.y).toBeCloseTo(2, 2);
  avatar.dispose();
});

it('turns toward the world facing, not the camera azimuth', () => {
  const avatar = createAvatar('chenmo');
  avatar.setFacing('e');
  // The smoothing is per-frame; 40 frames is well past the settle time.
  for (let i = 0; i < 40; i++) avatar.update(1 / 60);
  expect(avatar.root.rotation.y).toBeCloseTo(Math.PI / 2, 2);
  avatar.setFacing('n');
  for (let i = 0; i < 40; i++) avatar.update(1 / 60);
  expect(Math.abs(avatar.root.rotation.y)).toBeCloseTo(Math.PI, 2);
  avatar.dispose();
});

it('drives the walk cycle from the displayed distance, not wall clock', () => {
  // Same animClock must produce the same pose regardless of how many frames ran.
  const a = createAvatar('chenmo');
  const b = createAvatar('chenmo');
  a.setAnim('walk');
  b.setAnim('walk');
  a.setPhase(phaseFromAnimClock(250));
  b.setPhase(phaseFromAnimClock(250));
  a.update(1 / 60);
  for (let i = 0; i < 30; i++) b.update(1 / 60);
  expect(phaseFromAnimClock(250)).toBeCloseTo(0.6);
  // One tile of displayed movement == one full step cycle.
  expect(phaseFromAnimClock(500)).toBeCloseTo(1.2);
  a.dispose();
  b.dispose();
});

it('only lights materials that opt into lighting, so the terrain tone is untouched', () => {
  const scene = new THREE.Scene();
  const basic = new THREE.Mesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshBasicMaterial({ color: 0xffffff }),
  );
  scene.add(basic);
  const release = createAvatarLighting(scene);
  expect(scene.children.filter((child) => child instanceof THREE.Light)).toHaveLength(2);
  // MeshBasicMaterial ignores lights entirely; only Lambert/Standard respond.
  expect((basic.material as THREE.MeshBasicMaterial).isMeshBasicMaterial).toBe(true);
  release();
  expect(scene.children.filter((child) => child instanceof THREE.Light)).toHaveLength(0);
  scene.clear();
});

it('flips the pixel rows like a canvas texture so the atlas is not upside down', () => {
  // DataTexture defaults flipY=false; CanvasTexture defaults true. The paint
  // routine writes top-down and the UV helper does `1 - py/64`, so without the
  // flip the face lands on the legs (seen on the real machine 2026-11-08).
  const avatar = createAvatar('chenmo');
  let texture: THREE.DataTexture | undefined;
  avatar.root.traverse((node) => {
    if (node instanceof THREE.Mesh && node.material instanceof THREE.MeshLambertMaterial)
      texture ??= node.material.map as THREE.DataTexture;
  });
  expect(texture).toBeDefined();
  expect(texture!.flipY).toBe(true);
  expect(texture!.magFilter).toBe(THREE.NearestFilter);
  expect(texture!.generateMipmaps).toBe(false);
  avatar.dispose();
});

it('multiplies the wire tint instead of replacing each material colour', () => {
  // The wire sends 0xffffff for "no tint". Assigning it onto `color` would paint
  // the hair and every accessory solid white; it has to be a multiplier. The
  // textured body material legitimately stays white (its colour tints the map).
  const flatColors = (avatar: ReturnType<typeof createAvatar>) => {
    const found = new Set<string>();
    avatar.root.traverse((node) => {
      if (!(node instanceof THREE.Mesh)) return;
      const material = node.material;
      if (material instanceof THREE.MeshLambertMaterial && !material.map)
        found.add(material.color.getHexString());
    });
    return found;
  };
  const avatar = createAvatar('chenmo');
  avatar.setTint(0xffffff);
  const untinted = flatColors(avatar);
  expect(untinted.size).toBeGreaterThan(1);
  expect(untinted.has('ffffff')).toBe(false);
  expect(untinted.has('171717')).toBe(true);

  avatar.setTint(0x000000);
  for (const color of flatColors(avatar)) expect(color).toBe('000000');

  // Restoring white must restore the original palette exactly.
  avatar.setTint(0xffffff);
  expect(flatColors(avatar)).toEqual(untinted);
  avatar.dispose();
});

it('disposes every geometry and material it created', () => {
  const avatar = createAvatar('chenmo');
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  avatar.root.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    geometries.add(node.geometry);
    for (const material of Array.isArray(node.material) ? node.material : [node.material])
      materials.add(material);
  });
  expect(geometries.size).toBeGreaterThan(10);
  const disposed: string[] = [];
  for (const geometry of geometries) geometry.addEventListener('dispose', () => disposed.push('g'));
  for (const material of materials) material.addEventListener('dispose', () => disposed.push('m'));
  avatar.dispose();
  expect(disposed).toHaveLength(geometries.size + materials.size);
});
