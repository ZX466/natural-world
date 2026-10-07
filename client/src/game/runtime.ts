/**
 * client/src/game/runtime.ts — 前端运行时单例：镜像 + WS + mock 驱动。
 *
 * M0 阶段 sim 的 WS 网关未起（TASK-C05），连接失败后自动进入 mock 模式：
 * 用本地假数据驱动镜像（含移动实体与戏内时钟），保证 M0 前端可独立验收
 * 「可走动 + 昼夜调色 + 重连重置」。sim 起来后删掉 mock 分支即切真实。
 */
import { WorldMirror } from './world-mirror';
import { WsClient, setControlStateSink, type WsStatus } from '../net/ws';
import { fetchWorldMap, assembleCollision, assembleGround } from '../net/worldApi';
import { worldClock } from './clock';
import { useUiStore, type InGameTime, type Speed } from '../store/uiStore';

export const worldMirror = new WorldMirror();

const SIM_WS_URL = 'ws://127.0.0.1:8000/ws';
const MOCK_TICK_MS = 1000 / 60;
/** player_impulse.text 上限（PlayerImpulseMessage schema maxLength 64 同源） */
export const IMPULSE_MAX_LEN = 64;
const IMPULSE_TOO_LONG_MSG = '话说得太长了，说不清。';

function phaseOf(hour: number): InGameTime['phase'] {
  if (hour >= 5 && hour < 7) return 'dawn';
  if (hour >= 7 && hour < 17) return 'day';
  if (hour >= 17 && hour < 19) return 'dusk';
  return 'night';
}

class Runtime {
  private ws: WsClient | null = null;
  private mockTimer: ReturnType<typeof setInterval> | null = null;
  private mockTick = 0;
  private mockX = 5;
  private mockY = 5;
  private mockDir = 1;

  start(): void {
    this.ws = new WsClient(SIM_WS_URL, worldMirror, {
      onStatus: (status: WsStatus) => {
        useUiStore.getState().setWsStatus(status);
        // H-4：真实连接到达 → 停 mock（假时钟/假地图反盖真实数据的竞态根除）；
        // H-1：真实链路起 clock（世界静止无 delta 时前端时钟仍平滑推进，R3）。
        if (status === 'open') {
          this.stopMock();
          worldClock.start();
        }
      },
      onSnapshot: () => useUiStore.getState().setWsStatus('open'),
      onDelta: (msg) => {
        // 批次 A：计划看板（delta 即全量替换语义，sim 侧 PlanDelta[] 无增删协议）
        if (msg.plan) useUiStore.getState().setPlans([...msg.plan]);
      },
      onMonologue: (msg) => {
        // 批次 D10 分流：bubble = 村民的公开嘟囔（头顶气泡的文本投影）→
        // 街谈巷议；thought/plan = 陈默的心声 → 心之声面板。
        // monologue 帧无 actor 字段（W7 字段最小化），语义路由按 form 定。
        if (msg.form === 'bubble') {
          useUiStore.getState().pushChatter(msg.content);
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
    // sim 未就绪 → 2.5s 后仍无连接则进 mock（验收不受 TASK-C05 进度阻塞）
    setTimeout(() => {
      if (useUiStore.getState().wsStatus !== 'open') this.startMock();
    }, 2500);
  }

  /** H-4：mock 停转（定时器清空 + 计数归零；sendControl/requestMove 的 mock
   *  分支以 mockTimer===null 判定，清空即自然切回真实链路）。 */
  private stopMock(): void {
    if (this.mockTimer !== null) {
      clearInterval(this.mockTimer);
      this.mockTimer = null;
      this.mockTick = 0;
    }
  }

  /** 静态层走 HTTP（codex 意见 5）：缺它 handlePointer 的 map=null 守卫
   *  吞掉一切点击（M7 修复的第二个断链）。M7-T6 增地面层（瓦片渲染）。 */
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
      // 后端未起（mock 将接管）或网络失败：镜像保持 null，点击守卫维持
    }
  }

  /** 玩家控制（TopBar 倍速按钮）——真实链路发 set_control；mock 链路直接改本地。 */
  sendControl(action: 'pause' | 'resume' | 'set_speed', speed?: Speed): void {
    const store = useUiStore.getState();
    if (this.mockTimer !== null) {
      if (action === 'pause') store.setPaused(true);
      if (action === 'resume') store.setPaused(false);
      if (action === 'set_speed' && speed !== undefined) store.setSpeed(speed);
      return;
    }
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
    if (this.mockTimer !== null) {
      // mock：直线走过去（模拟 sim 寻路回放）
      const dx = Math.sign(x - this.mockX);
      const dy = Math.sign(y - this.mockY);
      this.mockX += dx;
      this.mockY += dy;
      return;
    }
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
   *  服务端 impulse_gate 拒收经 error 帧（ref=player_impulse）回同一 UI 位。
   *  mock 分支：本地出 accepted feedback（模板独白），骨架验收不受后端阻塞。 */
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
    if (this.mockTimer !== null) {
      store.setLastImpulseCue('accepted');
      store.setImpulseError(null);
      store.pushMonologue('thought', '心里默默记下了这个念头。');
      return;
    }
    this.ws?.send({ type: 'player_impulse', channel: 'control', text: cleaned });
  }

  // ── mock 驱动（TASK-C05 起服务后删除）─────────────────────────

  private startMock(): void {
    if (this.mockTimer !== null) return;
    useUiStore.getState().setWsStatus('open'); // mock 视为已连接（UI 层标记见 TopBar）
    worldMirror.setMap({
      w: 32,
      h: 32,
      tileset: 'mock',
      collision: new Uint8Array(32 * 32).fill(1),
    });
    worldMirror.applySnapshot(
      [
        { rtoken: 'mock-protagonist', x: 5, y: 5, facing: 's', sprite: 'chenmo', anim: 'idle' },
        { rtoken: 'mock-npc-1', x: 12, y: 9, facing: 'n', sprite: 'villager', anim: 'idle' },
      ],
      [],
    );
    worldMirror.protagonist = 'mock-protagonist';
    this.mockTimer = setInterval(() => this.mockStep(), MOCK_TICK_MS);
  }

  private mockStep(): void {
    const store = useUiStore.getState();
    if (store.paused) return;
    const speed = store.speed;
    // 60 tick/s × speed；游戏秒 = tick；86.4k tick = 1 游戏日
    this.mockTick += speed;
    const totalSec = this.mockTick;
    const day = Math.floor(totalSec / 86400) + 1;
    const hour = Math.floor((totalSec % 86400) / 3600);
    const minute = Math.floor((totalSec % 3600) / 60);
    store.setGameClock({
      day,
      hour,
      minute,
      phase: phaseOf(hour),
      isMarketDay: (day - 1) % 5 === 0,
    });

    // 主角来回走
    if (this.mockTick % 30 === 0) {
      this.mockX += this.mockDir;
      if (this.mockX >= 10 || this.mockX <= 3) this.mockDir *= -1;
      const actor = worldMirror.actors.get('mock-protagonist');
      if (actor) actor.x = this.mockX;
      const npc = worldMirror.actors.get('mock-npc-1');
      if (npc) npc.y = 9 + Math.round(Math.sin(this.mockTick / 90) * 2);
    }
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
