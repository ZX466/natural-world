/**
 * client/src/game/__tests__/runtime-loadstate.test.ts — 读档等待态 / 分叉告知 /
 * 控制错误位（主树 D3/D4/D5）。
 *
 * 三条根因（2026-11-04 实测）：
 * 1. **D3**：`SaveLoadPanel` 的 `busy` 在同步 `finally` 里立刻清回 ⇒ `disabled={busy}`
 *    从未生效。大库读档要重放 20s+，这段时间连点两下会把两个 `load_anchor` 都塞进
 *    服务端队列（`main.py:1142` 无判重）⇒ 连续分叉两次。等待态必须由**帧**驱动：
 *    `loadAnchor()` 置位，`full_snapshot`（世界已恢复）或 `error{ref:load_anchor}` 清除。
 * 2. **D4**：`session_state` 的 `notice`（「你回到了「X」那段日子」）与 `anchor`
 *    游标指针被 `ws.ts` 直接丢弃，玩家永远不知道世界换线了。
 * 3. **D5**：`set_control` 的 6 条戏内错误文案（`ws.py:1110-1145`）无 UI 落点。
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
    loadPending: false,
    forkNotice: null as string | null,
    sessionAnchor: null as { name: string; story_label: string } | null,
    controlError: null as string | null,
    monologues: [] as { form: string; content: string }[],
    plans: [] as { rtoken: string; text: string }[],
    setWsStatus: (s: string) => {
      store.wsStatus = s;
    },
    // onStatus 的「非 open」分支会清挖土库存（掉线收尾的一部分）。
    setVoxelInventory: vi.fn(),
    setGameClock: vi.fn(),
    setPaused: (p: boolean) => {
      store.paused = p;
    },
    setSpeed: (s: 1 | 4 | 16) => {
      store.speed = s;
    },
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
    setPlans: (p: { rtoken: string; text: string }[]) => {
      store.plans = p;
    },
  };
  const sent: Record<string, unknown>[] = [];
  return { callbacks, store, sent };
}

/** runtime.ts 自建 `new WorldMirror()`（不消费模块导出），mock 类必须带镜像方法。 */
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
    setControlStateSink: vi.fn(),
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

async function boot() {
  const deps = mockDeps();
  installWsMock(deps.callbacks, deps.sent);
  installMirrorMock();
  MOCK_OTHERS();
  vi.doMock('../../store/uiStore', () => ({ useUiStore: { getState: () => deps.store } }));
  const { runtime } = await import('../runtime');
  runtime.start();
  // 读档只在连接存活时有意义（断线分支另有用例）：默认置 open，
  // 否则每个「在途态」用例测到的都是断线拒收，而不是状态机本身。
  deps.store.wsStatus = 'open';
  return { ...deps, runtime };
}

describe('D3 读档等待态由帧驱动', () => {
  it('loadAnchor 置 loadPending=true（面板按钮据此真禁用）', async () => {
    const { runtime, store } = await boot();
    runtime.loadAnchor('a1');
    expect(store.loadPending).toBe(true);
  });

  it('在途中再点一次读档不发第二帧（React 重渲染前 disabled 还没生效）', async () => {
    // 双击的真实时序：两次 onClick 都可能在一次 paint 内跑完，
    // 此时按钮的 disabled 属性还没反映到 DOM ⇒ 只有请求侧判重能拦住。
    // 服务端 main.py 的 pending_loads 无判重（D2 正在 codex 树补），
    // 前端放过第二帧就是两个 fork。
    const { runtime, store, sent } = await boot();
    runtime.loadAnchor('a1');
    expect(sent).toHaveLength(1);
    runtime.loadAnchor('a1');
    expect(sent).toHaveLength(1); // 仍在途 ⇒ 第二帧被丢
    expect(store.loadPending).toBe(true);
  });

  it('读档完成后可以再读下一个档（判重不能把后续请求也挡掉）', async () => {
    const { callbacks, runtime, sent } = await boot();
    runtime.loadAnchor('a1');
    (callbacks.onSnapshot as () => void)();
    runtime.loadAnchor('a2');
    expect(sent).toHaveLength(2);
    expect(sent.at(-1)).toMatchObject({ type: 'load_anchor', anchor_id: 'a2' });
  });

  it('full_snapshot（世界已恢复）清 loadPending', async () => {
    const { callbacks, store, runtime } = await boot();
    runtime.loadAnchor('a1');
    expect(store.loadPending).toBe(true);
    (callbacks.onSnapshot as () => void)();
    expect(store.loadPending).toBe(false);
  });

  it('断线时读档不发帧、不置在途态，并给可见文案（否则「片刻后……」永远挂着）', async () => {
    // ws.ts 在断线时静默丢弃 send。若这里照样置 loadPending=true，
    // 面板会永远显示等待行、按钮永远禁用——比「没反应」更糟（在骗玩家）。
    const { store, runtime, sent } = await boot();
    store.wsStatus = 'closed';
    runtime.loadAnchor('a1');
    expect(store.loadPending).toBe(false);
    expect(store.loadError).toBe('这会儿连不上，读不了档。');
    expect(sent).toHaveLength(0);
  });

  it('在途中掉线也清 loadPending（否则「片刻后……」挂到重连为止）', async () => {
    // 掉线时服务端不会回 error 帧，也不会推 full_snapshot；等待行只能由
    // onStatus 的「非 open」分支收尾。重连后 full_snapshot 会再清一次，无害。
    const { callbacks, store, runtime } = await boot();
    runtime.loadAnchor('a1');
    expect(store.loadPending).toBe(true);
    (callbacks.onStatus as (s: string) => void)('closed');
    expect(store.loadPending).toBe(false);
  });

  it('读档失败（error{ref:load_anchor}）同样清 loadPending——否则按钮永久禁用', async () => {
    const { callbacks, store, runtime } = await boot();
    runtime.loadAnchor('a1');
    expect(store.loadPending).toBe(true); // 先置位，否则「清了」测不到东西
    const onError = callbacks.onError as (m: {
      ref: string;
      code: string;
      message: string;
    }) => void;
    onError({ ref: 'load_anchor', code: 'load_failed', message: '这个档读不出来了。' });
    expect(store.loadPending).toBe(false);
  });
});

describe('D4 session_state 的 notice / anchor 必须被消费', () => {
  it('notice → store.forkNotice（分叉告知不再被丢弃）', async () => {
    const { callbacks, store } = await boot();
    const onSessionState = callbacks.onSessionState as (m: {
      speed: number;
      paused: boolean;
      notice: string | null;
      anchor: { name: string; story_label: string } | null;
    }) => void;
    onSessionState({
      speed: 1,
      paused: false,
      notice: '你回到了「初到临河」那段日子',
      anchor: { name: '初到临河', story_label: '第二日 · 清晨' },
    });
    expect(store.forkNotice).toBe('你回到了「初到临河」那段日子');
    expect(store.sessionAnchor).toEqual({ name: '初到临河', story_label: '第二日 · 清晨' });
  });

  it('notice/anchor 为 null（连接首帧、非读档）→ 两个字段都置空', async () => {
    const { callbacks, store } = await boot();
    store.forkNotice = '旧文案';
    store.sessionAnchor = { name: '旧档', story_label: '第 1 天' };
    const onSessionState = callbacks.onSessionState as (m: {
      speed: number;
      paused: boolean;
      notice: string | null;
      anchor: { name: string; story_label: string } | null;
    }) => void;
    onSessionState({ speed: 1, paused: false, notice: null, anchor: null });
    expect(store.forkNotice).toBeNull();
    expect(store.sessionAnchor).toBeNull();
  });
});

describe('D5 set_control 被拒必须有玩家可见位', () => {
  it('error{ref:set_control} → controlError（文案原样，服务端已是戏内口语）', async () => {
    const { callbacks, store } = await boot();
    const onError = callbacks.onError as (m: {
      ref: string;
      code: string;
      message: string;
    }) => void;
    onError({ ref: 'set_control', code: 'bad_action', message: '本来就没停。' });
    expect(store.controlError).toBe('本来就没停。');
  });

  it('工程措辞 code（bad_channel）不得进控制提示位', async () => {
    const { callbacks, store } = await boot();
    const onError = callbacks.onError as (m: {
      ref: string;
      code: string;
      message: string;
    }) => void;
    onError({ ref: 'set_control', code: 'bad_channel', message: 'channel mismatch' });
    expect(store.controlError).not.toBe('channel mismatch');
    expect(store.controlError).toBe('这会儿调不了。');
  });

  it('新的控制请求清掉旧错误文案（否则顶栏永久挂着一行提示）', async () => {
    const { callbacks, store, runtime, sent } = await boot();
    const onError = callbacks.onError as (m: {
      ref: string;
      code: string;
      message: string;
    }) => void;
    onError({ ref: 'set_control', code: 'bad_action', message: '本来就没停。' });
    expect(store.controlError).toBe('本来就没停。');
    runtime.sendControl('pause');
    expect(store.controlError).toBeNull();
    expect(sent.at(-1)).toMatchObject({ type: 'set_control', action: 'pause' });
  });
});
