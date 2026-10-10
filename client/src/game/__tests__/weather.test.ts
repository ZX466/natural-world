/**
 * client/src/game/__tests__/weather.test.ts — 批次 D7 天气视觉钉。
 * mirror.weather 状态 + setWeather；雨/阴的 ambient 档位。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../clock', () => ({ worldClock: { apply: vi.fn(), start: vi.fn(), stop: vi.fn() } }));

import { WorldMirror } from '../world-mirror';

describe('WorldMirror weather（批次 D7）', () => {
  let mirror: WorldMirror;

  beforeEach(() => {
    mirror = new WorldMirror();
  });

  it('初始 weather = clear/1.0', () => {
    expect(mirror.weather).toEqual({ visual: 'clear', ambientLight: 1.0 });
  });

  it('applySnapshot 消费 weather 帧', () => {
    mirror.applySnapshot(
      [{ rtoken: 'r1', x: 1, y: 1, facing: 's', sprite: 'villager', anim: 'idle' }],
      [],
      { visual: 'rain', ambientLight: 0.75 },
    );
    expect(mirror.weather.visual).toBe('rain');
    expect(mirror.weather.ambientLight).toBe(0.75);
  });

  it('setWeather 增量更新（state_delta 随行）', () => {
    mirror.setWeather({ visual: 'overcast', ambientLight: 0.9 });
    expect(mirror.weather.visual).toBe('overcast');
  });
});
