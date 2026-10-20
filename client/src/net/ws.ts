/**
 * client/src/net/ws.ts — WS 客户端：连接/重连/消息分发（m0-client.md §3）。
 *
 * codex 意见 9：重连成功后必须发送 sync_request 并全量重置 worldStore 镜像
 * （收到 full_snapshot 才算恢复）——防增量丢失造成表现层幻觉。
 * 指数退避重连；戏内通道收到的未知消息类型静默忽略（versioning.md 铁律）。
 */
import type {
  ControlAckMessage,
  FullSnapshotMessage,
  ImpulseFeedbackMessage,
  MonologueMessage,
  StateDeltaMessage,
  WsErrorMessage,
  WsMessage,
} from './protocol';
import type { WorldMirror } from '../game/world-mirror';
import { worldClock } from '../game/clock';

const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 8000;

/** session_state.speed/paused → uiStore 的单一出口（D11）。
 *  ws.ts 不直接 import uiStore（net↔store 分层，runtime 已是桥）；经回调
 *  注入，由 runtime 装配。null = 帧未表达该字段（保持现状）。 */
export interface ControlStateSink {
  (speed: number | null, paused: boolean | null): void;
}
let controlStateSink: ControlStateSink | null = null;

/** runtime 装配点（session_state 帧的 speed/paused 消费面）。 */
export function setControlStateSink(sink: ControlStateSink | null): void {
  controlStateSink = sink;
}

function useControlState(speed: number, paused: boolean): void {
  controlStateSink?.(speed, paused);
}

/**
 * WS 信封 `v`（versioning.md §1：major.minor，当前 1.2）。
 * 必须与 sim 侧 `sim/api/ws.py::_PROTOCOL_VERSION` 一致——此前两处各写各的
 * （sim 0.1 / client 0.1）已漂移，P05 统一为 1.0（kilo K03：前端以 sim 为准）；
 * 1.1（裁 34-1 甲案）/ 1.2（M6-K2 诊断面进快照）升版后由
 * `sim/tests/test_protocol_version.py` 的跨树钉锁死
 * （本文件是**第二落点**，真相源在 ws.py；改一处必改另一处）。
 */
const PROTOCOL_VERSION = '1.9';

export type WsStatus = 'connecting' | 'open' | 'reconnecting' | 'closed';

export interface WsCallbacks {
  onStatus: (status: WsStatus) => void;
  onSnapshot: (msg: FullSnapshotMessage) => void;
  onDelta: (msg: StateDeltaMessage) => void;
  /** 批次 A：narrative 通道独白帧（bubble/thought/plan 三形态） */
  onMonologue?: (msg: MonologueMessage) => void;
  /** 批次 A：impulse 乐观反馈（入网即回） */
  onImpulseFeedback?: (msg: ImpulseFeedbackMessage) => void;
  /** 批次 A：协议 error 帧（ref 定位来源；player_impulse 由 runtime 消费） */
  onError?: (msg: WsErrorMessage) => void;
  /** 批次 D11：控制回执权威面（pause/resume/set_speed 的 speed/paused 真值；
   *  修前无此回调 → control_ack 被 default 吞 → 前端 paused/speed 永不更新） */
  onControlAck?: (msg: ControlAckMessage) => void;
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
        v: PROTOCOL_VERSION,
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
        if (msg.weather) {
          this.mirror.setWeather({
            visual: msg.weather.visual,
            ambientLight: msg.weather.ambient_light,
          });
        }
        if (msg.map) {
          // collision/ground 静态层走 HTTP（worldApi.ts），这里只消费 time
        }
        if (msg.structures) this.mirror.applyStructures(msg.structures); // E7 快照全集
        if (msg.time) worldClock.apply(msg.time); // M7-R3：时钟权威帧
        // 2026-10-11 心声历史：重启/重连面板不空（后端带最近 20 条，逐条回放）
        if (msg.monologue_history) {
          for (const frame of msg.monologue_history) {
            this.cb.onMonologue?.(frame as MonologueMessage);
          }
        }
        this.cb.onSnapshot(msg);
        break;
      case 'state_delta':
        this.mirror.applyActorDeltas(msg.actors);
        if (msg.lights) this.mirror.applyLightDeltas(msg.lights);
        if (msg.weather) {
          this.mirror.setWeather({
            visual: msg.weather.visual,
            ambientLight: msg.weather.ambient_light,
          });
        }
        if (msg.structures) this.mirror.applyStructures(msg.structures); // E7 增量
        if (msg.time) worldClock.apply(msg.time); // M7-R3
        this.cb.onDelta(msg);
        break;
      case 'session_state':
        // M5-K3 会话首帧（刻度/暂停态/游标）；M7：time 可选随帧同步。
        // D11：speed/paused 是服务端权威值——消费它们（修前只同步时钟，
        // 重连后 TopBar 高亮/暂停按钮文案与真实状态脱节）。
        useControlState(msg.speed, msg.paused);
        if (msg.time) worldClock.apply(msg.time);
        break;
      case 'control_ack':
        // D11：控制回执（pause/resume/set_speed 的权威 speed/paused）——
        // 修前被 default 静默吞掉：暂停后按钮文字不变（永远「暂停」）、
        // 倍速高亮不跟随，用户观感「暂停后无法继续/倍速无反馈」。
        this.cb.onControlAck?.(msg as ControlAckMessage);
        break;
      case 'monologue':
        this.cb.onMonologue?.(msg as MonologueMessage);
        break;
      case 'impulse_feedback':
        this.cb.onImpulseFeedback?.(msg as ImpulseFeedbackMessage);
        break;
      case 'error':
        this.cb.onError?.(msg as WsErrorMessage);
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
    this.sendRaw({ ...msg, v: PROTOCOL_VERSION, ws_seq: this.nextSeq() });
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
