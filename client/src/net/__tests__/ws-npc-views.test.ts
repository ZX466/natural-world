import { describe, expect, it } from 'vitest';
import type { NpcView } from '../protocol';
import { WsClient, type WsCallbacks } from '../ws';
import { WorldMirror } from '../../game/world-mirror';

const xiaoman: NpcView = {
  rtoken: 'rt_xiaoman',
  name: '小满',
  health: ['她夜里睡得不太安稳。'],
  bond: '她见了陈默会点点头。',
  knows: ['小满: 暗夜惊惧'],
};

function snapshot(npcViews?: NpcView[]) {
  return {
    type: 'full_snapshot',
    channel: 'render',
    v: '1.19',
    ws_seq: 0,
    actors: [],
    lights: [],
    structures: [],
    map: { w: 140, h: 100, tileset: 'linhe-town' },
    time: { day: 1, hour: 5, minute: 10, phase: 'dawn', is_market_day: false },
    ...(npcViews === undefined ? {} : { npc_views: npcViews }),
  };
}

function makeClient() {
  const snapshots: NpcView[][] = [];
  const deltas: unknown[] = [];
  const cb: WsCallbacks = {
    onStatus: () => {},
    onSnapshot: () => {},
    onDelta: (msg) => deltas.push(msg),
    onNpcViews: (items) => snapshots.push(items),
  };
  const client = new WsClient('ws://test', new WorldMirror(), cb);
  const dispatch = (frame: unknown) =>
    (client as unknown as { dispatch(raw: string): void }).dispatch(JSON.stringify(frame));
  return { snapshots, deltas, dispatch };
}

describe('WsClient npc_views', () => {
  it('delivers one complete group for each snapshot, including reconnect', () => {
    const { snapshots, dispatch } = makeClient();
    dispatch(snapshot([xiaoman]));
    dispatch(snapshot([xiaoman]));
    expect(snapshots).toEqual([[xiaoman], [xiaoman]]);
  });

  it.each([
    { label: 'missing field', rows: undefined },
    { label: 'empty array', rows: [] },
  ])('delivers an empty replacement for $label', ({ rows }) => {
    const { snapshots, dispatch } = makeClient();
    dispatch(snapshot([xiaoman]));
    dispatch(snapshot(rows));
    expect(snapshots).toEqual([[xiaoman], []]);
  });

  it('keeps delta upserts and removals on the delta callback', () => {
    const { snapshots, deltas, dispatch } = makeClient();
    const delta = {
      type: 'state_delta',
      channel: 'render',
      v: '1.19',
      ws_seq: 1,
      actors: [],
      npc_views: [xiaoman, { rtoken: 'rt_departed', op: 'remove' }],
    };
    dispatch(delta);
    expect(deltas).toEqual([delta]);
    expect(snapshots).toEqual([]);
  });
});
