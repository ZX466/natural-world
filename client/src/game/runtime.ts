/**
 * client/src/game/runtime.ts — 前端运行时单例：镜像 + WS + mock 驱动。
 *
 * M0 阶段 sim 的 WS 网关未起（TASK-C05），连接失败后自动进入 mock 模式：
 * 用本地假数据驱动镜像（含移动实体与戏内时钟），保证 M0 前端可独立验收
 * 「可走动 + 昼夜调色 + 重连重置」。sim 起来后删掉 mock 分支即切真实。
 */
import { WorldMirror } from './world-mirror';
import { WsClient, type WsStatus } from '../net/ws';
import { useUiStore, type InGameTime, type Speed } from '../store/uiStore';

export const worldMirror = new WorldMirror();

const SIM_WS_URL = 'ws://127.0.0.1:8000/ws';
const MOCK_TICK_MS = 1000 / 60;

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
      onStatus: (status: WsStatus) => useUiStore.getState().setWsStatus(status),
      onSnapshot: () => useUiStore.getState().setWsStatus('open'),
      onDelta: () => {},
    });
    this.ws.connect();
    // sim 未就绪 → 2.5s 后仍无连接则进 mock（验收不受 TASK-C05 进度阻塞）
    setTimeout(() => {
      if (useUiStore.getState().wsStatus !== 'open') this.startMock();
    }, 2500);
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
