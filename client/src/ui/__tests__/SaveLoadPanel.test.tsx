/**
 * client/src/ui/__tests__/SaveLoadPanel.test.tsx — 批次 D4 面板钉（SSR 断言）。
 * 渲染存档列表（名称+叙事标签）、新建存档、读档按钮（回调契约）、删除。
 */
import { describe, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

vi.mock('../../net/anchorsApi', () => ({
  anchorsApi: {
    list: vi.fn().mockResolvedValue([
      {
        id: 'a1',
        name: '第一天夜里',
        story_label: '第 1 天 夜晚',
        protected: false,
        created_at: '2026-10-06T00:00:00Z',
      },
    ]),
    create: vi.fn(),
    remove: vi.fn(),
    current: vi.fn().mockResolvedValue(null),
  },
}));

import { SaveLoadPanel } from '../SaveLoadPanel';

describe('SaveLoadPanel', () => {
  it('面板骨架（标题 + 存一档按钮）', () => {
    const html = renderToStaticMarkup(createElement(SaveLoadPanel));
    expect(html).toContain('存档');
    expect(html).toContain('存一档');
  });

  it('读档失败（store.loadError）→ 面板内 role=alert 提示', async () => {
    vi.resetModules();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: (selector: (s: { loadError: string | null }) => unknown) =>
        selector({ loadError: '这个档读不出来了。' }),
    }));
    const { SaveLoadPanel: Panel } = await import('../SaveLoadPanel');
    const html = renderToStaticMarkup(createElement(Panel));
    expect(html).toContain('role="alert"');
    expect(html).toContain('这个档读不出来了。');
  });

  it('loadError 为空串（服务端终扫全命中 fail-closed）→ 不渲染空提示框', async () => {
    vi.resetModules();
    vi.doMock('../../store/uiStore', () => ({
      useUiStore: (selector: (s: { loadError: string | null }) => unknown) =>
        selector({ loadError: '' }),
    }));
    const { SaveLoadPanel: Panel } = await import('../SaveLoadPanel');
    const html = renderToStaticMarkup(createElement(Panel));
    expect(html).not.toContain('role="alert"');
  });
});
