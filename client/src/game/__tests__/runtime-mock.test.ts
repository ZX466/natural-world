/**
 * client/src/game/__tests__/runtime-mock.test.ts — mock 删除回归钉（2026-10-12）：
 * README §3 登记的 mock 分支已删——sim 未起时前端必须**诚实**：
 * 状态停在 connecting/reconnecting/closed，永不进入任何假数据驱动。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

describe('runtime 无 mock 生命周期', () => {
  let clockStarted: number;

  beforeEach(() => {
    vi.resetModules();
    clockStarted = 0;

    vi.doMock('../world-mirror', () => ({
      // runtime.ts 自建 new WorldMirror()（不 import 单例）——mock 类必须自带
      // spy 方法（runtime-control.test.ts 同款教训），否则实例上无方法可断言。
      WorldMirror: class {
        setMap = vi.fn();
        applySnapshot = vi.fn();
        protagonist: string | null = null;
      },
      worldMirror: { setMap: vi.fn(), applySnapshot: vi.fn(), protagonist: null },
    }));
    vi.doMock('../clock', () => ({
      worldClock: {
        start: () => {
          clockStarted += 1;
        },
        stop: () => {},
        apply: vi.fn(),
      },
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
        setWsStatus: (s: string) => {
          state.wsStatus = s;
        },
        setGameClock: vi.fn(),
        setPaused: vi.fn(),
        setSpeed: vi.fn(),
      };
      return { useUiStore: { getState: () => state } };
    });
  });

  it('status open → worldClock.start（真实链路职责不变）', async () => {
    let statusCb: ((s: string) => void) | null = null;
    vi.doMock('../../net/ws', () => ({
      setControlStateSink: vi.fn(), // D11：runtime 顶层装配调用
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
    statusCb!('open');
    expect(clockStarted).toBe(1);
  });

  it('2.5s 超时后不进 mock：状态保持未连接、镜像无假数据', async () => {
    // fake timers 必须先于 start() 安装——start 里排的 2500ms 超时才落进 fake 钟
    // （后装会漏拍：真定时器不归 fake 推进管，测了个寂寞——本钉首版踩过）。
    vi.useFakeTimers();
    try {
      const { runtime } = await import('../runtime');
      runtime.start();
      await vi.advanceTimersByTimeAsync(3000);
    } finally {
      vi.useRealTimers();
    }

    // 诚实态：无假接管——wsStatus 不被改为 open，镜像无 mock 地图/实体
    // （runtime.ts 导出的 worldMirror 单例 = mock 类实例，自带 spy 方法）
    const { worldMirror } = await import('../runtime');
    const { useUiStore } = await import('../../store/uiStore');
    expect(useUiStore.getState().wsStatus).not.toBe('open');
    expect(worldMirror.setMap).not.toHaveBeenCalled();
    expect(worldMirror.applySnapshot).not.toHaveBeenCalled();
  });

  it('无连接时 sendControl/sendImpulse/requestMove 安全 no-op（不炸、不发帧）', async () => {
    const { runtime } = await import('../runtime');
    runtime.start();

    expect(() => runtime.sendControl('pause')).not.toThrow();
    expect(() => runtime.sendImpulse('心里想想')).not.toThrow();
    expect(() => runtime.requestMove(3, 3)).not.toThrow();
  });
});
