/** Complete opt-in world lifecycle. Phaser does not draw on this canvas. */
import type { WorldMirror } from '../../world-mirror';
import type { WorldGame } from '../../world-game';
import { effectiveHeight } from '../iso';
import { createTerrainAdapter, type TerrainAdapter } from './three-terrain-adapter';
import { loadTerrainAssets } from './three-assets';
import { worldOf } from './three-projection';
import { createActorLayer, type ActorLayer } from './three-actors';
import { createAvatarLighting } from './avatar3d';
import { avatars3dFromSearch } from '../presentation';
import { STAND_STRUCTURE_KEY } from './landmark-lre';
import { mountLandmark, type LandmarkMount } from './landmark-lre-mount';
import { loadActorAssets } from './three-actor-assets';
import { useUiStore } from '../../../store/uiStore';
import { WebAudioSynth } from '../../audio/synth';
import { worldAudio } from '../../audio';
import { createWeatherLayer } from './three-weather';
import { avoidCameraBlocks, cameraAzimuth } from './three-camera-collision';
import { createAvatarOcclusion } from './three-avatar-occlusion';
import { createWorldInput, type WorldInput } from './three-input';
import { screenRay, editFromRay, groundFromRay, WALK_HEIGHT } from './three-picking';
import { canStep } from '../../movement';
import { cachedRenderHeightLookup, type RenderHeightLookup } from '../cell-appearance';
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
  let occlusion: ReturnType<typeof createAvatarOcclusion> | null = null;
  let input: WorldInput | null = null;
  let cues: VoxelCues | null = null;
  let hovered: MovePoint | null = null;
  let hoverKey = '';
  let hoverAt = -Infinity;
  let weather: ReturnType<typeof createWeatherLayer> | null = null;
  let actorAssets: Awaited<ReturnType<typeof loadActorAssets>> | null = null;
  /** 逻辑高度 → 渲染高度（土坎 1 画成 2）。首帧 boot 之后才有值。 */
  let drawHeight: RenderHeightLookup | null = null;
  let previousTime = 0;
  let releaseLighting: (() => void) | null = null;
  let landmark: LandmarkMount | null = null;
  /** 已为哪张地图尝试过挂载：没锚点/没 shader 就不重试；换地图
   *  （重连/分支切换拿到新 `map` 对象）时才重算。 */
  let landmarkMap: WorldMirror['map'] = null;
  let audioContext: AudioContext | null = null;
  const audio = new WebAudioSynth(() => {
    audioContext ??= new AudioContext();
    return { context: audioContext, destination: audioContext.destination };
  });
  worldAudio.attach(audio);
  const releaseWorld = () => {
    occlusion?.dispose();
    occlusion = null;
    releaseLighting?.();
    releaseLighting = null;
    landmark?.dispose();
    landmark = null;
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
  const ensureLandmark = (): void => {
    if (!adapter) return;
    const map = mirror.map;
    if (map === null) return; // 快照还没到，下一帧再试
    // 同一张地图只处理一次（挂上了就留着，没锚点也不再试）；换了地图
    // （重连/切分支拿到新 `map` 对象）才重算，否则会留在旧坐标。
    if (landmarkMap === map) return;
    landmark?.dispose();
    landmark = null;
    landmarkMap = map;
    // 锚点来自世界数据：占地面在 collision 里已经不可走，模型必须立在同一矩形上。
    landmark = mountLandmark({
      scene: adapter.scene.scene,
      renderer: adapter.scene.renderer,
      mapW: map.w,
      mapH: map.h,
      anchor: map.structures?.[STAND_STRUCTURE_KEY],
      host: parent,
    });
  };
  const render = (time: number) => {
    if (disposed) return;
    if (adapter) {
      adapter.sync();
      input?.tick();
      const delta = previousTime ? Math.min(100, time - previousTime) : 16;
      previousTime = time;
      const ui = useUiStore.getState();
      actors?.update(time, delta, ui.speed, cameraAzimuth(adapter.scene.camera), ui.paused);
      ensureLandmark();
      // 地标用墙钟秒推进 shader 与粒子；它纯表现，不参与世界状态（C5 不受影响）。
      landmark?.update(delta / 1000, time / 1000);
      const map = mirror.map;
      const actor = mirror.actors.get(mirror.protagonist ?? '');
      if (actor && map) {
        const motion = actors?.views.get(actor.rtoken)?.motion;
        const target = worldOf(motion?.x ?? actor.x, motion?.y ?? actor.y, map.w, map.h);
        target.y =
          (motion?.height ??
            drawHeight!(
              actor.x,
              actor.y,
              effectiveHeight(
                actor.x,
                actor.y,
                adapter.heightOf,
                mirror.structures,
                mirror.voxelEdits,
              ),
            )) + 1.3;
        adapter.follow(target);
        // 相机避让用**实际渲染高度**：土坎画成 2 格矮墙，按逻辑 1 算会穿进去。
        // `renderHeightOf` 直接读这一帧交给场景的 `TerrainCell.h`（= `drawH`），
        // 所以新增任何「只抬高渲染」的格子都自动跟上，不必在这里再列一遍。
        avoidCameraBlocks(
          adapter.scene.camera,
          target,
          target.y - 1.3,
          map.w,
          map.h,
          adapter.renderHeightOf,
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
      if (landmark) {
        // 66 个子部件逐帧射线太贵，和上面的体素悬停同一套节流与门控：
        // 指针离开画布或开始转视角时清掉高亮，否则会一直亮着。
        if (pointer && !input?.orbiting) {
          const rect = canvas.getBoundingClientRect();
          landmark.hover(
            (2 * (pointer.x - rect.left)) / rect.width - 1,
            1 - (2 * (pointer.y - rect.top)) / rect.height,
            adapter.scene.camera,
            time,
            pointer,
          );
        } else {
          landmark.hover(Number.NaN, Number.NaN, adapter.scene.camera, time);
        }
      }
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
      if (actors)
        occlusion?.render(
          adapter.scene.renderer,
          adapter.scene.scene,
          adapter.scene.camera,
          actors.views,
          mirror.protagonist,
        );
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
      // 逻辑高度（服务端权威，土坎=1）与渲染高度（土坎画成 2 格矮墙）是两件事。
      // 渲染/拾取/脚底一律读 drawHeight；判定（碰撞、跳跃落点、`heightAt`）读 getHeight。
      const baseHeight = adapter.heightOf;
      const getHeight = (x: number, y: number) =>
        effectiveHeight(x, y, baseHeight, mirror.structures, mirror.voxelEdits);
      drawHeight = cachedRenderHeightLookup(() => mirror.map, getHeight);
      mirror.setHeightLookup(getHeight);
      const avatars3d = avatars3dFromSearch(globalThis.location?.search ?? '');
      occlusion = avatars3d ? createAvatarOcclusion() : null;
      actors = createActorLayer(
        adapter.scene.scene,
        adapter.scene.camera,
        mirror,
        adapter.heightOf,
        images,
        // 非空断言：上一行刚赋值。角色层只在 boot 成功后创建。
        { avatars3d, drawHeight: drawHeight! },
      );
      // Lambert materials need light; the terrain's baked vertex colours do not,
      // so this rig only ever affects the 3D avatars.
      // Lambert 角色与地标的 StandardMaterial 都需要光照；地形是 BasicMaterial
      // 烤死顶点色，不受影响。所以这套灯与 3D 开关无关，一律建。
      releaseLighting = createAvatarLighting(adapter.scene.scene);
      // 地标要读 `mirror.map` 的 `_structures` 锚点，而世界常在快照之前就 boot 完
      // （`worldReady` 才发首个快照）。所以真正挂载交给首帧的 `ensureLandmark()`
      // ——否则地标会永远不建，且没有任何报错。
      weather = createWeatherLayer(actors.overlay, mirror);
      cues = createVoxelCues(adapter.scene.scene, mirror, adapter.heightOf, drawHeight!);
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
          // 平面用**逻辑**高度：土坎不可走，站在旁边时周围地面画在 1，
          // 按渲染高度反投影会整体偏一格。
          return ray && mirror.map ? groundFromRay(ray, mirror.map, getHeight, elevation()) : null;
        },
        pickStructure: (x, y) => {
          if (!landmark) return false;
          const rect = canvas.getBoundingClientRect();
          return landmark.pick(
            (2 * (x - rect.left)) / rect.width - 1,
            1 - (2 * (y - rect.top)) / rect.height,
            adapter!.scene.camera,
          );
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
        azimuth: () => cameraAzimuth(adapter!.scene.camera),
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
