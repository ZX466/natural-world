import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => vi.unstubAllGlobals());

async function setup() {
  vi.resetModules();
  const callbacks: Record<string, unknown> = {},
    sent: Record<string, unknown>[] = [],
    pending: ((value: unknown) => void)[] = [];
  const state = {
    wsStatus: 'connecting',
    voxelInventory: null as { earth: number } | null,
    voxelError: null as string | null,
    setWsStatus: vi.fn((s: string) => {
      state.wsStatus = s;
    }),
    setVoxelInventory: vi.fn((n: { earth: number } | null) => {
      state.voxelInventory = n;
    }),
    setVoxelError: vi.fn((message: string | null) => {
      state.voxelError = message;
    }),
  };
  vi.doMock('../../store/uiStore', () => ({ useUiStore: { getState: () => state } }));
  vi.doMock('../clock', () => ({ worldClock: { start: vi.fn(), stop: vi.fn(), apply: vi.fn() } }));
  vi.doMock('../../net/worldApi', () => ({
    fetchWorldMap: vi.fn(() => new Promise((resolve) => pending.push(resolve))),
    assembleCollision: (w: number, h: number) => new Uint8Array(w * h).fill(1),
    assembleGround: (w: number, h: number) => new Uint16Array(w * h).fill(7),
  }));
  vi.doMock('../../net/ws', () => ({
    setControlStateSink: vi.fn(),
    WsClient: class {
      constructor(_url: string, _mirror: unknown, cb: Record<string, unknown>) {
        Object.assign(callbacks, cb);
      }
      connect() {}
      send(frame: Record<string, unknown>) {
        sent.push(frame);
      }
    },
  }));
  const module = await import('../runtime');
  module.runtime.start();
  return { ...module, callbacks, sent, pending, state };
}

it('sends only the declared voxel fields and refuses disconnected editing', async () => {
  const { runtime, callbacks, sent, state } = await setup();
  (callbacks.onStatus as (s: string) => void)('open');
  runtime.requestVoxel('place', 2, 3);
  expect(sent).toEqual([{ type: 'voxel_request', channel: 'render', action: 'place', x: 2, y: 3 }]);
  (callbacks.onStatus as (s: string) => void)('closed');
  runtime.requestVoxel('dig_start', 2, 3);
  expect(sent).toHaveLength(1);
  expect(state.voxelError).toBeTruthy();
});

it('uses voxel_state inventory for the HUD without turning it into impulses', async () => {
  const { callbacks, state, sent } = await setup();
  (callbacks.onVoxelState as (value: unknown) => void)({ dig: null, inventory: { earth: 3 } });
  expect(state.voxelInventory).toEqual({ earth: 3 });
  expect(sent).toEqual([]);
});

it('refreshes the current map on full snapshots and drops old asynchronous responses', async () => {
  const { callbacks, pending, worldMirror } = await setup();
  (callbacks.onSnapshot as () => void)();
  (callbacks.onSnapshot as () => void)();
  expect(pending).toHaveLength(3);
  pending[2]!({ w: 4, h: 4, tileset: 'current-branch', chunks: [] });
  await Promise.resolve();
  await Promise.resolve();
  expect(worldMirror.map?.tileset).toBe('current-branch');
  pending[0]!({ w: 4, h: 4, tileset: 'old-branch', chunks: [] });
  await Promise.resolve();
  await Promise.resolve();
  expect(worldMirror.map?.tileset).toBe('current-branch');
});

it('refuses disconnected movement with a diegetic HUD message and no frame', async () => {
  const { runtime, state, sent } = await setup();
  expect(runtime.requestMove(2, 1)).toBe(false);
  expect(sent).toEqual([]);
  expect(state.voxelError).toBe('这会儿走不了。');
});

it('locally rejects walls and disconnected islands and sends only declared movement fields', async () => {
  const { runtime, worldMirror, state, sent } = await setup();
  state.wsStatus = 'open';
  const collision = new Uint8Array(25).fill(1);
  for (let y = 0; y < 5; y++) collision[y * 5 + 2] = 0;
  worldMirror.setMap({ w: 5, h: 5, tileset: 'grid', collision });
  worldMirror.protagonist = 'hero';
  worldMirror.actors.set('hero', {
    rtoken: 'hero',
    x: 0,
    y: 2,
    facing: 'e',
    sprite: 'protagonist',
    anim: 'idle',
  });
  expect(runtime.requestMove(2, 2)).toBe(false);
  expect(state.voxelError).toBe('那处挡着路。');
  expect(runtime.requestMove(4, 2)).toBe(false);
  expect(state.voxelError).toBe('那处绕不过去。');
  expect(sent).toEqual([]);
  expect(runtime.requestMove(1, 2)).toBe(true);
  expect(sent).toEqual([{ type: 'move_request', channel: 'render', target_x: 1, target_y: 2 }]);
  expect(state.voxelError).toBeNull();
  // Collision changes happen in place; a new reachable opening must be visible.
  collision[12] = 1;
  expect(runtime.requestMove(4, 2)).toBe(true);
});

it('does not find a diagonal route through two touching wall corners', async () => {
  const { runtime, worldMirror, state, sent } = await setup();
  state.wsStatus = 'open';
  worldMirror.setMap({ w: 2, h: 2, tileset: 'grid', collision: new Uint8Array([1, 0, 0, 1]) });
  worldMirror.protagonist = 'hero';
  worldMirror.actors.set('hero', {
    rtoken: 'hero',
    x: 0,
    y: 0,
    facing: 'e',
    sprite: 'protagonist',
    anim: 'idle',
  });
  expect(runtime.requestMove(1, 1)).toBe(false);
  expect(sent).toEqual([]);
});
