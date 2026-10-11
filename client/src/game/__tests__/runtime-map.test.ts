/**
 * client/src/game/__tests__/runtime-map.test.ts — 真实模式地图加载回归钉。
 *
 * M7 修复二：start() 必须触发 /api/world/map 加载并装入镜像
 * （此前 M0 起真实模式 map=null，点击被 handlePointer 守卫吞掉）。
 *
 * 注意：runtime.ts 模块顶层自建 `export const worldMirror = new WorldMirror()`，
 * mock 必须 spy 在 WorldMirror 类实例方法上（而非工厂里另造单例——那是两个对象）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

describe('runtime.start loads world map', () => {
  let setMapSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.resetModules();
    setMapSpy = vi.fn();

    vi.doMock('../world-mirror', () => ({
      WorldMirror: class {
        setMap = (...a: unknown[]) => setMapSpy(...a);
        applySnapshot = vi.fn();
        protagonist: string | null = null;
      },
    }));
    vi.doMock('../../net/ws', () => ({
      setControlStateSink: vi.fn(), // D11：runtime 顶层装配调用
      WsClient: class {
        connect(): void {}
        send(_m: unknown): void {}
      },
    }));
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: { getState: () => ({ wsStatus: 'connecting' }) },
    }));
  });

  it('fetchWorldMap 成功 → setMap 收到组装后的碰撞网格', async () => {
    vi.doMock('../../net/worldApi', () => ({
      fetchWorldMap: vi.fn().mockResolvedValue({ w: 32, h: 32, tileset: 'grid', chunks: [] }),
      assembleCollision: (w: number, h: number) => new Uint8Array(w * h).fill(1),
      assembleGround: (w: number, h: number) => new Uint16Array(w * h),
    }));

    const { runtime } = await import('../runtime');
    runtime.start();
    // loadWorldMap 是 async：让事件循环清空
    await new Promise((r) => setTimeout(r, 0));

    expect(setMapSpy).toHaveBeenCalledTimes(1);
    const call = setMapSpy.mock.calls[0];
    if (!call) throw new Error('setMap 未被调用');
    const map = call[0] as { w: number; h: number; collision: Uint8Array; ground?: Uint16Array };
    expect(map.w).toBe(32);
    expect(map.h).toBe(32);
    expect(map.collision.length).toBe(32 * 32);
    expect(map.collision[0]).toBe(1);
    expect(map.ground?.length).toBe(32 * 32); // M7-T6：地面层同帧装入
  });

  it('fetchWorldMap 失败 → 不 setMap（map 保持 null，守卫继续生效）', async () => {
    vi.doMock('../../net/worldApi', () => ({
      fetchWorldMap: vi.fn().mockRejectedValue(new Error('backend down')),
      assembleCollision: vi.fn(),
      assembleGround: vi.fn(),
    }));

    const { runtime } = await import('../runtime');
    runtime.start();
    await new Promise((r) => setTimeout(r, 0));

    expect(setMapSpy).not.toHaveBeenCalled();
  });
});
