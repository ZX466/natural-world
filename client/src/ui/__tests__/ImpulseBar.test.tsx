/**
 * client/src/ui/__tests__/ImpulseBar.test.tsx — 批次 A UI 钉（SSR 断言，无 jsdom）。
 *
 * ImpulseBar：底部念头注入条——输入 + 回车/按钮发送（走 runtime.sendImpulse），
 * cue 视觉反馈（四态边色）+ impulseError 文案。
 * zustand v5 SSR 取 getInitialState（setState 不可见）→ store 整体 mock 成
 * vi.hoisted 可变状态；runtime 同 mock（补 IMPULSE_MAX_LEN 导出）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const storeState = vi.hoisted(() => ({
  lastImpulseCue: null as string | null,
  impulseError: null as string | null,
}));

vi.mock('../../store/uiStore', () => ({
  useUiStore: (selector: (s: typeof storeState) => unknown) => selector(storeState),
}));

const sendImpulse = vi.fn();

vi.mock('../../game/runtime', () => ({
  runtime: { sendImpulse: (...a: unknown[]) => sendImpulse(...a) },
  IMPULSE_MAX_LEN: 64,
}));

import { ImpulseBar, submitImpulse } from '../ImpulseBar';

function renderBar(): string {
  return renderToStaticMarkup(createElement(ImpulseBar));
}

describe('ImpulseBar', () => {
  beforeEach(() => {
    sendImpulse.mockClear();
    storeState.lastImpulseCue = null;
    storeState.impulseError = null;
  });

  it('渲染输入框 + 发送按钮', () => {
    const html = renderBar();
    expect(html).toContain('placeholder="往陈默心里放一个念头…"');
    expect(html).toContain('发送');
  });

  it('impulseError 非空 → 显示文案', () => {
    storeState.impulseError = '这个念头进不去。';
    expect(renderBar()).toContain('这个念头进不去。');
  });

  it('cue 四态 → data-cue 属性（视觉反馈钩子）', () => {
    storeState.lastImpulseCue = 'hesitation';
    expect(renderBar()).toContain('data-cue="hesitation"');
    storeState.lastImpulseCue = 'resistance';
    expect(renderBar()).toContain('data-cue="resistance"');
  });

  it('提交逻辑：trim 空白即拒发（不发空帧）', () => {
    submitImpulse('   ', (t) => sendImpulse(t));
    expect(sendImpulse).not.toHaveBeenCalled();
    submitImpulse('  今天去集市看看  ', (t) => sendImpulse(t));
    expect(sendImpulse).toHaveBeenCalledWith('今天去集市看看');
  });
});
