import * as THREE from 'three';
import { expect, it, vi } from 'vitest';
import { createAvatarOcclusion } from '../three-avatar-occlusion';

function fixture() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xabcdef);
  const camera = new THREE.PerspectiveCamera();
  const actor = () => {
    const mesh = new THREE.SkinnedMesh(new THREE.BoxGeometry(), new THREE.MeshLambertMaterial());
    const root = new THREE.Group().add(mesh);
    const sprite = new THREE.Sprite();
    const shadow = new THREE.Mesh();
    const silhouette = new THREE.Sprite();
    scene.add(root, sprite, shadow, silhouette);
    return { avatar: { root, mesh }, sprite, shadow, silhouette };
  };
  const hero = actor();
  const npc = actor();
  const wall = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial());
  const mist = new THREE.Mesh(
    new THREE.BoxGeometry(),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.3 }),
  );
  const hidden = new THREE.Mesh();
  hidden.visible = false;
  scene.add(wall, mist, hidden);
  const actors = new Map([
    ['hero', hero],
    ['npc', npc],
  ]);
  const calls: { objects: THREE.Object3D[]; material: THREE.Material | null }[] = [];
  const renderer = {
    autoClear: true,
    clearDepth: vi.fn(),
    render: vi.fn(() => {
      expect(scene.background).toBeNull();
      expect(renderer.autoClear).toBe(false);
      const objects: THREE.Object3D[] = [];
      scene.traverseVisible((o) => {
        if ('material' in o) objects.push(o);
      });
      calls.push({ objects, material: scene.overrideMaterial });
    }),
  };
  return {
    scene,
    camera,
    hero,
    npc,
    wall,
    mist,
    hidden,
    actors,
    calls,
    renderer,
    pass: createAvatarOcclusion(),
  };
}

it('uses only solid environment depth, then only the occluded hero mesh', () => {
  const f = fixture();
  const background = f.scene.background;
  const heroMaterial = f.hero.avatar.mesh.material;
  f.pass.render(f.renderer as never, f.scene, f.camera, f.actors, 'hero');
  expect(f.renderer.clearDepth).toHaveBeenCalledOnce();
  expect(f.calls).toHaveLength(2);
  expect(f.calls[0]!.objects).toEqual([f.wall]);
  expect(f.calls[0]!.material).toMatchObject({ colorWrite: false, depthWrite: true });
  expect(f.calls[1]!.objects).toEqual([f.hero.avatar.mesh]);
  expect(f.calls[1]!.material).toMatchObject({
    depthFunc: THREE.GreaterDepth,
    depthWrite: false,
    transparent: true,
  });
  expect(f.hero.avatar.mesh.material).toBe(heroMaterial);
  expect(f.scene.background).toBe(background);
  expect(f.scene.overrideMaterial).toBeNull();
  expect(f.renderer.autoClear).toBe(true);
  expect(f.npc.avatar.root.visible).toBe(true);
  expect(f.mist.visible).toBe(true);
  expect(f.hidden.visible).toBe(false);
});

it.each([1, 2])('restores render state and visibility if pass %i fails', (failedPass) => {
  const f = fixture();
  const original = new THREE.MeshNormalMaterial();
  f.scene.overrideMaterial = original;
  f.renderer.autoClear = false;
  let calls = 0;
  f.renderer.render.mockImplementation(() => {
    if (++calls === failedPass) throw new Error('GPU failure');
  });
  expect(() => f.pass.render(f.renderer as never, f.scene, f.camera, f.actors, 'hero')).toThrow(
    'GPU failure',
  );
  expect(f.scene.overrideMaterial).toBe(original);
  expect(f.scene.background).toBeInstanceOf(THREE.Color);
  expect(f.renderer.autoClear).toBe(false);
  expect(f.npc.avatar.root.visible).toBe(true);
  expect(f.hidden.visible).toBe(false);
});

it('skips absent or hidden 3D heroes and owns only its two pass materials', () => {
  const f = fixture();
  f.pass.render(f.renderer as never, f.scene, f.camera, f.actors, null);
  f.hero.avatar.root.visible = false;
  f.pass.render(f.renderer as never, f.scene, f.camera, f.actors, 'hero');
  expect(f.renderer.render).not.toHaveBeenCalled();
  f.hero.avatar.root.visible = true;
  f.pass.render(f.renderer as never, f.scene, f.camera, f.actors, 'hero');
  const disposers = f.calls.map((c) => vi.spyOn(c.material!, 'dispose'));
  const original = vi.spyOn(f.hero.avatar.mesh.material as THREE.Material, 'dispose');
  f.pass.dispose();
  expect(disposers.every((d) => d.mock.calls.length === 1)).toBe(true);
  expect(original).not.toHaveBeenCalled();
});
