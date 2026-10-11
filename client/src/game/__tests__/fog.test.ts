/**
 * client/src/game/__tests__/fog.test.ts — 批次 D17 视觉雾钉。
 *
 * WorldMirror 雾状态三行为（真实实现：world-mirror.ts 的 fog Set +
 * revealFog / applySnapshot 第四参 / reset 同治）：
 * - revealFog 并集语义（delta 增量多次到达不丢块、不重复）；
 * - applySnapshot 带 fog → 全量重置（重连/读档重同步）；不带 → 清空；
 * - reset 清雾（镜像重置面与 actors 同治）。
 */
import { describe, expect, it } from 'vitest';
import { WorldMirror } from '../world-mirror';

describe('WorldMirror 雾状态（D17）', () => {
  it('revealFog 并集：多次增量累积，不丢不重', () => {
    const m = new WorldMirror();
    m.revealFog([
      { cx: 0, cy: 0 },
      { cx: 1, cy: 0 },
      { cx: 0, cy: 0 },
    ]);
    expect(m.fog.size).toBe(2);
    expect(m.fog.has('0,0')).toBe(true);
    expect(m.fog.has('1,0')).toBe(true);
  });

  it('applySnapshot 带 fog → 全量重置为全集', () => {
    const m = new WorldMirror();
    m.revealFog([{ cx: 9, cy: 9 }]); // 旧态
    m.applySnapshot(
      [{ rtoken: 'r1', x: 0, y: 0, facing: 's', sprite: 'chenmo', anim: 'idle' }],
      [],
      undefined,
      {
        revealed: [
          { cx: 0, cy: 0 },
          { cx: 1, cy: 1 },
        ],
      },
    );
    expect(m.fog.size).toBe(2);
    expect(m.fog.has('9,9')).toBe(false);
  });

  it('applySnapshot 不带 fog → 清空（服务端旧版兼容面）', () => {
    const m = new WorldMirror();
    m.revealFog([{ cx: 3, cy: 3 }]);
    m.applySnapshot(
      [{ rtoken: 'r1', x: 0, y: 0, facing: 's', sprite: 'chenmo', anim: 'idle' }],
      [],
    );
    expect(m.fog.size).toBe(0);
  });

  it('reset 清雾（与 actors 同治）', () => {
    const m = new WorldMirror();
    m.revealFog([{ cx: 2, cy: 2 }]);
    m.reset();
    expect(m.fog.size).toBe(0);
    expect(m.resetCount).toBe(1);
  });
});
