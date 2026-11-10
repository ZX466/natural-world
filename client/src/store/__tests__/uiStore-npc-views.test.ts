import { beforeEach, describe, expect, it } from 'vitest';
import type { NpcView } from '../../net/protocol';
import { useUiStore } from '../uiStore';

const xiaoman: NpcView = {
  rtoken: 'rt_xiaoman',
  name: '小满',
  health: ['她夜里睡得不太安稳。'],
  bond: '她见了陈默会点点头。',
  knows: ['小满: 暗夜惊惧'],
};
const tiezhu: NpcView = {
  rtoken: 'rt_tiezhu',
  name: '赵铁柱',
  health: [],
  bond: '他记得陈默。',
  knows: [],
};

describe('uiStore npc_views projection', () => {
  beforeEach(() => useUiStore.setState({ npcViews: [] }));

  it('starts with no invented profiles', () => {
    expect(useUiStore.getInitialState().npcViews).toEqual([]);
  });

  it('replaces the whole snapshot and deduplicates tokens and narrative strings', () => {
    const store = useUiStore.getState();
    store.replaceNpcViews([tiezhu]);
    store.replaceNpcViews([
      xiaoman,
      { ...xiaoman, health: ['夜里醒得早。', '夜里醒得早。'], knows: ['旧事。', '旧事。'] },
    ]);
    expect(useUiStore.getState().npcViews).toEqual([
      { ...xiaoman, health: ['夜里醒得早。'], knows: ['旧事。'] },
    ]);
    store.replaceNpcViews([]);
    expect(useUiStore.getState().npcViews).toEqual([]);
  });

  it('merges complete changed rows by token without retaining withdrawn narratives', () => {
    const store = useUiStore.getState();
    store.replaceNpcViews([xiaoman, tiezhu]);
    const before = useUiStore.getState().npcViews;
    const changed = { ...xiaoman, health: [], knows: [], bond: '她愿意多说几句话。' };
    store.mergeNpcViews([changed, changed]);
    expect(useUiStore.getState().npcViews).toEqual([changed, tiezhu]);
    expect(before).toEqual([xiaoman, tiezhu]);
  });

  it('removes an explicit token idempotently while an empty delta preserves profiles', () => {
    const store = useUiStore.getState();
    store.replaceNpcViews([xiaoman, tiezhu]);
    store.mergeNpcViews([]);
    expect(useUiStore.getState().npcViews).toEqual([xiaoman, tiezhu]);
    store.mergeNpcViews([
      { rtoken: xiaoman.rtoken, op: 'remove' },
      { rtoken: xiaoman.rtoken, op: 'remove' },
      { rtoken: 'rt_unknown', op: 'remove' },
    ]);
    expect(useUiStore.getState().npcViews).toEqual([tiezhu]);
  });

  it('applies delta rows in order, including remove then reappear', () => {
    const store = useUiStore.getState();
    store.replaceNpcViews([xiaoman]);
    store.mergeNpcViews([{ rtoken: xiaoman.rtoken, op: 'remove' }, tiezhu, xiaoman]);
    expect(useUiStore.getState().npcViews).toEqual([tiezhu, xiaoman]);
    store.mergeNpcViews([xiaoman, { rtoken: xiaoman.rtoken, op: 'remove' }]);
    expect(useUiStore.getState().npcViews).toEqual([tiezhu]);
  });

  it('owns copies of the input narrative arrays', () => {
    const health = ['她夜里睡得不太安稳。'];
    const knows = ['小满: 暗夜惊惧'];
    useUiStore.getState().replaceNpcViews([{ ...xiaoman, health, knows }]);
    health.push('后来的话。');
    knows.push('后来的事。');
    expect(useUiStore.getState().npcViews).toEqual([xiaoman]);
  });
});
