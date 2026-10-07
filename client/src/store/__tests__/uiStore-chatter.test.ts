/**
 * client/src/store/__tests__/uiStore-chatter.test.ts — 批次 D10 街谈巷议钉。
 *
 * 村民 bubble（公开自语）与陈默心声（thought/plan）分流：
 * - pushMonologue 保持三形态入 monologues（既有行为零回归）；
 * - pushChatter 新面：村民公开嘟囔进 chatter 环形缓冲（独立 CAP）；
 * - runtime 路由：monologue(bubble) → chatter，thought/plan → monologues。
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { CHATTER_CAP, useUiStore } from '../uiStore';

const RESET = {
  monologues: [] as { form: 'bubble' | 'thought' | 'plan'; content: string }[],
  chatter: [] as string[],
  plans: [] as { rtoken: string; text: string }[],
  impulseError: null as string | null,
  lastImpulseCue: null as string | null,
};

describe('uiStore 街谈巷议（批次 D10）', () => {
  beforeEach(() => {
    useUiStore.setState(RESET);
  });

  it('pushChatter 追加且不可变（新数组）', () => {
    useUiStore.getState().pushChatter('这事我有点犯嘀咕。');
    const before = useUiStore.getState().chatter;
    useUiStore.getState().pushChatter('先磨蹭一会儿吧。');
    const after = useUiStore.getState().chatter;
    expect(after).toEqual(['这事我有点犯嘀咕。', '先磨蹭一会儿吧。']);
    expect(before).not.toBe(after);
  });

  it('chatter 环形上限：超过 CHATTER_CAP 丢最旧', () => {
    for (let i = 0; i <= CHATTER_CAP; i += 1) {
      useUiStore.getState().pushChatter(String(i));
    }
    const chatter = useUiStore.getState().chatter;
    expect(chatter).toHaveLength(CHATTER_CAP);
    expect(chatter[0]).toBe('1');
  });

  it('monologues 与 chatter 互不污染（分流面独立）', () => {
    useUiStore.getState().pushMonologue('thought', '心里话');
    useUiStore.getState().pushChatter('街上的嘟囔');
    expect(useUiStore.getState().monologues).toEqual([{ form: 'thought', content: '心里话' }]);
    expect(useUiStore.getState().chatter).toEqual(['街上的嘟囔']);
  });
});
