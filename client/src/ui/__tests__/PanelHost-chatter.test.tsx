/**
 * client/src/ui/PanelHost.test.tsx 批次 D10 追加钉 —— 街谈巷议节。
 *
 * 村民 bubble 分流到「街谈巷议」独立节（chatter 面板）；
 * 心之声只承载陈默的 thought/plan。
 * zustand v5 SSR 取 getInitialState（setState 不可见）→ store 整体 mock 成
 * vi.hoisted 可变状态。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const storeState = vi.hoisted(() => ({
  monologues: [] as { form: 'thought' | 'bubble' | 'plan'; content: string }[],
  chatter: [] as { name: string | null; content: string }[],
  plans: [] as { rtoken: string; text: string }[],
}));

vi.mock('../../store/uiStore', () => ({
  useUiStore: (selector: (s: typeof storeState) => unknown) => selector(storeState),
}));

import { PanelHost } from '../PanelHost';

function renderPanel(): string {
  return renderToStaticMarkup(createElement(PanelHost));
}

describe('PanelHost 街谈巷议（批次 D10）', () => {
  beforeEach(() => {
    storeState.monologues = [];
    storeState.chatter = [];
    storeState.plans = [];
  });

  it('空态：三块面板骨架可见', () => {
    const html = renderPanel();
    expect(html).toContain('心之声');
    expect(html).toContain('街谈巷议');
    expect(html).toContain('计划');
  });

  it('chatter 条目渲染在街谈巷议节（署名 + 内容）', () => {
    storeState.chatter = [
      { name: '赵铁柱', content: '这事我有点犯嘀咕。' },
      { name: null, content: '先磨蹭一会儿吧。' },
    ];
    const html = renderPanel();
    expect(html).toContain('赵铁柱：');
    expect(html).toContain('这事我有点犯嘀咕。');
    expect(html).toContain('先磨蹭一会儿吧。');
  });

  it('chatter 空 → 空态文案', () => {
    const html = renderPanel();
    expect(html).toContain('镇上还很安静。');
  });
});
