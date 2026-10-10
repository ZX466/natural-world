/**
 * client/src/store/__tests__/uiStore.test.ts — 批次 A 叙事状态钉。
 *
 * uiStore 新增三块叙事面（M4 协议消费端）：
 * - monologues：独白环形缓冲（上限 MONOLOGUE_CAP，丢最旧，不可变更新）；
 * - plans：计划看板（state_delta.plan 整组替换）；
 * - impulseError：impulse 入站 error 帧的玩家可见文案。
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { MONOLOGUE_CAP, useUiStore } from '../uiStore';

const RESET = {
  monologues: [] as { form: 'bubble' | 'thought' | 'plan'; content: string }[],
  plans: [] as { rtoken: string; text: string }[],
  impulseError: null as string | null,
  lastImpulseCue: null as string | null,
};

describe('uiStore 叙事状态（批次 A）', () => {
  beforeEach(() => {
    useUiStore.setState(RESET);
  });

  it('pushMonologue 追加条目且不可变（新数组）', () => {
    useUiStore.getState().pushMonologue('thought', '第一句');
    const before = useUiStore.getState().monologues;
    useUiStore.getState().pushMonologue('plan', '第二句');
    const after = useUiStore.getState().monologues;
    expect(after).toEqual([
      { form: 'thought', content: '第一句' },
      { form: 'plan', content: '第二句' },
    ]);
    expect(before).not.toBe(after);
  });

  it('环形上限：超过 MONOLOGUE_CAP 丢最旧', () => {
    for (let i = 0; i <= MONOLOGUE_CAP; i += 1) {
      useUiStore.getState().pushMonologue('thought', String(i));
    }
    const monologues = useUiStore.getState().monologues;
    expect(monologues).toHaveLength(MONOLOGUE_CAP);
    expect(monologues[0]?.content).toBe('1'); // "0" 被挤出
    expect(monologues[MONOLOGUE_CAP - 1]?.content).toBe(String(MONOLOGUE_CAP));
  });

  it('setPlans 整组替换（delta 即全量看板）', () => {
    useUiStore.getState().setPlans([{ rtoken: 'a', text: '旧计划' }]);
    useUiStore.getState().setPlans([{ rtoken: 'b', text: '新计划' }]);
    expect(useUiStore.getState().plans).toEqual([{ rtoken: 'b', text: '新计划' }]);
  });

  it('setImpulseError 置位与清空', () => {
    useUiStore.getState().setImpulseError('这个念头进不去。');
    expect(useUiStore.getState().impulseError).toBe('这个念头进不去。');
    useUiStore.getState().setImpulseError(null);
    expect(useUiStore.getState().impulseError).toBeNull();
  });

  it('setLastImpulseCue 置位（既有字段接通数据源）', () => {
    useUiStore.getState().setLastImpulseCue('hesitation');
    expect(useUiStore.getState().lastImpulseCue).toBe('hesitation');
  });
});
