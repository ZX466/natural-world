/**
 * client/src/ui/__tests__/labels.test.ts — 叙事化时间标签的展示口径。
 *
 * 实测（2026-11-04 隔离库）：`anchors.py` 六处 `story_label` 都硬写空串
 * （calendar 尚未接线）。契约 `anchors-api.md` §1.1 要求前端对空串显示「未标注」。
 * 不处理的话顶栏挂一个弹不出内容的 `title=""`、面板多一行永远空的 `<p>`。
 */
import { describe, expect, it } from 'vitest';
import { storyLabel } from '../labels';

describe('storyLabel', () => {
  it('正常标签原样返回', () => {
    expect(storyLabel('第二日 · 清晨')).toBe('第二日 · 清晨');
  });

  it('空串（calendar 未就绪）→ 「未标注」', () => {
    expect(storyLabel('')).toBe('未标注');
  });

  it('纯空白视同空串（服务端未来可能给 " "）', () => {
    expect(storyLabel('   ')).toBe('未标注');
  });
});
