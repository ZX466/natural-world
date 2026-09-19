/**
 * client/src/net/ws.ts — WS 客户端：连接/重连/消息分发（m0-client.md §3）。
 *
 * codex 意见 9：重连成功后必须发送 sync_request 并全量重置 worldStore 镜像
 * （收到 full_snapshot 才算恢复）——防增量丢失造成表现层幻觉。
 * 指数退避重连；戏内通道收到的未知消息类型静默忽略（versioning.md 铁律）。
 */
import type { FullSnapshotMessage, StateDeltaMessage, WsMessage } from './protocol';
import type { WorldMirror } from '../game/world-mirror';

const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 8000;

export type WsStatus = 'connecting' | 'open' | 'reconnecting' | 'closed';

export interface WsCallbacks {
  onStatus: (status: WsStatus) => void;
  onSnapshot: (msg: FullSnapshotMessage) => void;
  onDelta: (msg: StateDeltaMessage) => void;
}

export class WsClient {
  private ws: WebSocket | null = null;
  private seq = 0;
  private attempt = 0;
  private closedByUser = false;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly url: string,
    private readonly mirror: WorldMirror,
    private readonly cb: WsCallbacks,
  ) {}

  connect(): void {
    this.closedByUser = false;
    this.open();
  }

  private open(): void {
    this.cb.onStatus(this.attempt === 0 ? 'connecting' : 'reconnecting');
    const ws = new WebSocket(this.url);
    this.ws = ws;

    ws.onopen = () => {
      this.attempt = 0;
      this.cb.onStatus('open');
      // 重连后的首条消息：请求全量快照（M0 sim 未实现时收不到，镜像保持空直到 mock）
      this.sendRaw({
        type: 'sync_request',
        channel: 'session',
        reason: 'reconnect',
        v: '0.1',
        ws_seq: this.nextSeq(),
      });
    };

    ws.onmessage = (ev: MessageEvent) => {
      this.dispatch(String(ev.data));
    };

    ws.onclose = () => {
      this.cb.onStatus('closed');
      if (!this.closedByUser) this.scheduleReconnect();
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  private dispatch(raw: string): void {
    let msg: WsMessage;
    try {
      msg = JSON.parse(raw) as WsMessage;
    } catch {
      return; // 非 JSON 静默忽略
    }
    switch (msg.type) {
      case 'full_snapshot':
        this.mirror.applySnapshot(msg.actors, msg.lights);
        if (msg.map) {
          // collision 静态层走 HTTP，这里只登记尺寸/tileset（M0 mock 阶段）
        }
        this.cb.onSnapshot(msg);
        break;
      case 'state_delta':
        this.mirror.applyActorDeltas(msg.actors);
        if (msg.lights) this.mirror.applyLightDeltas(msg.lights);
        this.cb.onDelta(msg);
        break;
      default:
        // 未知类型/戏外未实现消息：静默忽略（不出错不出戏，versioning.md）
        break;
    }
  }

  /** C→S 消息统一入口（自动附 ws_seq/v）。
   *  注：Omit 对联合不分发（会坍缩成公共键），所以用可分配性宽松的入参 +
   *  序列化前统一附加信封字段；消息形状由调用方与生成的类型保证。 */
  send(msg: Record<string, unknown>): void {
    this.sendRaw({ ...msg, v: '0.1', ws_seq: this.nextSeq() });
  }

  private sendRaw(payload: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  private nextSeq(): number {
    this.seq += 1;
    return this.seq;
  }

  private scheduleReconnect(): void {
    if (this.timer !== null) return;
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** this.attempt, RECONNECT_MAX_MS);
    this.attempt += 1;
    this.timer = setTimeout(() => {
      this.timer = null;
      this.mirror.reset(); // codex 意见 9：重连前全量重置镜像
      this.open();
    }, delay);
  }

  close(): void {
    this.closedByUser = true;
    if (this.timer !== null) clearTimeout(this.timer);
    this.ws?.close();
  }
}
