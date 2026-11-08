/** Complete opt-in world lifecycle. Phaser does not draw on this canvas. */
import type { WorldMirror } from '../../world-mirror';
import type { WorldGame } from '../../world-game';
import { effectiveHeight } from '../iso';
import { createTerrainAdapter, type TerrainAdapter } from './three-terrain-adapter';
import { loadTerrainAssets } from './three-assets';
import { worldOf } from './three-projection';
import { createActorLayer, type ActorLayer } from './three-actors';
import { createAvatarLighting } from './avatar3d';
import { protagonistAvatar3dFromSearch } from '../presentation';
import { loadActorAssets } from './three-actor-assets';
import { useUiStore } from '../../../store/uiStore';
import { WebAudioSynth } from '../../audio/synth';
import { worldAudio } from '../../audio';
import { createWeatherLayer } from './three-weather';
import { avoidCameraBlocks } from './three-camera-collision';
import { createWorldInput, type WorldInput } from './three-input';
import { screenRay, editFromRay, groundFromRay, WALK_HEIGHT } from './three-picking';
import { canStep } from '../../movement';
import type { VoxelRequestMessage } from '../../../net/protocol';
import { createVoxelCues, type VoxelCues } from './three-voxel-cues';
import type { MovePoint } from '../../movement';
import { pointVisible } from '../visibility';

export interface WorldActions {
  requestMove(x: number, y: number, gait?: 'walk' | 'run'): boolean;
  requestJump(x: number, y: number, gait?: 'walk' | 'run'): boolean;
  requestVoxel(
    action: VoxelRequestMessage['action'],
    x: number,
    y: number,
    material?: VoxelRequestMessage['material'],
  ): void;
}
export function createThreeWorld(
  parent: HTMLElement,
  mirror: WorldMirror,
  actions: WorldActions,
): WorldGame {
  const canvas = document.createElement('canvas');
  canvas.dataset.worldRenderer = 'three';
  canvas.style.cssText = 'display:block;width:100%;height:100%;touch-action:none';
  canvas.title = '右键或中键拖动转动视角，滚轮缩放';
  parent.append(canvas);
  const abort = new AbortController();
  const ready = new Set<() => void>();
  let disposed = false;
  let booted = false;
  let adapter: TerrainAdapter | null = null;
  let actors: ActorLayer | null = null;
  let input: WorldInput | null = null;
  let cues: VoxelCues | null = null;
  let hovered: MovePoint | null = null;
  let hoverKey = '';
  let hoverAt = -Infinity;
  let weather: ReturnType<typeof createWeatherLayer> | null = null;
  let actorAssets: Awaited<ReturnType<typeof loadActorAssets>> | null = null;
  let previousTime = 0;
  let releaseLighting: (() => void) | null = null;
  let audioContext: AudioContext | null = null;
  const audio = new WebAudioSynth(() => {
    audioContext ??= new AudioContext();
    return { context: audioContext, destination: audioContext.destination };
  });
  worldAudio.attach(audio);
  const releaseWorld = () => {
    releaseLighting?.();
    releaseLighting = null;
    cues?.dispose();
    cues = null;
    input?.dispose();
    input = null;
    weather?.dispose();
    weather = null;
    actors?.dispose();
    actors = null;
    actorAssets?.dispose();
    actorAssets = null;
    adapter?.dispose();
    adapter = null;
    worldAudio.detach(audio);
    const context = audioContext;
    audioContext = null;
    void context?.close().catch(() => {});
  };
  canvas.addEventListener(
    'pointerdown',
    () => {
      void worldAudio.unlock();
    },
    { signal: abort.signal },
  );
  window.addEventListener(
    'blur',
    () => {
      input?.cancel();
      worldAudio.suspend();
    },
    { signal: abort.signal },
  );
  let frame = 0;
  const size = {
    width: Math.max(1, parent.clientWidth),
    height: Math.max(1, parent.clientHeight),
    setParentSize(width: number, height: number) {
      if (disposed || width <= 0 || height <= 0) return;
      size.width = width;
      size.height = height;
      adapter?.resize(width, height);
    },
  };
  const render = (time: number) => {
    if (disposed) return;
    if (adapter) {
      adapter.sync();
      input?.tick();
      const delta = previousTime ? Math.min(100, time - previousTime) : 16;
      previousTime = time;
      actors?.update(time, delta, useUiStore.getState().speed, adapter.orbitPose.azimuth);
      const map = mirror.map;
      const actor = mirror.actors.get(mirror.protagonist ?? '');
      if (actor && map) {
        const motion = actors?.views.get(actor.rtoken)?.motion;
        const target = worldOf(motion?.x ?? actor.x, motion?.y ?? actor.y, map.w, map.h);
        target.y =
          (motion?.height ??
            effectiveHeight(
              actor.x,
              actor.y,
              adapter.heightOf,
              mirror.structures,
              mirror.voxelEdits,
            )) + 1.3;
        adapter.follow(target);
        avoidCameraBlocks(adapter.scene.camera, target, target.y - 1.3, map.w, map.h, (x, y) =>
          effectiveHeight(x, y, adapter!.heightOf, mirror.structures, mirror.voxelEdits),
        );
      }
      const pointer = input?.pointer;
      if (pointer && !input?.orbiting) {
        const key = `${pointer.x}:${pointer.y}:${size.width}:${size.height}:${mirror.terrainVersion}:${adapter.scene.camera.matrixWorld.elements.join(',')}`;
        if (key !== hoverKey && time - hoverAt >= 50) {
          const ray = screenRay(
            adapter.scene.camera,
            pointer.x,
            pointer.y,
            canvas.getBoundingClientRect(),
          );
          hovered = ray ? editFromRay(ray, adapter.scene.meshes) : null;
          hoverKey = key;
          hoverAt = time;
        }
      } else {
        hovered = null;
        hoverKey = '';
      }
      const ui = useUiStore.getState();
      const goal = input?.goal;
      const visibleGoal = goal && map && actor && pointVisible(map, actor, goal) ? goal : null;
      cues?.update(
        hovered && map && actor && pointVisible(map, actor, hovered) ? hovered : null,
        visibleGoal,
        ui.voxelMaterial,
        ui.voxelInventory,
        adapter.scene.camera,
        ui.wsStatus === 'open',
      );
      adapter.scene.render();
      actors?.labels(size.width, size.height, Date.now());
      weather?.update(
        size.width,
        size.height,
        time,
        useUiStore.getState().gameClock?.phase ?? 'day',
      );
      actors?.renderOverlay(adapter.scene.renderer);
    }
    frame = requestAnimationFrame(render);
  };
  const imagePromise = loadActorAssets(abort.signal).then((images) => {
    if (disposed || abort.signal.aborted) {
      images.dispose();
      throw new DOMException('Aborted', 'AbortError');
    }
    actorAssets = images;
    return images;
  });
  void Promise.all([loadTerrainAssets(abort.signal), imagePromise])
    .then(([assets, images]) => {
      if (disposed) return;
      adapter = createTerrainAdapter({ canvas, mirror, ...assets });
      adapter.resize(size.width, size.height);
      const protagonist3d = protagonistAvatar3dFromSearch(globalThis.location?.search ?? '');
      actors = createActorLayer(
        adapter.scene.scene,
        adapter.scene.camera,
        mirror,
        adapter.heightOf,
        images,
        { protagonist3d },
      );
      // Lambert materials need light; the terrain's baked vertex colours do not,
      // so this rig only ever affects the 3D avatars.
      if (protagonist3d) releaseLighting = createAvatarLighting(adapter.scene.scene);
      weather = createWeatherLayer(actors.overlay, mirror);
      cues = createVoxelCues(adapter.scene.scene, mirror, adapter.heightOf);
      const baseHeight = adapter.heightOf;
      const getHeight = (x: number, y: number) =>
        effectiveHeight(x, y, baseHeight, mirror.structures, mirror.voxelEdits);
      mirror.setHeightLookup(getHeight);
      const elevation = () => {
        const actor = mirror.actors.get(mirror.protagonist ?? '');
        return actor?.elevation ?? (actor ? getHeight(actor.x, actor.y) : WALK_HEIGHT);
      };
      const typing = () => {
        const active = document.activeElement as HTMLElement | null;
        return (
          !!active &&
          (['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName) ||
            active.isContentEditable ||
            !!active.closest('[contenteditable="true"],[contenteditable=""]'))
        );
      };
      input = createWorldInput(canvas, {
        move: (point) => actions.requestMove(point.x, point.y, input?.running ? 'run' : 'walk'),
        jump: (point) => actions.requestJump(point.x, point.y, input?.running ? 'run' : 'walk'),
        airborne: () => !!mirror.actors.get(mirror.protagonist ?? '')?.jump?.active,
        voxel: (action, point) =>
          actions.requestVoxel(
            action,
            point.x,
            point.y,
            action === 'place' ? useUiStore.getState().voxelMaterial : undefined,
          ),
        pickEdit: (x, y) => {
          const ray = screenRay(adapter!.scene.camera, x, y, canvas.getBoundingClientRect());
          return ray ? editFromRay(ray, adapter!.scene.meshes) : null;
        },
        pickGround: (x, y) => {
          const ray = screenRay(adapter!.scene.camera, x, y, canvas.getBoundingClientRect());
          return ray && mirror.map ? groundFromRay(ray, mirror.map, getHeight, elevation()) : null;
        },
        blocked: (point) => mirror.map?.collision[point.y * mirror.map.w + point.x] !== 1,
        hero: () => mirror.actors.get(mirror.protagonist ?? '') ?? null,
        step: (point) => {
          const actor = mirror.actors.get(mirror.protagonist ?? '');
          return !!(
            actor &&
            mirror.map &&
            canStep(mirror.map, actor, point, getHeight, elevation())
          );
        },
        enabled: () =>
          useUiStore.getState().wsStatus === 'open' &&
          !!mirror.map &&
          mirror.actors.has(mirror.protagonist ?? ''),
        typing,
        epoch: () => `${mirror.resetCount}:${mirror.voxelSnapshotVersion}`,
        revision: () => mirror.terrainVersion + mirror.locomotionRevision,
        azimuth: () => adapter!.orbitPose.azimuth,
        rotate: (dx, dy) => adapter!.rotate(dx, dy),
        zoom: (delta) => adapter!.zoom(delta),
        error: (message) => useUiStore.getState().setVoxelError(message),
      });
      window.addEventListener(
        'keydown',
        (event) => {
          if (!event.repeat && !typing()) void worldAudio.unlock();
        },
        { signal: abort.signal },
      );

      booted = true;
      for (const callback of ready) callback();
      ready.clear();
      frame = requestAnimationFrame(render);
    })
    .catch((error: unknown) => {
      if (!disposed) {
        abort.abort();
        releaseWorld();
        useUiStore.getState().setVoxelError('这会儿看不清四周。');
        console.error('World renderer could not start', error);
      }
    });
  return {
    get isBooted() {
      return booted;
    },
    scale: size,
    events: {
      once(_event, listener) {
        if (booted) listener();
        else ready.add(listener);
      },
      off(_event, listener) {
        ready.delete(listener);
      },
    },
    destroy(removeCanvas) {
      if (disposed) return;
      disposed = true;
      abort.abort();
      cancelAnimationFrame(frame);
      ready.clear();
      releaseWorld();
      if (removeCanvas) canvas.remove();
    },
  };
}
