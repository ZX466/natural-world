/**
 * client/src/game/__tests__/runtime-control.test.ts — 批次 D11 控制回执钉。
 *
 * 两案根因：control_ack 被 ws dispatch default 吞 → 前端 paused/speed 永不更新
 * （暂停后按钮永远「暂停」= 无法继续；倍速高亮不跟随）。修后：
 * - onControlAck（pause/resume/set_speed）→ 权威 speed/paused 回写 store；
 * - session_state（重连/读档首帧）→ setControlStateSink 消费 speed/paused。
 */
import { describe, expect, it, vi } from 'vitest';

function mockDeps() {
  vi.resetModules();
  const store = {
    wsStatus: 'connecting' as string,
    paused: false,
    speed: 1,
    lastImpulseCue: null as string | null,
    impulseError: null as string | null,
    monologues: [] as { form: string; content: string }[],
    chatter: [] as string[],
    plans: [] as { rtoken: string; text: string }[],
    setWsStatus: (s: string) => {
      store.wsStatus = s;
    },
    setGameClock: vi.fn(),
    setPaused: (p: boolean) => {
      store.paused = p;
    },
    setSpeed: (s: 1 | 4 | 16) => {
      store.speed = s;
    },
    setLastImpulseCue: vi.fn(),
    setImpulseError: vi.fn(),
    pushMonologue: vi.fn(),
    pushChatter: vi.fn(),
    setPlans: vi.fn(),
  };
  const sent: Record<string, unknown>[] = [];
  return { store, sent };
}

/** runtime.ts 自建 `new WorldMirror()`；mock 类必须带镜像方法（既有教训）。 */
function installMirrorMock() {
  vi.doMock('../world-mirror', () => {
    const mirrorMethods = {
      setMap: vi.fn(),
      applySnapshot: vi.fn(),
      applyActorDeltas: vi.fn(),
      applyLightDeltas: vi.fn(),
      reset: vi.fn(),
      actors: new Map(),
      protagonist: null as string | null,
    };
    return {
      WorldMirror: class {
        setMap = mirrorMethods.setMap;
        applySnapshot = mirrorMethods.applySnapshot;
        applyActorDeltas = mirrorMethods.applyActorDeltas;
        applyLightDeltas = mirrorMethods.applyLightDeltas;
        reset = mirrorMethods.reset;
        actors = mirrorMethods.actors;
        protagonist = mirrorMethods.protagonist;
      },
      worldMirror: mirrorMethods,
    };
  });
}

const MOCK_OTHERS = (): void => {
  vi.doMock('../clock', () => ({
    worldClock: { start: vi.fn(), stop: vi.fn(), apply: vi.fn() },
  }));
  vi.doMock('../../net/worldApi', () => ({
    fetchWorldMap: vi.fn().mockRejectedValue(new Error('no backend')),
    assembleCollision: vi.fn(),
    assembleGround: vi.fn(),
  }));
};

/** ws mock：捕获 callbacks + 捕获 setControlStateSink 装配的 sink。 */
function installWsMock(callbacks: Record<string, unknown>, sent: Record<string, unknown>[]) {
  vi.doMock('../../net/ws', () => {
    const state = { sink: null as ((s: number, p: boolean) => void) | null };
    (callbacks as Record<string, unknown>).__sink = state;
    return {
      setControlStateSink: (sink: (s: number, p: boolean) => void) => {
        state.sink = sink;
      },
      WsClient: class {
        constructor(_u: string, _m: unknown, cb: Record<string, unknown>) {
          Object.assign(callbacks, cb);
        }
        connect(): void {}
        send(msg: Record<string, unknown>): void {
          sent.push(msg);
        }
      },
    };
  });
}

describe('runtime 控制回执（批次 D11）', () => {
  it('control_ack(pause) → paused=true（按钮文案随权威值翻转）', async () => {
    const { store } = mockDeps();
    const callbacks: Record<string, unknown> = {};
    const sent: Record<string, unknown>[] = [];
    installWsMock(callbacks, sent);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => store },
    }));
    const { runtime } = await import('../runtime');
    runtime.start();

    const ack = callbacks.onControlAck as (msg: {
      action: string;
      applied: boolean;
      paused?: boolean;
      speed?: number;
    }) => void;
    ack({ action: 'pause', applied: true, paused: true });
    expect(store.paused).toBe(true);

    ack({ action: 'resume', applied: true, speed: 4, paused: false });
    expect(store.paused).toBe(false);
    expect(store.speed).toBe(4); // resume 的 ack 带「恢复后倍率」
  });

  it('control_ack(set_speed) → speed 回写；paused 缺省不翻转', async () => {
    const { store } = mockDeps();
    const callbacks: Record<string, unknown> = {};
    const sent: Record<string, unknown>[] = [];
    installWsMock(callbacks, sent);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => store },
    }));
    const { runtime } = await import('../runtime');
    runtime.start();

    const ack = callbacks.onControlAck as (msg: {
      action: string;
      applied: boolean;
      paused?: boolean;
      speed?: number;
    }) => void;
    ack({ action: 'set_speed', applied: true, speed: 16, paused: false });
    expect(store.speed).toBe(16);
    expect(store.paused).toBe(false);

    // 暂停中变速：ack 带 paused=true + speed（记忆倍率）——前端照实渲染
    ack({ action: 'set_speed', applied: true, speed: 4, paused: true });
    expect(store.paused).toBe(true);
    expect(store.speed).toBe(4);

    // fast_forward ack：无 speed/paused 字段 → 状态不变（paused 仍是上一拍 true）
    store.speed = 1;
    ack({ action: 'fast_forward', applied: true });
    expect(store.speed).toBe(1);
    expect(store.paused).toBe(true);
  });

  it('session_state sink：重连首帧的 speed/paused 权威同步', async () => {
    const { store } = mockDeps();
    const callbacks: Record<string, unknown> = {};
    const sent: Record<string, unknown>[] = [];
    installWsMock(callbacks, sent);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => store },
    }));
    const { runtime } = await import('../runtime');
    runtime.start();

    const sink = (callbacks.__sink as { sink: ((s: number, p: boolean) => void) | null }).sink;
    expect(sink).not.toBeNull();
    sink!(16, true);
    expect(store.speed).toBe(16);
    expect(store.paused).toBe(true);
  });

  it('mock 模式 pause/resume：本地立即翻转（无后端也保持按钮可用）', async () => {
    const { store } = mockDeps();
    const callbacks: Record<string, unknown> = {};
    const sent: Record<string, unknown>[] = [];
    installWsMock(callbacks, sent);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => store },
    }));
    const { runtime } = await import('../runtime');
    runtime.start();
    vi.useFakeTimers();
    try {
      runtime.start();
      await vi.advanceTimersByTimeAsync(3000);
    } finally {
      vi.useRealTimers();
    }

    runtime.sendControl('pause');
    expect(store.paused).toBe(true);
    runtime.sendControl('resume');
    expect(store.paused).toBe(false);
  });
});
