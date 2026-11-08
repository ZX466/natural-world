/** World billboards plus projected, collision-avoiding name/bubble sprites. */
import * as THREE from 'three';
import type { WorldMirror } from '../../world-mirror';
import type { HeightLookup } from '../iso';
import { effectiveHeight } from '../iso';
import {
  CHENMO_SHEET,
  GOD_SHEET,
  GOD_SPRITE_KEYS,
  VILLAGER_SHEET,
  facingRow,
  walkFrameFor,
} from '../actors';
import { advanceMotion, cameraFacing, type ActorMotion } from '../actor-motion';
import {
  assignStackOffsets,
  layoutNameLabels,
  manhattan,
  shouldShowNameLabel,
  type NameLabelCandidate,
} from '../presentation';
import { placeBubble, selectBubbleNames } from '../bubbles';
import { worldOf } from './three-projection';
import { visibleActorTokens } from '../visibility';
import { flightTarget, gaitCadenceMs } from '../../locomotion';
import { createAvatar, createAvatarAtlas, phaseFromAnimClock, type Avatar3D } from './avatar3d';

export interface TextImage {
  texture: THREE.Texture;
  width: number;
  height: number;
}
export interface ActorAssets {
  texture(key: string): THREE.Texture | undefined;
  text(value: string, bubble: boolean): TextImage;
}
export interface ActorView {
  readonly key: string;
  /** The billboard. With a 3D avatar this stays as the label anchor only and its
   *  material is switched off, so every screen-space layout rule keeps working. */
  readonly sprite: THREE.Sprite;
  readonly shadow: THREE.Mesh;
  /** Present only for the protagonist while the 3D trial flag is on. */
  avatar: Avatar3D | null;
  silhouette: THREE.Sprite | null;
  label: THREE.Sprite | null;
  name: string | undefined;
  motion: ActorMotion;
}

export interface ActorLayerOptions {
  /** Swap the protagonist's billboard for a segmented voxel avatar. Trial only:
   *  everyone else keeps the shipped 2D sheets until the batching work lands. */
  readonly protagonist3d?: boolean;
}

export function createActorLayer(
  scene: THREE.Scene,
  camera: THREE.PerspectiveCamera,
  mirror: WorldMirror,
  heightOf: HeightLookup,
  assets: ActorAssets,
  options: ActorLayerOptions = {},
) {
  const protagonist3d = options.protagonist3d === true;
  // One atlas for the whole world: 19 presets in a single 512×256 texture, so
  // every 3D actor shares one material map instead of generating its own.
  const avatarAtlas = protagonist3d ? createAvatarAtlas() : null;
  const views = new Map<string, ActorView>();
  const bubbles = new Map<string, THREE.Sprite>();
  const overlay = new THREE.Scene();
  const overlayCamera = new THREE.OrthographicCamera(0, 1, 1, 0, -10, 10);
  const shadowGeometry = new THREE.CircleGeometry(0.28, 16);
  let reset = '';

  const destroyText = (sprite: THREE.Sprite) => {
    overlay.remove(sprite);
    sprite.material.map?.dispose();
    sprite.material.dispose();
  };
  const textSprite = (text: string, bubble: boolean) => {
    const image = assets.text(text, bubble);
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: image.texture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
      }),
    );
    sprite.center.set(0.5, 0);
    sprite.scale.set(image.width, image.height, 1);
    sprite.renderOrder = bubble ? 20 : 10;
    sprite.userData.text = text;
    overlay.add(sprite);
    return sprite;
  };
  const destroyView = (view: ActorView) => {
    scene.remove(view.sprite, view.shadow);
    if (view.avatar) {
      scene.remove(view.avatar.root);
      view.avatar.dispose();
    }
    if (view.silhouette) {
      scene.remove(view.silhouette);
      view.silhouette.material.dispose();
    }
    view.sprite.material.map?.dispose();
    view.sprite.material.dispose();
    (view.shadow.material as THREE.Material).dispose();
    if (view.label) destroyText(view.label);
  };
  const clear = () => {
    for (const view of views.values()) destroyView(view);
    views.clear();
    for (const bubble of bubbles.values()) destroyText(bubble);
    bubbles.clear();
  };

  const update = (time: number, delta: number, speed: number, azimuth: number) => {
    const map = mirror.map;
    if (!map) {
      clear();
      return;
    }
    const token = `${mirror.resetCount}:${mirror.voxelSnapshotVersion}`;
    if (token !== reset) {
      clear();
      reset = token;
    }
    const stacks = assignStackOffsets(mirror.actors.values());
    const shown = visibleActorTokens(mirror);
    for (const [rtoken, actor] of mirror.actors) {
      const requested = rtoken === mirror.protagonist ? 'protagonist' : actor.sprite;
      const key = assets.texture(requested) ? requested : 'villager';
      let view = views.get(rtoken);
      if (view && view.key !== key) {
        destroyView(view);
        views.delete(rtoken);
        view = undefined;
      }
      const height =
        actor.elevation ??
        effectiveHeight(actor.x, actor.y, heightOf, mirror.structures, mirror.voxelEdits);
      // The server always reports facing "s", so it cannot drive the sheet row.
      // This layer feeds `advanceMotion` tile-space coordinates, where a one-tile
      // step dominates any height change — inference from those deltas is correct,
      // so leave `facing` unset and let the buffer derive it.
      const flight = flightTarget(actor.jump, (x, y, z) => ({ x, y, z }));
      const target = {
        x: actor.x,
        y: actor.y,
        height,
        cadenceMs: gaitCadenceMs(actor.gait),
        ...(flight ? { flight } : {}),
      } as const;
      if (!view) {
        const texture = assets.texture(key)?.clone();
        if (!texture) continue;
        texture.needsUpdate = true;
        const sprite = new THREE.Sprite(
          new THREE.SpriteMaterial({
            map: texture,
            alphaTest: 0.2,
            transparent: true,
            depthWrite: true,
          }),
        );
        sprite.center.set(0.5, 0);
        const fauna = key.startsWith('fauna_');
        sprite.scale.set(fauna ? 0.8 : 0.9, fauna ? 0.8 : 1.8, 1);
        const shadow = new THREE.Mesh(
          shadowGeometry,
          new THREE.MeshBasicMaterial({
            color: 0x141510,
            opacity: 0.22,
            transparent: true,
            depthWrite: false,
          }),
        );
        shadow.rotation.x = -Math.PI / 2;
        scene.add(sprite, shadow);
        // The trial swaps only the protagonist. `key` stays 'protagonist' so the
        // rest of the layer (labels, silhouette, stack offsets) is untouched.
        const avatar =
          avatarAtlas && rtoken === mirror.protagonist ? createAvatar('chenmo', avatarAtlas) : null;
        if (avatar) {
          scene.add(avatar.root);
          // The billboard becomes an invisible anchor: `labels` projects
          // `sprite.position` upward by `scale.y`, so the layout keeps working
          // without a second anchor path.
          sprite.material.visible = false;
        }
        view = {
          key,
          sprite,
          shadow,
          avatar,
          silhouette: null,
          name: undefined,
          label: null,
          motion: advanceMotion(undefined, target, time, delta, speed),
        };
        views.set(rtoken, view);
      }
      if (view.name !== actor.name) {
        if (view.label) destroyText(view.label);
        view.label = actor.name ? textSprite(actor.name, false) : null;
        view.name = actor.name;
      }
      view.motion = advanceMotion(view.motion, target, time, delta, speed);
      const world = worldOf(view.motion.x, view.motion.y, map.w, map.h);
      const offset = stacks.get(rtoken) ?? { dx: 0, dy: 0 };
      view.sprite.position.set(
        world.x + offset.dx / 16,
        view.motion.height,
        world.z + offset.dy / 16,
      );
      if (view.avatar) {
        // The replay buffer already decided where and how fast the actor is
        // drawn; the avatar only reads those results, so 3D and 2D never drift.
        view.avatar.setPosition(
          view.sprite.position.x,
          view.sprite.position.y,
          view.sprite.position.z,
        );
        view.avatar.setFacing(view.motion.facing);
        view.avatar.setPhase(phaseFromAnimClock(view.motion.animClock));
        view.avatar.setAnim(
          view.motion.airborne
            ? 'jump'
            : view.motion.animClock >= 0
              ? (actor.gait ?? 'walk')
              : 'idle',
        );
        view.avatar.setJumpProgress(actor.jump?.active ? actor.jump.progress : null);
        view.avatar.setTint(actor.tint ?? 0xffffff);
        view.avatar.update(delta / 1000);
      }
      view.shadow.position.set(
        view.sprite.position.x,
        (view.motion.airborne
          ? effectiveHeight(
              Math.floor(view.motion.x + 0.5),
              Math.floor(view.motion.y + 0.5),
              heightOf,
              mirror.structures,
              mirror.voxelEdits,
            )
          : view.motion.height) + 0.008,
        view.sprite.position.z,
      );
      view.sprite.material.color.setHex(actor.tint ?? 0xffffff);
      view.sprite.material.opacity = key.startsWith('fauna_') && actor.anim === 'rest' ? 0.5 : 1;
      view.sprite.visible = view.shadow.visible = shown.has(rtoken);
      if (view.avatar) {
        view.avatar.root.visible = shown.has(rtoken);
        // The billboard is the label anchor: it must keep a position but never
        // paint, so it never draws a second copy of the hero.
        view.sprite.visible = false;
      }
      if (rtoken === mirror.protagonist && !view.silhouette && !view.avatar) {
        // A faint second pass marks only the player's own occluded pixels.
        // Other people retain ordinary depth testing and never get this pass.
        view.silhouette = new THREE.Sprite(
          new THREE.SpriteMaterial({
            map: view.sprite.material.map,
            alphaTest: 0.2,
            transparent: true,
            opacity: 0.42,
            depthTest: true,
            depthWrite: false,
            depthFunc: THREE.GreaterDepth,
          }),
        );
        view.silhouette.center.copy(view.sprite.center);
        view.silhouette.renderOrder = 5;
        scene.add(view.silhouette);
      }
      if (view.silhouette) {
        view.silhouette.visible = shown.has(rtoken) && rtoken === mirror.protagonist;
        view.silhouette.position.copy(view.sprite.position);
        view.silhouette.scale.copy(view.sprite.scale);
      }
      if (!key.startsWith('fauna_') && !view.avatar) {
        const sheet =
          key === 'protagonist'
            ? CHENMO_SHEET
            : GOD_SPRITE_KEYS.includes(key)
              ? GOD_SHEET
              : VILLAGER_SHEET;
        const frame = walkFrameFor(
          sheet,
          facingRow(sheet, cameraFacing(view.motion.facing, azimuth)),
          view.motion.animClock,
        );
        const texture = view.sprite.material.map!;
        const image = texture.image as { width: number; height: number };
        texture.repeat.set(16 / image.width, 32 / image.height);
        texture.offset.set(
          ((frame % sheet.cols) * 16) / image.width,
          1 - ((Math.floor(frame / sheet.cols) + 1) * 32) / image.height,
        );
      }
    }
    for (const [rtoken, view] of views)
      if (!mirror.actors.has(rtoken)) {
        destroyView(view);
        views.delete(rtoken);
      }
  };

  const labels = (width: number, height: number, now: number) => {
    overlayCamera.left = 0;
    overlayCamera.right = width;
    overlayCamera.top = height;
    overlayCamera.bottom = 0;
    overlayCamera.updateProjectionMatrix();
    mirror.pruneBubbles(now);
    const hero = mirror.actors.get(mirror.protagonist ?? '');
    const nameCounts = new Map<string, number>();
    for (const actor of mirror.actors.values())
      if (actor.name) nameCounts.set(actor.name, (nameCounts.get(actor.name) ?? 0) + 1);
    const anchors = new Map<string, { x: number; y: number; view: ActorView }>();
    const candidates: NameLabelCandidate[] = [];
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
    for (const [rtoken, view] of views) {
      if (view.label) view.label.visible = false;
      // A 3D avatar's billboard is a hidden anchor, so its own visibility says
      // nothing about whether the actor is on screen.
      const onScreen = view.avatar ? view.avatar.root.visible : view.sprite.visible;
      if (!onScreen) continue;
      const actor = mirror.actors.get(rtoken)!;
      const head = view.sprite.position
        .clone()
        .addScaledVector(up, view.sprite.scale.y)
        .project(camera);
      if (head.z < -1 || head.z > 1 || Math.abs(head.x) > 1 || Math.abs(head.y) > 1) continue;
      const x = ((head.x + 1) * width) / 2;
      const y = ((1 - head.y) * height) / 2;
      if (actor.name && (!anchors.has(actor.name) || rtoken === mirror.protagonist))
        anchors.set(actor.name, { x, y, view });
      const distance = hero ? manhattan(hero, actor) : Infinity;
      if (view.label && (rtoken === mirror.protagonist || shouldShowNameLabel(distance)))
        candidates.push({
          rtoken,
          x,
          y: y - 6,
          width: view.label.scale.x,
          height: view.label.scale.y,
          isProtagonist: rtoken === mirror.protagonist,
          distance,
        });
    }
    for (const [rtoken, point] of layoutNameLabels(candidates)) {
      const label = views.get(rtoken)!.label!;
      label.position.set(point.x, height - point.y, 0);
      label.visible = true;
    }
    const selected = selectBubbleNames(
      // The wire identifies a bubble by name only; ambiguity must not reveal
      // a hidden speaker by attaching their words to a visible namesake.
      new Map(
        [...mirror.bubbles].filter(([name]) => anchors.has(name) && nameCounts.get(name) === 1),
      ),
      hero?.name,
    );
    for (const [name, bubble] of bubbles)
      if (!selected.includes(name)) {
        destroyText(bubble);
        bubbles.delete(name);
      }
    const placed: { x: number; y: number; width: number; height: number }[] = [];
    for (const name of selected) {
      const content = mirror.bubbles.get(name)!.text;
      let sprite = bubbles.get(name);
      if (sprite && sprite.userData.text !== content) {
        destroyText(sprite);
        bubbles.delete(name);
        sprite = undefined;
      }
      if (!sprite) {
        sprite = textSprite(content, true);
        bubbles.set(name, sprite);
      }
      const anchor = anchors.get(name)!;
      const box = placeBubble(
        { x: anchor.x, y: anchor.y - 24, width: sprite.scale.x, height: sprite.scale.y },
        placed,
      );
      sprite.position.set(box.x, height - box.y, 0);
      placed.push(box);
    }
  };
  return {
    views,
    bubbles,
    overlay,
    update,
    labels,
    renderOverlay(renderer: THREE.WebGLRenderer) {
      const auto = renderer.autoClear;
      renderer.autoClear = false;
      renderer.clearDepth();
      renderer.render(overlay, overlayCamera);
      renderer.autoClear = auto;
    },
    dispose() {
      clear();
      shadowGeometry.dispose();
      avatarAtlas?.dispose();
    },
  };
}
export type ActorLayer = ReturnType<typeof createActorLayer>;
