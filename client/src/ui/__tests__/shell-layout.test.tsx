import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, expect, it, vi } from 'vitest';

vi.mock('../CanvasHost', () => ({ CanvasHost: () => createElement('div', { 'aria-label': '游戏画面' }) }));
vi.mock('../../game/runtime', () => ({
  IMPULSE_MAX_LEN: 64,
  runtime: { sendControl: vi.fn(), sendImpulse: vi.fn(), loadAnchor: vi.fn() },
}));

import App from '../../App';
import { ImpulseBar } from '../ImpulseBar';

afterEach(() => vi.unstubAllGlobals());

it('shows the journal on desktop without permanently mounting a separate save column', () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true }));
  const html = renderToStaticMarkup(createElement(App));
  expect(html).toContain('陈默心里还很安静。');
  expect(html).not.toContain('还没有存档。');
  expect(html).toContain('aria-controls="side-panel"');
  expect(html).toContain('aria-expanded="true"');
});

it('starts compact screens with the world available and both side-panel contents closed', () => {
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  const html = renderToStaticMarkup(createElement(App));
  expect(html).toContain('游戏画面');
  expect(html).not.toContain('陈默心里还很安静。');
  expect(html).not.toContain('还没有存档。');
  expect(html).toContain('aria-expanded="false"');
});

it('gives the impulse input a persistent accessible name and retains its length limit', () => {
  const html = renderToStaticMarkup(createElement(ImpulseBar));
  expect(html).toContain('aria-label="往陈默心里放一个念头"');
  expect(html).toContain('maxLength="64"');
});
