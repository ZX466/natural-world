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
  chatter: [] as { name: string | null; content: string }[],
  plans: [] as { rtoken: string; text: string }[],
  impulseError: null as string | null,
  lastImpulseCue: null as string | null,
};

describe('uiStore 街谈巷议（批次 D10/D12）', () => {
  beforeEach(() => {
    useUiStore.setState(RESET);
  });

  it('pushChatter 追加且不可变（新数组）', () => {
    useUiStore.getState().pushChatter('赵铁柱', '这事我有点犯嘀咕。');
    const before = useUiStore.getState().chatter;
    useUiStore.getState().pushChatter(null, '先磨蹭一会儿吧。');
    const after = useUiStore.getState().chatter;
    expect(after).toEqual([
      { name: '赵铁柱', content: '这事我有点犯嘀咕。' },
      { name: null, content: '先磨蹭一会儿吧。' },
    ]);
    expect(before).not.toBe(after);
  });

  it('chatter 环形上限：超过 CHATTER_CAP 丢最旧', () => {
    for (let i = 0; i <= CHATTER_CAP; i += 1) {
      useUiStore.getState().pushChatter(null, String(i));
    }
    const chatter = useUiStore.getState().chatter;
    expect(chatter).toHaveLength(CHATTER_CAP);
    expect(chatter[0]?.content).toBe('1');
  });

  it('monologues 与 chatter 互不污染（分流面独立）', () => {
    useUiStore.getState().pushMonologue('thought', '心里话');
    useUiStore.getState().pushChatter('李阿婆', '街上的嘟囔');
    expect(useUiStore.getState().monologues).toEqual([{ form: 'thought', content: '心里话' }]);
    expect(useUiStore.getState().chatter).toEqual([{ name: '李阿婆', content: '街上的嘟囔' }]);
  });

  it('replaceChatter 整组替换：重连快照不叠加重复行', () => {
    useUiStore.getState().pushChatter('赵铁柱', '先说的一句。');
    useUiStore.getState().pushChatter('李阿婆', '街上很静。');
    // 快照带的是「最近 N 条」的完整投影，不是增量：重复回放会让同一句叠两遍。
    useUiStore.getState().replaceChatter([
      { name: '赵铁柱', content: '先说的一句。' },
      { name: '李阿婆', content: '街上很静。' },
    ]);
    expect(useUiStore.getState().chatter).toEqual([
      { name: '赵铁柱', content: '先说的一句。' },
      { name: '李阿婆', content: '街上很静。' },
    ]);
  });

  it('replaceChatter 保留环形上限', () => {
    const many = Array.from({ length: CHATTER_CAP + 3 }, (_, i) => ({
      name: null,
      content: String(i),
    }));
    useUiStore.getState().replaceChatter(many);
    const chatter = useUiStore.getState().chatter;
    expect(chatter).toHaveLength(CHATTER_CAP);
    expect(chatter[chatter.length - 1]?.content).toBe(String(CHATTER_CAP + 2));
  });
});
