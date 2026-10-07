/**
 * client/src/ui/__tests__/PanelHost.test.tsx — 批次 A UI 钉（SSR 断言，无 jsdom）。
 *
 * PanelHost：右侧竖栏两块面板——心之声（独白流）+ 计划看板（有则展开无则收起）。
 * zustand v5 SSR 取 getInitialState（setState 不可见）→ store 整体 mock 成
 * vi.hoisted 可变状态。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const storeState = vi.hoisted(() => ({
  monologues: [] as { form: 'thought' | 'bubble' | 'plan'; content: string }[],
  chatter: [] as string[],
  plans: [] as { rtoken: string; text: string }[],
}));

vi.mock('../../store/uiStore', () => ({
  useUiStore: (selector: (s: typeof storeState) => unknown) => selector(storeState),
}));

import { PanelHost } from '../PanelHost';

function renderPanel(): string {
  return renderToStaticMarkup(createElement(PanelHost));
}

describe('PanelHost', () => {
  beforeEach(() => {
    storeState.monologues = [];
    storeState.chatter = [];
    storeState.plans = [];
  });

  it('空态：两块面板骨架可见', () => {
    const html = renderPanel();
    expect(html).toContain('心之声');
    expect(html).toContain('计划');
  });

  it('独白条目渲染（form 标签 + content）', () => {
    storeState.monologues = [
      { form: 'thought', content: '这话我记下了。' },
      { form: 'plan', content: '先去药铺看看。' },
    ];
    const html = renderPanel();
    expect(html).toContain('这话我记下了。');
    expect(html).toContain('先去药铺看看。');
  });

  it('计划看板：plans 非空 → 文本可见', () => {
    storeState.plans = [{ rtoken: 'r1', text: '今天先把菜浇了，再去集市。' }];
    expect(renderPanel()).toContain('今天先把菜浇了，再去集市。');
  });

  it('plans 空 → 看板收起（不渲染条目区）', () => {
    const html = renderPanel();
    expect(html).not.toContain('plan-item');
  });
});
