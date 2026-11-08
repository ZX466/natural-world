import { afterEach, expect, it, vi } from 'vitest';
import { WsClient } from '../ws';
import { WorldMirror } from '../../game/world-mirror';

class Socket {
  static OPEN = 1;
  static last: Socket;
  readyState = 1;
  onopen: (() => void | Promise<void>) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: Record<string, unknown>[] = [];
  constructor() {
    Socket.last = this;
  }
  send(raw: string) {
    this.sent.push(JSON.parse(raw));
  }
  close() {
    this.readyState = 3;
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it('sends hello first and releases commands only after hello_ack', async () => {
  vi.stubGlobal('WebSocket', Socket);
  const fetchToken = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ token: 'test-only-token' }),
  });
  vi.stubGlobal('fetch', fetchToken);
  const client = new WsClient('ws://127.0.0.1:8000/ws', new WorldMirror(), {
    onStatus: vi.fn(),
    onSnapshot: vi.fn(),
    onDelta: vi.fn(),
  });
  client.connect();
  const socket = Socket.last;
  await socket.onopen?.();
  expect(fetchToken).toHaveBeenCalledWith('http://127.0.0.1:8000/api/ws-token', {
    cache: 'no-store',
  });
  expect(socket.sent.map((frame) => frame.type)).toEqual(['hello']);
  client.send({ type: 'set_control', channel: 'control', action: 'pause' });
  expect(socket.sent.map((frame) => frame.type)).toEqual(['hello']);
  socket.onmessage?.({ data: JSON.stringify({ type: 'hello_ack', channel: 'session' }) });
  expect(socket.sent.map((frame) => frame.type)).toEqual(['hello', 'sync_request', 'set_control']);
  client.close();
});

it('keeps commands unsent when token retrieval fails', async () => {
  vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
  const client = new WsClient('ws://127.0.0.1:8000/ws', new WorldMirror(), {
    onStatus: vi.fn(),
    onSnapshot: vi.fn(),
    onDelta: vi.fn(),
  });
  client.connect();
  const socket = Socket.last;
  await socket.onopen?.();
  client.send({ type: 'set_control', channel: 'control', action: 'pause' });
  expect(socket.sent).toEqual([]);
  expect(socket.readyState).toBe(3);
  client.close();
});

it.each(['move_request', 'jump_request'])(
  '%s waits for auth and sends the 1.16 envelope',
  async (type) => {
    vi.stubGlobal('WebSocket', Socket);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ token: 'test-only-token' }) }),
    );
    const client = new WsClient('ws://127.0.0.1:8000/ws', new WorldMirror(), {
      onStatus: vi.fn(),
      onSnapshot: vi.fn(),
      onDelta: vi.fn(),
    });
    client.connect();
    const socket = Socket.last;
    await socket.onopen?.();
    client.send({ type, channel: 'render', target_x: 1, target_y: 2, gait: 'run' });
    expect(socket.sent.map((frame) => frame.type)).toEqual(['hello']);
    socket.onmessage?.({ data: JSON.stringify({ type: 'hello_ack', channel: 'session' }) });
    expect(socket.sent.map((frame) => frame.type)).toEqual(['hello', 'sync_request', type]);
    expect(socket.sent.at(-1)).toMatchObject({
      type,
      v: '1.16',
      target_x: 1,
      target_y: 2,
      gait: 'run',
    });
    client.close();
  },
);

it.each(['move_request', 'jump_request'])(
  '%s is dropped while disconnected and never replays a stale command',
  async (type) => {
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', Socket);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ token: 'test-only-token' }) }),
    );
    const client = new WsClient('ws://127.0.0.1:8000/ws', new WorldMirror(), {
      onStatus: vi.fn(),
      onSnapshot: vi.fn(),
      onDelta: vi.fn(),
    });
    client.send({ type, channel: 'render', target_x: 0, target_y: 0 });
    client.connect();
    const first = Socket.last;
    await first.onopen?.();
    client.send({ type, channel: 'render', target_x: 1, target_y: 2 });
    first.close();
    first.onclose?.();
    client.send({ type, channel: 'render', target_x: 3, target_y: 4 });
    await vi.advanceTimersByTimeAsync(500);
    const second = Socket.last;
    expect(second).not.toBe(first);
    await second.onopen?.();
    second.onmessage?.({ data: JSON.stringify({ type: 'hello_ack', channel: 'session' }) });
    expect(second.sent.map((frame) => frame.type)).toEqual(['hello', 'sync_request']);
    client.close();
  },
);

it('worldReady waits for this connection snapshot and resets on close or reconnect', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ token: 'test-only-token' }) }),
  );
  const onStatus = vi.fn();
  const mirror = new WorldMirror();
  const client = new WsClient('ws://127.0.0.1:8000/ws', mirror, {
    onStatus,
    onSnapshot: () => expect(client.worldReady).toBe(true),
    onDelta: vi.fn(),
  });
  const snapshot = JSON.stringify({
    v: '1.16',
    ws_seq: 2,
    channel: 'render',
    type: 'full_snapshot',
    actors: [{ rtoken: 'opaque', sprite: 'villager', x: 1, y: 2, facing: 's', anim: 'idle' }],
    lights: [],
    structures: [],
    map: { tileset: 'town', w: 4, h: 4 },
    weather: { visual: 'clear', ambient_light: 1 },
    time: { day: 1, hour: 8, minute: 0, phase: 'day', is_market_day: false },
  });
  expect(client.worldReady).toBe(false);
  client.connect();
  const first = Socket.last;
  await first.onopen?.();
  expect(client.worldReady).toBe(false);
  first.onmessage?.({ data: JSON.stringify({ type: 'hello_ack', channel: 'session' }) });
  expect(onStatus).toHaveBeenLastCalledWith('open');
  expect(client.worldReady).toBe(false);
  first.onmessage?.({
    data: JSON.stringify({ type: 'state_delta', channel: 'render', actors: [] }),
  });
  expect(client.worldReady).toBe(false);
  first.onmessage?.({ data: snapshot });
  expect(client.worldReady).toBe(true);
  expect(mirror.actors.get('opaque')?.x).toBe(1);
  first.close();
  first.onclose?.();
  expect(client.worldReady).toBe(false);
  await vi.advanceTimersByTimeAsync(500);
  const second = Socket.last;
  await second.onopen?.();
  second.onmessage?.({ data: JSON.stringify({ type: 'hello_ack', channel: 'session' }) });
  expect(client.worldReady).toBe(false);
  // A snapshot from the old socket must not unlock the new connection.
  first.onmessage?.({ data: snapshot });
  expect(client.worldReady).toBe(false);
  second.onmessage?.({ data: snapshot });
  expect(client.worldReady).toBe(true);
  client.close();
  expect(client.worldReady).toBe(false);
  client.connect();
  const third = Socket.last;
  await third.onopen?.();
  third.onmessage?.({ data: JSON.stringify({ type: 'hello_ack', channel: 'session' }) });
  expect(client.worldReady).toBe(false);
  client.close();
});

it('worldReady stays false if the full snapshot cannot be applied', async () => {
  vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ token: 'test-only-token' }) }),
  );
  const client = new WsClient('ws://127.0.0.1:8000/ws', new WorldMirror(), {
    onStatus: vi.fn(),
    onSnapshot: vi.fn(),
    onDelta: vi.fn(),
  });
  client.connect();
  const socket = Socket.last;
  await socket.onopen?.();
  socket.onmessage?.({ data: JSON.stringify({ type: 'hello_ack', channel: 'session' }) });
  expect(() =>
    socket.onmessage?.({
      data: JSON.stringify({ type: 'full_snapshot', channel: 'render', actors: null, lights: [] }),
    }),
  ).toThrow();
  expect(client.worldReady).toBe(false);
  client.close();
});
