/**
 * client/src/ui/__tests__/PanelHost.test.tsx — 批次 A UI 钉（SSR 断言，无 jsdom）。
 *
 * PanelHost：右侧竖栏两块面板——心之声（陈默独白流）+ 街谈巷议（村民嘟囔）。
 * 计划看板已于 2026-10-26 退役（NPC defers 文本，行为已可见）。
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

describe('PanelHost', () => {
  beforeEach(() => {
    storeState.monologues = [];
    storeState.chatter = [];
    storeState.plans = [];
  });

  it('空态：只剩心之声与街谈巷议两块面板', () => {
    const html = renderPanel();
    expect(html).toContain('心之声');
    expect(html).toContain('街谈巷议');
    // 计划看板已退役：计划文本本来就在心之声里以「打算」出现，独立看板是重复面。
    expect(html).not.toContain('od-panel--plan');
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

  it('state_delta.plan 的 NPC 计划不再单独渲染（面板退役）', () => {
    storeState.plans = [{ rtoken: 'rt_2', text: '先去别处，等会儿再浇水。' }];
    const html = renderPanel();
    expect(html).not.toContain('先去别处，等会儿再浇水。');
    // 也不许挂进心之声——那是陈默的内心，不是 NPC 的打算。
    expect(html).not.toContain('打算');
  });
});
