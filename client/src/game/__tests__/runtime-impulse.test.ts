/**
 * client/src/game/__tests__/runtime-impulse.test.ts — 批次 A impulse 链路钉。
 *
 * runtime 新增 sendImpulse（ImpulseBar → sim player_impulse）+ 虚拟导入回调
 * onNarrativeWs（ws 分发 → store 叙事面；避免 WsClient↔uiStore 循环依赖）。
 * mock 分支：无后端也出 feedback（骨架验收不受后端阻塞）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
afterEach(() => vi.unstubAllGlobals());

function mockDeps() {
  vi.resetModules();
  const callbacks: Record<string, unknown> = {};
  const store = {
    wsStatus: 'connecting' as string,
    paused: false,
    speed: 1,
    lastImpulseCue: null as string | null,
    impulseError: null as string | null,
    loadError: null as string | null,
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
    setLoadError: (e: string | null) => {
      store.loadError = e;
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
      setBubble: vi.fn(),
      applySnapshot: vi.fn(),
      applyActorDeltas: vi.fn(),
      applyLightDeltas: vi.fn(),
      reset: vi.fn(),
      actors: new Map(),
      structures: new Map(),
      protagonist: null as string | null,
    };
    return {
      WorldMirror: class {
        setMap = mirrorMethods.setMap;
        setBubble = mirrorMethods.setBubble;
        applySnapshot = mirrorMethods.applySnapshot;
        applyActorDeltas = mirrorMethods.applyActorDeltas;
        applyLightDeltas = mirrorMethods.applyLightDeltas;
        reset = mirrorMethods.reset;
        actors = mirrorMethods.actors;
        structures = mirrorMethods.structures;
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
      constructor(_u: string, _m: unknown, cb: Record<string, unknown>) {
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
  it.each(['', '?renderer=flat'])(
    'shows the reaction as a protagonist bubble only in iso (%s)',
    async (search) => {
      vi.stubGlobal('location', { search });
      const { callbacks, store, sent } = mockDeps();
      installWsMock(callbacks, sent);
      installMirrorMock();
      MOCK_OTHERS();
      vi.doMock('../../store/uiStore', () => ({ useUiStore: { getState: () => store } }));
      const { runtime, worldMirror } = await import('../runtime');
      runtime.start();
      worldMirror.protagonist = 'hero';
      worldMirror.actors.set('hero', {
        rtoken: 'hero',
        name: '陈默',
        x: 1,
        y: 1,
        facing: 's',
        sprite: 'protagonist',
        anim: 'idle',
      });
      const feedback = callbacks.onImpulseFeedback as (msg: {
        cue: string;
        reaction_monologue: { form: string; content: string };
      }) => void;
      feedback({
        cue: 'accepted',
        reaction_monologue: { form: 'thought', content: '先去集市看看。' },
      });
      expect(store.monologues).toEqual([{ form: 'thought', content: '先去集市看看。' }]);
      if (search === '') {
        expect(vi.mocked(worldMirror.setBubble).mock.calls[0]?.slice(0, 3)).toEqual([
          '陈默',
          '先去集市看看。',
          4000,
        ]);
      } else expect(worldMirror.setBubble).not.toHaveBeenCalled();
    },
  );
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

    const feedback = callbacks.onImpulseFeedback as (msg: {
      cue: string;
      reaction_monologue: { form: string; content: string };
    }) => void;
    feedback({
      cue: 'accepted',
      reaction_monologue: { form: 'thought', content: '这话我记下了。' },
    });
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

  it('onError(ref=load_anchor) → loadError（读档失败玩家可见）', async () => {
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
    onError({ ref: 'load_anchor', message: '这个档读不出来了。' });
    expect(store.loadError).toBe('这个档读不出来了。');
    expect(store.impulseError).toBeNull(); // 不串到念头位
  });

  it('loadAnchor 发新请求时清掉上一次的失败文案', async () => {
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
    onError({ ref: 'load_anchor', message: '这个档读不出来了。' });
    expect(store.loadError).toBe('这个档读不出来了。');

    runtime.loadAnchor('a1');
    expect(store.loadError).toBeNull();
    expect(sent.at(-1)).toMatchObject({ type: 'load_anchor', anchor_id: 'a1' });
  });

  it('load_anchor 的工程错误码（bad_channel 等）不得把英文原文送进面板', async () => {
    const { callbacks, store, sent } = mockDeps();
    installWsMock(callbacks, sent);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => store },
    }));
    const { runtime } = await import('../runtime');
    runtime.start();

    const onError = callbacks.onError as (msg: {
      ref: string;
      code: string;
      message: string;
    }) => void;
    // 客户端发错 channel 时服务端回 bad_channel/"channel mismatch"（ws.py:995）——
    // 那是工程措辞，绝不能进玩家可见位（§4.5 戏内文风）。
    onError({ ref: 'load_anchor', code: 'bad_channel', message: 'channel mismatch' });
    expect(store.loadError).not.toBe('channel mismatch');
    expect(store.loadError).toBe('这个档读不出来了。');
  });

  it('load_failed 的空文案原样透传（不归一成 null，交给面板判空）', async () => {
    const { callbacks, store, sent } = mockDeps();
    installWsMock(callbacks, sent);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => store },
    }));
    const { runtime } = await import('../runtime');
    runtime.start();

    const onError = callbacks.onError as (msg: {
      ref: string;
      code: string;
      message: string;
    }) => void;
    onError({ ref: 'load_anchor', code: 'load_failed', message: '' });
    expect(store.loadError).toBe('');
  });

  it('读档成功（full_snapshot）清掉旧失败文案', async () => {
    const { callbacks, store, sent } = mockDeps();
    installWsMock(callbacks, sent);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => store },
    }));
    const { runtime } = await import('../runtime');
    runtime.start();

    const onError = callbacks.onError as (msg: {
      ref: string;
      code: string;
      message: string;
    }) => void;
    onError({ ref: 'load_anchor', code: 'load_failed', message: '这个档读不出来了。' });
    expect(store.loadError).toBe('这个档读不出来了。');

    // 读档成功帧序 = session_state → timescale → full_snapshot；快照到达即世界已恢复。
    (callbacks.onSnapshot as () => void)();
    expect(store.loadError).toBeNull();
  });
});
