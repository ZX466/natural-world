/**
 * client/src/net/__tests__/ws-narrative.test.ts — 批次 A WS 分发扩展钉。
 *
 * dispatch 新增三个已定义但此前被 default 静默吞掉的消息类型：
 * monologue（narrative 通道独白）/ impulse_feedback（control 反馈）/ error。
 * 未知类型仍静默（versioning.md 铁律不回退）。
 */
import { describe, expect, it, vi } from 'vitest';
import type { WsCallbacks } from '../ws';
import { WsClient } from '../ws';
import type { WorldMirror } from '../../game/world-mirror';

function makeClient() {
  const cb: WsCallbacks = {
    onStatus: vi.fn(),
    onSnapshot: vi.fn(),
    onDelta: vi.fn(),
    onMonologue: vi.fn(),
    onImpulseFeedback: vi.fn(),
    onError: vi.fn(),
    onControlAck: vi.fn(),
  };
  const client = new WsClient('ws://test', {} as WorldMirror, cb);
  // dispatch 是私有方法；单测经类型断言直调（帧 JSON 字符串入）
  const dispatch = (raw: string): void =>
    (client as unknown as { dispatch(raw: string): void }).dispatch(raw);
  return { cb, dispatch };
}

describe('WsClient dispatch 叙事消息（批次 A）', () => {
  it('monologue → onMonologue（form/content 原样）', () => {
    const { cb, dispatch } = makeClient();
    dispatch(
      JSON.stringify({
        type: 'monologue',
        channel: 'narrative',
        v: '1.3',
        ws_seq: 0,
        form: 'thought',
        content: '这话我记下了。',
      }),
    );
    expect(cb.onMonologue).toHaveBeenCalledTimes(1);
    expect(cb.onMonologue).toHaveBeenCalledWith({
      type: 'monologue',
      channel: 'narrative',
      v: '1.3',
      ws_seq: 0,
      form: 'thought',
      content: '这话我记下了。',
    });
  });

  it('impulse_feedback → onImpulseFeedback（cue/reaction_monologue）', () => {
    const { cb, dispatch } = makeClient();
    dispatch(
      JSON.stringify({
        type: 'impulse_feedback',
        channel: 'control',
        v: '1.3',
        ws_seq: 0,
        injected: true,
        cue: 'hesitation',
        reaction_monologue: { form: 'thought', content: '心里一颤。' },
      }),
    );
    expect(cb.onImpulseFeedback).toHaveBeenCalledTimes(1);
    expect(cb.onImpulseFeedback).toHaveBeenCalledWith(
      expect.objectContaining({ cue: 'hesitation', reaction_monologue: { form: 'thought', content: '心里一颤。' } }),
    );
  });

  it('error → onError（ref/code/message）', () => {
    const { cb, dispatch } = makeClient();
    dispatch(
      JSON.stringify({
        type: 'error',
        channel: 'error',
        v: '1.4',
        ws_seq: 0,
        ref: 'player_impulse',
        code: 'bad_impulse',
        message: '这个念头进不去。',
      }),
    );
    expect(cb.onError).toHaveBeenCalledTimes(1);
    expect(cb.onError).toHaveBeenCalledWith(
      expect.objectContaining({ ref: 'player_impulse', message: '这个念头进不去。' }),
    );
  });

  it('control_ack → onControlAck（D11：暂停/倍速权威回执，修前被 default 吞）', () => {
    const { cb, dispatch } = makeClient();
    dispatch(
      JSON.stringify({
        type: 'control_ack',
        channel: 'control',
        v: '1.4',
        ws_seq: 0,
        action: 'pause',
        applied: true,
        paused: true,
      }),
    );
    expect(cb.onControlAck).toHaveBeenCalledTimes(1);
    expect(cb.onControlAck).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'pause', applied: true, paused: true }),
    );
  });

  it('未知类型仍静默忽略（不出错不出戏）', () => {
    const { cb, dispatch } = makeClient();
    expect(() =>
      dispatch(JSON.stringify({ type: 'future_thing', channel: 'narrative', v: '9.9' })),
    ).not.toThrow();
    expect(cb.onMonologue).not.toHaveBeenCalled();
    expect(cb.onImpulseFeedback).not.toHaveBeenCalled();
    expect(cb.onError).not.toHaveBeenCalled();
  });
});
