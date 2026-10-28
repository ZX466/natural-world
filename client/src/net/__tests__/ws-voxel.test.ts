import { expect, it, vi } from 'vitest';
import { WorldMirror } from '../../game/world-mirror';
import { WsClient } from '../ws';

function scene() {
  const mirror = new WorldMirror();
  mirror.setMap({
    w: 4,
    h: 4,
    tileset: 'grid',
    collision: new Uint8Array(16).fill(1),
    ground: new Uint16Array(16).fill(7),
  });
  const onVoxelState = vi.fn();
  const client = new WsClient('ws://127.0.0.1:8000/ws', mirror, {
    onStatus: vi.fn(),
    onSnapshot: vi.fn(),
    onDelta: vi.fn(),
    onVoxelState,
  });
  const dispatch = (client as unknown as { dispatch(raw: string): void }).dispatch.bind(client);
  const send = (type: string, body: Record<string, unknown>) =>
    dispatch(JSON.stringify({ type, channel: 'render', v: '1.13', ws_seq: 1, ...body }));
  return { mirror, onVoxelState, send };
}

it('consumes voxel state only after validating progress and whole nonnegative stock', () => {
  const { mirror, onVoxelState, send } = scene();
  send('voxel_state', { dig: { x: 2, y: 1, progress: 0.4 }, inventory: { earth: 2 } });
  expect(mirror.voxelDig).toEqual({ x: 2, y: 1, progress: 0.4 });
  expect(onVoxelState).toHaveBeenCalledTimes(1);
  send('voxel_state', { dig: null, inventory: { earth: -1 } });
  send('voxel_state', { dig: { x: 2, y: 1, progress: 2 }, inventory: { earth: 3 } });
  expect(onVoxelState).toHaveBeenCalledTimes(1);
  expect(mirror.voxelDig?.progress).toBe(0.4);
});

it('merges edit deltas and clears stale edits on a full snapshot even when omitted', () => {
  const { mirror, send } = scene();
  send('state_delta', { actors: [], voxel_edits: [{ x: 2, y: 1, action: 'place', gid: 0 }] });
  expect(mirror.map!.collision[6]).toBe(0);
  send('full_snapshot', {
    actors: [],
    lights: [],
    structures: [],
    map: { w: 4, h: 4, tileset: 'grid' },
    weather: { visual: 'clear', ambient_light: 1 },
    time: { day: 1, hour: 10, minute: 0, phase: 'day', is_market_day: true },
  });
  expect(mirror.voxelEdits.size).toBe(0);
  expect(mirror.map!.collision[6]).toBe(1);
});

it('ignores malformed edit coordinates instead of corrupting the typed arrays', () => {
  const { mirror, send } = scene();
  send('state_delta', {
    actors: [],
    voxel_edits: [
      { x: true, y: 1, action: 'place', gid: 0 },
      { x: 99, y: 1, action: 'place', gid: 0 },
      { x: 1, y: 1, action: 'paint', gid: 0 },
      { x: 1, y: 1, action: 'dig', gid: -1 },
    ],
  });
  expect(mirror.voxelEdits.size).toBe(0);
  expect([...mirror.map!.collision]).toEqual(new Array(16).fill(1));
});

it('forwards three-material stock but rejects malformed optional counts before the HUD callback', () => {
  const { onVoxelState, send } = scene();
  send('voxel_state', { dig: null, inventory: { earth: 0, stone: 2, wood: 3 } });
  expect(onVoxelState).toHaveBeenCalledTimes(1);
  expect(onVoxelState).toHaveBeenLastCalledWith(
    expect.objectContaining({
      inventory: { earth: 0, stone: 2, wood: 3 },
    }),
  );
  for (const inventory of [
    { earth: 0, stone: -1 },
    { earth: 0, wood: 0.5 },
    { earth: 0, stone: null },
  ]) {
    send('voxel_state', { dig: null, inventory });
  }
  expect(onVoxelState).toHaveBeenCalledTimes(1);
  send('voxel_state', { v: '1.12', dig: null, inventory: { earth: 4 } });
  expect(onVoxelState).toHaveBeenCalledTimes(2);
});
