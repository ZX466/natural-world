import { afterEach, describe, expect, it, vi } from 'vitest';
import type { NpcView, NpcViewDelta } from '../../net/protocol';

class Socket {
  static OPEN = 1;
  static last: Socket;
  readyState = 1;
  onopen: (() => void | Promise<void>) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor() {
    Socket.last = this;
  }

  send() {}
  close() {
    this.readyState = 3;
  }
  receive(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

const xiaoman: NpcView = {
  rtoken: 'rt_xiaoman',
  name: '小满',
  health: ['她夜里睡得不太安稳。'],
  bond: '她见了陈默会点点头。',
  knows: ['小满: 暗夜惊惧'],
};
const tiezhu: NpcView = {
  rtoken: 'rt_tiezhu',
  name: '赵铁柱',
  health: [],
  bond: '他记得陈默。',
  knows: [],
};

function snapshot(npcViews?: NpcView[]) {
  return {
    type: 'full_snapshot',
    channel: 'render',
    v: '1.19',
    ws_seq: 0,
    actors: [],
    lights: [],
    structures: [],
    map: { w: 140, h: 100, tileset: 'linhe-town' },
    time: { day: 1, hour: 5, minute: 10, phase: 'dawn', is_market_day: false },
    ...(npcViews === undefined ? {} : { npc_views: npcViews }),
  };
}

function delta(npcViews?: NpcViewDelta[]) {
  return {
    type: 'state_delta',
    channel: 'render',
    v: '1.19',
    ws_seq: 1,
    actors: [],
    ...(npcViews === undefined ? {} : { npc_views: npcViews }),
  };
}

async function startRuntime() {
  vi.resetModules();
  vi.stubGlobal('WebSocket', Socket);
  // Keep runtime, WS dispatch, world mirror and store real; only transport is offline.
  const fetch = vi.fn().mockRejectedValue(new Error('offline test'));
  vi.stubGlobal('fetch', fetch);
  const { runtime } = await import('../runtime');
  const { useUiStore } = await import('../../store/uiStore');
  runtime.start();
  return { socket: Socket.last, useUiStore, fetch };
}

afterEach(() => vi.unstubAllGlobals());

describe('runtime npc_views transport to store', () => {
  it('replaces a reconnect snapshot instead of appending or retaining removed people', async () => {
    const { socket, useUiStore } = await startRuntime();
    socket.receive(snapshot([xiaoman, tiezhu]));
    socket.receive(snapshot([xiaoman]));
    socket.receive(snapshot([xiaoman]));
    expect(useUiStore.getState().npcViews).toEqual([xiaoman]);
  });

  it.each([
    { label: 'missing', rows: undefined },
    { label: 'empty', rows: [] },
  ])('clears old profiles when snapshot npc_views is $label', async ({ rows }) => {
    const { socket, useUiStore } = await startRuntime();
    socket.receive(snapshot([xiaoman]));
    socket.receive(snapshot(rows));
    expect(useUiStore.getState().npcViews).toEqual([]);
  });

  it('merges stationary changes, deduplicates repeated updates and consumes removals', async () => {
    const { socket, useUiStore } = await startRuntime();
    socket.receive(snapshot([xiaoman, tiezhu]));
    const changed = { ...xiaoman, health: [], knows: [], bond: '她愿意多说几句话。' };
    socket.receive(delta([changed, changed]));
    expect(useUiStore.getState().npcViews).toEqual([changed, tiezhu]);
    socket.receive(delta([{ rtoken: xiaoman.rtoken, op: 'remove' }]));
    socket.receive(delta([{ rtoken: xiaoman.rtoken, op: 'remove' }]));
    expect(useUiStore.getState().npcViews).toEqual([tiezhu]);
  });

  it('keeps current people on missing/empty delta data without a narrative HTTP query', async () => {
    const { socket, useUiStore, fetch } = await startRuntime();
    socket.receive(snapshot([tiezhu]));
    const beforeDelta = fetch.mock.calls.length;
    socket.receive(delta());
    socket.receive(delta([]));
    expect(useUiStore.getState().npcViews).toEqual([tiezhu]);
    expect(fetch).toHaveBeenCalledTimes(beforeDelta);
  });
});
