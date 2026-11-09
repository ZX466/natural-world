import { afterEach, expect, it, vi } from 'vitest';
import { WorldMirror } from '../../../world-mirror';
import type { WorldInputPorts } from '../three-input';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  for (const module of [
    '../three-assets',
    '../three-actor-assets',
    '../three-terrain-adapter',
    '../three-actors',
    '../three-weather',
    '../three-voxel-cues',
    '../three-input',
    '../avatar3d',
    '../../../audio',
    '../../../audio/synth',
    '../../../../store/uiStore',
  ])
    vi.doUnmock(module);
});

it('wires gait, authoritative flight and elevated steps into the native controller', async () => {
  vi.resetModules();
  const mirror = new WorldMirror();
  mirror.setMap({ w: 4, h: 4, tileset: 'grid', collision: new Uint8Array(16) });
  mirror.protagonist = 'hero';
  mirror.applySnapshot(
    [
      {
        rtoken: 'hero',
        x: 1,
        y: 1,
        facing: 's',
        sprite: 'protagonist',
        anim: 'idle',
        elevation: 2,
      },
    ],
    [],
  );
  let ports!: WorldInputPorts;
  const controller = { running: false, dispose: vi.fn() };
  const requestMove = vi.fn(() => true),
    requestJump = vi.fn(() => true);
  vi.doMock('../three-assets', () => ({ loadTerrainAssets: () => Promise.resolve({}) }));
  vi.doMock('../three-actor-assets', () => ({
    loadActorAssets: () => Promise.resolve({ dispose() {} }),
  }));
  vi.doMock('../three-terrain-adapter', () => ({
    createTerrainAdapter: () => ({
      heightOf: (x: number) => (x === 3 ? 1 : 2),
      resize() {},
      dispose() {},
      scene: { scene: {}, camera: {} },
    }),
  }));
  vi.doMock('../three-actors', () => ({ createActorLayer: () => ({ overlay: {}, dispose() {} }) }));
  // 3D is the default now, so the lighting rig is built on every boot; the
  // mocked scene has no `add`, so stub the rig out with the actor layer.
  vi.doMock('../avatar3d', () => ({ createAvatarLighting: () => () => {} }));
  vi.doMock('../three-weather', () => ({ createWeatherLayer: () => ({ dispose() {} }) }));
  vi.doMock('../three-voxel-cues', () => ({ createVoxelCues: () => ({ dispose() {} }) }));
  vi.doMock('../three-input', () => ({
    createWorldInput: (_canvas: unknown, wired: WorldInputPorts) => {
      ports = wired;
      return controller;
    },
  }));
  vi.doMock('../../../audio', () => ({ worldAudio: { attach() {}, detach() {}, unlock() {} } }));
  vi.doMock('../../../audio/synth', () => ({ WebAudioSynth: class {} }));
  vi.doMock('../../../../store/uiStore', () => ({
    useUiStore: { getState: () => ({ wsStatus: 'open' }) },
  }));
  class Canvas extends EventTarget {
    dataset = {};
    style = {};
    title = '';
    remove() {}
  }
  vi.stubGlobal('document', { createElement: () => new Canvas(), activeElement: null });
  vi.stubGlobal('window', new EventTarget());
  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn(() => 1),
  );
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const { createThreeWorld } = await import('../three-world');
  const game = createThreeWorld(
    { append() {}, clientWidth: 800, clientHeight: 600 } as unknown as HTMLElement,
    mirror,
    { requestMove, requestJump, requestVoxel() {} },
  );
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(game.isBooted).toBe(true);
  expect(mirror.heightAt(1, 1)).toBe(2);
  expect(ports.step({ x: 2, y: 1 })).toBe(true);
  expect(ports.step({ x: 3, y: 1 })).toBe(false);
  expect(ports.blocked({ x: 2, y: 1 })).toBe(true);
  ports.move({ x: 2, y: 1 });
  controller.running = true;
  ports.move({ x: 2, y: 1 });
  ports.jump!({ x: 3, y: 1 });
  expect(requestMove.mock.calls).toEqual([
    [2, 1, 'walk'],
    [2, 1, 'run'],
  ]);
  expect(requestJump.mock.calls).toEqual([[3, 1, 'run']]);
  const before = ports.revision();
  mirror.applyActorDeltas([
    {
      rtoken: 'hero',
      jump: {
        rtoken: 'flight',
        start_x: 1,
        start_y: 1,
        goal_x: 2,
        goal_y: 1,
        start_height: 2,
        target_height: 2,
        progress: 0,
        active: true,
        duration: 0.6,
        arc_height: 1.5,
      },
    },
  ]);
  expect(ports.airborne!()).toBe(true);
  expect(ports.revision()).toBeGreaterThan(before);
  game.destroy(true);
  expect(controller.dispose).toHaveBeenCalledTimes(1);
  expect(mirror.heightAt(1, 1)).toBe(2);
});

it.each(['failure', 'cancel'])('disposes ready actor textures once on %s', async (mode) => {
  vi.resetModules();
  let settle!: () => void;
  const terrain = new Promise((resolve, reject) => {
    settle = () => (mode === 'cancel' ? resolve({}) : reject(new Error('missing terrain')));
  });
  const images = { texture: vi.fn(), text: vi.fn(), dispose: vi.fn() };
  vi.doMock('../three-assets', () => ({ loadTerrainAssets: () => terrain }));
  vi.doMock('../three-actor-assets', () => ({ loadActorAssets: () => Promise.resolve(images) }));
  vi.doMock('../../../audio', () => ({
    worldAudio: { attach() {}, detach() {}, suspend() {}, unlock() {} },
  }));
  vi.doMock('../../../audio/synth', () => ({ WebAudioSynth: class {} }));
  class Canvas extends EventTarget {
    dataset = {};
    style = {};
    title = '';
    remove = vi.fn();
  }
  const canvas = new Canvas();
  vi.stubGlobal('document', { createElement: () => canvas });
  vi.stubGlobal('window', new EventTarget());
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  vi.spyOn(console, 'error').mockImplementation(() => {});
  const { createThreeWorld } = await import('../three-world');
  const game = createThreeWorld(
    { append() {}, clientWidth: 800, clientHeight: 600 } as unknown as HTMLElement,
    {} as Parameters<typeof createThreeWorld>[1],
    { requestMove: () => false, requestJump: () => false, requestVoxel() {} },
  );
  await Promise.resolve();
  if (mode === 'cancel') game.destroy(true);
  settle();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(images.dispose).toHaveBeenCalledTimes(1);
  game.destroy(true);
  expect(images.dispose).toHaveBeenCalledTimes(1);
  expect(canvas.remove).toHaveBeenCalledTimes(1);
});
