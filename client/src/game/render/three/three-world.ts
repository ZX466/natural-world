/** Complete opt-in world lifecycle. Phaser does not draw on this canvas. */
import type { WorldMirror } from '../../world-mirror';
import type { WorldGame } from '../../world-game';
import { effectiveHeight } from '../iso';
import { createTerrainAdapter, type TerrainAdapter } from './three-terrain-adapter';
import { loadTerrainAssets } from './three-assets';
import { worldOf } from './three-projection';
import { createActorLayer, type ActorLayer } from './three-actors';
import { loadActorAssets } from './three-actor-assets';
import { useUiStore } from '../../../store/uiStore';
import { WebAudioSynth } from '../../audio/synth';
import { worldAudio } from '../../audio';
import { createWeatherLayer } from './three-weather';
import { avoidCameraBlocks } from './three-camera-collision';

export function createThreeWorld(parent: HTMLElement, mirror: WorldMirror): WorldGame {
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
  let weather: ReturnType<typeof createWeatherLayer> | null = null;
  let actorAssets: Awaited<ReturnType<typeof loadActorAssets>> | null = null;
  let previousTime = 0;
  let audioContext: AudioContext | null = null;
  const audio = new WebAudioSynth(() => {
    audioContext ??= new AudioContext();
    return { context: audioContext, destination: audioContext.destination };
  });
  worldAudio.attach(audio);
  const releaseWorld = () => {
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
      drag = null;
      worldAudio.suspend();
    },
    { signal: abort.signal },
  );
  let frame = 0;
  let drag: { id: number; x: number; y: number } | null = null;
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
  canvas.addEventListener('contextmenu', (event) => event.preventDefault(), {
    signal: abort.signal,
  });
  canvas.addEventListener(
    'pointerdown',
    (event) => {
      if (event.button !== 1 && event.button !== 2) return;
      event.preventDefault();
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY };
      canvas.setPointerCapture(event.pointerId);
    },
    { signal: abort.signal },
  );
  canvas.addEventListener(
    'pointermove',
    (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      adapter?.rotate(event.clientX - drag.x, event.clientY - drag.y);
      drag.x = event.clientX;
      drag.y = event.clientY;
    },
    { signal: abort.signal },
  );
  canvas.addEventListener(
    'pointerup',
    () => {
      drag = null;
    },
    { signal: abort.signal },
  );
  canvas.addEventListener(
    'pointercancel',
    () => {
      drag = null;
    },
    { signal: abort.signal },
  );
  canvas.addEventListener(
    'wheel',
    (event) => {
      event.preventDefault();
      adapter?.zoom(event.deltaY);
    },
    { signal: abort.signal, passive: false },
  );

  const render = (time: number) => {
    if (disposed) return;
    if (adapter) {
      adapter.sync();
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
      actors = createActorLayer(
        adapter.scene.scene,
        adapter.scene.camera,
        mirror,
        adapter.heightOf,
        images,
      );
      weather = createWeatherLayer(actors.overlay, mirror);
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
