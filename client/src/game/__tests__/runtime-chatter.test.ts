/**
 * client/src/game/__tests__/runtime-chatter.test.ts — 批次 D10 monologue 分流钉。
 *
 * monologue 帧按 form 语义路由（帧无 actor 字段，W7）：
 * - bubble → pushChatter（街谈巷议：村民公开嘟囔）；
 * - thought/plan → pushMonologue（心之声：陈默的内心）。
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
    pushChatter: (content: string) => {
      store.chatter = [...store.chatter, content];
    },
    setPlans: (p: { rtoken: string; text: string }[]) => {
      store.plans = p;
    },
  };
  const sent: Record<string, unknown>[] = [];
  return { store, sent };
}

/** runtime.ts 自建 `new WorldMirror()`（不消费模块的 worldMirror 导出），
 *  mock 类必须带镜像方法（runtime-impulse.test.ts 同款教训）。 */
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

describe('runtime monologue 分流（批次 D10）', () => {
  it('bubble → 街谈巷议（不进心之声）', async () => {
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

    const onMonologue = callbacks.onMonologue as (msg: { form: string; content: string }) => void;
    onMonologue({ form: 'bubble', content: '这事我有点犯嘀咕。' });
    expect(store.chatter).toEqual(['这事我有点犯嘀咕。']);
    expect(store.monologues).toEqual([]);
  });

  it('thought/plan → 心之声（不进街谈巷议）', async () => {
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

    const onMonologue = callbacks.onMonologue as (msg: { form: string; content: string }) => void;
    onMonologue({ form: 'thought', content: '这话我记下了。' });
    onMonologue({ form: 'plan', content: '先去药铺看看。' });
    expect(store.monologues).toEqual([
      { form: 'thought', content: '这话我记下了。' },
      { form: 'plan', content: '先去药铺看看。' },
    ]);
    expect(store.chatter).toEqual([]);
  });
});
