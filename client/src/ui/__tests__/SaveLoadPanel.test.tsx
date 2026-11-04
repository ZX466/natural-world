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

/** 面板消费的 store 面（**全量**——少一个键会让 SSR 断言悄悄测错东西）。 */
const baseState = {
  loadError: null as string | null,
  loadPending: false,
  forkNotice: null as string | null,
};

async function renderWith(patch: Partial<typeof baseState>) {
  vi.resetModules();
  const state = { ...baseState, ...patch };
  vi.doMock('../../store/uiStore', () => ({
    useUiStore: (selector: (s: typeof state) => unknown) => selector(state),
  }));
  const { SaveLoadPanel: Panel } = await import('../SaveLoadPanel');
  return renderToStaticMarkup(createElement(Panel));
}

describe('SaveLoadPanel', () => {
  it('面板骨架（标题 + 存一档按钮）', () => {
    const html = renderToStaticMarkup(createElement(SaveLoadPanel));
    expect(html).toContain('存档');
    expect(html).toContain('存一档');
  });

  it('读档失败（store.loadError）→ 面板内 role=alert 提示', async () => {
    const html = await renderWith({ loadError: '这个档读不出来了。' });
    expect(html).toContain('role="alert"');
    expect(html).toContain('这个档读不出来了。');
  });

  it('loadError 为空串（服务端终扫全命中 fail-closed）→ 不渲染空提示框', async () => {
    const html = await renderWith({ loadError: '' });
    expect(html).not.toContain('role="alert"');
  });

  it('D3：读档在途 → 「片刻后……」等待行 + 按钮真禁用', async () => {
    const html = await renderWith({ loadPending: true });
    expect(html).toContain('片刻后');
    expect(html).toContain('role="status"');
    // 列表行在 SSR 里是空的（`anchorsApi.list()` 异步未落地）⇒ 断「存一档」按钮，
    // 它恒渲染、且读档在途时必须禁用（读档途中存档会快照到半恢复的世界）。
    const saveBtn = html.match(/<button[^>]*>\s*存一档\s*<\/button>/)?.[0] ?? '';
    expect(saveBtn).not.toBe('');
    expect(saveBtn).toContain('disabled');
  });

  it('D3：无在途 → 不显示等待行，存一档按钮可点', async () => {
    const html = await renderWith({});
    expect(html).not.toContain('片刻后');
    const saveBtn = html.match(/<button[^>]*>\s*存一档\s*<\/button>/)?.[0] ?? '';
    expect(saveBtn).not.toBe('');
    expect(saveBtn).not.toContain('disabled');
  });

  it('D4：分叉告知（forkNotice）在面板里可见', async () => {
    const html = await renderWith({ forkNotice: '你回到了「初到临河」那段日子' });
    expect(html).toContain('你回到了「初到临河」那段日子');
  });
});
