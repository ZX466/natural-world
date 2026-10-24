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
