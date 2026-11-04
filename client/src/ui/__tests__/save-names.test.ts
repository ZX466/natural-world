/**
 * client/src/ui/__tests__/save-names.test.ts — 存档默认名不撞名（主树 D6-②）。
 *
 * 缺陷：`SaveLoadPanel` 用 `游历 ${items.length + 1}` 起名 ⇒ 删掉任意一个存档后
 * 再存一档，编号回退到已被占用的值（两个同名档），玩家在列表里分不出哪个是新的。
 * 契约：默认名 = **现存「游历 N」里的最大 N + 1**，与列表长度无关，永不与现存档重名。
 */
import { describe, expect, it } from 'vitest';
import { nextSaveName } from '../save-names';

const named = (...names: string[]) => names.map((name, i) => ({ id: `a${i}`, name }));

describe('nextSaveName', () => {
  it('空列表 → 游历 1', () => {
    expect(nextSaveName([])).toBe('游历 1');
  });

  it('连续三个默认名 → 游历 4', () => {
    expect(nextSaveName(named('游历 1', '游历 2', '游历 3'))).toBe('游历 4');
  });

  it('删掉中间一个（游历 1、游历 3）→ 游历 4，不撞回游历 3', () => {
    // 这是原实现的真实故障：items.length + 1 = 3 ⇒ 与现存「游历 3」同名。
    expect(nextSaveName(named('游历 1', '游历 3'))).toBe('游历 4');
  });

  it('玩家自定义名不参与编号', () => {
    expect(nextSaveName(named('初到临河', '游历 1'))).toBe('游历 2');
  });

  it('存在被重命名成高编号的档（游历 9）→ 游历 10', () => {
    expect(nextSaveName(named('游历 1', '游历 9'))).toBe('游历 10');
  });

  it('「游历」后面不是数字（游历 外传）不算编号档', () => {
    expect(nextSaveName(named('游历 外传', '游历 1'))).toBe('游历 2');
  });
});
