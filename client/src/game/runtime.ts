/**
 * client/src/game/runtime.ts — 前端运行时单例：镜像 + WS 驱动。
 *
 * mock 分支已删（2026-10-12，README §3 待办清欠）：sim 未起时前端保持诚实——
 * 状态停在 connecting/reconnecting/closed，无假数据、无假时钟；
 * 所有 send 在断线时由 ws.ts 静默丢弃（不炸），恢复连接后镜像经快照重建。
 */
import { WorldMirror } from './world-mirror';
import { WsClient, setControlStateSink, type WsStatus } from '../net/ws';
import { fetchWorldMap, assembleCollision, assembleGround } from '../net/worldApi';
import { worldClock } from './clock';
import { useUiStore, type Speed } from '../store/uiStore';

export const worldMirror = new WorldMirror();

const SIM_WS_URL = 'ws://127.0.0.1:8000/ws';
/** player_impulse.text 上限（PlayerImpulseMessage schema maxLength 64 同源） */
export const IMPULSE_MAX_LEN = 64;
const IMPULSE_TOO_LONG_MSG = '话说得太长了，说不清。';
/** D14 头顶气泡停留时长（ms；阅读 15 字约 4s，取整档） */
export const BUBBLE_DURATION_MS = 4000;

class Runtime {
  private ws: WsClient | null = null;

  start(): void {
    this.ws = new WsClient(SIM_WS_URL, worldMirror, {
      onStatus: (status: WsStatus) => {
        useUiStore.getState().setWsStatus(status);
        // H-1：真实链路起 clock（世界静止无 delta 时前端时钟仍平滑推进，R3）。
        if (status === 'open') {
          worldClock.start();
        }
      },
      onSnapshot: () => useUiStore.getState().setWsStatus('open'),
      onDelta: (msg) => {
        // 批次 A：计划看板（delta 即全量替换语义，sim 侧 PlanDelta[] 无增删协议）
        if (msg.plan) useUiStore.getState().setPlans([...msg.plan]);
      },
      onMonologue: (msg) => {
        // 批次 D10 分流：bubble = 村民的公开嘟囔 → 街谈巷议 + 头顶气泡（D14）；
        // thought/plan = 陈默的心声 → 心之声面板。
        // monologue 帧无 actor 字段（W7 字段最小化），语义路由按 form 定。
        // D12：bubble 帧可选 name（说话人戏内名）随行进署名。
        if (msg.form === 'bubble') {
          useUiStore.getState().pushChatter(msg.name ?? null, msg.content);
          // D14：头顶气泡（有署名才冒——无名嘟囔无处定位）
          if (msg.name) {
            worldMirror.setBubble(msg.name, msg.content, BUBBLE_DURATION_MS, Date.now());
          }
        } else {
          useUiStore.getState().pushMonologue(msg.form, msg.content);
        }
      },
      onImpulseFeedback: (msg) => {
        const store = useUiStore.getState();
        store.setLastImpulseCue(msg.cue);
        store.setImpulseError(null);
        store.pushMonologue(msg.reaction_monologue.form, msg.reaction_monologue.content);
      },
      onError: (msg) => {
        // 仅 impulse 来源的 error 入玩家可见位；其他 ref（load_anchor 等）当前无 UI 面
        if (msg.ref === 'player_impulse') useUiStore.getState().setImpulseError(msg.message);
      },
      onControlAck: (msg) => {
        // 批次 D11：控制回执权威面——pause/resume/set_speed 后服务端真值回写
        // store（TopBar 暂停按钮文案 + 倍速高亮跟随）。applied=false 当前协议
        // 恒 true（8.1 占位）；错误路径走 error 帧不经此处。
        const store = useUiStore.getState();
        if (msg.paused !== undefined && msg.paused !== null) {
          store.setPaused(msg.paused);
        }
        if (msg.speed !== undefined && msg.speed !== null) {
          store.setSpeed(msg.speed as Speed);
        }
        // fast_forward 的 ack 不带 speed/paused：受理即终态（世界已推进完），
        // 无本地状态可回写（全量快照随后由 dispatch 的 snapshot 分支消费）。
      },
    });
    this.ws.connect();
    this.loadWorldMap();
  }

  /** 静态层走 HTTP（codex 意见 5）：缺它 handlePointer 的 map=null 守卫
   *  吞掉一切点击（M7 修复的第二个断链）。M7-T6 增地面层（瓦片渲染）。
   *  后端未起时镜像保持 null（诚实态），点击守卫维持。 */
  private async loadWorldMap(): Promise<void> {
    try {
      const raw = await fetchWorldMap();
      worldMirror.setMap({
        w: raw.w,
        h: raw.h,
        tileset: raw.tileset,
        collision: assembleCollision(raw.w, raw.h, raw.chunks),
        ground: assembleGround(raw.w, raw.h, raw.chunks),
      });
    } catch {
      // 后端未起或网络失败：镜像保持 null；WS 指数退避重连由 ws.ts 负责
    }
  }

  /** 玩家控制（TopBar 倍速按钮）——真实链路发 set_control；断线时 ws.ts 静默丢弃。 */
  sendControl(action: 'pause' | 'resume' | 'set_speed', speed?: Speed): void {
    if (action === 'set_speed' && speed !== undefined) {
      this.ws?.send({ type: 'set_control', channel: 'control', action, speed });
      return;
    }
    if (action === 'pause' || action === 'resume') {
      this.ws?.send({ type: 'set_control', channel: 'control', action });
    }
  }

  /** WorldScene 点击寻路请求：专用 move_request 消息（TASK-K01；W5 红线——
   *  移动绝不走 impulse 文本旁路，codex C04 抽查记账项）。 */
  requestMove(x: number, y: number): void {
    const move: { type: 'move_request'; channel: 'render'; target_x: number; target_y: number } = {
      type: 'move_request',
      channel: 'render',
      target_x: x,
      target_y: y,
    };
    this.ws?.send(move);
  }

  /** 读档=分叉（批次 D4）：发 load_anchor，成功后服务端推「分叉告知 + 全量
   *  快照」两帧——镜像重置与游标指针消费链路现成（ws.ts dispatch/session_state）。 */
  loadAnchor(anchorId: string): void {
    this.ws?.send({ type: 'load_anchor', channel: 'session', anchor_id: anchorId });
  }

  /** 念头注入（ImpulseBar → sim player_impulse；批次 A）。
   *  客户端预校验：空白/超长即本地拒（不发帧、置 impulseError）；
   *  服务端 impulse_gate 拒收经 error 帧（ref=player_impulse）回同一 UI 位。 */
  sendImpulse(text: string): void {
    const store = useUiStore.getState();
    const cleaned = text.trim();
    if (!cleaned) {
      store.setImpulseError('念头还没成形。');
      return;
    }
    if (cleaned.length > IMPULSE_MAX_LEN) {
      store.setImpulseError(IMPULSE_TOO_LONG_MSG);
      return;
    }
    this.ws?.send({ type: 'player_impulse', channel: 'control', text: cleaned });
  }
}

export const runtime = new Runtime();

// D11：session_state 帧的 speed/paused 权威消费（ws.ts 不直接依赖 store——
// 经 sink 注入；重连/读档后 TopBar 与服务端真实状态对齐）。
setControlStateSink((speed, paused) => {
  const store = useUiStore.getState();
  if (speed !== null) store.setSpeed(speed as Speed);
  if (paused !== null) store.setPaused(paused);
});
