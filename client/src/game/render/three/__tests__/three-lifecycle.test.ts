import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
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
