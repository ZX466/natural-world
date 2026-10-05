/**
 * client/src/game/__tests__/clock.test.ts — R3 时钟推进器回归钉。
 * 权威帧重同步 / 按速推进 / 暂停停走 / 速度切换。
 * 换算常量：GAME_SECONDS_PER_REAL_SECOND = 60（sim 1x = 60tps，DESIGN §10）。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { createClock } from '../clock';
import { useUiStore } from '../../store/uiStore';

const tick = (ms: number) => vi.advanceTimersByTime(ms);

describe('createClock', () => {
  beforeEach(() => {
    useUiStore.getState().setPaused(false);
    useUiStore.getState().setSpeed(1);
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it('apply 权威帧立即重同步 store', () => {
    const clock = createClock();
    clock.apply({ day: 3, hour: 14, minute: 25, phase: 'day', is_market_day: false });
    const t = useUiStore.getState().gameClock;
    expect(t?.day).toBe(3);
    expect(t?.hour).toBe(14);
    expect(t?.minute).toBe(25);
    clock.stop();
  });

  it('1x 下每真实秒推进 60 游戏秒', () => {
    const clock = createClock();
    clock.apply({ day: 1, hour: 0, minute: 0, phase: 'night', is_market_day: true });
    clock.start();
    tick(60_000); // 60 真实秒 = 60×60 游戏秒 = 1 游戏小时
    const t = useUiStore.getState().gameClock;
    expect(t?.hour).toBe(1);
    expect(t?.day).toBe(1);
    clock.stop();
  });

  it('跨日推进（120 真实秒 @1x = 2 游戏小时 → day 2 01:00）', () => {
    const clock = createClock();
    clock.apply({ day: 1, hour: 23, minute: 0, phase: 'night', is_market_day: true });
    clock.start();
    tick(120_000);
    const t = useUiStore.getState().gameClock;
    expect(t?.day).toBe(2);
    expect(t?.hour).toBe(1);
    clock.stop();
  });

  it('跨日集市日重算（MARKET_DAY_INTERVAL=5 镜像）', () => {
    const clock = createClock();
    // day10 (10-1)%5=4 非集市 → 推 2h 到 day11 (11-1)%5=0 集市日翻转 true
    clock.apply({ day: 10, hour: 23, minute: 50, phase: 'night', is_market_day: false });
    clock.start();
    tick(60_000 * 2); // 2 游戏小时 → day 11 01:50
    const t = useUiStore.getState().gameClock;
    expect(t?.day).toBe(11);
    expect(t?.isMarketDay).toBe(true);
    clock.stop();
  });

  it('paused 时钟停走', () => {
    const clock = createClock();
    clock.apply({ day: 1, hour: 5, minute: 0, phase: 'dawn', is_market_day: true });
    clock.start();
    useUiStore.getState().setPaused(true);
    tick(30_000);
    const t = useUiStore.getState().gameClock;
    expect(t?.hour).toBe(5);
    expect(t?.minute).toBe(0);
    clock.stop();
  });

  it('16x 加速（15 真实秒 = 15×16 游戏分 = 4 游戏小时）', () => {
    const clock = createClock();
    clock.apply({ day: 1, hour: 0, minute: 0, phase: 'night', is_market_day: true });
    clock.start();
    useUiStore.getState().setSpeed(16);
    tick(15_000);
    const t = useUiStore.getState().gameClock;
    expect(t?.hour).toBe(4);
    clock.stop();
  });

  it('stop 后不再推进', () => {
    const clock = createClock();
    clock.apply({ day: 1, hour: 0, minute: 0, phase: 'night', is_market_day: true });
    clock.start();
    clock.stop();
    tick(60_000);
    expect(useUiStore.getState().gameClock?.hour).toBe(0);
  });
});
