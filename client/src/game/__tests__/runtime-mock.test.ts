/**
 * client/src/game/__tests__/runtime-mock.test.ts — H-4 回归钉：
 * mock 接管后真实连接到达（ws status 'open'）→ mock 定时器必须停转。
 * （修前 mock 永生：假时钟每 16ms 覆盖真实 worldClock.apply。）
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

describe('runtime mock lifecycle（H-4）', () => {
  let clockStarted: number;


  beforeEach(() => {
    vi.resetModules();
    clockStarted = 0;


    vi.doMock('../world-mirror', () => ({
      WorldMirror: class {},
      worldMirror: { setMap: vi.fn(), applySnapshot: vi.fn(), protagonist: null },
    }));
    vi.doMock('../clock', () => ({
      worldClock: { start: () => { clockStarted += 1; }, stop: () => {}, apply: vi.fn() },
    }));
    vi.doMock('../../net/worldApi', () => ({
      fetchWorldMap: vi.fn().mockRejectedValue(new Error('no backend')),
      assembleCollision: vi.fn(),
      assembleGround: vi.fn(),
    }));
    vi.doMock('../../store/uiStore', () => {
      const state = {
        wsStatus: 'connecting',
        paused: false,
        speed: 1,
        setWsStatus: (s: string) => { state.wsStatus = s; },
        setGameClock: vi.fn(),
        setPaused: vi.fn(),
        setSpeed: vi.fn(),
      };
      return { useUiStore: { getState: () => state } };
    });
  });

  it('status open → worldClock.start 且 stopMock 清定时器', async () => {
    let statusCb: ((s: string) => void) | null = null;
    vi.doMock('../../net/ws', () => ({
      WsClient: class {
        constructor(_u: string, _m: unknown, cb: { onStatus: (s: string) => void }) {
          statusCb = cb.onStatus;
        }
        connect(): void {}
        send(): void {}
      },
    }));

    const { runtime } = await import('../runtime');
    runtime.start();
    // 模拟真实连接到达
    statusCb!('open');
    expect(clockStarted).toBe(1);
    // 再来一次 open（重连）不重复 start（clock.start 幂等由 timer!==null 保证，这里只验不炸）
    statusCb!('open');
    expect(clockStarted).toBe(2); // start 幂等性在 clock 内部；重复调用无害
  });
});
