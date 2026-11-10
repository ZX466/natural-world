import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import type { NpcView } from '../../net/protocol';

const storeState = vi.hoisted(() => ({
  monologues: [],
  chatter: [],
  npcViews: [] as NpcView[],
}));

vi.mock('../../store/uiStore', () => ({
  useUiStore: (selector: (s: typeof storeState) => unknown) => selector(storeState),
}));

import { PanelHost } from '../PanelHost';

function renderPeople(): string {
  return (
    renderToStaticMarkup(createElement(PanelHost)).match(
      /<section aria-label="人物"[\s\S]*?<\/section>/,
    )?.[0] ?? ''
  );
}

describe('PanelHost 人物叙事', () => {
  beforeEach(() => {
    storeState.npcViews = [];
  });

  it('adds an empty third panel after voice and chatter, without invented profiles', () => {
    const html = renderToStaticMarkup(createElement(PanelHost));
    expect(html.indexOf('aria-label="人物"')).toBeGreaterThan(
      html.indexOf('aria-label="街谈巷议"'),
    );
    expect(renderPeople()).toContain('人物');
    expect(renderPeople()).not.toContain('<li');
  });

  it('renders each server narrative once and retains its wording', () => {
    storeState.npcViews = [
      {
        rtoken: 'rt_xiaoman',
        name: '小满',
        health: ['她夜里睡得不太安稳。', '她夜里睡得不太安稳。'],
        bond: '她见了陈默会点点头。',
        knows: ['小满: 暗夜惊惧', '小满: 暗夜惊惧', '她夜里睡得不太安稳。'],
      },
    ];
    const html = renderPeople();
    expect(html).toContain('小满');
    expect(html.split('她夜里睡得不太安稳。')).toHaveLength(2);
    expect(html.split('她见了陈默会点点头。')).toHaveLength(2);
    expect(html.split('小满: 暗夜惊惧')).toHaveLength(2);
    expect(html).not.toContain('rt_xiaoman');
  });

  it('keeps absent health and knowledge blank and uses a natural name fallback', () => {
    storeState.npcViews = [{ rtoken: 'rt_unnamed', health: [], bond: '他记得陈默。', knows: [] }];
    const html = renderPeople();
    expect(html.replace(/<[^>]+>/g, '')).toBe('人物一位相识他记得陈默。');
    expect(html).not.toContain('rt_unnamed');
  });

  it('renders names and narratives as plain text instead of HTML', () => {
    storeState.npcViews = [
      {
        rtoken: 'rt_markup',
        name: '<img src=x onerror=alert(1)>',
        health: ['<script>bad()</script>'],
        bond: '<b>相识</b>',
        knows: ['<iframe src=x>旧事</iframe>'],
      },
    ];
    const html = renderPeople();
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
    expect(html).toContain('&lt;script&gt;bad()&lt;/script&gt;');
    expect(html).toContain('&lt;b&gt;相识&lt;/b&gt;');
    expect(html).toContain('&lt;iframe src=x&gt;旧事&lt;/iframe&gt;');
    expect(html).not.toMatch(/<(img|script|b|iframe)[\s>]/);
  });
});
