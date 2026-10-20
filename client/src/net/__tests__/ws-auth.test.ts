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

afterEach(() => vi.unstubAllGlobals());

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
  expect(fetchToken).toHaveBeenCalledWith('/api/ws-token', { cache: 'no-store' });
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
