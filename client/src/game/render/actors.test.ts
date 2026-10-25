/**
 * client/src/game/render/actors.test.ts — R2 位移推断回归钉 + 评审修复钉。
 * C-2：帧号按 17 列线性换算（chenmo.png 272×256），朝北 idle 必须是**非透明**站立帧。
 * H-2：walk 动画钟 moved 累加/idle 归 -1（修前写反循环死）。
 * H-3：零位移沿用 lastFacing（停下不转身）。
 */
import { describe, expect, it } from 'vitest';
import {
  inferFacing,
  advanceAnimClock,
  walkFrameFor,
  facingRow,
  CHENMO_SHEET,
  GOD_SHEET,
  GOD_SPRITE_KEYS,
} from './actors';

describe('inferFacing', () => {
  it.each([
    [1, 0, 's', 'e'],
    [-1, 0, 's', 'w'],
    [0, -1, 's', 'n'],
    [0, 1, 's', 's'],
    [1, 1, 's', 's'], // 对角取主导轴（|dy|≥|dx| 取 y 轴）
    [-2, 1, 's', 'w'], // 主导轴 x
  ])('(%i,%i) 上次=%s → %s', (dx, dy, last, want) => {
    expect(inferFacing(dx, dy, last as 'n' | 'e' | 's' | 'w')).toBe(want);
  });

  it('H-3：零位移沿用 lastFacing（停下不转身）', () => {
    expect(inferFacing(0, 0, 'n')).toBe('n');
    expect(inferFacing(0, 0, 'w')).toBe('w');
    expect(inferFacing(0, 0)).toBe('s'); // 无历史时默认朝南
  });
});

describe('advanceAnimClock（H-2 修复钉）', () => {
  it('moved 从 -1 起步归 0，随后逐帧累加', () => {
    expect(advanceAnimClock(-1, true, 16)).toBe(0);
    expect(advanceAnimClock(0, true, 16)).toBe(16);
    expect(advanceAnimClock(16, true, 16)).toBe(32);
  });
  it('静止归 -1（站立帧）', () => {
    expect(advanceAnimClock(32, false, 16)).toBe(-1);
  });
  it('连续 moved 时钟单调递增（循环不死）', () => {
    let c = -1;
    for (let i = 0; i < 5; i++) c = advanceAnimClock(c, true, 16);
    expect(c).toBe(64); // 0,16,32,48,64
  });
});

describe('陈默帧表（C-2 修复钉：17 列线性换算）', () => {
  it('站立帧 = row*17 + 1（col 1 = 步-站-步 中帧）', () => {
    expect(walkFrameFor(CHENMO_SHEET, 0, -1)).toBe(1); // 朝南站立
    expect(walkFrameFor(CHENMO_SHEET, 1, -1)).toBe(18); // 朝北站立（修前=4 全透明 → 主角消失）
    expect(walkFrameFor(CHENMO_SHEET, 2, -1)).toBe(35); // 朝东
    expect(walkFrameFor(CHENMO_SHEET, 3, -1)).toBe(52); // 朝西
  });
  it('walk 环在行内 0..2 循环，不跨行', () => {
    expect(walkFrameFor(CHENMO_SHEET, 1, 0)).toBe(17); // row1 col0
    expect(walkFrameFor(CHENMO_SHEET, 1, 150)).toBe(18);
    expect(walkFrameFor(CHENMO_SHEET, 1, 300)).toBe(19);
    expect(walkFrameFor(CHENMO_SHEET, 1, 450)).toBe(17); // 回卷
  });
  it('facingRow 映射（下/上/右/左 = 0/1/2/3）', () => {
    expect(facingRow('s')).toBe(0);
    expect(facingRow('n')).toBe(1);
    expect(facingRow('e')).toBe(2);
    expect(facingRow('w')).toBe(3);
  });
});

describe('walkFrameFor（D10：villager 4 列帧表）', () => {
  const VILLAGER = { cols: 4, framesPerRow: 4 } as const;

  it('站立帧 = row*4 + 0（col 0 站立）', () => {
    expect(walkFrameFor(VILLAGER, 0, -1)).toBe(0);
    expect(walkFrameFor(VILLAGER, 1, -1)).toBe(4);
    expect(walkFrameFor(VILLAGER, 3, -1)).toBe(12);
  });
  it('walk 环在行内 0..3 循环，不跨行', () => {
    expect(walkFrameFor(VILLAGER, 1, 0)).toBe(4);
    expect(walkFrameFor(VILLAGER, 1, 150)).toBe(5);
    expect(walkFrameFor(VILLAGER, 1, 300)).toBe(6);
    expect(walkFrameFor(VILLAGER, 1, 450)).toBe(7);
    expect(walkFrameFor(VILLAGER, 1, 600)).toBe(4); // 回卷
  });
  it('chenmo 几何经同一入口结果不变（单入口防两套换算漂移）', () => {
    const CHENMO = { cols: 17, framesPerRow: 3, standCol: 1 } as const;
    expect(walkFrameFor(CHENMO, 0, -1)).toBe(1);
    expect(walkFrameFor(CHENMO, 1, 150)).toBe(18);
  });
});

describe('GOD 古风外观池（2026-10-12 D1-D5 接入）', () => {
  it('几何 3 列 3 帧 standCol 1（48×128 产物实证）', () => {
    expect(GOD_SHEET).toEqual({ cols: 3, framesPerRow: 3, standCol: 1 });
  });
  it('池 17 张且 key 与后端 slug 同名（D4 红线：无军事/名人词面）', () => {
    expect(GOD_SPRITE_KEYS).toHaveLength(17);
    for (const banned of ['banshi', 'chicheng', 'gushou', 'zhuge', 'sima']) {
      expect(GOD_SPRITE_KEYS.some((k) => k.includes(banned))).toBe(false);
    }
  });
  it('GOD 站立 = row*3+1；走环行内 0..2 循环', () => {
    expect(walkFrameFor(GOD_SHEET, facingRow('s'), -1)).toBe(0 * 3 + 1);
    expect(walkFrameFor(GOD_SHEET, facingRow('n'), -1)).toBe(1 * 3 + 1);
    expect(walkFrameFor(GOD_SHEET, facingRow('e'), 0)).toBe(2 * 3 + 0);
    expect(walkFrameFor(GOD_SHEET, facingRow('e'), 150)).toBe(2 * 3 + 1);
    expect(walkFrameFor(GOD_SHEET, facingRow('e'), 300)).toBe(2 * 3 + 2);
    expect(walkFrameFor(GOD_SHEET, facingRow('e'), 450)).toBe(2 * 3 + 0); // 回卷
  });
});
