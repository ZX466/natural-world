/**
 * client/src/game/__tests__/runtime-monologue-history.test.ts — 心声历史重同步钉。
 *
 * 2026-11-05 实机缺陷：重连/读档后的 full_snapshot 带 `monologue_history`
 *（最近 N 条完整投影），前端逐条追加 ⇒ 面板每重连一次整屏重复。
 * 截图实证：心之声面板两条一模一样的气味独白。
 *
 * 钉的是消费端语义：历史是**替换**，不是增量。
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => vi.unstubAllGlobals());

function mockDeps() {
  vi.resetModules();
  const store = {
    wsStatus: 'connecting' as string,
    paused: false,
    speed: 1,
    lastImpulseCue: null as string | null,
    impulseError: null as string | null,
    loadError: null as string | null,
    loadPending: false,
    forkNotice: null as string | null,
    sessionAnchor: null as { name: string; story_label: string } | null,
    controlError: null as string | null,
    monologues: [] as { form: string; content: string }[],
    chatter: [] as { name: string | null; content: string }[],
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
    setLoadPending: (p: boolean) => {
      store.loadPending = p;
    },
    setForkNotice: (n: string | null) => {
      store.forkNotice = n;
    },
    setSessionAnchor: (a: { name: string; story_label: string } | null) => {
      store.sessionAnchor = a;
    },
    setControlError: (e: string | null) => {
      store.controlError = e;
    },
    pushMonologue: (form: string, content: string) => {
      store.monologues = [...store.monologues, { form, content }];
    },
    pushChatter: (name: string | null, content: string) => {
      store.chatter = [...store.chatter, { name, content }];
    },
    // 被测语义：替换（快照历史 = 完整投影）
    replaceMonologues: (entries: readonly { form: string; content: string }[]) => {
      store.monologues = [...entries];
    },
    replaceChatter: (entries: readonly { name: string | null; content: string }[]) => {
      store.chatter = [...entries];
    },
    setPlans: (p: { rtoken: string; text: string }[]) => {
      store.plans = p;
    },
  };
  return { store };
}

function installMirrorMock() {
  vi.doMock('../world-mirror', () => {
    const mirror = {
      setMap: vi.fn(),
      applySnapshot: vi.fn(),
      applyActorDeltas: vi.fn(),
      applyLightDeltas: vi.fn(),
      reset: vi.fn(),
      setBubble: vi.fn(),
      pruneBubbles: vi.fn().mockReturnValue(false),
      bubbles: new Map(),
      actors: new Map(),
      protagonist: null as string | null,
    };
    return {
      WorldMirror: class {
        setMap = mirror.setMap;
        applySnapshot = mirror.applySnapshot;
        applyActorDeltas = mirror.applyActorDeltas;
        applyLightDeltas = mirror.applyLightDeltas;
        reset = mirror.reset;
        setBubble = mirror.setBubble;
        pruneBubbles = mirror.pruneBubbles;
        bubbles = mirror.bubbles;
        actors = mirror.actors;
        protagonist = mirror.protagonist;
      },
      worldMirror: mirror,
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

function installWsMock(callbacks: Record<string, unknown>) {
  vi.doMock('../../net/ws', () => ({
    setControlStateSink: vi.fn(),
    WsClient: class {
      constructor(_u: string, _m: unknown, cb: Record<string, unknown>) {
        Object.assign(callbacks, cb);
      }
      connect(): void {}
      send(): void {}
    },
  }));
}

describe('runtime 心声历史重同步（2026-11-05 实机缺陷）', () => {
  it('两次快照同一历史：面板不叠加重复行', async () => {
    const { store } = mockDeps();
    const callbacks: Record<string, unknown> = {};
    installWsMock(callbacks);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({ useUiStore: { getState: () => store } }));
    const { runtime } = await import('../runtime');
    runtime.start();

    const history = [
      {
        type: 'monologue',
        channel: 'narrative',
        v: '1.14',
        ws_seq: 0,
        form: 'thought',
        content: '夜深了，这气味冲鼻子不对劲。',
      },
      {
        type: 'monologue',
        channel: 'narrative',
        v: '1.14',
        ws_seq: 0,
        form: 'thought',
        content: '先回铺子稳当些。',
      },
    ];
    const onHistory = callbacks.onMonologueHistory as (
      h: readonly { form: string; content: string }[],
    ) => void;

    onHistory(history);
    onHistory(history); // 重连再来一次同一投影

    expect(store.monologues).toEqual([
      { form: 'thought', content: '夜深了，这气味冲鼻子不对劲。' },
      { form: 'thought', content: '先回铺子稳当些。' },
    ]);
  });

  it('历史按 form 分流：bubble → 街谈巷议，thought/plan → 心之声', async () => {
    const { store } = mockDeps();
    const callbacks: Record<string, unknown> = {};
    installWsMock(callbacks);
    installMirrorMock();
    MOCK_OTHERS();
    vi.doMock('../../store/uiStore', () => ({ useUiStore: { getState: () => store } }));
    const { runtime } = await import('../runtime');
    runtime.start();

    const onHistory = callbacks.onMonologueHistory as (
      h: readonly {
        type: string;
        channel: string;
        v: string;
        ws_seq: number;
        form: string;
        content: string;
        name?: string;
      }[],
    ) => void;
    onHistory([
      {
        type: 'monologue',
        channel: 'narrative',
        v: '1.14',
        ws_seq: 0,
        form: 'bubble',
        content: '这阵子不大太平。',
        name: '窦鸡贩',
      },
      {
        type: 'monologue',
        channel: 'narrative',
        v: '1.14',
        ws_seq: 0,
        form: 'thought',
        content: '这话我记下了。',
      },
      {
        type: 'monologue',
        channel: 'narrative',
        v: '1.14',
        ws_seq: 0,
        form: 'plan',
        content: '先去药铺看看。',
      },
    ]);

    expect(store.chatter).toEqual([{ name: '窦鸡贩', content: '这阵子不大太平。' }]);
    expect(store.monologues).toEqual([
      { form: 'thought', content: '这话我记下了。' },
      { form: 'plan', content: '先去药铺看看。' },
    ]);
  });
});
