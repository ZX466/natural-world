import { expect, it, vi } from 'vitest';

async function setup() {
  vi.resetModules();
  const sent: Record<string, unknown>[] = [];
  const callbacks: Record<string, unknown> = {};
  const connection = { worldReady: false };
  const state = {
    wsStatus: 'open',
    voxelError: null as string | null,
    setVoxelError: vi.fn((message: string | null) => {
      state.voxelError = message;
    }),
    setWsStatus: vi.fn(),
    setVoxelInventory: vi.fn(),
    setLoadPending: vi.fn(),
    setLoadError: vi.fn(),
    setControlError: vi.fn(),
    setPlans: vi.fn(),
  };
  vi.doMock('../../store/uiStore', () => ({ useUiStore: { getState: () => state } }));
  vi.doMock('../clock', () => ({ worldClock: { start: vi.fn(), stop: vi.fn(), apply: vi.fn() } }));
  vi.doMock('../../net/worldApi', () => ({
    fetchWorldMap: vi.fn(() => new Promise(() => {})),
    assembleCollision: vi.fn(),
    assembleGround: vi.fn(),
  }));
  vi.doMock('../../net/ws', () => ({
    setControlStateSink: vi.fn(),
    WsClient: class {
      get worldReady() {
        return connection.worldReady;
      }
      constructor(_url: string, _mirror: unknown, sink: Record<string, unknown>) {
        Object.assign(callbacks, sink);
      }
      connect() {}
      send(frame: Record<string, unknown>) {
        sent.push(frame);
      }
    },
  }));
  const { runtime, worldMirror } = await import('../runtime');
  runtime.start();
  worldMirror.setMap({ w: 5, h: 5, tileset: 'grid', collision: new Uint8Array(25).fill(1) });
  worldMirror.protagonist = 'hero';
  worldMirror.applySnapshot(
    [
      {
        rtoken: 'hero',
        x: 1,
        y: 2,
        facing: 's',
        sprite: 'protagonist',
        anim: 'idle',
        elevation: 1,
      },
    ],
    [],
  );
  worldMirror.setHeightLookup((x) => (x === 2 ? 2 : x === 3 ? 3 : 1));
  return { runtime, worldMirror, sent, callbacks, connection, state };
}

it('requires this connection snapshot before jump, forwards only intent, and leaves pose authoritative', async () => {
  const { runtime, worldMirror, connection, sent } = await setup();
  expect(runtime.requestJump(2, 2)).toBe(false);
  expect(sent).toEqual([]);
  connection.worldReady = true;
  expect(runtime.requestJump(2, 2)).toBe(true);
  expect(sent).toEqual([
    { type: 'jump_request', channel: 'render', target_x: 2, target_y: 2, gait: 'walk' },
  ]);
  expect(worldMirror.actors.get('hero')).toMatchObject({ x: 1, y: 2, elevation: 1 });
  expect(worldMirror.actors.get('hero')?.jump).toBeUndefined();
});

it('bounds jump reach, refuses water and malformed goals, and admits a bank top without making it walkable', async () => {
  const { runtime, worldMirror, connection, sent } = await setup();
  connection.worldReady = true;
  expect(runtime.requestJump(3, 2)).toBe(false);
  expect(runtime.requestJump(3, 2, 'run')).toBe(true);
  worldMirror.setHeightLookup(() => 0);
  expect(runtime.requestJump(1, 2)).toBe(false);
  worldMirror.setHeightLookup(() => 1);
  worldMirror.map!.collision[2 * 5 + 2] = 0;
  expect(runtime.requestJump(2, 2)).toBe(true);
  expect(worldMirror.map!.collision[12]).toBe(0);
  for (const x of [NaN, Infinity, -1, 1.5, 5]) expect(runtime.requestJump(x, 2)).toBe(false);
  expect(sent).toHaveLength(2);
});

it('sends explicit gait on same-height movement, supports stops on high blocks, and freezes ground intent in flight', async () => {
  const { runtime, worldMirror, connection, sent } = await setup();
  expect(runtime.requestMove(1, 3, 'walk')).toBe(false);
  connection.worldReady = true;
  expect(runtime.requestMove(1, 3, 'walk')).toBe(true);
  expect(runtime.requestMove(2, 2, 'run')).toBe(false);
  worldMirror.applyActorDeltas([{ rtoken: 'hero', x: 2, elevation: 2 }]);
  worldMirror.map!.collision[12] = 0;
  expect(runtime.requestMove(2, 3, 'run')).toBe(true);
  expect(runtime.requestMove(2, 2, 'walk')).toBe(true);
  expect(sent.map((frame) => frame.gait)).toEqual(['walk', 'run', 'walk']);
  worldMirror.applyActorDeltas([
    {
      rtoken: 'hero',
      jump: {
        rtoken: 'flight',
        start_x: 2,
        start_y: 2,
        goal_x: 1,
        goal_y: 2,
        start_height: 2,
        target_height: 1,
        progress: 0.5,
        active: true,
        duration: 0.6,
        arc_height: 1.5,
      },
    },
  ]);
  expect(runtime.requestMove(2, 3, 'run')).toBe(false);
  expect(runtime.requestJump(1, 2)).toBe(false);
  expect(sent).toHaveLength(3);
});

it('makes jump rejection visible and retries possible without inventing a landing', async () => {
  const { worldMirror, callbacks, state } = await setup();
  const before = worldMirror.locomotionRevision;
  (callbacks.onError as (msg: unknown) => void)({
    ref: 'jump_request',
    code: 'bad_target',
    message: 'internal',
  });
  expect(state.voxelError).toBe('那处跳不过去。');
  expect(worldMirror.locomotionRevision).toBe(before + 1);
  expect(worldMirror.actors.get('hero')?.jump).toBeUndefined();
});
