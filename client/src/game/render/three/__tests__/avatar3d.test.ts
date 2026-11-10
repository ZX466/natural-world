import * as THREE from 'three';
import { afterEach, expect, it } from 'vitest';
import {
  GOD_SPRITE_POOL,
  createAvatar,
  createAvatarAtlas,
  createAvatarLighting,
  phaseFromAnimClock,
  type Avatar3D,
  type AvatarAtlas,
} from '../avatar3d';

let atlas: AvatarAtlas | null = null;
function sharedAtlas(): AvatarAtlas {
  atlas ??= createAvatarAtlas();
  return atlas;
}
afterEach(() => {
  atlas?.dispose();
  atlas = null;
});

/** Box3.setFromObject counts hidden meshes too; a switched-off outline must
 *  not inflate the measured silhouette. */
function visibleBox(root: THREE.Object3D): THREE.Box3 {
  const box = new THREE.Box3();
  root.updateMatrixWorld(true);
  root.traverseVisible((node) => {
    if (node instanceof THREE.Mesh) box.expandByObject(node);
  });
  return box;
}

function bone(avatar: Avatar3D, name: string): THREE.Bone {
  return avatar.mesh.skeleton.bones.find((item) => item.name === name)!;
}

it('leans forward and swings its arms while working', () => {
  const avatar = createAvatar('villager', sharedAtlas());
  avatar.setAnim('work');
  avatar.setPhase(0);
  avatar.update(0);
  expect(bone(avatar, 'spine').rotation.x).toBeGreaterThan(0.25);
  const arm = bone(avatar, 'armUpperR').rotation.x;
  avatar.setPhase(0.23);
  avatar.update(0);
  expect(Math.abs(bone(avatar, 'armUpperR').rotation.x - arm)).toBeGreaterThan(0.2);
  avatar.dispose();
});

it('brings the right hand to its mouth while eating', () => {
  const avatar = createAvatar('villager', sharedAtlas());
  avatar.setAnim('eat');
  avatar.setPhase(0);
  avatar.update(0);
  avatar.root.updateMatrixWorld(true);
  const hand = new THREE.Vector3(0, -0.29, 0).applyMatrix4(bone(avatar, 'armLowerR').matrixWorld);
  const mouth = new THREE.Vector3(0, 0.16, 0.32).applyMatrix4(bone(avatar, 'head').matrixWorld);
  expect(hand.distanceTo(mouth)).toBeLessThan(0.28);
  expect(hand.y).toBeGreaterThan(bone(avatar, 'armUpperR').getWorldPosition(new THREE.Vector3()).y);
  avatar.dispose();
});

it('crouches with bent knees and grounded feet while resting', () => {
  const avatar = createAvatar('villager', sharedAtlas());
  avatar.setAnim('rest');
  avatar.setPhase(0);
  avatar.update(0);
  expect(bone(avatar, 'hips').position.y).toBeLessThan(0.46);
  expect(bone(avatar, 'legLowerL').rotation.x).toBeGreaterThan(1.5);
  expect(bone(avatar, 'legLowerR').rotation.x).toBeGreaterThan(1.5);
  expect(visibleBox(avatar.root).min.y).toBeCloseTo(0, 3);
  avatar.dispose();
});

it('turns its torso and raises an arm while chatting', () => {
  const avatar = createAvatar('villager', sharedAtlas());
  avatar.setAnim('chat');
  avatar.setPhase(0);
  avatar.update(0);
  expect(bone(avatar, 'spine').rotation.y).toBeGreaterThan(0.2);
  expect(bone(avatar, 'armUpperL').rotation.z).toBeGreaterThan(0.5);
  avatar.dispose();
});

it('keeps four distinct action poses on the same mesh, geometry, material and atlas', () => {
  const shared = sharedAtlas();
  const avatar = createAvatar('chenmo', shared);
  const { mesh } = avatar;
  const { geometry, material, skeleton } = mesh;
  const poses = new Set<string>();
  for (const anim of ['work', 'eat', 'rest', 'chat'] as const) {
    avatar.setAnim(anim);
    avatar.setPhase(0.17);
    avatar.update(0);
    poses.add(JSON.stringify(skeleton.bones.map((item) => [...item.position, ...item.quaternion])));
    const meshes: THREE.Mesh[] = [];
    avatar.root.traverse((node) => {
      if (node instanceof THREE.Mesh) meshes.push(node);
    });
    expect(meshes).toEqual([mesh]);
    expect(mesh.geometry).toBe(geometry);
    expect(mesh.material).toBe(material);
    expect(mesh.skeleton).toBe(skeleton);
    expect(skeleton.bones).toHaveLength(16);
    expect((material as THREE.MeshLambertMaterial).map).toBe(shared.texture);
  }
  expect(poses.size).toBe(4);
  expect(shared.texture.image.width).toBe(512);
  expect(shared.texture.image.height).toBe(256);
  avatar.dispose();
});

it('draws one skinned mesh per avatar, not one per body part', () => {
  // The source SDK emitted 46 meshes (body + outline per part), i.e. ~2346 draw
  // calls at 51 actors. The whole point of this shape is to collapse that.
  const avatar = createAvatar('chenmo', sharedAtlas());
  const meshes: THREE.Mesh[] = [];
  avatar.root.traverse((node) => {
    if (node instanceof THREE.Mesh) meshes.push(node);
  });
  expect(meshes).toHaveLength(1);
  expect(avatar.mesh).toBeInstanceOf(THREE.SkinnedMesh);
  expect(avatar.mesh.material).toBeInstanceOf(THREE.MeshLambertMaterial);
  avatar.dispose();
});

it('shares one atlas texture across every avatar', () => {
  const shared = sharedAtlas();
  const a = createAvatar('chenmo', shared);
  const b = createAvatar('god_villager_ali', shared);
  expect((a.mesh.material as THREE.MeshLambertMaterial).map).toBe(shared.texture);
  expect((b.mesh.material as THREE.MeshLambertMaterial).map).toBe(shared.texture);
  expect(shared.texture.image.width).toBeGreaterThan(256);
  a.dispose();
  b.dispose();
});

it('gives every real NPC sprite key its own atlas tile', () => {
  // The SDK keyed presets by `god_villager_01`..`17`, but the game's sprite keys
  // are names. A mismatch would silently paint every NPC as the protagonist.
  const shared = sharedAtlas();
  const tiles = new Set(GOD_SPRITE_POOL.map((id) => shared.tileOf(id)));
  expect(tiles.size).toBe(GOD_SPRITE_POOL.length);
  expect(tiles.has(shared.tileOf('chenmo'))).toBe(false);
  expect(shared.tileOf('nonexistent')).toBe(shared.tileOf('chenmo'));
});

it('binds a 16-bone skeleton with rigid weights', () => {
  const avatar = createAvatar('chenmo', sharedAtlas());
  const skeleton = avatar.mesh.skeleton;
  expect(skeleton.bones).toHaveLength(16);
  const weights = avatar.mesh.geometry.getAttribute('skinWeight');
  const indices = avatar.mesh.geometry.getAttribute('skinIndex');
  for (let i = 0; i < weights.count; i++) {
    expect(weights.getX(i)).toBe(1);
    expect(indices.getX(i)).toBeLessThan(16);
  }
  avatar.dispose();
});

it('builds a 1.80-tall body rooted at the feet with no DOM canvas', () => {
  // No accessories: the body itself must be exactly the 2D collision box.
  const plain = createAvatar('villager', sharedAtlas());
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
  const hero = createAvatar('chenmo', sharedAtlas());
  hero.update(1 / 60);
  const heroBox = visibleBox(hero.root);
  expect(heroBox.min.y).toBeCloseTo(0, 2);
  expect(heroBox.max.y).toBeGreaterThan(1.8);
  expect(heroBox.max.y).toBeLessThan(1.98);
  hero.dispose();
});

it('places the feet exactly on the given block top', () => {
  const avatar = createAvatar('chenmo', sharedAtlas());
  avatar.setPosition(10, 2, 15);
  avatar.update(0);
  expect(avatar.root.position.y).toBe(2);
  expect(visibleBox(avatar.root).min.y).toBeCloseTo(2, 2);
  avatar.dispose();
});

it('turns toward the world facing, not the camera azimuth', () => {
  const avatar = createAvatar('chenmo', sharedAtlas());
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
  const a = createAvatar('chenmo', sharedAtlas());
  const b = createAvatar('chenmo', sharedAtlas());
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

it('flips the pixel rows like a canvas texture so the atlas is not upside down', () => {
  // DataTexture defaults flipY=false; CanvasTexture defaults true. The paint
  // routine writes top-down and the UV helper does `1 - py/H`, so without the
  // flip the face lands on the legs (seen on the real machine 2026-11-08).
  const shared = sharedAtlas();
  expect(shared.texture.flipY).toBe(true);
  expect(shared.texture.magFilter).toBe(THREE.NearestFilter);
  expect(shared.texture.generateMipmaps).toBe(false);
});

it('carries flat part colours in vertex colours so one material covers them', () => {
  // Hair, belt and the gourd used to need their own materials; they now ride in
  // the merged geometry's colour attribute against a white atlas swatch.
  const avatar = createAvatar('chenmo', sharedAtlas());
  const colors = avatar.mesh.geometry.getAttribute('color');
  expect(colors).toBeDefined();
  const seen = new Set<string>();
  for (let i = 0; i < colors.count; i++)
    seen.add(new THREE.Color(colors.getX(i), colors.getY(i), colors.getZ(i)).getHexString());
  // White (textured parts) plus 陈默's flat accessories: red bun band, the gourd,
  // the herb basket and the tool handle. The hair black comes from the atlas
  // tile, not from vertex colour, so it is deliberately absent here.
  expect(seen.size).toBeGreaterThan(1);
  expect(seen.has('ffffff')).toBe(true);
  expect(seen.has('c43c3c')).toBe(true); // belt band + gourd
  expect(seen.has('5a6b49')).toBe(true); // herb basket
  expect(seen.has('6d4a2f')).toBe(true); // tool handle
  avatar.dispose();
});

it('multiplies the wire tint instead of replacing colours', () => {
  // The wire sends 0xffffff for "no tint". Vertex colours carry the palette, so
  // material.color is a pure multiplier and white leaves everything untouched.
  const avatar = createAvatar('chenmo', sharedAtlas());
  const material = avatar.mesh.material as THREE.MeshLambertMaterial;
  avatar.setTint(0xffffff);
  expect(material.color.getHex()).toBe(0xffffff);
  avatar.setTint(0x000000);
  expect(material.color.getHex()).toBe(0);
  avatar.setTint(0xffffff);
  expect(material.color.getHex()).toBe(0xffffff);
  avatar.dispose();
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

it('ships no see-through silhouette until it can be done correctly', () => {
  // The 2D path marks occluded pixels with a same-depth GreaterDepth sprite,
  // which works because a sprite is flat. On a real mesh the body's own back
  // faces are behind its front faces, so the same comparison painted a yellow
  // shell around the whole avatar on the real machine. Better absent than wrong.
  const avatar = createAvatar('chenmo', sharedAtlas());
  expect('setXray' in avatar).toBe(false);
  const meshes: THREE.Mesh[] = [];
  avatar.root.traverse((node) => {
    if (node instanceof THREE.Mesh) meshes.push(node);
  });
  expect(meshes).toHaveLength(1);
  avatar.dispose();
});

it('disposes the geometry, materials and skeleton it created', () => {
  const avatar = createAvatar('chenmo', sharedAtlas());
  const disposed: string[] = [];
  avatar.mesh.geometry.addEventListener('dispose', () => disposed.push('geometry'));
  (avatar.mesh.material as THREE.Material).addEventListener('dispose', () => disposed.push('body'));
  avatar.dispose();
  expect(disposed).toContain('geometry');
  expect(disposed).toContain('body');
});
