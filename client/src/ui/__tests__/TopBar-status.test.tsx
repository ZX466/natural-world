import { beforeEach, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const state = vi.hoisted(() => ({
  wsStatus: 'open',
  gameClock: null,
  speed: 1,
  paused: false,
  combatActive: false,
  sessionAnchor: null as { name: string; story_label: string } | null,
  controlError: null as string | null,
}));
vi.mock('../../store/uiStore', () => ({
  useUiStore: (selector: (s: typeof state) => unknown) => selector(state),
}));
vi.mock('../../game/runtime', () => ({ runtime: { sendControl: vi.fn() } }));

import { TopBar } from '../TopBar';

const render = () =>
  renderToStaticMarkup(
    createElement(TopBar, {
      onOpenSettings: vi.fn(),
      onTogglePanel: vi.fn(),
      activePanel: null,
    }),
  );
beforeEach(() => {
  state.wsStatus = 'open';
  state.sessionAnchor = null;
  state.controlError = null;
});

it.each([
  ['connecting', '连接中'],
  ['reconnecting', '重连'],
  ['closed', '已断开，正在重试'],
])('shows a readable connection hint for %s', (status, label) => {
  state.wsStatus = status;
  const html = render();
  expect(html).toContain(label);
  expect(html).toContain('role="status"');
});

it('hides the connection hint while open', () => {
  expect(render()).not.toContain('data-connection-status');
});

it.each([
  ['open', '连接正常'],
  ['connecting', '连接中…'],
  ['reconnecting', '正在重连…'],
  ['closed', '已断开，正在重试'],
])('gives the status dot an accessible label for %s', (status, label) => {
  state.wsStatus = status;
  const dot = render().match(/<span[^>]*class="od-status [^"]*"[^>]*>/)?.[0];
  expect(dot).toContain('role="status"');
  expect(dot).toContain(`aria-label="${label}"`);
  expect(dot).toContain(`title="${label}"`);
});

it('D4：session_state.anchor 的档名显示在顶栏（游标指针此前被丢弃）', () => {
  state.sessionAnchor = { name: '初到临河', story_label: '第二日 · 清晨' };
  const html = render();
  expect(html).toContain('初到临河');
  expect(html).toContain('title="第二日 · 清晨"');
});

it('D4：无游标（连接首帧 / 非读档）→ 不渲染档名', () => {
  expect(render()).not.toContain('title="第');
});

it('D5：set_control 被拒 → 顶栏出 role=alert 文案', () => {
  state.controlError = '本来就没停。';
  const html = render();
  expect(html).toContain('role="alert"');
  expect(html).toContain('本来就没停。');
});

it('D5：无控制错误 → 不渲染 alert', () => {
  expect(render()).not.toContain('role="alert"');
});
