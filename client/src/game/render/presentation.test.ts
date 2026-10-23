/**
 * client/src/game/render/presentation.test.ts — A 档画面降噪纯函数钉。
 *
 * 目标（用户 2026-10-20 反馈「人物聚在一起很混乱」）：
 * - 深度随脚底 y 增大（靠下的人压住靠上的人，消除同层互压错觉）
 * - 名字/气泡永远在精灵之上
 * - 名字只在主角附近显示（远端 50 个标签是最大噪声源）
 * - 同格多人按稳定顺序分配视觉偏移（逻辑坐标不动）
 */
import { describe, expect, it } from 'vitest';
import {
  ACTOR_DEPTH_BASE,
  ACTOR_FRAME_HEIGHT,
  BUBBLE_GAP,
  LABEL_GAP,
  NAME_LABEL_RADIUS,
  NIGHT_OVERLAY_DEPTH,
  ISO_DEPTH,
  aboveSurface,
  STACK_OFFSETS,
  actorDepth,
  assignStackOffsets,
  bubbleDepth,
  bubbleY,
  labelDepth,
  labelY,
  manhattan,
  shouldShowNameLabel,
} from './presentation';
import { depthKey } from './iso';

describe('actorDepth（脚底 y 排序）', () => {
  it('靠下（y 大）的人深度更大，画在上层', () => {
    expect(actorDepth(20)).toBeGreaterThan(actorDepth(10));
  });

  it('深度落在 [BASE, 夜幕层) 区间内——角色必须被夜晚/雨天遮罩压暗', () => {
    // 地图最大脚底 y = 100 格 × 16px = 1600px；夜幕层 depth=100（WorldScene）
    expect(actorDepth(0)).toBe(ACTOR_DEPTH_BASE);
    expect(actorDepth(0)).toBeGreaterThanOrEqual(ACTOR_DEPTH_BASE);
    expect(actorDepth(1600)).toBeLessThan(NIGHT_OVERLAY_DEPTH);
    expect(actorDepth(1600)).toBeGreaterThan(actorDepth(800));
  });

  it('同格两人深度相同（再由偏移与绘制顺序区分）', () => {
    expect(actorDepth(7)).toBe(actorDepth(7));
  });
});

describe('labelDepth / bubbleDepth', () => {
  it('名字与气泡都在所有精灵之上，气泡在名字之上，且都在夜幕层之下', () => {
    const d = actorDepth(33);
    expect(labelDepth(33)).toBeGreaterThan(d);
    expect(bubbleDepth(33)).toBeGreaterThan(labelDepth(33));
    expect(labelDepth(33)).toBeGreaterThan(actorDepth(1600));
    expect(bubbleDepth(1600)).toBeLessThan(NIGHT_OVERLAY_DEPTH);
  });
});

describe('iso presentation bands', () => {
  it('puts labels and bubbles above the world, then rain and night above all text', () => {
    const worldTop = depthKey(139, 99) + 2;
    expect(labelDepth(0, 'iso')).toBeGreaterThan(worldTop);
    expect(bubbleDepth(0, 'iso')).toBeGreaterThan(labelDepth(10000, 'iso'));
    expect(ISO_DEPTH.RAIN).toBeGreaterThan(bubbleDepth(10000, 'iso'));
    expect(ISO_DEPTH.NIGHT).toBe(ISO_DEPTH.RAIN + 1);
    expect(ISO_DEPTH).toEqual({ LABEL: 300000, BUBBLE: 310000, RAIN: 400000, NIGHT: 400001 });
  });

  it('lifts from the projected surface in screen pixels while retaining flat formulas', () => {
    expect(aboveSurface(100, 32, 6, 3)).toBe(66);
    expect(aboveSurface(100, 16, 20, 4)).toBe(79);
    expect(labelDepth(100, 'flat')).toBe(labelDepth(100));
    expect(bubbleDepth(100, 'flat')).toBe(bubbleDepth(100));
  });
});

describe('shouldShowNameLabel（主角邻域才显示名字）', () => {
  it('半径内显示、半径外隐藏、边界含等号', () => {
    expect(shouldShowNameLabel(0)).toBe(true);
    expect(shouldShowNameLabel(NAME_LABEL_RADIUS)).toBe(true);
    expect(shouldShowNameLabel(NAME_LABEL_RADIUS + 1)).toBe(false);
  });

  it('可传入更小半径', () => {
    expect(shouldShowNameLabel(3, 2)).toBe(false);
    expect(shouldShowNameLabel(2, 2)).toBe(true);
  });
});

describe('manhattan', () => {
  it('计算逻辑格曼哈顿距离', () => {
    expect(manhattan({ x: 3, y: 4 }, { x: 3, y: 4 })).toBe(0);
    expect(manhattan({ x: 0, y: 0 }, { x: 3, y: 4 })).toBe(7);
  });
});

describe('labelY / bubbleY（头顶锚点）', () => {
  it('名字在精灵头顶之上（精灵 32px 高，脚底为原点）', () => {
    // 脚底 y=100 → 头顶 68 → 名字基线 66
    expect(labelY(100)).toBe(100 - ACTOR_FRAME_HEIGHT - LABEL_GAP);
    expect(labelY(100)).toBeLessThan(100 - ACTOR_FRAME_HEIGHT);
  });

  it('气泡在名字之上（y 更小）', () => {
    expect(bubbleY(100)).toBeLessThan(labelY(100));
    expect(bubbleY(100)).toBe(100 - ACTOR_FRAME_HEIGHT - BUBBLE_GAP);
  });

  it('锚点随脚底平移（相对偏移恒定）', () => {
    expect(labelY(300) - labelY(100)).toBe(200);
    expect(bubbleY(300) - bubbleY(100)).toBe(200);
  });
});

describe('assignStackOffsets（同格错位）', () => {
  it('独占一格的 actor 无偏移', () => {
    const offsets = assignStackOffsets([{ rtoken: 'a', x: 2, y: 3 }]);
    expect(offsets.get('a')).toEqual({ dx: 0, dy: 0 });
  });

  it('不同格的人互不影响，全部无偏移', () => {
    const offsets = assignStackOffsets([
      { rtoken: 'a', x: 2, y: 3 },
      { rtoken: 'b', x: 3, y: 3 },
      { rtoken: 'c', x: 2, y: 4 },
    ]);
    expect([...offsets.values()]).toEqual([
      { dx: 0, dy: 0 },
      { dx: 0, dy: 0 },
      { dx: 0, dy: 0 },
    ]);
  });

  it('同格两人获得两个不同的偏移，且与输入顺序无关', () => {
    const forward = assignStackOffsets([
      { rtoken: 'a', x: 5, y: 5 },
      { rtoken: 'b', x: 5, y: 5 },
    ]);
    const reverse = assignStackOffsets([
      { rtoken: 'b', x: 5, y: 5 },
      { rtoken: 'a', x: 5, y: 5 },
    ]);
    expect(forward.get('a')).toEqual(reverse.get('a'));
    expect(forward.get('b')).toEqual(reverse.get('b'));
    expect(forward.get('a')).not.toEqual(forward.get('b'));
    expect(forward.get('a')).toEqual(STACK_OFFSETS[0]);
    expect(forward.get('b')).toEqual(STACK_OFFSETS[1]);
  });

  it('同格超过偏移表容量时循环复用，仍确定性', () => {
    const actors = Array.from({ length: STACK_OFFSETS.length + 2 }, (_, i) => ({
      rtoken: `n${String(i).padStart(2, '0')}`,
      x: 1,
      y: 1,
    }));
    const offsets = assignStackOffsets(actors);
    expect(offsets.size).toBe(actors.length);
    expect(offsets.get('n00')).toEqual(STACK_OFFSETS[0]);
    expect(offsets.get(`n${String(STACK_OFFSETS.length).padStart(2, '0')}`)).toEqual(
      STACK_OFFSETS[0],
    );
  });

  it('偏移量限制在 6px 内（不让人明显离开脚下格子）', () => {
    for (const o of STACK_OFFSETS) {
      expect(Math.abs(o.dx)).toBeLessThanOrEqual(6);
      expect(Math.abs(o.dy)).toBeLessThanOrEqual(6);
    }
  });
});
