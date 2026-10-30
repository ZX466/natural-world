import { beforeEach, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const state = vi.hoisted(() => ({
  wsStatus: 'open',
  gameClock: null,
  speed: 1,
  paused: false,
  combatActive: false,
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
