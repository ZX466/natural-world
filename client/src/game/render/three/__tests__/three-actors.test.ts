import * as THREE from 'three';
import { expect, it, vi } from 'vitest';
import { WorldMirror } from '../../../world-mirror';
import { createActorLayer } from '../three-actors';

function setup(protagonist3d = false) {
  const mirror = new WorldMirror();
  mirror.setMap({ w: 5, h: 6, tileset: 'grid', collision: new Uint8Array(30).fill(1) });
  mirror.protagonist = 'hero';
  mirror.applySnapshot(
    [
      {
        rtoken: 'hero',
        x: 2,
        y: 3,
        facing: 's',
        sprite: 'protagonist',
        anim: 'idle',
        name: '陈默',
      },
      {
        rtoken: 'other',
        x: 2,
        y: 0,
        facing: 'n',
        sprite: 'god_villager_ali',
        anim: 'idle',
        name: '阿梨',
      },
    ],
    [],
  );
  const camera = new THREE.PerspectiveCamera(60, 1, 0.05, 300);
  camera.position.set(0, 3, 9);
  camera.lookAt(0, 2, 0);
  camera.updateMatrixWorld(true);
  const scene = new THREE.Scene();
  const texture = new THREE.DataTexture(new Uint8Array(272 * 256 * 4), 272, 256);
  const layer = createActorLayer(
    scene,
    camera,
    mirror,
    () => 1,
    {
      texture: () => texture,
      text: (value: string) => ({
        texture: new THREE.Texture(),
        width: value.length * 12,
        height: 20,
      }),
    },
    { protagonist3d },
  );
  return { mirror, camera, scene, texture, layer };
}

it('uses billboards with feet on world height and projection-dependent apparent size', () => {
  const { layer, camera } = setup();
  layer.update(0, 16, 1, 0);
  const hero = layer.views.get('hero')!.sprite;
  const other = layer.views.get('other')!.sprite;
  expect(hero).toBeInstanceOf(THREE.Sprite);
  expect(hero.center.y).toBe(0);
  expect(hero.position.y).toBeCloseTo(1);
  expect(hero.scale.y).toBe(1.8);
  expect(other.scale.y).toBe(1.8);
  const apparentHeight = (sprite: THREE.Sprite) => {
    const feet = sprite.position.clone().project(camera);
    const top = sprite.position
      .clone()
      .add(new THREE.Vector3(0, 1.8, 0).applyQuaternion(camera.quaternion))
      .project(camera);
    return top.y - feet.y;
  };
  expect(apparentHeight(hero)).toBeGreaterThan(apparentHeight(other));
});

it('stands at authoritative elevation even when terrain presentation has not refreshed', () => {
  const { layer, mirror } = setup();
  mirror.applyActorDeltas([{ rtoken: 'hero', elevation: 3, gait: 'walk' }]);
  layer.update(0, 16, 1, 0);
  const hero = layer.views.get('hero')!;
  expect(hero.sprite.position.y).toBe(3);
  expect(hero.motion.height).toBe(3);
});

it('renders the server flight through the replay buffer while the shadow stays on support', () => {
  const { layer, mirror } = setup();
  layer.update(0, 16, 1, 0);
  const jump = {
    rtoken: 'flight',
    start_x: 2,
    start_y: 3,
    goal_x: 3,
    goal_y: 3,
    start_height: 1,
    target_height: 2,
    progress: 0,
    active: true,
    duration: 0.6,
    arc_height: 1.5,
  };
  mirror.applyActorDeltas([{ rtoken: 'hero', elevation: 1, gait: 'run', jump }]);
  layer.update(100, 100, 1, 0);
  mirror.applyActorDeltas([{ rtoken: 'hero', jump: { ...jump, progress: 0.5 } }]);
  layer.update(400, 300, 1, 0);
  mirror.applyActorDeltas([
    { rtoken: 'hero', x: 3, elevation: 2, jump: { ...jump, progress: 1, active: false } },
  ]);
  layer.update(700, 100, 1, 0);
  const hero = layer.views.get('hero')!;
  expect(hero.motion.airborne).toBe(true);
  expect(hero.sprite.position.y).toBeGreaterThan(2);
  expect(hero.shadow.position.y).toBeCloseTo(1.008);
  expect(hero.motion.animClock).toBe(-1);
  layer.update(1100, 100, 1, 0);
  expect(hero.sprite.position.y).toBe(2);
  expect(hero.motion.airborne).toBe(false);
});

it('updates frame UVs, removes departed actors and drops old snapshot interpolation', () => {
  const { layer, mirror, scene } = setup();
  layer.update(0, 16, 1, 0);
  const hero = layer.views.get('hero')!;
  mirror.applyActorDeltas([{ rtoken: 'hero', x: 3 }]);
  layer.update(100, 16, 1, 0);
  // The renderer draws an instant one replay delay in the past, so x=3 arrives
  // at t=100 but only becomes visible after the delay has elapsed.
  layer.update(300, 200, 1, 0);
  const midway = layer.views.get('hero')!.motion.x;
  expect(midway).toBeGreaterThan(2);
  expect(midway).toBeLessThan(3);
  expect(hero.sprite.material.map!.repeat.x).toBeCloseTo(1 / 17);
  mirror.applyActorDeltas([{ rtoken: 'other', op: 'remove' }]);
  layer.update(320, 16, 1, 0);
  expect(layer.views.has('other')).toBe(false);
  mirror.applyVoxelEdits([], true);
  layer.update(500, 180, 1, 0);
  expect(layer.views.get('hero')!.motion.x).toBe(3);
  const dispose = vi.spyOn(layer.views.get('hero')!.sprite.material, 'dispose');
  layer.dispose();
  expect(scene.children).toHaveLength(0);
  expect(dispose).toHaveBeenCalled();
});

it('leaves every actor on the shipped billboard path when the trial flag is off', () => {
  const { layer } = setup(false);
  layer.update(0, 16, 1, 0);
  for (const view of layer.views.values()) expect(view.avatar).toBeNull();
  expect(layer.views.get('hero')!.sprite.visible).toBe(true);
});

it('swaps only the protagonist for a 3D avatar and keeps the label anchored', () => {
  const { layer } = setup(true);
  layer.update(0, 16, 1, 0);
  layer.labels(800, 800, 1000);
  const hero = layer.views.get('hero')!;
  const other = layer.views.get('other')!;
  expect(hero.avatar).not.toBeNull();
  expect(other.avatar).toBeNull();
  // The billboard survives as a hidden anchor so the shared screen-space label
  // layout keeps projecting from `sprite.position` + `scale.y`.
  expect(hero.sprite.visible).toBe(false);
  expect(hero.avatar!.root.position.y).toBeCloseTo(hero.sprite.position.y);
  expect(hero.avatar!.root.visible).toBe(true);
  expect(hero.label!.visible).toBe(true);
  // The 3D hero no longer runs the sheet UV math, but the NPC still does.
  // repeat.x is one 16px cell over the atlas width, not one over the column count.
  expect(other.sprite.material.map!.repeat.x).toBeCloseTo(16 / 272);
});

it('hides the 3D protagonist together with its label when it is occluded', () => {
  const { layer, mirror } = setup(true);
  const collision = new Uint8Array(400).fill(1);
  collision[212] = 0;
  mirror.setMap({ w: 20, h: 20, tileset: 'grid', collision });
  mirror.applySnapshot(
    [
      {
        rtoken: 'hero',
        x: 10,
        y: 10,
        facing: 's',
        sprite: 'protagonist',
        anim: 'idle',
        name: '陈默',
      },
      {
        rtoken: 'other',
        x: 11,
        y: 10,
        facing: 's',
        sprite: 'villager',
        anim: 'idle',
        name: '近人',
      },
    ],
    [],
  );
  layer.update(0, 16, 1, 0);
  layer.labels(800, 800, 1000);
  expect(layer.views.get('hero')!.avatar!.root.visible).toBe(true);
  // A 3D actor has no sheet silhouette pass; the outline takes its place.
  expect(layer.views.get('hero')!.silhouette).toBeNull();
});

it('projects names and active bubbles with shared screen-space layout', () => {
  const { layer, mirror } = setup();
  mirror.setBubble('陈默', '先去走走。', 2000, 1000);
  layer.update(0, 16, 1, 0);
  layer.labels(800, 800, 1000);
  expect(layer.views.get('hero')!.label!.visible).toBe(true);
  expect(layer.bubbles.size).toBe(1);
  mirror.pruneBubbles(4000);
  layer.labels(800, 800, 4000);
  expect(layer.bubbles.size).toBe(0);
});

it('hides a blocked actor, shadow, name and bubble together and refreshes after a wall edit', () => {
  const { layer, mirror } = setup();
  const collision = new Uint8Array(400).fill(1);
  collision[212] = 0;
  mirror.setMap({ w: 20, h: 20, tileset: 'grid', collision });
  mirror.applySnapshot(
    [
      {
        rtoken: 'hero',
        x: 10,
        y: 10,
        facing: 's',
        sprite: 'protagonist',
        anim: 'idle',
        name: '陈默',
      },
      { rtoken: 'near', x: 11, y: 10, facing: 's', sprite: 'villager', anim: 'idle', name: '近人' },
      {
        rtoken: 'hidden',
        x: 14,
        y: 10,
        facing: 's',
        sprite: 'villager',
        anim: 'idle',
        name: '墙后',
      },
    ],
    [],
  );
  mirror.setBubble('墙后', '不该显示的墙后话语', 5000, 1000);
  layer.update(0, 16, 1, 0);
  layer.labels(800, 800, 1000);
  expect(layer.views.get('near')!.sprite.visible).toBe(true);
  const hidden = layer.views.get('hidden')!;
  expect(hidden.sprite.visible).toBe(false);
  expect(hidden.shadow.visible).toBe(false);
  expect(hidden.label!.visible).toBe(false);
  expect(layer.bubbles.has('墙后')).toBe(false);
  expect(layer.views.get('hero')!.silhouette?.visible).toBe(true);
  mirror.applyVoxelEdits([{ x: 12, y: 10, action: 'dig', gid: 7, height: 1, material: 'earth' }]);
  layer.update(100, 16, 1, 0);
  layer.labels(800, 800, 1000);
  expect(hidden.sprite.visible).toBe(true);
  expect(layer.bubbles.has('墙后')).toBe(true);
});

it('does not attribute a hidden speakers bubble to a visible actor with the same name', () => {
  const { layer, mirror } = setup();
  const collision = new Uint8Array(400).fill(1);
  collision[212] = 0;
  mirror.setMap({ w: 20, h: 20, tileset: 'grid', collision });
  mirror.applySnapshot(
    [
      {
        rtoken: 'hero',
        x: 10,
        y: 10,
        facing: 's',
        sprite: 'protagonist',
        anim: 'idle',
        name: '陈默',
      },
      {
        rtoken: 'near',
        x: 11,
        y: 10,
        facing: 's',
        sprite: 'villager',
        anim: 'idle',
        name: '同名者',
      },
      {
        rtoken: 'hidden',
        x: 14,
        y: 10,
        facing: 's',
        sprite: 'villager',
        anim: 'idle',
        name: '同名者',
      },
    ],
    [],
  );
  mirror.setBubble('同名者', '来源无法区分的墙后话语', 5000, 1000);
  layer.update(0, 16, 1, 0);
  layer.labels(800, 800, 1000);
  expect(layer.views.get('near')!.sprite.visible).toBe(true);
  expect(layer.bubbles.has('同名者')).toBe(false);
});
