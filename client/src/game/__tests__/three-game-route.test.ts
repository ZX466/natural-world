import { afterEach, expect, it, vi } from 'vitest';
const data = vi.hoisted(() => ({
  three: { isBooted: true },
  phaser: vi.fn(function () {
    return { events: { on() {} } };
  }),
}));
vi.mock('phaser', () => ({
  default: { Scene: class {}, Game: data.phaser, AUTO: 0, Scale: { RESIZE: 0 } },
}));
vi.mock('../render/three/three-world', () => ({ createThreeWorld: () => data.three }));
vi.mock('../runtime', () => ({ runtime: {} }));
afterEach(() => vi.unstubAllGlobals());

it('hands the whole world to three without creating a Phaser overlay canvas', async () => {
  vi.stubGlobal('location', { search: '?terrain=three' });
  const { createGame } = await import('../main');
  const game = createGame({} as HTMLElement, {} as Parameters<typeof createGame>[1]);
  expect(game).toBe(data.three);
  expect(data.phaser).not.toHaveBeenCalled();
});

it('boots the three world when the URL says nothing at all', async () => {
  // three is the default since the 2026-11-07 acceptance; a bare URL must not
  // fall back to Phaser.
  vi.stubGlobal('location', { search: '' });
  const { createGame } = await import('../main');
  const game = createGame({} as HTMLElement, {} as Parameters<typeof createGame>[1]);
  expect(game).toBe(data.three);
  expect(data.phaser).not.toHaveBeenCalled();
});

it('still routes to Phaser when ?terrain=phaser is asked for explicitly', async () => {
  vi.stubGlobal('location', { search: '?terrain=phaser' });
  const { createGame } = await import('../main');
  const game = createGame({} as HTMLElement, {} as Parameters<typeof createGame>[1]);
  expect(game).not.toBe(data.three);
  expect(data.phaser).toHaveBeenCalledTimes(1);
});
