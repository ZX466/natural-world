/**
 * client/src/ui/labels.ts — 叙事化时间标签的展示口径（契约 `anchors-api.md` §1.1）。
 *
 * `story_label` 在 calendar 未就绪时是**空串**（不是 null，字段必须存在）。
 * 空串直接渲染会留下一个永远弹不出内容的 `title=""` 或一行空 `<p>`，
 * 按契约显示「未标注」。
 */
export const UNLABELED_TIME = '未标注';

export function storyLabel(raw: string): string {
  return raw.trim() === '' ? UNLABELED_TIME : raw;
}
