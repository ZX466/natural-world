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
