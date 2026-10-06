/**
 * client/src/game/render/actors.test.ts — R2 位移推断回归钉。
 * sim 侧 facing/anim 现硬编码（ws.py "s"/"idle"）——表现层推断纯前端职责；
 * sim 真供数日切协议字段的缝已留（MirrorActor 的 facing/anim 键直接读）。
 */
import { describe, expect, it } from 'vitest';
import { inferFacing, inferAnim } from './actors';

describe('inferFacing', () => {
  it.each([
    [0, 0, 's'], // 无位移保持默认朝南
    [1, 0, 'e'],
    [-1, 0, 'w'],
    [0, -1, 'n'],
    [0, 1, 's'],
    [1, 1, 's'], // 对角取主导轴（|dy|≥|dx| 取 y 轴）
    [-2, 1, 'w'], // 主导轴 x
  ])('(%i,%i)→%s', (dx, dy, want) => {
    expect(inferFacing(dx, dy)).toBe(want);
  });
});

describe('inferAnim', () => {
  it('位置变化=walk，不变=idle', () => {
    expect(inferAnim({ x: 1, y: 1 }, { x: 2, y: 1 })).toBe('walk');
    expect(inferAnim({ x: 1, y: 1 }, { x: 1, y: 1 })).toBe('idle');
  });
});
