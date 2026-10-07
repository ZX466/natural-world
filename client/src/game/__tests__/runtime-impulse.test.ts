/**
 * client/src/game/__tests__/runtime-impulse.test.ts — 批次 A impulse 链路钉。
 *
 * runtime 新增 sendImpulse（ImpulseBar → sim player_impulse）+ 虚拟导入回调
 * onNarrativeWs（ws 分发 → store 叙事面；避免 WsClient↔uiStore 循环依赖）。
 * mock 分支：无后端也出 feedback（骨架验收不受后端阻塞）。
 */
import { describe, expect, it, vi } from 'vitest';

function mockDeps() {
  vi.resetModules();
  const callbacks: Record<string, unknown> = {};
  const store = {
    wsStatus: 'connecting' as string,
    paused: false,
    speed: 1,
    lastImpulseCue: null as string | null,
    impulseError: null as string | null,
    monologues: [] as { form: string; content: string }[],
    plans: [] as { rtoken: string; text: string }[],
    setWsStatus: (s: string) => {
      store.wsStatus = s;
    },
    setGameClock: vi.fn(),
    setPaused: vi.fn(),
    setSpeed: vi.fn(),
    setLastImpulseCue: (c: string | null) => {
      store.lastImpulseCue = c;
    },
    setImpulseError: (e: string | null) => {
      store.impulseError = e;
    },
    pushMonologue: (form: string, content: string) => {
      store.monologues = [...store.monologues, { form, content }];
    },
    setPlans: (p: { rtoken: string; text: string }[]) => {
      store.plans = p;
    },
  };
  const sent: Record<string, unknown>[] = [];
  return { callbacks, store, sent };
}

/** runtime.ts 自建 `new WorldMirror()`（不消费模块的 worldMirror 导出），
 *  mock 类必须带镜像方法（runtime-mock.test.ts 同款教训）。 */
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

function installWsMock(callbacks: Record<string, unknown>, sent: Record<string, unknown>[]) {
  vi.doMock('../../net/ws', () => ({
    setControlStateSink: vi.fn(), // D11：runtime 顶层装配调用（本测试不消费）
    WsClient: class {
      constructor(
        _u: string,
        _m: unknown,
        cb: Record<string, unknown>,
      ) {
        Object.assign(callbacks, cb);
      }
      connect(): void {}
      send(msg: Record<string, unknown>): void {
        sent.push(msg);
      }
    },
  }));
}

describe('runtime impulse 链路（批次 A）', () => {
  it('sendImpulse 真实链路：player_impulse 帧形状 + 长度校验前置', async () => {
    const { callbacks, store, sent } = mockDeps();
    installWsMock(callbacks, sent);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => store },
    }));
    const { runtime } = await import('../runtime');
    runtime.start();

    runtime.sendImpulse('今天去集市看看');
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({
      type: 'player_impulse',
      channel: 'control',
      text: '今天去集市看看',
    });

    // >64 字客户端即拦（不发帧）
    runtime.sendImpulse('长'.repeat(65));
    expect(sent).toHaveLength(1);
    expect(store.impulseError).toBe('话说得太长了，说不清。');
  });

  it('onImpulseFeedback → cue 入 store；reaction_monologue 进思维流', async () => {
    const { callbacks, store, sent } = mockDeps();
    installWsMock(callbacks, sent);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => store },
    }));
    const { runtime } = await import('../runtime');
    runtime.start();

    const feedback = callbacks.onImpulseFeedback as (
      msg: { cue: string; reaction_monologue: { form: string; content: string } },
    ) => void;
    feedback({ cue: 'accepted', reaction_monologue: { form: 'thought', content: '这话我记下了。' } });
    expect(store.lastImpulseCue).toBe('accepted');
    expect(store.impulseError).toBeNull();
    expect(store.monologues).toEqual([{ form: 'thought', content: '这话我记下了。' }]);
  });

  it('onError(ref=player_impulse) → impulseError；其他 ref 忽略', async () => {
    const { callbacks, store, sent } = mockDeps();
    installWsMock(callbacks, sent);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => store },
    }));
    const { runtime } = await import('../runtime');
    runtime.start();

    const onError = callbacks.onError as (msg: { ref: string; message: string }) => void;
    onError({ ref: 'player_impulse', message: '这个念头进不去。' });
    expect(store.impulseError).toBe('这个念头进不去。');
    onError({ ref: 'load_anchor', message: '这个档读不出来了。' });
    expect(store.impulseError).toBe('这个念头进不去。'); // 非 impulse ref 不覆盖
  });

  it('mock 模式 sendImpulse：本地 feedback（accepted + 模板独白）', async () => {
    const { callbacks, store, sent } = mockDeps();
    installWsMock(callbacks, sent);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => store },
    }));
    const { runtime } = await import('../runtime');
    runtime.start();
    // 触发 mock 接管（wsStatus 未 open → 2.5s 定时进 mock；直接调私有方法太脆，
    // 用 vi.useFakeTimers 推进）
    vi.useFakeTimers();
    try {
      runtime.start(); // start 幂等性由 ws 实例重建保证（测试内二次 start 仅推定时）
      await vi.advanceTimersByTimeAsync(3000);
    } finally {
      vi.useRealTimers();
    }
    runtime.sendImpulse('心里想想');
    expect(sent).toHaveLength(0); // mock 不发帧
    expect(store.lastImpulseCue).toBe('accepted');
    expect(store.monologues.length).toBe(1);
    expect(store.monologues[0]?.form).toBe('thought');
  });
});
