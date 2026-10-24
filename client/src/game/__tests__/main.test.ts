/**
 * client/src/game/__tests__/main.test.ts — move_request 事件桥回归钉。
 *
 * 背景（M7 修复）：WorldScene 自 M0-C04 起 emit 'client:move_request'，
 * 但全仓无监听者，runtime.requestMove 零调用 → 点击移动整链失效。
 * 本钉锁死：createGame 必须把该事件桥到 runtime.requestMove。
 * 纯 node 环境：phaser/runtime/world-mirror 全 mock，无需 DOM。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

type MoveHandler = (payload: {
  x: number;
  y: number;
  action?: 'dig_start' | 'dig_cancel' | 'place';
}) => void;

describe('createGame move_request bridge', () => {
  const handlers = new Map<string, Set<MoveHandler>>();

  beforeEach(() => {
    handlers.clear();
    vi.resetModules();

    // mock phaser：捕获 game.events.on 注册；Scene 基类 noop
    vi.doMock('phaser', () => {
      const fakeGame = {
        events: {
          on: (name: string, cb: MoveHandler) => {
            if (!handlers.has(name)) handlers.set(name, new Set());
            handlers.get(name)!.add(cb);
          },
        },
      };
      class Scene {
        constructor(_cfg?: unknown) {}
      }
      class GameObjects {
        static Rectangle = class {};
        static Arc = class {};
      }
      const Phaser = {
        AUTO: 'AUTO',
        Game: class {
          events = fakeGame.events;
          constructor(_cfg: unknown) {}
        },
        Scene,
        GameObjects,
        Scale: { RESIZE: 'RESIZE' },
        Math: { Linear: (a: number, _b: number, _t: number) => a },
      };
      return { default: Phaser };
    });

    // mock runtime：捕获 requestMove 调用
    vi.doMock('../runtime', () => ({
      runtime: { requestMove: vi.fn(), requestVoxel: vi.fn() },
    }));
    // mock mirror（仅类型依赖，无行为）
    vi.doMock('../world-mirror', () => ({
      WorldMirror: class {},
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('注册 client:move_request 监听并转发到 runtime.requestMove', async () => {
    const { createGame } = await import('../main');
    const fakeMirror = {} as Parameters<typeof createGame>[1];
    createGame({} as HTMLElement, fakeMirror);

    const listeners = handlers.get('client:move_request');
    expect(listeners).toBeDefined();
    expect(listeners!.size).toBe(1);

    const { runtime } = await import('../runtime');
    const payload = { x: 7, y: 9 };
    for (const cb of listeners!) cb(payload);
    expect(runtime.requestMove).toHaveBeenCalledWith(7, 9);
  });

  it('forwards voxel gestures through the runtime without adding control fields', async () => {
    const { createGame } = await import('../main');
    createGame({} as HTMLElement, {} as Parameters<typeof createGame>[1]);
    const listeners = handlers.get('client:voxel_request');
    expect(listeners?.size).toBe(1);
    for (const cb of listeners!) cb({ action: 'dig_start', x: 7, y: 9 });
    const { runtime } = await import('../runtime');
    expect(runtime.requestVoxel).toHaveBeenCalledWith('dig_start', 7, 9);
    expect(runtime.requestMove).not.toHaveBeenCalled();
  });
});
