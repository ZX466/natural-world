/**
 * client/src/net/ws.ts — WS 客户端：连接/重连/消息分发（m0-client.md §3）。
 *
 * codex 意见 9：重连成功后必须发送 sync_request 并全量重置 worldStore 镜像
 * （收到 full_snapshot 才算恢复）——防增量丢失造成表现层幻觉。
 * 指数退避重连；戏内通道收到的未知消息类型静默忽略（versioning.md 铁律）。
 */
import type {
  CombatEventMessage,
  ControlAckMessage,
  FullSnapshotMessage,
  ImpulseFeedbackMessage,
  MonologueMessage,
  NpcView,
  SessionStateMessage,
  StateDeltaMessage,
  WsErrorMessage,
  WsMessage,
  VoxelStateMessage,
} from './protocol';
import type { WorldMirror } from '../game/world-mirror';
import { worldClock } from '../game/clock';
import { useUiStore } from '../store/uiStore';

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
 * WS 信封 `v`（versioning.md §1：major.minor，当前值见下方常量）。
 * 必须与 sim 侧 `sim/api/ws.py::_PROTOCOL_VERSION` 一致——此前两处各写各的
 * （sim 0.1 / client 0.1）已漂移，P05 统一为 1.0（kilo K03：前端以 sim 为准）；
 * 1.1（裁 34-1 甲案）/ 1.2（M6-K2 诊断面进快照）升版后由
 * `sim/tests/test_protocol_version.py` 的跨树钉锁死
 * （本文件是**第二落点**，真相源在 ws.py；改一处必改另一处）。
 */
const PROTOCOL_VERSION = '1.19';

export type WsStatus = 'connecting' | 'open' | 'reconnecting' | 'closed';

export interface WsCallbacks {
  onCombatEvent?: (msg: CombatEventMessage) => void;
  onVoxelState?: (msg: VoxelStateMessage) => void;
  onStatus: (status: WsStatus) => void;
  onSnapshot: (msg: FullSnapshotMessage) => void;
  onDelta: (msg: StateDeltaMessage) => void;
  /** 批次 A：narrative 通道独白帧（bubble/thought/plan 三形态） */
  onMonologue?: (msg: MonologueMessage) => void;
  /** 快照附带的心声历史（重连/读档后重同步）。**整组替换语义**：这是最近 N 条
   *  的完整投影，不是增量——逐条喂 onMonologue 会让面板每重连一次整屏重复
   *  （2026-11-05 实机实证：两条一模一样的心声）。 */
  onMonologueHistory?: (history: readonly MonologueMessage[]) => void;
  /** 人物近况的完整快照；缺省字段也以空组替换，避免重连/读档残留旧档案。 */
  onNpcViews?: (items: NpcView[]) => void;
  /** 批次 A：impulse 乐观反馈（入网即回） */
  onImpulseFeedback?: (msg: ImpulseFeedbackMessage) => void;
  /** 批次 A：协议 error 帧（ref 定位来源；player_impulse 由 runtime 消费） */
  onError?: (msg: WsErrorMessage) => void;
  /** 批次 D11：控制回执权威面（pause/resume/set_speed 的 speed/paused 真值；
   *  修前无此回调 → control_ack 被 default 吞 → 前端 paused/speed 永不更新） */
  onControlAck?: (msg: ControlAckMessage) => void;
  /** 主树 D4：session_state 的 `notice`（分叉告知）与 `anchor`（游标指针）。
   *  speed/paused 走 sink（D11 单一出口），这里只搬那两个**此前被丢弃**的键。 */
  onSessionState?: (msg: SessionStateMessage) => void;
}

export class WsClient {
  private ws: WebSocket | null = null;
  private seq = 0;
  private attempt = 0;
  private closedByUser = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private authenticated = false;
  private snapshotReady = false;
  private pendingMessages: Record<string, unknown>[] = [];

  constructor(
    private readonly url: string,
    private readonly mirror: WorldMirror,
    private readonly cb: WsCallbacks,
  ) {}

  /** Side-effectful actor inputs wait for an authenticated, current world. */
  get worldReady(): boolean {
    return this.ws?.readyState === WebSocket.OPEN && this.authenticated && this.snapshotReady;
  }

  connect(): void {
    this.closedByUser = false;
    this.open();
  }

  private open(): void {
    this.authenticated = false;
    this.snapshotReady = false;
    this.pendingMessages = [];
    this.cb.onStatus(this.attempt === 0 ? 'connecting' : 'reconnecting');
    const ws = new WebSocket(this.url);
    this.ws = ws;

    ws.onopen = async () => {
      try {
        const tokenUrl = new URL('/api/ws-token', this.url.replace(/^ws/, 'http'));
        const response = await fetch(tokenUrl.toString(), { cache: 'no-store' });
        if (!response.ok) throw new Error('handshake unavailable');
        const body: unknown = await response.json();
        if (
          !body ||
          typeof body !== 'object' ||
          !('token' in body) ||
          typeof body.token !== 'string' ||
          !body.token
        )
          throw new Error('invalid handshake');
        if (this.ws !== ws || ws.readyState !== WebSocket.OPEN) return;
        this.sendRaw({
          type: 'hello',
          channel: 'session',
          token: body.token,
          v: PROTOCOL_VERSION,
          ws_seq: this.nextSeq(),
        });
      } catch {
        if (this.ws === ws) ws.close();
      }
    };

    ws.onmessage = (ev: MessageEvent) => {
      if (this.ws !== ws) return;
      this.dispatch(String(ev.data));
    };

    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.authenticated = false;
      this.snapshotReady = false;
      this.pendingMessages = [];
      this.cb.onStatus('closed');
      if (!this.closedByUser) this.scheduleReconnect();
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  private dispatch(raw: string): void {
    let msg: WsMessage | { type: 'hello_ack' };
    try {
      msg = JSON.parse(raw) as WsMessage | { type: 'hello_ack' };
    } catch {
      return; // 非 JSON 静默忽略
    }
    switch (msg.type) {
      case 'hello_ack': {
        if (this.authenticated) break;
        this.authenticated = true;
        this.attempt = 0;
        this.cb.onStatus('open');
        this.send({ type: 'sync_request', channel: 'session', reason: 'reconnect' });
        const pending = this.pendingMessages;
        this.pendingMessages = [];
        for (const frame of pending) this.send(frame);
        break;
      }
      case 'full_snapshot':
        this.mirror.applySnapshot(msg.actors, msg.lights);
        this.mirror.applyVoxelEdits(Array.isArray(msg.voxel_edits) ? msg.voxel_edits : [], true);
        if (msg.weather) {
          this.mirror.setWeather({
            visual: msg.weather.visual,
            ambientLight: msg.weather.ambient_light,
          });
        }
        if (msg.map) {
          // collision/ground 静态层走 HTTP（worldApi.ts），这里只消费 time
        }
        this.mirror.applyStructures(msg.structures ?? [], true); // 全量替换，包括空快照
        if (msg.time) worldClock.apply(msg.time); // M7-R3：时钟权威帧
        // 2026-10-11 心声历史：重启/重连面板不空（后端带最近 20 条）。
        // 2026-11-05 修：这是**重同步**（完整投影），交给消费方整组替换。
        // 逐条重放曾让每次重连/读档把同一句叠一遍（实机截图两条同句心声）。
        if (msg.monologue_history) {
          this.cb.onMonologueHistory?.(msg.monologue_history as readonly MonologueMessage[]);
        }
        this.cb.onNpcViews?.(Array.isArray(msg.npc_views) ? msg.npc_views : []);
        this.snapshotReady = true;
        this.cb.onSnapshot(msg);
        break;
      case 'state_delta':
        this.mirror.applyActorDeltas(msg.actors);
        if (Array.isArray(msg.voxel_edits)) this.mirror.applyVoxelEdits(msg.voxel_edits);
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
      case 'voxel_state':
        if (this.mirror.applyVoxelState(msg)) this.cb.onVoxelState?.(msg);
        break;
      case 'session_state':
        // M5-K3 会话首帧（刻度/暂停态/游标）；M7：time 可选随帧同步。
        // D11：speed/paused 是服务端权威值——消费它们（修前只同步时钟，
        // 重连后 TopBar 高亮/暂停按钮文案与真实状态脱节）。
        useControlState(msg.speed, msg.paused);
        if (msg.time) worldClock.apply(msg.time);
        // 主树 D4：notice（「你回到了「X」那段日子」）与 anchor（游标指针）
        // 此前被直接丢弃 ⇒ 读档分叉后玩家永远不知道世界换线了。
        this.cb.onSessionState?.(msg as SessionStateMessage);
        break;
      case 'control_ack':
        // D11：控制回执（pause/resume/set_speed 的权威 speed/paused）——
        // 修前被 default 静默吞掉：暂停后按钮文字不变（永远「暂停」）、
        // 倍速高亮不跟随，用户观感「暂停后无法继续/倍速无反馈」。
        this.cb.onControlAck?.(msg as ControlAckMessage);
        break;
      case 'timescale':
        useUiStore.getState().setCombatActive(msg.active);
        break;
      case 'combat_event':
        useUiStore.getState().recordCombatEvent();
        this.cb.onCombatEvent?.(msg);
        break;
      case 'monologue':
        this.cb.onMonologue?.(msg as MonologueMessage);
        break;
      case 'impulse_feedback':
        this.cb.onImpulseFeedback?.(msg as ImpulseFeedbackMessage);
        break;
      case 'error':
        if (msg.code === 'auth_error') {
          this.ws?.close();
          break;
        }
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
    if (this.ws?.readyState === WebSocket.OPEN && !this.authenticated) {
      this.pendingMessages.push(msg);
      return;
    }
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
    this.authenticated = false;
    this.snapshotReady = false;
    this.pendingMessages = [];
    if (this.timer !== null) clearTimeout(this.timer);
    this.ws?.close();
  }
}
