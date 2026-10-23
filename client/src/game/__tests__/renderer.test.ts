import { afterEach, expect, it, vi } from 'vitest';
import { WorldMirror } from '../world-mirror';
vi.mock('phaser', () => ({ default: { Scene: class {} } }));
import { WorldScene } from '../scenes/WorldScene';

afterEach(() => vi.unstubAllGlobals());

function rendererScene(search: string) {
  vi.stubGlobal('location', { search });
  const mirror = new WorldMirror();
  mirror.setMap({ w: 2, h: 2, tileset: 'grid', collision: new Uint8Array([1, 0, 1, 1]) });
  const scene = new WorldScene(mirror);
  const graphics = { clear: vi.fn(), fillStyle: vi.fn(), fillRect: vi.fn() };
  const iso = { redraw: vi.fn(), sync: vi.fn() };
  Object.assign(scene, { mapLayer: graphics, structureLayer: graphics, isoTerrain: iso });
  const internal = scene as unknown as {
    redrawMap(): void;
    syncStructures(): void;
    renderMode: string;
  };
  return { scene, internal, mirror, graphics, iso };
}

it('keeps the explicit flat grid and original structure phase drawing', () => {
  const { internal, mirror, graphics, iso } = rendererScene('?renderer=flat');
  internal.redrawMap();
  expect(internal.renderMode).toBe('flat');
  expect(graphics.fillRect).toHaveBeenCalledTimes(4);
  expect(graphics.fillRect).toHaveBeenLastCalledWith(16, 16, 15, 15);
  mirror.applyStructures([{ rtoken: 'house', x: 1, y: 1, phase: 'built' }]);
  internal.syncStructures();
  expect(graphics.fillStyle).toHaveBeenLastCalledWith(0x6b4f2a, 0.92);
  expect(iso.redraw).not.toHaveBeenCalled();
  expect(iso.sync).not.toHaveBeenCalled();
});

it('defaults to iso and routes terrain/structures without flat rectangles', () => {
  const { internal, graphics, iso, mirror } = rendererScene('?renderer=iso');
  internal.redrawMap();
  internal.syncStructures();
  expect(internal.renderMode).toBe('iso');
  expect(iso.redraw).toHaveBeenCalledWith(mirror.map, mirror.structures);
  expect(iso.sync).toHaveBeenCalledWith(mirror.map, mirror.structures);
  expect(graphics.fillRect).not.toHaveBeenCalled();
  expect(rendererScene('').internal.renderMode).toBe('iso');
  expect(rendererScene('?renderer=unknown').internal.renderMode).toBe('iso');
});

it('preloads the height table alongside the current tileset', () => {
  const { scene } = rendererScene('?renderer=iso');
  const load = { image: vi.fn(), json: vi.fn(), spritesheet: vi.fn() };
  Object.assign(scene, { load });
  scene.preload();
  expect(load.json).toHaveBeenCalledWith('linhe-height', '/assets/tilesets/linhe-height.json');
  expect(load.image).toHaveBeenCalledWith('god-town-16', '/assets/tilesets/god-town-16.png');
});
