import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import type { WsStatus } from '../../net/ws';

const effect = vi.hoisted(() => vi.fn());
const state = vi.hoisted(() => ({
  wsStatus: 'open' as WsStatus,
  lastImpulseCue: null as string | null,
  impulseError: null as string | null,
  setLastImpulseCue: (cue: string | null) => {
    state.lastImpulseCue = cue;
  },
  setImpulseError: (message: string | null) => {
    state.impulseError = message;
  },
}));

vi.mock('react', async (original) => ({
  ...(await original<typeof import('react')>()),
  // 现有组件测试用 SSR；显式执行注册的 effect 验证计时与卸载清理，无新增 DOM 依赖。
  useEffect: effect,
}));
vi.mock('../../store/uiStore', () => ({
  useUiStore: Object.assign((selector: (s: typeof state) => unknown) => selector(state), {
    getState: () => state,
  }),
}));
vi.mock('../../game/runtime', () => ({ runtime: { sendImpulse: vi.fn() }, IMPULSE_MAX_LEN: 64 }));

import { ImpulseBar, submitImpulse } from '../ImpulseBar';

const confirmation = '这个念头，他听见了。';
const render = () => renderToStaticMarkup(createElement(ImpulseBar));
function runEffect(): (() => void) | undefined {
  expect(effect).toHaveBeenCalled();
  return (effect.mock.calls.at(-1)![0] as () => (() => void) | undefined)();
}

beforeEach(() => {
  vi.useFakeTimers();
  effect.mockClear();
  state.wsStatus = 'open';
  state.lastImpulseCue = null;
  state.impulseError = null;
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

it('renders an accessible confirmation only after the feedback cue arrives', () => {
  expect(render()).not.toContain(confirmation);
  state.setLastImpulseCue('accepted');
  const html = render();
  expect(html).toContain(confirmation);
  expect(html).toContain('role="status"');
  const visible = html.replace(/<[^>]*>/g, '');
  expect(visible).not.toMatch(/\b(ok|success|sent|200)\b/i);
  expect(visible).not.toMatch(/成功|已发送/);
});

it('rejects an offline submission through the existing error layer', () => {
  state.wsStatus = 'closed';
  state.setLastImpulseCue('accepted');
  const send = vi.fn();
  expect(submitImpulse('去街上看看', send, state)).toBe(false);
  expect(send).not.toHaveBeenCalled();
  const html = render();
  expect(html).toContain('话递不过去，四下里静得很。');
  expect(html).toContain('role="alert"');
  expect(html).not.toContain(confirmation);
});

it('clears the previous confirmation on the next submission', () => {
  state.setLastImpulseCue('accepted');
  expect(render()).toContain(confirmation);
  const send = vi.fn();
  expect(submitImpulse('再问一声', send, state)).toBe(true);
  expect(send).toHaveBeenCalledWith('再问一声');
  expect(render()).not.toContain(confirmation);
});

it('removes the confirmation after six seconds', () => {
  state.setLastImpulseCue('accepted');
  render();
  const cleanup = runEffect();
  vi.advanceTimersByTime(5999);
  expect(render()).toContain(confirmation);
  vi.advanceTimersByTime(1);
  expect(render()).not.toContain(confirmation);
  cleanup?.();
});

it('cancels the expiry timer on cleanup', () => {
  state.setLastImpulseCue('accepted');
  render();
  const cleanup = runEffect();
  expect(cleanup).toBeTypeOf('function');
  cleanup?.();
  vi.advanceTimersByTime(6000);
  expect(state.lastImpulseCue).toBe('accepted');
});
