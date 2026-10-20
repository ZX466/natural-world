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

const render = () => renderToStaticMarkup(createElement(TopBar, { onOpenSettings: vi.fn() }));
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
