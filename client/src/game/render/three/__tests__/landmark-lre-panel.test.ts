import { expect, it } from 'vitest';
import { explodeStageText } from '../landmark-lre-panel';

/** 拆解阶段文案必须与 vendored `setExplodePercentage` 的四段 smoothstep 对齐：
 *  0–25 一阶、25–50 二阶、50–75 三阶、75–100 四阶。文案错了玩家会以为
 *  滑块没生效（部件已经在动，字还停在上一阶）。 */
it('labels the four explode stages at the same thresholds the vendor uses', () => {
  expect(explodeStageText(0)).toContain('闭锁');
  expect(explodeStageText(1)).toContain('一阶');
  expect(explodeStageText(25)).toContain('一阶');
  expect(explodeStageText(26)).toContain('二阶');
  expect(explodeStageText(50)).toContain('二阶');
  expect(explodeStageText(51)).toContain('三阶');
  expect(explodeStageText(75)).toContain('三阶');
  expect(explodeStageText(76)).toContain('四阶');
  expect(explodeStageText(100)).toContain('四阶');
});

it('keeps the stage monotonic as the slider is dragged', () => {
  const order = ['闭锁', '一阶', '二阶', '三阶', '四阶'];
  let last = 0;
  for (let percent = 0; percent <= 100; percent++) {
    const text = explodeStageText(percent);
    const index = order.findIndex((word) => text.includes(word));
    expect(index).toBeGreaterThanOrEqual(last);
    last = index;
  }
});
