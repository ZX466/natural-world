/** Complete opt-in world lifecycle. Phaser does not draw on this canvas. */
import type { WorldMirror } from '../../world-mirror';
import type { WorldGame } from '../../world-game';
import { effectiveHeight } from '../iso';
import { createTerrainAdapter, type TerrainAdapter } from './three-terrain-adapter';
import { loadTerrainAssets } from './three-assets';
import { worldOf } from './three-projection';

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

  const render = () => {
    if (disposed) return;
    if (adapter) {
      adapter.sync();
      const map = mirror.map;
      const actor = mirror.actors.get(mirror.protagonist ?? '');
      if (actor && map) {
        const target = worldOf(actor.x, actor.y, map.w, map.h);
        target.y =
          effectiveHeight(
            actor.x,
            actor.y,
            adapter.heightOf,
            mirror.structures,
            mirror.voxelEdits,
          ) + 1.3;
        adapter.follow(target);
      }
      adapter.scene.render();
    }
    frame = requestAnimationFrame(render);
  };
  void loadTerrainAssets(abort.signal)
    .then((assets) => {
      if (disposed) return;
      adapter = createTerrainAdapter({ canvas, mirror, ...assets });
      adapter.resize(size.width, size.height);
      booted = true;
      for (const callback of ready) callback();
      ready.clear();
      frame = requestAnimationFrame(render);
    })
    .catch((error: unknown) => {
      if (!disposed) console.error('World renderer could not start', error);
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
      adapter?.dispose();
      if (removeCanvas) canvas.remove();
    },
  };
}
