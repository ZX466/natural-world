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

it('marks a dug cell on the flat renderer with a dark inset', () => {
  const { internal, mirror, graphics } = rendererScene('?renderer=flat');
  mirror.applyVoxelEdits([{ x: 0, y: 0, action: 'dig', gid: 1 }]);
  internal.redrawMap();
  // 4 grid cells + earth fill + dark inset for the dug cell.
  expect(graphics.fillRect).toHaveBeenCalledTimes(6);
  expect(graphics.fillStyle).toHaveBeenCalledWith(0x3f3020, expect.any(Number));
});

it('keeps the placed strip on the flat renderer instead of a dig scar', () => {
  const { internal, mirror, graphics } = rendererScene('?renderer=flat');
  mirror.applyVoxelEdits([{ x: 0, y: 0, action: 'place', gid: 0 }]);
  internal.redrawMap();
  expect(graphics.fillStyle).toHaveBeenCalledWith(0x6b4f2a, 1);
  expect(graphics.fillStyle.mock.calls.filter((call) => call[0] === 0x3f3020)).toHaveLength(0);
});

it('defaults to iso and routes terrain/structures without flat rectangles', () => {
  const { internal, graphics, iso, mirror } = rendererScene('?renderer=iso');
  internal.redrawMap();
  internal.syncStructures();
  expect(internal.renderMode).toBe('iso');
  expect(iso.redraw).toHaveBeenCalledWith(
    mirror.map,
    mirror.structures,
    mirror.voxelEdits,
    mirror.terrainVersion,
  );
  expect(iso.sync).toHaveBeenCalledWith(
    mirror.map,
    mirror.structures,
    mirror.voxelEdits,
    mirror.terrainVersion,
  );
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

it('shows committed voxel walls and dug earth in flat without keeping future collision', () => {
  const { internal, mirror, graphics } = rendererScene('?renderer=flat');
  mirror.applyVoxelEdits([{ x: 0, y: 0, action: 'place', gid: 0 }]);
  internal.redrawMap();
  expect(graphics.fillStyle).toHaveBeenLastCalledWith(0x6b4f2a, 1);
  expect(graphics.fillRect).toHaveBeenLastCalledWith(13, 0, 3, 16);
  expect(mirror.map!.collision[0]).toBe(0);
  mirror.applyVoxelEdits([], true);
  internal.redrawMap();
  expect(mirror.map!.collision[0]).toBe(1);
  expect(graphics.fillRect).toHaveBeenLastCalledWith(16, 16, 15, 15);
});
